#Embedded file name: ACEStream\Core\Subtitles\MetadataDomainObjects\SubtitleInfo.pyo
from __future__ import with_statement
from ACEStream.Core.Subtitles.MetadataDomainObjects.Languages import LanguagesProvider
import base64
import codecs
import hashlib
import os.path
import sys
DEBUG = False

class SubtitleInfo(object):

    def __init__(self, lang, path = None, checksum = None):
        self._languages = LanguagesProvider.getLanguagesInstance()
        if lang not in self._languages.supportedLanguages.keys():
            raise ValueError('Language' + lang + ' not supported')
        self._lang = lang
        self._path = path
        self._checksum = checksum

    def getLang(self):
        return self._lang

    lang = property(getLang)

    def setPath(self, path):
        self._path = path

    def getPath(self):
        return self._path

    path = property(getPath, setPath)

    def setChecksum(self, checksum):
        self._checksum = checksum

    def getChecksum(self):
        return self._checksum

    checksum = property(getChecksum, setChecksum)

    def subtitleExists(self):
        if self.path is None:
            return False
        return os.path.isfile(self.path)

    def computeChecksum(self):
        self.checksum = self._doComputeChecksum()

    def _doComputeChecksum(self):
        try:
            with codecs.open(self.path, 'rb', 'utf-8', 'replace') as subFile:
                content = subFile.read()
            hasher = hashlib.sha1()
            hasher.update(content.encode('utf-8', 'replace'))
            return hasher.digest()
        except IOError:
            print >> sys.stderr, 'Warning: Unable to open ' + self.path + ' for reading'

    def verifyChecksum(self):
        computed = self._doComputeChecksum()
        return computed == self.checksum

    def __str__(self):
        if self.path is not None:
            path = self.path
        else:
            path = 'None'
        return 'subtitle: [lang=' + self.lang + '; path=' + path + '; sha1=' + base64.encodestring(self.checksum).rstrip() + ']'

    def __eq__(self, other):
        if self is other:
            return True
        return self.lang == other.lang and self.checksum == other.checksum

    def __ne__(self, other):
        return not self.__eq__(other)
