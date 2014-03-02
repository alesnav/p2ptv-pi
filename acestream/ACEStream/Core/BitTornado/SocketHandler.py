#Embedded file name: ACEStream\Core\BitTornado\SocketHandler.pyo
import socket
import errno
try:
    from select import poll, POLLIN, POLLOUT, POLLERR, POLLHUP
    timemult = 1000
except ImportError:
    from selectpoll import poll, POLLIN, POLLOUT, POLLERR, POLLHUP
    timemult = 1

from time import sleep
from clock import clock
import sys
from random import shuffle, randrange
from traceback import print_exc, print_stack
from ACEStream.GlobalConfig import globalConfig
from ACEStream.Core.Utilities.logger import log, log_exc
try:
    True
except:
    True = 1
    False = 0

DEBUG = False
DEBUG2 = False
all = POLLIN | POLLOUT
if sys.platform == 'win32':
    SOCKET_BLOCK_ERRORCODE = 10035
else:
    SOCKET_BLOCK_ERRORCODE = errno.EWOULDBLOCK

class InterruptSocketHandler:

    @staticmethod
    def data_came_in(interrupt_socket, data):
        pass


class InterruptSocket:

    def __init__(self, socket_handler):
        self.socket_handler = socket_handler
        self.handler = InterruptSocketHandler
        self.ip = '127.0.0.1'
        self.port = None
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.interrupt_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.ip, 0))
        bind_host, bind_port = self.socket.getsockname()
        if DEBUG:
            log('InterruptSocket::__init__: bound on', bind_host, bind_port)
        self.port = bind_port
        self.socket_handler.single_sockets[self.socket.fileno()] = self
        self.socket_handler.poll.register(self.socket, POLLIN)

    def interrupt(self):
        self.interrupt_socket.sendto('+', (self.ip, self.port))

    def get_ip(self):
        return self.ip

    def get_port(self):
        return self.port


class UdpSocket:

    def __init__(self, socket, handler):
        self.socket = socket
        self.handler = handler


class SingleSocket:

    def __init__(self, socket_handler, sock, handler, ip = None):
        self.socket_handler = socket_handler
        self.socket = sock
        self.handler = handler
        self.buffer = []
        self.last_hit = clock()
        self.fileno = sock.fileno()
        self.connected = False
        self.skipped = 0
        self.myip = None
        self.myport = -1
        self.ip = None
        self.port = -1
        try:
            myname = self.socket.getsockname()
            self.myip = myname[0]
            self.myport = myname[1]
            peername = self.socket.getpeername()
            self.ip = peername[0]
            self.port = peername[1]
        except:
            if ip is None:
                self.ip = 'unknown'
            else:
                self.ip = ip

        self.data_sent = 0
        self.data_received = 0
        if DEBUG:
            log('SingleSocket::__init__: myip', self.myip, 'myport', self.myport, 'ip', self.ip, 'port', self.port, 'handler', self.handler)

    def get_ip(self, real = False):
        if real:
            try:
                peername = self.socket.getpeername()
                self.ip = peername[0]
                self.port = peername[1]
            except:
                pass

        return self.ip

    def get_port(self, real = False):
        if real:
            self.get_ip(True)
        return self.port

    def get_myip(self, real = False):
        if real:
            try:
                myname = self.socket.getsockname()
                self.myip = myname[0]
                self.myport = myname[1]
            except:
                print_exc()

        return self.myip

    def get_myport(self, real = False):
        if real:
            self.get_myip(True)
        return self.myport

    def close(self):
        if self.socket is None:
            if DEBUG2:
                log('SingleSocket::close: self.socket is None, return: len(buffer)', len(self.buffer))
            return
        if DEBUG2:
            log('SingleSocket::close: ---')
        self.connected = False
        sock = self.socket
        self.socket = None
        self.buffer = []
        try:
            del self.socket_handler.single_sockets[self.fileno]
        except:
            print_exc()

        try:
            self.socket_handler.poll.unregister(sock)
        except:
            print_exc()

        sock.close()

    def shutdown(self, val):
        if DEBUG2:
            log('SingleSocket::shutdown: val', val)
        self.socket.shutdown(val)

    def is_flushed(self):
        return not self.buffer

    def write(self, s):
        if self.socket is None:
            if DEBUG2:
                log('SingleSocket::write: self.socket is None, return')
            return
        self.buffer.append(s)
        buf_len = len(self.buffer)
        if DEBUG2:
            log('SingleSocket::write: buf_len', buf_len, 'data_len', len(s))
        if buf_len == 1:
            self.try_write()

    def try_write(self):
        if DEBUG2:
            log('SingleSocket::try_write: connected', self.connected, 'buf_len', len(self.buffer))
        if self.connected:
            dead = False
            try:
                while self.buffer:
                    buf = self.buffer[0]
                    amount = self.socket.send(buf)
                    self.data_sent += amount
                    if amount == 0:
                        self.skipped += 1
                        break
                    self.skipped = 0
                    if amount != len(buf):
                        self.buffer[0] = buf[amount:]
                        break
                    del self.buffer[0]

            except socket.error as e:
                blocked = False
                try:
                    blocked = e[0] == SOCKET_BLOCK_ERRORCODE
                    dead = not blocked
                except:
                    dead = True

                if not blocked:
                    self.skipped += 1
            except:
                if DEBUG2:
                    print_exc()
                return

            if self.skipped >= 5:
                dead = True
            if dead:
                self.socket_handler.dead_from_write.append(self)
                return
        if self.buffer:
            self.socket_handler.poll.register(self.socket, all)
        else:
            self.socket_handler.poll.register(self.socket, POLLIN)

    def set_handler(self, handler):
        if DEBUG2:
            log('SingleSocket::set_handler: handler', handler)
        self.handler = handler


class SocketHandler:

    def __init__(self, timeout, ipv6_enable, readsize = 100000, max_connects = 1000):
        self.timeout = timeout
        self.ipv6_enable = ipv6_enable
        self.readsize = readsize
        self.poll = poll()
        self.single_sockets = {}
        self.dead_from_write = []
        if max_connects <= 0:
            max_connects = 1000
        if DEBUG:
            log('SocketHandler::__init__: max_connects', max_connects)
        self.max_connects = max_connects
        self.servers = {}
        self.btengine_said_reachable = False
        self.interrupt_socket = None
        self.udp_sockets = {}
        if globalConfig.get_mode() == 'stream' and globalConfig.get_value('private_source'):
            self.white_list = globalConfig.get_value('support_nodes')
            if DEBUG:
                log('SocketHandler::__init__: white_list', self.white_list)
        else:
            self.white_list = None

    def scan_for_timeouts(self):
        t = clock() - self.timeout
        tokill = []
        for s in self.single_sockets.values():
            if type(s) is SingleSocket and s.last_hit < t:
                tokill.append(s)

        for k in tokill:
            if k.socket is not None:
                if DEBUG:
                    log('SocketHandler::scan_for_timeouts: closing connection', k.get_ip())
                self._close_socket(k)

    def bind(self, port, bind = [], reuse = False, ipv6_socket_style = 1):
        port = int(port)
        addrinfos = []
        self.servers = {}
        self.interfaces = []
        if bind:
            if self.ipv6_enable:
                socktype = socket.AF_UNSPEC
            else:
                socktype = socket.AF_INET
            for addr in bind:
                if sys.version_info < (2, 2):
                    addrinfos.append((socket.AF_INET,
                     None,
                     None,
                     None,
                     (addr, port)))
                else:
                    addrinfos.extend(socket.getaddrinfo(addr, port, socktype, socket.SOCK_STREAM))

        else:
            if self.ipv6_enable:
                addrinfos.append([socket.AF_INET6,
                 None,
                 None,
                 None,
                 ('', port)])
            if not addrinfos or ipv6_socket_style != 0:
                addrinfos.append([socket.AF_INET,
                 None,
                 None,
                 None,
                 ('', port)])
        for addrinfo in addrinfos:
            try:
                server = socket.socket(addrinfo[0], socket.SOCK_STREAM)
                if reuse:
                    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.setblocking(0)
                if DEBUG:
                    log('SocketHandler::bind: try to bind socket on', addrinfo[4])
                server.bind(addrinfo[4])
                self.servers[server.fileno()] = server
                bind_host, bind_port = server.getsockname()
                self.interfaces.append((bind_host, bind_port))
                if DEBUG:
                    log('SocketHandler::bind: socket bound: host', bind_host, 'port', bind_port)
                server.listen(64)
                self.poll.register(server, POLLIN)
            except socket.error as e:
                for server in self.servers.values():
                    try:
                        server.close()
                    except:
                        pass

                if self.ipv6_enable and ipv6_socket_style == 0 and self.servers:
                    raise socket.error('blocked port (may require ipv6_binds_v4 to be set)')
                raise socket.error(str(e))

        if not self.servers:
            raise socket.error('unable to open server port')
        return self.interfaces[:]

    def find_and_bind(self, first_try, minport, maxport, bind = '', reuse = False, ipv6_socket_style = 1, randomizer = False):
        e = 'maxport less than minport - no ports to check'
        if minport == 0 and maxport == 0:
            portrange = range(1)
        elif maxport - minport < 50 or not randomizer:
            portrange = range(minport, maxport + 1)
            if randomizer:
                shuffle(portrange)
                portrange = portrange[:20]
        else:
            portrange = []
            while len(portrange) < 20:
                listen_port = randrange(minport, maxport + 1)
                if listen_port not in portrange:
                    portrange.append(listen_port)

        if first_try != 0:
            try:
                self.bind(first_try, bind, reuse=reuse, ipv6_socket_style=ipv6_socket_style)
                return first_try
            except socket.error as e:
                pass

        for listen_port in portrange:
            try:
                interfaces = self.bind(listen_port, bind, reuse=reuse, ipv6_socket_style=ipv6_socket_style)
                if len(interfaces) == 0:
                    raise socket.error('failed to bind on port')
                host, listen_port = interfaces[0]
                return listen_port
            except socket.error as e:
                raise

        raise socket.error(str(e))

    def set_handler(self, handler):
        self.handler = handler

    def start_connection_raw(self, dns, socktype = socket.AF_INET, handler = None):
        if handler is None:
            if DEBUG2:
                log('SocketHandler::start_connection_raw: handler is None, use self.handler:', self.handler)
            handler = self.handler
        elif DEBUG2:
            log('SocketHandler::start_connection_raw: use handler from params:', handler)
        sock = socket.socket(socktype, socket.SOCK_STREAM)
        sock.setblocking(0)
        try:
            if DEBUG2:
                log('SocketHandler::start_connection_raw: dns', dns, 'socket', sock.fileno())
            err = sock.connect_ex(dns)
            if DEBUG2:
                if err == 0:
                    msg = 'No error'
                else:
                    msg = errno.errorcode[err]
                log('SocketHandler:start_connection_raw: connect_ex on socket #', sock.fileno(), 'returned', err, msg)
            if err != 0:
                if sys.platform == 'win32' and err == 10035:
                    pass
                elif err == errno.EINPROGRESS:
                    pass
                else:
                    raise socket.error((err, errno.errorcode[err]))
        except socket.error as e:
            if DEBUG2:
                log('SocketHandler::start_connection_raw: SocketError in connect_ex')
                print_exc()
            raise
        except Exception as e:
            if DEBUG2:
                log('SocketHandler::start_connection_raw: Exception in connect_ex')
                print_exc()
            raise socket.error(str(e))

        self.poll.register(sock, POLLIN)
        s = SingleSocket(self, sock, handler, dns[0])
        self.single_sockets[sock.fileno()] = s
        if DEBUG2:
            log('SocketHandler::start_connection_raw: socket created: count_sockets', len(self.single_sockets))
        return s

    def start_connection(self, dns, handler = None, randomize = False):
        if handler is None:
            handler = self.handler
        if sys.version_info < (2, 2):
            s = self.start_connection_raw(dns, socket.AF_INET, handler)
        else:
            try:
                try:
                    socket.inet_aton(dns[0])
                    addrinfos = [(socket.AF_INET,
                      None,
                      None,
                      None,
                      (dns[0], dns[1]))]
                except:
                    try:
                        socktype = socket.AF_UNSPEC
                        addrinfos = socket.getaddrinfo(dns[0], int(dns[1]), socktype, socket.SOCK_STREAM)
                    except:
                        socktype = socket.AF_INET
                        addrinfos = socket.getaddrinfo(dns[0], int(dns[1]), socktype, socket.SOCK_STREAM)

            except socket.error as e:
                raise
            except Exception as e:
                raise socket.error(str(e))

            if randomize:
                shuffle(addrinfos)
            for addrinfo in addrinfos:
                try:
                    s = self.start_connection_raw(addrinfo[4], addrinfo[0], handler)
                    break
                except Exception as e:
                    if DEBUG:
                        print_exc()

            else:
                raise socket.error('unable to connect')

        return s

    def _sleep(self):
        sleep(1)

    def handle_events(self, events):
        for sock, event in events:
            s = self.servers.get(sock)
            if s:
                if event & (POLLHUP | POLLERR) != 0:
                    if DEBUG2:
                        log('SocketHandler::handle_events: got event, close server socket')
                    self.poll.unregister(s)
                    del self.servers[sock]
                else:
                    try:
                        newsock, addr = s.accept()
                        if not self.btengine_said_reachable:
                            try:
                                from ACEStream.Core.NATFirewall.DialbackMsgHandler import DialbackMsgHandler
                                dmh = DialbackMsgHandler.getInstance()
                                dmh.network_btengine_reachable_callback()
                            except ImportError:
                                if DEBUG:
                                    print_exc()

                            self.btengine_said_reachable = True
                        count_sockets = len(self.single_sockets)
                        if DEBUG2:
                            log('SocketHandler::handle_events: got incoming connection: from', newsock.getpeername(), 'count_sockets', count_sockets, 'max_connects', self.max_connects)
                        if count_sockets >= self.max_connects:
                            if DEBUG2:
                                log('SocketHandler::handle_events: too many connects, close remote socket: count_sockets', count_sockets, 'max_connects', self.max_connects)
                            newsock.close()
                        elif self.white_list is not None and addr[0] not in self.white_list:
                            if DEBUG2:
                                log('SocketHandler::handle_events: not in the white list, close remote socket: addr', addr)
                            newsock.close()
                        else:
                            newsock.setblocking(0)
                            nss = SingleSocket(self, newsock, self.handler)
                            self.single_sockets[newsock.fileno()] = nss
                            self.poll.register(newsock, POLLIN)
                            self.handler.external_connection_made(nss)
                    except socket.error as e:
                        if DEBUG:
                            log('SocketHandler::handle_events: SocketError while accepting new connection')
                            print_exc()
                        self._sleep()

                continue
            s = self.udp_sockets.get(sock)
            if s:
                packets = []
                try:
                    while True:
                        data, addr = s.socket.recvfrom(65535)
                        if not data:
                            if DEBUG2:
                                log('SocketHandler: UDP no-data', addr)
                            break
                        else:
                            if DEBUG2:
                                log('SocketHandler: Got UDP data', addr, 'len', len(data))
                            packets.append((addr, data))

                except socket.error as e:
                    if DEBUG:
                        log('SocketHandler: UDP Socket error')
                        print_exc()
                finally:
                    s.handler.data_came_in(packets)

                continue
            s = self.single_sockets.get(sock)
            if s:
                if event & (POLLHUP | POLLERR):
                    if DEBUG2:
                        log('SocketHandler::handle_events: got event, connect socket got error: ip', s.ip, 'port', s.port)
                    self._close_socket(s)
                    continue
                if event & POLLIN:
                    try:
                        s.last_hit = clock()
                        if s.socket is None:
                            data = None
                        else:
                            data = s.socket.recv(100000)
                        if not data:
                            if DEBUG:
                                log('SocketHandler::handle_events: no-data closing connection', s.get_ip(), s.get_port())
                            self._close_socket(s)
                        else:
                            if hasattr(s, 'data_received'):
                                s.data_received += len(data)
                            s.handler.data_came_in(s, data)
                    except socket.error as e:
                        if DEBUG:
                            log('SocketHandler::handle_events: socket error', str(e))
                        code, msg = e
                        if code != SOCKET_BLOCK_ERRORCODE:
                            if DEBUG:
                                log('SocketHandler::handle_events: closing connection because not WOULDBLOCK', s.get_ip(), 'error', code)
                            self._close_socket(s)
                            continue

                if event & POLLOUT and s.socket and not s.is_flushed():
                    s.connected = True
                    s.try_write()
                    if s.is_flushed():
                        s.handler.connection_flushed(s)

    def close_dead(self):
        while self.dead_from_write:
            old = self.dead_from_write
            self.dead_from_write = []
            for s in old:
                if s.socket:
                    if DEBUG2:
                        log('SocketHandler::close_dead: closing connection', s.get_ip())
                    self._close_socket(s)

    def _close_socket(self, s):
        if DEBUG2:
            log('SocketHandler::_close_socket: closing connection to', s.get_ip(), 'ss.handler', s.handler)
        s.close()
        s.handler.connection_lost(s)

    def do_poll(self, t):
        r = self.poll.poll(t * timemult)
        if r is None:
            connects = len(self.single_sockets)
            to_close = int(connects * 0.05) + 1
            self.max_connects = connects - to_close
            closelist = [ sock for sock in self.single_sockets.values() if not isinstance(sock, InterruptSocket) ]
            shuffle(closelist)
            closelist = closelist[:to_close]
            for sock in closelist:
                if DEBUG2:
                    log('SocketHandler::do_poll: closing connection', sock.get_ip())
                self._close_socket(sock)

            return []
        return r

    def get_stats(self):
        return {'interfaces': self.interfaces}

    def shutdown(self):
        for ss in self.single_sockets.values():
            try:
                ss.close()
            except:
                pass

        for server in self.servers.values():
            try:
                server.close()
            except:
                pass

    def create_udpsocket(self, port, host):
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 870400)
        server.bind((host, port))
        server.setblocking(0)
        return server

    def start_listening_udp(self, serversocket, handler):
        self.udp_sockets[serversocket.fileno()] = UdpSocket(serversocket, handler)
        self.poll.register(serversocket, POLLIN)

    def stop_listening_udp(self, serversocket):
        self.poll.unregister(serversocket)
        del self.udp_sockets[serversocket.fileno()]

    def get_interrupt_socket(self):
        if not self.interrupt_socket:
            self.interrupt_socket = InterruptSocket(self)
        return self.interrupt_socket
