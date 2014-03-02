#Embedded file name: ACEStream\Utilities\configreader.pyo
import sys
import os
from cStringIO import StringIO
from ConfigParser import ConfigParser, MissingSectionHeaderError, NoSectionError, ParsingError, DEFAULTSECT
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
from ACEStream.Core.defaults import dldefaults, DEFAULTPORT
bt1_defaults = []
for k, v in dldefaults.iteritems():
    bt1_defaults.append((k, v, 'See triblerAPI'))

DEBUG = False

class ConfigReader(ConfigParser):

    def __init__(self, filename, section, defaults = None):
        if defaults is None:
            defaults = {}
        ConfigParser.__init__(self)
        self.defaults = defaults
        self.defaultvalues = {'string': '',
         'int': 0,
         'float': 0.0,
         'boolean': False,
         'color': None,
         'bencode-list': [],
         'bencode-string': '',
         'bencode-fontinfo': {'name': None,
                              'size': None,
                              'style': None,
                              'weight': None}}
        self.filename = filename
        self.section = section
        dirname = os.path.dirname(self.filename)
        if not os.access(dirname, os.F_OK):
            os.makedirs(dirname)
        if filename.endswith('abc.conf') and not os.access(filename, os.F_OK):
            defaults['minport'] = str(DEFAULTPORT)
        try:
            self.read(self.filename)
        except MissingSectionHeaderError:
            oldfile = open(self.filename, 'r')
            oldconfig = oldfile.readlines()
            oldfile.close()
            newfile = open(self.filename, 'w')
            newfile.write('[' + self.section + ']\n')
            newfile.writelines(oldconfig)
            newfile.close()
            self.read(self.filename)
        except ParsingError:
            self.tryRepair()
            self.read(self.filename)

    def testConfig(self, goodconfig, newline, passes = 0):
        if newline:
            testconfig = goodconfig + newline + '\r\n'
            newfile = StringIO(testconfig)
            try:
                testparser = ConfigParser()
                testparser.readfp(newfile)
                return testconfig
            except MissingSectionHeaderError:
                if passes > 0:
                    return goodconfig
                else:
                    return self.testConfig(goodconfig + '[' + self.section + ']\n', newline, passes=1)
            except ParsingError:
                return goodconfig

    def tryRepair(self):
        oldconfig = ''
        try:
            oldfile = open(self.filename, 'r')
            oldconfig = oldfile.readlines()
            oldfile.close()
        except:
            newfile = open(self.filename, 'w')
            newfile.write('[' + self.section + ']\n')
            newfile.close()
            return

        goodconfig = ''
        for line in oldconfig:
            newline = line.strip()
            goodconfig = self.testConfig(goodconfig, newline)

        newfile = open(self.filename, 'w')
        newfile.writelines(goodconfig)
        newfile.close()

    def setSection(self, section):
        self.section = section

    def ValueToString(self, value, typex):
        if typex == 'boolean':
            if value:
                text = '1'
            else:
                text = '0'
        elif typex == 'color':
            red = str(value.Red())
            while len(red) < 3:
                red = '0' + red

            green = str(value.Green())
            while len(green) < 3:
                green = '0' + green

            blue = str(value.Blue())
            while len(blue) < 3:
                blue = '0' + blue

            text = str(red) + str(green) + str(blue)
        elif typex.startswith('bencode'):
            text = bencode(value)
        elif type(value) is unicode:
            text = value
        else:
            text = str(value)
        return text

    def StringToValue(self, value, type):
        if value is not None:
            if not isinstance(value, unicode) and not isinstance(value, str):
                return value
        try:
            if type == 'boolean':
                if value == '1':
                    value = True
                else:
                    value = False
            elif type == 'int':
                value = int(value)
            elif type == 'float':
                value = float(value)
            elif type == 'color':
                value = None
            elif type.startswith('bencode'):
                value = bdecode(value)
        except:
            value = None

        if value is None:
            value = self.defaultvalues[type]
        return value

    def ReadDefault(self, param, type = 'string', section = None):
        if section is None:
            section = self.section
        if param is None or param == '':
            return ''
        param = param.lower()
        value = self.defaults.get(param, None)
        value = self.StringToValue(value, type)
        return value

    def Read(self, param, type = 'string', section = None):
        if section is None:
            section = self.section
        if DEBUG:
            print >> sys.stderr, 'ConfigReader: Read(', param, 'type', type, 'section', section
        if param is None or param == '':
            return ''
        try:
            value = self.get(section, param)
            value = value.strip('"')
        except:
            param = param.lower()
            value = self.defaults.get(param, None)
            if DEBUG:
                sys.stderr.write('ConfigReader: Error while reading parameter: (' + str(param) + ')\n')
            if value is None:
                if not DEBUG:
                    pass
                for k, v, d in bt1_defaults:
                    if k == param:
                        value = v
                        break

        if DEBUG:
            print >> sys.stderr, 'ConfigReader: Read', param, type, section, 'got', value
        value = self.StringToValue(value, type)
        return value

    def Exists(self, param, section = None):
        if section is None:
            section = self.section
        return self.has_option(section, param)

    def Items(self, section = None):
        if section is None:
            section = self.section
        try:
            items = self.items(section)
            for i in range(len(items)):
                key, value = items[i]
                value = value.strip('"')
                items[i] = (key, value)

            return items
        except:
            self.add_section(section)

        return []

    def GetOptions(self, section = None):
        if section is None:
            section = self.section
        try:
            options = self.options(section)
        except NoSectionError:
            options = []

        return options

    def Write(self, param, value, type = 'string', section = None):
        if section is None:
            section = self.section
        if param is None or param == '':
            return False
        param = param.lower()
        if not self.has_section(section):
            self.add_section(section)
        text = self.ValueToString(value, type)
        while 1:
            try:
                oldtext = self.Read(param)
                self.set(section, param, text)
                if oldtext != text:
                    return True
                break
            except NoSectionError:
                self.add_section(section)
            except:
                break

        return False

    def DeleteEntry(self, param, section = None):
        if section is None:
            section = self.section
        try:
            return self.remove_option(section, param)
        except:
            return False

    def DeleteGroup(self, section = None):
        if section is None:
            section = self.section
        try:
            return self.remove_section(section)
        except:
            return False

    def Flush(self):
        self.write(open(self.filename, 'w'))

    def _read(self, fp, fpname):
        cursect = None
        optname = None
        lineno = 0
        e = None
        firstline = True
        while True:
            line = fp.readline()
            if not line:
                break
            lineno = lineno + 1
            if firstline:
                if line[:3] == '\xef\xbb\xbf':
                    line = line[3:]
                    self.encoding = 'utf_8'
                else:
                    self.encoding = sys.getfilesystemencoding()
                    if self.encoding is None:
                        self.encoding = 'utf_8'
                firstline = False
            if line.strip() == '' or line[0] in '#;':
                continue
            if line.split(None, 1)[0].lower() == 'rem' and line[0] in 'rR':
                continue
            if line[0].isspace() and cursect is not None and optname:
                value = line.strip()
                if value:
                    cursect[optname] = '%s\n%s' % (cursect[optname], value.decode(self.encoding))
            else:
                mo = self.SECTCRE.match(line)
                if mo:
                    sectname = mo.group('header')
                    if sectname in self._sections:
                        cursect = self._sections[sectname]
                    elif sectname == DEFAULTSECT:
                        cursect = self._defaults
                    else:
                        cursect = {'__name__': sectname}
                        self._sections[sectname] = cursect
                    optname = None
                elif cursect is None:
                    raise MissingSectionHeaderError(fpname, lineno, line)
                else:
                    mo = self.OPTCRE.match(line)
                    if mo:
                        optname, vi, optval = mo.group('option', 'vi', 'value')
                        if vi in ('=', ':') and ';' in optval:
                            pos = optval.find(';')
                            if pos != -1 and optval[pos - 1].isspace():
                                optval = optval[:pos]
                        optval = optval.strip()
                        if optval == '""':
                            optval = ''
                        optname = self.optionxform(optname.rstrip())
                        try:
                            _opt = optval.decode(self.encoding)
                        except UnicodeDecodeError:
                            self.encoding = sys.getfilesystemencoding()
                            if self.encoding is None:
                                self.encoding = 'utf_8'
                            _opt = optval.decode(self.encoding)

                        cursect[optname] = _opt
                    else:
                        if not e:
                            e = ParsingError(fpname)
                        e.append(lineno, repr(line))

        if e:
            raise e

    def write(self, fp):
        fp.writelines('\xef\xbb\xbf')
        if self._defaults:
            fp.write('[%s]\n' % DEFAULTSECT)
            for key, value in self._defaults.items():
                if type(value) is not str and type(value) is not unicode:
                    value = str(value)
                fp.write((key + ' = ' + value + '\n').encode('utf_8'))

            fp.write('\n')
        for section in self._sections:
            fp.write('[%s]\n' % section)
            for key, value in self._sections[section].items():
                if key != '__name__':
                    if type(value) is not str and type(value) is not unicode:
                        value = str(value)
                    try:
                        fp.write((key + ' = ' + value + '\n').encode('utf_8'))
                    except UnicodeDecodeError:
                        fp.write(key + ' = ' + value + '\n')

            fp.write('\n')
