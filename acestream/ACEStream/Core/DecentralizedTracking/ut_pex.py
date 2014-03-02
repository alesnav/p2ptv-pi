#Embedded file name: ACEStream\Core\DecentralizedTracking\ut_pex.pyo
__fool_epydoc = 481
import sys
from types import DictType, StringType
from ACEStream.Core.BitTornado.BT1.track import compact_peer_info
from ACEStream.Core.BitTornado.bencode import bencode
EXTEND_MSG_UTORRENT_PEX_ID = chr(1)
EXTEND_MSG_UTORRENT_PEX = 'ut_pex'
DEBUG = False

def create_ut_pex(addedconns, droppedconns, thisconn):
    addedconns = addedconns[:50]
    droppedconns = droppedconns[:50]
    d = {}
    compactedpeerstr = compact_connections(addedconns, thisconn)
    d['added'] = compactedpeerstr
    flags = ''
    for i in range(len(addedconns)):
        conn = addedconns[i]
        if conn == thisconn:
            continue
        flag = 0
        if conn.get_extend_encryption():
            flag |= 1
        if conn.download is not None and conn.download.peer_is_complete():
            flag |= 2
        if conn.is_tribler_peer():
            flag |= 4
        flags += chr(flag)

    d['added.f'] = flags
    compactedpeerstr = compact_connections(droppedconns)
    d['dropped'] = compactedpeerstr
    return bencode(d)


def check_ut_pex(d):
    if type(d) != DictType:
        raise ValueError('ut_pex: not a dict')
    same_apeers = []
    apeers = check_ut_pex_peerlist(d, 'added')
    dpeers = check_ut_pex_peerlist(d, 'dropped')
    if 'added.f' in d:
        addedf = d['added.f']
        if type(addedf) != StringType:
            raise ValueError('ut_pex: added.f: not string')
        if len(addedf) != len(apeers) and not len(addedf) == 0:
            raise ValueError('ut_pex: added.f: more flags than peers')
        addedf = map(ord, addedf)
        for i in range(min(len(apeers), len(addedf)) - 1, -1, -1):
            if addedf[i] & 4:
                same_apeers.append(apeers.pop(i))
                addedf.pop(i)

    if DEBUG:
        print >> sys.stderr, 'ut_pex: Got', apeers
    return (same_apeers, apeers, dpeers)


def check_ut_pex_peerlist(d, name):
    if name not in d:
        return []
    peerlist = d[name]
    if type(peerlist) != StringType:
        raise ValueError('ut_pex:' + name + ': not string')
    if len(peerlist) % 6 != 0:
        raise ValueError('ut_pex:' + name + ': not multiple of 6 bytes')
    peers = decompact_connections(peerlist)
    for ip, port in peers:
        if ip == '127.0.0.1':
            raise ValueError('ut_pex:' + name + ': address is localhost')

    return peers


def ut_pex_get_conns_diff(currconns, prevconns):
    addedconns = []
    droppedconns = []
    for conn in currconns:
        if conn not in prevconns:
            addedconns.append(conn)

    for conn in prevconns:
        if conn not in currconns:
            droppedconns.append(conn)

    return (addedconns, droppedconns)


def compact_connections(conns, thisconn = None):
    compactpeers = []
    for conn in conns:
        if conn == thisconn:
            continue
        ip = conn.get_ip()
        port = conn.get_extend_listenport()
        if port is None:
            raise ValueError('ut_pex: compact: listen port unknown?!')
        else:
            compactpeer = compact_peer_info(ip, port)
            compactpeers.append(compactpeer)

    compactpeerstr = ''.join(compactpeers)
    return compactpeerstr


def decompact_connections(p):
    peers = []
    for x in xrange(0, len(p), 6):
        ip = '.'.join([ str(ord(i)) for i in p[x:x + 4] ])
        port = ord(p[x + 4]) << 8 | ord(p[x + 5])
        peers.append((ip, port))

    return peers
