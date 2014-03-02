#Embedded file name: ACEStream\Core\Video\VideoSource.pyo
import os
import sys
from threading import RLock, Thread
from traceback import print_exc
from time import sleep
from ACEStream.GlobalConfig import globalConfig
from ACEStream.Core.BitTornado.BT1.PiecePicker import PiecePicker
from ACEStream.Core.simpledefs import *
from ACEStream.Core.Video.LiveSourceAuth import NullAuthenticator, ECDSAAuthenticator, RSAAuthenticator
from ACEStream.Core.Utilities.TSCrypto import sha
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.BitTornado.CurrentRateMeasure import Measure
DEBUG = False
DEBUG_TRANSPORT = False

class SimpleThread(Thread):

    def __init__(self, runfunc):
        Thread.__init__(self)
        self.setDaemon(True)
        self.setName('VideoSourceSimple' + self.getName())
        self.runfunc = runfunc

    def run(self):
        self.runfunc()


class VideoSourceTransporter:

    def __init__(self, stream, bt1download, authconfig, restartstatefilename):
        self.stream = stream
        self.bt1download = bt1download
        self.restartstatefilename = restartstatefilename
        self.exiting = False
        self.ratemeasure = Measure(30)
        self.storagewrapper = bt1download.storagewrapper
        self.picker = bt1download.picker
        self.rawserver = bt1download.rawserver
        self.connecter = bt1download.connecter
        self.fileselector = bt1download.fileselector
        self.videostatus = bt1download.videostatus
        self.buffer = []
        self.buflen = 0
        self.bufferlock = RLock()
        self.handling_pieces = False
        self.readlastseqnum = False
        if authconfig.get_method() == LIVE_AUTHMETHOD_ECDSA:
            self.authenticator = ECDSAAuthenticator(self.videostatus.piecelen, self.bt1download.len_pieces, keypair=authconfig.get_keypair())
        elif authconfig.get_method() == LIVE_AUTHMETHOD_RSA:
            self.authenticator = RSAAuthenticator(self.videostatus.piecelen, self.bt1download.len_pieces, keypair=authconfig.get_keypair())
        else:
            self.authenticator = NullAuthenticator(self.videostatus.piecelen, self.bt1download.len_pieces)

    def start(self):
        self.input_thread_handle = SimpleThread(self.input_thread)
        self.input_thread_handle.start()

    def _read(self, length):
        return self.stream.read(length)

    def input_thread(self):
        log('stream: started input thread')
        contentbs = self.authenticator.get_content_blocksize()
        try:
            if DEBUG_TRANSPORT:
                f = open('/tmp/stream.dat', 'wb')
            while not self.exiting:
                data = self._read(contentbs)
                if not data:
                    break
                if DEBUG:
                    log('VideoSource: read %d bytes' % len(data))
                if DEBUG_TRANSPORT:
                    log('VideoSource::input_thread: read chunk: want', contentbs, 'len', len(data))
                    f.write(data)
                self.ratemeasure.update_rate(len(data))
                self.process_data(data)

            if DEBUG_TRANSPORT:
                f.close()
        except IOError:
            if DEBUG:
                print_exc()

        self.shutdown()

    def shutdown(self):
        if DEBUG:
            log('VideoSource::shutdown: ---')
        if self.exiting:
            return
        self.exiting = True
        try:
            self.stream.close()
        except IOError:
            pass

    def process_data(self, data):
        vs = self.videostatus
        self.bufferlock.acquire()
        try:
            self.buffer.append(data)
            self.buflen += len(data)
            if not self.handling_pieces:
                self.rawserver.add_task(self.create_pieces)
                self.handling_pieces = True
        finally:
            self.bufferlock.release()

    def create_pieces(self):

        def handle_one_piece():
            vs = self.videostatus
            contentbs = self.authenticator.get_content_blocksize()
            if self.buflen < contentbs:
                return False
            if len(self.buffer[0]) == contentbs:
                content = self.buffer[0]
                del self.buffer[0]
            else:
                if DEBUG:
                    print >> sys.stderr, 'VideoSource: JOIN ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^'
                buffer = ''.join(self.buffer)
                self.buffer = [buffer[contentbs:]]
                content = buffer[:contentbs]
            self.buflen -= contentbs
            datas = self.authenticator.sign(content)
            piece = ''.join(datas)
            self.add_piece(vs.playback_pos, piece)
            self.del_piece(vs.live_piece_to_invalidate())
            self.readlastseqnum = True
            if self.restartstatefilename is not None:
                try:
                    lastseqnum = self.authenticator.get_source_seqnum()
                    f = open(self.restartstatefilename, 'wb')
                    f.write(str(lastseqnum))
                    f.close()
                except:
                    print_exc()

            vs.inc_playback_pos()
            return True

        if not self.readlastseqnum and self.restartstatefilename is not None and os.path.isfile(self.restartstatefilename):
            self.readlastseqnum = True
            try:
                f = open(self.restartstatefilename, 'rb')
                data = f.read()
                f.close()
                lastseqnum = int(data)
                log('stream: restarting stream from piece', lastseqnum)
                lastpiecenum = lastseqnum % self.authenticator.get_npieces()
                self.authenticator.set_source_seqnum(lastseqnum)
                self.videostatus.set_live_startpos(lastpiecenum)
            except:
                print_exc()

        self.bufferlock.acquire()
        try:
            while handle_one_piece():
                pass

            self.handling_pieces = False
        finally:
            self.bufferlock.release()

    def add_piece(self, index, piece):
        if DEBUG:
            log('VideoSource::add_piece: index', index)
        if globalConfig.get_value('live_source_show_pieces', False):
            log('stream: created piece', index, 'speed %.2f KiB/s' % (self.ratemeasure.get_rate_noupdate() / 1024))
        chunk_size = self.storagewrapper.request_size
        length = min(len(piece), self.storagewrapper._piecelen(index))
        x = 0
        while x < length:
            self.storagewrapper.new_request(index)
            self.storagewrapper.piece_came_in(index, x, [], piece[x:x + chunk_size])
            x += chunk_size

        self.picker.complete(index)
        self.connecter.got_piece(index)

    def del_piece(self, piece):
        if DEBUG:
            log('VideoSource::del_piece:', piece)
        self.picker.downloader.live_invalidate(piece)


class RateLimitedVideoSourceTransporter(VideoSourceTransporter):

    def __init__(self, ratelimit, *args, **kwargs):
        VideoSourceTransporter.__init__(self, *args, **kwargs)
        self.ratelimit = int(ratelimit)

    def _read(self, length):
        t = 1.0 * length / self.ratelimit
        if DEBUG:
            print >> sys.stderr, 'RateLimitedVideoSourceTransporter::_read: ratelimit', self.ratelimit, 'sleep', t
        sleep(t)
        return VideoSourceTransporter._read(self, length)


class PiecePickerSource(PiecePicker):

    def next(self, *args, **kwargs):
        return None

    def complete(self, *args, **kwargs):
        return True

    def got_have(self, *args, **kwargs):
        return True

    def lost_have(self, *args, **kwargs):
        pass

    def invalidate_piece(self, *args, **kwargs):
        pass

    def got_peer(self, *args, **kwargs):
        pass

    def lost_peer(self, *args, **kwargs):
        pass
