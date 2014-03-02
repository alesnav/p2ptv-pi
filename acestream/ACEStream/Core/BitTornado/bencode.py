#Embedded file name: ACEStream\Core\BitTornado\bencode.pyo
from types import IntType, LongType, StringType, ListType, TupleType, DictType
from ACEStream.Core.Utilities.odict import odict
try:
    from types import BooleanType
except ImportError:
    BooleanType = None

try:
    from types import UnicodeType
except ImportError:
    UnicodeType = None

from traceback import print_exc, print_stack
import sys
DEBUG = False

def decode_int(x, f, params = None):
    f += 1
    newf = x.index('e', f)
    try:
        n = int(x[f:newf])
    except:
        n = long(x[f:newf])

    if x[f] == '-':
        if x[f + 1] == '0':
            raise ValueError
    elif x[f] == '0' and newf != f + 1:
        raise ValueError
    return (n, newf + 1)


def decode_string(x, f, params = None):
    colon = x.index(':', f)
    try:
        n = int(x[f:colon])
    except (OverflowError, ValueError):
        n = long(x[f:colon])

    if x[f] == '0' and colon != f + 1:
        raise ValueError
    colon += 1
    return (x[colon:colon + n], colon + n)


def decode_unicode(x, f, params = None):
    s, f = decode_string(x, f + 1)
    return (s.decode('UTF-8'), f)


def decode_list(x, f, params = None):
    r, f = [], f + 1
    while x[f] != 'e':
        v, f = decode_func[x[f]](x, f, params)
        r.append(v)

    return (r, f + 1)


def decode_dict(x, f, params = None):
    if params != None and 'use_ordered_dict' in params:
        r = odict()
    else:
        r = {}
    f = f + 1
    lastkey = None
    while x[f] != 'e':
        k, f = decode_string(x, f)
        lastkey = k
        r[k], f = decode_func[x[f]](x, f, params)

    return (r, f + 1)


decode_func = {}
decode_func['l'] = decode_list
decode_func['d'] = decode_dict
decode_func['i'] = decode_int
decode_func['0'] = decode_string
decode_func['1'] = decode_string
decode_func['2'] = decode_string
decode_func['3'] = decode_string
decode_func['4'] = decode_string
decode_func['5'] = decode_string
decode_func['6'] = decode_string
decode_func['7'] = decode_string
decode_func['8'] = decode_string
decode_func['9'] = decode_string

def bdecode(x, sloppy = 1, params = None):
    try:
        r, l = decode_func[x[0]](x, 0, params)
    except (IndexError, KeyError, ValueError):
        if DEBUG:
            print_exc()
        raise ValueError, 'bad bencoded data'

    if not sloppy and l != len(x):
        raise ValueError, 'bad bencoded data'
    return r


def test_bdecode():
    try:
        bdecode('0:0:')
    except ValueError:
        pass

    try:
        bdecode('ie')
    except ValueError:
        pass

    try:
        bdecode('i341foo382e')
    except ValueError:
        pass

    try:
        bdecode('i-0e')
    except ValueError:
        pass

    try:
        bdecode('i123')
    except ValueError:
        pass

    try:
        bdecode('')
    except ValueError:
        pass

    try:
        bdecode('i6easd')
    except ValueError:
        pass

    try:
        bdecode('35208734823ljdahflajhdf')
    except ValueError:
        pass

    try:
        bdecode('2:abfdjslhfld')
    except ValueError:
        pass

    try:
        bdecode('02:xy')
    except ValueError:
        pass

    try:
        bdecode('l')
    except ValueError:
        pass

    try:
        bdecode('leanfdldjfh')
    except ValueError:
        pass

    try:
        bdecode('relwjhrlewjh')
    except ValueError:
        pass

    try:
        bdecode('d')
    except ValueError:
        pass

    try:
        bdecode('defoobar')
    except ValueError:
        pass

    try:
        bdecode('d3:fooe')
    except ValueError:
        pass

    try:
        bdecode('di1e0:e')
    except ValueError:
        pass

    try:
        bdecode('d1:b0:1:a0:e')
    except ValueError:
        pass

    try:
        bdecode('d1:a0:1:a0:e')
    except ValueError:
        pass

    try:
        bdecode('i03e')
    except ValueError:
        pass

    try:
        bdecode('l01:ae')
    except ValueError:
        pass

    try:
        bdecode('9999:x')
    except ValueError:
        pass

    try:
        bdecode('l0:')
    except ValueError:
        pass

    try:
        bdecode('d0:0:')
    except ValueError:
        pass

    try:
        bdecode('d0:')
    except ValueError:
        pass


bencached_marker = []

class Bencached:

    def __init__(self, s):
        self.marker = bencached_marker
        self.bencoded = s


BencachedType = type(Bencached(''))

def encode_bencached(x, r, params = None):
    r.append(x.bencoded)


def encode_int(x, r, params = None):
    r.extend(('i', str(x), 'e'))


def encode_bool(x, r, params = None):
    encode_int(int(x), r)


def encode_string(x, r, params = None):
    r.extend((str(len(x)), ':', x))


def encode_unicode(x, r, params = None):
    encode_string(x.encode('UTF-8'), r)


def encode_list(x, r, params = None):
    r.append('l')
    for e in x:
        encode_func[type(e)](e, r)

    r.append('e')


def encode_dict(x, r, params = None):
    r.append('d')
    ilist = x.items()
    if params != None and 'skip_dict_sorting' in params:
        pass
    else:
        ilist.sort()
    for k, v in ilist:
        if DEBUG:
            print >> sys.stderr, 'bencode: Encoding', `k`, `v`
        try:
            r.extend((str(len(k)), ':', k))
        except:
            print >> sys.stderr, 'k: %s' % k
            raise

        encode_func[type(v)](v, r)

    r.append('e')


encode_func = {}
encode_func[BencachedType] = encode_bencached
encode_func[IntType] = encode_int
encode_func[LongType] = encode_int
encode_func[StringType] = encode_string
encode_func[ListType] = encode_list
encode_func[TupleType] = encode_list
encode_func[DictType] = encode_dict
encode_func[odict] = encode_dict
if BooleanType:
    encode_func[BooleanType] = encode_bool
if UnicodeType:
    encode_func[UnicodeType] = encode_unicode

def bencode(x, params = None):
    r = []
    try:
        encode_func[type(x)](x, r, params)
    except:
        print >> sys.stderr, 'bencode: *** error *** could not encode type %s (value: %s)' % (type(x), x)
        print_stack()
        print_exc()

    try:
        return ''.join(r)
    except:
        if DEBUG:
            print >> sys.stderr, 'bencode: join error', x
            for elem in r:
                print >> sys.stderr, 'elem', elem, 'has type', type(elem)

            print_exc()
        return ''


def test_bencode():
    try:
        bencode({1: 'foo'})
    except AssertionError:
        pass


try:
    import psyco
    psyco.bind(bdecode)
    psyco.bind(bencode)
except ImportError:
    pass
