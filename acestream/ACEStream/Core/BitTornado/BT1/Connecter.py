#Embedded file name: ACEStream\Core\BitTornado\BT1\Connecter.pyo
import time
import sys
from types import DictType, IntType, LongType, ListType, StringType
from random import shuffle
from traceback import print_stack
from math import ceil
import socket
import urlparse
from ACEStream.Core.simpledefs import *
from ACEStream.GlobalConfig import globalConfig
from ACEStream.Core.BitTornado.bitfield import Bitfield
from ACEStream.Core.BitTornado.clock import clock
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
from ACEStream.Core.BitTornado.__init__ import version_short, decodePeerID, TRIBLER_PEERID_LETTER
from ACEStream.Core.BitTornado.BT1.convert import tobinary, toint
from ACEStream.Core.BitTornado.BT1.MessageID import *
from ACEStream.Core.DecentralizedTracking.MagnetLink.__init__ import *
from ACEStream.Core.DecentralizedTracking.ut_pex import *
from ACEStream.Core.BitTornado.BT1.track import compact_ip, decompact_ip
from ACEStream.Core.BitTornado.CurrentRateMeasure import Measure
from ACEStream.Core.ClosedSwarm import ClosedSwarm
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False
DEBUG_NORMAL_MSGS = False
DEBUG_UT_PEX = False
DEBUG_MESSAGE_HANDLING = False
DEBUG_CS = False
UNAUTH_PERMID_PERIOD = 3600
UT_METADATA_FLOOD_FACTOR = 1
UT_METADATA_FLOOD_PERIOD = 5 * 60 * 60
EXTEND_MSG_HANDSHAKE_ID = chr(0)
EXTEND_MSG_OVERLAYSWARM = 'Tr_OVERLAYSWARM'
EXTEND_MSG_G2G_V1 = 'Tr_G2G'
EXTEND_MSG_G2G_V2 = 'Tr_G2G_v2'
EXTEND_MSG_HASHPIECE = 'Tr_hashpiece'
EXTEND_MSG_CS = 'NS_CS'
EXTEND_MSG_INVALIDATE = 'Ts_INVALIDATE'
CURRENT_LIVE_VERSION = 1
EXTEND_MSG_LIVE_PREFIX = 'Tr_LIVE_v'
LIVE_FAKE_MESSAGE_ID = chr(254)
G2G_CALLBACK_INTERVAL = 4

def show(s):
    text = []
    for i in xrange(len(s)):
        text.append(ord(s[i]))

    return text


class Connection():

    def __init__(self, connection, connecter):
        self.connection = connection
        self.connecter = connecter
        self.got_anything = False
        self.next_upload = None
        self.outqueue = []
        self.partial_message = None
        self.download = None
        self.upload = None
        self.send_choke_queued = False
        self.just_unchoked = None
        self.unauth_permid = None
        self.looked_for_permid = UNAUTH_PERMID_PERIOD - 3
        self.closed = False
        self.extend_hs_dict = {}
        self.initiated_overlay = False
        self.extended_version = None
        self.last_requested_piece = None
        self.last_received_piece = None
        self.support_piece_invalidate = False
        self.use_g2g = False
        self.g2g_version = None
        self.perc_sent = {}
        self.last_perc_sent = {}
        config = self.connecter.config
        self.forward_speeds = [Measure(config['max_rate_period'], config['upload_rate_fudge']), Measure(config['max_rate_period'], config['upload_rate_fudge'])]
        self.total_downloaded = 0
        self.total_uploaded = 0
        self.ut_pex_first_flag = True
        self.na_candidate_ext_ip = None
        self.na_candidate_ext_ip = None
        self.pex_received = 0
        self.is_closed_swarm = False
        self.cs_complete = False
        self.remote_is_authenticated = False
        self.remote_supports_cs = False
        if not self.connecter.is_closed_swarm:
            self.cs_complete = True
        if self.connecter.is_closed_swarm:
            if DEBUG_CS:
                print >> sys.stderr, 'connecter: conn: CS: This is a closed swarm'
            self.is_closed_swarm = True
            if 'poa' in self.connecter.config:
                try:
                    from base64 import decodestring
                    poa = ClosedSwarm.POA.deserialize(decodestring(self.connecter.config['poa']))
                except Exception as e:
                    log_exc()
                    poa = None

            else:
                print >> sys.stderr, 'connecter: conn: CS: Missing POA'
                poa = None
            my_keypair = ClosedSwarm.read_cs_keypair(self.connecter.config['eckeypairfilename'])
            self.closed_swarm_protocol = ClosedSwarm.ClosedSwarm(my_keypair, self.connecter.infohash, self.connecter.config['cs_keys'], poa)
            if DEBUG_CS:
                print >> sys.stderr, 'connecter: conn: CS: Closed swarm ready to start handshake'

    def get_myip(self, real = False):
        return self.connection.get_myip(real)

    def get_myport(self, real = False):
        return self.connection.get_myport(real)

    def get_ip(self, real = False):
        return self.connection.get_ip(real)

    def get_port(self, real = False):
        return self.connection.get_port(real)

    def get_id(self):
        return self.connection.get_id()

    def get_readable_id(self):
        return self.connection.get_readable_id()

    def can_send_to(self):
        if self.is_closed_swarm and not self.remote_is_authenticated:
            return False
        return True

    def close(self):
        self.connection.close()
        self.closed = True

    def is_closed(self):
        return self.closed

    def is_locally_initiated(self):
        return self.connection.is_locally_initiated()

    def send_interested(self):
        self._send_message(INTERESTED)

    def send_not_interested(self):
        self._send_message(NOT_INTERESTED)

    def send_choke(self):
        if self.partial_message:
            self.send_choke_queued = True
        else:
            self._send_message(CHOKE)
            self.upload.choke_sent()
            self.just_unchoked = 0

    def send_unchoke(self):
        if not self.cs_complete:
            if DEBUG_CS:
                print >> sys.stderr, 'Connection: send_unchoke: Not sending UNCHOKE, closed swarm handshanke not done'
            return False
        if self.send_choke_queued:
            self.send_choke_queued = False
            if DEBUG_NORMAL_MSGS:
                print >> sys.stderr, 'Connection: send_unchoke: CHOKE SUPPRESSED'
        else:
            self._send_message(UNCHOKE)
            if self.partial_message or self.just_unchoked is None or not self.upload.interested or self.download.active_requests:
                self.just_unchoked = 0
            else:
                self.just_unchoked = clock()
        return True

    def send_request(self, index, begin, length):
        self.last_requested_piece = index
        self._send_message(REQUEST + tobinary(index) + tobinary(begin) + tobinary(length))
        if DEBUG_NORMAL_MSGS:
            print >> sys.stderr, 'sending REQUEST to', self.get_ip()
            print >> sys.stderr, 'sent request: ' + str(index) + ': ' + str(begin) + '-' + str(begin + length)

    def send_cancel(self, index, begin, length):
        self._send_message(CANCEL + tobinary(index) + tobinary(begin) + tobinary(length))
        if DEBUG_NORMAL_MSGS:
            print >> sys.stderr, 'sent cancel: ' + str(index) + ': ' + str(begin) + '-' + str(begin + length)

    def send_bitfield(self, bitfield):
        if not self.cs_complete:
            print >> sys.stderr, 'Connection: send_bitfield: Not sending bitfield - CS handshake not done'
            return
        if self.can_send_to():
            self._send_message(BITFIELD + bitfield)
        else:
            print >> sys.stderr, 'Connection: send_bitfield: Sending empty bitfield to unauth node'
            self._send_message(BITFIELD + Bitfield(self.connecter.numpieces).tostring())

    def send_have(self, index):
        if self.can_send_to():
            self._send_message(HAVE + tobinary(index))

    def send_keepalive(self):
        self._send_message('')

    def _send_message(self, s):
        s = tobinary(len(s)) + s
        if self.partial_message:
            self.outqueue.append(s)
        else:
            self.connection.send_message_raw(s)

    def send_partial(self, bytes):
        if self.connection.closed:
            return 0
        if not self.can_send_to():
            return 0
        if self.partial_message is None:
            s = self.upload.get_upload_chunk()
            if s is None:
                return 0
            index, begin, hashlist, piece = s
            if self.use_g2g:
                self.g2g_sent_piece_part(self, index, begin, hashlist, piece)
                for c in self.connecter.connections.itervalues():
                    if not c.use_g2g:
                        continue
                    c.queue_g2g_piece_xfer(index, begin, piece)

            if self.connecter.merkle_torrent:
                hashpiece_msg_id = self.his_extend_msg_name_to_id(EXTEND_MSG_HASHPIECE)
                bhashlist = bencode(hashlist)
                if hashpiece_msg_id is None:
                    self.partial_message = ''.join((tobinary(13 + len(bhashlist) + len(piece)),
                     HASHPIECE,
                     tobinary(index),
                     tobinary(begin),
                     tobinary(len(bhashlist)),
                     bhashlist,
                     piece.tostring()))
                else:
                    self.partial_message = ''.join((tobinary(14 + len(bhashlist) + len(piece)),
                     EXTEND,
                     hashpiece_msg_id,
                     tobinary(index),
                     tobinary(begin),
                     tobinary(len(bhashlist)),
                     bhashlist,
                     piece.tostring()))
            else:
                self.partial_message = ''.join((tobinary(len(piece) + 9),
                 PIECE,
                 tobinary(index),
                 tobinary(begin),
                 piece.tostring()))
            if DEBUG_NORMAL_MSGS:
                print >> sys.stderr, 'sending chunk: ' + str(index) + ': ' + str(begin) + '-' + str(begin + len(piece))
        if bytes < len(self.partial_message):
            self.connection.send_message_raw(self.partial_message[:bytes])
            self.partial_message = self.partial_message[bytes:]
            return bytes
        q = [self.partial_message]
        self.partial_message = None
        if self.send_choke_queued:
            self.send_choke_queued = False
            self.outqueue.append(tobinary(1) + CHOKE)
            self.upload.choke_sent()
            self.just_unchoked = 0
        q.extend(self.outqueue)
        self.outqueue = []
        q = ''.join(q)
        self.connection.send_message_raw(q)
        return len(q)

    def get_upload(self):
        return self.upload

    def get_download(self):
        return self.download

    def set_download(self, download):
        self.download = download

    def backlogged(self):
        return not self.connection.is_flushed()

    def got_request(self, i, p, l):
        self.upload.got_request(i, p, l)
        if self.just_unchoked:
            self.connecter.ratelimiter.ping(clock() - self.just_unchoked)
            self.just_unchoked = 0

    def supports_extend_msg(self, msg_name):
        if 'm' in self.extend_hs_dict:
            return msg_name in self.extend_hs_dict['m']
        else:
            return False

    def got_extend_handshake(self, d):
        if DEBUG:
            print >> sys.stderr, 'connecter: Got EXTEND handshake:', d
        if 'm' in d:
            if type(d['m']) != DictType:
                raise ValueError('Key m does not map to a dict')
            m = d['m']
            newm = {}
            for key, val in m.iteritems():
                if type(val) != IntType:
                    if type(val) == StringType:
                        newm[key] = ord(val)
                        continue
                    else:
                        raise ValueError('Message ID in m-dict not int')
                newm[key] = val

            if 'm' not in self.extend_hs_dict:
                self.extend_hs_dict['m'] = {}
            self.extend_hs_dict['m'].update(newm)
            if self.connecter.overlay_enabled and EXTEND_MSG_OVERLAYSWARM in self.extend_hs_dict['m']:
                if self.connection.locally_initiated:
                    if DEBUG:
                        print >> sys.stderr, 'connecter: Peer supports Tr_OVERLAYSWARM, attempt connection'
                    self.connect_overlay()
            if EXTEND_MSG_CS in self.extend_hs_dict['m']:
                self.remote_supports_cs = True
                if DEBUG_CS:
                    print >> sys.stderr, 'connecter: Peer supports Closed swarms'
                if self.is_closed_swarm and self.connection.locally_initiated:
                    if DEBUG_CS:
                        print >> sys.stderr, 'connecter: Initiating Closed swarm handshake'
                    self.start_cs_handshake()
            else:
                self.remote_supports_cs = False
                if DEBUG_CS:
                    print >> sys.stderr, 'connecter: conn: Remote node does not support CS, flagging CS as done'
                self.connecter.cs_handshake_completed()
            if self.connecter.use_g2g and (EXTEND_MSG_G2G_V1 in self.extend_hs_dict['m'] or EXTEND_MSG_G2G_V2 in self.extend_hs_dict['m']):
                if self.connection.locally_initiated:
                    if DEBUG:
                        print >> sys.stderr, 'connecter: Peer supports Tr_G2G'
                self.use_g2g = True
                if EXTEND_MSG_G2G_V2 in self.extend_hs_dict['m']:
                    self.g2g_version = EXTEND_MSG_G2G_V2
                else:
                    self.g2g_version = EXTEND_MSG_G2G_V1
        for key in ['p',
         'e',
         'yourip',
         'ipv4',
         'ipv6',
         'reqq']:
            if key in d:
                self.extend_hs_dict[key] = d[key]

        if 'yourip' in d:
            try:
                yourip = decompact_ip(d['yourip'])
                try:
                    from ACEStream.Core.NATFirewall.DialbackMsgHandler import DialbackMsgHandler
                    dmh = DialbackMsgHandler.getInstance()
                    dmh.network_btengine_extend_yourip(yourip)
                except:
                    if DEBUG:
                        log_exc()

                if 'same_nat_try_internal' in self.connecter.config and self.connecter.config['same_nat_try_internal']:
                    if 'ipv4' in d:
                        self.na_check_for_same_nat(yourip)
            except:
                log_exc()

        self.extended_version = d.get('v', None)
        repexer = self.connecter.repexer
        if repexer:
            try:
                repexer.got_extend_handshake(self, self.extended_version)
            except:
                log_exc()

    def supports_piece_invalidate(self):
        return self.support_piece_invalidate

    def his_extend_msg_name_to_id(self, ext_name):
        val = self.extend_hs_dict['m'].get(ext_name)
        if val is None:
            return val
        else:
            return chr(val)

    def get_extend_encryption(self):
        return self.extend_hs_dict.get('e', 0)

    def get_extend_listenport(self):
        return self.extend_hs_dict.get('p')

    def is_tribler_peer(self):
        client, version = decodePeerID(self.connection.id)
        return client == TRIBLER_PEERID_LETTER

    def send_extend_handshake(self):
        hisip = self.connection.get_ip(real=True)
        ipv4 = None
        if self.connecter.config.get('same_nat_try_internal', 0):
            is_tribler_peer = self.is_tribler_peer()
            print >> sys.stderr, 'connecter: send_extend_hs: Peer is ACEStream client', is_tribler_peer
            if is_tribler_peer:
                ipv4 = self.get_ip(real=True)
        d = {}
        d['m'] = self.connecter.EXTEND_HANDSHAKE_M_DICT
        d['p'] = self.connecter.mylistenport
        ver = version_short.replace('-', ' ', 1)
        d['v'] = ver
        d['e'] = 0
        cip = compact_ip(hisip)
        if cip is not None:
            d['yourip'] = cip
        if ipv4 is not None:
            cip = compact_ip(ipv4)
            if cip is not None:
                d['ipv4'] = cip
        if self.connecter.ut_metadata_enabled:
            d['metadata_size'] = self.connecter.ut_metadata_size
        self._send_message(EXTEND + EXTEND_MSG_HANDSHAKE_ID + bencode(d))
        if DEBUG:
            print >> sys.stderr, 'connecter: sent extend: id=0+', d, 'yourip', hisip, 'ipv4', ipv4

    def got_ut_pex(self, d):
        if DEBUG_UT_PEX:
            print >> sys.stderr, 'connecter: Got uTorrent PEX:', d
        same_added_peers, added_peers, dropped_peers = check_ut_pex(d)
        self.pex_received += 1
        repexer = self.connecter.repexer
        if repexer:
            try:
                repexer.got_ut_pex(self, d)
            except:
                log_exc()

            return
        mx = self.connecter.ut_pex_max_addrs_from_peer
        if DEBUG_UT_PEX:
            print >> sys.stderr, 'connecter: Got', len(added_peers) + len(same_added_peers), 'peers via uTorrent PEX, using max', mx
        if self.is_tribler_peer():
            shuffle(same_added_peers)
            shuffle(added_peers)
            sample_peers = same_added_peers
            sample_peers.extend(added_peers)
        else:
            sample_peers = same_added_peers
            sample_peers.extend(added_peers)
            shuffle(sample_peers)
        sample_added_peers_with_id = []
        for dns in sample_peers[:mx]:
            peer_with_id = (dns, 0)
            sample_added_peers_with_id.append(peer_with_id)

        if len(sample_added_peers_with_id) > 0:
            if DEBUG_UT_PEX:
                print >> sys.stderr, 'connecter: Starting ut_pex conns to', len(sample_added_peers_with_id)
            self.connection.Encoder.start_connections(sample_added_peers_with_id)

    def try_send_pex(self, currconns = [], addedconns = [], droppedconns = []):
        if self.supports_extend_msg(EXTEND_MSG_UTORRENT_PEX):
            try:
                if DEBUG_UT_PEX:
                    print >> sys.stderr, 'connecter: ut_pex: Creating msg for', self.get_ip(), self.get_extend_listenport()
                if self.first_ut_pex():
                    aconns = currconns
                    dconns = []
                else:
                    aconns = addedconns
                    dconns = droppedconns
                payload = create_ut_pex(aconns, dconns, self)
                self.send_extend_ut_pex(payload)
            except:
                log_exc()

    def send_extend_ut_pex(self, payload):
        msg = EXTEND + self.his_extend_msg_name_to_id(EXTEND_MSG_UTORRENT_PEX) + payload
        self._send_message(msg)

    def first_ut_pex(self):
        if self.ut_pex_first_flag:
            self.ut_pex_first_flag = False
            return True
        else:
            return False

    def send_invalidate(self, index):
        if self.supports_piece_invalidate():
            payload = bencode(index)
            self._send_message(EXTEND + self.his_extend_msg_name_to_id(EXTEND_MSG_INVALIDATE) + payload)

    def _send_cs_message(self, cs_list):
        blist = bencode(cs_list)
        self._send_message(EXTEND + self.his_extend_msg_name_to_id(EXTEND_MSG_CS) + blist)

    def got_cs_message(self, cs_list):
        if not self.is_closed_swarm:
            raise Exception('Got ClosedSwarm message, but this swarm is not closed')
        t = cs_list[0]
        if t == CS_CHALLENGE_A:
            if DEBUG_CS:
                print >> sys.stderr, 'connecter: conn: CS: Got initial challenge'
            try:
                response = self.closed_swarm_protocol.b_create_challenge(cs_list)
                self._send_cs_message(response)
            except Exception as e:
                if DEBUG_CS:
                    print >> sys.stderr, 'connecter: conn: CS: Bad initial challenge:', e

        elif t == CS_CHALLENGE_B:
            if DEBUG_CS:
                print >> sys.stderr, 'connecter: conn: CS: Got return challenge'
            try:
                response = self.closed_swarm_protocol.a_provide_poa_message(cs_list)
                if DEBUG_CS and not response:
                    print >> sys.stderr, "connecter: I'm not intererested in data"
                self._send_cs_message(response)
            except Exception as e:
                if DEBUG_CS:
                    print >> sys.stderr, 'connecter: conn: CS: Bad return challenge', e
                log_exc()

        elif t == CS_POA_EXCHANGE_A:
            if DEBUG_CS:
                print >> sys.stderr, 'connecter: conn: CS:Got POA from A'
            try:
                response = self.closed_swarm_protocol.b_provide_poa_message(cs_list)
                self.remote_is_authenticated = self.closed_swarm_protocol.is_remote_node_authorized()
                if DEBUG_CS:
                    print >> sys.stderr, 'connecter: conn: CS: Remote node authorized:', self.remote_is_authenticated
                if response:
                    self._send_cs_message(response)
            except Exception as e:
                if DEBUG_CS:
                    print >> sys.stderr, 'connecter: conn: CS: Bad POA from A:', e

        elif t == CS_POA_EXCHANGE_B:
            try:
                self.closed_swarm_protocol.a_check_poa_message(cs_list)
                self.remote_is_authenticated = self.closed_swarm_protocol.is_remote_node_authorized()
                if DEBUG_CS:
                    print >> sys.stderr, 'connecter: conn: CS: Remote node authorized:', self.remote_is_authenticated
            except Exception as e:
                if DEBUG_CS:
                    print >> sys.stderr, 'connecter: conn: CS: Bad POA from B:', e

        if not self.closed_swarm_protocol.is_incomplete():
            self.connecter.cs_handshake_completed()
            self.cs_complete = True

    def g2g_sent_piece_part(self, c, index, begin, hashlist, piece):
        wegaveperc = float(len(piece)) / float(self.connecter.piece_size)
        if index in self.perc_sent:
            self.perc_sent[index] = self.perc_sent[index] + wegaveperc
        else:
            self.perc_sent[index] = wegaveperc

    def queue_g2g_piece_xfer(self, index, begin, piece):
        if self.g2g_version == EXTEND_MSG_G2G_V1:
            self.send_g2g_piece_xfer_v1(index, begin, piece)
            return
        perc = float(len(piece)) / float(self.connecter.piece_size)
        if index in self.last_perc_sent:
            self.last_perc_sent[index] = self.last_perc_sent[index] + perc
        else:
            self.last_perc_sent[index] = perc

    def dequeue_g2g_piece_xfer(self):
        psf = float(self.connecter.piece_size)
        ppdict = {}
        for index, perc in self.last_perc_sent.iteritems():
            capperc = min(1.0, perc)
            percb = chr(int(100.0 * capperc))
            ppdict[str(index)] = percb

        self.last_perc_sent = {}
        if len(ppdict) > 0:
            self.send_g2g_piece_xfer_v2(ppdict)

    def send_g2g_piece_xfer_v1(self, index, begin, piece):
        self._send_message(self.his_extend_msg_name_to_id(EXTEND_MSG_G2G_V1) + tobinary(index) + tobinary(begin) + tobinary(len(piece)))

    def send_g2g_piece_xfer_v2(self, ppdict):
        blist = bencode(ppdict)
        self._send_message(EXTEND + self.his_extend_msg_name_to_id(EXTEND_MSG_G2G_V2) + blist)

    def got_g2g_piece_xfer_v1(self, index, begin, length):
        hegaveperc = float(length) / float(self.connecter.piece_size)
        self.g2g_peer_forwarded_piece_part(index, hegaveperc)

    def got_g2g_piece_xfer_v2(self, ppdict):
        for indexstr, hegavepercb in ppdict.iteritems():
            index = int(indexstr)
            hegaveperc = float(ord(hegavepercb)) / 100.0
            self.g2g_peer_forwarded_piece_part(index, hegaveperc)

    def g2g_peer_forwarded_piece_part(self, index, hegaveperc):
        length = ceil(hegaveperc * float(self.connecter.piece_size))
        self.forward_speeds[1].update_rate(length)
        if index not in self.perc_sent:
            return
        wegaveperc = self.perc_sent[index]
        overlapperc = wegaveperc * hegaveperc
        overlap = ceil(overlapperc * float(self.connecter.piece_size))
        if overlap > 0:
            self.forward_speeds[0].update_rate(overlap)

    def g2g_score(self):
        return [ x.get_rate() for x in self.forward_speeds ]

    def connect_overlay(self):
        if DEBUG:
            print >> sys.stderr, 'connecter: Initiating overlay connection'
        if not self.initiated_overlay:
            from ACEStream.Core.Overlay.SecureOverlay import SecureOverlay
            self.initiated_overlay = True
            so = SecureOverlay.getInstance()
            so.connect_dns(self.connection.dns, self.network_connect_dns_callback)

    def network_connect_dns_callback(self, exc, dns, permid, selversion):
        if exc is not None:
            print >> sys.stderr, 'connecter: peer', dns, "said he supported overlay swarm, but we can't connect to him", exc

    def start_cs_handshake(self):
        try:
            if DEBUG_CS:
                print >> sys.stderr, 'connecter: conn: CS: Initiating Closed Swarm Handshake'
            challenge = self.closed_swarm_protocol.a_create_challenge()
            self._send_cs_message(challenge)
        except Exception as e:
            print >> sys.stderr, 'connecter: conn: CS: Bad initial challenge:', e

    def na_check_for_same_nat(self, yourip):
        hisip = self.connection.get_ip(real=True)
        if hisip == yourip:
            myextip = self.connecter.get_extip_func(unknowniflocal=True)
            myintip = self.get_ip(real=True)
            if DEBUG:
                print >> sys.stderr, 'connecter: na_check_for_same_nat: his', hisip, 'myext', myextip, 'myint', myintip
            if hisip != myintip or hisip == '127.0.0.1':
                if myextip is None:
                    if DEBUG:
                        print >> sys.stderr, "connecter: na_check_same_nat: Don't know my ext ip, try to loopback to", yourip, "to see if that's me"
                    self.na_start_loopback_connection(yourip)
                elif hisip == myextip:
                    if DEBUG:
                        print >> sys.stderr, 'connecter: na_check_same_nat: Yes, trying to connect via internal'
                    self.na_start_internal_connection()
                else:
                    if DEBUG:
                        print >> sys.stderr, 'connecter: na_check_same_nat: Maybe, me thinks not, try to loopback to', yourip
                    self.na_start_loopback_connection(yourip)

    def na_start_loopback_connection(self, yourip):
        if DEBUG:
            print >> sys.stderr, 'connecter: na_start_loopback: Checking if my ext ip is', yourip
        self.na_candidate_ext_ip = yourip
        dns = (yourip, self.connecter.mylistenport)
        self.connection.Encoder.start_connection(dns, 0, forcenew=True)

    def na_got_loopback(self, econnection):
        himismeip = econnection.get_ip(real=True)
        if DEBUG:
            print >> sys.stderr, 'connecter: conn: na_got_loopback:', himismeip, self.na_candidate_ext_ip
        if self.na_candidate_ext_ip == himismeip:
            self.na_start_internal_connection()

    def na_start_internal_connection(self):
        if DEBUG:
            print >> sys.stderr, 'connecter: na_start_internal_connection'
        if not self.is_locally_initiated():
            hisip = decompact_ip(self.extend_hs_dict['ipv4'])
            hisport = self.extend_hs_dict['p']
            if hisip == '224.4.8.1' and hisport == 4810:
                hisip = '127.0.0.1'
                hisport = 4811
            self.connection.na_want_internal_conn_from = hisip
            hisdns = (hisip, hisport)
            if DEBUG:
                print >> sys.stderr, 'connecter: na_start_internal_connection to', hisdns
            self.connection.Encoder.start_connection(hisdns, 0)

    def na_get_address_distance(self):
        return self.connection.na_get_address_distance()

    def is_live_source(self):
        if self.connecter.live_streaming:
            is_source = self.connecter.is_live_source(self.get_ip())
            return is_source
        return False

    def is_live_authorized_peer(self):
        if self.connecter.live_streaming:
            is_authorized = self.connecter.is_live_authorized_peer(self.get_ip())
            return is_authorized
        return False


class Connecter():

    def __init__(self, metadata, make_upload, downloader, choker, numpieces, piece_size, totalup, config, ratelimiter, merkle_torrent, sched = None, coordinator = None, helper = None, get_extip_func = lambda : None, mylistenport = None, use_g2g = False, infohash = None, authorized_peers = [], live_streaming = False, is_private_torrent = False):
        self.app_mode = globalConfig.get_mode()
        self.downloader = downloader
        self.make_upload = make_upload
        self.choker = choker
        self.numpieces = numpieces
        self.piece_size = piece_size
        self.config = config
        self.ratelimiter = ratelimiter
        self.rate_capped = False
        self.sched = sched
        self.totalup = totalup
        self.rate_capped = False
        self.connections = {}
        self.external_connection_made = 0
        self.merkle_torrent = merkle_torrent
        self.use_g2g = use_g2g
        self.coordinator = coordinator
        self.helper = helper
        self.round = 0
        self.get_extip_func = get_extip_func
        self.mylistenport = mylistenport
        self.infohash = infohash
        self.live_streaming = live_streaming
        self.live_source_ip = None
        self.live_authorized_peers = set()
        if self.live_streaming:
            if self.app_mode == 'node':
                source_node = globalConfig.get_value('source_node')
                if source_node is not None:
                    self.live_source_ip = source_node[0]
            for tier in authorized_peers:
                for peer in tier:
                    self.live_authorized_peers.add(peer[0])

            if DEBUG:
                log('connecter::__init__: live_source', self.live_source_ip, 'live_authorized_peers', self.live_authorized_peers)
        self.overlay_enabled = 0
        if self.config['overlay']:
            self.overlay_enabled = True
        if DEBUG:
            if self.overlay_enabled:
                print >> sys.stderr, 'connecter: Enabling overlay'
            else:
                print >> sys.stderr, 'connecter: Disabling overlay'
        self.ut_pex_enabled = 0
        if not is_private_torrent and 'ut_pex_max_addrs_from_peer' in self.config:
            self.ut_pex_max_addrs_from_peer = self.config['ut_pex_max_addrs_from_peer']
            self.ut_pex_enabled = self.ut_pex_max_addrs_from_peer > 0
        self.ut_pex_previous_conns = []
        self.ut_metadata_enabled = self.config['magnetlink']
        if self.ut_metadata_enabled:
            infodata = bencode(metadata['info'])
            self.ut_metadata_size = len(infodata)
            self.ut_metadata_list = [ infodata[index:index + 16384] for index in xrange(0, len(infodata), 16384) ]
            self.ut_metadata_history = []
            if DEBUG:
                print >> sys.stderr, 'connecter.__init__: Enable ut_metadata'
        if DEBUG_UT_PEX:
            if self.ut_pex_enabled:
                print >> sys.stderr, 'connecter: Enabling uTorrent PEX', self.ut_pex_max_addrs_from_peer
            else:
                print >> sys.stderr, 'connecter: Disabling uTorrent PEX'
        self.EXTEND_HANDSHAKE_M_DICT = {}
        if DEBUG:
            print >> sys.stderr, 'connecter: I support Closed Swarms'
        d = {EXTEND_MSG_CS: ord(CS_CHALLENGE_A)}
        self.EXTEND_HANDSHAKE_M_DICT.update(d)
        if self.overlay_enabled:
            d = {EXTEND_MSG_OVERLAYSWARM: ord(CHALLENGE)}
            self.EXTEND_HANDSHAKE_M_DICT.update(d)
        if self.ut_pex_enabled:
            d = {EXTEND_MSG_UTORRENT_PEX: ord(EXTEND_MSG_UTORRENT_PEX_ID)}
            self.EXTEND_HANDSHAKE_M_DICT.update(d)
            self.sched(self.ut_pex_callback, 6)
        if self.use_g2g:
            d = {EXTEND_MSG_G2G_V2: ord(G2G_PIECE_XFER)}
            self.EXTEND_HANDSHAKE_M_DICT.update(d)
            self.sched(self.g2g_callback, G2G_CALLBACK_INTERVAL)
        if self.merkle_torrent:
            d = {EXTEND_MSG_HASHPIECE: ord(HASHPIECE)}
            self.EXTEND_HANDSHAKE_M_DICT.update(d)
        if self.ut_metadata_enabled:
            d = {EXTEND_MSG_METADATA: ord(EXTEND_MSG_METADATA_ID)}
            self.EXTEND_HANDSHAKE_M_DICT.update(d)
        livekey = EXTEND_MSG_LIVE_PREFIX + str(CURRENT_LIVE_VERSION)
        d = {livekey: ord(LIVE_FAKE_MESSAGE_ID)}
        self.EXTEND_HANDSHAKE_M_DICT.update(d)
        if DEBUG:
            print >> sys.stderr, 'Connecter: EXTEND: my dict', self.EXTEND_HANDSHAKE_M_DICT
        if config['overlay']:
            from ACEStream.Core.Overlay.OverlayThreadingBridge import OverlayThreadingBridge
            self.overlay_bridge = OverlayThreadingBridge.getInstance()
        else:
            self.overlay_bridge = None
        self.repexer = None
        self.is_closed_swarm = False
        self.cs_post_func = None
        if 'cs_keys' in self.config:
            if self.config['cs_keys'] != None:
                if len(self.config['cs_keys']) == 0:
                    if DEBUG_CS:
                        print >> sys.stderr, 'connecter: cs_keys is empty'
                else:
                    if DEBUG_CS:
                        print >> sys.stderr, 'connecter: This is a closed swarm  - has cs_keys'
                    self.is_closed_swarm = True

    def is_live_source(self, ip):
        return ip == self.live_source_ip

    def is_live_authorized_peer(self, ip):
        return ip in self.live_authorized_peers

    def how_many_connections(self):
        return len(self.connections)

    def connection_made(self, connection):
        c = Connection(connection, self)
        self.connections[connection] = c
        repexer = self.repexer
        if repexer:
            try:
                repexer.connection_made(c, connection.supports_extend_messages())
                if c.closed:
                    return c
            except:
                log_exc()

        if connection.supports_extend_messages():
            client, version = decodePeerID(connection.id)
            if DEBUG:
                print >> sys.stderr, 'connecter: Peer is client', client, 'version', version, c.get_ip(), c.get_port()
            if self.overlay_enabled and client == TRIBLER_PEERID_LETTER and version <= '3.5.0' and connection.locally_initiated:
                if DEBUG:
                    print >> sys.stderr, 'connecter: Peer is previous ACEStream version, attempt overlay connection'
                c.connect_overlay()
            elif self.ut_pex_enabled:
                c.send_extend_handshake()
        c.upload = self.make_upload(c, self.ratelimiter, self.totalup)
        c.download = self.downloader.make_download(c)
        if not self.is_closed_swarm:
            if DEBUG_CS:
                print >> sys.stderr, 'connecter: connection_made: Freeing choker!'
            self.choker.connection_made(c)
        else:
            if DEBUG_CS:
                print >> sys.stderr, 'connecter: connection_made: Will free choker later'
            self.choker.add_connection(c)
            self.cs_post_func = lambda : self._cs_completed(c)
        return c

    def connection_lost(self, connection):
        c = self.connections[connection]
        repexer = self.repexer
        if repexer:
            try:
                repexer.connection_closed(c)
            except:
                log_exc()

        if self.overlay_bridge is not None:
            ip = c.get_ip(False)
            port = c.get_port(False)
            down_kb = int(c.total_downloaded / 1024)
            up_kb = int(c.total_uploaded / 1024)
            if DEBUG:
                print >> sys.stderr, 'bartercast: attempting database update, adding olthread'
            olthread_bartercast_conn_lost_lambda = lambda : olthread_bartercast_conn_lost(ip, port, down_kb, up_kb)
            self.overlay_bridge.add_task(olthread_bartercast_conn_lost_lambda, 0)
        del self.connections[connection]
        if c.download:
            c.download.disconnected()
        self.choker.connection_lost(c)

    def connection_flushed(self, connection):
        conn = self.connections[connection]
        if conn.next_upload is None and (conn.partial_message is not None or conn.upload.buffer):
            self.ratelimiter.queue(conn)

    def got_piece(self, i, invalidate_piece = None):
        for co in self.connections.values():
            co.send_have(i)

    def our_extend_msg_id_to_name(self, ext_id):
        for key, val in self.EXTEND_HANDSHAKE_M_DICT.iteritems():
            if val == ord(ext_id):
                return key

    def get_ut_pex_conns(self):
        conns = []
        for conn in self.connections.values():
            if conn.get_extend_listenport() is not None:
                conns.append(conn)

        return conns

    def get_ut_pex_previous_conns(self):
        return self.ut_pex_previous_conns

    def set_ut_pex_previous_conns(self, conns):
        self.ut_pex_previous_conns = conns

    def ut_pex_callback(self):
        proxy_mode = self.config.get('proxy_mode', 0)
        if proxy_mode == PROXY_MODE_PRIVATE:
            if DEBUG_UT_PEX:
                print >> sys.stderr, 'connecter: Private Mode - Returned from ut_pex_callback'
            return
        if DEBUG_UT_PEX:
            print >> sys.stderr, 'connecter: Periodic ut_pex update'
        currconns = self.get_ut_pex_conns()
        addedconns, droppedconns = ut_pex_get_conns_diff(currconns, self.get_ut_pex_previous_conns())
        self.set_ut_pex_previous_conns(currconns)
        if DEBUG_UT_PEX:
            for conn in addedconns:
                print >> sys.stderr, 'connecter: ut_pex: Added', conn.get_ip(), conn.get_extend_listenport()

            for conn in droppedconns:
                print >> sys.stderr, 'connecter: ut_pex: Dropped', conn.get_ip(), conn.get_extend_listenport()

        for c in currconns:
            c.try_send_pex(currconns, addedconns, droppedconns)

        self.sched(self.ut_pex_callback, 60)

    def g2g_callback(self):
        try:
            self.sched(self.g2g_callback, G2G_CALLBACK_INTERVAL)
            for c in self.connections.itervalues():
                if not c.use_g2g:
                    continue
                c.dequeue_g2g_piece_xfer()

        except:
            log_exc()

    def got_ut_metadata(self, connection, dic, message):
        if DEBUG:
            print >> sys.stderr, 'connecter.got_ut_metadata:', dic
        msg_type = dic.get('msg_type', None)
        if type(msg_type) not in (int, long):
            raise ValueError('Invalid ut_metadata.msg_type')
        piece = dic.get('piece', None)
        if type(piece) not in (int, long):
            raise ValueError('Invalid ut_metadata.piece type')
        if not 0 <= piece < len(self.ut_metadata_list):
            raise ValueError('Invalid ut_metadata.piece value')
        if msg_type == 0:
            if DEBUG:
                print >> sys.stderr, 'connecter.got_ut_metadata: Received request for piece', piece
            now = time.time()
            deadline = now - UT_METADATA_FLOOD_PERIOD
            self.ut_metadata_history = [ timestamp for timestamp in self.ut_metadata_history if timestamp > deadline ]
            if len(self.ut_metadata_history) > UT_METADATA_FLOOD_FACTOR * len(self.ut_metadata_list):
                reply = bencode({'msg_type': 2,
                 'piece': piece})
            else:
                reply = bencode({'msg_type': 1,
                 'piece': piece,
                 'data': self.ut_metadata_list[piece]})
                self.ut_metadata_history.append(now)
            connection._send_message(EXTEND + connection.his_extend_msg_name_to_id(EXTEND_MSG_METADATA) + reply)
        elif msg_type == 1:
            raise ValueError('Invalid ut_metadata: we did not request data')
        elif msg_type == 2:
            raise ValueError('Invalid ut_metadata: we did not request data that can be rejected')
        else:
            raise ValueError('Invalid ut_metadata.msg_type value')

    def got_hashpiece(self, connection, message):
        try:
            c = self.connections[connection]
            if len(message) <= 13:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad HASHPIECE: msg len'
                connection.close()
                return
            i = toint(message[1:5])
            if i >= self.numpieces:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad HASHPIECE: index out of range'
                connection.close()
                return
            begin = toint(message[5:9])
            len_hashlist = toint(message[9:13])
            bhashlist = message[13:13 + len_hashlist]
            hashlist = bdecode(bhashlist)
            if not isinstance(hashlist, list):
                raise AssertionError, 'hashlist not list'
            for oh in hashlist:
                if not isinstance(oh, list) or not len(oh) == 2 or not isinstance(oh[0], int) or not isinstance(oh[1], str) or not len(oh[1]) == 20:
                    raise AssertionError, 'hashlist entry invalid'

            piece = message[13 + len_hashlist:]
            if DEBUG_NORMAL_MSGS:
                print >> sys.stderr, 'connecter: Got HASHPIECE', i, begin
            if c.download.got_piece(i, begin, hashlist, piece):
                self.got_piece(i)
        except Exception as e:
            if DEBUG:
                print >> sys.stderr, 'Close on bad HASHPIECE: exception', str(e)
                log_exc()
            connection.close()

    def na_got_loopback(self, econnection):
        if DEBUG:
            print >> sys.stderr, 'connecter: na_got_loopback: Got connection from', econnection.get_ip(), econnection.get_port()
        for c in self.connections.itervalues():
            ret = c.na_got_loopback(econnection)
            if ret is not None:
                return ret

        return False

    def na_got_internal_connection(self, origconn, newconn):
        if DEBUG:
            print >> sys.stderr, 'connecter: na_got_internal: From', newconn.get_ip(), newconn.get_port()
        origconn.close()

    def got_message(self, connection, message):
        c = self.connections[connection]
        t = message[0]
        if DEBUG_MESSAGE_HANDLING:
            st = time.time()
        if DEBUG_NORMAL_MSGS:
            print >> sys.stderr, 'connecter: Got', getMessageName(t), connection.get_ip()
        if t == EXTEND:
            self.got_extend_message(connection, c, message, self.ut_pex_enabled)
            return
        if self.is_closed_swarm and c.can_send_to():
            c.got_anything = False
        if t == BITFIELD and c.got_anything:
            if DEBUG:
                print >> sys.stderr, 'Close on BITFIELD'
            connection.close()
            return
        c.got_anything = True
        if t in [CHOKE,
         UNCHOKE,
         INTERESTED,
         NOT_INTERESTED] and len(message) != 1:
            if DEBUG:
                print >> sys.stderr, 'Close on bad (UN)CHOKE/(NOT_)INTERESTED', t
            connection.close()
            return
        if t == CHOKE:
            if DEBUG_NORMAL_MSGS:
                print >> sys.stderr, 'connecter: Got CHOKE from', connection.get_ip()
            c.download.got_choke()
        elif t == UNCHOKE:
            if DEBUG_NORMAL_MSGS:
                print >> sys.stderr, 'connecter: Got UNCHOKE from', connection.get_ip()
            c.download.got_unchoke()
        elif t == INTERESTED:
            if DEBUG_NORMAL_MSGS:
                print >> sys.stderr, 'connecter: Got INTERESTED from', connection.get_ip()
            if c.upload is not None:
                c.upload.got_interested()
        elif t == NOT_INTERESTED:
            c.upload.got_not_interested()
        elif t == HAVE:
            if len(message) != 5:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad HAVE: msg len'
                connection.close()
                return
            i = toint(message[1:])
            if i >= self.numpieces:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad HAVE: index out of range'
                connection.close()
                return
            if DEBUG_NORMAL_MSGS:
                print >> sys.stderr, 'connecter: Got HAVE(', i, ') from', connection.get_ip()
            c.download.got_have(i)
        elif t == BITFIELD:
            if DEBUG_NORMAL_MSGS:
                print >> sys.stderr, 'connecter: Got BITFIELD from', connection.get_ip()
            try:
                b = Bitfield(self.numpieces, message[1:], calcactiveranges=self.live_streaming)
            except ValueError:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad BITFIELD'
                connection.close()
                return

            if c.download is not None:
                c.download.got_have_bitfield(b)
        elif t == REQUEST:
            if not c.can_send_to():
                c.cs_status_unauth_requests.inc()
                print >> sys.stderr, 'Got REQUEST but remote node is not authenticated'
                return
            if len(message) != 13:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad REQUEST: msg len'
                connection.close()
                return
            i = toint(message[1:5])
            if i >= self.numpieces:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad REQUEST: index out of range'
                connection.close()
                return
            if DEBUG_NORMAL_MSGS:
                print >> sys.stderr, 'connecter: Got REQUEST(', i, ') from', connection.get_ip()
            c.got_request(i, toint(message[5:9]), toint(message[9:]))
        elif t == CANCEL:
            if len(message) != 13:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad CANCEL: msg len'
                connection.close()
                return
            i = toint(message[1:5])
            if i >= self.numpieces:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad CANCEL: index out of range'
                connection.close()
                return
            c.upload.got_cancel(i, toint(message[5:9]), toint(message[9:]))
        elif t == PIECE:
            if len(message) <= 9:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad PIECE: msg len'
                connection.close()
                return
            i = toint(message[1:5])
            if i >= self.numpieces:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad PIECE: msg len'
                connection.close()
                return
            if DEBUG_NORMAL_MSGS:
                print >> sys.stderr, 'connecter: Got PIECE(', i, ') from', connection.get_ip()
            try:
                c.last_received_piece = i
                if c.download.got_piece(i, toint(message[5:9]), [], message[9:]):
                    self.got_piece(i)
            except Exception as e:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad PIECE: exception', str(e)
                    log_exc()
                connection.close()
                return

        elif t == HASHPIECE:
            self.got_hashpiece(connection, message)
        elif t == G2G_PIECE_XFER:
            if len(message) <= 12:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad G2G_PIECE_XFER: msg len'
                connection.close()
                return
            if not c.use_g2g:
                if DEBUG:
                    print >> sys.stderr, 'Close on receiving G2G_PIECE_XFER over non-g2g connection'
                connection.close()
                return
            index = toint(message[1:5])
            begin = toint(message[5:9])
            length = toint(message[9:13])
            c.got_g2g_piece_xfer_v1(index, begin, length)
        else:
            connection.close()
        if DEBUG_MESSAGE_HANDLING:
            et = time.time()
            diff = et - st
            if diff > 0.1:
                print >> sys.stderr, 'connecter: $$$$$$$$$$$$', getMessageName(t), 'took', diff

    def got_extend_message(self, connection, c, message, ut_pex_enabled):
        if DEBUG:
            log('connecter::got_extend_message: len', len(message))
            log('connecter::got_extend_message: his handshake', c.extend_hs_dict, c.get_ip())
        try:
            if len(message) < 4:
                if DEBUG:
                    print >> sys.stderr, 'Close on bad EXTEND: msg len'
                connection.close()
                return
            ext_id = message[1]
            if DEBUG:
                print >> sys.stderr, 'connecter: Got EXTEND message, id', ord(ext_id)
            if ext_id == EXTEND_MSG_HANDSHAKE_ID:
                d = bdecode(message[2:])
                if type(d) == DictType:
                    c.got_extend_handshake(d)
                else:
                    if DEBUG:
                        print >> sys.stderr, 'Close on bad EXTEND: payload of handshake is not a bencoded dict'
                    connection.close()
                    return
            else:
                ext_msg_name = self.our_extend_msg_id_to_name(ext_id)
                if ext_msg_name is None:
                    if DEBUG:
                        print >> sys.stderr, "Close on bad EXTEND: peer sent ID we didn't define in handshake"
                    connection.close()
                    return
                if ext_msg_name == EXTEND_MSG_OVERLAYSWARM:
                    if DEBUG:
                        print >> sys.stderr, "Not closing EXTEND+CHALLENGE: peer didn't read our spec right, be liberal"
                elif ext_msg_name == EXTEND_MSG_UTORRENT_PEX and ut_pex_enabled:
                    d = bdecode(message[2:])
                    if type(d) == DictType:
                        c.got_ut_pex(d)
                    else:
                        if DEBUG:
                            print >> sys.stderr, 'Close on bad EXTEND: payload of ut_pex is not a bencoded dict'
                        connection.close()
                        return
                elif ext_msg_name == EXTEND_MSG_METADATA:
                    if DEBUG:
                        print >> sys.stderr, 'Connecter.got_extend_message() ut_metadata'
                    d = bdecode(message[2:], sloppy=1)
                    if type(d) == DictType:
                        self.got_ut_metadata(c, d, message)
                    else:
                        if DEBUG:
                            print >> sys.stderr, 'Connecter.got_extend_message() close on bad ut_metadata message'
                        connection.close()
                        return
                elif ext_msg_name == EXTEND_MSG_G2G_V2 and self.use_g2g:
                    ppdict = bdecode(message[2:])
                    if type(ppdict) != DictType:
                        if DEBUG:
                            print >> sys.stderr, 'Close on bad EXTEND+G2G: payload not dict'
                        connection.close()
                        return
                    for k, v in ppdict.iteritems():
                        if type(k) != StringType or type(v) != StringType:
                            if DEBUG:
                                print >> sys.stderr, 'Close on bad EXTEND+G2G: key,value not of type int,char'
                            connection.close()
                            return
                        try:
                            int(k)
                        except:
                            if DEBUG:
                                print >> sys.stderr, 'Close on bad EXTEND+G2G: key not int'
                            connection.close()
                            return

                        if ord(v) > 100:
                            if DEBUG:
                                print >> sys.stderr, 'Close on bad EXTEND+G2G: value too big', ppdict, v, ord(v)
                            connection.close()
                            return

                    c.got_g2g_piece_xfer_v2(ppdict)
                elif ext_msg_name == EXTEND_MSG_HASHPIECE and self.merkle_torrent:
                    oldmsg = message[1:]
                    self.got_hashpiece(connection, oldmsg)
                elif ext_msg_name == EXTEND_MSG_CS:
                    cs_list = bdecode(message[2:])
                    c.got_cs_message(cs_list)
                elif ext_msg_name == EXTEND_MSG_INVALIDATE:
                    if not self.live_streaming:
                        if DEBUG:
                            log('connecter::got_extend_message: received invalidate on vod')
                        return
                    piece = bdecode(message[2:])
                    try:
                        piece = int(piece)
                    except:
                        if DEBUG:
                            log('connecter::got_extend_message: received bad invalidate value:', piece)
                        connection.close()
                        return

                    c.download.got_invalidate(piece)
                else:
                    if DEBUG:
                        print >> sys.stderr, "Close on bad EXTEND: peer sent ID that maps to name we don't support", ext_msg_name, `ext_id`, ord(ext_id)
                    connection.close()
                    return
            return
        except Exception as e:
            if DEBUG:
                print >> sys.stderr, 'Close on bad EXTEND: exception:', str(e), `(message[2:])`
                log_exc()
            connection.close()
            return

    def _cs_completed(self, connection):
        connection.cs_complete = True
        try:
            have_list = connection.upload.storage.get_have_list()
            bitfield = Bitfield(self.numpieces, have_list)
            connection.send_bitfield(bitfield.tostring())
            connection.got_anything = False
            self.choker.start_connection(connection)
        except Exception as e:
            print >> sys.stderr, 'connecter: CS: Error restarting after CS handshake:', e

    def cs_handshake_completed(self):
        if DEBUG_CS:
            print >> sys.stderr, 'connecter: Closed swarm handshake completed!'
        if self.cs_post_func:
            self.cs_post_func()
        elif DEBUG_CS:
            print >> sys.stderr, "connecter: CS: Woops, don't have post function"


def olthread_bartercast_conn_lost(ip, port, down_kb, up_kb):
    from ACEStream.Core.CacheDB.CacheDBHandler import PeerDBHandler, BarterCastDBHandler
    peerdb = PeerDBHandler.getInstance()
    bartercastdb = BarterCastDBHandler.getInstance()
    if bartercastdb:
        permid = peerdb.getPermIDByIP(ip)
        my_permid = bartercastdb.my_permid
        if DEBUG:
            print >> sys.stderr, 'bartercast: (Connecter): Up %d down %d peer %s:%s (PermID = %s)' % (up_kb,
             down_kb,
             ip,
             port,
             `permid`)
        changed = False
        if permid is not None:
            if down_kb > 0:
                new_value = bartercastdb.incrementItem((my_permid, permid), 'downloaded', down_kb, commit=False)
                changed = True
            if up_kb > 0:
                new_value = bartercastdb.incrementItem((my_permid, permid), 'uploaded', up_kb, commit=False)
                changed = True
        else:
            if down_kb > 0:
                new_value = bartercastdb.incrementItem((my_permid, 'non-tribler'), 'downloaded', down_kb, commit=False)
                changed = True
            if up_kb > 0:
                new_value = bartercastdb.incrementItem((my_permid, 'non-tribler'), 'uploaded', up_kb, commit=False)
                changed = True
        if changed:
            bartercastdb.commit()
    elif DEBUG:
        print >> sys.stderr, 'BARTERCAST: No bartercastdb instance'
