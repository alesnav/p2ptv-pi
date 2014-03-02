#Embedded file name: ACEStream\Utilities\LSO.pyo
import os
import sys
import random
from traceback import print_exc
try:
    from pyamf import sol
    GOT_PYAMF = True
except ImportError:
    GOT_PYAMF = False

from ACEStream.Core.osutils import get_appstate_dir
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False

class LSO:

    def __init__(self, root, name):
        self.root = root
        self.name = name

    def get_uid(self):
        if not GOT_PYAMF:
            if DEBUG:
                log('lso::get_uid: mising pyamf')
            return
        path = self.build_path(self.root, self.name)
        if DEBUG:
            log('lso::get_uid: path', path)
        uid = None
        try:
            if path is not None and os.path.isfile(path):
                lso = sol.load(path)
                if DEBUG:
                    log('lso::get_uid: file found, try to load: path', path, 'data', lso)
                if lso.has_key('uid'):
                    uid = lso['uid']
                    if DEBUG:
                        log('lso::get_uid: successfullly loaded: uid', uid, 'path', path)
            elif DEBUG:
                log('lso::get_uid: file not found: path', path)
        except:
            if DEBUG:
                print_exc()

        if uid is None:
            uid = self.create_uid()
            if DEBUG:
                log('lso::get_uid: create new uid:', uid)
            if path is not None and uid is not None:
                try:
                    d = os.path.dirname(path)
                    if not os.path.isdir(d):
                        os.mkdir(d)
                    lso = sol.SOL(self.name)
                    lso['uid'] = uid
                    if DEBUG:
                        log('lso::get_uid: save to file: path', path, 'data', lso)
                    sol.save(lso, path)
                except:
                    if DEBUG:
                        print_exc()

        return uid

    def build_path(self, root, name):
        path = None
        filename = name + '.sol'
        if sys.platform == 'win32':
            state_dir = get_appstate_dir()
            top = os.path.join(state_dir, 'Macromedia', 'Flash Player', '#SharedObjects')
            if os.path.isdir(top):
                for f in os.listdir(top):
                    path = os.path.join(top, f, root, filename)
                    break

        return path

    def create_uid(self):
        uid = []
        hex_digits = '0123456789ABCDEF'
        for i in xrange(32):
            uid.append(random.choice(hex_digits))

        uid[12] = '4'
        uid[16] = hex_digits[int(uid[16], 16) & 3 | 8]
        return ''.join(uid)
