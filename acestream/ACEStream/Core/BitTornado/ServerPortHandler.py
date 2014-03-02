#Embedded file name: ACEStream\Core\BitTornado\ServerPortHandler.pyo
import sys
from cStringIO import StringIO
from binascii import b2a_hex
try:
    True
except:
    True = 1
    False = 0

from BT1.Encrypter import protocol_name
from ACEStream.Core.Utilities.logger import log, log_exc

def toint(s):
    return long(b2a_hex(s), 16)


default_task_id = []
DEBUG = False
DEBUG2 = False

def show(s):
    for i in xrange(len(s)):
        print ord(s[i]),

    print


class SingleRawServer:

    def __init__(self, info_hash, multihandler, doneflag, protocol):
        self.info_hash = info_hash
        self.doneflag = doneflag
        self.protocol = protocol
        self.multihandler = multihandler
        self.rawserver = multihandler.rawserver
        self.finished = False
        self.running = False
        self.handler = None
        self.taskqueue = []
        if DEBUG:
            log('SingleRawServer::__init__: info_hash', info_hash, 'protocol', protocol)

    def shutdown(self):
        if DEBUG:
            log('SingleRawServer::shutdown: info_hash', self.info_hash, 'finished', self.finished)
        if not self.finished:
            self.multihandler.shutdown_torrent(self.info_hash)

    def _shutdown(self):
        if DEBUG:
            log('SingleRawServer:_shutdown: finished', self.finished, 'handler', self.handler)
        if not self.finished:
            self.finished = True
            self.running = False
            self.rawserver.kill_tasks(self.info_hash)
            if self.handler:
                self.handler.close_all()

    def _external_connection_made(self, c, options, msg_remainder):
        if DEBUG2:
            log('SingleRawServer::_external_connection_made: running', self.running, 'options', options, 'msg_remainder', msg_remainder, 'c', c)
        if self.running:
            c.set_handler(self.handler)
            self.handler.externally_handshaked_connection_made(c, options, msg_remainder)

    def add_task(self, func, delay = 0, id = default_task_id):
        if id is default_task_id:
            id = self.info_hash
        if not self.finished:
            self.rawserver.add_task(func, delay, id)

    def start_connection(self, dns, handler = None):
        if DEBUG2:
            log('SingleRawServer::start_connection: dns', dns, 'handler', handler, 'self.handler', self.handler)
        if not handler:
            handler = self.handler
        c = self.rawserver.start_connection(dns, handler)
        return c

    def start_listening(self, handler):
        if DEBUG:
            log('SingleRawServer::start_listening: handler', handler, 'running', self.running)
        self.handler = handler
        self.running = True
        return self.shutdown

    def is_finished(self):
        return self.finished

    def get_exception_flag(self):
        return self.rawserver.get_exception_flag()


class NewSocketHandler:

    def __init__(self, multihandler, connection):
        self.multihandler = multihandler
        self.connection = connection
        connection.set_handler(self)
        self.closed = False
        self.buffer = StringIO()
        self.complete = False
        self.next_len, self.next_func = 1, self.read_header_len
        self.multihandler.rawserver.add_task(self._auto_close, 15)
        if DEBUG:
            log('NewSocketHandler::__init__: ip', self.connection.get_ip(), 'port', self.connection.get_port())

    def _auto_close(self):
        if DEBUG2:
            log('NewSocketHandler::_auto_close: complete', self.complete, 'ip', self.connection.get_ip(), 'port', self.connection.get_port())
        if not self.complete:
            self.close()

    def close(self):
        if DEBUG2:
            log('NewSocketHandler::close: complete', self.complete, 'ip', self.connection.get_ip(), 'port', self.connection.get_port())
        if not self.closed:
            self.connection.close()
            self.closed = True

    def read_header_len(self, s):
        if s == 'G':
            self.protocol = 'HTTP'
            self.firstbyte = s
            if DEBUG2:
                log('NewSocketHandler::read_header_len: got http connection: protocol', self.protocol, 'firstbyte', self.firstbyte)
            return True
        else:
            l = ord(s)
            if DEBUG2:
                log('NewSocketHandler::read_header_len: len', l, 'next read_header()')
            return (l, self.read_header)

    def read_header(self, s):
        self.protocol = s
        if DEBUG2:
            log('NewSocketHandler::read_header: protocol', self.protocol, 'next read_reserved()')
        return (8, self.read_reserved)

    def read_reserved(self, s):
        self.options = s
        if DEBUG2:
            log('NewSocketHandler::read_reserved: options', self.options, 'next read_download_id()')
        return (20, self.read_download_id)

    def read_download_id(self, s):
        if DEBUG2:
            log('NewSocketHandler:read_download_id: s', s, 'peername', self.connection.socket.getpeername())
        if self.multihandler.singlerawservers.has_key(s):
            if self.multihandler.singlerawservers[s].protocol == self.protocol:
                if DEBUG2:
                    log('NewSocketHandler::read_download_id: found rawserver for this id: s', s)
                return True
        if DEBUG2:
            log('NewSocketHandler::read_download_id: no rawserver found this id: s', s)

    def read_dead(self, s):
        return None

    def data_came_in(self, garbage, s):
        if DEBUG2:
            log('NewSocketHandler::data_came_in: data', s)
        while 1:
            if self.closed:
                if DEBUG2:
                    log('NewSocketHandler::data_came_in: closed, exit loop')
                return
            buf_len = self.buffer.tell()
            data_len = len(s)
            i = self.next_len - buf_len
            if DEBUG2:
                log('NewSocketHandler::data_came_in: data_len', data_len, 'buf_len', buf_len, 'next_len', self.next_len, 'i', i)
            if i > data_len:
                if DEBUG2:
                    log('NewSocketHandler::data_came_in: write to buffer and break')
                self.buffer.write(s)
                return
            self.buffer.write(s[:i])
            s = s[i:]
            m = self.buffer.getvalue()
            self.buffer.reset()
            self.buffer.truncate()
            if DEBUG2:
                log('NewSocketHandler::data_came_in: process data:', m)
            try:
                x = self.next_func(m)
            except:
                self.next_len, self.next_func = 1, self.read_dead
                raise

            if x is None:
                if DEBUG2:
                    log('NewSocketHandler::data_came_in: func', self.next_func, 'returned None, close and break')
                self.close()
                return
            if x == True:
                if self.protocol == 'HTTP':
                    if DEBUG2:
                        log('NewSocketHandler::data_came_in: got http connection')
                    self.multihandler.httphandler.external_connection_made(self.connection)
                    self.multihandler.httphandler.data_came_in(self.connection, self.firstbyte)
                    self.multihandler.httphandler.data_came_in(self.connection, s)
                else:
                    if DEBUG2:
                        log('NewSocketHandler::data_came_in: non-http connection: m', m)
                    self.multihandler.singlerawservers[m]._external_connection_made(self.connection, self.options, s)
                self.complete = True
                return
            self.next_len, self.next_func = x
            if DEBUG2:
                log('NewSocketHandler::data_came_in: continue: next_len', self.next_len, 'next_func', self.next_func)

    def connection_flushed(self, ss):
        if DEBUG2:
            log('NewSocketHandler::connection_flushed: no-op: ss', ss)

    def connection_lost(self, ss):
        if DEBUG2:
            log('NewSocketHandler::connection_lost: ss', ss)
        self.closed = True


class MultiHandler:

    def __init__(self, rawserver, doneflag):
        self.rawserver = rawserver
        self.masterdoneflag = doneflag
        self.singlerawservers = {}
        self.connections = {}
        self.taskqueues = {}
        self.httphandler = None

    def newRawServer(self, info_hash, doneflag, protocol = protocol_name):
        new = SingleRawServer(info_hash, self, doneflag, protocol)
        self.singlerawservers[info_hash] = new
        if DEBUG:
            log('multihandler::newRawServer: infohash', info_hash, 'protocol', protocol, 'count_single_servers', len(self.singlerawservers))
        return new

    def shutdown_torrent(self, info_hash):
        try:
            self.singlerawservers[info_hash]._shutdown()
            del self.singlerawservers[info_hash]
            if DEBUG:
                log('multihandler::shutdown_torrent: infohash', info_hash, 'count_single_servers', len(self.singlerawservers))
        except:
            if DEBUG:
                log('multihandler::shutdown_torrent: got error: infohash', info_hash)
                print_exc()
            raise

    def listen_forever(self):
        if DEBUG:
            log('multihandler::listen_forever: --')
        self.rawserver.listen_forever(self)
        for srs in self.singlerawservers.values():
            srs.finished = True
            srs.running = False
            srs.doneflag.set()

    def set_httphandler(self, httphandler):
        self.httphandler = httphandler

    def external_connection_made(self, ss):
        if DEBUG2:
            log('multihandler::external_connection_made: create NewSocketHandler: ss', ss, 'count_single_servers', len(self.singlerawservers), 'count_connections', len(self.connections))
        NewSocketHandler(self, ss)
