#Embedded file name: ACEStream\Core\Subtitles\RichMetadataInterceptor.pyo
import sys
from ACEStream.Core.Subtitles.MetadataDomainObjects.MetadataDTO import deserialize
from ACEStream.Core.Subtitles.MetadataDomainObjects.MetadataExceptions import SerializationException, RichMetadataException
from ACEStream.Core.Utilities.utilities import isValidPermid, bin2str, show_permid_short
from copy import copy
from struct import pack, unpack
from ACEStream.Core.simpledefs import NTFY_RICH_METADATA, NTFY_UPDATE, NTFY_INSERT
DEBUG = False

class RichMetadataInterceptor(object):

    def __init__(self, metadataDbHandler, voteCastDBHandler, myPermId, subSupport = None, peerHaveManager = None, notifier = None):
        self.rmdDb = metadataDbHandler
        self.votecastDB = voteCastDBHandler
        self.my_permid = myPermId
        self.subSupport = subSupport
        self.peerHaveManager = peerHaveManager
        self.notifier = notifier

    def _splitChannelcastAndRichMetadataContents(self, enrichedChannelcastMessage):
        if not isinstance(enrichedChannelcastMessage, dict):
            if DEBUG:
                print >> sys.stderr, 'Invalid channelcast message received'
            return
        rmdData = list()
        for signature in iter(enrichedChannelcastMessage):
            msg = enrichedChannelcastMessage[signature]
            if 'rich_metadata' in msg.keys():
                metadataEntry = msg['rich_metadata']
                if metadataEntry is None or not validMetadataEntry(metadataEntry):
                    continue
                else:
                    channel_id = msg['publisher_id']
                    infohash = msg['infohash']
                    binary_havemask = metadataEntry.pop(-1)
                    havemask, = unpack('!L', binary_havemask)
                    metadataEntry.insert(0, infohash)
                    metadataEntry.insert(0, channel_id)
                    try:
                        curMetadataDTO = deserialize(metadataEntry)
                    except SerializationException as e:
                        if DEBUG:
                            print >> sys.stderr, 'Invalid metadata message content: %s' % e
                        continue

                    rmdData.append((curMetadataDTO, havemask))

        return rmdData

    def handleRMetadata(self, sender_permid, channelCastMessage, fromQuery = False):
        metadataDTOs = self._splitChannelcastAndRichMetadataContents(channelCastMessage)
        if DEBUG:
            print >> sys.stderr, 'Handling rich metadata from %s...' % show_permid_short(sender_permid)
        for md_and_have in metadataDTOs:
            md = md_and_have[0]
            havemask = md_and_have[1]
            vote = self.votecastDB.getVote(bin2str(md.channel), bin2str(self.my_permid))
            if DEBUG:
                id = 'RQ' if fromQuery else 'R'
                print >> sys.stderr, '%s, %s, %s, %s, %d' % (id,
                 md.channel,
                 md.infohash,
                 show_permid_short(sender_permid),
                 md.timestamp)
            if vote == -1:
                continue
            isUpdate = self.rmdDb.insertMetadata(md)
            self.peerHaveManager.newHaveReceived(md.channel, md.infohash, sender_permid, havemask)
            if isUpdate is not None:
                md = self.rmdDb.getMetadata(md.channel, md.infohash)
                self._notifyRichMetadata(md, isUpdate)
            if vote == 2:
                if DEBUG:
                    print >> sys.stderr, 'Subscribed to channel %s, trying to retrieveall subtitle contents' % (show_permid_short(md.channel),)
                self._getAllSubtitles(md)

    def _computeSize(self, msg):
        import ACEStream.Core.BitTornado.bencode as bencode
        bencoded = bencode.bencode(msg)
        return len(bencoded)

    def _notifyRichMetadata(self, metadataDTO, isUpdate):
        if self.notifier is not None:
            eventType = NTFY_UPDATE if isUpdate else NTFY_INSERT
            self.notifier.notify(NTFY_RICH_METADATA, eventType, (metadataDTO.channel, metadataDTO.infohash))

    def _getAllSubtitles(self, md):
        subtitles = md.getAllSubtitles()
        try:
            self.subSupport.retrieveMultipleSubtitleContents(md.channel, md.infohash, subtitles.values())
        except RichMetadataException as e:
            print >> sys.stderr, 'Warning: Retrievement of all subtitles failed: ' + str(e)

    def addRichMetadataContent(self, channelCastMessage, destPermid = None, fromQuery = False):
        if not len(channelCastMessage) > 0:
            if DEBUG:
                print >> sys.stderr, 'no entries to enrich with rmd'
            return channelCastMessage
        if DEBUG:
            if fromQuery:
                print >> sys.stderr, 'Intercepted a channelcast message as answer to a query'
            else:
                print >> sys.stderr, 'Intercepted a channelcast message as normal channelcast'
        doesChannelHaveSubtitles = {}
        for key, content in channelCastMessage.iteritems():
            channel_id = content['publisher_id']
            infohash = content['infohash']
            if channel_id not in doesChannelHaveSubtitles:
                doesChannelHaveSubtitles[channel_id] = self.rmdDb.getNrMetadata(channel_id) > 0
            if doesChannelHaveSubtitles[channel_id]:
                metadataDTO = self.rmdDb.getMetadata(channel_id, infohash)
                if metadataDTO is not None:
                    try:
                        if DEBUG:
                            print >> sys.stderr, 'Enriching a channelcast message with subtitle contents'
                        metadataPack = metadataDTO.serialize()
                        metadataPack.pop(0)
                        metadataPack.pop(0)
                        havemask = self.peerHaveManager.retrieveMyHaveMask(channel_id, infohash)
                        binary_havemask = pack('!L', havemask)
                        metadataPack.append(binary_havemask)
                        content['rich_metadata'] = metadataPack
                        if DEBUG:
                            size = self._computeSize(metadataPack)
                            dest = 'NA' if destPermid is None else show_permid_short(destPermid)
                            id = 'SQ' if fromQuery else 'S'
                            print >> sys.stderr, '%s, %s, %s, %s, %d, %d' % (id,
                             bin2str(metadataDTO.channel),
                             bin2str(metadataDTO.infohash),
                             dest,
                             metadataDTO.timestamp,
                             size)
                    except Exception as e:
                        print >> sys.stderr, 'Warning: Error serializing metadata: %s', str(e)

        return channelCastMessage


def validMetadataEntry(entry):
    if entry is None or len(entry) != 6:
        if DEBUG:
            print >> sys.stderr, 'An invalid metadata entry was found in channelcast message'
        return False
    if not isinstance(entry[1], int) or entry[1] <= 0:
        if DEBUG:
            print >> sys.stderr, 'Invalid rich metadata: invalid timestamp'
        return False
    if not isinstance(entry[2], basestring) or not len(entry[2]) == 4:
        if DEBUG:
            print >> sys.stderr, 'Invalid rich metadata: subtitles mask'
        return False
    if not isinstance(entry[3], list):
        if DEBUG:
            print >> sys.stderr, "Invalid rich metadata: subtitles' checsums"
        return False
    for checksum in entry[3]:
        if not isinstance(entry[2], basestring) or not len(checksum) == 20:
            if DEBUG:
                print >> sys.stderr, "Invalid rich metadata: subtitles' checsums"
            return False

    if not isinstance(entry[2], basestring) or not len(entry[5]) == 4:
        if DEBUG:
            print >> sys.stderr, 'Invalid rich metadata: have mask'
        return False
    return True
