#Embedded file name: ACEStream\Core\Subtitles\MetadataDomainObjects\MetadataDTO.pyo
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
from ACEStream.Core.Subtitles.MetadataDomainObjects.Languages import LanguagesProvider
from ACEStream.Core.Subtitles.MetadataDomainObjects.MetadataExceptions import SerializationException
from ACEStream.Core.Subtitles.MetadataDomainObjects.SubtitleInfo import SubtitleInfo
from ACEStream.Core.Overlay.permid import sign_data, verify_data
from ACEStream.Core.Utilities.utilities import isValidInfohash, isValidPermid
from math import floor
from struct import pack, unpack
import sys
import time
DEBUG = False
_languagesUtil = LanguagesProvider.getLanguagesInstance()

class MetadataDTO(object):

    def __init__(self, publisher, infohash, timestamp = None, description = u'', subtitles = None, signature = None):
        self.channel = publisher
        self.infohash = infohash
        if timestamp is not None:
            timestring = int(floor(timestamp))
        else:
            timestring = int(floor(time.time()))
        self.timestamp = timestring
        if isinstance(description, str):
            description = unicode(description, 'utf-8')
        self.description = description
        if subtitles is None:
            subtitles = {}
        self._subtitles = subtitles
        self.signature = signature

    def resetTimestamp(self):
        self.timestamp = int(floor(time.time()))

    def addSubtitle(self, subtitle):
        self._subtitles[subtitle.lang] = subtitle

    def removeSubtitle(self, lang):
        if lang in self._subtitles.keys():
            del self._subtitles[lang]

    def getSubtitle(self, lang):
        if lang not in self._subtitles.keys():
            return None
        else:
            return self._subtitles[lang]

    def getAllSubtitles(self):
        return self._subtitles.copy()

    def sign(self, keypair):
        bencoding = self._packData()
        signature = sign_data(bencoding, keypair)
        self.signature = signature

    def verifySignature(self):
        toVerify = self._packData()
        binaryPermId = self.channel
        return verify_data(toVerify, binaryPermId, self.signature)

    def _packData(self):
        if self.description is not None:
            pass
        if self.description is None:
            self.description = u''
        bitmask, checksums = self._getSubtitlesMaskAndChecksums()
        tosign = (self.channel,
         self.infohash,
         self.description.encode('utf-8'),
         self.timestamp,
         pack('!L', bitmask),
         checksums)
        bencoding = bencode(tosign)
        return bencoding

    def serialize(self):
        if self.signature is None:
            raise SerializationException('The content must be signed')
        pack = bdecode(self._packData())
        pack.append(self.signature)
        return pack

    def _getSubtitlesMaskAndChecksums(self):
        languagesList = []
        checksumsList = []
        sortedKeys = sorted(self._subtitles.keys())
        for key in sortedKeys:
            sub = self._subtitles[key]
            if sub.checksum is None:
                if sub.subtitleExists():
                    sub.computueCheksum()
                else:
                    if DEBUG:
                        print >> sys.stderr, 'Warning: Cannot get checksum for ' + sub.lang + ' subtitle. Skipping it.'
                    continue
            languagesList.append(sub.lang)
            checksumsList.append(sub.checksum)

        bitmask = _languagesUtil.langCodesToMask(languagesList)
        checksums = tuple(checksumsList)
        return (bitmask, checksums)

    def __eq__(self, other):
        if self is other:
            return True
        return self.channel == other.channel and self.infohash == other.infohash and self.description == other.description and self.timestamp == other.timestamp and self.getAllSubtitles() == other.getAllSubtitles()

    def __ne__(self, other):
        return not self.__eq__(other)


def deserialize(packed):
    message = packed
    if len(message) != 7:
        raise SerializationException('Wrong number of fields in metadata')
    channel = message[0]
    infohash = message[1]
    description = message[2].decode('utf-8')
    timestamp = message[3]
    binarybitmask = message[4]
    bitmask, = unpack('!L', binarybitmask)
    listOfChecksums = message[5]
    signature = message[6]
    subtitles = _createSubtitlesDict(bitmask, listOfChecksums)
    dto = MetadataDTO(channel, infohash, timestamp, description, subtitles, signature)
    if not dto.verifySignature():
        raise SerializationException('Invalid Signature!')
    return dto


def _createSubtitlesDict(bitmask, listOfChecksums):
    langList = _languagesUtil.maskToLangCodes(bitmask)
    if len(langList) != len(listOfChecksums):
        raise SerializationException('Unexpected num of checksums')
    subtitles = {}
    for i in range(0, len(langList)):
        sub = SubtitleInfo(langList[i])
        sub.checksum = listOfChecksums[i]
        subtitles[langList[i]] = sub

    return subtitles
