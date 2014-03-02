#Embedded file name: ACEStream\Core\Utilities\win32regchecker.pyo
import sys
import os
from traceback import print_exc, print_stack
if sys.platform == 'win32':
    import _winreg
    HKCR = _winreg.HKEY_CLASSES_ROOT
    HKLM = _winreg.HKEY_LOCAL_MACHINE
    HKCU = _winreg.HKEY_CURRENT_USER
else:
    HKCR = 0
    HKLM = 1
    HKCU = 2
DEBUG = False

class Win32RegChecker:

    def __init__(self):
        pass

    def readRootKey(self, key_name, value_name = '', ignore_errors = False):
        return self.readKey(HKCR, key_name, value_name, ignore_errors)

    def readKey(self, hkey, key_name, value_name = '', ignore_errors = False):
        if sys.platform != 'win32':
            return None
        try:
            if DEBUG:
                print >> sys.stderr, 'win32regcheck: Opening', key_name, value_name
            full_key = _winreg.OpenKey(hkey, key_name, 0, _winreg.KEY_READ)
            if DEBUG:
                print >> sys.stderr, 'win32regcheck: Open returned', full_key
            value_data, value_type = _winreg.QueryValueEx(full_key, value_name)
            if DEBUG:
                print >> sys.stderr, 'win32regcheck: Read', value_data, value_type
            _winreg.CloseKey(full_key)
            return value_data
        except:
            if not ignore_errors:
                print_exc(file=sys.stderr)
                print_stack()
            return None

    def readKeyRecursively(self, hkey, key_name, value_name = ''):
        if sys.platform != 'win32':
            return None
        lasthkey = hkey
        try:
            toclose = []
            keyparts = key_name.split('\\')
            print >> sys.stderr, 'win32regcheck: keyparts', keyparts
            for keypart in keyparts:
                if keypart == '':
                    continue
                if DEBUG:
                    print >> sys.stderr, 'win32regcheck: Opening', keypart
                full_key = _winreg.OpenKey(lasthkey, keypart, 0, _winreg.KEY_READ)
                lasthkey = full_key
                toclose.append(full_key)

            if DEBUG:
                print >> sys.stderr, 'win32regcheck: Open returned', full_key
            value_data, value_type = _winreg.QueryValueEx(full_key, value_name)
            if DEBUG:
                print >> sys.stderr, 'win32regcheck: Read', value_data, value_type
            for hkey in toclose:
                _winreg.CloseKey(hkey)

            return value_data
        except:
            print_exc()
            return None

    def writeKey(self, hkey, key_name, value_name, value_data, value_type):
        try:
            full_key = _winreg.CreateKey(hkey, key_name)
        except EnvironmentError:
            return False

        _winreg.SetValueEx(full_key, value_name, 0, value_type, value_data)
        _winreg.CloseKey(full_key)
        return True


if __name__ == '__main__':
    w = Win32RegChecker()
    winfiletype = w.readRootKey('.wmv')
    playkey = winfiletype + '\\shell\\play\\command'
    urlplay = w.readRootKey(playkey)
    print urlplay
    openkey = winfiletype + '\\shell\\open\\command'
    urlopen = w.readRootKey(openkey)
    print urlopen
