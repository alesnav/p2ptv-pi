#Embedded file name: ACEStream\Core\ClosedSwarm\ClosedSwarm.pyo
import time
import os.path
from base64 import encodestring, decodestring
from M2Crypto.EC import pub_key_from_der
from ACEStream.Core.Overlay import permid
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
from ACEStream.Core.BitTornado.BT1.MessageID import *

class ClosedSwarmException(Exception):
    pass


class MissingKeyException(ClosedSwarmException):
    pass


class MissingCertificateException(ClosedSwarmException):
    pass


class BadMessageException(ClosedSwarmException):
    pass


class WrongSwarmException(ClosedSwarmException):
    pass


class InvalidSignatureException(ClosedSwarmException):
    pass


class InvalidPOAException(ClosedSwarmException):
    pass


class POAExpiredException(ClosedSwarmException):
    pass


def pubkey_from_der(der_key):
    return pub_key_from_der(decodestring(der_key))


def generate_cs_keypair(keypair_filename = None, pubkey_filename = None):
    keypair = permid.generate_keypair()
    if keypair_filename:
        permid.save_keypair(keypair, keypair_filename)
    pubkey = encodestring(str(keypair.pub().get_der())).replace('\n', '')
    if pubkey_filename:
        permid.save_pub_key(keypair, pubkey_filename)
    return (keypair, pubkey)


def read_cs_keypair(keypair_filename):
    return permid.read_keypair(keypair_filename)


def save_cs_keypair(keypair, keypairfilename):
    return keypair.save_key(keypairfilename, None)


def read_cs_pubkey(pubkey_filename):
    return open(pubkey_filename, 'r').read()


def write_poa_to_file(filename, poa):
    target = open(filename, 'wb')
    target.write(poa.serialize())
    return filename


def read_poa_from_file(filename):
    if not os.path.exists(filename):
        raise Exception("File '%s' not found" % filename)
    data = open(filename, 'rb').read()
    return POA.deserialize(data)


def trivial_get_poa(path, perm_id, swarm_id):
    filename = encodestring(perm_id).replace('\n', '')
    filename = filename.replace('/', '')
    filename = filename.replace('\\', '')
    t_id = encodestring(swarm_id).replace('\n', '')
    t_id = t_id.replace('/', '')
    t_id = t_id.replace('/', '')
    poa_path = os.path.join(path, filename + '.' + t_id + '.poa')
    return read_poa_from_file(poa_path)


def trivial_save_poa(path, perm_id, swarm_id, poa):
    filename = encodestring(perm_id).replace('\n', '')
    filename = filename.replace('/', '')
    filename = filename.replace('\\', '')
    t_id = encodestring(swarm_id).replace('\n', '')
    t_id = t_id.replace('/', '')
    t_id = t_id.replace('/', '')
    if not os.path.exists(path):
        os.makedirs(path)
    poa_path = os.path.join(path, filename + '.' + t_id + '.poa')
    return write_poa_to_file(poa_path, poa)


class POA:

    def __init__(self, torrent_id, torrent_pub_key, node_pub_key, signature = '', expire_time = 0):
        self.torrent_id = torrent_id
        self.torrent_pub_key = torrent_pub_key
        self.node_pub_key = node_pub_key
        self.signature = signature
        self.expire_time = expire_time

    def serialize_to_list(self):
        return [self.torrent_id,
         self.torrent_pub_key,
         self.node_pub_key,
         self.expire_time,
         self.signature]

    def deserialize_from_list(lst):
        if not lst or len(lst) < 5:
            raise InvalidPOAException('Bad list')
        torrent_id = lst[0]
        torrent_pub_key = lst[1]
        node_pub_key = lst[2]
        expire_time = lst[3]
        signature = lst[4]
        return POA(torrent_id, torrent_pub_key, node_pub_key, signature, expire_time)

    deserialize_from_list = staticmethod(deserialize_from_list)

    def serialize(self):
        lst = [self.torrent_id,
         self.torrent_pub_key,
         self.node_pub_key,
         self.expire_time,
         self.signature]
        return bencode(lst)

    def deserialize(encoded):
        if not encoded:
            raise InvalidPOAException('Cannot deserialize nothing')
        try:
            lst = bdecode(encoded)
            if len(lst) < 5:
                raise InvalidPOAException('Too few entries (got %d, expected 5)' % len(lst))
            return POA(lst[0], lst[1], lst[2], expire_time=lst[3], signature=lst[4])
        except Exception as e:
            raise InvalidPOAException('De-serialization failed (%s)' % e)

    deserialize = staticmethod(deserialize)

    def get_torrent_pub_key(self):
        return encodestring(self.torrent_pub_key).replace('\n', '')

    def verify(self):
        if self.expire_time and self.expire_time < time.mktime(time.gmtime()):
            raise POAExpiredException('Expired')
        try:
            lst = [self.torrent_id, self.torrent_pub_key, self.node_pub_key]
            b_list = bencode(lst)
            digest = permid.sha(b_list).digest()
            pub = pub_key_from_der(self.torrent_pub_key)
            if not pub.verify_dsa_asn1(digest, self.signature):
                raise InvalidPOAException('Proof of access verification failed')
        except Exception as e:
            raise InvalidPOAException('Bad POA: %s' % e)

    def sign(self, torrent_key_pair):
        lst = [self.torrent_id, self.torrent_pub_key, self.node_pub_key]
        b_list = bencode(lst)
        digest = permid.sha(b_list).digest()
        self.signature = torrent_key_pair.sign_dsa_asn1(digest)

    def save(self, filename):
        target = open(filename, 'wb')
        target.write(self.serialize())
        target.close()
        return filename

    def load(filename):
        if not os.path.exists(filename):
            raise Exception("File '%s' not found" % filename)
        data = open(filename, 'rb').read()
        return POA.deserialize(data)

    load = staticmethod(load)


def create_poa(torrent_id, torrent_keypair, pub_permid, expire_time = 0):
    poa = POA(torrent_id, str(torrent_keypair.pub().get_der()), pub_permid, expire_time=expire_time)
    poa.sign(torrent_keypair)
    return poa


class ClosedSwarm:
    IDLE = 0
    EXPECTING_RETURN_CHALLENGE = 1
    EXPECTING_INITIATOR_RESPONSE = 2
    SEND_INITIATOR_RESPONSE = 3
    COMPLETED = 4

    def __init__(self, my_keypair, torrent_id, torrent_pubkeys, poa):
        if poa:
            if not poa.__class__ == POA:
                raise Exception('POA is not of class POA, but of class %s' % poa.__class__)
        self.state = self.IDLE
        self.my_keypair = my_keypair
        self.pub_permid = str(my_keypair.pub().get_der())
        self.torrent_id = torrent_id
        self.torrent_pubkeys = torrent_pubkeys
        self.poa = poa
        self.remote_node_authorized = False
        self.nonce_a = None
        self.nonce_b = None
        self.remote_nonce = None
        self.my_nonce = None
        if self.poa:
            if self.poa.get_torrent_pub_key() not in self.torrent_pubkeys:
                import sys
                print >> sys.stderr, 'Bad POA for this torrent (wrong torrent key!)'
                self.poa = None

    def is_remote_node_authorized(self):
        return self.remote_node_authorized

    def set_poa(self, poa):
        self.poa = poa

    def give_up(self):
        self.state = self.COMPLETED

    def is_incomplete(self):
        return self.state != self.COMPLETED

    def _create_challenge_msg(self, msg_id):
        self.my_nonce, my_nonce_bencoded = permid.generate_challenge()
        return [msg_id, self.torrent_id, self.my_nonce]

    def a_create_challenge(self):
        self.state = self.EXPECTING_RETURN_CHALLENGE
        return self._create_challenge_msg(CS_CHALLENGE_A)

    def b_create_challenge(self, lst):
        self.state = self.EXPECTING_INITIATOR_RESPONSE
        if len(lst) != 3:
            raise BadMessageException('Bad number of elements in message, expected 2, got %d' % len(lst))
        if lst[0] != CS_CHALLENGE_A:
            raise BadMessageException('Expected initial challenge, got something else')
        torrent_id, nonce_a = lst[1:]
        if self.torrent_id != torrent_id:
            raise WrongSwarmException('Expected %s, got %s' % (self.torrent_id, torrent_id))
        self.remote_nonce = nonce_a
        return self._create_challenge_msg(CS_CHALLENGE_B)

    def _create_poa_message(self, msg_id, nonce_a, nonce_b):
        if not self.poa:
            raise MissingCertificateException('Missing certificate')
        msg = [msg_id] + self.poa.serialize_to_list()
        lst = [nonce_a, nonce_b, self.poa.serialize()]
        b_list = bencode(lst)
        digest = permid.sha(b_list).digest()
        sig = self.my_keypair.sign_dsa_asn1(digest)
        msg.append(sig)
        return msg

    def _validate_poa_message(self, lst, nonce_a, nonce_b):
        if len(lst) != 7:
            raise BadMessageException('Require 7 elements, got %d' % len(lst))
        poa = POA.deserialize_from_list(lst[1:-1])
        sig = lst[-1]
        if poa.torrent_id != self.torrent_id:
            raise WrongSwarmException('Wrong swarm')
        if poa.get_torrent_pub_key() not in self.torrent_pubkeys:
            raise InvalidPOAException('Bad POA for this torrent')
        lst = [nonce_a, nonce_b, poa.serialize()]
        import sys
        b_list = bencode(lst)
        digest = permid.sha(b_list).digest()
        try:
            pub = pub_key_from_der(poa.node_pub_key)
        except:
            print >> sys.stderr, 'The node_pub_key is no good'
            print >> sys.stderr, poa.node_pub_key
            raise Exception("Node's public key is no good...")

        if not pub.verify_dsa_asn1(digest, sig):
            raise InvalidSignatureException('Freshness test failed')
        poa.verify()
        return poa

    def a_provide_poa_message(self, lst):
        self.state = self.COMPLETED
        if len(lst) != 3:
            raise BadMessageException('Require 3 elements, got %d' % len(lst))
        if lst[0] != CS_CHALLENGE_B:
            raise BadMessageException("Expected RETURN_CHALLENGE, got '%s'" % lst[0])
        if lst[1] != self.torrent_id:
            raise WrongSwarmException('POA for wrong swarm')
        self.remote_nonce = lst[2]
        msg = self._create_poa_message(CS_POA_EXCHANGE_A, self.my_nonce, self.remote_nonce)
        return msg

    def b_provide_poa_message(self, lst, i_am_seeding = False):
        self.state = self.COMPLETED
        if lst[0] != CS_POA_EXCHANGE_A:
            import sys
            print >> sys.stderr, 'Not CS_POA_EXCHANGE_A'
            raise BadMessageException('Expected POA EXCHANGE')
        try:
            self._validate_poa_message(lst, self.remote_nonce, self.my_nonce)
            self.remote_node_authorized = True
        except Exception as e:
            self.remote_node_authorized = False
            import sys
            print >> sys.stderr, 'POA could not be validated:', e

        if i_am_seeding:
            return
        msg = self._create_poa_message(CS_POA_EXCHANGE_B, self.remote_nonce, self.my_nonce)
        return msg

    def a_check_poa_message(self, lst):
        self.state = self.COMPLETED
        if lst[0] != CS_POA_EXCHANGE_B:
            raise BadMessageException('Expected POA EXCHANGE')
        self._validate_poa_message(lst, self.my_nonce, self.remote_nonce)
        self.remote_node_authorized = True
