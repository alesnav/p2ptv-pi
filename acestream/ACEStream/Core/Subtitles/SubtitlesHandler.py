#Embedded file name: ACEStream\Core\Subtitles\SubtitlesHandler.pyo
from __future__ import with_statement
from ACEStream.Core.Subtitles.MetadataDomainObjects.Languages import LanguagesProvider
from ACEStream.Core.Subtitles.MetadataDomainObjects.MetadataExceptions import MetadataDBException, RichMetadataException
from ACEStream.Core.CacheDB.Notifier import Notifier
from ACEStream.Core.Subtitles.SubtitleHandler.SimpleTokenBucket import SimpleTokenBucket
from ACEStream.Core.Subtitles.SubtitleHandler.SubsMessageHandler import SubsMessageHandler
from ACEStream.Core.Utilities import utilities
from ACEStream.Core.Utilities.TSCrypto import sha
from ACEStream.Core.Utilities.utilities import bin2str, show_permid_short
from ACEStream.Core.simpledefs import NTFY_ACT_DISK_FULL, NTFY_SUBTITLE_CONTENTS, NTFY_UPDATE
import os
import sys
from shutil import copyfile
SUBS_EXTENSION = '.srt'
SUBS_LOG_PREFIX = 'subtitles: '
MAX_SUBTITLE_SIZE = 1 * 1024 * 1024
MAX_SUBS_MESSAGE_SIZE = int(2 * MAX_SUBTITLE_SIZE / 1024)
DEBUG = False

class SubtitlesHandler(object):
    __single = None

    def __init__(self):
        SubtitlesHandler.__single = self
        self.languagesUtility = LanguagesProvider.getLanguagesInstance()
        self.subtitlesDb = None
        self.registered = False
        self.subs_dir = None

    @staticmethod
    def getInstance(*args, **kw):
        if SubtitlesHandler.__single is None:
            SubtitlesHandler(*args, **kw)
        return SubtitlesHandler.__single

    def register(self, overlay_bridge, metadataDBHandler, session):
        self.overlay_bridge = overlay_bridge
        self.subtitlesDb = metadataDBHandler
        self.config_dir = os.path.abspath(session.get_state_dir())
        subs_path = os.path.join(self.config_dir, session.get_subtitles_collecting_dir())
        self.subs_dir = os.path.abspath(session.get_subtitles_collecting_dir())
        self._upload_rate = session.get_subtitles_upload_rate()
        self.max_subs_message_size = MAX_SUBS_MESSAGE_SIZE
        self._session = session
        tokenBucket = SimpleTokenBucket(self._upload_rate, self.max_subs_message_size)
        self._subsMsgHndlr = SubsMessageHandler(self.overlay_bridge, tokenBucket, MAX_SUBTITLE_SIZE)
        self._subsMsgHndlr.registerListener(self)
        if os.path.isdir(self.config_dir):
            if not os.path.isdir(self.subs_dir):
                try:
                    os.mkdir(self.subs_dir)
                except:
                    msg = u'Cannot create collecting dir %s ' % self.subs_dir
                    print >> sys.stderr, 'Error: %s' % msg
                    raise IOError(msg)

        else:
            msg = u'Configuration dir %s does not exists' % self.subs_dir
            print >> sys.stderr, 'Error: %s' % msg
            raise IOError(msg)
        self._notifier = Notifier.getInstance()
        self.registered = True

    def sendSubtitleRequest(self, permid, channel_id, infohash, languages, callback = None, selversion = -1):
        if DEBUG:
            print >> sys.stderr, SUBS_LOG_PREFIX + 'preparing to send GET_SUBS to ' + utilities.show_permid_short(permid)
        if len(languages) == 0:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + ' no subtitles to request.'
            return
        requestDetails = dict()
        requestDetails['channel_id'] = channel_id
        requestDetails['infohash'] = infohash
        requestDetails['languages'] = languages
        self._subsMsgHndlr.sendSubtitleRequest(permid, requestDetails, lambda e, d, c, i, b: self._subsRequestSent(e, d, c, i, b), callback, selversion)

    def _subsRequestSent(self, exception, dest, channel_id, infohash, bitmask):
        pass

    def receivedSubsRequest(self, permid, request, selversion):
        channel_id, infohash, languages = request
        allSubtitles = self.subtitlesDb.getAllSubtitles(channel_id, infohash)
        contentsList = {}
        for lang in sorted(languages):
            if lang in allSubtitles.keys():
                if allSubtitles[lang].subtitleExists():
                    content = self._readSubContent(allSubtitles[lang].path)
                    if content is not None:
                        contentsList[lang] = content
                else:
                    if DEBUG:
                        print >> sys.stderr, SUBS_LOG_PREFIX + 'File not available for channel %s, infohash %s, lang %s' % (show_permid_short(channel_id), bin2str(infohash), lang)
                    self.subtitlesDb.updateSubtitlePath(channel_id, infohash, lang, None)
            elif DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Subtitle not available for channel %s, infohash %s, lang %s' % (show_permid_short(channel_id), bin2str(infohash), lang)

        if len(contentsList) == 0:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'None of the requested subtitles were available. No answer will be sent to %s' % show_permid_short(permid)
            return True
        return self._subsMsgHndlr.sendSubtitleResponse(permid, (channel_id, infohash, contentsList), selversion)

    def _readSubContent(self, path):
        try:
            fileName = path
            file = open(fileName, 'rb')
            fileContent = file.read()
            file.close()
        except IOError as e:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Error reading from subs file %s: %s' % (relativeName, e)
            fileContent = None

        if fileContent and len(fileContent) <= MAX_SUBTITLE_SIZE:
            return fileContent
        print >> sys.stderr, 'Warning: Subtitle %s dropped. Bigger than %d' % (relativeName, MAX_SUBTITLE_SIZE)

    def _subs_send_callback(self, exception, permid):
        if exception is not None:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Failed to send metadata to %s: %s' % (show_permid_short(permid), str(exception))

    def receivedSubsResponse(self, permid, msg, callbacks, selversion):
        channel_id, infohash, contentsDictionary = msg
        metadataDTO = self.subtitlesDb.getMetadata(channel_id, infohash)
        filepaths = dict()
        somethingToWrite = False
        for lang, subtitleContent in contentsDictionary.iteritems():
            try:
                filename = self._saveSubOnDisk(channel_id, infohash, lang, subtitleContent)
                filepaths[lang] = filename
            except IOError as e:
                if DEBUG:
                    print >> sys.stderr, SUBS_LOG_PREFIX + 'Unable to save subtitle for channel %s and infohash %s to file: %s' % (show_permid_short(channel_id), str(infohash), e)
                continue
            except Exception as e:
                if DEBUG:
                    print >> sys.stderr, 'Unexpected error copying subtitle On Disk: ' + str(e)
                raise e

            subToUpdate = metadataDTO.getSubtitle(lang)
            if subToUpdate is None:
                print >> sys.stderr, 'Warning:' + SUBS_LOG_PREFIX + 'Subtitles database inconsistency.'
                raise MetadataDBException('Subtitles database inconsistency!')
            subToUpdate.path = filename
            if not subToUpdate.verifyChecksum():
                if DEBUG:
                    print >> sys.stderr, 'Received a subtitle having invalid checsum from %s' % show_permid_short(permid)
                subToUpdate.path = None
                os.remove(filename)
                continue
            self.subtitlesDb.updateSubtitlePath(channel_id, infohash, subToUpdate.lang, filename, False)
            somethingToWrite = True

        if somethingToWrite:
            self.subtitlesDb.commit()
        if DEBUG:
            print >> sys.stderr, 'Subtitle written on disk and informations on database.'
        if callbacks:
            self._scheduleUserCallbacks(callbacks)
        return True

    def _scheduleUserCallbacks(self, callbacks):

        def call_helper(callback, listOfLanguages):
            self.overlay_bridge.add_task(lambda : callback(listOfLanguages))

        for callback, bitmask in callbacks:
            listOfLanguages = self.languagesUtility.maskToLangCodes(bitmask)
            call_helper(callback, listOfLanguages)

    def _saveSubOnDisk(self, channel_id, infohash, lang, subtitleContent):
        filename = getSubtitleFileRelativeName(channel_id, infohash, lang)
        filename = os.path.join(self.subs_dir, filename)
        file = open(filename, 'wb')
        file.write(subtitleContent)
        file.close()
        return filename

    def _notify_sub_is_in(self, channel_id, infohash, langCode, filename):
        if DEBUG:
            print >> sys.stderr, SUBS_LOG_PREFIX + 'Subtitle is in at' + filename
        if self._notifier is not None:
            self.notifier.notify(NTFY_SUBTITLE_CONTENTS, NTFY_UPDATE, (channel_id, infohash), langCode, filename)

    def setUploadRate(self, uploadRate):
        self._upload_rate = float(uploadRate)
        self._subsMsgHndlr._tokenBucket.fill_rate = float(uploadRate)

    def getUploadRate(self):
        return self._upload_rate

    def delUploadRate(self):
        raise RuntimeError('Operation not supported')

    upload_rate = property(getUploadRate, setUploadRate, delUploadRate, 'Controls the subtitles uploading rate. Expressed in KB/s')

    def copyToSubtitlesFolder(self, pathToMove, channel_id, infohash, langCode):
        if not os.path.isfile(pathToMove):
            raise RichMetadataException('File not found.')
        if os.path.getsize(pathToMove) >= MAX_SUBTITLE_SIZE:
            raise RichMetadataException('Subtitle bigger then %d KBs' % (MAX_SUBTITLE_SIZE / 1024))
        if not pathToMove.endswith(SUBS_EXTENSION):
            raise RichMetadataException('Only .srt subtitles are supported')
        filename = getSubtitleFileRelativeName(channel_id, infohash, langCode)
        filename = os.path.join(self.subs_dir, filename)
        copyfile(pathToMove, filename)
        return filename

    def getMessageHandler(self):
        return self._subsMsgHndlr.handleMessage


def getSubtitleFileRelativeName(channel_id, infohash, langCode):
    hasher = sha()
    for data in (channel_id, infohash, langCode):
        hasher.update(data)

    subtitleName = hasher.hexdigest() + SUBS_EXTENSION
    return subtitleName
