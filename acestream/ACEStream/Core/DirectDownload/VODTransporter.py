#Embedded file name: ACEStream\Core\DirectDownload\VODTransporter.pyo
import os
import time
import binascii
from traceback import print_exc
from threading import Condition
from ACEStream.Core.Video.MovieTransport import MovieTransport, MovieTransportStreamWrapper
from ACEStream.Core.simpledefs import *
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False
DEFAULT_READ_SIZE = 1048576
REFILL_BUFFER_INTERVAL = 0.1

class VODTransporter(MovieTransport):

    def __init__(self, dd, dlhash, fileinfo, vodeventfunc):
        self.wait_sufficient_speed = dd.config.get('wait_sufficient_speed', False)
        self.player_buffer_time = dd.config.get('player_buffer_time', 5)
        self.live_buffer_time = dd.config.get('live_buffer_time', 10)
        self.fileinfo = fileinfo
        self.dd = dd
        self.rawserver = dd.rawserver
        self.downloader = dd.downloader
        self.storage = dd.storage
        self.vodeventfunc = vodeventfunc
        self.log_prefix = 'dd-vod::' + binascii.hexlify(dlhash) + ':'
        if DEBUG:
            log(self.log_prefix + '__init__: fileinfo', self.fileinfo, 'wait_sufficient_speed', self.wait_sufficient_speed, 'player_buffer_time', self.player_buffer_time)
        self.set_mimetype(self.fileinfo['mimetype'])
        bitrate = self.fileinfo.get('bitrate', None)
        if bitrate is None:
            self.bitrate_set = False
            self.bitrate = 102400
            if DEBUG:
                log(self.log_prefix + '__init__: set fake bitrate: bitrate', self.bitrate)
        else:
            self.bitrate_set = True
            self.bitrate = bitrate
            if DEBUG:
                log(self.log_prefix + '__init__: got bitrate: bitrate', self.bitrate)
        self.data_ready = Condition()
        self._complete = False
        self.filestream = None
        self.prebufprogress = 0.0
        self.prebufstart = time.time()
        self.playable = False
        self.usernotified = False
        self.playing = False
        self.prebuffering = True
        self.stream_pos = 0
        self.outbuf = []
        self.stat_outbuf = []
        self.outbuflen = 0
        self.outbufpos = 0
        self.update_prebuffering()
        self.refill_buffer_task()

    def set_bitrate(self, bitrate):
        if DEBUG:
            log(self.log_prefix + 'set_bitrate: bitrate', bitrate, 'fileinfo', self.fileinfo)
        self.bitrate = bitrate
        self.bitrate_set = True

    def is_playable(self):
        if not self.playable or self.prebuffering:
            self.playable = self.prebufprogress == 1.0 and self.enough_buffer()
        return self.playable

    def get_prebuffering_progress(self):
        return self.prebufprogress

    def complete(self):
        if DEBUG:
            log(self.log_prefix + 'complete: ---')
        if not self._complete:
            self._complete = True
            path = self.storage.get_dest_path()
            self.data_ready.acquire()
            try:
                self.filestream = open(path, 'rb')
                self.filestream.seek(self.stream_pos)
                if DEBUG:
                    log(self.log_prefix + 'complete: open file and seek: path', path, 'stream_pos', self.stream_pos)
                self.data_ready.notify()
            finally:
                self.data_ready.release()

    def got_data_observer(self, pos, length):
        if self.prebuffering:
            self.rawserver.add_task(self.update_prebuffering, 0.1)
            return True
        else:
            return False

    def update_prebuffering(self):
        if not self.prebuffering:
            return
        want_len = min(self.bitrate * self.player_buffer_time, self.storage.get_content_length())
        avail_len = self.storage.get_available_length(0)
        if avail_len >= want_len and self.enough_buffer():
            self.data_ready.acquire()
            try:
                if DEBUG:
                    log(self.log_prefix + 'update_prebuffering: ready: want', want_len, 'avail', avail_len)
                self.prebuffering = False
                self.notify_playable()
                self.data_ready.notify()
                return True
            finally:
                self.data_ready.release()

        else:
            if DEBUG:
                log(self.log_prefix + 'update_prebuffering: not ready: want', want_len, 'avail', avail_len)
            return False

    def expected_download_time(self):
        bytes_left = self.storage.get_amount_left()
        if bytes_left == 0:
            return True
        rate = self.downloader.measure.get_rate()
        if rate < 0.1:
            return float(2147483648L)
        time_left = bytes_left / float(rate)
        return time_left

    def expected_playback_time(self):
        bytes_to_play = self.storage.get_content_length() - self.outbufpos
        if bytes_to_play <= 0:
            return 0
        if not self.bitrate_set:
            return float(2147483648L)
        playback_time = bytes_to_play / float(self.bitrate)
        return playback_time

    def enough_buffer(self):
        try:
            if not self.bitrate_set:
                return True
            if not self.wait_sufficient_speed:
                return True
            expected_download_time = self.expected_download_time()
            expected_playback_time = self.expected_playback_time()
            if DEBUG:
                log(self.log_prefix + 'enough_buffer: expected_download_time', expected_download_time, 'expected_playback_time', expected_playback_time)
            return max(0.0, expected_download_time - expected_playback_time) == 0.0
        except:
            log_exc()
            return True

    def expected_buffering_time(self):
        download_time = self.expected_download_time()
        playback_time = self.expected_playback_time()
        if download_time > float(1073741824) and playback_time > float(1073741824):
            return float(2147483648L)
        return abs(download_time - playback_time)

    def get_playable_after(self):
        return self.expected_buffering_time()

    def notify_playable(self):
        self.prebufprogress = 1.0
        self.playable = True
        if self.usernotified:
            return
        mimetype = self.get_mimetype()
        complete = self.storage.is_finished()
        if complete:
            stream = None
            filename = self.storage.get_dest_path()
        else:
            stream = MovieTransportStreamWrapper(self)
            filename = None
        try:
            self.vodeventfunc(self.fileinfo, VODEVENT_START, {'complete': complete,
             'filename': filename,
             'mimetype': mimetype,
             'stream': stream,
             'length': self.storage.get_content_length(),
             'bitrate': self.bitrate})
        except:
            log_exc()

    def get_mimetype(self):
        return self.mimetype

    def set_mimetype(self, mimetype):
        self.mimetype = mimetype

    def start(self, bytepos = 0, force = False):
        if DEBUG:
            log(self.log_prefix + 'start: bytepos', bytepos, 'playing', self.playing, 'force', force)
        if self.playing and not force:
            return
        self.downloader.start(bytepos)
        self.data_ready.acquire()
        try:
            self.stream_pos = bytepos
            self.playing = True
            if self._complete:
                if self.filestream is None:
                    path = self.storage.get_dest_path()
                    if DEBUG:
                        log(self.log_prefix + 'start: open file: path', path)
                    self.filestream = open(path, 'rb')
                if DEBUG:
                    log(self.log_prefix + 'start: seek file: pos', bytepos)
                self.filestream.seek(bytepos)
            else:
                self.outbuf = []
                self.stat_outbuf = []
                self.outbuflen = 0
                self.outbufpos = self.stream_pos
        finally:
            self.data_ready.release()

        self.update_prebuffering()
        self.refill_buffer()

    def shutdown(self):
        if DEBUG:
            log(self.log_prefix + 'shutdown: ---')
        self.stop()

    def stop(self, seek = False):
        if DEBUG:
            log(self.log_prefix + 'stop: playing', self.playing, 'seek', seek)
        if not self.playing:
            return
        self.playing = False
        self.data_ready.acquire()
        try:
            self.outbuf = []
            self.stat_outbuf = []
            self.outbuflen = 0
            self.outbufpos = 0
            self.prebuffering = False
            if not seek:
                if self.filestream is not None:
                    if DEBUG:
                        log(self.log_prefix + 'stop: close filestream')
                    self.filestream.close()
                    self.filestream = None
            self.data_ready.notify()
        finally:
            self.data_ready.release()

    def seek(self, pos, whence = os.SEEK_SET):
        length = self.storage.get_content_length()
        self.data_ready.acquire()
        try:
            if whence == os.SEEK_SET:
                abspos = pos
            elif whence == os.SEEK_END:
                if pos > 0:
                    raise ValueError('seeking beyond end of stream')
                else:
                    abspos = length + pos
            else:
                raise ValueError('seeking does not currently support SEEK_CUR')
            if DEBUG:
                log(self.log_prefix + 'seek: pos', pos, 'whence', whence, 'length', length, 'abspos', abspos)
            if self._complete:
                if self.filestream is None:
                    path = self.storage.get_dest_path()
                    if DEBUG:
                        log(self.log_prefix + 'seek: open file:', path)
                    self.filestream = open(path, 'rb')
                if DEBUG:
                    log(self.log_prefix + 'seek: seek file: abspos', abspos)
                self.filestream.seek(abspos)
                self.stream_pos = abspos
            else:
                self.stop(seek=True)
                self.start(abspos)
        finally:
            self.data_ready.release()

    def read(self, numbytes = None):
        self.data_ready.acquire()
        try:
            data = self.pop(numbytes)
            if data is None:
                return
            self.stream_pos += len(data)
            if DEBUG:
                log(self.log_prefix + 'read: update stream pos: stream_pos', self.stream_pos, 'datalen', len(data))
            return data
        except:
            print_exc()
        finally:
            self.data_ready.release()

    def pop(self, max_size = None):
        while self.prebuffering and not self.done():
            self.data_ready.wait()

        while not self._complete and not self.outbuf and not self.done():
            self.data_ready.wait()

        if self._complete:
            if max_size is None:
                max_size = DEFAULT_READ_SIZE
            if DEBUG:
                log(self.log_prefix + 'pop: read from filestream: max_size', max_size)
            data = self.filestream.read(max_size)
            return data
        if not self.outbuf:
            if DEBUG:
                log(self.log_prefix + 'pop: empty buffer, return None: _complete', self._complete)
            return
        while True:
            bad_chunk = False
            start_pos = None
            total_length = 0
            total_data = ''
            if DEBUG:
                log(self.log_prefix + 'pop: read data from outbuf')
            while self.outbuf:
                pos, data = self.outbuf.pop(0)
                self.stat_outbuf.pop(0)
                length = len(data)
                if max_size is not None and total_length + length > max_size:
                    offset = total_length + length - max_size
                    newpos = pos + length - offset
                    newdata = data[-offset:]
                    data = data[:-offset]
                    oldlength = length
                    length = len(data)
                    if DEBUG:
                        log(self.log_prefix + 'pop: trim chunk to max size: pos', pos, 'oldlen', oldlength, 'max_size', max_size, 'offset', offset, 'total_len', total_length, 'newlen', length, 'newpos', newpos)
                    self.outbuf.insert(0, (newpos, newdata))
                    self.stat_outbuf.insert(0, (newpos, len(newdata)))
                if start_pos is None:
                    start_pos = pos
                total_data += data
                total_length += length
                self.outbuflen -= length
                if DEBUG:
                    log(self.log_prefix + 'pop: outbufpos', self.outbufpos, 'pos', pos, 'start_pos', start_pos, 'len', length, 'total_len', total_length, 'max_size', max_size, 'outbuflen', self.outbuflen)
                if not start_pos <= self.stream_pos <= start_pos + total_length:
                    if DEBUG:
                        log(self.log_prefix + 'pop: wrong chunk popped, discard: stream_pos', self.stream_pos, 'start_pos', start_pos, 'total_len', total_length)
                    bad_chunk = True
                    break
                if max_size is None:
                    break
                if total_length >= max_size:
                    if DEBUG:
                        log(self.log_prefix + 'pop: stop popping, max size reached: total_length', total_length, 'max_size', max_size)
                    break

            if bad_chunk:
                continue
            break

        return total_data

    def max_buffer_size(self):
        return int(self.player_buffer_time * self.bitrate * 2)

    def done(self):
        if not self.playing:
            return True
        return self.outbufpos == self.storage.get_content_length() and len(self.outbuf) == 0

    def refill_buffer(self):
        self.data_ready.acquire()
        try:
            if self.prebuffering or self._complete or not self.playing or self.done():
                return
            mx = self.max_buffer_size()
            length = self.storage.get_content_length()
            while self.outbuflen < mx and self.outbufpos < length:
                numbytes = mx - self.outbuflen
                if DEBUG:
                    log(self.log_prefix + 'refill_buffer: read from storage: pos', self.outbufpos, 'numbytes', numbytes, 'outbuflen', self.outbuflen, 'mx', mx)
                data = self.storage.read(self.outbufpos, numbytes)
                if not data:
                    if DEBUG:
                        log(self.log_prefix + 'refill_buffer: no data available: pos', self.outbufpos)
                    break
                datalen = len(data)
                self.outbuf.append((self.outbufpos, data))
                self.stat_outbuf.append((self.outbufpos, datalen))
                self.outbuflen += datalen
                self.outbufpos += datalen
                self.data_ready.notify()
                if DEBUG:
                    log(self.log_prefix + 'refill_buffer: got data from storage: datalen', datalen, 'outbufpos', self.outbufpos, 'outbuflen', self.outbuflen)

        except:
            log_exc()
        finally:
            self.data_ready.release()

    def refill_buffer_task(self):
        self.refill_buffer()
        self.rawserver.add_task(self.refill_buffer_task, REFILL_BUFFER_INTERVAL)

    def set_wait_sufficient_speed(self, value):
        if DEBUG:
            log(self.log_prefix + 'set_wait_sufficient_speed:', value)
        self.wait_sufficient_speed = value

    def set_player_buffer_time(self, value):
        if DEBUG:
            log(self.log_prefix + 'set_player_buffer_time:', value)
        self.player_buffer_time = value
