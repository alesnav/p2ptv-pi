#Embedded file name: ACEStream\Core\BitTornado\BT1\convert.pyo
from binascii import b2a_hex

def toint(s):
    return long(b2a_hex(s), 16)


def tobinary(i):
    return chr(i >> 24) + chr(i >> 16 & 255) + chr(i >> 8 & 255) + chr(i & 255)
