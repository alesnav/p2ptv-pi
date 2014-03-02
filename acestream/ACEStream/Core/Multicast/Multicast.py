#Embedded file name: ACEStream\Core\Multicast\Multicast.pyo
import socket
import threading
import struct
import select
import string
import sys
import time
import random
from traceback import print_exc
import base64
from ACEStream.Core.BuddyCast.buddycast import BuddyCastFactory
DEBUG = False

class MyLogger:
    enabled = DEBUG

    def debug(self, message):
        if self.enabled:
            print >> sys.stderr, 'pdisc: DEBUG:', message

    def info(self, message):
        if self.enabled:
            print >> sys.stderr, 'pdisc: INFO:', message

    def warning(self, message):
        if self.enabled:
            print >> sys.stderr, 'pdisc: WARNING:', message

    def error(self, message):
        if self.enabled:
            print >> sys.stderr, 'pdisc: ERROR:', message

    def fatal(self, message):
        if self.enabled:
            print >> sys.stderr, 'pdisc: FATAL:', message

    def exception(self, message):
        if self.enabled:
            print >> sys.stderr, 'pdisc: EXCEPTION:', message
            import traceback
            traceback.print_exc()


class Multicast:

    def __init__(self, config, overlay_bridge, myport, myselversion, peerdb, logger = None, capabilities = None):
        self.myport = myport
        self.myselversion = myselversion
        self.overlay_bridge = overlay_bridge
        self.peer_db = peerdb
        if logger:
            self.log = logger
        else:
            self.log = MyLogger()
        self.config = config
        self.capabilities = capabilities
        self.enabled = False
        self.announceHandlers = []
        self.on_node_announce = None
        self.incoming_pongs = {}
        self.interfaces = []
        self.address_family = socket.AF_INET
        if self.config['multicast_ipv6_enabled']:
            if not socket.has_ipv6:
                self.log.warning('Missing IPv6 support')
            else:
                self.address_family = socket.AF_INET6
        self.sock = socket.socket(self.address_family, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        for res in socket.getaddrinfo(None, self.config['multicast_port'], self.address_family, socket.SOCK_DGRAM, 0, socket.AI_PASSIVE):
            af, socktype, proto, canonname, sa = res
            try:
                self.sock.bind(sa)
            except:
                self.log.exception('Error binding')

        try:
            if self.config['multicast_ipv6_enabled']:
                self.interfaces = self._joinMulticast(self.config['multicast_ipv6_address'], self.config['multicast_port'], self.sock)
                self.enabled = True
        except:
            self.log.exception('Exception during IPv6 multicast join')

        try:
            if self.config['multicast_ipv4_enabled']:
                self._joinMulticast(self.config['multicast_ipv4_address'], self.config['multicast_port'], self.sock)
                self.enabled = True
        except:
            self.log.exception('Exception during IPv4 multicast join')

    def _getCapabilities(self, elements):
        capabilities = []
        for elem in elements:
            if elem.startswith('c:'):
                capabilities.append(elem[2:])

        return capabilities

    def getSocket(self):
        return self.sock

    def _joinMulticast(self, addr, port, sock):
        import struct
        for res in socket.getaddrinfo(addr, port, socket.AF_UNSPEC, socket.SOCK_DGRAM):
            af, socktype, proto, canonname, sa = res
            break

        if af == socket.AF_INET6:
            num_colons = addr.count(':')
            new_colons = ':'
            for i in range(num_colons, 8):
                new_colons = '%s0:' % new_colons

            addr = addr.replace('::', new_colons)
            addr_pack = ''
            for l in addr.split(':'):
                word = int(l, 16)
                addr_pack = addr_pack + struct.pack('!H', word)

            interfaces = []
            for i in range(1, 32):
                try:
                    mreq = addr_pack + struct.pack('l', i)
                    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP, mreq)
                    ok = True
                    self.log.debug('Joined IPv6 multicast on interface %d' % i)
                    interfaces.append(i)
                except Exception as e:
                    pass

            if len(interfaces) == 0:
                self.log.fatal('Could not join on any interface')
                raise Exception('Could not join multicast on any interface')
            return interfaces
        if af == socket.AF_INET:
            addr_pack = ''
            grpaddr = 0
            bytes = map(int, string.split(addr, '.'))
            for byte in bytes:
                grpaddr = grpaddr << 8 | byte

            ifaddr = socket.INADDR_ANY
            mreq = struct.pack('ll', socket.htonl(grpaddr), socket.htonl(ifaddr))
            try:
                self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            except Exception as e:
                self.log.exception('Exception joining IPv4 multicast')

            return []

    def data_came_in(self, packets):
        process_data_func = lambda : self._data_came_in_callback(packets)
        self.overlay_bridge.add_task(process_data_func, 0)

    def _data_came_in_callback(self, packets):
        for addr, data in packets:
            self.log.debug('Got a message from %s' % str(addr))
            try:
                elements = data.split('\n')
                if elements[0] == 'NODE_DISCOVER':
                    if len(elements) < 3:
                        raise Exception('Too few elements')
                    if not self.config['multicast_announce']:
                        self.log.debug('Not announcing myself')
                        continue
                    remotePermID = elements[2]
                    self.log.debug('Got node discovery from %s' % remotePermID)
                    permid_64 = base64.b64encode(self.config['permid']).replace('\n', '')
                    msg = 'NODE_ANNOUNCE\n%s' % permid_64
                    if self.capabilities:
                        for capability in self.capabilities:
                            msg += '\nc:%s' % capability

                    try:
                        self.sock.sendto(msg, addr)
                    except Exception as e:
                        self.log.error('Could not send announce message to %s: %s' % (str(addr), e))
                        continue

                elif elements[0] == 'ANNOUNCE':
                    self.handleAnnounce(addr, elements)
                elif elements[0] == 'NODE_ANNOUNCE':
                    if self.on_node_announce:
                        try:
                            self.on_node_announce(elements[1], addr, self._getCapabilities(elements))
                        except Exception as e:
                            self.log.exception('Exception handling node announce')

                elif elements[0] == 'PING':
                    permid = base64.b64decode(elements[1])
                    if permid == self.config['permid']:
                        msg = 'PONG\n%s\n%s' % (elements[1], elements[2])
                        self._sendMulticast(msg)
                elif elements[0] == 'PONG':
                    nonce = int(elements[2])
                    if self.outstanding_pings.has_key(nonce):
                        self.incoming_pongs[nonce] = time.time()
                else:
                    self.log.warning('Got bad discovery message from %s' % str(addr))
            except Exception as e:
                self.log.exception("Illegal message '%s' from '%s'" % (data, addr[0]))

    def _send(self, addr, msg):
        for res in socket.getaddrinfo(addr, self.config['multicast_port'], socket.AF_UNSPEC, socket.SOCK_DGRAM):
            af, socktype, proto, canonname, sa = res

        try:
            sock = socket.socket(af, socktype)
            sock.sendto(msg, sa)
        except Exception as e:
            self.log.warning("Error sending '%s...' to %s: %s" % (msg[:8], str(sa), e))

        return sock

    def discoverNodes(self, timeout = 3.0, requiredCapabilities = None):
        msg = 'NODE_DISCOVER\nTr_OVERLAYSWARM node\npermid:%s' % base64.b64encode(self.config['permid']).replace('\n', '')
        addrList = []
        sockList = []
        if self.config['multicast_ipv4_enabled']:
            sockList.append(self._send(self.config['multicast_ipv4_address'], msg))
        if self.config['multicast_ipv6_enabled']:
            for iface in self.interfaces:
                sockList.append(self._send('%s%%%s' % (self.config['multicast_ipv6_address'], iface), msg))

        nodeList = []
        endAt = time.time() + timeout
        while time.time() < endAt:
            SelectList = sockList[:]
            InList, OutList, ErrList = select.select(SelectList, [], [], 1.0)
            if len(ErrList) < 0:
                self.log.warning('Select gives error...')
            while len(InList) > 0:
                sock2 = InList.pop(0)
                try:
                    data, addr = sock2.recvfrom(1450)
                except socket.error as e:
                    self.log.warning('Exception receiving: %s' % e)
                    continue
                except Exception as e:
                    print_exc()
                    self.log.warning('Unknown exception receiving')
                    continue

                try:
                    elements = data.split('\n')
                    if len(elements) < 2:
                        self.log.warning('Bad message from %s: %s' % (addr, data))
                        continue
                    if elements[0] != 'NODE_ANNOUNCE':
                        self.log.warning('Unknown message from %s: %s' % (addr, data))
                        continue
                    permid = base64.b64decode(elements[1])
                    self.log.info('Discovered node %s at (%s)' % (permid, str(addr)))
                    capabilities = self._getCapabilities(elements)
                    if requiredCapabilities:
                        ok = False
                        for rc in requiredCapabilities:
                            if rc in capabilities:
                                ok = True
                                break

                        if not ok:
                            continue
                    nodeList.append((permid, addr, capabilities))
                except Exception as e:
                    self.log.warning('Could not understand message: %s' % e)

        return nodeList

    def sendNodeAnnounce(self):
        msg = 'NODE_ANNOUNCE\n%s' % base64.b64encode(self.config['permid']).replace('\n', '')
        if self.capabilities:
            for capability in self.capabilities:
                msg += '\nc:%s' % capability

        try:
            self._sendMulticast(msg)
        except:
            self.log.error('Could not send announce message')

    def setNodeAnnounceHandler(self, handler):
        self.on_node_announce = handler

    def addAnnounceHandler(self, handler):
        self.announceHandlers.append(handler)

    def removeAnnouncehandler(self, handler):
        try:
            self.announceHandlers.remove(handler)
        except:
            pass

    def handleAnnounce(self, addr, elements):
        if elements[0] != 'ANNOUNCE':
            raise Exception('Announce handler called on non-announce: %s' % elements[0])
        if len(elements) < 3:
            raise Exception('Bad announce, too few elements in message')
        try:
            permid = base64.b64decode(elements[1])
            numElements = int(elements[2])
        except:
            raise Exception('Bad announce message')

        if len(elements) < 3 + numElements:
            raise Exception('Incomplete announce message')
        _list = elements[3:3 + numElements]
        list = []
        for elem in _list:
            if elem.isdigit():
                list.append(long(elem))
            else:
                list.append(elem)

        if len(self.announceHandlers) == 0:
            self.log.warning("Got node-announce, but I'm missing announce handlers")
        for handler in self.announceHandlers:
            try:
                self.log.debug('Calling callback handler')
                handler(permid, addr, list)
            except:
                self.log.exception("Could not activate announce handler callback '%s'" % handler)

    def handleOVERLAYSWARMAnnounce(self, permid, addr, params):
        self.log.debug('Got Tr_OVERLAYSWARM announce!')
        port, selversion = params
        if permid == self.config['permid']:
            self.log.debug('Discovered myself')
            return
        if self.flag_peer_as_local_to_db(permid, True):
            self.log.debug('node flagged as local')
            return
        try:
            try:
                self.log.debug('Adding peer at %s to database' % addr[0])
                self.add_peer_to_db(permid, (addr[0], port), selversion)
            except Exception as e:
                print >> sys.stderr, 'pdisc: Could not add node:', e

            try:
                self.flag_peer_as_local_to_db(permid, True)
                self.log.debug('node flagged as local')
            except Exception as e:
                print >> sys.stderr, 'pdisc: Could not flag node as local:', e

            bc_core = BuddyCastFactory.getInstance().buddycast_core
            if bc_core:
                self.log.debug('Triggering buddycast')
                bc_core.startBuddyCast(permid)
        finally:
            params = [self.myport, self.myselversion]
            self.log.debug('Sending announce myself')
            try:
                self.sendAnnounce(params)
            except:
                self.log.exception('Sending announcement')

    def sendAnnounce(self, list):
        if not self.enabled:
            return
        msg = 'ANNOUNCE\n%s\n%d\n' % (base64.b64encode(self.config['permid']).replace('\n', ''), len(list))
        for elem in list:
            msg += '%s\n' % elem

        self._sendMulticast(msg)

    def _sendMulticast(self, msg):
        if self.config['multicast_ipv4_enabled']:
            self._send(self.config['multicast_ipv4_address'], msg)
        if self.config['multicast_ipv6_enabled']:
            for iface in self.interfaces:
                self._send('%s%%%s' % (self.config['multicast_ipv6_address'], iface), msg)

    def ping(self, permid, numPings = 3):
        self.outstanding_pings = {}
        self.incoming_pongs = {}
        for i in range(0, numPings):
            nonce = random.randint(0, 2147483647)
            msg = 'PING\n%s\n%s' % (base64.b64encode(permid).replace('\n', ''), nonce)
            self.outstanding_pings[nonce] = time.time()
            self._sendMulticast(msg)
            time.sleep(0.25)

        time.sleep(0.5)
        if len(self.incoming_pongs) == 0:
            return (None, None, None)
        max = 0
        min = 2147483647
        total = 0
        num = 0
        for nonce in self.outstanding_pings.keys():
            if self.incoming_pongs.has_key(nonce):
                diff = self.incoming_pongs[nonce] - self.outstanding_pings[nonce]
                if diff > max:
                    max = diff
                if diff < min:
                    min = diff
                total += diff
                num += 1

        avg = total / num
        self.outstanding_pings = {}
        self.incoming_pongs = {}
        return (avg, min, max)

    def add_peer_to_db(self, permid, dns, selversion):
        now = int(time.time())
        peer_data = {'permid': permid,
         'ip': dns[0],
         'port': dns[1],
         'oversion': selversion,
         'last_seen': now,
         'last_connected': now}
        self.peer_db.addPeer(permid, peer_data, update_dns=True, update_connected=True, commit=True)

    def flag_peer_as_local_to_db(self, permid, is_local):
        peer = self.peer_db.getPeer(permid, ('is_local',))
        if peer is not None:
            if isinstance(peer, list):
                flag = peer[0]
            else:
                flag = peer
            if not flag == is_local:
                self.peer_db.setPeerLocalFlag(permid, is_local)
            return True
        return False
