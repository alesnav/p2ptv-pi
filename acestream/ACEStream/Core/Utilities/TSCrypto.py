#Embedded file name: ACEStream\Core\Utilities\TSCrypto.pyo
import sys
import base64
import textwrap
import binascii
import hashlib
from cStringIO import StringIO
from M2Crypto import EVP, RC4

def xor_encrypt(data, key):
    chunk_size = 16384
    pos = 0
    l = len(data)
    is_str = isinstance(data, str)
    res = ''
    while pos < l:
        rc4 = RC4.RC4(key)
        chunk = data[pos:pos + chunk_size]
        if is_str:
            res += rc4.update(chunk)
        else:
            data.update(rc4.update(chunk), pos)
        pos += chunk_size
        del rc4

    return res


def block_encrypt(data, key):
    return xor_encrypt(data, key)


def block_decrypt(data, key):
    return xor_encrypt(data, key)


def m2_cipher_filter(cipher, inf, outf):
    while 1:
        buf = inf.read()
        if not buf:
            break
        outf.write(cipher.update(buf))

    outf.write(cipher.final())
    return outf.getvalue()


def m2_AES_encrypt(data, key):
    key = hashlib.md5(key).digest()
    iv = '\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    k = EVP.Cipher(alg='aes_128_cbc', key=key, iv=iv, op=1, padding=True)
    pbuf = StringIO(data)
    cbuf = StringIO()
    ciphertext = m2_cipher_filter(k, pbuf, cbuf)
    pbuf.close()
    cbuf.close()
    return ciphertext


def m2_AES_decrypt(data, key):
    key = hashlib.md5(key).digest()
    iv = '\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    j = EVP.Cipher(alg='aes_128_cbc', key=key, iv=iv, op=0, padding=True)
    pbuf = StringIO()
    cbuf = StringIO(data)
    plaintext = m2_cipher_filter(j, cbuf, pbuf)
    pbuf.close()
    cbuf.close()
    return plaintext


try:
    from Crypto.Cipher import AES

    def AES_encrypt(data, key):
        aes = AES.new(key, AES.MODE_CFB)
        return aes.encrypt(data)


    def AES_decrypt(data, key):
        aes = AES.new(key, AES.MODE_CFB)
        return aes.decrypt(data)


except:

    def AES_encrypt(data, key):
        return data


    def AES_decrypt(data, key):
        return data


USE_M2CRYPTO_SHA = False
if USE_M2CRYPTO_SHA:

    class sha:

        def __init__(self, data = None):
            self.hash = None
            self.md = EVP.MessageDigest('sha1')
            if data is not None:
                self.md.update(data)

        def update(self, data):
            if self.hash:
                raise ValueError('sha: Cannot update after calling digest (OpenSSL limitation)')
            self.md.update(data)

        def digest(self):
            if not self.hash:
                self.hash = self.md.final()
            return self.hash

        def hexdigest(self):
            d = self.digest()
            return binascii.hexlify(d)


else:
    from hashlib import sha1 as sha

def RSA_pub_key_from_der(der):
    from M2Crypto import RSA, BIO
    s = '-----BEGIN PUBLIC KEY-----\n'
    b = base64.standard_b64encode(der)
    s += textwrap.fill(b, 64)
    s += '\n'
    s += '-----END PUBLIC KEY-----\n'
    bio = BIO.MemoryBuffer(s)
    return RSA.load_pub_key_bio(bio)


def RSA_keypair_to_pub_key_in_der(keypair):
    from M2Crypto import RSA, BIO
    bio = BIO.MemoryBuffer()
    keypair.save_pub_key_bio(bio)
    pem = bio.read_all()
    stream = StringIO(pem)
    lines = stream.readlines()
    s = ''
    for i in range(1, len(lines) - 1):
        s += lines[i]

    return base64.standard_b64decode(s)
