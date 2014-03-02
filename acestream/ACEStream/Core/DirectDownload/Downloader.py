#Embedded file name: ACEStream\Core\DirectDownload\Downloader.pyo
import os
import binascii
import time
from threading import Thread, Lock
from urlparse import urlparse
from httplib import HTTPConnection
from traceback import print_exc
from ACEStream.version import VERSION
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.BitTornado.CurrentRateMeasure import Measure
from ACEStream.Core.Utilities.timeouturlopen import urlOpenTimeout
DEBUG = False
USER_AGENT = 'ACEStream/' + VERSION
MAX_REDIRECTS = 10

class FatalErrorException(Exception):
    pass


class NonFatalErrorException(Exception):
    pass


class ReadErrorException(Exception):
    pass


class Downloader:

    def __init__(self, url, dlhash, rawserver, failed_func, max_errors = 10):
        if DEBUG:
            log('dd-downloader::__init__: url', url, 'hash', binascii.hexlify(dlhash))
        self.url = url
        self.rawserver = rawserver
        self.failed_func = failed_func
        self.final_url = None
        self.storage = None
        self.lock = Lock()
        self.measure = Measure(10.0)
        self.errors = 0
        self.max_errors = max_errors
        self.seek = None
        self.shutdown_flag = False
        self.running = False
        self.log_prefix = 'dd-downloader::' + binascii.hexlify(dlhash) + ':'

    def predownload(self, callback, timeout = 10):
        if self.lock.locked():
            self.seek = pos
            return
        t = Thread(target=self._predownload, args=[callback, timeout])
        t.setName('dd-downloader-predownload-' + t.getName())
        t.setDaemon(True)
        t.start()

    def _predownload(self, callback, timeout):
        self.lock.acquire()
        self.running = True
        try:
            if DEBUG:
                log(self.log_prefix + '_predownload: url', self.url, 'timeout', timeout)
            stream = urlOpenTimeout(self.url, timeout=timeout)
            content_type = stream.info().getheader('Content-Type')
            content_length = stream.info().getheader('Content-Length')
            if DEBUG:
                log(self.log_prefix + '_predownload: request finished: content_type', content_type, 'content_length', content_length)
            data = ''
            while True:
                if self.shutdown_flag:
                    if DEBUG:
                        log(self.log_prefix + '_predownload: got shutdown flag while reading: url', self.url)
                    break
                buf = stream.read(524288)
                if not buf:
                    if DEBUG:
                        log(self.log_prefix + '_predownload: eof: url', self.url)
                    break
                data += buf
                if DEBUG:
                    log(self.log_prefix + '_predownload: read chunk: url', self.url, 'read_len', len(data))

            stream.close()
            if not self.shutdown_flag:
                if DEBUG:
                    log(self.log_prefix + '_predownload: finished, run callback: url', self.url, 'content_type', content_type, 'content_length', content_length, 'data_len', len(data))
                callback(content_type, data)
        except Exception as e:
            if DEBUG:
                print_exc()
            self.failed_func(e)
        finally:
            self.running = False
            self.lock.release()

    def init(self, callback = None, timeout = 10):
        if callback is None:
            return self._init()
        t = Thread(target=self._init, args=[callback, timeout])
        t.setName('dd-downloader-init-' + t.getName())
        t.setDaemon(True)
        t.start()

    def _init(self, callback = None, timeout = 10):
        try:
            scheme, host, path = self.parse_url(self.url)
            redirects = 0
            connection = HTTPConnection(host)
            while True:
                connection.request('HEAD', path, None, {'Host': host,
                 'User-Agent': USER_AGENT})
                r = connection.getresponse()
                if r.status == 200:
                    break
                elif r.status == 301 or r.status == 302:
                    redirect_url = r.getheader('Location', None)
                    if DEBUG:
                        log(self.log_prefix + 'init: got redirect: url', self.url, 'redirect', redirect_url)
                    scheme, rhost, path = self.parse_url(redirect_url)
                    redirects += 1
                    if redirects > MAX_REDIRECTS:
                        raise Exception('Too much redirects')
                    if rhost != host:
                        connection.close()
                        connection = HTTPConnection(rhost)
                        host = rhost
                else:
                    raise Exception('Bad http status: ' + str(r.status))

            mime = r.getheader('Content-Type', None)
            length = r.getheader('Content-Length', None)
            connection.close()
            if length is None:
                raise Exception('No content-length in response')
            if mime is None:
                raise Exception('No content-type in response')
            length = int(length)
            self.final_url = scheme + '://' + host + path
            if DEBUG:
                log(self.log_prefix + 'init: got response: length', length, 'mime', mime, 'final_url', self.final_url)
            if callback is None:
                return (length, mime)
            callback(length, mime)
        except Exception as e:
            if DEBUG:
                print_exc()
            if callback is None:
                raise e
            else:
                self.failed_func(e)

    def set_storage(self, storage):
        self.storage = storage

    def start(self, pos = 0):
        if self.storage is None:
            raise Exception('Storage is not set')
        if self.final_url is None:
            raise Exception('Final url is not set')
        if self.lock.locked():
            self.seek = pos
            return
        t = Thread(target=self._request, args=[pos])
        t.setName('dd-downloader-' + t.getName())
        t.setDaemon(True)
        t.start()

    def _request(self, pos):
        self.lock.acquire()
        self.running = True
        try:
            while True:
                if self.shutdown_flag:
                    if DEBUG:
                        log(self.log_prefix + '_request: got shutdown flag before read: url', self.url)
                    break
                pos = self.storage.get_unfinished_pos(pos)
                if pos is None:
                    if DEBUG:
                        log(self.log_prefix + '_request: no unfinished pos, break: url', self.url)
                    break
                self._read(pos)
                if self.seek is not None:
                    pos = self.seek
                    self.seek = None
                    continue
                break

        except ReadErrorException:
            if DEBUG:
                log(self.log_prefix + '_request: read error, retry immediatelly: url', self.url, 'pos', pos)
            start_lambda = lambda : self.start(pos)
            self.rawserver.add_task(start_lambda, 0.1)
        except FatalErrorException as e:
            if DEBUG:
                log(self.log_prefix + '_request: fatal error, exit: url', self.url, 'pos', pos)
            self.failed_func(e)
        except Exception as e:
            self.errors += 1
            if DEBUG:
                print_exc()
            if self.errors > self.max_errors:
                if DEBUG:
                    log(self.log_prefix + '_request: non-fatal error, max errors reached: errors', self.errors, 'max', self.max_errors)
                self.failed_func(e)
            else:
                retry_in = 5 * (1 + self.errors / 10)
                if DEBUG:
                    log(self.log_prefix + '_request: non-fatal error: url', self.url, 'pos', pos, 'errors', self.errors, 'retry_in', retry_in)
                start_lambda = lambda : self.start(pos)
                self.rawserver.add_task(start_lambda, retry_in)
        finally:
            self.running = False
            self.lock.release()

    def is_running(self):
        return self.running

    def _read(self, pos):
        scheme, host, path = self.parse_url(self.final_url)
        request_range = str(pos) + '-'
        connection = HTTPConnection(host)
        connection.request('GET', path, None, {'Host': host,
         'User-Agent': USER_AGENT,
         'Range': 'bytes=%s' % request_range})
        r = connection.getresponse()
        if DEBUG:
            log(self.log_prefix + '_read: url', self.url, 'final', self.final_url, 'pos', pos, 'status', r.status)
        if r.status != 200 and r.status != 206:
            if DEBUG:
                log(self.log_prefix + '_read: bad http status: url', self.url, 'status', r.status)
            connection.close()
            if 400 <= r.status < 500:
                raise FatalErrorException, 'http status ' + str(r.status)
            else:
                raise NonFatalErrorException, 'http status ' + str(r.status)
        request_size = r.getheader('Content-Length', None)
        if request_size is None:
            if DEBUG:
                log(self.log_prefix + '_read: missing content length: url', self.url)
            connection.close()
            return
        try:
            request_size = int(request_size)
        except:
            if DEBUG:
                print_exc()
            connection.close()
            return

        if DEBUG:
            log(self.log_prefix + '_read: url', self.url, 'request_range', request_range, 'request_size', request_size)
        total_read = 0
        read_size = 16384
        while True:
            chunk = r.read(read_size)
            if not chunk:
                if total_read != request_size:
                    if DEBUG:
                        log(self.log_prefix + '_read: no data, raise read error: url', self.url, 'pos', pos, 'total_read', total_read, 'request_size', request_size)
                    raise ReadErrorException()
                if DEBUG:
                    log(self.log_prefix + '_read: no data, exit: url', self.url, 'pos', pos)
                break
            chunk_len = len(chunk)
            total_read += chunk_len
            if DEBUG:
                log('>>>> ' + self.log_prefix + '_read: got chunk: pos', pos, 'chunk_len', chunk_len, 'total_read', total_read)
            self.measure.update_rate(chunk_len)
            if chunk_len != read_size and total_read != request_size:
                if DEBUG:
                    log(self.log_prefix + '_read: bad data len, raise read error: url', self.url, 'pos', pos, 'total_read', total_read, 'request_size', request_size, 'chunk_len', chunk_len, 'read_size', read_size)
                raise ReadErrorException()
            if self.shutdown_flag:
                if DEBUG:
                    log(self.log_prefix + '_read: got shutdown flag on read: url', self.url)
                break
            try:
                t = time.time()
                updated_len = self.storage.write(pos, chunk)
                if DEBUG:
                    log('%%%%' + self.log_prefix + '_read: write to storage: pos', pos, 'len', chunk_len, 'time', time.time() - t)
                if updated_len == 0:
                    if DEBUG:
                        log(self.log_prefix + '_read: data exists in storage: url', self.url, 'pos', pos, 'len', chunk_len, 'seek_flag', self.seek)
                    if self.seek is None:
                        self.seek = self.storage.get_unfinished_pos(pos)
                        if self.seek is None:
                            if DEBUG:
                                log(self.log_prefix + '_read: no unfinished data, exit: url', self.url, 'pos', pos)
                            break
            except:
                if DEBUG:
                    print_exc()
                    log(self.log_prefix + '_read: cannot write, exit: url', self.url)
                raise FatalErrorException, 'cannot write to storage'

            if self.seek is not None:
                log(self.log_prefix + '_read: got seek: url', self.url, 'seek', self.seek)
                break
            pos += chunk_len

        connection.close()

    def parse_url(self, url):
        scheme, host, path, pars, query, fragment = urlparse(url)
        if scheme != 'http':
            raise ValueError('Unsupported scheme ' + scheme)
        if len(host) == 0:
            raise ValueError('Empty host')
        if len(path) == 0:
            path = '/'
        if len(pars) > 0:
            path += ';' + pars
        if len(query) > 0:
            path += '?' + query
        if len(fragment) > 0:
            path += '#' + fragment
        return (scheme, host, path)

    def shutdown(self):
        if DEBUG:
            log(self.log_prefix + 'shutdown: ---')
        self.shutdown_flag = True
