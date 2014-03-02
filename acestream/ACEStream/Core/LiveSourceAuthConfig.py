#Embedded file name: ACEStream\Core\LiveSourceAuthConfig.pyo
from ACEStream.Core.simpledefs import *
import ACEStream.Core.Overlay.permid as permidmod
from ACEStream.Core.Utilities.TSCrypto import RSA_keypair_to_pub_key_in_der
from M2Crypto import RSA

class LiveSourceAuthConfig:

    def __init__(self, authmethod):
        self.authmethod = authmethod

    def get_method(self):
        return self.authmethod


class ECDSALiveSourceAuthConfig(LiveSourceAuthConfig):

    def __init__(self, keypair = None):
        LiveSourceAuthConfig.__init__(self, LIVE_AUTHMETHOD_ECDSA)
        if keypair is None:
            self.keypair = permidmod.generate_keypair()
        else:
            self.keypair = keypair

    def get_pubkey(self):
        return str(self.keypair.pub().get_der())

    def get_keypair(self):
        return self.keypair

    def load(filename):
        keypair = permidmod.read_keypair(filename)
        return ECDSALiveSourceAuthConfig(keypair)

    load = staticmethod(load)

    def save(self, filename):
        permidmod.save_keypair(self.keypair, filename)


class RSALiveSourceAuthConfig(LiveSourceAuthConfig):

    def __init__(self, keypair = None):
        LiveSourceAuthConfig.__init__(self, LIVE_AUTHMETHOD_RSA)
        if keypair is None:
            self.keypair = rsa_generate_keypair()
        else:
            self.keypair = keypair

    def get_pubkey(self):
        return RSA_keypair_to_pub_key_in_der(self.keypair)

    def get_keypair(self):
        return self.keypair

    def load(filename):
        keypair = rsa_read_keypair(filename)
        return RSALiveSourceAuthConfig(keypair)

    load = staticmethod(load)

    def save(self, filename):
        rsa_write_keypair(self.keypair, filename)


def rsa_generate_keypair():
    e = 3
    keysize = 768
    return RSA.gen_key(keysize, e)


def rsa_read_keypair(filename):
    return RSA.load_key(filename)


def rsa_write_keypair(keypair, filename):
    keypair.save_key(filename, cipher=None)
