#Embedded file name: ACEStream\Core\Subtitles\SubtitlesSupport.pyo
from ACEStream.Core.Subtitles.MetadataDomainObjects.Languages import LanguagesProvider
from ACEStream.Core.Subtitles.MetadataDomainObjects.MetadataDTO import MetadataDTO
from ACEStream.Core.Subtitles.MetadataDomainObjects.MetadataExceptions import RichMetadataException
from ACEStream.Core.Subtitles.MetadataDomainObjects.SubtitleInfo import SubtitleInfo
from ACEStream.Core.Utilities import utilities
from ACEStream.Core.Utilities.utilities import isValidPermid, bin2str
import sys
import threading
DEBUG = False

class SubtitlesSupport(object):
    __single = None
    _singletonLock = threading.RLock()

    def __init__(self):
        try:
            SubtitlesSupport._singletonLock.acquire()
            SubtitlesSupport.__single = self
        finally:
            SubtitlesSupport._singletonLock.release()

        self.richMetadata_db = None
        self.subtitlesHandler = None
        self.channelcast_db = None
        self.langUtility = LanguagesProvider.getLanguagesInstance()
        self._registered = False

    @staticmethod
    def getInstance(*args, **kw):
        try:
            SubtitlesSupport._singletonLock.acquire()
            if SubtitlesSupport.__single == None:
                SubtitlesSupport(*args, **kw)
        finally:
            SubtitlesSupport._singletonLock.release()

        return SubtitlesSupport.__single

    def _register(self, richMetadataDBHandler, subtitlesHandler, channelcast_db, my_permid, my_keypair, peersHaveManger, ol_bridge):
        self.richMetadata_db = richMetadataDBHandler
        self.subtitlesHandler = subtitlesHandler
        self.channelcast_db = channelcast_db
        self.my_permid = my_permid
        self.my_keypair = my_keypair
        self._peersHaveManager = peersHaveManger
        self._ol_bridge = ol_bridge
        self._registered = True

    def getSubtileInfosForInfohash(self, infohash):
        returnDictionary = dict()
        metadataDTOs = self.richMetadata_db.getAllMetadataForInfohash(infohash)
        for metadataDTO in metadataDTOs:
            channel = metadataDTO.channel
            subtitles = metadataDTO.getAllSubtitles()
            if len(subtitles) > 0:
                returnDictionary[channel] = subtitles

        return returnDictionary

    def getSubtitleInfos(self, channel, infohash):
        metadataDTO = self.richMetadata_db.getMetadata(channel, infohash)
        if metadataDTO:
            return metadataDTO.getAllSubtitles()
        return {}

    def publishSubtitle(self, infohash, lang, pathToSrtSubtitle):
        channelid = bin2str(self.my_permid)
        base64infohash = bin2str(infohash)
        consinstent = self.channelcast_db.isItemInChannel(channelid, base64infohash)
        if not consinstent:
            msg = 'Infohash %s not found in my channel. Rejecting subtitle' % base64infohash
            if DEBUG:
                print >> sys.stderr, msg
            raise RichMetadataException(msg)
        try:
            filepath = self.subtitlesHandler.copyToSubtitlesFolder(pathToSrtSubtitle, self.my_permid, infohash, lang)
        except Exception as e:
            if DEBUG:
                print >> sys.stderr, 'Failed to read and copy subtitle to appropriate folder: %s' % str(e)

        metadataDTO = self.richMetadata_db.getMetadata(self.my_permid, infohash)
        if metadataDTO is None:
            metadataDTO = MetadataDTO(self.my_permid, infohash)
        else:
            metadataDTO.resetTimestamp()
        newSubtitle = SubtitleInfo(lang, filepath)
        if newSubtitle.subtitleExists():
            newSubtitle.computeChecksum()
        else:
            msg = 'Inconsistency found. The subtitle was not published'
            if DEBUG:
                print >> sys.stderr, msg
            raise RichMetadataException(msg)
        metadataDTO.addSubtitle(newSubtitle)
        metadataDTO.sign(self.my_keypair)
        self.richMetadata_db.insertMetadata(metadataDTO)

    def retrieveSubtitleContent(self, channel, infohash, subtitleInfo, callback = None):
        if subtitleInfo.subtitleExists():
            if subtitleInfo.verifyChecksum():
                callback(subtitleInfo)
                return
            if DEBUG:
                print >> sys.stderr, 'Subtitle is locally available but has invalid checksum. Issuing another download'
            subtitleInfo.path = None
        languages = [subtitleInfo.lang]

        def call_me_when_subtitle_arrives(listOfLanguages):
            if callback is not None:
                sub = self.richMetadata_db.getSubtitle(channel, infohash, listOfLanguages[0])
                callback(sub)

        self._queryPeersForSubtitles(channel, infohash, languages, call_me_when_subtitle_arrives)

    def retrieveMultipleSubtitleContents(self, channel, infohash, listOfSubInfos, callback = None):
        languages = []
        locallyAvailableSubs = []
        for subtitleInfo in listOfSubInfos:
            if subtitleInfo.checksum is None:
                if DEBUG:
                    print >> sys.stderr, 'No checksum for subtitle %s. Skipping it in the request' % subtitleInfo
                continue
            if subtitleInfo.subtitleExists():
                if subtitleInfo.verifyChecksum():
                    locallyAvailableSubs.append(subtitleInfo)
                    continue
                else:
                    if DEBUG:
                        print >> sys.stderr, 'Subtitle is locally available but has invalid checksum. Issuing another download'
                    subtitleInfo.path = None
            languages.append(subtitleInfo.lang)

        if len(locallyAvailableSubs) > 0 and callback is not None:
            callback(locallyAvailableSubs)

        def call_me_when_subtitles_arrive(listOfLanguages):
            if callback is not None:
                subInfos = list()
                allSubtitles = self.richMetadata_db.getAllSubtitles(channel, infohash)
                for lang in listOfLanguages:
                    subInfos.append(allSubtitles[lang])

                callback(subInfos)

        if len(languages) > 0:
            self._queryPeersForSubtitles(channel, infohash, languages, call_me_when_subtitles_arrive)

    def _queryPeersForSubtitles(self, channel, infohash, languages, callback):

        def task():
            bitmask = self.langUtility.langCodesToMask(languages)
            if not bitmask > 0:
                if DEBUG:
                    print >> sys.stderr, 'Will not send a request for 0 subtitles'
                return
            peers_to_query = self._peersHaveManager.getPeersHaving(channel, infohash, bitmask)
            for peer in peers_to_query:
                self.subtitlesHandler.sendSubtitleRequest(peer, channel, infohash, languages, callback)

        self._ol_bridge.add_task(task)

    def runDBConsinstencyRoutine(self):
        result = self.richMetadata_db.getAllLocalSubtitles()
        for channel in result:
            for infohash in result[channel]:
                for subInfo in result[channel][infohash]:
                    if not subInfo.subtitleExists():
                        if channel == self.my_permid:
                            metadataDTO = self.richMetadata_db.getMetadata(channel, infohash)
                            metadataDTO.removeSubtitle(subInfo.lang)
                            metadataDTO.sign(self.my_keypair)
                            self.richMetadata_db.insertMetadata(metadataDTO)
                        else:
                            self.richMetadata_db.updateSubtitlePath(channel, infohash, subInfo.lang, None)
