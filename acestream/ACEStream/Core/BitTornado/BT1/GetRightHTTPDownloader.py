#Embedded file name: ACEStream\Core\BitTornado\BT1\GetRightHTTPDownloader.pyo
import sys
import time
from random import randint
from urlparse import urlparse
from httplib import HTTPConnection
import urllib
from threading import Thread, currentThread, Lock, Event
from traceback import print_stack, print_exc
from ACEStream.version import VERSION
from ACEStream.Core.BitTornado.CurrentRateMeasure import Measure
from ACEStream.Core.Utilities.timeouturlopen import find_proxy
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False

class SingleDownloadHelperInterface():

    def __init__(self):
        pass


EXPIRE_TIME = 60 * 60
MAX_REDIRECTS = 5
USER_AGENT = 'ACEStream/' + VERSION
SEED_UNKNOWN = 0
SEED_GOOD = 1
SEED_BAD = 2
HTTP_UNKNOWN = 0
HTTP_OK = 1
HTTP_FATAL_ERROR = 2
HTTP_NONFATAL_ERROR = 3
MIN_SPEED_ANALYZE_TIME = 10
MIN_SPEED_ANALYZE_AMOUNT = 1048576

class haveComplete():

    def complete(self):
        return True

    def toboollist(self):
        return [True]

    def __getitem__(self, x):
        return True


haveall = haveComplete()

class SingleDownload(SingleDownloadHelperInterface):

    def __init__(self, downloader, url):
        SingleDownloadHelperInterface.__init__(self)
        self.downloader = downloader
        self.baseurl = url
        try:
            self.scheme, self.netloc, path, pars, query, fragment = urlparse(url)
        except:
            if DEBUG:
                log('HTTPDownloader::__init__: cannot parse url', url)
            self.downloader.errorfunc('cannot parse http seed address: ' + url)
            return

        if self.scheme != 'http':
            if DEBUG:
                log('HTTPDownloader::__init__: not http url', url)
            self.downloader.errorfunc('http seed url not http: ' + url)
            return
        self.proxyhost = find_proxy(url)
        try:
            if self.proxyhost is None:
                self.connection = HTTPConnection(self.netloc)
            else:
                self.connection = HTTPConnection(self.proxyhost)
        except:
            if DEBUG:
                print >> sys.stderr, 'HTTPDownloader::__init__: cannot connect to http seed', url
            self.downloader.errorfunc('cannot connect to http seed: ' + url)
            return

        self.url = path
        if len(query) > 0:
            self.url += '?' + query
        self.measure = Measure(downloader.max_rate_period)
        self.short_measure = Measure(10.0)
        self.total_read_time = 0.0
        self.total_read_bytes = 0
        self.avg_speed = 0
        self.last_speed = 0
        self.total_read_time_non_proxy = 0.0
        self.total_read_bytes_non_proxy = 0
        self.avg_speed_non_proxy = 0
        self.total_read_time_proxy = 0.0
        self.total_read_bytes_proxy = 0
        self.avg_speed_proxy = 0
        self.max_speed = 0
        self.is_proxy = False
        self.proxy_seek_data = None
        self.proxy_speed_data = None
        self.seed_status = SEED_UNKNOWN
        self.http_status = HTTP_UNKNOWN
        self.next_try = None
        self.stop_proxy_data = None
        self.cancel_flag = False
        self.stop_flag = False
        self.shutdown_flag = False
        self.proxy_respect_reserved_pieces = False
        self.vodmode = False
        self.index = None
        self.new_playback_pos = None
        self.last_requested_piece = None
        self.last_received_piece = None
        self.piece_size = self.downloader.storage._piecelen(0)
        self.total_len = self.downloader.storage.total_length
        self.requests = []
        self.proxy_requests = {}
        self.request_size = 0
        self.request_stream_pos = 0
        self.request_piece_pos = 0
        self.request_range = ''
        self.endflag = False
        self.error = None
        self.retry_period = 10
        self._retry_period = None
        self.errorcount = 0
        self.goodseed = False
        self.active = False
        self.cancelled = False
        self.request_lock = Lock()
        self.video_support_policy = True
        self.video_support_enabled = False
        self.video_support_speed = 0.0
        self.video_support_slow_start = False
        if not self.video_support_policy:
            self.resched(1)

    def resched(self, len = None):
        if self.video_support_policy:
            if not self.video_support_enabled or self.video_support_slow_start:
                if DEBUG:
                    log('ghttp::resched: cancel: url', self.baseurl, 'video_support_policy', self.video_support_policy, 'video_support_enabled', self.video_support_enabled, 'video_support_slow_start', self.video_support_slow_start)
                return
        if self.stop_flag:
            if DEBUG:
                log('ghttp::resched: got stop flag on reschedule, exit: url', self.baseurl)
            return
        if len is None:
            len = self.retry_period
        if DEBUG:
            log('ghttp::resched: len', len)
        if len > 0:
            self.downloader.rawserver.add_task(self.download, len)
        else:
            self.download()

    def _want(self, index):
        if self.endflag or self.vodmode:
            want = self.downloader.storage.do_I_have_requests(index)
        else:
            want = self.downloader.storage.is_unstarted(index)
        return want

    def can_start(self, min_speed = None):
        if self.seed_status == SEED_BAD:
            return False
        if self.http_status == HTTP_FATAL_ERROR:
            return False
        if self.next_try is not None and self.next_try > time.time():
            return False
        if min_speed is not None and self.avg_speed > 0 and self.avg_speed < min_speed:
            return False
        return True

    def start_proxy(self, pos, callback_failed = None, speed = None, respect_reserved_pieces = False):
        if DEBUG:
            log('ghttp::start_proxy: run _start_proxy in a separate thread: pos', pos, 'speed', speed, 'respect_reserved_pieces', respect_reserved_pieces)
        self.is_proxy = True
        self.proxy_respect_reserved_pieces = respect_reserved_pieces
        from ACEStream.Core.Session import Session
        session = Session.get_instance()
        f = lambda : self._start_proxy(pos, callback_failed, speed)
        session.uch.perform_usercallback(f)

    def stop_proxy(self, finish_piece = False):
        if DEBUG:
            log('ghttp::stop_proxy: finish_piece', finish_piece, 'thread', currentThread().getName())
        self.stop_proxy_data = {'finish_piece': finish_piece}

    def is_stopping(self):
        return not not self.stop_proxy_data

    def seek_proxy(self, pos, speed = None, respect_reserved_pieces = False):
        if DEBUG:
            log('ghttp::seek_proxy: pos', pos, 'speed', speed, 'respect_reserved_pieces', respect_reserved_pieces, 'thread', currentThread().getName())
        self.proxy_seek_data = {'pos': pos}
        self.proxy_speed_data = speed
        self.proxy_respect_reserved_pieces = respect_reserved_pieces

    def set_speed_data(self, speed_data):
        if DEBUG:
            log('ghttp::set_speed_data:', speed_data)
        self.proxy_speed_data = speed_data

    def _start_proxy(self, pos, callback_failed = None, speed = None):
        if DEBUG:
            log('ghttp::_start_proxy: acquire lock: pos', pos, 'thread', currentThread().getName())
        self.request_lock.acquire()
        self.active = True
        if DEBUG:
            log('ghttp::_start_proxy: acquire lock done: pos', pos, 'thread', currentThread().getName())
        resched = False
        try:
            if self.seed_status == SEED_BAD:
                if DEBUG:
                    log('ghttp::_start_proxy: bad seed at start, skip start: thread', currentThread().getName())
                self.active = False
                return
            self.downloader.proxy_started(self)
            if self.proxy_seek_data is not None:
                if DEBUG:
                    log('ghttp::_start_proxy: seek on start: proxy_seek_data', self.proxy_seek_data, 'thread', currentThread().getName())
                pos = self.proxy_seek_data['pos']
                self.proxy_seek_data = None
            if self.proxy_speed_data is not None:
                speed = self.proxy_speed_data
                self.proxy_speed_data = None
            while True:
                if self.stop_proxy_data is not None:
                    if DEBUG:
                        log('ghttp::_start_proxy: stop on start: thread', currentThread().getName())
                    break
                if not self.goodseed:
                    self.goodseed = True
                    self.downloader.seedsfound += 1
                self.proxy_requests = {}
                resched = self.read_raw(pos, speed)
                if self.proxy_seek_data is not None:
                    self.release_proxy_requests()
                    pos = self.proxy_seek_data['pos']
                    if self.proxy_speed_data is not None:
                        speed = self.proxy_speed_data
                        self.proxy_speed_data = None
                    else:
                        speed = None
                    if DEBUG:
                        log('ghttp::_start_proxy: seek proxy: pos', pos, 'speed', speed, 'thread', currentThread().getName())
                    self.proxy_seek_data = None
                    continue
                break

        except:
            self.errorcount += 1
            resched = False
            log_exc()
        finally:
            self.release_proxy_requests()
            failed = False
            retry_in = 0.1
            if self.seed_status == SEED_BAD or self.http_status == HTTP_FATAL_ERROR:
                failed = True
                resched = False
            elif self.errorcount > 0:
                failed = True
                resched = True
                retry_in = 5 * (1 + self.errorcount / 10)
                self.next_try = time.time() + retry_in
                if DEBUG:
                    log('ghttp::_start_proxy: got errors, set retry: errors', self.errorcount, 'retry_in', retry_in)
            if failed:
                if callback_failed is not None:
                    callback_failed()
                if self.goodseed:
                    self.goodseed = False
                    self.downloader.seedsfound -= 1
            self.stop_proxy_data = None
            self.is_proxy = False
            self.downloader.proxy_stopped(self)
            self.active = False
            self.request_lock.release()
            if resched:
                self.video_support_enabled = True
                self.stop_flag = False
                self.shutdown_flag = False
                self.resched(retry_in)
            else:
                self.video_support_enabled = False

    def read_raw(self, pos, speed_data = None):
        chunk_size = self.downloader.storage.request_size
        read_size = chunk_size
        offset = pos % chunk_size
        newpos = pos - offset
        if DEBUG:
            log('ghttp::read_raw: url', self.baseurl, 'pos', pos, 'chunk_size', chunk_size, 'offset', offset, 'newpos', newpos, 'speed_data', speed_data)
        pos = newpos
        current_piece_index, current_piece_offset = self.downloader.voddownload.piecepos_from_bytepos(self.downloader.voddownload.videostatus, pos)
        if DEBUG:
            log('ghttp::read_raw: start request: url', self.baseurl, 'pos', pos, 'index', current_piece_index, 'offset', current_piece_offset, 'proxy_respect_reserved_pieces', self.proxy_respect_reserved_pieces)
        if self.proxy_respect_reserved_pieces:
            self.downloader.picker_lock.acquire()
        try:
            while True:
                try_next_piece = False
                if self.proxy_respect_reserved_pieces and not self.downloader.storage.do_I_have_requests(current_piece_index):
                    try_next_piece = True
                    if DEBUG:
                        log('ghttp::read_raw: no inactive requests, try next piece: url', self.baseurl, 'pos', pos, 'index', current_piece_index)
                else:
                    gaps = self.downloader.storage.get_unfinished_gaps(current_piece_index)
                    if len(gaps) == 0:
                        try_next_piece = True
                        if DEBUG:
                            log('ghttp::read_raw: no unfinished gaps, try next piece: url', self.baseurl, 'pos', pos, 'index', current_piece_index)
                if try_next_piece:
                    current_piece_index += 1
                    current_piece_offset = 0
                    if current_piece_index > self.downloader.voddownload.videostatus.last_piece:
                        if DEBUG:
                            log('ghttp::read_raw: reached last piece, exit: url', self.baseurl, 'pos', pos, 'index', current_piece_index)
                        return False
                    piece_start, piece_end = self.downloader.voddownload.bytepos_from_piecepos(self.downloader.voddownload.videostatus, current_piece_index)
                    pos = piece_start
                    if DEBUG:
                        log('ghttp::read_raw: trying next piece: url', self.baseurl, 'pos', pos, 'index', current_piece_index)
                    continue
                first_gap_start = gaps[0][0]
                if DEBUG:
                    log('ghttp::read_raw: found gaps: url', self.baseurl, 'pos', pos, 'index', current_piece_index, 'current_piece_offset', current_piece_offset, 'first_gap_start', first_gap_start)
                if first_gap_start > current_piece_offset:
                    pos += first_gap_start - current_piece_offset
                    if DEBUG:
                        log('ghttp::read_raw: adjust start pos: url', self.baseurl, 'pos', pos, 'index', current_piece_index, 'first_gap_start', first_gap_start)
                break

            self.proxy_requests[current_piece_index] = self.downloader.storage.get_all_piece_request(current_piece_index)[:]
        finally:
            if self.proxy_respect_reserved_pieces:
                self.downloader.picker_lock.release()

        if DEBUG:
            log('ghttp::read_raw: start request, reserve requests: index', current_piece_index, 'url', self.baseurl, 'requests', self.proxy_requests[current_piece_index])
        start_pos = pos
        request_range = str(pos) + '-'
        redirects = 0
        retval = True
        while redirects < MAX_REDIRECTS:
            if self.proxyhost is None:
                realurl = self.url
            else:
                realurl = self.scheme + '://' + self.netloc + self.url
            if DEBUG:
                log('ghttp::read_raw: redirects', redirects, 'host', self.netloc, 'realurl', realurl, 'request_range', request_range)
            t = time.time()
            time_start_read = t
            self.short_measure.reset()
            self.connection.request('GET', realurl, None, {'Host': self.netloc,
             'User-Agent': USER_AGENT,
             'Range': 'bytes=%s' % request_range})
            r = self.connection.getresponse()
            self.total_read_time += time.time() - t
            self.total_read_time_proxy += time.time() - t
            if r.status == 301 or r.status == 302:
                redirect_url = r.getheader('Location', None)
                if DEBUG:
                    log('ghttp::read_raw: got redirect: status', r.status, 'redirect_url', redirect_url, 'host', self.netloc, 'realurl', realurl)
                if redirect_url is None:
                    break
                try:
                    self.scheme, redirect_host, path, pars, query, fragment = urlparse(redirect_url)
                    self.url = path
                    if len(query) > 0:
                        self.url += '?' + query
                except:
                    if DEBUG:
                        log('ghttp::read_raw: failed to parse redirect url:', redirect_url)
                    break

                if redirect_host != self.netloc:
                    self.netloc = redirect_host
                    if self.proxyhost is None:
                        self.connection = HTTPConnection(self.netloc)
                ++redirects
            else:
                break

        if DEBUG:
            log('ghttp::read_raw: request finished: pos', pos, 'baseurl', self.baseurl, 'host', self.netloc, 'realurl', realurl, 'status', r.status)
        if r.status != 200 and r.status != 206:
            self.connection.close()
            if 400 <= r.status < 500:
                self.http_status = HTTP_FATAL_ERROR
                retval = False
            else:
                self.http_status = HTTP_NONFATAL_ERROR
                self.errorcount += 1
                retval = True
            return retval
        self.http_status = HTTP_OK
        self.errorcount = 0
        self.next_try = None
        total_read = 0
        expected_read = self.downloader.voddownload.videostatus.selected_movie['size'] - pos
        if DEBUG:
            log('ghttp::read_raw: start read: pos', pos, 'expected_read', expected_read, 'baseurl', self.baseurl, 'chunk_size', chunk_size)
        request_history = []
        stop_at_pos = None
        while True:
            t = time.time()
            chunk = r.read(read_size)
            self.total_read_time += time.time() - t
            self.total_read_time_proxy += time.time() - t
            if not chunk:
                if total_read != expected_read:
                    if DEBUG:
                        log('ghttp::read_raw: read less data than expected: url', self.baseurl, 'start_pos', start_pos, 'pos', pos, 'total_read', total_read, 'expected_read', expected_read)
                    raise Exception('Failed to receive data')
                break
            length = len(chunk)
            total_read += length
            if length != read_size and total_read != expected_read:
                if DEBUG:
                    log('ghttp::read_raw: read bad chunk: url', self.baseurl, 'start_pos', start_pos, 'pos', pos, 'chunk_length', length, 'read_size', read_size, 'total_read', total_read, 'expected_read', expected_read)
                raise Exception('Failed to receive data')
            current_piece_index, current_piece_offset = self.downloader.voddownload.piecepos_from_bytepos(self.downloader.voddownload.videostatus, pos)
            if DEBUG:
                log('ghttp::read_raw: read chunk: pos', pos, 'len', length, 'index', current_piece_index, 'offset', current_piece_offset)
            seek_pos = self.downloader.voddownload.got_proxy_data(pos, chunk)
            if seek_pos is not None:
                if self.stop_proxy_data is not None:
                    if DEBUG:
                        log('ghttp::read_raw: got stop flag after seek request from got_proxy_data, skip seeking: index', current_piece_index, 'seek_pos', seek_pos, 'stop_proxy_data', self.stop_proxy_data, 'url', self.baseurl)
                    retval = True
                    break
                if self.proxy_seek_data is not None:
                    log('ghttp::read_raw: got seek from got_proxy_data, but already got a seek request: url', self.baseurl, 'proxy_seek_data', self.proxy_seek_data)
                else:
                    bytes_to_seek = seek_pos - pos - length
                    speed = self.short_measure.get_rate_noupdate()
                    time_to_seek = float(bytes_to_seek) / max(speed, 0.1)
                    if time_to_seek > 2:
                        if DEBUG:
                            log('ghttp::read_raw: got seek from got_proxy_data, do seek: seek_pos', seek_pos, 'bytes_to_seek', bytes_to_seek, 'time_to_seek', time_to_seek, 'speed', speed)
                        self.proxy_seek_data = {'pos': seek_pos}
                        self.proxy_speed_data = speed_data
                        break
                    elif DEBUG:
                        log('ghttp::read_raw: got seek from got_proxy_data, skip seek: seek_pos', seek_pos, 'bytes_to_seek', bytes_to_seek, 'time_to_seek', time_to_seek, 'speed', speed)
            t = time.time()
            try:
                if not self.downloader.storage.do_I_have(current_piece_index):
                    if current_piece_index not in self.proxy_requests:
                        self.proxy_requests[current_piece_index] = self.downloader.storage.get_all_piece_request(current_piece_index)[:]
                        if DEBUG:
                            log('ghttp::read_raw: reserve requests: index', current_piece_index, 'requests', self.proxy_requests[current_piece_index])
                    try:
                        self.proxy_requests[current_piece_index].remove((current_piece_offset, length))
                        if DEBUG:
                            log('ghttp::read_raw: remove request: index', current_piece_index, 'offset', current_piece_offset, 'len', length, 'pos', pos, 'url', self.baseurl)
                    except:
                        if DEBUG:
                            log('ghttp::read_raw: no request: index', current_piece_index, 'offset', current_piece_offset, 'len', length, 'pos', pos, 'url', self.baseurl)

                    self.last_requested_piece = current_piece_index
                    status = self.downloader.storage.piece_came_in(current_piece_index, current_piece_offset, [], chunk)
                    if status == 2:
                        if self.seed_status == SEED_UNKNOWN:
                            self.seed_status = SEED_GOOD
                        self.last_received_piece = current_piece_index
                        self.downloader.picker.complete(current_piece_index)
                        self.downloader.peerdownloader.check_complete(current_piece_index)
                        self.downloader.gotpiecefunc(current_piece_index)
                    elif status == 0:
                        if DEBUG:
                            log('ghttp::read_raw: bad piece: index', current_piece_index, 'piece_offset', current_piece_offset, 'len', length)
                        self.seed_status = SEED_BAD
                        break
            except:
                log_exc()

            if self.stop_proxy_data is not None:
                if self.stop_proxy_data['finish_piece']:
                    piece_start, piece_end = self.downloader.voddownload.bytepos_from_piecepos(self.downloader.voddownload.videostatus, current_piece_index)
                    stop_at_pos = piece_end
                    if DEBUG:
                        log('ghttp::read_raw: proxy stopped while reading: finish_piece', self.stop_proxy_data['finish_piece'], 'index', current_piece_index, 'stop_at_pos', stop_at_pos, 'baseurl', self.baseurl, 'thread', currentThread().getName())
                else:
                    if DEBUG:
                        log('ghttp::read_raw: proxy stopped while reading: finish_piece', self.stop_proxy_data['finish_piece'], 'baseurl', self.baseurl, 'thread', currentThread().getName())
                    retval = True
                    break
            if self.proxy_seek_data is not None:
                if DEBUG:
                    log('ghttp::read_raw: proxy seek while reading: pos', pos, 'proxy_seek_data', self.proxy_seek_data, 'baseurl', self.baseurl, 'thread', currentThread().getName())
                if self.stop_proxy_data is not None:
                    self.stop_proxy_data = None
                    if DEBUG:
                        log('ghttp::read_raw: reset stop_proxy_data on seek')
                time_start_read = time.time()
                if start_pos <= self.proxy_seek_data['pos'] <= pos + length:
                    if DEBUG:
                        log('ghttp::read_raw: proxy seek into downloaded range, skip seek: start_pos', start_pos, 'pos', pos, 'length', length, 'seek_pos', self.proxy_seek_data['pos'])
                    self.proxy_seek_data = None
                elif self.proxy_seek_data['pos'] >= start_pos:
                    bytes_to_seek = self.proxy_seek_data['pos'] - pos - length
                    speed = self.short_measure.get_rate_noupdate()
                    time_to_seek = float(bytes_to_seek) / max(speed, 0.1)
                    if time_to_seek > 2.0:
                        if DEBUG:
                            log('ghttp::read_raw: proxy seek, stop current request: pos', pos, 'length', length, 'seek_pos', self.proxy_seek_data['pos'], 'bytes_to_seek', bytes_to_seek, 'speed', speed, 'time_to_seek', time_to_seek)
                        break
                    else:
                        if DEBUG:
                            log('ghttp::read_raw: proxy seek, keep current request: pos', pos, 'length', length, 'seek_pos', self.proxy_seek_data['pos'], 'bytes_to_seek', bytes_to_seek, 'speed', speed, 'time_to_seek', time_to_seek)
                        self.proxy_seek_data = None
                elif self.proxy_seek_data['pos'] < start_pos:
                    skip_seek = False
                    if self.proxy_respect_reserved_pieces:
                        seek_piece, seek_piece_offset = self.downloader.voddownload.piecepos_from_bytepos(self.downloader.voddownload.videostatus, self.proxy_seek_data['pos'])
                        if not self.downloader.storage.do_I_have_requests(seek_piece):
                            skip_seek = True
                        if DEBUG:
                            log('ghttp::read_raw: check is seek position has inactive requests: url', self.baseurl, 'seek_pos', self.proxy_seek_data['pos'], 'seek_piece', seek_piece, 'seek_piece_offset', 'skip_seek', skip_seek)
                    if not skip_seek:
                        if DEBUG:
                            log('ghttp::read_raw: proxy seek, stop current request: start_pos', start_pos, 'pos', pos, 'length', length, 'seek_pos', self.proxy_seek_data['pos'])
                        break
                else:
                    if DEBUG:
                        log('ghttp::read_raw: proxy seek, stop current request: start_pos', start_pos, 'pos', pos, 'length', length, 'seek_pos', self.proxy_seek_data['pos'])
                    break
            if self.proxy_speed_data is not None:
                speed_data = self.proxy_speed_data
                self.proxy_speed_data = None
            pos += length
            self.total_read_bytes += length
            self.total_read_bytes_proxy += length
            if self.total_read_time >= MIN_SPEED_ANALYZE_TIME or self.total_read_bytes >= MIN_SPEED_ANALYZE_AMOUNT:
                self.avg_speed = self.total_read_bytes / self.total_read_time
            if stop_at_pos is None and self.total_read_time_proxy >= MIN_SPEED_ANALYZE_TIME or self.total_read_bytes_proxy >= MIN_SPEED_ANALYZE_AMOUNT:
                self.avg_speed_proxy = self.total_read_bytes_proxy / self.total_read_time_proxy
            if self.avg_speed > self.max_speed:
                self.max_speed = self.avg_speed
            self.measure.update_rate(length)
            self.downloader.measurefunc(length)
            current_rate = self.short_measure.update_rate(length)
            if stop_at_pos is not None and pos >= stop_at_pos:
                if DEBUG:
                    log('ghttp::read_raw: stop position reached, stop proxy: pos', pos, 'stop_at_pos', stop_at_pos)
                retval = True
                break
            if speed_data is not None:
                now = time.time()
                if now >= time_start_read + speed_data['timeout']:
                    if current_rate < speed_data['min_speed_fail']:
                        index, piece_offset = self.downloader.voddownload.piecepos_from_bytepos(self.downloader.voddownload.videostatus, pos - length)
                        piecelen = self.downloader.storage._piecelen(index)
                        bytes_left = piecelen - piece_offset
                        time_left = bytes_left / float(max(current_rate, 0.0001))
                        if DEBUG:
                            log('ghttp::read_raw: failed to gain desired speed: current_rate', current_rate, 'speed_data', speed_data, 'pos', pos, 'index', index, 'piece_offset', piece_offset, 'piecelen', piecelen, 'bytes_left', bytes_left, 'time_left', time_left)
                        stop_proxy, finish_piece, start_http_support = speed_data['callback'](self, current_rate, time_left)
                        if DEBUG:
                            log('ghttp::read_raw: response from speed callback: stop_proxy', stop_proxy, 'finish_piece', finish_piece, 'start_http_support', start_http_support)
                        if stop_proxy:
                            if not finish_piece:
                                if start_http_support:
                                    if DEBUG:
                                        log('ghttp::read_raw: failed to gain desired speed, stop proxy and switch to regular mode')
                                    retval = True
                                else:
                                    if DEBUG:
                                        log('ghttp::read_raw: failed to gain desired speed, stop proxy')
                                    retval = False
                                break
                            else:
                                retval = True
                                piece_start, piece_end = self.downloader.voddownload.bytepos_from_piecepos(self.downloader.voddownload.videostatus, index)
                                stop_at_pos = piece_end
                                if DEBUG:
                                    log('ghttp::read_raw: failed to gain desired speed, stop after current piece: index', index, 'start', piece_start, 'end', piece_end, 'stop_at_pos', stop_at_pos)
                                if pos >= stop_at_pos:
                                    if DEBUG:
                                        log('ghttp::read_raw: stop position reached, stop proxy: pos', pos, 'stop_at_pos', stop_at_pos)
                                    break

        if DEBUG:
            log('ghttp::read_raw: read done: retval', retval, 'status', r.status, 'request_range', request_range, 'total_read', total_read, 'baseurl', self.baseurl, 'host', self.netloc, 'realurl', realurl)
        self.connection.close()
        return retval

    def download(self):
        if self.is_proxy:
            if DEBUG:
                log('ghttp::download: proxy mode active, skip regular download: baseurl', self.baseurl, 'thread', currentThread().getName())
            return
        if self.stop_flag:
            if DEBUG:
                log('ghttp::download: got stop flag: url', self.baseurl)
            return
        if self.request_lock.locked():
            if DEBUG:
                log('ghttp::download: locked, exit: baseurl', self.baseurl)
            return
        self.vodmode = self.downloader.voddownload is not None
        if DEBUG:
            log('ghttp::download: set vodmode', self.vodmode)
        from ACEStream.Core.Session import Session
        session = Session.get_instance()
        session.uch.perform_usercallback(self._download)

    def _download(self):
        self.request_lock.acquire()
        if DEBUG:
            log('ghttp::_download: start: url', self.baseurl, 'vodmode', self.vodmode, 'thread', currentThread().getName())
        if self.stop_flag:
            if DEBUG:
                log('ghttp::_download: got stop flag: url', self.baseurl)
            self.request_lock.release()
            return
        self.cancelled = False
        if self.downloader.picker.am_I_complete():
            self.request_lock.release()
            self.downloader.downloads.remove(self)
            if DEBUG:
                log('ghttp::_download: completed, exit')
            return
        self.downloader.picker_lock.acquire()
        try:
            if self.vodmode and not self.downloader.voddownload.videostatus.prebuffering:
                self.index = self.downloader.voddownload.http_support_request_piece(self)
            else:
                self.index = self.downloader.picker.next(haveall, self._want, self, shuffle=False)
            if self.index is None and not self.vodmode and not self.endflag:
                if DEBUG:
                    log('ghttp::_download: index is none, set endflag: url', self.baseurl)
                self.endflag = True
                self.index = self.downloader.picker.next(haveall, self._want, self, shuffle=False)
            if self.index is None:
                self.request_lock.release()
                self.downloader.picker_lock.release()
                if DEBUG:
                    log('ghttp::_download: index is none, exit: vodmode', self.vodmode, 'endflag', self.endflag, 'url', self.baseurl)
                self.resched(1)
                return
            if not self._get_requests():
                if DEBUG:
                    log('ghttp::_download: cannot get requests, reschedule: index', index, 'url', self.baseurl)
                self.request_lock.release()
                self.downloader.picker_lock.release()
                self.resched(0.01)
                return
            gaps = self.downloader.storage.get_unfinished_gaps(self.index)
            if len(gaps) == 0:
                if DEBUG:
                    log('ghttp::_download: no unfinished gaps, reschedule: index', index, 'url', self.baseurl)
                self.request_lock.release()
                self.downloader.picker_lock.release()
                self.resched(0.01)
                return
            if DEBUG:
                log('ghttp::_download: got unfinished gaps: url', self.baseurl, 'gaps', gaps)
            self.last_requested_piece = self.index
            if self.vodmode:
                piece_start, piece_len = self.downloader.voddownload.bytepos_from_piecepos(self.downloader.voddownload.videostatus, self.index)
            else:
                piece_start = self.piece_size * self.index
            first_gap_start = gaps[0][0]
            last_gap_end = gaps[-1][1]
            self.request_piece_pos = first_gap_start
            self.request_stream_pos = piece_start + first_gap_start
            end = piece_start + last_gap_end
            self.request_range = '%d-%d' % (self.request_stream_pos, end)
            self.request_size = end - self.request_stream_pos + 1
            if DEBUG:
                log('ghttp::_download: start: index', self.index, 'piece_start', piece_start, 'first_gap_start', first_gap_start, 'last_gap_end', last_gap_end, 'range', self.request_range, 'size', self.request_size, 'url', self.baseurl)
            self.downloader.picker_lock.release()
            self.active = True
            self._request(self.vodmode)
        except:
            log_exc()
            self.downloader.picker_lock.release()

    def _request(self, vodmode):
        self.error = None
        self.received_data = None
        if not self.goodseed:
            self.goodseed = True
            self.downloader.seedsfound += 1
        try:
            redirects = 0
            while redirects < MAX_REDIRECTS:
                if self.proxyhost is None:
                    realurl = self.url
                else:
                    realurl = self.scheme + '://' + self.netloc + self.url
                if DEBUG:
                    log('ghttp::_request: redirects', redirects, 'host', self.netloc, 'realurl', realurl, 'index', self.index, 'request_range', self.request_range, 'vodmode', vodmode)
                time_start_connection = time.time()
                self.short_measure.reset()
                self.connection.request('GET', realurl, None, {'Host': self.netloc,
                 'User-Agent': USER_AGENT,
                 'Range': 'bytes=%s' % self.request_range})
                r = self.connection.getresponse()
                if r.status == 301 or r.status == 302:
                    redirect_url = r.getheader('Location', None)
                    if DEBUG:
                        log('ghttp::_request: got redirect: status', r.status, 'redirect_url', redirect_url, 'host', self.netloc, 'realurl', realurl)
                    if redirect_url is None:
                        break
                    try:
                        self.scheme, redirect_host, path, pars, query, fragment = urlparse(redirect_url)
                        self.url = path
                        if len(query) > 0:
                            self.url += '?' + query
                    except:
                        if DEBUG:
                            log('ghttp::_request: failed to parse redirect url:', redirect_url)
                        break

                    if redirect_host != self.netloc:
                        self.netloc = redirect_host
                        if self.proxyhost is None:
                            self.connection = HTTPConnection(self.netloc)
                    ++redirects
                else:
                    break

            self.connection_status = r.status
            if DEBUG:
                log('ghttp::_request: request finished, start read: status', r.status, 'baseurl', self.baseurl, 'host', self.netloc, 'realurl', realurl, 'vodmode', vodmode)
            if r.status != 200 and r.status != 206:
                data = None
                self.errorcount += 1
            elif self.cancel_flag:
                data = None
                if DEBUG:
                    log('ghttp::_request: got cancel flag before read: url', self.baseurl)
            elif self.stop_flag:
                data = None
                if DEBUG:
                    log('ghttp::_request: got stop flag before read: url', self.baseurl)
            elif self.shutdown_flag:
                data = None
                if DEBUG:
                    log('ghttp::_request: got shutdown flag before read: url', self.baseurl)
            else:
                self.errorcount = 0
                data = ''
                total_read = 0
                chunk_size = self.downloader.storage.request_size
                stream_pos = self.request_stream_pos
                piece_pos = self.request_piece_pos
                while True:
                    t = time.time()
                    chunk = r.read(chunk_size)
                    if not chunk:
                        if total_read != self.request_size:
                            if DEBUG:
                                log('ghttp::_request: read less data than expected: url', self.baseurl, 'request_range', self.request_range, 'request_size', self.request_size, 'total_read', total_read)
                            raise Exception('Failed to receive data')
                        break
                    time_read = time.time() - t
                    length = len(chunk)
                    total_read += length
                    if length != chunk_size and total_read != self.request_size:
                        if DEBUG:
                            log('ghttp::_request: read bad chunk: url', self.baseurl, 'chunk_length', length, 'read_size', chunk_size, 'total_read', total_read, 'request_size', self.request_size, 'request_range', self.request_range)
                        raise Exception('Failed to receive data')
                    self.measure.update_rate(length)
                    self.short_measure.update_rate(length)
                    self.downloader.measurefunc(length)
                    if not vodmode:
                        data += chunk
                    else:
                        seek_pos = self.downloader.voddownload.got_proxy_data(stream_pos, chunk)
                        if seek_pos is not None:
                            if DEBUG:
                                log('ghttp::_request: got seek pos from voddownload: stream_pos', stream_pos, 'index', self.index, 'url', self.baseurl)
                            break
                        try:
                            self.requests.remove((piece_pos, length))
                            if DEBUG:
                                log('ghttp::_request: remove request: index', self.index, 'piece_pos', piece_pos, 'len', length, 'url', self.baseurl)
                        except:
                            if DEBUG:
                                log('ghttp::_request: no request: index', self.index, 'piece_pos', piece_pos, 'len', length, 'url', self.baseurl)

                        status = self.downloader.storage.piece_came_in(self.index, piece_pos, [], chunk)
                        if status == 0:
                            if DEBUG:
                                log('ghttp::_request: bad piece: index', self.index, 'piece_pos', piece_pos, 'url', self.baseurl)
                            self.seed_status = SEED_BAD
                            break
                        elif status == 2:
                            if DEBUG:
                                log('ghttp::_request: complete piece: index', self.index, 'piece_pos', piece_pos, 'url', self.baseurl)
                            if self.seed_status == SEED_UNKNOWN:
                                self.seed_status = SEED_GOOD
                            self.last_received_piece = self.index
                            self.downloader.picker.complete(self.index)
                            self.downloader.peerdownloader.check_complete(self.index)
                            self.downloader.gotpiecefunc(self.index)
                        if self.downloader.storage.do_I_have(self.index):
                            if DEBUG:
                                log('ghttp::_request: got piece, stop downloading: index', self.index, 'url', self.baseurl)
                            self._retry_period = 0.1
                            break
                        stream_pos += length
                        piece_pos += length
                    if self.cancel_flag:
                        if DEBUG:
                            log('ghttp::_request: got cancel flag while reading')
                        data = None
                        break
                    if self.stop_flag:
                        if DEBUG:
                            log('ghttp::_request: got stop flag while reading')
                        data = None
                        break
                    if self.shutdown_flag:
                        if DEBUG:
                            log('ghttp::_request: got shutdown flag')
                        data = None
                        break
                    if self.is_proxy or self.new_playback_pos is not None and self.new_playback_pos > self.index:
                        if DEBUG:
                            log('ghttp::_request: going to proxy mode or playback pos changed, cancel current request and discard data: baseurl', self.baseurl, 'index', self.index, 'request_range', self.request_range)
                        data = None
                        if self.new_playback_pos is not None:
                            self._retry_period = 0.1
                        break
                    if time_start_connection is not None:
                        self.total_read_time += time.time() - time_start_connection
                        self.total_read_time_non_proxy += time.time() - time_start_connection
                        time_start_connection = None
                    self.total_read_bytes += length
                    self.total_read_bytes_non_proxy += length
                    self.total_read_time += time_read
                    self.total_read_time_non_proxy += time_read
                    if self.total_read_time >= MIN_SPEED_ANALYZE_TIME or self.total_read_bytes >= MIN_SPEED_ANALYZE_AMOUNT:
                        self.avg_speed = self.total_read_bytes / max(self.total_read_time, 0.0001)
                    if self.total_read_time_non_proxy >= MIN_SPEED_ANALYZE_TIME or self.total_read_bytes_non_proxy >= MIN_SPEED_ANALYZE_AMOUNT:
                        self.avg_speed_non_proxy = self.total_read_bytes_non_proxy / max(self.total_read_time_non_proxy, 0.0001)

                self.last_speed = self.short_measure.get_rate_noupdate()
            self.received_data = data
            if DEBUG and self.received_data is not None:
                log('ghttp::_request: read done: status', self.connection_status, 'index', self.index, 'len(data)', len(self.received_data), 'last_speed', self.last_speed, 'url', self.baseurl)
            self.connection.close()
        except:
            if DEBUG:
                print_exc()
            self.error = 'error accessing http seed'
            try:
                self.connection.close()
            except:
                pass

            try:
                self.connection = HTTPConnection(self.netloc)
            except:
                self.connection = None

        self.request_finished(vodmode)

    def request_finished(self, vodmode):
        if DEBUG:
            log('ghttp::request_finished: baseurl', self.baseurl, 'vodmode', vodmode)
        self.active = False
        if self.shutdown_flag:
            self.request_lock.release()
            return
        if self.cancel_flag:
            self.cancel_flag = False
        if self.stop_flag:
            self.stop_flag = False
            self.video_support_enabled = False
        if self.error is not None:
            self.downloader.errorfunc(self.error)
            self.errorcount += 1
        if vodmode:
            self._release_requests()
        else:
            if self.received_data:
                self.errorcount = 0
                if not self._got_data():
                    self.received_data = None
            if not self.received_data:
                self._release_requests()
                self.downloader.peerdownloader.piece_flunked(self.index)
        self.index = None
        self.new_playback_pos = None
        self.request_lock.release()
        if self.seed_status == SEED_BAD:
            if self.goodseed:
                self.goodseed = False
                self.downloader.seedsfound -= 1
            if DEBUG:
                log('ghttp::request_finished: bad seed, stop asking: baseurl', self.baseurl)
            return
        if self.errorcount == 0:
            self._retry_period = 0.1
        else:
            self._retry_period = min(60.0, 5 * (1 + self.errorcount / 10))
        when = self._retry_period
        resched_lambda = lambda : self.resched(when)
        self.downloader.rawserver.add_task(resched_lambda)

    def _got_data(self):
        if self.connection_status == 503:
            try:
                self.retry_period = max(int(self.received_data), 5)
            except:
                pass

            if DEBUG:
                log('ghttp::_got_data: seed returned 503. self.url:', self.url, ' self.retry_period:', self.retry_period)
            return False
        if self.connection_status != 200 and self.connection_status != 206:
            self.errorcount += 1
            if DEBUG:
                log('ghttp::_got_data: connection_status', self.connection_status, 'url', self.url)
            return False
        self._retry_period = self.video_support_speed
        if len(self.received_data) != self.request_size:
            log('ghttp::_got_data: bad length: len(self.received_data)', len(self.received_data), 'self.request_size', self.request_size)
            return False
        if self.cancelled:
            return False
        if not self._fulfill_requests():
            if DEBUG:
                log('ghttp::_got_data: corrupted piece, mark as bad seed: baseurl', self.baseurl, 'index', self.index)
            self.seed_status = SEED_BAD
            return False
        self.last_received_piece = self.index
        if self.seed_status == SEED_UNKNOWN:
            self.seed_status = SEED_GOOD
        if self.downloader.storage.do_I_have(self.index):
            self.downloader.picker.complete(self.index)
            self.downloader.peerdownloader.check_complete(self.index)
            self.downloader.gotpiecefunc(self.index)
        return True

    def _get_requests(self):
        self.requests = []
        if DEBUG:
            log('ghttp::_get_requests: index', self.index)
        if self.downloader.storage.do_I_have_requests(self.index):
            self.requests.extend(self.downloader.storage.get_all_piece_request(self.index))
            self.requests.sort()
            if DEBUG:
                log('ghttp::_get_requests: got requests: index', self.index, 'len(requests)', len(self.requests), 'requests', self.requests)
            return True
        if DEBUG:
            log('ghttp::_get_requests: NO REQUESTS!!!: url', self.baseurl, 'index', index)
        return False

    def _fulfill_requests(self):
        success = True
        if DEBUG:
            log('ghttp::_fulfill_requests: len(requests)', len(self.requests))
        while self.requests:
            begin, length = self.requests.pop(0)
            if not self.downloader.storage.piece_came_in(self.index, begin, [], self.received_data[begin:begin + length]):
                success = False
                break

        return success

    def _release_requests(self):
        for begin, length in self.requests:
            self.downloader.storage.request_lost(self.index, begin, length)

        self.requests = []

    def release_reserved_requests(self, requests):
        if DEBUG:
            log('ghttp::release_reserved_requests:', requests)
        for index, begin, length in requests:
            self.downloader.storage.request_lost(index, begin, length)

        requests = []

    def release_proxy_requests(self):
        if DEBUG:
            log('ghttp::release_proxy_requests:', self.proxy_requests)
        for index, requests in self.proxy_requests.iteritems():
            for begin, length in requests:
                self.downloader.storage.request_lost(index, begin, length)

        self.proxy_requests = {}

    def _request_ranges(self):
        s = ''
        begin, length = self.requests[0]
        for begin1, length1 in self.requests[1:]:
            if begin + length == begin1:
                length += length1
                continue
            else:
                if s:
                    s += ','
                s += str(begin) + '-' + str(begin + length - 1)
                begin, length = begin1, length1

        if s:
            s += ','
        s += str(begin) + '-' + str(begin + length - 1)
        return s

    def helper_forces_unchoke(self):
        pass

    def helper_set_freezing(self, val):
        self.frozen_by_helper = val

    def slow_start_wake_up(self):
        self.video_support_slow_start = False
        self.resched(0)

    def is_slow_start(self):
        return self.video_support_slow_start

    def start_video_support(self, level = 0.0, sleep_time = None, min_speed = None):
        if self.is_proxy:
            if DEBUG:
                log('ghttp::start_video_support: seed is proxy, skip start: url', self.baseurl)
            self.video_support_enabled = True
            return False
        if min_speed is not None and self.avg_speed > 0 and self.avg_speed < min_speed:
            if DEBUG:
                log('ghttp::start_video_support: seed too slow, skip start: url', self.baseurl, 'min_speed', min_speed, 'avg_speed', self.avg_speed)
            self.video_support_enabled = False
            return False
        self.video_support_speed = 0.001 * (10 ** level - 1)
        if not self.video_support_enabled:
            self.video_support_enabled = True
            self.stop_flag = False
            self.shutdown_flag = False
            if DEBUG:
                log('ghttp::start_video_support: url', self.baseurl, 'vodmode', self.vodmode, 'level', level, 'sleep_time', sleep_time, 'min_speed', min_speed)
            if sleep_time:
                if not self.video_support_slow_start:
                    self.video_support_slow_start = True
                    self.downloader.rawserver.add_task(self.slow_start_wake_up, sleep_time)
            else:
                self.resched(self.video_support_speed)
        return True

    def stop_video_support(self, shutdown = False, stop = False):
        if shutdown:
            self.shutdown_flag = True
        if stop:
            self.stop_flag = True
        if not self.video_support_enabled:
            return
        if DEBUG:
            log('ghttp::stop_video_support: url', self.baseurl)
        self.video_support_enabled = False

    def is_video_support_enabled(self):
        return self.video_support_enabled

    def playback_pos_changed(self, playback_pos):
        if self.index is not None and self.index < playback_pos:
            if DEBUG:
                log('ghttp::playback_pos_changed: index', self.index, 'playback_pos', playback_pos, 'url', self.baseurl)
            self.new_playback_pos = playback_pos

    def got_piece(self, index):
        if DEBUG:
            log('ghttp::got_piece: index', index, 'self.index', self.index, 'url', self.baseurl)
        if self.index == index:
            self.cancel_flag = True


class GetRightHTTPDownloader():

    def __init__(self, storage, picker, rawserver, finflag, errorfunc, peerdownloader, max_rate_period, infohash, measurefunc, gotpiecefunc):
        self.storage = storage
        self.picker = picker
        self.rawserver = rawserver
        self.finflag = finflag
        self.errorfunc = errorfunc
        self.peerdownloader = peerdownloader
        self.infohash = infohash
        self.max_rate_period = max_rate_period
        self.gotpiecefunc = gotpiecefunc
        self.measurefunc = measurefunc
        self.downloads = []
        self.seedsfound = 0
        self.video_support_enabled = False
        self.picker_lock = Lock()
        self.proxy_lock = Lock()
        self.proxy_download = None
        self.voddownload = None

    def make_download(self, url):
        self.downloads.append(SingleDownload(self, url))
        return self.downloads[-1]

    def get_downloads(self):
        if self.finflag.isSet():
            return []
        return self.downloads

    def get_info(self, param = None):
        info = {}
        if param is None:
            count_all = 0
            count_proxy = 0
            count_regular = 0
            avg_speed_all = 0
            avg_speed_proxy = 0
            avg_speed_regular = 0
            for d in self.downloads:
                count_all += 1
                avg_speed_all += d.avg_speed
                if d.is_proxy:
                    count_proxy += 1
                    avg_speed_proxy += d.avg_speed
                else:
                    count_regular += 1
                    avg_speed_regular += d.avg_speed

            info = {'count_all': count_all,
             'count_proxy': count_proxy,
             'count_regular': count_regular,
             'avg_speed_all': avg_speed_all,
             'avg_speed_proxy': avg_speed_proxy,
             'avg_speed_regular': avg_speed_regular}
        return info

    def cancel_piece_download(self, pieces):
        for d in self.downloads:
            if d.active and d.index in pieces:
                d.cancelled = True

    def start_video_support(self, level = 0.0, sleep_time = None, min_speed = None):
        to_start = []
        for d in self.downloads:
            if d.can_start():
                to_start.append((d, d.avg_speed))

        to_start.sort(key=lambda x: x[1], reverse=True)
        if DEBUG:
            log('ghttp-d::start_video_support: to_start', [ (x[0].baseurl, x[1]) for x in to_start ])
        for d, avg_speed in to_start:
            enabled = d.start_video_support(level, sleep_time, min_speed)
            if not self.video_support_enabled and enabled:
                self.video_support_enabled = True

    def stop_video_support(self, shutdown = False, stop = False):
        if DEBUG:
            log('ghttp-d::stop_video_support: len(downloads)', len(self.downloads), 'shutdown', shutdown, 'stop', stop)
        for d in self.downloads:
            d.stop_video_support(shutdown, stop)

        self.video_support_enabled = False

    def is_video_support_enabled(self):
        return self.video_support_enabled

    def playback_pos_changed(self, playback_pos):
        for d in self.downloads:
            d.playback_pos_changed(playback_pos)

    def got_piece(self, index):
        for d in self.downloads:
            if d.active and not d.is_proxy and d.index is not None and d.index == index:
                d.got_piece(index)

    def is_slow_start(self):
        for d in self.downloads:
            if d.is_slow_start():
                return True

        return False

    def is_proxy_enabled(self, return_proxy = False):
        self.proxy_lock.acquire()
        try:
            if self.proxy_download is None:
                return
            if return_proxy:
                return self.proxy_download
            return (self.proxy_download.avg_speed, self.proxy_download.max_speed)
        finally:
            self.proxy_lock.release()

    def start_proxy(self, pos, seek = True, speed = None, callback_failed = None, respect_reserved_pieces = False):
        self.proxy_lock.acquire()
        try:
            if DEBUG:
                log('ghttp-d::start_proxy: pos', pos, 'seek', seek, 'speed', speed, 'proxy_download', not not self.proxy_download, 'thread', currentThread().getName())
            if self.proxy_download is not None:
                if seek:
                    self.proxy_download.seek_proxy(pos, speed, respect_reserved_pieces)
                return (self.proxy_download.avg_speed, self.proxy_download.max_speed)
            proxy = self.get_proxy(speed)
            if proxy is None:
                if DEBUG:
                    log('ghttp-d::start_proxy: cannot select proxy: speed', speed)
                return
            self.proxy_download = proxy
            proxy.start_proxy(pos, callback_failed, speed, respect_reserved_pieces)
            return (proxy.avg_speed, proxy.max_speed)
        finally:
            self.proxy_lock.release()

    def stop_proxy(self, finish_piece = False):
        self.proxy_lock.acquire()
        try:
            if self.proxy_download is not None:
                if DEBUG:
                    log('ghttp-d::stop_proxy: proxy_download', self.proxy_download.baseurl, 'thread', currentThread().getName())
                self.proxy_download.stop_proxy(finish_piece=finish_piece)
        except:
            log_exc()
        finally:
            self.proxy_lock.release()

    def proxy_started(self, proxy):
        self.proxy_lock.acquire()
        if DEBUG:
            log('ghttp-d::proxy_started:', proxy.baseurl)
        self.proxy_download = proxy
        self.proxy_lock.release()

    def proxy_stopped(self, proxy):
        self.proxy_lock.acquire()
        if DEBUG:
            log('ghttp-d::proxy_stopped:', proxy.baseurl)
        self.proxy_download = None
        self.proxy_lock.release()

    def get_proxy(self, speed_data):
        proxy1 = None
        proxy2 = None
        proxy3 = None
        for d in self.downloads:
            if proxy1 is None and d.can_start():
                proxy1 = d
                proxy2 = d
                proxy3 = d
            elif d.can_start():
                if d.avg_speed_proxy > proxy1.avg_speed_proxy:
                    proxy1 = d
                if d.avg_speed_non_proxy > proxy2.avg_speed_non_proxy:
                    proxy2 = d
                if d.avg_speed > proxy3.avg_speed:
                    proxy3 = d

        proxy = None
        if proxy1 is not None:
            if speed_data is None:
                if DEBUG:
                    log('ghttp-d::get_proxy: no speed data, select proxy3:', proxy3.baseurl)
                proxy = proxy3
            else:
                if DEBUG:
                    log('ghttp-d::get_proxy: candidates: speed_data', speed_data, 'proxy1', proxy1.avg_speed_proxy, proxy1.baseurl, 'proxy2', proxy2.avg_speed_non_proxy, proxy2.baseurl, 'proxy3', proxy3.avg_speed, proxy3.baseurl)
                if 'min_speed_start_proxy' in speed_data and proxy1.avg_speed_proxy >= speed_data['min_speed_start_proxy']:
                    proxy = proxy1
                    if DEBUG:
                        log('ghttp-d::get_proxy: selected proxy 1')
                elif 'min_speed_start_non_proxy' in speed_data and proxy2.avg_speed_non_proxy >= speed_data['min_speed_start_non_proxy']:
                    proxy = proxy2
                    if DEBUG:
                        log('ghttp-d::get_proxy: selected proxy 2')
                elif proxy3.avg_speed == 0 or proxy3.avg_speed >= speed_data['min_speed_start']:
                    proxy = proxy3
                    if DEBUG:
                        log('ghttp-d::get_proxy: selected proxy 3')
                elif DEBUG:
                    log('ghttp-d::get_proxy: cannot select proxy')
        return proxy

    def can_support(self, min_speed = None):
        for d in self.downloads:
            if d.can_start(min_speed):
                return True

        return False

    def set_voddownload(self, voddownload):
        self.voddownload = voddownload
