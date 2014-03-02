#Embedded file name: ACEStream\Player\UtilityStub.pyo
import sys
import os
import locale
from traceback import print_exc
from ACEStream.Lang.lang import Lang

class UtilityStub:

    def __init__(self, installdir, statedir):
        self.installdir = installdir
        self.statedir = statedir
        self.config = self
        try:
            lang_code, encoding = locale.getdefaultlocale()
            self.encoding = encoding
            self.lang = Lang(self, lang_code)
        except:
            print_exc()
            self.lang = Lang(self)
            self.encoding = None

    def getConfigPath(self):
        return self.statedir

    def getPath(self):
        enc = sys.getfilesystemencoding()
        if enc is None:
            enc = self.encoding
        if enc is not None:
            return self.installdir.decode(enc)
        else:
            return self.installdir

    def Read(self, key):
        if key == 'videoplayerpath':
            return 'vlc'
