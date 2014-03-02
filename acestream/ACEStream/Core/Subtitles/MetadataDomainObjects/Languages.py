#Embedded file name: ACEStream\Core\Subtitles\MetadataDomainObjects\Languages.pyo
from __future__ import with_statement
import csv
import codecs
MAX_SUPPORTED_LANGS = 32
DEFAULT_LANG_CONF_FILE = 'res/subs_languages.csv'

def _loadLanguages(langFilePath):
    languages = {}
    with codecs.open(langFilePath, 'r', 'utf-8') as csvfile:
        csvreader = csv.reader(csvfile)
        for row in csvreader:
            if len(row) != 2:
                raise ValueError('Erroneous format in csv')
            if len(row[0]) != 3:
                raise ValueError('Lang codes must be 3 characters length')
            languages[row[0]] = row[1]

    return languages


_languages = {'ara': 'Arabic',
 'ben': 'Bengali',
 'ces': 'Czech',
 'dan': 'Danish',
 'deu': 'German',
 'ell': 'Greek',
 'eng': 'English',
 'fas': 'Persian',
 'fin': 'Finnish',
 'fra': 'French',
 'hin': 'Hindi',
 'hrv': 'Croatian',
 'hun': 'Hungarian',
 'ita': 'Italian',
 'jav': 'Javanese',
 'jpn': 'Japanese',
 'kor': 'Korean',
 'lit': 'Latvia',
 'msa': 'Malay',
 'nld': 'Dutch',
 'pan': 'Panjabi',
 'pol': 'Polish',
 'por': 'Portuguese',
 'ron': 'Romanian',
 'rus': 'Russian',
 'spa': 'Spanish',
 'srp': 'Serbian',
 'swe': 'Swedish',
 'tur': 'Turkish',
 'ukr': 'Ukranian',
 'vie': 'Vietnamese',
 'zho': 'Chinese'}

class Languages(object):

    def __init__(self, lang_dict = _languages):
        self.supportedLanguages = {}
        self.langMappings = {}
        self.supportedLanguages = lang_dict
        self._supportedCodes = frozenset(self.supportedLanguages.keys())
        if len(self.supportedLanguages) > MAX_SUPPORTED_LANGS:
            raise ValueError('Maximum number of supported languages is %d' % MAX_SUPPORTED_LANGS)
        self._initMappings()

    def _initMappings(self):
        counter = 0
        sortedKeys = sorted(self.supportedLanguages.keys())
        for code in sortedKeys:
            self.langMappings[code] = 1 << counter
            counter += 1

    def getMaskLength(self):
        return MAX_SUPPORTED_LANGS

    def maskToLangCodes(self, mask):
        codeslist = []
        for code, cur_mask in self.langMappings.iteritems():
            if mask & cur_mask != 0:
                codeslist.append(code)

        return sorted(codeslist)

    def langCodesToMask(self, codes):
        validCodes = self.supportedLanguages.keys()
        mask = 0
        for lang in codes:
            if lang not in validCodes:
                raise ValueError(lang + ' is not a supported language code')
            mask = mask | self.langMappings[lang]

        return mask

    def isLangCodeSupported(self, langCode):
        return langCode in self._supportedCodes

    def isLangListSupported(self, listOfLangCodes):
        givenCodes = set(listOfLangCodes)
        return givenCodes & self._supportedCodes == givenCodes

    def getLangSupported(self):
        return self.supportedLanguages


class LanguagesProvider(object):
    _langInstance = None

    @staticmethod
    def getLanguagesInstance():
        if LanguagesProvider._langInstance is None:
            LanguagesProvider._langInstance = Languages(_languages)
        return LanguagesProvider._langInstance
