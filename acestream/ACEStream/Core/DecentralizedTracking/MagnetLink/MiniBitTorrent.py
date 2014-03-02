#Embedded file name: ACEStream\Core\DecentralizedTracking\MagnetLink\MiniBitTorrent.pyo
from cStringIO import StringIO
from random import getrandbits
from threading import Lock, Event, Thread
from time import time
from traceback import print_exc
from urllib import urlopen, urlencode
import sys
from ACEStream.Core.BitTornado.BT1.MessageID import protocol_name, EXTEND
from ACEStream.Core.BitTornado.BT1.convert import toint, tobinary
from ACEStream.Core.BitTornado.RawServer import RawServer
from ACEStream.Core.BitTornado.SocketHandler import SocketHandler
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
from ACEStream.Core.Utilities.TSCrypto import sha
UT_EXTEND_HANDSHAKE = chr(0)
UT_PEX_ID = chr(1)
UT_METADATA_ID = chr(2)
METADATA_PIECE_SIZE = 16 * 1024
MAX_CONNECTIONS = 30
MAX_TIME_INACTIVE = 10
DEBUG = False

class Connection():

    def __init__(self, swarm, raw_server, address):
        self._swarm = swarm
        self._closed = False
        self._in_buffer = StringIO()
        self._next_len = 1
        self._next_func = self.read_header_len
        self._address = address
        self._last_activity = time()
        self._her_ut_metadata_id = chr(0)
        self._metadata_requests = {}
        if DEBUG:
            print >> sys.stderr, self._address, 'MiniBitTorrent: New connection'
        self._socket = raw_server.start_connection(address, self)
        self.write_handshake()

    @property
    def address(self):
        return self._address

    def write_handshake(self):
        self._socket.write(''.join((chr(len(protocol_name)),
         protocol_name,
         '\x00\x00\x00\x00\x000\x00\x00',
         self._swarm.get_info_hash(),
         self._swarm.get_peer_id())))

    def write_extend_message(self, metadata_message_id, payload):
        if DEBUG:
            print >> sys.stderr, self._address, 'MiniBitTorrent.write_extend_message()'
        payload = bencode(payload)
        self._socket.write(''.join((tobinary(2 + len(payload)),
         EXTEND,
         metadata_message_id,
         payload)))

    def read_header_len(self, s):
        if ord(s) != len(protocol_name):
            return None
        return (len(protocol_name), self.read_header)

    def read_header(self, s):
        if s != protocol_name:
            return None
        return (8, self.read_reserved)

    def read_reserved(self, s):
        if ord(s[5]) & 16:
            if DEBUG:
                print >> sys.stderr, self._address, 'MiniBitTorrent.read_reserved() extend module is supported'
            self.write_extend_message(UT_EXTEND_HANDSHAKE, {'m': {'ut_pex': ord(UT_PEX_ID),
                   'ut_metadata': ord(UT_METADATA_ID),
                   'metadata_size': self._swarm.get_metadata_size()}})
            return (20, self.read_download_id)
        else:
            if DEBUG:
                print >> sys.stderr, self._address, 'MiniBitTorrent.read_reserved() extend module not supported'
            return None

    def read_download_id(self, s):
        if s != self._swarm.get_info_hash():
            if DEBUG:
                print >> sys.stderr, self._address, 'MiniBitTorrent.read_download_id() invalid info hash'
            return None
        return (20, self.read_peer_id)

    def read_peer_id(self, s):
        self._swarm.add_good_peer(self._address)
        return (4, self.read_len)

    def read_len(self, s):
        l = toint(s)
        return (l, self.read_message)

    def read_message(self, s):
        if s != '':
            if not self.got_message(s):
                return None
        return (4, self.read_len)

    def got_message(self, data):
        if data[0] == EXTEND and len(data) > 2:
            self._last_activity = time()
            return self.got_extend_message(data)
        return True

    def _request_some_metadata_piece(self):
        if not self._closed:
            piece, length = self._swarm.reserve_metadata_piece()
            if isinstance(piece, (int, long)):
                if DEBUG:
                    print >> sys.stderr, self._address, 'MiniBitTorrent.got_extend_message() Requesting metadata piece', piece
                self._metadata_requests[piece] = length
                self.write_extend_message(self._her_ut_metadata_id, {'msg_type': 0,
                 'piece': piece})
            else:
                self._swarm._raw_server.add_task(self._request_some_metadata_piece, 1)

    def got_extend_message(self, data):
        try:
            message = bdecode(data[2:], sloppy=True)
            if DEBUG:
                print >> sys.stderr, self._address, 'MiniBitTorrent.got_extend_message()', len(message), 'bytes as payload'
        except:
            if DEBUG:
                print >> sys.stderr, self._address, 'MiniBitTorrent.got_extend_message() Received invalid UT_METADATA message'
            return False

        if data[1] == UT_EXTEND_HANDSHAKE:
            if 'metadata_size' in message and isinstance(message['metadata_size'], int) and message['metadata_size'] > 0:
                self._swarm.add_metadata_size_opinion(message['metadata_size'])
            if 'm' in message and isinstance(message['m'], dict) and 'ut_metadata' in message['m'] and isinstance(message['m']['ut_metadata'], int):
                self._her_ut_metadata_id = chr(message['m']['ut_metadata'])
                self._request_some_metadata_piece()
            elif not ('m' in message and isinstance(message['m'], dict) and 'ut_pex' in message['m']):
                return False
        elif data[1] == UT_PEX_ID:
            if 'added' in message and isinstance(message['added'], str) and len(message['added']) % 6 == 0:
                added = message['added']
                addresses = []
                for offset in xrange(0, len(added), 6):
                    address = ('%s.%s.%s.%s' % (ord(added[offset]),
                      ord(added[offset + 1]),
                      ord(added[offset + 2]),
                      ord(added[offset + 3])), ord(added[offset + 4]) << 8 | ord(added[offset + 5]))
                    addresses.append(address)

                if DEBUG:
                    print >> sys.stderr, self._address, 'MiniBitTorrent.got_extend_message()', len(addresses), 'peers from PEX'
                self._swarm.add_potential_peers(addresses)
                if self._her_ut_metadata_id == chr(0):
                    return False
        elif data[1] == UT_METADATA_ID:
            if 'msg_type' in message:
                if message['msg_type'] == 0 and 'piece' in message and isinstance(message['piece'], int):
                    if DEBUG:
                        print >> sys.stderr, self._address, 'MiniBitTorrent.got_extend_message() Rejecting request for piece', message['piece']
                    self.write_extend_message(self._her_ut_metadata_id, {'msg_type': 2,
                     'piece': message['piece']})
                elif message['msg_type'] == 1:
                    if not ('piece' in message and isinstance(message['piece'], (int, long)) and message['piece'] in self._metadata_requests):
                        if DEBUG:
                            print >> sys.stderr, self._address, 'MiniBitTorrent.got_extend_message() No or invalid piece number', message.get('piece', -1), '?', message.get('piece', -1) in self._metadata_requests
                        return False
                    if DEBUG:
                        print >> sys.stderr, self._address, 'MiniBitTorrent.got_extend_message() Received metadata piece', message['piece']
                    length = self._metadata_requests[message['piece']]
                    self._swarm.add_metadata_piece(message['piece'], data[-length:])
                    del self._metadata_requests[message['piece']]
                    self._request_some_metadata_piece()
                elif message['msg_type'] == 2 and 'piece' in message and isinstance(message['piece'], int) and message['piece'] in self._metadata_requests:
                    if DEBUG:
                        print >> sys.stderr, self._address, 'MiniBitTorrent.got_extend_message() Our request for', message['piece'], 'was rejected'
                    del self._metadata_requests[message['piece']]
                    self._swarm.unreserve_metadata_piece(message['piece'])
                    self._swarm._raw_server.add_task(self._request_some_metadata_piece, 5)
                else:
                    if DEBUG:
                        print >> sys.stderr, self._address, 'MiniBitTorrent.got_extend_message() Received unknown message'
                    return False
            else:
                if DEBUG:
                    print >> sys.stderr, self._address, 'MiniBitTorrent.got_extend_message() Received invalid extend message (no msg_type)'
                return False
        else:
            if DEBUG:
                print >> sys.stderr, self._address, 'MiniBitTorrent.got_extend_message() Received unknown extend message'
            return False
        return True

    def data_came_in(self, socket, data):
        while not self._closed:
            left = self._next_len - self._in_buffer.tell()
            if left > len(data):
                self._in_buffer.write(data)
                return
            self._in_buffer.write(data[:left])
            data = data[left:]
            message = self._in_buffer.getvalue()
            self._in_buffer.reset()
            self._in_buffer.truncate()
            next_ = self._next_func(message)
            if next_ is None:
                self.close()
                return
            self._next_len, self._next_func = next_

    def connection_lost(self, socket):
        if DEBUG:
            print >> sys.stderr, self._address, 'MiniBitTorrent.connection_lost()'
        if not self._closed:
            self._closed = True
            self._swarm.connection_lost(self)

    def connection_flushed(self, socket):
        pass

    def check_for_timeout(self, deadline):
        if self._last_activity < deadline:
            if DEBUG:
                print >> sys.stderr, self._address, 'MiniBitTorrent.check_for_timeout() Timeout!'
            self.close()

    def close(self):
        if DEBUG:
            print >> sys.stderr, self._address, 'MiniBitTorrent.close()'
        if not self._closed:
            self.connection_lost(self._socket)
            self._socket.close()

    def __str__(self):
        return 'MiniBitTorrentCON' + str(self._closed) + str(self._socket.connected) + str(self._swarm._info_hash)


class MiniSwarm():

    def __init__(self, info_hash, raw_server, callback):
        self._info_hash = info_hash
        self._raw_server = raw_server
        self._callback = callback
        self._peer_id = '-ST0100-' + ''.join([ chr(getrandbits(8)) for _ in range(12) ])
        self._lock = Lock()
        self._connections = []
        self._metadata_blocks = []
        self._metadata_size = 0
        self._metadata_size_opinions = {}
        self._potential_peers = {}
        self._good_peers = {}
        self._closed = False
        self._raw_server.add_task(self._timeout_connections, 5)

    def add_good_peer(self, address):
        self._good_peers[address] = time()

    def get_info_hash(self):
        return self._info_hash

    def get_peer_id(self):
        return self._peer_id

    def get_metadata_size(self):
        return self._metadata_size

    def add_metadata_size_opinion(self, metadata_size):
        if metadata_size in self._metadata_size_opinions:
            self._metadata_size_opinions[metadata_size] += 1
        else:
            self._metadata_size_opinions[metadata_size] = 1
        if len(self._metadata_size_opinions) == 1:
            metadata_size = self._metadata_size_opinions.keys()[0]
            if DEBUG:
                print >> sys.stderr, 'MiniBitTorrent.add_metadata_size_opinion() Metadata size is:', metadata_size, '(%d unanimous vote)' % sum(self._metadata_size_opinions.values())
        else:
            options = [ (weight, metadata_size) for metadata_size, weight in self._metadata_size_opinions.iteritems() ]
            options.sort(reverse=True)
            if DEBUG:
                print >> sys.stderr, 'MiniBitTorrent.add_metadata_size_opinion() Choosing metadata size from multiple options:', options
            metadata_size = options[0][1]
        if self._metadata_size != metadata_size:
            self._metadata_size = metadata_size
            pieces = metadata_size / METADATA_PIECE_SIZE
            if metadata_size % METADATA_PIECE_SIZE != 0:
                pieces += 1
            if len(self._metadata_blocks) > pieces:
                if DEBUG:
                    print >> sys.stderr, 'MiniBitTorrent.add_metadata_size_opinion() removing some blocks...'
                self._metadata_blocks = [ block_tuple for block_tuple in self._metadata_blocks if block_tuple[1] < pieces ]
            elif len(self._metadata_blocks) < pieces:
                blocks = [ [0, piece, None] for piece in xrange(len(self._metadata_blocks), pieces) ]
                if DEBUG:
                    print >> sys.stderr, 'MiniBitTorrent.add_metadata_size_opinion() adding', len(blocks), 'blocks...'
                self._metadata_blocks.extend(blocks)

    def reserve_metadata_piece(self):
        for block_tuple in self._metadata_blocks:
            if block_tuple[2] is None:
                block_tuple[0] += 1
                self._metadata_blocks.sort()
                if block_tuple[1] < len(self._metadata_blocks) - 1:
                    length = METADATA_PIECE_SIZE
                else:
                    length = self._metadata_size % METADATA_PIECE_SIZE
                return (block_tuple[1], length)

        return (None, None)

    def unreserve_metadata_piece(self, piece):
        for index, block_tuple in zip(xrange(len(self._metadata_blocks)), self._metadata_blocks):
            if block_tuple[1] == piece:
                block_tuple[0] = max(0, block_tuple[0] - 1)
                self._metadata_blocks.sort()
                break

    def add_metadata_piece(self, piece, data):
        if not self._closed:
            for index, block_tuple in zip(xrange(len(self._metadata_blocks)), self._metadata_blocks):
                if block_tuple[1] == piece:
                    block_tuple[0] = max(0, block_tuple[0] - 1)
                    block_tuple[2] = data
                    self._metadata_blocks.sort()
                    break

            for requested, piece, data in self._metadata_blocks:
                if data is None:
                    break
            else:
                metadata_blocks = [ (piece, data) for _, piece, data in self._metadata_blocks ]
                metadata_blocks.sort()
                metadata = ''.join([ data for _, data in metadata_blocks ])
                info_hash = sha(metadata).digest()
                if info_hash == self._info_hash:
                    if DEBUG:
                        print >> sys.stderr, 'MiniBitTorrent.add_metadata_piece() Done!'
                    peers = [ (timestamp, address) for address, timestamp in self._good_peers.iteritems() ]
                    peers.sort(reverse=True)
                    peers = [ address for _, address in peers ]
                    self._callback(bdecode(metadata), peers)
                else:
                    if DEBUG:
                        print >> sys.stderr, 'MiniBitTorrent.add_metadata_piece() Failed hashcheck! Restarting all over again :('
                    self._metadata_blocks = [ [requested, piece, None] for requested, piece, data in self._metadata_blocks ]

    def add_potential_peers(self, addresses):
        if not self._closed:
            self._lock.acquire()
            try:
                for address in addresses:
                    if address not in self._potential_peers:
                        self._potential_peers[address] = 0

            finally:
                self._lock.release()

            if len(self._connections) < MAX_CONNECTIONS:
                self._create_connections()

    def _create_connections(self):
        now = time()
        self._lock.acquire()
        try:
            addresses = [ (timestamp, address) for address, timestamp in self._potential_peers.iteritems() if timestamp + 60 < now ]
            if DEBUG:
                print >> sys.stderr, len(self._connections), '/', len(self._potential_peers), '->', len(addresses)
        finally:
            self._lock.release()

        addresses.sort()
        for timestamp, address in addresses:
            if len(self._connections) >= MAX_CONNECTIONS:
                break
            already_on_this_address = False
            for connection in self._connections:
                if connection.address == address:
                    already_on_this_address = True
                    break

            if already_on_this_address:
                continue
            try:
                connection = Connection(self, self._raw_server, address)
            except:
                connection = None
                if DEBUG:
                    print >> sys.stderr, 'MiniBitTorrent.add_potential_peers() ERROR'
                print_exc()

            self._lock.acquire()
            try:
                self._potential_peers[address] = now
                if connection:
                    self._connections.append(connection)
            finally:
                self._lock.release()

    def _timeout_connections(self):
        deadline = time() - MAX_TIME_INACTIVE
        for connection in self._connections:
            connection.check_for_timeout(deadline)

        if not self._closed:
            self._raw_server.add_task(self._timeout_connections, 1)

    def connection_lost(self, connection):
        try:
            self._connections.remove(connection)
        except:
            pass

        if not self._closed:
            self._create_connections()

    def close(self):
        if not self._closed:
            self._closed = True
            for connection in self._connections:
                connection.close()


class MiniTracker(Thread):

    def __init__(self, swarm, tracker):
        Thread.__init__(self)
        self._swarm = swarm
        self._tracker = tracker
        self.start()

    def run(self):
        announce = self._tracker + '?' + urlencode({'info_hash': self._swarm.get_info_hash(),
         'peer_id': self._swarm.get_peer_id(),
         'port': '12345',
         'compact': '1',
         'uploaded': '0',
         'downloaded': '0',
         'left': '-1',
         'event': 'started'})
        handle = urlopen(announce)
        if handle:
            body = handle.read()
            if body:
                try:
                    body = bdecode(body)
                except:
                    pass
                else:
                    peers = []
                    peer_data = body['peers']
                    for x in range(0, len(peer_data), 6):
                        key = peer_data[x:x + 6]
                        ip = '.'.join([ str(ord(i)) for i in peer_data[x:x + 4] ])
                        port = ord(peer_data[x + 4]) << 8 | ord(peer_data[x + 5])
                        peers.append((ip, port))

                    if DEBUG:
                        print >> sys.stderr, 'MiniTracker.run() received', len(peers), 'peer addresses from tracker'
                    self._swarm.add_potential_peers(peers)
