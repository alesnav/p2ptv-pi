#Embedded file name: ACEStream\Core\osutils.pyo
import sys
import os
import time
import binascii
import subprocess
if sys.platform == 'win32':
    try:
        from win32com.shell import shell

        def get_home_dir():
            return shell.SHGetSpecialFolderPath(0, 40)


        def get_appstate_dir():
            return shell.SHGetSpecialFolderPath(0, 26)


        def get_picture_dir():
            return shell.SHGetSpecialFolderPath(0, 39)


        def get_desktop_dir():
            return shell.SHGetSpecialFolderPath(0, 16)


    except ImportError:

        def get_home_dir():
            try:
                return os.path.expanduser(u'~')
            except Exception as unicode_error:
                pass

            home = os.path.expanduser('~')
            head, tail = os.path.split(home)
            print >> sys.stderr, 'get_home_dir: home', home, 'head', head, 'tail', tail
            dirs = os.listdir(head)
            udirs = os.listdir(unicode(head))
            print >> sys.stderr, 'get_home_dir: dirs', dirs, 'udirs', udirs
            islen = lambda dir: len(dir) == len(tail)
            dirs = filter(islen, dirs)
            udirs = filter(islen, udirs)
            if len(dirs) == 1 and len(udirs) == 1:
                return os.path.join(head, udirs[0])
            for dir in dirs[:]:
                if dir in udirs:
                    dirs.remove(dir)
                    udirs.remove(dir)

            if len(dirs) == 1 and len(udirs) == 1:
                return os.path.join(head, udirs[0])
            writable_udir = [ udir for udir in udirs if os.access(udir, os.W_OK) ]
            if len(writable_udir) == 1:
                return os.path.join(head, writable_udir[0])
            for dir, udir in zip(dirs, udirs):
                if dir == tail:
                    return os.path.join(head, udir)

            raise unicode_error


        def get_appstate_dir():
            homedir = get_home_dir()
            winversion = sys.getwindowsversion()
            if winversion[0] == 6:
                appdir = os.path.join(homedir, u'AppData', u'Roaming')
            else:
                appdir = os.path.join(homedir, u'Application Data')
            return appdir


        def get_picture_dir():
            return get_home_dir()


        def get_desktop_dir():
            home = get_home_dir()
            return os.path.join(home, u'Desktop')


else:

    def get_home_dir():
        return os.path.expanduser(u'~')


    def get_appstate_dir():
        return get_home_dir()


    def get_picture_dir():
        return get_desktop_dir()


    def get_desktop_dir():
        home = get_home_dir()
        desktop = os.path.join(home, 'Desktop')
        if os.path.exists(desktop):
            return desktop
        else:
            return home


if sys.version.startswith('2.4'):
    os.SEEK_SET = 0
    os.SEEK_CUR = 1
    os.SEEK_END = 2
try:
    from os import statvfs
    import statvfs

    def getfreespace(path):
        s = os.statvfs(path.encode('utf-8'))
        size = s[statvfs.F_BAVAIL] * long(s[statvfs.F_BSIZE])
        return size


except:
    if sys.platform == 'win32':
        try:
            import win32file
            try:
                win32file.GetDiskFreeSpaceEx('.')

                def getfreespace(path):
                    while True:
                        try:
                            return win32file.GetDiskFreeSpaceEx(path)[0]
                        except:
                            path = os.path.split(path)[0]
                            if not path:
                                raise


            except:

                def getfreespace(path):
                    spc, bps, nfc, tnc = win32file.GetDiskFreeSpace(path)
                    return long(nfc) * long(spc) * long(bps)


        except ImportError:

            def getfreespace(path):
                try:
                    mystdin, mystdout = os.popen2(u'dir "' + path + u'"')
                    sizestring = '0'
                    for line in mystdout:
                        line = line.strip()
                        index = line.rfind('bytes free')
                        if index > -1 and line[index:] == 'bytes free':
                            parts = line.split(' ')
                            if len(parts) > 3:
                                part = parts[-3]
                                part = part.replace(',', '')
                                sizestring = part
                                break

                    size = long(sizestring)
                    if size == 0L:
                        print >> sys.stderr, "getfreespace: can't determine freespace of ", path
                        for line in mystdout:
                            print >> sys.stderr, line

                        size = 1208925819614629174706176L
                except:
                    size = 1208925819614629174706176L

                return size


    else:

        def getfreespace(path):
            return 1208925819614629174706176L


invalidwinfilenamechars = ''
for i in range(32):
    invalidwinfilenamechars += chr(i)

invalidwinfilenamechars += '"*/:<>?\\|'
invalidlinuxfilenamechars = '/'

def fix_filebasename(name, unit = False, maxlen = 255):
    if unit and (len(name) != 2 or name[1] != ':'):
        return 'c:'
    elif not name or name == '.' or name == '..':
        return '_'
    if unit:
        name = name[0]
    fixed = False
    if len(name) > maxlen:
        name = name[:maxlen]
        fixed = True
    fixedname = ''
    spaces = 0
    for c in name:
        if sys.platform.startswith('win'):
            invalidchars = invalidwinfilenamechars
        else:
            invalidchars = invalidlinuxfilenamechars
        if c in invalidchars:
            fixedname += '_'
            fixed = True
        else:
            fixedname += c
            if c == ' ':
                spaces += 1

    file_dir, basename = os.path.split(fixedname)
    while file_dir != '':
        fixedname = basename
        file_dir, basename = os.path.split(fixedname)
        fixed = True

    if fixedname == '':
        fixedname = '_'
        fixed = True
    if fixed:
        return last_minute_filename_clean(fixedname)
    elif spaces == len(name):
        return '_'
    else:
        return last_minute_filename_clean(name)


def last_minute_filename_clean(name):
    s = name.strip()
    if sys.platform == 'win32' and s.endswith('..'):
        s = s[:-2]
    return s


def get_readable_torrent_name(infohash, raw_filename):
    hex_infohash = binascii.hexlify(infohash)
    suffix = '__' + hex_infohash + '.torrent'
    save_name = ' ' + fix_filebasename(raw_filename, maxlen=254 - len(suffix)) + suffix
    return save_name


if sys.platform == 'win32':
    import win32pdh

    def getcpuload():
        cpupath = win32pdh.MakeCounterPath((None, 'Processor', '_Total', None, -1, '% Processor Time'))
        query = win32pdh.OpenQuery(None, 0)
        counter = win32pdh.AddCounter(query, cpupath, 0)
        win32pdh.CollectQueryData(query)
        time.sleep(0.1)
        win32pdh.CollectQueryData(query)
        status, value = win32pdh.GetFormattedCounterValue(counter, win32pdh.PDH_FMT_LONG)
        return float(value) / 100.0


elif sys.platform == 'linux2':

    def read_proc_stat():
        f = open('/proc/stat', 'rb')
        try:
            while True:
                line = f.readline()
                if len(line) == 0:
                    break
                if line.startswith('cpu '):
                    words = line.split()
                    total = 0
                    for i in range(1, 5):
                        total += int(words[i])

                    idle = int(words[4])
                    return (total, idle)

        finally:
            f.close()


    def getcpuload():
        total1, idle1 = read_proc_stat()
        time.sleep(0.1)
        total2, idle2 = read_proc_stat()
        total = total2 - total1
        idle = idle2 - idle1
        return 1.0 - float(idle) / float(total)


else:

    def getupload():
        raise ValueError('Not yet implemented')


def startfile(filepath):
    if sys.platform == 'darwin':
        subprocess.call(('open', filepath))
    elif sys.platform == 'linux2':
        subprocess.call(('xdg-open', filepath))
    elif hasattr(os, 'startfile'):
        os.startfile(filepath)
