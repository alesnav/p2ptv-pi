#Embedded file name: ACEStream\Video\VideoServer.pyo
import sys
import time
import socket
import BaseHTTPServer
from SocketServer import ThreadingMixIn
from threading import RLock, Thread, currentThread
from traceback import print_stack, print_exc
import string
from cStringIO import StringIO
import os
from ACEStream.GlobalConfig import globalConfig
import ACEStream.Core.osutils
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False
DEBUGCONTENT = False
DEBUGWEBUI = False
DEBUGLOCK = False
DEBUGBASESERV = False

class ConnectionResetError(Exception):
    pass


def bytestr2int(b):
    if b == '':
        return None
    else:
        return int(b)


class AbstractPathMapper():

    def __init__(self):
        pass

    def get(self, path):
        msg = 'AbstractPathMapper: Unknown path ' + path
        stream = StringIO(msg)
        streaminfo = {'mimetype': 'text/plain',
         'stream': stream,
         'length': len(msg)}
        return streaminfo


class VideoHTTPServer(ThreadingMixIn, BaseHTTPServer.HTTPServer):
    __single = None

    def __init__(self, port):
        if VideoHTTPServer.__single:
            raise RuntimeError, 'HTTPServer is Singleton'
        VideoHTTPServer.__single = self
        self.port = port
        if globalConfig.get_value('allow-non-local-client-connection'):
            bind_address = ''
        else:
            bind_address = '127.0.0.1'
        BaseHTTPServer.HTTPServer.__init__(self, (bind_address, self.port), SimpleServer)
        self.daemon_threads = True
        self.allow_reuse_address = True
        self.lock = RLock()
        self.urlpath2streaminfo = {}
        self.mappers = []
        self.errorcallback = None
        self.statuscallback = None
        self.ic = None
        self.load_torr = None
        self.url_is_set = 0

    def getInstance(*args, **kw):
        if VideoHTTPServer.__single is None:
            VideoHTTPServer(*args, **kw)
        return VideoHTTPServer.__single

    getInstance = staticmethod(getInstance)

    def background_serve(self):
        name = 'VideoHTTPServerThread-1'
        self.thread2 = Thread(target=self.serve_forever, name=name)
        self.thread2.setDaemon(True)
        self.thread2.start()

    def register(self, errorcallback, statuscallback, load_torr):
        self.errorcallback = errorcallback
        self.statuscallback = statuscallback
        self.load_torr = load_torr
 
    def set_inputstream(self, streaminfo, urlpath):
        self.lock.acquire()
        if DEBUGLOCK:
            log('videoserver::set_inputstream: urlpath', urlpath, 'streaminfo', streaminfo, 'thread', currentThread().getName())
        if self.urlpath2streaminfo.has_key(urlpath):
            if DEBUGLOCK:
                log('videoserver::set_inputstream: path exists, delete old: urlpath', urlpath, 'thread', currentThread().getName())
            self.del_inputstream(urlpath)
        streaminfo['lock'] = RLock()
        self.urlpath2streaminfo[urlpath] = streaminfo
        self.lock.release()
        self.url_is_set = urlpath

    def acquire_inputstream(self, urlpath):
        global DEBUG
        if urlpath is None:
            return
        streaminfo = None
        for mapper in self.mappers:
            streaminfo = mapper.get(urlpath)
            if streaminfo is not None and (streaminfo['statuscode'] == 200 or streaminfo['statuscode'] == 301):
                return streaminfo

        self.lock.acquire()
        if DEBUGLOCK:
            log('VideoServer::acquire_inputstream: lock done', urlpath, currentThread().getName())
        try:
            streaminfo = self.urlpath2streaminfo.get(urlpath, None)
            if DEBUG:
                log('videoserver::acquire_inputstream: got streaminfo: urlpath', urlpath, 'streaminfo', streaminfo)
        finally:
            if DEBUGLOCK:
                log('VideoServer::acquire_inputstream: unlock', urlpath, currentThread().getName())
            self.lock.release()

        if streaminfo is not None and 'lock' in streaminfo:
            if DEBUGLOCK:
                log('VideoServer::acquire_inputstream: lock stream: urlpath', urlpath, 'streaminfo', streaminfo, 'thread', currentThread().getName())
            streaminfo['lock'].acquire()
            if DEBUGLOCK:
                log('VideoServer::acquire_inputstream: lock stream done: urlpath', urlpath, 'thread', currentThread().getName())
        return streaminfo

    def release_inputstream(self, urlpath):
        if DEBUGLOCK:
            log('VideoServer::release_inputstream: lock', urlpath, currentThread().getName())
        self.lock.acquire()
        try:
            streaminfo = self.urlpath2streaminfo.get(urlpath, None)
        finally:
            if DEBUGLOCK:
                log('VideoServer::release_inputstream: unlock', urlpath, currentThread().getName())
            self.lock.release()

        if streaminfo is not None and 'lock' in streaminfo:
            if DEBUGLOCK:
                log('VideoServer::release_inputstream: unlock stream: urlpath', urlpath, 'streaminfo', streaminfo, 'thread', currentThread().getName())
            streaminfo['lock'].release()

    def del_inputstream(self, urlpath):
        if DEBUGLOCK:
            log('VideoServer::del_inputstream: enter', urlpath)
        streaminfo = self.acquire_inputstream(urlpath)
        self.lock.acquire()
        if DEBUGLOCK:
            log('VideoServer::del_inputstream: lock', urlpath, currentThread().getName())
        try:
            del self.urlpath2streaminfo[urlpath]
        except KeyError:
            if DEBUGLOCK:
                log('videoserver::del_inputstream: path not found: urlpath', urlpath)
        finally:
            if DEBUGLOCK:
                log('VideoServer::del_inputstream: unlock', urlpath, currentThread().getName())
            self.lock.release()

        if streaminfo is not None and 'lock' in streaminfo:
            if DEBUGLOCK:
                log('VideoServer::del_inputstream: stream: unlock', urlpath, currentThread().getName())
            streaminfo['lock'].release()

    def get_port(self):
        return self.port

    def add_path_mapper(self, mapper):
        self.mappers.append(mapper)

    def shutdown(self):
        if DEBUG:
            print >> sys.stderr, 'videoserv: Shutting down HTTP'
        self.socket.close()

    def handle_error(self, request, client_address):
        if DEBUGBASESERV:
            print >> sys.stderr, 'VideoHTTPServer: handle_error', request, client_address
            log_exc()


class SimpleServer(BaseHTTPServer.BaseHTTPRequestHandler):
    RANGE_REQUESTS_ENABLED = True

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        global DEBUG
        try:
          if self.path.startswith('/LOAD'):
             content_id = self.path.split("=")[1]
             content_type = self.path.split("=")[0].split('/')[2]
             self.server.load_torr(content_type, content_id)
             t = 0
             while not self.server.url_is_set and t < 30:
               t+=1
               time.sleep(1)
             if DEBUG:
                log('videoserv: do_GET: Got request', self.path, self.headers.getheader('range'), currentThread().getName())
             nbytes2send = None
             nbyteswritten = 0
             try:
                 streaminfo = self.server.acquire_inputstream(self.server.url_is_set)
             except:
                 streaminfo = None

             if self.request_version == 'HTTP/1.1':
                self.protocol_version = 'HTTP/1.1'
             try:
                if streaminfo is None or 'statuscode' in streaminfo and streaminfo['statuscode'] != 200:
                    if streaminfo is None:
                        streaminfo = {'statuscode': 500,
                         'statusmsg': "Internal Server Error, couldn't find resource"}
                    if DEBUG:
                        log('videoserv: do_GET: Cannot serve request', streaminfo['statuscode'], currentThread().getName())
                    if streaminfo['statuscode'] == 301:
                        self.send_header('Location', streaminfo['statusmsg'])
                        self.end_headers()
                    else:
                        self.send_header('Content-Type', 'text/plain')
                        self.send_header('Content-Length', len(streaminfo['statusmsg']))
                        self.end_headers()
                        self.wfile.write(streaminfo['statusmsg'])
                    return
                mimetype = streaminfo['mimetype']
                stream = streaminfo['stream']
                length = streaminfo['length']
                if 'blocksize' in streaminfo:
                    blocksize = streaminfo['blocksize']
                else:
                    blocksize = 65536
                if 'svc' in streaminfo:
                    svc = streaminfo['svc']
                else:
                    svc = False
                if DEBUG:
                    log('videoserv: do_GET: MIME type is', mimetype, 'length', length, 'blocksize', blocksize, currentThread().getName())
                firstbyte = 0
                if length is not None:
                    lastbyte = length - 1
                else:
                    lastbyte = None
                range = self.headers.getheader('range')
                if self.RANGE_REQUESTS_ENABLED and length and range:
                    bad = False
                    type, seek = string.split(range, '=')
                    if seek.find(',') != -1:
                        bad = True
                    else:
                        firstbytestr, lastbytestr = string.split(seek, '-')
                        firstbyte = bytestr2int(firstbytestr)
                        lastbyte = bytestr2int(lastbytestr)
                        if length is None:
                            bad = True
                        elif firstbyte is None and lastbyte is None:
                            bad = True
                        elif firstbyte >= length:
                            bad = True
                        elif lastbyte >= length:
                            if firstbyte is None:
                                lastbyte = length - 1
                            else:
                                bad = True
                    if bad:
                        self.send_response(416)
                        if length is None:
                            crheader = 'bytes */*'
                        else:
                            crheader = 'bytes */' + str(length)
                        self.send_header('Content-Range', crheader)
                        self.end_headers()
                        return
                    if firstbyte is not None and lastbyte is None:
                        nbytes2send = length - firstbyte
                        lastbyte = length - 1
                    elif firstbyte is None and lastbyte is not None:
                        nbytes2send = lastbyte
                        firstbyte = length - lastbyte
                        lastbyte = length - 1
                    else:
                        nbytes2send = lastbyte + 1 - firstbyte
                    crheader = 'bytes ' + str(firstbyte) + '-' + str(lastbyte) + '/' + str(length)
                    if DEBUG:
                        log('VideoServer::do_Get: send response 206,', crheader)
                    self.send_response(206)
                    self.send_header('Content-Range', crheader)
                else:
                    nbytes2send = length
                    self.send_response(200)
                if DEBUG:
                    log('videoserv: do_GET: final range', firstbyte, lastbyte, nbytes2send, currentThread().getName())
                if not svc:
                    try:
                        stream.seek(firstbyte)
                    except:
                        log_exc()

                if self.request_version == 'HTTP/1.1':
                    self.send_header('Connection', 'Keep-Alive')
                    self.send_header('Keep-Alive', 'timeout=15, max=100')
                self.send_header('Content-Type', mimetype)
                self.send_header('Accept-Ranges', 'bytes')
                try:
                    if streaminfo.has_key('bitrate') and streaminfo['bitrate'] is not None and length is not None:
                        bitrate = streaminfo['bitrate']
                        estduration = float(length) / float(bitrate)
                        self.send_header('X-Content-Duration', estduration)
                except:
                    log_exc()

                if length is not None:
                    self.send_header('Content-Length', nbytes2send)
                else:
                    self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                if svc:
                    data = stream.read()
                    if len(data) > 0:
                        self.wfile.write(data)
                    elif len(data) == 0:
                        if DEBUG:
                            log('videoserv: svc: stream.read() no data')
                else:
                    done = False
                    while True:
                        tt = time.time()
                        data = stream.read(blocksize)
                        data_len = len(data)
                        if data_len == 0:
                            done = True
                        tt = time.time() - tt
                        if DEBUG:
                            log('videoserver::get: read done: blocksize', blocksize, 'length', length, 'len(data)', data_len, 'time', tt, 'thread', currentThread().getName())
                        if length is None:
                            self.wfile.write('%x\r\n' % data_len)
                        if data_len > 0:
                            tt = time.time()
                            if length is not None and nbyteswritten + data_len > nbytes2send:
                                endlen = nbytes2send - nbyteswritten
                                if endlen != 0:
                                    self.wfile.write(data[:endlen])
                                done = True
                                nbyteswritten += endlen
                            else:
                                try:
                                    playback_started = stream.stream.mt.playback_started
                                    bitrate = stream.stream.mt.videostatus.bitrate
                                except:
                                    playback_started = False
                                    bitrate = None

                                if bitrate is None:
                                    try:
                                        self.wfile.write(data)
                                    except:
                                        raise ConnectionResetError()

                                else:
                                    delay = 0.01
                                    speed = bitrate * 8
                                    chunk_size = bitrate
                                    pos = 0
                                    while pos < data_len:
                                        chunk = data[pos:pos + chunk_size]
                                        try:
                                            self.wfile.write(chunk)
                                        except:
                                            raise ConnectionResetError()

                                        if DEBUG:
                                            log('videoserver::get: write chunk: pos', pos, 'chunk_size', chunk_size, 'delay', delay, 'speed', speed, 'thread', currentThread().getName())
                                        pos += chunk_size

                                nbyteswritten += data_len
                            if DEBUG:
                                log('videoserver::get: write done: nbyteswritten', nbyteswritten, 'time', time.time() - tt, 'thread', currentThread().getName())
                        if length is None:
                            self.wfile.write('\r\n')
                        if done:
                            if DEBUG:
                                log('videoserver::get: stream reached EOF: thread', currentThread().getName())
                            break

                    if DEBUG and nbyteswritten != nbytes2send:
                        log('videoserver::get: sent wrong amount: wanted', nbytes2send, 'got', nbyteswritten, 'thread', currentThread().getName())
                    if not range:
                        stream.close()
                        if self.server.statuscallback is not None:
                            self.server.statuscallback('Done')
             except ConnectionResetError:
                if DEBUG:
                    log('videoserver::get: connection reset')

             except:
                log_exc()
             finally:
	        self.server.release_inputstream(self.server.url_is_set)
		self.server.ic.stop()
		self.server.ic.shutdown()

	  else:
            if self.path.startswith('/webUI'):
                DEBUG = DEBUGWEBUI
            else:
                DEBUG = DEBUGCONTENT
            if DEBUG:
                log('videoserv: do_GET: Got request', self.path, self.headers.getheader('range'), currentThread().getName())
            nbytes2send = None
            nbyteswritten = 0
            try:
                streaminfo = self.server.acquire_inputstream(self.path)
            except:
                streaminfo = None

            if self.request_version == 'HTTP/1.1':
                self.protocol_version = 'HTTP/1.1'
            try:
                if streaminfo is None or 'statuscode' in streaminfo and streaminfo['statuscode'] != 200:
                    if streaminfo is None:
                        streaminfo = {'statuscode': 500,
                         'statusmsg': "Internal Server Error, couldn't find resource"}
                    if DEBUG:
                        log('videoserv: do_GET: Cannot serve request', streaminfo['statuscode'], currentThread().getName())
                    self.send_response(streaminfo['statuscode'])
                    if streaminfo['statuscode'] == 301:
                        self.send_header('Location', streaminfo['statusmsg'])
                        self.end_headers()
                    else:
                        self.send_header('Content-Type', 'text/plain')
                        self.send_header('Content-Length', len(streaminfo['statusmsg']))
                        self.end_headers()
                        self.wfile.write(streaminfo['statusmsg'])
                    return
                mimetype = streaminfo['mimetype']
                stream = streaminfo['stream']
                length = streaminfo['length']
                if 'blocksize' in streaminfo:
                    blocksize = streaminfo['blocksize']
                else:
                    blocksize = 65536
                if 'svc' in streaminfo:
                    svc = streaminfo['svc']
                else:
                    svc = False
                if DEBUG:
                    log('videoserv: do_GET: MIME type is', mimetype, 'length', length, 'blocksize', blocksize, currentThread().getName())
                firstbyte = 0
                if length is not None:
                    lastbyte = length - 1
                else:
                    lastbyte = None
                range = self.headers.getheader('range')
                if self.RANGE_REQUESTS_ENABLED and length and range:
                    bad = False
                    type, seek = string.split(range, '=')
                    if seek.find(',') != -1:
                        bad = True
                    else:
                        firstbytestr, lastbytestr = string.split(seek, '-')
                        firstbyte = bytestr2int(firstbytestr)
                        lastbyte = bytestr2int(lastbytestr)
                        if length is None:
                            bad = True
                        elif firstbyte is None and lastbyte is None:
                            bad = True
                        elif firstbyte >= length:
                            bad = True
                        elif lastbyte >= length:
                            if firstbyte is None:
                                lastbyte = length - 1
                            else:
                                bad = True
                    if bad:
                        self.send_response(416)
                        if length is None:
                            crheader = 'bytes */*'
                        else:
                            crheader = 'bytes */' + str(length)
                        self.send_header('Content-Range', crheader)
                        self.end_headers()
                        return
                    if firstbyte is not None and lastbyte is None:
                        nbytes2send = length - firstbyte
                        lastbyte = length - 1
                    elif firstbyte is None and lastbyte is not None:
                        nbytes2send = lastbyte
                        firstbyte = length - lastbyte
                        lastbyte = length - 1
                    else:
                        nbytes2send = lastbyte + 1 - firstbyte
                    crheader = 'bytes ' + str(firstbyte) + '-' + str(lastbyte) + '/' + str(length)
                    if DEBUG:
                        log('VideoServer::do_Get: send response 206,', crheader)
                    self.send_response(206)
                    self.send_header('Content-Range', crheader)
                else:
                    nbytes2send = length
                    self.send_response(200)
                if DEBUG:
                    log('videoserv: do_GET: final range', firstbyte, lastbyte, nbytes2send, currentThread().getName())
                if not svc:
                    try:
                        stream.seek(firstbyte)
                    except:
                        log_exc()

                if self.request_version == 'HTTP/1.1':
                    self.send_header('Connection', 'Keep-Alive')
                    self.send_header('Keep-Alive', 'timeout=15, max=100')
                self.send_header('Content-Type', mimetype)
                self.send_header('Accept-Ranges', 'bytes')
                try:
                    if streaminfo.has_key('bitrate') and streaminfo['bitrate'] is not None and length is not None:
                        bitrate = streaminfo['bitrate']
                        estduration = float(length) / float(bitrate)
                        self.send_header('X-Content-Duration', estduration)
                except:
                    log_exc()

                if length is not None:
                    self.send_header('Content-Length', nbytes2send)
                else:
                    self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                if svc:
                    data = stream.read()
                    if len(data) > 0:
                        self.wfile.write(data)
                    elif len(data) == 0:
                        if DEBUG:
                            log('videoserv: svc: stream.read() no data')
                else:
                    done = False
                    while True:
                        tt = time.time()
                        data = stream.read(blocksize)
                        data_len = len(data)
                        if data_len == 0:
                            done = True
                        tt = time.time() - tt
                        if DEBUG:
                            log('videoserver::get: read done: blocksize', blocksize, 'length', length, 'len(data)', data_len, 'time', tt, 'thread', currentThread().getName())
                        if length is None:
                            self.wfile.write('%x\r\n' % data_len)
                        if data_len > 0:
                            tt = time.time()
                            if length is not None and nbyteswritten + data_len > nbytes2send:
                                endlen = nbytes2send - nbyteswritten
                                if endlen != 0:
                                    self.wfile.write(data[:endlen])
                                done = True
                                nbyteswritten += endlen
                            else:
                                try:
                                    playback_started = stream.stream.mt.playback_started
                                    bitrate = stream.stream.mt.videostatus.bitrate
                                except:
                                    playback_started = False
                                    bitrate = None

                                if bitrate is None:
                                    try:
                                        self.wfile.write(data)
                                    except:
                                        raise ConnectionResetError()

                                else:
                                    delay = 0.01
                                    speed = bitrate * 8
                                    chunk_size = bitrate
                                    pos = 0
                                    while pos < data_len:
                                        chunk = data[pos:pos + chunk_size]
                                        try:
                                            self.wfile.write(chunk)
                                        except:
                                            raise ConnectionResetError()

                                        if DEBUG:
                                            log('videoserver::get: write chunk: pos', pos, 'chunk_size', chunk_size, 'delay', delay, 'speed', speed, 'thread', currentThread().getName())
                                        pos += chunk_size

                                nbyteswritten += data_len
                            if DEBUG:
                                log('videoserver::get: write done: nbyteswritten', nbyteswritten, 'time', time.time() - tt, 'thread', currentThread().getName())
                        if length is None:
                            self.wfile.write('\r\n')
                        if done:
                            if DEBUG:
                                log('videoserver::get: stream reached EOF: thread', currentThread().getName())
                            break

                    if DEBUG and nbyteswritten != nbytes2send:
                        log('videoserver::get: sent wrong amount: wanted', nbytes2send, 'got', nbyteswritten, 'thread', currentThread().getName())
                    if not range:
                        stream.close()
                        if self.server.statuscallback is not None:
                            self.server.statuscallback('Done')
            except ConnectionResetError:
                if DEBUG:
                    log('videoserver::get: connection reset')
            except:
                log_exc()
            finally:
                self.server.release_inputstream(self.path)

        except socket.error as e2:
            if DEBUG:
                log('videoserv: SocketError occured while serving', currentThread().getName())
                log_exc()
        except Exception as e:
            if DEBUG:
                log('videoserv: Error occured while serving', currentThread().getName())
            log_exc()
            self.error(e, self.path)

    def error(self, e, url):
        if self.server.errorcallback is not None:
            self.server.errorcallback(e, url)
        else:
            log_exc()
        if self.server.statuscallback is not None:
            self.server.statuscallback('Error playing video:' + str(e))


class VideoRawVLCServer():
    __single = None

    def __init__(self):
        if VideoRawVLCServer.__single:
            raise RuntimeError, 'VideoRawVLCServer is Singleton'
        VideoRawVLCServer.__single = self
        self.lock = RLock()
        self.oldsid = None
        self.sid2streaminfo = {}

    def getInstance(*args, **kw):
        if VideoRawVLCServer.__single is None:
            VideoRawVLCServer(*args, **kw)
        return VideoRawVLCServer.__single

    getInstance = staticmethod(getInstance)

    def set_inputstream(self, streaminfo, sid):
        self.lock.acquire()
        try:
            print >> sys.stderr, 'VLCRawServer: setting sid', sid
            self.sid2streaminfo[sid] = streaminfo
        finally:
            self.lock.release()

    def get_inputstream(self, sid):
        self.lock.acquire()
        try:
            return self.sid2streaminfo[sid]
        finally:
            self.lock.release()

    def shutdown(self):
        pass

    def ReadDataCallback(self, bufc, buflen, sid):
        try:
            if self.oldsid is not None and self.oldsid != sid:
                oldstream = self.sid2streaminfo[self.oldsid]['stream']
                del self.sid2streaminfo[self.oldsid]
                try:
                    oldstream.close()
                except:
                    log_exc()

            self.oldsid = sid
            streaminfo = self.get_inputstream(sid)
            data = streaminfo['stream'].read(buflen)
            size = len(data)
            if size == 0:
                return 0
            bufc[0:size] = data
            return size
        except:
            log_exc()
            return -1

    def SeekDataCallback(self, pos, sid):
        try:
            if True:
                streaminfo = self.get_inputstream(sid)
                streaminfo['stream'].seek(pos, os.SEEK_SET)
                return 0
            return -1
        except:
            log_exc()
            return -1


class MultiHTTPServer(ThreadingMixIn, VideoHTTPServer):
    __single = None

    def __init__(self, port):
        if MultiHTTPServer.__single:
            raise RuntimeError, 'MultiHTTPServer is Singleton'
        MultiHTTPServer.__single = self
        self.port = port
        BaseHTTPServer.HTTPServer.__init__(self, ('127.0.0.1', self.port), SimpleServer)
        self.daemon_threads = True
        self.allow_reuse_address = True
        self.lock = RLock()
        self.urlpath2streaminfo = {}
        self.mappers = []
        self.errorcallback = None
        self.statuscallback = None

    def background_serve(self):
        name = 'MultiHTTPServerThread-1'
        self.thread2 = Thread(target=self.serve_forever, name=name)
        self.thread2.setDaemon(True)
        self.thread2.start()
