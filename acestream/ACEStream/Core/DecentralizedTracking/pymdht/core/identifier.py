#Embedded file name: ACEStream\Core\DecentralizedTracking\pymdht\core\identifier.pyo
import sys
import random
import logging
logger = logging.getLogger('dht')
BITS_PER_BYTE = 8
ID_SIZE_BYTES = 20
ID_SIZE_BITS = ID_SIZE_BYTES * BITS_PER_BYTE

def _bin_to_hex(bin_str):
    hex_list = [ '%02x' % ord(c) for c in bin_str ]
    return ''.join(hex_list)


def _hex_to_bin_byte(hex_byte):
    hex_down = '0123456789abcdef'
    hex_up = '0123456789ABCDEF'
    value = 0
    for i in xrange(2):
        value *= 16
        try:
            value += hex_down.index(hex_byte[i])
        except ValueError:
            try:
                value += hex_up.index(hex_byte[i])
            except ValueError:
                raise IdError

    return chr(value)


def _hex_to_bin(hex_str):
    return ''.join([ _hex_to_bin_byte(hex_byte) for hex_byte in zip(hex_str[::2], hex_str[1::2]) ])


def _byte_xor(byte1, byte2):
    return chr(ord(byte1) ^ ord(byte2))


def _first_different_byte(str1, str2):
    for i in range(len(str1)):
        if str1[i] != str2[i]:
            return i

    raise IndexError


def _first_different_bit(byte1, byte2):
    byte = ord(byte1) ^ ord(byte2)
    i = 0
    while byte >> BITS_PER_BYTE - 1 == 0:
        byte <<= 1
        i += 1

    return i


class IdError(Exception):
    pass


class Id(object):

    def __init__(self, hex_or_bin_id):
        if not isinstance(hex_or_bin_id, str):
            raise IdError
        if len(hex_or_bin_id) == ID_SIZE_BYTES:
            self._bin_id = hex_or_bin_id
        elif len(hex_or_bin_id) == ID_SIZE_BYTES * 2:
            self._bin_id = _hex_to_bin(hex_or_bin_id)
        else:
            raise IdError, 'input: %r' % hex_or_bin_id

    def __hash__(self):
        return self.bin_id.__hash__()

    @property
    def bin_id(self):
        return self._bin_id

    def __eq__(self, other):
        return self.bin_id == other.bin_id

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        return self.bin_id

    def __repr__(self):
        return '%s' % _bin_to_hex(self.bin_id)

    def distance(self, other):
        byte_list = [ _byte_xor(a, b) for a, b in zip(self.bin_id, other.bin_id) ]
        return Id(''.join(byte_list))

    def log_distance(self, other):
        try:
            byte_i = _first_different_byte(self.bin_id, other.bin_id)
        except IndexError:
            return -1

        unmatching_bytes = ID_SIZE_BYTES - byte_i - 1
        byte1 = self.bin_id[byte_i]
        byte2 = other.bin_id[byte_i]
        bit_i = _first_different_bit(byte1, byte2)
        unmatching_bits = BITS_PER_BYTE - bit_i - 1
        return unmatching_bytes * BITS_PER_BYTE + unmatching_bits

    def order_closest(self, id_list):
        id_list_copy = id_list[:]
        max_distance = ID_SIZE_BITS + 1
        log_distance_list = []
        for element in id_list:
            log_distance_list.append(self.log_distance(element))

        result = []
        for _ in range(len(id_list)):
            lowest_index = None
            lowest_distance = max_distance
            for j in range(len(id_list_copy)):
                if log_distance_list[j] < lowest_distance:
                    lowest_index = j
                    lowest_distance = log_distance_list[j]

            result.append(id_list_copy[lowest_index])
            del log_distance_list[lowest_index]
            del id_list_copy[lowest_index]

        return result

    def generate_close_id(self, log_distance):
        if log_distance < 0:
            return self
        byte_num, bit_num = divmod(log_distance, BITS_PER_BYTE)
        byte_index = len(self.bin_id) - byte_num - 1
        int_byte = ord(self.bin_id[byte_index])
        import sys
        int_byte = int_byte ^ 1 << bit_num
        for i in range(bit_num):
            int_byte = int_byte & 255 - (1 << i)
            int_byte = int_byte + (random.randint(0, 1) << i)

        id_byte = chr(int_byte)
        end_bytes = ''.join([ chr(random.randint(0, 255)) for _ in xrange(byte_index + 1, ID_SIZE_BYTES) ])
        bin_id = self.bin_id[:byte_index] + id_byte + end_bytes
        result = Id(bin_id)
        return result


class RandomId(Id):

    def __init__(self):
        random_str = ''.join([ chr(random.randint(0, 255)) for _ in xrange(ID_SIZE_BYTES) ])
        Id.__init__(self, random_str)
