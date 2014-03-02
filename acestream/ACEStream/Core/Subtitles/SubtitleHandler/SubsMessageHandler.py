#Embedded file name: ACEStream\Core\Subtitles\SubtitleHandler\SubsMessageHandler.pyo
from ACEStream.Core.BitTornado.BT1.MessageID import SUBS, GET_SUBS
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
from ACEStream.Core.Subtitles.MetadataDomainObjects.Languages import LanguagesProvider
from ACEStream.Core.Subtitles.MetadataDomainObjects.MetadataExceptions import SubtitleMsgHandlerException
from ACEStream.Core.Overlay.SecureOverlay import OLPROTO_VER_FOURTEENTH
from ACEStream.Core.Utilities import utilities
from ACEStream.Core.Utilities.utilities import show_permid_short, validInfohash, validPermid, bin2str
from time import time
from traceback import print_exc
from struct import pack, unpack
import sys
import threading
SUBS_LOG_PREFIX = 'subtitles: '
REQUEST_VALIDITY_TIME = 10 * 60
CLEANUP_PERIOD = 5 * 60
DEBUG = False

class SubsMessageHandler(object):

    def __init__(self, overlayBridge, tokenBucket, maxSubsSize):
        self._languagesUtility = LanguagesProvider.getLanguagesInstance()
        self._overlay_bridge = overlayBridge
        self._listenersList = list()
        self._tokenBucket = tokenBucket
        self._nextUploadTime = 0
        self.requestedSubtitles = {}
        self._requestsLock = threading.RLock()
        self._nextCleanUpTime = int(time()) + CLEANUP_PERIOD
        self._uploadQueue = []
        self._requestValidityTime = REQUEST_VALIDITY_TIME
        self._maxSubSize = maxSubsSize

    def setTokenBucket(self, tokenBucket):
        self._tokenBucket = tokenBucket

    def getTokenBucket(self):
        return self._tokenBucket

    tokenBucket = property(getTokenBucket, setTokenBucket)

    def _getRequestedSubtitlesKey(self, channel_id, infohash):
        return ''.join((channel_id, infohash))

    def sendSubtitleRequest(self, dest_permid, requestDetails, msgSentCallback = None, usrCallback = None, selversion = -1):
        channel_id = requestDetails['channel_id']
        infohash = requestDetails['infohash']
        languages = requestDetails['languages']
        bitmask = self._languagesUtility.langCodesToMask(languages)
        if bitmask != 0:
            try:
                if selversion == -1:
                    self._overlay_bridge.connect(dest_permid, lambda e, d, p, s: self._get_subs_connect_callback(e, d, p, s, channel_id, infohash, bitmask, msgSentCallback, usrCallback))
                else:
                    self._get_subs_connect_callback(None, None, dest_permid, selversion, channel_id, infohash, bitmask, msgSentCallback, usrCallback)
            except Exception as e:
                if DEBUG:
                    print >> sys.stderr, SUBS_LOG_PREFIX + 'Unable to send: %s' % str(e)
                raise SubtitleMsgHandlerException(e)

        else:
            raise SubtitleMsgHandlerException('Empty request, nothing to send')

    def sendSubtitleResponse(self, destination, response_params, selversion = -1):
        channel_id, infohash, contentsList = response_params
        task = {'permid': destination,
         'channel_id': channel_id,
         'infohash': infohash,
         'subtitles': contentsList,
         'selversion': selversion}
        self._uploadQueue.append(task)
        if int(time()) >= self._nextUploadTime:
            self._checkingUploadQueue()
        return True

    def handleMessage(self, permid, selversion, message):
        t = message[0]
        if t == GET_SUBS:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Got GET_SUBS len: %s from %s' % (len(message), show_permid_short(permid))
            return self._handleGETSUBS(permid, message, selversion)
        elif t == SUBS:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Got SUBS len: %s from %s' % (len(message), show_permid_short(permid))
            return self._handleSUBS(permid, message, selversion)
        else:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Unknown Overlay Message %d' % ord(t)
            return False

    def _handleGETSUBS(self, permid, message, selversion):
        if selversion < OLPROTO_VER_FOURTEENTH:
            if DEBUG:
                print >> sys.stderr, 'The peer that sent the GET_SUBS request has an oldprotcol version: this is strange. Dropping the msg'
            return False
        decoded = self._decodeGETSUBSMessage(message)
        if decoded is None:
            if DEBUG:
                print >> sys.stderr, 'Error decoding a GET_SUBS message from %s' % utilities.show_permid_short(permid)
            return False
        if DEBUG:
            channel_id, infohash, languages = decoded
            bitmask = self._languagesUtility.langCodesToMask(languages)
            print >> sys.stderr, '%s, %s, %s, %s, %d, %d' % ('RG',
             show_permid_short(permid),
             show_permid_short(channel_id),
             bin2str(infohash),
             bitmask,
             len(message))
        for listener in self._listenersList:
            listener.receivedSubsRequest(permid, decoded, selversion)

        return True

    def _handleSUBS(self, permid, message, selversion):
        if selversion < OLPROTO_VER_FOURTEENTH:
            if DEBUG:
                print >> sys.stderr, 'The peer that sent the SUBS request has an oldprotcol version: this is strange. Dropping the msg'
            return False
        decoded = self._decodeSUBSMessage(message)
        if decoded is None:
            if DEBUG:
                print >> sys.stderr, 'Error decoding a SUBS message from %s' % utilities.show_permid_short(permid)
            return False
        channel_id, infohash, bitmask, contents = decoded
        if DEBUG:
            print >> sys.stderr, '%s, %s, %s, %s, %d, %d' % ('RS',
             show_permid_short(permid),
             show_permid_short(channel_id),
             bin2str(infohash),
             bitmask,
             len(message))
        requestedSubs = self._checkRequestedSubtitles(channel_id, infohash, bitmask)
        if requestedSubs == 0:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Received a SUBS message that was not requested. Dropping'
            return False
        requestedSubsCodes = self._languagesUtility.maskToLangCodes(requestedSubs)
        for lang in contents.keys():
            if lang not in requestedSubsCodes:
                del contents[lang]

        callbacks = self._removeFromRequestedSubtitles(channel_id, infohash, bitmask)
        tuple = (channel_id, infohash, contents)
        for listener in self._listenersList:
            listener.receivedSubsResponse(permid, tuple, callbacks, selversion)

        return True

    def registerListener(self, listenerObject):
        self._listenersList.append(listenerObject)

    def _get_subs_connect_callback(self, exception, dns, permid, selversion, channel_id, infohash, bitmask, msgSentCallback, usrCallback):
        if exception is not None:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'GET_SUBS not sent. Unable to connect to ' + utilities.show_permid_short(permid)
        else:
            if selversion > 0 and selversion < OLPROTO_VER_FOURTEENTH:
                msg = 'GET_SUBS not send, the other peers had an old protocol version: %d' % selversion
                if DEBUG:
                    print >> sys.stderr, msg
                raise SubtitleMsgHandlerException(msg)
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'sending GET_SUBS to ' + utilities.show_permid_short(permid)
            try:
                message = self._createGETSUBSMessage(channel_id, infohash, bitmask)
                if DEBUG:
                    print >> sys.stderr, '%s, %s, %s, %s, %d, %d' % ('SG',
                     show_permid_short(permid),
                     show_permid_short(channel_id),
                     bin2str(infohash),
                     bitmask,
                     len(message))
                self._overlay_bridge.send(permid, message, lambda exc, permid: self._sent_callback(exc, permid, channel_id, infohash, bitmask, msgSentCallback, usrCallback))
            except Exception as e:
                print_exc()
                msg = 'GET_SUBS not sent: %s' % str(e)
                raise SubtitleMsgHandlerException(e)

    def _sent_callback(self, exc, permid, channel_id, infohash, bitmask, msgSentCallback, usrCallback):
        if exc is not None:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Unable to send GET_SUBS to: ' + utilities.show_permid_short(permid) + ': ' + exc
        else:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'GET_SUBS sent to %s' % utilities.show_permid_short(permid)
            self._addToRequestedSubtitles(channel_id, infohash, bitmask, usrCallback)
            if msgSentCallback is not None:
                msgSentCallback(exc, permid, channel_id, infohash, bitmask)

    def _createGETSUBSMessage(self, channel_id, infohash, bitmask):
        binaryBitmask = pack('!L', bitmask)
        body = bencode((channel_id, infohash, binaryBitmask))
        head = GET_SUBS
        return head + body

    def _decodeGETSUBSMessage(self, message):
        try:
            values = bdecode(message[1:])
        except:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Error bdecoding message'
            return None

        if len(values) != 3:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Invalid number of fields in GET_SUBS'
            return None
        channel_id, infohash, bitmask = values[0], values[1], values[2]
        if not validPermid(channel_id):
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Invalid channel_id in GET_SUBS'
            return None
        if not validInfohash(infohash):
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Invalid infohash in GET_SUBS'
            return None
        if not isinstance(bitmask, str) or not len(bitmask) == 4:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Invalid bitmask in GET_SUBS'
            return None
        try:
            bitmask, = unpack('!L', bitmask)
            languages = self._languagesUtility.maskToLangCodes(bitmask)
        except:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Invalid bitmask in GET_SUBS'
            return None

        return (channel_id, infohash, languages)

    def _decodeSUBSMessage(self, message):
        try:
            values = bdecode(message[1:])
        except:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Error bdecoding SUBS message'
            return None

        if len(values) != 4:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Invalid number of fields in SUBS'
            return None
        channel_id, infohash, bitmask, contents = (values[0],
         values[1],
         values[2],
         values[3])
        if not validPermid(channel_id):
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Invalid channel_id in SUBS'
            return None
        if not validInfohash(infohash):
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Invalid infohash in SUBS'
            return None
        if not isinstance(bitmask, str) or not len(bitmask) == 4:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Invalid bitmask in SUBS'
            return None
        try:
            bitmask, = unpack('!L', bitmask)
            languages = self._languagesUtility.maskToLangCodes(bitmask)
        except:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Invalid bitmask in SUBS'
            return None

        if not isinstance(contents, list):
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Invalid contents in SUBS'
            return None
        if len(languages) != len(contents):
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Bitmask and contents do not match in SUBS'
            return None
        numOfContents = len(languages)
        if numOfContents == 0:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Empty message. Discarding.'
            return None
        contentsDictionary = dict()
        for i in range(numOfContents):
            lang = languages[i]
            subtitle = contents[i]
            if len(subtitle) <= self._maxSubSize:
                contentsDictionary[lang] = subtitle
            elif DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Dropping subtitle, too large', len(subtitle), self._maxSubSize
            else:
                continue

        bitmask = self._languagesUtility.langCodesToMask(contentsDictionary.keys())
        return (channel_id,
         infohash,
         bitmask,
         contentsDictionary)

    def _checkingUploadQueue(self):
        if DEBUG:
            print >> sys.stderr, SUBS_LOG_PREFIX + 'Checking the upload queue...'
        if not self._tokenBucket.upload_rate > 0:
            return
        if not len(self._uploadQueue) > 0:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'Upload queue is empty.'
        while len(self._uploadQueue) > 0:
            responseData = self._uploadQueue[0]
            encodedMsg = self._createSingleResponseMessage(responseData)
            if encodedMsg is None:
                if DEBUG:
                    print >> sys.stderr, SUBS_LOG_PREFIX + 'Nothing to send'
                del self._uploadQueue[0]
                continue
            msgSize = len(encodedMsg) / 1024.0
            if msgSize > self._tokenBucket.capacity:
                print >> sys.stderr, 'Warning:' + SUBS_LOG_PREFIX + 'SUBS message too big. Discarded!'
                del self._uploadQueue[0]
                continue
            if self._tokenBucket.consume(msgSize):
                if DEBUG:
                    keys = responseData['subtitles'].keys()
                    bitmask = self._languagesUtility.langCodesToMask(keys)
                    print >> sys.stderr, '%s, %s, %s, %s, %d, %d' % ('SS',
                     show_permid_short(responseData['permid']),
                     show_permid_short(responseData['channel_id']),
                     bin2str(responseData['infohash']),
                     bitmask,
                     int(msgSize * 1024))
                self._doSendSubtitles(responseData['permid'], encodedMsg, responseData['selversion'])
                del self._uploadQueue[0]
            else:
                neededCapacity = max(0, msgSize - self._tokenBucket.tokens)
                delay = neededCapacity / self._tokenBucket.upload_rate
                self._nextUploadTime = time() + delay
                self.overlay_bridge.add_task(self._checkingUploadQueue, delay)
                return

    def _createSingleResponseMessage(self, responseData):
        orderedKeys = sorted(responseData['subtitles'].keys())
        payload = list()
        for lang in orderedKeys:
            fileContent = responseData['subtitles'][lang]
            if fileContent is not None and len(fileContent) <= self._maxSubSize:
                payload.append(fileContent)
            else:
                print >> sys.stderr, 'Warning: Subtitle in % for ch: %s, infohash:%s dropped. Bigger then %d' % (lang,
                 responseData['channel_id'],
                 responseData['infohash'],
                 self._maxSubSize)

        if not len(payload) > 0:
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'No payload to send in SUBS'
            return
        bitmask = self._languagesUtility.langCodesToMask(orderedKeys)
        binaryBitmask = pack('!L', bitmask)
        header = (responseData['channel_id'], responseData['infohash'], binaryBitmask)
        message = bencode((header[0],
         header[1],
         header[2],
         payload))
        return SUBS + message

    def _doSendSubtitles(self, permid, msg, selversion):
        if DEBUG:
            print >> sys.stderr, SUBS_LOG_PREFIX + 'Sending SUBS message to %s...' % show_permid_short(permid)
        self._overlay_bridge.send(permid, msg, self._subs_send_callback)

    def _subs_send_callback(self, exc, permid):
        if exc is not None:
            print >> sys.stderr, 'Warning: Sending of SUBS message to %s failed: %s' % (show_permid_short(permid), str(exc))
        elif DEBUG:
            print >> sys.stderr, 'SUBS message succesfully sent to %s' % show_permid_short(permid)

    def _addToRequestedSubtitles(self, channel_id, infohash, bitmask, callback = None):
        if int(time()) >= self._nextCleanUpTime:
            self._cleanUpRequestedSubtitles()
        key = self._getRequestedSubtitlesKey(channel_id, infohash)
        if key in self.requestedSubtitles.keys():
            rsEntry = self.requestedSubtitles[key]
            rsEntry.newRequest(bitmask)
        else:
            rsEntry = _RequestedSubtitlesEntry()
            rsEntry.newRequest(bitmask, callback)
            self.requestedSubtitles[key] = rsEntry

    def _cleanUpRequestedSubtitles(self):
        keys = self.requestedSubtitles.keys()
        now = int(time())
        for key in keys:
            rsEntry = self.requestedSubtitles[key]
            somethingDeleted = rsEntry.cleanUpRequests(self._requestValidityTime)
            if somethingDeleted:
                if DEBUG:
                    print >> sys.stderr, 'Deleting subtitle request for key %s: expired.', key
            if rsEntry.cumulativeBitmask == 0:
                del self.requestedSubtitles[key]

        self._nextCleanUpTime = now + CLEANUP_PERIOD

    def _removeFromRequestedSubtitles(self, channel_id, infohash, bitmask):
        key = self._getRequestedSubtitlesKey(channel_id, infohash)
        if key not in self.requestedSubtitles.keys():
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'asked to remove a subtitle that' + 'was never requested from the requestedList'
            return None
        else:
            rsEntry = self.requestedSubtitles[key]
            callbacks = rsEntry.removeFromRequested(bitmask)
            if rsEntry.cumulativeBitmask == 0:
                del self.requestedSubtitles[key]
            return callbacks

    def _checkRequestedSubtitles(self, channel_id, infohash, bitmask):
        key = self._getRequestedSubtitlesKey(channel_id, infohash)
        if key not in self.requestedSubtitles.keys():
            if DEBUG:
                print >> sys.stderr, SUBS_LOG_PREFIX + 'asked to remove a subtitle that' + 'was never requested from the requested List'
            return 0
        else:
            rsEntry = self.requestedSubtitles[key]
            reqBitmask = rsEntry.cumulativeBitmask & bitmask
            return reqBitmask


class _RequestedSubtitlesEntry():

    def __init__(self):
        self.requestsList = list()
        self.cumulativeBitmask = 0

    def newRequest(self, req_bitmask, callback = None):
        self.requestsList.append([req_bitmask, callback, int(time())])
        self.cumulativeBitmask = int(self.cumulativeBitmask | req_bitmask)

    def removeFromRequested(self, rem_bitmask):
        callbacks = list()
        self.cumulativeBitmask = self.cumulativeBitmask & ~rem_bitmask
        length = len(self.requestsList)
        i = 0
        while i < length:
            entry = self.requestsList[i]
            receivedLangs = entry[0] & rem_bitmask
            if receivedLangs != 0:
                callbacks.append((entry[1], receivedLangs))
                updatedBitmask = entry[0] & ~receivedLangs
                if updatedBitmask == 0:
                    del self.requestsList[i]
                    i -= 1
                    length -= 1
                else:
                    entry[0] = updatedBitmask
            i += 1

        return callbacks

    def cleanUpRequests(self, validityDelta):
        somethingDeleted = False
        now = int(time())
        length = len(self.requestsList)
        i = 0
        while i < length:
            entry = self.requestsList[i]
            requestTime = entry[2]
            if requestTime + validityDelta < now:
                self.cumulativeBitmask = self.cumulativeBitmask & ~entry[0]
                del self.requestsList[i]
                i -= 1
                length -= 1
                somethingDeleted = True
            i += 1

        return somethingDeleted
