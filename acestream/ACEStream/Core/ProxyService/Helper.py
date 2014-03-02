#Embedded file name: ACEStream\Core\ProxyService\Helper.pyo
import sys
from traceback import print_exc
from time import time
from collections import deque
from threading import Lock
from ACEStream.Core.BitTornado.bencode import bencode
from ACEStream.Core.BitTornado.BT1.MessageID import ASK_FOR_HELP, STOP_HELPING, REQUEST_PIECES, CANCEL_PIECE, JOIN_HELPERS, RESIGN_AS_HELPER, DROPPED_PIECE, PROXY_HAVE, PROXY_UNHAVE
from ACEStream.Core.Overlay.OverlayThreadingBridge import OverlayThreadingBridge
from ACEStream.Core.CacheDB.CacheDBHandler import PeerDBHandler, TorrentDBHandler
from ACEStream.Core.Utilities.utilities import show_permid_short
from ACEStream.Core.ProxyService.ProxyServiceUtil import *
MAX_ROUNDS = 200
DEBUG = False

class SingleDownloadHelperInterface:

    def __init__(self):
        self.frozen_by_helper = False

    def helper_set_freezing(self, val):
        self.frozen_by_helper = val

    def is_frozen_by_helper(self):
        return self.frozen_by_helper

    def is_choked(self):
        pass

    def helper_forces_unchoke(self):
        pass

    def _request_more(self, new_unchoke = False):
        pass


class Helper:

    def __init__(self, torrent_hash, num_pieces, coordinator_permid, coordinator = None):
        self.torrent_hash = torrent_hash
        self.coordinator = coordinator
        self.coordinator_permid = {}
        if coordinator_permid is not None and coordinator_permid == '':
            self.coordinator_permid[None] = [None, -1]
        else:
            peerdb = PeerDBHandler.getInstance()
            peer = peerdb.getPeer(coordinator_permid)
            if peer is not None:
                ip = peer['ip']
                port = peer['port']
                self.coordinator_permid[coordinator_permid] = [ip, port]
            else:
                self.coordinator_permid[None] = [None, -1]
            self.coordinator_ip = None
            self.coordinator_port = None
        self.overlay_bridge = OverlayThreadingBridge.getInstance()
        self.reserved_pieces = [False] * num_pieces
        self.ignored_pieces = [False] * num_pieces
        self.distr_reserved_pieces = [False] * num_pieces
        self.requested_pieces = deque()
        self.requested_pieces_lock = Lock()
        self.counter = 0
        self.completed = False
        self.marker = [True] * num_pieces
        self.round = 0
        self.encoder = None
        self.continuations = []
        self.outstanding = None
        self.last_req_time = 0
        self.received_challenges = {}
        self.downloader = None

    def test(self):
        result = self.reserve_piece(10, None)
        print >> sys.stderr, 'reserve piece returned: ' + str(result)
        print >> sys.stderr, 'Test passed'

    def notify(self):
        if self.outstanding is None:
            if DEBUG:
                print >> sys.stderr, 'helper: notify: No continuation waiting?'
        else:
            if DEBUG:
                print >> sys.stderr, 'helper: notify: Waking downloader'
            sdownload = self.outstanding
            self.outstanding = None
            self.restart(sdownload)
            l = self.continuations[:]
            self.continuations = []
            for sdownload in l:
                self.restart(sdownload)

    def restart(self, sdownload):
        if sdownload.is_choked():
            sdownload.helper_forces_unchoke()
        sdownload.helper_set_freezing(False)
        sdownload._request_more()

    def send_join_helpers(self, permid):
        if DEBUG:
            print >> sys.stderr, 'helper: send_join_helpers: sending a join_helpers message to', show_permid_short(permid)
        olthread_send_join_helpers_lambda = lambda : self.olthread_send_join_helpers(permid)
        self.overlay_bridge.add_task(olthread_send_join_helpers_lambda, 0)

    def olthread_send_join_helpers(self, permid):
        olthread_join_helpers_connect_callback_lambda = lambda e, d, p, s: self.olthread_join_helpers_connect_callback(e, d, p, s)
        self.overlay_bridge.connect(permid, olthread_join_helpers_connect_callback_lambda)

    def olthread_join_helpers_connect_callback(self, exc, dns, permid, selversion):
        if exc is None:
            message = JOIN_HELPERS + self.torrent_hash
            if DEBUG:
                print >> sys.stderr, 'helper: olthread_join_helpers_connect_callback: Sending JOIN_HELPERS to', show_permid_short(permid)
            self.overlay_bridge.send(permid, message, self.olthread_join_helpers_send_callback)
        elif DEBUG:
            print >> sys.stderr, 'helper: olthread_join_helpers_connect_callback: error connecting to', show_permid_short(permid), exc

    def olthread_join_helpers_send_callback(self, exc, permid):
        if exc is not None:
            if DEBUG:
                print >> sys.stderr, 'helper: olthread_join_helpers_send_callback: error sending message to', show_permid_short(permid), exc

    def send_proxy_have(self, aggregated_haves):
        if DEBUG:
            print >> sys.stderr, 'helper: send_proxy_have: sending a proxy_have message to all', len(self.coordinator_permid), 'coordinator(s)'
        aggregated_string = aggregated_haves.tostring()
        olthread_send_proxy_have_lambda = lambda : self.olthread_send_proxy_have(self.coordinator_permid.keys(), aggregated_string)
        self.overlay_bridge.add_task(olthread_send_proxy_have_lambda, 0)

    def olthread_send_proxy_have(self, permid, aggregated_string):
        for permid in self.coordinator_permid.keys():
            if DEBUG:
                print >> sys.stderr, 'helper: olthread_send_proxy_have: Sending PROXY_HAVE to', show_permid_short(permid)

        olthread_proxy_have_connect_callback_lambda = lambda e, d, p, s: self.olthread_proxy_have_connect_callback(e, d, p, s, aggregated_string)
        self.overlay_bridge.connect(permid, olthread_proxy_have_connect_callback_lambda)

    def olthread_proxy_have_connect_callback(self, exc, dns, permid, selversion, aggregated_string):
        if exc is None:
            message = PROXY_HAVE + self.torrent_hash + bencode(aggregated_string)
            if DEBUG:
                print >> sys.stderr, 'helper: olthread_proxy_have_connect_callback: Sending PROXY_HAVE to', show_permid_short(permid)
            self.overlay_bridge.send(permid, message, self.olthread_proxy_have_send_callback)
        elif DEBUG:
            print >> sys.stderr, 'helper: olthread_proxy_have_connect_callback: error connecting to', show_permid_short(permid), exc

    def olthread_proxy_have_send_callback(self, exc, permid):
        if exc is not None:
            if DEBUG:
                print >> sys.stderr, 'helper: olthread_proxy_have_send_callback: error sending message to', show_permid_short(permid), exc

    def send_resign_as_helper(self, permid):
        if DEBUG:
            print 'helper: send_resign_as_helper: sending a resign_as_helper message to', permid
        olthread_send_resign_as_helper_lambda = lambda : self.olthread_send_resign_as_helper(permid)
        self.overlay_bridge.add_task(olthread_send_resign_as_helper_lambda, 0)

    def olthread_send_resign_as_helper(self, permid):
        olthread_resign_as_helper_connect_callback_lambda = lambda e, d, p, s: self.olthread_resign_as_helper_connect_callback(e, d, p, s)
        self.overlay_bridge.connect(permid, olthread_resign_as_helper_connect_callback_lambda)

    def olthread_resign_as_helper_connect_callback(self, exc, dns, permid, selversion):
        if exc is None:
            message = RESIGN_AS_HELPER + self.torrent_hash
            if DEBUG:
                print >> sys.stderr, 'helper: olthread_resign_as_helper_connect_callback: Sending RESIGN_AS_HELPER to', show_permid_short(permid)
            self.overlay_bridge.send(permid, message, self.olthread_resign_as_helper_send_callback)
        elif DEBUG:
            print >> sys.stderr, 'helper: olthread_resign_as_helper_connect_callback: error connecting to', show_permid_short(permid), exc

    def olthread_resign_as_helper_send_callback(self, exc, permid):
        if exc is not None:
            if DEBUG:
                print >> sys.stderr, 'helper: olthread_resign_as_helper_send_callback: error sending message to', show_permid_short(permid), exc

    def got_ask_for_help(self, permid, infohash, challenge):
        if DEBUG:
            print >> sys.stderr, 'helper: got_ask_for_help: will answer to the help request from', show_permid_short(permid)
        if self.can_help(infohash):
            if DEBUG:
                print >> sys.stderr, 'helper: got_ask_for_help: received a help request, going to send join_helpers'
            self.send_join_helpers(permid)
            self.received_challenges[permid] = challenge
            peerdb = PeerDBHandler.getInstance()
            peer = peerdb.getPeer(permid)
            if peer is not None:
                ip = peer['ip']
                port = peer['port']
                if permid not in self.coordinator_permid.keys():
                    self.coordinator_permid[permid] = [ip, port]
            if DEBUG:
                print >> sys.stderr, 'helper: got_ask_for_help: sending haves to all coordinators'
            self.start_data_connection()
            if self.downloader is not None:
                self.downloader.aggregate_and_send_haves()
        else:
            if DEBUG:
                print >> sys.stderr, 'helper: got_ask_for_help: received a help request, going to send resign_as_helper'
            self.send_resign_as_helper(permid)
            return False
        return True

    def can_help(self, infohash):
        return True

    def got_stop_helping(self, permid, infohash):
        return True

    def got_request_pieces(self, permid, piece):
        if DEBUG:
            print 'helper: got_request_pieces: received request_pieces for piece', piece
        self.reserved_pieces[piece] = True
        self.distr_reserved_pieces[piece] = True
        self.ignored_pieces[piece] = False
        self.requested_pieces_lock.acquire()
        self.requested_pieces.append(piece)
        self.requested_pieces_lock.release()
        self.start_data_connection()

    def start_data_connection(self):
        if self.encoder is None:
            return
        dns = (self.coordinator_ip, self.coordinator_port)
        for coord_permid in self.coordinator_permid.keys():
            coord_ip, coord_port = self.coordinator_permid[coord_permid]
            dns = (coord_ip, coord_port)
            if DEBUG:
                print >> sys.stderr, 'helper: start_data_connection: Starting data connection to coordinator at', dns
            self.encoder.start_connection(dns, id=None, coord_con=True, challenge=self.received_challenges[coord_permid])

    def is_coordinator(self, permid):
        if permid in self.coordinator_permid.keys():
            return True
        else:
            return False

    def is_coordinator_ip(self, ip):
        for coord_ip, coord_port in self.coordinator_permid.values():
            if ip == coord_ip:
                return True

        return False

    def next_request(self):
        self.requested_pieces_lock.acquire()
        if len(self.requested_pieces) == 0:
            self.requested_pieces_lock.release()
            if DEBUG:
                print >> sys.stderr, 'helper: next_request: no requested pieces yet. Returning None'
            return None
        else:
            next_piece = self.requested_pieces.popleft()
            self.requested_pieces_lock.release()
            if DEBUG:
                print >> sys.stderr, 'helper: next_request: Returning', next_piece
            return next_piece

    def set_encoder(self, encoder):
        self.encoder = encoder

    def set_downloader(self, downloader):
        self.downloader = downloader

    def get_coordinator_permid(self):
        return self.coordinator_permid.keys()

    def is_reserved(self, piece):
        if self.reserved_pieces[piece] or self.coordinator is not None and self.is_complete():
            return True
        return self.reserved_pieces[piece]

    def is_ignored(self, piece):
        if not self.ignored_pieces[piece] or self.coordinator is not None and self.is_complete():
            return False
        return self.ignored_pieces[piece]

    def is_complete(self):
        if self.completed:
            return True
        self.round = (self.round + 1) % MAX_ROUNDS
        if self.round != 0:
            return False
        if self.coordinator is not None:
            self.completed = self.coordinator.reserved_pieces == self.marker
        else:
            self.completed = self.distr_reserved_pieces == self.marker
        return self.completed
