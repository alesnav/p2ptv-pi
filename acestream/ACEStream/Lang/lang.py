#Embedded file name: ACEStream\Lang\lang.pyo
import sys
import os
from traceback import print_exc, print_stack
from cStringIO import StringIO
from ACEStream.GlobalConfig import globalConfig
from ACEStream.Core.Session import Session
from ACEStream.Utilities.configreader import ConfigReader
from ACEStream.Core.BitTornado.__init__ import version_id

class Lang:

    def __init__(self, utility, system_default_locale = 'en_EN'):
        self.utility = utility
        default_filename = 'en_EN.lang'
        langpath = os.path.join(self.utility.getPath(), 'data', 'lang')
        sys.stdout.write('Setting up languages\n')
        sys.stdout.write('Default: ' + str(default_filename) + '\n')
        sys.stdout.write('System: ' + str(system_default_locale) + '\n')
        self.user_lang = None
        user_filepath = os.path.join(self.utility.getConfigPath(), 'user.lang')
        if existsAndIsReadable(user_filepath):
            self.user_lang = ConfigReader(user_filepath, 'ABC/language')
        parsed_locale = self.parse_locale(system_default_locale)
        self.local_lang_filename = parsed_locale + '.lang'
        self.local_lang = None
        local_filepath = os.path.join(langpath, self.local_lang_filename)
        if self.local_lang_filename != default_filename and existsAndIsReadable(local_filepath):
            if globalConfig.get_mode() == 'client_wx':
                import wx
                self.local_lang = wx.FileConfig(localFilename=local_filepath)
                self.local_lang.SetPath('ABC/language')
            else:
                self.local_lang = ConfigReader(local_filepath, 'ABC/language')
        self.default_lang = None
        default_filepath = os.path.join(langpath, default_filename)
        if existsAndIsReadable(default_filepath):
            self.default_lang = ConfigReader(default_filepath, 'ABC/language')
        self.cache = {}
        self.langwarning = False

    def parse_locale(self, locale_name):
        if locale_name.startswith('en'):
            return 'en_EN'
        elif locale_name.startswith('ru'):
            return 'ru_RU'
        else:
            return locale_name

    def flush(self):
        if self.user_lang is not None:
            try:
                self.user_lang.DeleteEntry('dummyparam', False)
            except:
                pass

            self.user_lang.Flush()
        self.cache = {}

    def get(self, label, tryuser = True, trylocal = True, trydefault = True, giveerror = True):
        if tryuser and trylocal and trydefault:
            tryall = True
        else:
            tryall = False
        if tryall and label in self.cache:
            return self.expandEnter(self.cache[label])
        if label == 'version':
            return version_id
        if label == 'build':
            return 'Build 19721'
        if label == 'build_date':
            return 'May 19, 2011'
        if tryuser:
            text, found = self.getFromLanguage(label, self.user_lang)
            if found:
                if tryall:
                    self.cache[label] = text
                return self.expandEnter(text)
        if trylocal and self.local_lang is not None:
            text, found = self.getFromLanguage(label, self.local_lang, giveerror=True)
            if found:
                if tryall:
                    self.cache[label] = text
                return self.expandEnter(text)
        if trydefault:
            text, found = self.getFromLanguage(label, self.default_lang)
            if found:
                if tryall:
                    self.cache[label] = text
                return self.expandEnter(text)
        if giveerror:
            sys.stdout.write('Language file: Got an error finding: ' + label)
            self.error(label)
        return label

    def expandEnter(self, text):
        text = text.replace('\\r', '\n')
        text = text.replace('\\n', '\n')
        return text

    def getFromLanguage(self, label, langfile, giveerror = False):
        try:
            if langfile is not None:
                if langfile.Exists(label):
                    return (self.getSingleline(label, langfile), True)
                if langfile.Exists(label + '_line1'):
                    return (self.getMultiline(label, langfile), True)
                if giveerror:
                    self.error(label, silent=True)
        except:
            fileused = ''
            langfilenames = {'user.lang': self.user_lang,
             self.local_lang_filename: self.local_lang,
             self.default_lang_filename: self.default_lang}
            for name in langfilenames:
                if langfilenames[name] == langfile:
                    fileused = name
                    break

            sys.stderr.write('Error reading language file: (' + fileused + '), label: (' + label + ')\n')
            data = StringIO()
            print_exc(file=data)
            sys.stderr.write(data.getvalue())

        return ('', False)

    def getSingleline(self, label, langfile):
        return langfile.Read(label)

    def getMultiline(self, label, langfile):
        i = 1
        text = ''
        while langfile.Exists(label + '_line' + str(i)):
            if i != 1:
                text += '\n'
            text += langfile.Read(label + '_line' + str(i))
            i += 1

        if not text:
            sys.stdout.write('Language file: Got an error reading multiline string\n')
            self.error(label)
        return text

    def writeUser(self, label, text):
        change = False
        text_user = self.get(label, trylocal=False, trydefault=False, giveerror=False)
        text_nonuser = self.get(label, tryuser=False, giveerror=False)
        user_lang = self.user_lang
        if text == text_nonuser:
            if text_user != '':
                user_lang.Write('exampleparam', 'example value')
                user_lang.DeleteEntry(label)
                change = True
        elif text != text_user:
            user_lang.Write(label, text)
            change = True
        return change

    def error(self, label, silent = True):
        if not self.langwarning:
            self.langwarning = True
            error_title = self.get('error')
            error_text = self.get('errorlanguagefile')
            if error_text == '':
                error_text = 'Your language file is missing at least one string.\nPlease check to see if an updated version is available.'
        sys.stderr.write('\nError reading language file!\n')
        sys.stderr.write('  Cannot find value for variable: ' + label + '\n')


def existsAndIsReadable(filename):
    return os.access(filename, os.F_OK) and os.access(filename, os.R_OK)
