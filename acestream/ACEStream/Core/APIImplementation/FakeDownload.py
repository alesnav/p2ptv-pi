#Embedded file name: ACEStream\Core\APIImplementation\FakeDownload.pyo
from ACEStream.Core.API import *
from ACEStream.Core.Utilities.EncryptedStorage import EncryptedStorageStream
from ACEStream.Core.Utilities.logger import log, log_exc

class FakeDownload:

    def __init__(self, dltype, path, meta, offset_fix, vodeventfunc):
        self.dltype = dltype
        self.path = path
        self.meta = meta
        self.offset_fix = offset_fix
        self.vodeventfunc = vodeventfunc

    def get_type(self):
        return self.dltype

    def get_mode(self):
        return DLMODE_VOD

    def get_hash(self):
        return self.meta['hash']

    def restart(self):
        if self.vodeventfunc is not None:
            stream = EncryptedStorageStream(self.path, self.meta['hash'], self.meta['file_length'], self.meta['offset'], self.meta['piecelen'], offset_fix=self.offset_fix)
            self.vodeventfunc(self, VODEVENT_START, {'complete': True,
             'filename': None,
             'mimetype': None,
             'stream': stream,
             'length': self.meta['file_length'],
             'bitrate': None,
             'blocksize': self.meta['piecelen']})

    def set_state_callback(self, usercallback, getpeerlist = False):
        ds = self.network_get_state()
        usercallback(ds)

    def network_get_state(self, usercallback = None, getpeerlist = False, sessioncalling = False):
        status = DLSTATUS_SEEDING
        ds = DownloadState(self, status, None, 1.0)
        return ds

    def got_duration(self, duration, from_player = True):
        pass
