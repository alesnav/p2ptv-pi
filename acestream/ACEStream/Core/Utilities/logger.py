#Embedded file name: ACEStream\Core\Utilities\logger.pyo
import sys
from traceback import format_exc
from time import strftime

def safe_str(s):
    try:
        return str(s)
    except UnicodeEncodeError:
        try:
            return s.encode(sys.getfilesystemencoding())
        except:
            return ''


def log(*args):
    print >> sys.stderr, strftime('%Y-%m-%d %H:%M:%S'), ' '.join([ safe_str(x) for x in args ])


def log_exc():
    exc = format_exc()
    print >> sys.stderr, exc
