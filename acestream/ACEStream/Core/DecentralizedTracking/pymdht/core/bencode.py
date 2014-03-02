#Embedded file name: ACEStream\Core\DecentralizedTracking\pymdht\core\bencode.pyo
import cStringIO
import logging
logger = logging.getLogger('dht')

class LoggingException(Exception):

    def __init__(self, msg):
        logger.info('%s: %s' % (self.__class__, msg))


class EncodeError(LoggingException):
    pass


class DecodeError(LoggingException):

    def __init__(self, msg, bencoded):
        LoggingException.__init__(self, '\nBencoded: '.join((msg, repr(bencoded))))


class RecursionDepthError(DecodeError):
    pass


def encode(data):
    output = cStringIO.StringIO()
    encode_f = _get_encode_f(data)
    encode_f(data, output)
    result = output.getvalue()
    output.close()
    return result


def decode(bencoded, max_depth = 4):
    if not bencoded:
        raise DecodeError('Empty bencoded string', bencoded)
    try:
        decode_f = _get_decode_f(bencoded, 0)
        data, next_pos = decode_f(bencoded, 0, max_depth)
    except DecodeError:
        raise
    except:
        raise DecodeError('UNEXPECTED>>>>>>>>>>>>', bencoded)
    else:
        if next_pos != len(bencoded):
            raise DecodeError('Extra characters after valid bencode.', bencoded)

    return data


def _encode_str(data, output):
    output.write('%d:%s' % (len(data), data))


def _encode_int(data, output):
    output.write('i%de' % data)


def _encode_list(data, output):
    output.write('l')
    for item in data:
        encode_f = _get_encode_f(item)
        encode_f(item, output)

    output.write('e')


def _encode_dict(data, output):
    output.write('d')
    keys = data.keys()
    keys.sort()
    for key in keys:
        if type(key) != str:
            raise EncodeError, 'Found a non-string key. Data: %r' % data
        value = data[key]
        _encode_fs[str](key, output)
        encode_f = _get_encode_f(value)
        encode_f(value, output)

    output.write('e')


def _decode_str(bencoded, pos, _):
    str_len, str_begin = _get_int(bencoded, pos, ':')
    str_end = str_begin + str_len
    return (bencoded[str_begin:str_end], str_end)


def _decode_int(bencoded, pos, _):
    return _get_int(bencoded, pos + 1, 'e')


def _decode_list(bencoded, pos, max_depth):
    if max_depth == 0:
        raise RecursionDepthError('maximum recursion depth exceeded', bencoded)
    result = []
    next_pos = pos + 1
    bencoded_length = len(bencoded)
    while bencoded[next_pos] != 'e':
        decode_f = _get_decode_f(bencoded, next_pos)
        item, next_pos = decode_f(bencoded, next_pos, max_depth - 1)
        if next_pos >= bencoded_length:
            raise DecodeError('End of string and ending character not found', bencoded[pos:])
        result.append(item)

    return (result, next_pos + 1)


def _decode_dict(bencoded, pos, max_depth):
    if max_depth == 0:
        raise RecursionDepthError('maximum recursion depth exceeded', bencoded)
    result = {}
    next_pos = pos + 1
    bencoded_length = len(bencoded)
    while bencoded[next_pos] != 'e':
        decode_f = _get_decode_f(bencoded, next_pos)
        if decode_f != _decode_str:
            raise DecodeError('Keys must be string. Found: <%s>' % bencoded[next_pos], bencoded)
        key, next_pos = decode_f(bencoded, next_pos, max_depth - 1)
        if next_pos >= bencoded_length:
            raise DecodeError('End of string and ending character not found', bencoded[pos:])
        decode_f = _get_decode_f(bencoded, next_pos)
        value, next_pos = decode_f(bencoded, next_pos, max_depth - 1)
        if next_pos >= bencoded_length:
            raise DecodeError('End of string and ending character not found', bencoded[pos:])
        result[key] = value

    return (result, next_pos + 1)


def _get_encode_f(value):
    try:
        return _encode_fs[type(value)]
    except KeyError as e:
        raise EncodeError, 'Invalid type: <%r>' % e


def _get_int(bencoded, pos, char):
    try:
        end = bencoded.index(char, pos)
    except ValueError:
        raise DecodeError('Character %s not found.', bencoded)

    try:
        result = int(bencoded[pos:end])
    except ValueError as e:
        raise DecodeError('Not an integer: %r' % e, bencoded)

    return (result, end + 1)


def _get_decode_f(bencoded, pos):
    try:
        return _decode_fs[bencoded[pos]]
    except KeyError as e:
        raise DecodeError('Caracter in position %d raised %r' % (pos, e), bencoded)


_encode_fs = {str: _encode_str,
 int: _encode_int,
 long: _encode_int,
 tuple: _encode_list,
 list: _encode_list,
 dict: _encode_dict}
_decode_fs = {'i': _decode_int,
 'l': _decode_list,
 'd': _decode_dict}
for i in xrange(10):
    _decode_fs[str(i)] = _decode_str
