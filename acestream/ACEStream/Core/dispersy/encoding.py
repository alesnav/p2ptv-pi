#Embedded file name: ACEStream\Core\dispersy\encoding.pyo


def _a_encode_int(value, mapping):
    value = str(value).encode('UTF-8')
    return (str(len(value)).encode('UTF-8'), 'i', value)


def _a_encode_float(value, mapping):
    value = str(value).encode('UTF-8')
    return (str(len(value)).encode('UTF-8'), 'f', value)


def _a_encode_unicode(value, mapping):
    value = value.encode('UTF-8')
    return (str(len(value)).encode('UTF-8'), 's', value)


def _a_encode_bytes(value, mapping):
    return (str(len(value)).encode('UTF-8'), 'b', value)


def _a_encode_iterable(values, mapping):
    encoded = [str(len(values)).encode('UTF-8'), 't']
    extend = encoded.extend
    for value in values:
        extend(mapping[type(value)](value, mapping))

    return encoded


def _a_encode_dictionary(values, mapping):
    encoded = [str(len(values)).encode('UTF-8'), 'd']
    extend = encoded.extend
    for key, value in sorted(values.items()):
        extend(mapping[type(key)](key, mapping))
        extend(mapping[type(value)](value, mapping))

    return encoded


_a_encode_mapping = {int: _a_encode_int,
 long: _a_encode_int,
 float: _a_encode_float,
 unicode: _a_encode_unicode,
 str: _a_encode_bytes,
 list: _a_encode_iterable,
 tuple: _a_encode_iterable,
 dict: _a_encode_dictionary}

def encode(data):
    return 'a' + ''.join(_a_encode_mapping[type(data)](data, _a_encode_mapping))


def _a_decode_int(stream, offset, count, _):
    return (offset + count, int(stream[offset:offset + count]))


def _a_decode_float(stream, offset, count, _):
    return (offset + count, float(stream[offset:offset + count]))


def _a_decode_unicode(stream, offset, count, _):
    if len(stream) >= offset + count:
        return (offset + count, stream[offset:offset + count].decode('UTF-8'))
    raise ValueError('Invalid stream length', len(stream), offset + count)


def _a_decode_bytes(stream, offset, count, _):
    if len(stream) >= offset + count:
        return (offset + count, stream[offset:offset + count])
    raise ValueError('Invalid stream length', len(stream), offset + count)


def _a_decode_iterable(stream, offset, count, mapping):
    container = []
    for _ in range(count):
        index = offset
        while 48 <= ord(stream[index]) <= 57:
            index += 1

        offset, value = mapping[stream[index]](stream, index + 1, int(stream[offset:index]), mapping)
        container.append(value)

    return (offset, tuple(container))


def _a_decode_dictionary(stream, offset, count, mapping):
    container = {}
    for _ in range(count):
        index = offset
        while 48 <= ord(stream[index]) <= 57:
            index += 1

        offset, key = mapping[stream[index]](stream, index + 1, int(stream[offset:index]), mapping)
        index = offset
        while 48 <= ord(stream[index]) <= 57:
            index += 1

        offset, value = mapping[stream[index]](stream, index + 1, int(stream[offset:index]), mapping)
        container[key] = value

    if len(container) < count:
        raise ValueError('Duplicate key in dictionary')
    return (offset, container)


_a_decode_mapping = {'i': _a_decode_int,
 'f': _a_decode_float,
 's': _a_decode_unicode,
 'b': _a_decode_bytes,
 't': _a_decode_iterable,
 'd': _a_decode_dictionary}

def decode(stream, offset = 0):
    if stream[offset] == 'a':
        index = offset + 1
        while 48 <= ord(stream[index]) <= 57:
            index += 1

        return _a_decode_mapping[stream[index]](stream, index + 1, int(stream[offset + 1:index]), _a_decode_mapping)
    raise ValueError('Unknown version found')
