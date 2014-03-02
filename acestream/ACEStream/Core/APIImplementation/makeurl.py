#Embedded file name: ACEStream\Core\APIImplementation\makeurl.pyo
import sys
import urlparse
import urllib
import math
if sys.platform != 'win32':
    import curses.ascii
from types import IntType, LongType
from struct import pack, unpack
from base64 import b64encode, b64decode
from M2Crypto import Rand
from traceback import print_exc, print_stack
from ACEStream.Core.simpledefs import *
from ACEStream.Core.Utilities.TSCrypto import sha
DEBUG = False

def metainfo2p2purl(metainfo):
    info = metainfo['info']
    bitrate = None
    if 'azureus_properties' in metainfo:
        azprops = metainfo['azureus_properties']
        if 'Content' in azprops:
            content = metainfo['azureus_properties']['Content']
            if 'Speed Bps' in content:
                bitrate = content['Speed Bps']
    if 'encoding' not in metainfo:
        encoding = 'utf-8'
    else:
        encoding = metainfo['encoding']
    urldict = {}
    urldict['s'] = p2purl_encode_piecelength(info['piece length'])
    urldict['n'] = p2purl_encode_name2url(info['name'], encoding)
    if info.has_key('length'):
        urldict['l'] = p2purl_encode_nnumber(info['length'])
    else:
        raise ValueError('Multi-file torrents currently not supported')
    if info.has_key('root hash'):
        urldict['r'] = b64urlencode(info['root hash'])
    elif info.has_key('live'):
        urldict['k'] = b64urlencode(info['live']['pubkey'])
        urldict['a'] = info['live']['authmethod']
    else:
        raise ValueError('url-compat and Merkle torrent must be on to create URL')
    if bitrate is not None:
        urldict['b'] = p2purl_encode_nnumber(bitrate)
    query = ''
    for k in ['n',
     'r',
     'k',
     'l',
     's',
     'a',
     'b']:
        if k in urldict:
            if query != '':
                query += '&'
            v = urldict[k]
            if k == 'n':
                s = v
            else:
                s = k + '=' + v
            query += s

    sidx = metainfo['announce'].find(':')
    hierpart = metainfo['announce'][sidx + 1:]
    url = P2PURL_SCHEME + ':' + hierpart + '?' + query
    return url


def p2purl2metainfo(url):
    if DEBUG:
        print >> sys.stderr, 'p2purl2metainfo: URL', url
    colidx = url.find(':')
    scheme = url[0:colidx]
    qidx = url.find('?')
    if qidx == -1:
        authority = None
        path = None
        query = url[colidx + 1:]
        fragment = None
    else:
        authoritypath = url[colidx + 3:qidx]
        pidx = authoritypath.find('/')
        authority = authoritypath[0:pidx]
        path = authoritypath[pidx:]
        fidx = url.find('#')
        if fidx == -1:
            query = url[qidx + 1:]
            fragment = None
        else:
            query = url[qidx + 1:fidx]
            fragment = url[fidx:]
        csbidx = authority.find(']')
        if authority.startswith('[') and csbidx != -1:
            if csbidx == len(authority) - 1:
                port = None
            else:
                port = authority[csbidx + 1:]
        else:
            cidx = authority.find(':')
            if cidx != -1:
                port = authority[cidx + 1:]
            else:
                port = None
        if port is not None and not port.isdigit():
            raise ValueError('Port not int')
    if scheme != P2PURL_SCHEME:
        raise ValueError('Unknown scheme ' + P2PURL_SCHEME)
    metainfo = {}
    if authority and path:
        metainfo['announce'] = 'http://' + authority + path
        result = urlparse.urlparse(metainfo['announce'])
        if result[0] != 'http':
            raise ValueError('Malformed tracker URL')
    reqinfo = p2purl_parse_query(query)
    metainfo.update(reqinfo)
    swarmid = metainfo2swarmid(metainfo)
    if DEBUG:
        print >> sys.stderr, 'p2purl2metainfo: parsed', `metainfo`
    return (metainfo, swarmid)


def metainfo2swarmid(metainfo):
    if 'live' in metainfo['info']:
        swarmid = pubkey2swarmid(metainfo['info']['live'])
    else:
        swarmid = metainfo['info']['root hash']
    return swarmid


def p2purl_parse_query(query):
    if DEBUG:
        print >> sys.stderr, 'p2purl_parse_query: query', query
    gotname = False
    gotkey = False
    gotrh = False
    gotlen = False
    gotps = False
    gotam = False
    gotbps = False
    reqinfo = {}
    reqinfo['info'] = {}
    kvs = query.split('&')
    for kv in kvs:
        if '=' not in kv:
            reqinfo['info']['name'] = p2purl_decode_name2utf8(kv)
            reqinfo['encoding'] = 'UTF-8'
            gotname = True
            continue
        k, v = kv.split('=')
        if k == 'k' or k == 'a' and 'live' not in reqinfo['info']:
            reqinfo['info']['live'] = {}
        if k == 'n':
            reqinfo['info']['name'] = p2purl_decode_name2utf8(v)
            reqinfo['encoding'] = 'UTF-8'
            gotname = True
        elif k == 'r':
            reqinfo['info']['root hash'] = p2purl_decode_base64url(v)
            gotrh = True
        elif k == 'k':
            reqinfo['info']['live']['pubkey'] = p2purl_decode_base64url(v)
            gotkey = True
        elif k == 'l':
            reqinfo['info']['length'] = p2purl_decode_nnumber(v)
            gotlen = True
        elif k == 's':
            reqinfo['info']['piece length'] = p2purl_decode_piecelength(v)
            gotps = True
        elif k == 'a':
            reqinfo['info']['live']['authmethod'] = v
            gotam = True
        elif k == 'b':
            bitrate = p2purl_decode_nnumber(v)
            reqinfo['azureus_properties'] = {}
            reqinfo['azureus_properties']['Content'] = {}
            reqinfo['azureus_properties']['Content']['Speed Bps'] = bitrate
            gotbps = True

    if not gotname:
        raise ValueError('Missing name field')
    if not gotrh and not gotkey:
        raise ValueError('Missing root hash or live pub key field')
    if gotrh and gotkey:
        raise ValueError('Found both root hash and live pub key field')
    if not gotlen:
        raise ValueError('Missing length field')
    if not gotps:
        raise ValueError('Missing piece size field')
    if gotkey and not gotam:
        raise ValueError('Missing live authentication method field')
    if gotrh and gotam:
        raise ValueError('Inconsistent: root hash and live authentication method field')
    if not gotbps:
        raise ValueError('Missing bitrate field')
    return reqinfo


def pubkey2swarmid(livedict):
    if DEBUG:
        print >> sys.stderr, 'pubkey2swarmid:', livedict.keys()
    if livedict['authmethod'] == 'None':
        return Rand.rand_bytes(20)
    else:
        return sha(livedict['pubkey']).digest()


def p2purl_decode_name2utf8(v):
    if sys.platform != 'win32':
        for c in v:
            if not curses.ascii.isascii(c):
                raise ValueError('Name contains unescaped 8-bit value ' + `c`)

    return urllib.unquote_plus(v)


def p2purl_encode_name2url(name, encoding):
    if encoding.lower() == 'utf-8':
        utf8name = name
    else:
        uname = unicode(name, encoding)
        utf8name = uname.encode('utf-8')
    return urllib.quote_plus(utf8name)


def p2purl_decode_base64url(v):
    return b64urldecode(v)


def p2purl_decode_nnumber(s):
    b = b64urldecode(s)
    if len(b) == 2:
        format = 'H'
    elif len(b) == 4:
        format = 'l'
    else:
        format = 'Q'
    format = '!' + format
    return unpack(format, b)[0]


def p2purl_encode_nnumber(s):
    if type(s) == IntType:
        if s < 65536:
            format = 'H'
        elif s < 4294967296L:
            format = 'l'
    else:
        format = 'Q'
    format = '!' + format
    return b64urlencode(pack(format, s))


def p2purl_decode_piecelength(s):
    return int(math.pow(2.0, float(s)))


def p2purl_encode_piecelength(s):
    return str(int(math.log(float(s), 2.0)))


def b64urlencode(input):
    output = b64encode(input)
    output = output.rstrip('=')
    output = output.replace('+', '-')
    output = output.replace('/', '_')
    return output


def b64urldecode(input):
    inter = input[:]
    padlen = 4 - (len(inter) - len(inter) / 4 * 4)
    padstr = '=' * padlen
    inter += padstr
    inter = inter.replace('-', '+')
    inter = inter.replace('_', '/')
    output = b64decode(inter)
    return output
