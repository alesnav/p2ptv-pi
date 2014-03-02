#Embedded file name: ACEStream\Core\BitTornado\__init__.pyo
from ACEStream.__init__ import LIBRARYNAME
version_id = '2.0'
product_name = 'ACEStream'
version_short = 'ACEStream-' + version_id
report_email = 'info@acestream.net'
TRIBLER_PEERID_LETTER = 'R'
version = version_short + ' (' + product_name + ')'
_idprefix = TRIBLER_PEERID_LETTER
from types import StringType
from time import time, clock
from string import strip
import socket
import random
try:
    from os import getpid
except ImportError:

    def getpid():
        return 1


from base64 import decodestring
import sys
from traceback import print_exc
mapbase64 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.-'
for subver in version_short.split('-')[1].split('.'):
    try:
        subver = int(subver)
    except:
        subver = 0

    _idprefix += mapbase64[subver]

_idprefix += '-' * (6 - len(_idprefix))
_idrandom = [None]

def resetPeerIDs():
    try:
        f = open('/dev/urandom', 'rb')
        x = f.read(20)
        f.close()
    except:
        random.seed()
        x = ''
        while len(x) < 20:
            r = random.randint(0, 255)
            x += chr(r)

        x = x[:20]

    s = ''
    for i in x:
        s += mapbase64[ord(i) & 63]

    _idrandom[0] = s[:11]


def createPeerID(ins = '---'):
    resetPeerIDs()
    return _idprefix + ins + _idrandom[0]


def decodePeerID(id):
    client = None
    version = None
    try:
        if id[0] == '-':
            client = id[1:3]
            encversion = id[3:7]
        else:
            client = id[0]
            encversion = id[1:4]
        version = ''
        for i in range(len(encversion)):
            for j in range(len(mapbase64)):
                if mapbase64[j] == encversion[i]:
                    if len(version) > 0:
                        version += '.'
                    version += str(j)

    except:
        print_exc(file=sys.stderr)

    return [client, version]
