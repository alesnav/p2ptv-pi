#Embedded file name: ACEStream\Core\Video\MovieTransport.pyo
import os, sys
from ACEStream.Core.osutils import *
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False

class MovieTransport:

    def __init__(self):
        pass

    def start(self, bytepos = 0):
        pass

    def size(self):
        pass

    def read(self):
        pass

    def stop(self):
        pass

    def done(self):
        pass

    def get_mimetype(self):
        pass

    def set_mimetype(self, mimetype):
        pass

    def available(self):
        pass


class MovieTransportStreamWrapper:

    def __init__(self, mt):
        self.mt = mt
        self.started = False

    def read(self, numbytes = None):
        if DEBUG:
            log('MovieTransportStreamWrapper::read: numbytes', numbytes)
        if not self.started:
            self.mt.start(0)
            self.started = True
        if self.mt.done():
            return ''
        data = self.mt.read(numbytes)
        if data is None:
            if DEBUG:
                log('MovieTransportStreamWrapper:read: mt.read returns None')
            data = ''
        return data

    def seek(self, pos, whence = os.SEEK_SET):
        if DEBUG:
            log('MovieTransportStreamWrapper::seek: pos', pos, 'whence', whence)
        if not self.started:
            self.mt.start(0)
            self.started = True
        else:
            self.mt.seek(pos, whence=whence)

    def close(self):
        if DEBUG:
            log('MovieTransportStreamWrapper::close')
        self.mt.stop()

    def available(self):
        return self.mt.available()

    def get_generation_time(self):
        raise ValueError('This is an unauthenticated stream that provides no timestamp')
