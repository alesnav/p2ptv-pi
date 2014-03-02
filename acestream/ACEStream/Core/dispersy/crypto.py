#Embedded file name: ACEStream\Core\dispersy\crypto.pyo
from hashlib import sha1, sha224, sha256, sha512, md5
from math import ceil
from random import randint
from struct import pack
import M2Crypto
_curves = {u'very-low': M2Crypto.EC.NID_sect163k1,
 u'low': M2Crypto.EC.NID_sect233k1,
 u'medium': M2Crypto.EC.NID_sect409k1,
 u'high': M2Crypto.EC.NID_sect571r1}

def _progress(*args):
    pass


def ec_generate_key(security):
    ec = M2Crypto.EC.gen_params(_curves[security])
    ec.gen_key()
    return ec


def ec_public_pem_to_public_bin(pem):
    return ''.join(pem.split('\n')[1:-2]).decode('BASE64')


def ec_private_pem_to_private_bin(pem):
    return ''.join(pem.split('\n')[1:-2]).decode('BASE64')


def ec_to_private_pem(ec, cipher = None, password = None):

    def get_password(*args):
        return password or ''

    bio = M2Crypto.BIO.MemoryBuffer()
    ec.save_key_bio(bio, cipher, get_password)
    return bio.read_all()


def ec_to_public_pem(ec):
    bio = M2Crypto.BIO.MemoryBuffer()
    ec.save_pub_key_bio(bio)
    return bio.read_all()


def ec_from_private_pem(pem, password = None):

    def get_password(*args):
        return password or ''

    return M2Crypto.EC.load_key_bio(M2Crypto.BIO.MemoryBuffer(pem), get_password)


def ec_from_public_pem(pem):
    return M2Crypto.EC.load_pub_key_bio(M2Crypto.BIO.MemoryBuffer(pem))


def ec_to_private_bin(ec):
    return ec_private_pem_to_private_bin(ec_to_private_pem(ec))


def ec_to_public_bin(ec):
    return ec_public_pem_to_public_bin(ec_to_public_pem(ec))


def ec_from_private_bin(string):
    return ec_from_private_pem(''.join(('-----BEGIN EC PRIVATE KEY-----\n', string.encode('BASE64'), '-----END EC PRIVATE KEY-----\n')))


def ec_from_public_bin(string):
    return ec_from_public_pem(''.join(('-----BEGIN PUBLIC KEY-----\n', string.encode('BASE64'), '-----END PUBLIC KEY-----\n')))


def ec_signature_length(ec):
    return int(ceil(len(ec) / 8.0)) * 2


def ec_sign(ec, digest):
    length = int(ceil(len(ec) / 8.0))
    r, s = ec.sign_dsa(digest)
    return '\x00' * (length - len(r) + 4) + r[4:] + '\x00' * (length - len(s) + 4) + s[4:]


def ec_verify(ec, digest, signature):
    length = len(signature) / 2
    prefix = pack('!L', length)
    try:
        return bool(ec.verify_dsa(digest, prefix + signature[:length], prefix + signature[length:]))
    except:
        return False


def rsa_generate_key(bits = 1024, exponent = 5, progress = _progress):
    return M2Crypto.RSA.gen_key(bits, exponent, progress)


def rsa_to_private_pem(rsa, cipher = 'aes_128_cbc', password = None):

    def get_password(*args):
        return password or '-empty-'

    bio = M2Crypto.BIO.MemoryBuffer()
    rsa.save_key_bio(bio, cipher, get_password)
    return bio.read_all()


def rsa_to_private_bin(rsa, cipher = 'aes_128_cbc', password = None):
    pem = rsa_to_private_pem(rsa, cipher, password)
    lines = pem.split('\n')
    return ''.join(lines[4:-2]).decode('BASE64')


def rsa_to_public_pem(rsa):
    bio = M2Crypto.BIO.MemoryBuffer()
    rsa.save_pub_key_bio(bio)
    return bio.read_all()


def rsa_to_public_bin(rsa, cipher = 'aes_128_cbc', password = None):
    pem = rsa_to_public_pem(rsa, cipher, password)
    lines = pem.split('\n')
    return ''.join(lines[1:-2]).decode('BASE64')


def rsa_from_private_pem(pem, password = None):

    def get_password(*args):
        return password or '-empty-'

    return M2Crypto.RSA.load_key_bio(M2Crypto.BIO.MemoryBuffer(pem), get_password)


def rsa_from_public_pem(pem):
    return M2Crypto.RSA.load_pub_key_bio(M2Crypto.BIO.MemoryBuffer(pem))


if __name__ == '__main__':

    def EC_name(curve):
        for name in dir(M2Crypto.EC):
            value = getattr(M2Crypto.EC, name)
            if isinstance(value, int) and value == curve:
                return name


    import math
    import time
    for curve in [u'low', u'medium', u'high']:
        ec = ec_generate_key(curve)
        private_pem = ec_to_private_pem(ec)
        public_pem = ec_to_public_pem(ec)
        public_bin = ec_to_public_bin(ec)
        private_bin = ec_to_private_bin(ec)
        print 'generated:', time.ctime()
        print 'curve:', curve, '<<<', EC_name(_curves[curve]), '>>>'
        print 'len:', len(ec), 'bits ~', ec_signature_length(ec), 'bytes signature'
        print 'pub:', len(public_bin), public_bin.encode('HEX')
        print 'prv:', len(private_bin), private_bin.encode('HEX')
        print 'pub-sha1', sha1(public_bin).digest().encode('HEX')
        print 'prv-sha1', sha1(private_bin).digest().encode('HEX')
        print public_pem.strip()
        print private_pem.strip()
        print
        ec2 = ec_from_public_pem(public_pem)
        ec2 = ec_from_private_pem(private_pem)
        ec2 = ec_from_public_bin(public_bin)
        ec2 = ec_from_private_bin(private_bin)
