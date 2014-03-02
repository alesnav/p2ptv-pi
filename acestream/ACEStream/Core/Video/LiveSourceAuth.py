#Embedded file name: ACEStream\Core\Video\LiveSourceAuth.pyo
import sys
from traceback import print_exc
from cStringIO import StringIO
import struct
import time
import array
from ACEStream.Core.Utilities.TSCrypto import sha, RSA_pub_key_from_der
from ACEStream.Core.osutils import *
from M2Crypto import EC
from ACEStream.Core.osutils import *
from types import StringType
DEBUG = False

class Authenticator:

    def __init__(self, piecelen, npieces):
        self.piecelen = piecelen
        self.npieces = npieces
        self.seqnum = 0L

    def get_piece_length(self):
        return self.piecelen

    def get_npieces(self):
        return self.npieces

    def get_content_blocksize(self):
        pass

    def sign(self, content):
        pass

    def verify(self, piece):
        pass

    def get_content(self, piece):
        pass

    def get_source_seqnum(self):
        return self.seqnum

    def set_source_seqnum(self, seqnum):
        self.seqnum = seqnum


class NullAuthenticator(Authenticator):

    def __init__(self, piecelen, npieces):
        Authenticator.__init__(self, piecelen, npieces)
        self.contentblocksize = piecelen

    def get_content_blocksize(self):
        return self.contentblocksize

    def sign(self, content):
        return [content]

    def verify(self, piece):
        return True

    def get_content(self, piece):
        return piece


class ECDSAAuthenticator(Authenticator):
    SEQNUM_SIZE = 8
    RTSTAMP_SIZE = 8
    LENGTH_SIZE = 1
    MAX_ECDSA_ASN1_SIGSIZE = 64
    EXTRA_SIZE = SEQNUM_SIZE + RTSTAMP_SIZE
    OUR_SIGSIZE = EXTRA_SIZE + LENGTH_SIZE + MAX_ECDSA_ASN1_SIGSIZE

    def __init__(self, piecelen, npieces, keypair = None, pubkeypem = None):
        print >> sys.stderr, 'ECDSAAuth: npieces', npieces
        Authenticator.__init__(self, piecelen, npieces)
        self.contentblocksize = piecelen - self.OUR_SIGSIZE
        self.keypair = keypair
        if pubkeypem is not None:
            self.pubkey = EC.pub_key_from_der(pubkeypem)
        else:
            self.pubkey = None
        self.startts = None

    def get_content_blocksize(self):
        return self.contentblocksize

    def sign(self, content):
        rtstamp = time.time()
        extra = struct.pack('>Qd', self.seqnum, rtstamp)
        self.seqnum += 1L
        sig = ecdsa_sign_data(content, extra, self.keypair)
        lensig = chr(len(sig))
        if len(sig) != self.MAX_ECDSA_ASN1_SIGSIZE:
            diff = self.MAX_ECDSA_ASN1_SIGSIZE - len(sig)
            padding = '\x00' * diff
            return [content,
             extra,
             lensig,
             sig,
             padding]
        else:
            return [content,
             extra,
             lensig,
             sig]

    def verify(self, piece, index):
        try:
            extra = piece[-self.OUR_SIGSIZE:-self.OUR_SIGSIZE + self.EXTRA_SIZE]
            lensig = ord(piece[-self.OUR_SIGSIZE + self.EXTRA_SIZE])
            if lensig > self.MAX_ECDSA_ASN1_SIGSIZE:
                print >> sys.stderr, 'ECDSAAuth: @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ failed piece', index, 'lensig wrong', lensig
                return False
            diff = lensig - self.MAX_ECDSA_ASN1_SIGSIZE
            if diff == 0:
                sig = piece[-self.OUR_SIGSIZE + self.EXTRA_SIZE + self.LENGTH_SIZE:]
            else:
                sig = piece[-self.OUR_SIGSIZE + self.EXTRA_SIZE + self.LENGTH_SIZE:diff]
            content = piece[:-self.OUR_SIGSIZE]
            if DEBUG:
                print >> sys.stderr, 'ECDSAAuth: verify piece', index, 'sig', `sig`
                print >> sys.stderr, 'ECDSAAuth: verify dig', sha(content).hexdigest()
            ret = ecdsa_verify_data_pubkeyobj(content, extra, self.pubkey, sig)
            if ret:
                seqnum, rtstamp = self._decode_extra(piece)
                if DEBUG:
                    print >> sys.stderr, 'ECDSAAuth: verify piece', index, 'seq', seqnum, 'ts %.5f s' % rtstamp, 'ls', lensig
                mod = seqnum % self.get_npieces()
                thres = self.seqnum - self.get_npieces() / 2
                if seqnum <= thres:
                    print >> sys.stderr, 'ECDSAAuth: @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ failed piece', index, 'old seqnum', seqnum, '<<', self.seqnum
                    return False
                if mod != index:
                    print >> sys.stderr, 'ECDSAAuth: @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ failed piece', index, 'expected', mod
                    return False
                if self.startts is not None and rtstamp < self.startts:
                    print >> sys.stderr, 'ECDSAAuth: @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ failed piece', index, 'older than oldest known ts', rtstamp, self.startts
                    return False
                self.seqnum = max(self.seqnum, seqnum)
                if self.startts is None:
                    self.startts = rtstamp - 300.0
                    print >> sys.stderr, 'ECDSAAuth: @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@: startts', self.startts
            else:
                print >> sys.stderr, 'ECDSAAuth: @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ piece', index, 'failed sig'
            return ret
        except:
            print_exc()
            return False

    def get_content(self, piece):
        return piece[:-self.OUR_SIGSIZE]

    def get_seqnum(self, piece):
        seqnum, rtstamp = self._decode_extra(piece)
        return seqnum

    def get_rtstamp(self, piece):
        seqnum, rtstamp = self._decode_extra(piece)
        return rtstamp

    def _decode_extra(self, piece):
        extra = piece[-self.OUR_SIGSIZE:-self.OUR_SIGSIZE + self.EXTRA_SIZE]
        if type(extra) == array.array:
            extra = extra.tostring()
        return struct.unpack('>Qd', extra)


def ecdsa_sign_data(plaintext, extra, ec_keypair):
    digester = sha(plaintext)
    digester.update(extra)
    digest = digester.digest()
    return ec_keypair.sign_dsa_asn1(digest)


def ecdsa_verify_data_pubkeyobj(plaintext, extra, pubkey, blob):
    digester = sha(plaintext)
    digester.update(extra)
    digest = digester.digest()
    return pubkey.verify_dsa_asn1(digest, blob)


class RSAAuthenticator(Authenticator):
    SEQNUM_SIZE = 8
    RTSTAMP_SIZE = 8
    EXTRA_SIZE = SEQNUM_SIZE + RTSTAMP_SIZE

    def our_sigsize(self):
        return self.EXTRA_SIZE + self.rsa_sigsize()

    def rsa_sigsize(self):
        return len(self.pubkey) / 8

    def __init__(self, piecelen, npieces, keypair = None, pubkeypem = None, max_age = None):
        Authenticator.__init__(self, piecelen, npieces)
        self.keypair = keypair
        if pubkeypem is not None:
            self.pubkey = RSA_pub_key_from_der(pubkeypem)
        else:
            self.pubkey = self.keypair
        self.contentblocksize = piecelen - self.our_sigsize()
        self.startts = None
        if DEBUG:
            print >> sys.stderr, 'RSAAuthenticator::__init__: max_age', max_age
        self.max_age = max_age

    def get_content_blocksize(self):
        return self.contentblocksize

    def sign(self, content):
        rtstamp = time.time()
        extra = struct.pack('>Qd', self.seqnum, rtstamp)
        self.seqnum += 1L
        sig = rsa_sign_data(content, extra, self.keypair)
        return [content, extra, sig]

    def verify(self, piece, index):
        try:
            extra = piece[-self.our_sigsize():-self.our_sigsize() + self.EXTRA_SIZE]
            sig = piece[-self.our_sigsize() + self.EXTRA_SIZE:]
            content = piece[:-self.our_sigsize()]
            if DEBUG:
                print >> sys.stderr, 'RSAAuth::verify: index', index, 'extra', len(extra), 'sig', len(sig), 'content', len(content)
            ret = rsa_verify_data_pubkeyobj(content, extra, self.pubkey, sig)
            if ret:
                seqnum, rtstamp = self._decode_extra(piece)
                if DEBUG:
                    print >> sys.stderr, 'RSAAuth: verify piece', index, 'seq', seqnum, 'ts %.5f s' % rtstamp
                mod = seqnum % self.get_npieces()
                thres = self.seqnum - self.get_npieces() / 2
                if seqnum <= thres:
                    if DEBUG:
                        print >> sys.stderr, 'RSAAuth: @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ failed piece', index, 'old seqnum', seqnum, '<<', self.seqnum
                    return False
                if mod != index:
                    if DEBUG:
                        print >> sys.stderr, 'RSAAuth: @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ failed piece', index, 'expected', mod
                    return False
                if self.max_age is not None and self.startts is not None and rtstamp < self.startts - self.max_age:
                    if DEBUG:
                        print >> sys.stderr, 'RSAAuth: @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ failed piece', index, 'expired: last_ts', self.startts, 'piece_ts', rtstamp, 'max_age', self.max_age
                    return False
                self.seqnum = max(self.seqnum, seqnum)
                if self.startts is None:
                    self.startts = rtstamp
                else:
                    self.startts = max(self.startts, rtstamp)
                    if DEBUG:
                        print >> sys.stderr, 'RSAAuth: @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@: startts', self.startts
            elif DEBUG:
                print >> sys.stderr, 'RSAAuth: @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ piece', index, 'failed sig'
            return ret
        except:
            if DEBUG:
                print_exc()
            return False

    def get_content(self, piece):
        return piece[:-self.our_sigsize()]

    def get_seqnum(self, piece):
        seqnum, rtstamp = self._decode_extra(piece)
        return seqnum

    def get_rtstamp(self, piece):
        seqnum, rtstamp = self._decode_extra(piece)
        return rtstamp

    def _decode_extra(self, piece):
        extra = piece[-self.our_sigsize():-self.our_sigsize() + self.EXTRA_SIZE]
        if type(extra) == array.array:
            extra = extra.tostring()
        return struct.unpack('>Qd', extra)


def rsa_sign_data(plaintext, extra, rsa_keypair):
    digester = sha(plaintext)
    digester.update(extra)
    digest = digester.digest()
    return rsa_keypair.sign(digest)


def rsa_verify_data_pubkeyobj(plaintext, extra, pubkey, sig):
    digester = sha(plaintext)
    digester.update(extra)
    digest = digester.digest()
    s = sig.tostring()
    if DEBUG:
        import binascii
        print >> sys.stderr, 'rsa_verify_data_pubkeyobj: len(digest)', len(digest), 'len(s)', len(s), 'digest', digest, 'extra', extra, binascii.hexlify(extra.tostring())
    return pubkey.verify(digest, s)


class AuthStreamWrapper:

    def __init__(self, inputstream, authenticator):
        self.inputstream = inputstream
        self.buffer = StringIO()
        self.authenticator = authenticator
        self.piecelen = authenticator.get_piece_length()
        self.last_rtstamp = None

    def read(self, numbytes = None):
        rawdata = self._readn(self.piecelen)
        if len(rawdata) == 0:
            return rawdata
        content = self.authenticator.get_content(rawdata)
        self.last_rtstamp = self.authenticator.get_rtstamp(rawdata)
        if numbytes is None or numbytes < 0:
            raise ValueError('Stream has unlimited size, read all not supported.')
        elif numbytes < len(content):
            raise ValueError('reading less than piecesize not supported yet')
        else:
            return content

    def get_generation_time(self):
        return self.last_rtstamp

    def seek(self, pos, whence = os.SEEK_SET):
        if pos == 0 and whence == os.SEEK_SET:
            if DEBUG:
                print >> sys.stderr, 'AuthStreamWrapper:seek: ignoring seek 0 in live'
        else:
            raise ValueError('authstream does not support seek')

    def close(self):
        self.inputstream.close()

    def available(self):
        return self.inputstream.available()

    def _readn(self, n):
        nwant = n
        while True:
            data = self.inputstream.read(nwant)
            if len(data) == 0:
                return data
            nwant -= len(data)
            self.buffer.write(data)
            if nwant <= 0:
                break

        self.buffer.seek(0)
        data = self.buffer.read(n)
        self.buffer.seek(0)
        return data


class VariableReadAuthStreamWrapper:

    def __init__(self, inputstream, piecelen):
        self.inputstream = inputstream
        self.buffer = ''
        self.piecelen = piecelen

    def read(self, numbytes = None):
        if numbytes is None or numbytes < 0:
            raise ValueError('Stream has unlimited size, read all not supported.')
        return self._readn(numbytes)

    def get_generation_time(self):
        return self.inputstream.get_generation_time()

    def seek(self, pos, whence = os.SEEK_SET):
        return self.inputstream.seek(pos, whence=whence)

    def close(self):
        self.inputstream.close()

    def available(self):
        return self.inputstream.available()

    def _readn(self, nwant):
        if len(self.buffer) == 0:
            data = self.inputstream.read(self.piecelen)
            if len(data) == 0:
                return data
            self.buffer = data
        lenb = len(self.buffer)
        tosend = min(nwant, lenb)
        if tosend == lenb:
            pre = self.buffer
            post = ''
        else:
            pre = self.buffer[0:tosend]
            post = self.buffer[tosend:]
        self.buffer = post
        return pre
