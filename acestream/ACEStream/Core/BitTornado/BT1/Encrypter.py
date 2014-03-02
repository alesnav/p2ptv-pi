#Embedded file name: ACEStream\Core\BitTornado\BT1\Encrypter.pyo
import sys
from base64 import b64encode
from cStringIO import StringIO
from binascii import b2a_hex
from socket import error as socketerror
from urllib import quote
from struct import unpack
from time import time
from traceback import print_stack
from ACEStream.Core.BitTornado.BT1.MessageID import protocol_name, option_pattern
from ACEStream.Core.BitTornado.BT1.convert import toint
from ACEStream.Core.ProxyService.ProxyServiceUtil import *
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.GlobalConfig import globalConfig
try:
    True
except:
    True = 1
    False = 0

DEBUG = False
DEBUG_CLOSE = False
DEBUG_SKIP_SOURCE_CONNECTION = False
if sys.platform == 'win32':
    winvertuple = sys.getwindowsversion()
    spstr = winvertuple[4]
    if winvertuple[0] == 5 or winvertuple[0] == 6 and winvertuple[1] == 0 and spstr < 'Service Pack 2':
        MAX_INCOMPLETE = 8
    else:
        MAX_INCOMPLETE = 1024
else:
    MAX_INCOMPLETE = 32
AUTOCLOSE_TIMEOUT = 55

def make_readable(s):
    if not s:
        return ''
    if quote(s).find('%') >= 0:
        return b2a_hex(s).upper()
    return '"' + s + '"'


def show(s):
    return b2a_hex(s)


class IncompleteCounter():

    def __init__(self):
        self.c = 0

    def increment(self):
        self.c += 1

    def decrement(self):
        self.c -= 1

    def toomany(self):
        return self.c >= MAX_INCOMPLETE


incompletecounter = IncompleteCounter()

class Connection():

    def __init__(self, Encoder, connection, id, ext_handshake = False, locally_initiated = None, dns = None, coord_con = False, proxy_con = False, challenge = None, proxy_permid = None):
        self.Encoder = Encoder
        self.connection = connection
        self.connecter = Encoder.connecter
        self.id = id
        self.readable_id = make_readable(id)
        self.coord_con = coord_con
        self.proxy_con = proxy_con
        self.proxy_permid = proxy_permid
        self.challenge = challenge
        if locally_initiated is not None:
            self.locally_initiated = locally_initiated
        elif coord_con:
            self.locally_initiated = True
        elif proxy_con:
            self.locally_initiated = True
        else:
            self.locally_initiated = id != None
        self.complete = False
        self.keepalive = lambda : None
        self.closed = False
        self.buffer = StringIO()
        self.dns = dns
        self.support_extend_messages = False
        self.connecter_conn = None
        self.support_merklehash = False
        self.na_want_internal_conn_from = None
        self.na_address_distance = None
        if self.locally_initiated:
            incompletecounter.increment()
        self.create_time = time()
        if self.locally_initiated or ext_handshake:
            if DEBUG:
                log('Encoder.Connection::__init__: writing protname + options + infohash')
            self.connection.write(chr(len(protocol_name)) + protocol_name + option_pattern + self.Encoder.download_id)
        if ext_handshake:
            if DEBUG:
                log('Encoder.Connection::__init__: writing my peer-ID')
            if coord_con:
                if DEBUG:
                    log('Encoder.Connection::__init__: i am a doe, using challenge', self.challenge)
                proxy_peer_id = encode_challenge_in_peerid(self.Encoder.my_id, self.challenge)
                self.connection.write(proxy_peer_id)
            else:
                self.connection.write(self.Encoder.my_id)
            if DEBUG:
                log('Encoder.Connection::__init__: next func = read_peer_id: ip', self.get_ip(), 'port', self.get_port())
            self.next_len, self.next_func = 20, self.read_peer_id
        else:
            if DEBUG:
                log('Encoder.Connection::__init__: next func = read_header_len: ip', self.get_ip(), 'port', self.get_port())
            self.next_len, self.next_func = 1, self.read_header_len
        self.Encoder.raw_server.add_task(self._auto_close, AUTOCLOSE_TIMEOUT)

    def get_ip(self, real = False):
        return self.connection.get_ip(real)

    def get_port(self, real = False):
        return self.connection.get_port(real)

    def get_myip(self, real = False):
        return self.connection.get_myip(real)

    def get_myport(self, real = False):
        return self.connection.get_myport(real)

    def get_id(self):
        return self.id

    def get_proxy_permid(self):
        return self.proxy_permid

    def get_readable_id(self):
        return self.readable_id

    def is_locally_initiated(self):
        return self.locally_initiated

    def is_flushed(self):
        return self.connection.is_flushed()

    def supports_merklehash(self):
        return self.support_merklehash

    def supports_extend_messages(self):
        return self.support_extend_messages

    def set_options(self, s):
        r = unpack('B', s[5])
        if r[0] & 16:
            self.support_extend_messages = True
            if DEBUG:
                log('encoder::set_options: Peer supports EXTEND')
        if r[0] & 32:
            self.support_merklehash = True
            if DEBUG:
                log('encoder::set_options: Peer supports Merkle hashes')

    def read_header_len(self, s):
        if ord(s) != len(protocol_name):
            if DEBUG:
                log('Encoder.Connection::read_header_len: bad header len: ip', self.get_ip(), 'port', self.get_port(), 's', ord(s))
            return None
        if DEBUG:
            log('Encoder.Connection::read_header_len: next func is read_header: ip', self.get_ip(), 'port', self.get_port())
        return (len(protocol_name), self.read_header)

    def read_header(self, s):
        if s != protocol_name:
            if DEBUG:
                log('Encoder.Connection::read_header: bad header: ip', self.get_ip(), 'port', self.get_port(), 's', s)
            return None
        if DEBUG:
            log('Encoder.Connection::read_header: next func is read_reserved: ip', self.get_ip(), 'port', self.get_port())
        return (8, self.read_reserved)

    def read_reserved(self, s):
        if DEBUG:
            log('Encoder.Connection::read_reserved: Reserved bits:', show(s))
            log('Encoder.Connection::read_reserved: Reserved bits=', show(option_pattern))
        self.set_options(s)
        if DEBUG:
            log('Encoder.Connection::read_reserved: next func is read_download_id: ip', self.get_ip(), 'port', self.get_port())
        return (20, self.read_download_id)

    def read_download_id(self, s):
        if s != self.Encoder.download_id:
            return None
        if not self.locally_initiated:
            self.Encoder.connecter.external_connection_made += 1
            if self.coord_con:
                if DEBUG:
                    log('encoder::read_download_id: i am a proxy, using challenge', self.challenge)
                proxy_peer_id = encode_challenge_in_peerid(self.Encoder.my_id, self.challenge)
                self.connection.write(chr(len(protocol_name)) + protocol_name + option_pattern + self.Encoder.download_id + proxy_peer_id)
            else:
                self.connection.write(chr(len(protocol_name)) + protocol_name + option_pattern + self.Encoder.download_id + self.Encoder.my_id)
        if DEBUG:
            log('Encoder.Connection::read_download_id: next func is read_peer_id: ip', self.get_ip(), 'port', self.get_port())
        return (20, self.read_peer_id)

    def read_peer_id(self, s):
        if DEBUG:
            log('Encoder.Connection::read_peer_id: ip', self.get_ip(), 'port', self.get_port())
        if not self.id:
            self.id = s
            self.readable_id = make_readable(s)
        elif s != self.id:
            if DEBUG:
                log('Encoder.Connection::read_peer_id: s != self.id, returning None: ip', self.get_ip(), 'port', self.get_port())
            return None
        self.complete = self.Encoder.got_id(self)
        if DEBUG:
            log('Encoder.Connection::read_peer_id: complete', self.complete, 'ip', self.get_ip(), 'port', self.get_port())
        if not self.complete:
            if DEBUG:
                log('Encoder.Connection::read_peer_id: self not complete!!!, returning None: ip', self.get_ip(), 'port', self.get_port())
            return None
        if self.locally_initiated:
            if self.coord_con:
                if DEBUG:
                    log('Encoder.Connection::read_peer_id: i am a proxy, using challenge', self.challenge)
                proxy_peer_id = encode_challenge_in_peerid(self.Encoder.my_id, self.challenge)
                self.connection.write(proxy_peer_id)
            else:
                self.connection.write(self.Encoder.my_id)
            incompletecounter.decrement()
            self.Encoder._start_connection_from_queue(sched=False)
        c = self.Encoder.connecter.connection_made(self)
        self.keepalive = c.send_keepalive
        return (4, self.read_len)

    def read_len(self, s):
        l = toint(s)
        if l > self.Encoder.max_len:
            return None
        return (l, self.read_message)

    def read_message(self, s):
        if s != '':
            self.connecter.got_message(self, s)
        return (4, self.read_len)

    def read_dead(self, s):
        return None

    def _auto_close(self):
        if not self.complete:
            if DEBUG:
                log('Encoder.Connection:_auto_close: ', self.get_myip(), self.get_myport(), 'to', self.get_ip(), self.get_port())
            repexer = self.Encoder.repexer
            if repexer and not self.closed:
                try:
                    repexer.connection_timeout(self)
                except:
                    log_exc()

            self.close()

    def close(self, closeall = False):
        if DEBUG:
            log('Encoder.Connection::close: ip', self.get_ip(), 'port', self.get_port())
        if not self.closed:
            self.connection.close()
            self.sever(closeall=closeall)

    def sever(self, closeall = False):
        self.closed = True
        if self.Encoder.connections.has_key(self.connection):
            self.Encoder.admin_close(self.connection)
        repexer = self.Encoder.repexer
        if repexer and not self.complete:
            try:
                repexer.connection_closed(self)
            except:
                log_exc()

        if self.complete:
            self.connecter.connection_lost(self)
        elif self.locally_initiated:
            incompletecounter.decrement()
            if not closeall:
                self.Encoder._start_connection_from_queue(sched=False)

    def send_message_raw(self, message):
        if not self.closed:
            self.connection.write(message)

    def data_came_in(self, connection, s):
        self.Encoder.measurefunc(len(s))
        while 1:
            if self.closed:
                return
            i = self.next_len - self.buffer.tell()
            if i > len(s):
                self.buffer.write(s)
                return
            self.buffer.write(s[:i])
            s = s[i:]
            m = self.buffer.getvalue()
            self.buffer.reset()
            self.buffer.truncate()
            try:
                x = self.next_func(m)
            except:
                log_exc()
                self.next_len, self.next_func = 1, self.read_dead
                raise

            if x is None:
                if DEBUG:
                    print >> sys.stderr, 'encoder: function failed', self.next_func
                self.close()
                return
            self.next_len, self.next_func = x

    def connection_flushed(self, connection):
        if self.complete:
            self.connecter.connection_flushed(self)

    def connection_lost(self, connection):
        if self.Encoder.connections.has_key(connection):
            self.sever()

    def is_coordinator_con(self):
        if self.coord_con:
            return True
        elif self.Encoder.helper is not None and self.Encoder.helper.is_coordinator_ip(self.get_ip()) and self.get_ip() != '127.0.0.1':
            return True
        else:
            return False

    def is_helper_con(self):
        coordinator = self.connecter.coordinator
        if coordinator is None:
            return False
        return coordinator.is_helper_ip(self.get_ip())

    def na_set_address_distance(self):
        hisip = self.get_ip(real=True)
        myip = self.get_myip(real=True)
        a = hisip.split('.')
        b = myip.split('.')
        if a[0] == b[0] and a[1] == b[1] and a[2] == b[2]:
            if DEBUG:
                print >> sys.stderr, 'encoder.connection: na: Found peer on local LAN', self.get_ip()
            self.na_address_distance = 0
        else:
            self.na_address_distance = 1

    def na_get_address_distance(self):
        return self.na_address_distance


class Encoder():

    def __init__(self, connecter, raw_server, my_id, max_len, schedulefunc, keepalive_delay, download_id, measurefunc, config, limit_connections_queue):
        self.raw_server = raw_server
        self.connecter = connecter
        self.my_id = my_id
        self.max_len = max_len
        self.schedulefunc = schedulefunc
        self.keepalive_delay = keepalive_delay
        self.download_id = download_id
        self.measurefunc = measurefunc
        self.config = config
        self.connections = {}
        self.banned = {}
        self.to_connect = set()
        self.trackertime = None
        self.paused = False
        self.limit_connections_queue = limit_connections_queue
        if self.config['max_connections'] == 0:
            self.max_connections = 1073741824
        else:
            self.max_connections = self.config['max_connections']
        self.rerequest = None
        self.toofast_banned = {}
        self.helper = None
        self.white_list = None
        self.black_list = None
        self.app_mode = globalConfig.get_mode()
        if self.app_mode == 'node':
            self.last_source_check_time = None
            source_node = globalConfig.get_value('source_node')
            support_nodes = globalConfig.get_value('support_nodes')
            if not globalConfig.get_value('allow_peers_download'):
                self.white_list = set()
                if source_node is not None and globalConfig.get_value('allow_source_download'):
                    self.white_list.add(source_node[0])
                if len(support_nodes) and globalConfig.get_value('allow_support_download'):
                    self.white_list.update([ addr[0] for addr in support_nodes ])
            else:
                self.black_list = set()
                if source_node is not None and not globalConfig.get_value('allow_source_download'):
                    self.black_list.add(source_node[0])
                if len(support_nodes) and not globalConfig.get_value('allow_support_download'):
                    self.black_list.update([ addr[0] for addr in support_nodes ])
                if len(self.black_list) == 0:
                    self.black_list = None
            if DEBUG:
                log('Encoder::__init__: white_list', self.white_list, 'black_list', self.black_list)
        schedulefunc(self.send_keepalives, keepalive_delay)
        self.repexer = None

    def send_keepalives(self):
        self.schedulefunc(self.send_keepalives, self.keepalive_delay)
        if self.paused:
            return
        for c in self.connections.values():
            c.keepalive()

    def start_connections(self, dnsidlist):
        if self.rerequest is not None and self.rerequest.am_video_source:
            if DEBUG:
                log('encoder::start_connections: do not start connections for live source')
            return
        if DEBUG:
            log('encoder::start_connections: adding', len(dnsidlist), 'peers to queue, current len', len(self.to_connect))
        wasempty = not self.to_connect
        self.to_connect.update(dnsidlist)
        if self.limit_connections_queue > 0:
            if DEBUG:
                log('encoder::start_connections: check queue limit: qlen', len(self.to_connect), 'limit', self.limit_connections_queue)
            while len(self.to_connect) > self.limit_connections_queue:
                self.to_connect.pop()

            if DEBUG:
                log('encoder::start_connections: queue limit done: qlen', len(self.to_connect), 'limit', self.limit_connections_queue)
        if wasempty:
            self.raw_server.add_task(self._start_connection_from_queue)
        self.trackertime = time()

    def _start_connection_from_queue(self, sched = True):
        try:
            force_sched = False
            if self.app_mode == 'node' and (self.last_source_check_time is None or time() - self.last_source_check_time > 10):
                try:
                    self.last_source_check_time = time()
                    if globalConfig.get_value('allow_source_download'):
                        source_node = globalConfig.get_value('source_node')
                        if source_node is not None:
                            connected_to_source = False
                            if len(self.connections) == 0:
                                if DEBUG:
                                    log('encoder::_start_connection_from_queue: no connections, connect to the source:', source_node)
                            else:
                                if DEBUG:
                                    log('encoder::_start_connection_from_queue: check connection to the source:', source_node)
                                for v in self.connections.values():
                                    if v is None:
                                        continue
                                    ip = v.get_ip(True)
                                    port = v.get_port(False)
                                    if DEBUG:
                                        log('encoder::_start_connection_from_queue: check connection to the source: test ip', ip, 'port', port)
                                    if ip == source_node[0] and port == source_node[1]:
                                        connected_to_source = True
                                        if DEBUG:
                                            log('encoder::_start_connection_from_queue: got connection to the source:', source_node)
                                        break

                            if not connected_to_source:
                                if DEBUG:
                                    log('encoder::_start_connection_from_queue: start connection to the source:', source_node)
                                force_sched = True
                                self.to_connect.add((tuple(source_node), 0))
                    if globalConfig.get_value('allow_support_download'):
                        support_nodes = globalConfig.get_value('support_nodes')
                        if len(support_nodes):
                            nodes = {}
                            for addr in support_nodes:
                                nodes[tuple(addr)] = False

                            if len(self.connections) == 0:
                                if DEBUG:
                                    log('encoder::_start_connection_from_queue: no connections, connect to support nodes:', support_nodes)
                            else:
                                for v in self.connections.values():
                                    if v is None:
                                        continue
                                    ip = v.get_ip(True)
                                    port = v.get_port(False)
                                    if DEBUG:
                                        log('encoder::_start_connection_from_queue: check connection to support node: test ip', ip, 'port', port)
                                    addr = (ip, port)
                                    if addr in nodes:
                                        nodes[addr] = True
                                        if DEBUG:
                                            log('encoder::_start_connection_from_queue: got connection to support node:', addr)

                            for addr, connected in nodes.iteritems():
                                if not connected:
                                    if DEBUG:
                                        log('encoder::_start_connection_from_queue: start connection to support node:', addr)
                                    force_sched = True
                                    self.to_connect.add((addr, 0))

                except:
                    print_exc()

            if not self.to_connect:
                return
            if self.connecter.external_connection_made:
                max_initiate = self.config['max_initiate']
            else:
                max_initiate = int(self.config['max_initiate'] * 1.5)
            cons = len(self.connections)
            if DEBUG:
                log('encoder::_start_connection_from_queue: conns', cons, 'max conns', self.max_connections, 'max init', max_initiate)
            if cons >= self.max_connections or cons >= max_initiate:
                delay = 60.0
                if DEBUG:
                    log('encoder::_start_connection_from_queue: cons >= max: delay', delay)
            elif self.paused or incompletecounter.toomany():
                delay = 1.0
                if DEBUG:
                    log('encoder::_start_connection_from_queue: paused or too many: delay', delay)
            else:
                delay = 0.0
                dns, id = self.to_connect.pop()
                if self.white_list is not None and dns[0] not in self.white_list:
                    if DEBUG:
                        log('encoder::_start_connection_from_queue: peer is not in the white list: dns', dns)
                elif self.black_list is not None and dns[0] in self.black_list:
                    if DEBUG:
                        log('encoder::_start_connection_from_queue: peer is in the black list: dns', dns)
                else:
                    if DEBUG:
                        log('encoder::_start_connection_from_queue: start now: dns', dns, 'id', id)
                    self.start_connection(dns, id)
            if force_sched or self.to_connect and sched:
                if force_sched:
                    delay = 11.0
                if DEBUG:
                    log('encoder::_start_connection_from_queue: start_from_queue: force', force_sched, 'delay', delay)
                self.raw_server.add_task(self._start_connection_from_queue, delay)
        except:
            log_exc()
            raise

    def start_connection(self, dns, id, coord_con = False, proxy_con = False, forcenew = False, challenge = None, proxy_permid = None):
        if DEBUG:
            log('encoder::start_connection: start_connection:', dns)
            log('encoder::start_connection: start_connection: qlen', len(self.to_connect), 'nconns', len(self.connections), 'maxi', self.config['max_initiate'], 'maxc', self.config['max_connections'])
        if (self.paused or len(self.connections) >= self.max_connections or id == self.my_id or self.banned.has_key(dns[0])) and not forcenew:
            if DEBUG:
                print >> sys.stderr, "encoder: start_connection: we're paused or too busy"
            return True
        for v in self.connections.values():
            if v is None:
                continue
            if id and v.id == id and not forcenew:
                if DEBUG:
                    log('encoder::start_connection: already connected to peer', id)
                return True
            ip = v.get_ip(True)
            port = v.get_port(False)
            if DEBUG:
                log('encoder::start_connection: candidate', ip, port, 'want', dns[0], dns[1])
            if self.config['security'] and ip != 'unknown' and ip == dns[0] and port == dns[1] and not forcenew:
                if DEBUG:
                    log('encoder::start_connection: using existing', ip, 'want port', dns[1], 'existing port', port, 'id', `id`)
                return True

        try:
            if DEBUG:
                log('encoder::start_connection: Setting up new to peer', dns, 'id', `id`, 'proxy_con', proxy_con, 'challenge', challenge)
            c = self.raw_server.start_connection(dns)
            con = Connection(self, c, id, dns=dns, coord_con=coord_con, proxy_con=proxy_con, challenge=challenge, proxy_permid=proxy_permid)
            self.connections[c] = con
            c.set_handler(con)
        except socketerror:
            if DEBUG:
                log('encoder::start_connection: failed')
            return False

        return True

    def _start_connection(self, dns, id):

        def foo(self = self, dns = dns, id = id):
            self.start_connection(dns, id)

        self.schedulefunc(foo, 0)

    def got_id(self, connection):
        if connection.id == self.my_id:
            ret = self.connecter.na_got_loopback(connection)
            if DEBUG:
                print >> sys.stderr, 'encoder: got_id: connection to myself? keep', ret
            if ret == False:
                self.connecter.external_connection_made -= 1
            return ret
        ip = connection.get_ip(True)
        port = connection.get_port(False)
        connection.na_set_address_distance()
        if self.config['security'] and self.banned.has_key(ip):
            if DEBUG:
                print >> sys.stderr, 'encoder: got_id: security ban on IP'
            return False
        for v in self.connections.values():
            if connection is not v:
                if DEBUG:
                    print >> sys.stderr, 'encoder: got_id: new internal conn from peer? ids', connection.id, v.id
                if connection.id == v.id:
                    if DEBUG:
                        print >> sys.stderr, 'encoder: got_id: new internal conn from peer? addrs', v.na_want_internal_conn_from, ip
                    if v.na_want_internal_conn_from == ip:
                        self.connecter.na_got_internal_connection(v, connection)
                        return True
                    if v.create_time < connection.create_time:
                        if DEBUG:
                            print >> sys.stderr, 'encoder: got_id: create time bad?!'
                    return False
                if self.config['security'] and ip != 'unknown' and ip == v.get_ip(True) and port == v.get_port(False):
                    if DEBUG:
                        log('encoder::got_id: closing duplicate connection')
                    v.close()

        return True

    def external_connection_made(self, connection):
        if DEBUG:
            log('encoder::external_connection_made: ip', connection.get_ip(), 'port', connection.get_port())
        if self.paused or len(self.connections) >= self.max_connections:
            if DEBUG:
                log('encoder::external_connection_made: paused or too many: ip', connection.get_ip(), 'port', connection.get_port())
            connection.close()
            return False
        con = Connection(self, connection, None)
        self.connections[connection] = con
        connection.set_handler(con)
        return True

    def externally_handshaked_connection_made(self, connection, options, msg_remainder):
        if DEBUG:
            log('encoder::externally_handshaked_connection_made: ip', connection.get_ip(), 'port', connection.get_port())
        if self.paused or len(self.connections) >= self.max_connections:
            connection.close()
            return False
        con = Connection(self, connection, None, True)
        con.set_options(options)
        self.connections[connection] = con
        connection.set_handler(con)
        if msg_remainder:
            con.data_came_in(con, msg_remainder)
        return True

    def close_all(self):
        if DEBUG:
            print >> sys.stderr, 'encoder: closing all connections'
        copy = self.connections.values()[:]
        for c in copy:
            c.close(closeall=True)

        self.connections = {}

    def ban(self, ip):
        self.banned[ip] = 1

    def pause(self, flag):
        self.paused = flag

    def set_helper(self, helper):
        self.helper = helper

    def set_rerequester(self, rerequest):
        self.rerequest = rerequest

    def how_many_connections(self):
        return len(self.connections) + len(self.to_connect)

    def admin_close(self, conn):
        del self.connections[conn]
        now = time()
        remaining_connections = len(self.connections) + len(self.to_connect)
        if DEBUG_CLOSE:
            log('Encoder::admin_close: ip', conn.get_ip(), 'port', conn.get_port(), 'remaining connections', remaining_connections)
            print_stack()
        if DEBUG_CLOSE and remaining_connections == 0 and self.trackertime and self.rerequest is not None:
            log('>>>encoder:admin_close: amount left', self.rerequest.amount_left(), 'is_video_source', self.rerequest.am_video_source)
        if remaining_connections == 0 and self.trackertime and self.rerequest is not None and not self.rerequest.am_video_source and self.rerequest.amount_left():
            if self.rerequest.check_network_connection(announce=False):
                schedule_refresh_in = max(30, int(300 - (now - self.trackertime)))
                if DEBUG_CLOSE:
                    log('Encoder::admin_close: want new peers in', schedule_refresh_in, 's')
                if schedule_refresh_in <= 0:
                    self.rerequest.encoder_wants_new_peers()
                else:
                    self.raw_server.add_task(self.rerequest.encoder_wants_new_peers, schedule_refresh_in)
            self.trackertime = None
