#Embedded file name: ACEStream\Core\APIImplementation\miscutils.pyo
import sys
import re
from threading import Timer
DEBUG = False

def parse_playtime_to_secs(hhmmss):
    if DEBUG:
        print >> sys.stderr, 'miscutils: Playtime is', hhmmss
    r = re.compile('([0-9\\.]+):*')
    occ = r.findall(hhmmss)
    t = None
    if len(occ) > 0:
        if len(occ) == 3:
            t = int(occ[0]) * 3600 + int(occ[1]) * 60 + float(occ[2])
        elif len(occ) == 2:
            t = int(occ[0]) * 60 + float(occ[1])
        elif len(occ) == 1:
            t = float(occ[0])
    return int(t)


def offset2piece(offset, piecesize):
    p = offset / piecesize
    if offset % piecesize > 0:
        p += 1
    return p


def NamedTimer(*args, **kwargs):
    t = Timer(*args, **kwargs)
    t.setDaemon(True)
    t.setName('NamedTimer' + t.getName())
    return t
