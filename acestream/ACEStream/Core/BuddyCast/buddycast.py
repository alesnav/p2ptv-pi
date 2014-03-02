#Embedded file name: ACEStream\Core\BuddyCast\buddycast.pyo
__fool_epydoc = 481
import sys
from random import sample, randint, shuffle
from time import time, gmtime, strftime
from traceback import print_exc, print_stack
from array import array
from bisect import insort
from copy import deepcopy
import gc
import socket
from ACEStream.Core.simpledefs import BCCOLPOLICY_SIMPLE
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
from ACEStream.Core.BitTornado.BT1.MessageID import BUDDYCAST, BARTERCAST, KEEP_ALIVE, VOTECAST, CHANNELCAST
from ACEStream.Core.Utilities.utilities import show_permid_short, show_permid, validPermid, validIP, validPort, validInfohash, readableBuddyCastMsg, hostname_or_ip2ip
from ACEStream.Core.Utilities.unicode import dunno2unicode
from ACEStream.Core.simpledefs import NTFY_ACT_MEET, NTFY_ACT_RECOMMEND, NTFY_MYPREFERENCES, NTFY_INSERT, NTFY_DELETE
from ACEStream.Core.NATFirewall.DialbackMsgHandler import DialbackMsgHandler
from ACEStream.Core.Overlay.SecureOverlay import OLPROTO_VER_FIRST, OLPROTO_VER_SECOND, OLPROTO_VER_THIRD, OLPROTO_VER_FOURTH, OLPROTO_VER_FIFTH, OLPROTO_VER_SIXTH, OLPROTO_VER_SEVENTH, OLPROTO_VER_EIGHTH, OLPROTO_VER_ELEVENTH, OLPROTO_VER_FIFTEENTH, OLPROTO_VER_CURRENT, OLPROTO_VER_LOWEST
from ACEStream.Core.CacheDB.sqlitecachedb import bin2str, str2bin
from similarity import P2PSim_Single, P2PSim_Full, P2PSimColdStart
from TorrentCollecting import SimpleTorrentCollecting
from ACEStream.Core.Statistics.Logger import OverlayLogger
from ACEStream.Core.Statistics.Crawler import Crawler
from ACEStream.Core.Session import Session
from threading import currentThread
from bartercast import BarterCastCore
from votecast import VoteCastCore
from channelcast import ChannelCastCore
DEBUG = False
debug = False
debugnic = False
unblock = 0
MAX_BUDDYCAST_LENGTH = 10 * 1024
REMOTE_SEARCH_PEER_NTORRENTS_THRESHOLD = 100
PEER_SIM_POS = 0
PEER_LASTSEEN_POS = 1

def now():
    return int(time())


def ctime(t):
    return strftime('%Y-%m-%d.%H:%M:%S', gmtime(t))


def validBuddyCastData(prefxchg, nmyprefs = 50, nbuddies = 10, npeers = 10, nbuddyprefs = 10, selversion = 0):

    def validPeer(peer):
        validPermid(peer['permid'])
        validIP(peer['ip'])
        validPort(peer['port'])

    def validHisPeer(peer):
        validIP(peer['ip'])
        validPort(peer['port'])

    def validPref(pref, num):
        if not (isinstance(prefxchg, list) or isinstance(prefxchg, dict)):
            raise RuntimeError, 'bc: invalid pref type ' + str(type(prefxchg))
        if num > 0 and len(pref) > num:
            raise RuntimeError, 'bc: length of pref exceeds ' + str((len(pref), num))
        for p in pref:
            validInfohash(p)

    validHisPeer(prefxchg)
    if not isinstance(prefxchg['name'], str):
        raise RuntimeError, 'bc: invalid name type ' + str(type(prefxchg['name']))
    prefs = prefxchg['preferences']
    if prefs:
        if type(prefs[0]) == list:
            validPref([ pref[0] for pref in prefs ], nmyprefs)
        else:
            validPref(prefs, nmyprefs)
    if len(prefxchg['taste buddies']) > nbuddies:
        raise RuntimeError, "bc: length of prefxchg['taste buddies'] exceeds " + str(len(prefxchg['taste buddies']))
    for b in prefxchg['taste buddies']:
        validPeer(b)

    if len(prefxchg['random peers']) > npeers:
        raise RuntimeError, 'bc: length of random peers ' + str(len(prefxchg['random peers']))
    for b in prefxchg['random peers']:
        validPeer(b)

    if 'collected torrents' in prefxchg:
        if not isinstance(prefxchg['collected torrents'], list):
            raise RuntimeError, "bc: invalid 'collected torrents' type " + str(type(prefxchg['collected torrents']))
        for value in prefxchg['collected torrents']:
            if selversion >= OLPROTO_VER_ELEVENTH:
                if not isinstance(value, list):
                    raise RuntimeError, "bc: invalid 'collected torrents' type of list elem should be list, not " + str(type(value))
                if len(value) != 5:
                    raise RuntimeError, "bc: invalid 'collected torrents' length of list elem should be 5"
                infohash = value[0]
                seeders = value[1]
                leechers = value[2]
                age = value[3]
                sources = value[4]
                if not len(infohash) == 20:
                    raise RuntimeError, 'bc: invalid infohash length ' + str(len(infohash))
            else:
                infohash = value
                if not isinstance(infohash, str):
                    raise RuntimeError, 'bc: invalid infohash type ' + str(type(infohash))
                if not len(infohash) == 20:
                    raise RuntimeError, 'bc: invalid infohash length ' + str(len(infohash))

    if selversion >= OLPROTO_VER_FIFTEENTH:
        try:
            if not isinstance(prefxchg['services'], int):
                raise RuntimeError, "bc: invalid 'services' type " + str(type(prefxchg['services']))
        except:
            raise RuntimeError, 'bc: invalid message: no services information'

    return True


class BuddyCastFactory():
    __single = None

    def __init__(self, superpeer = False, log = ''):
        if BuddyCastFactory.__single:
            raise RuntimeError, 'BuddyCastFactory is singleton'
        BuddyCastFactory.__single = self
        self.registered = False
        self.buddycast_core = None
        self.buddycast_interval = 15
        self.superpeer = superpeer
        self.log = log
        self.running = False
        self.data_handler = None
        self.started = False
        self.max_peers = 2500
        self.ranonce = False
        if self.superpeer:
            print >> sys.stderr, 'bc: Starting in SuperPeer mode'

    def getInstance(*args, **kw):
        if BuddyCastFactory.__single is None:
            BuddyCastFactory(*args, **kw)
        return BuddyCastFactory.__single

    getInstance = staticmethod(getInstance)

    def register(self, overlay_bridge, launchmany, errorfunc, metadata_handler, torrent_collecting_solution, running, max_peers = 2500, amcrawler = False):
        if self.registered:
            return
        self.overlay_bridge = overlay_bridge
        self.launchmany = launchmany
        self.metadata_handler = metadata_handler
        self.torrent_collecting_solution = torrent_collecting_solution
        self.errorfunc = errorfunc
        self.running = bool(running)
        self.max_peers = max_peers
        self.amcrawler = amcrawler
        self.registered = True

    def register2(self):
        if self.registered:
            if debug:
                print >> sys.stderr, 'bc: Register BuddyCast', currentThread().getName()
            self.overlay_bridge.add_task(self.olthread_register, 0)

    def olthread_register(self, start = True):
        if debug:
            print >> sys.stderr, 'bc: OlThread Register', currentThread().getName()
        self.data_handler = DataHandler(self.launchmany, self.overlay_bridge, max_num_peers=self.max_peers)
        self.bartercast_core = BarterCastCore(self.data_handler, self.overlay_bridge, self.log, self.launchmany.secure_overlay.get_dns_from_peerdb)
        self.votecast_core = VoteCastCore(self.data_handler, self.overlay_bridge, self.launchmany.session, self.getCurrrentInterval, self.log, self.launchmany.secure_overlay.get_dns_from_peerdb)
        self.channelcast_core = ChannelCastCore(self.data_handler, self.overlay_bridge, self.launchmany.session, self.getCurrrentInterval, self.log, self.launchmany.secure_overlay.get_dns_from_peerdb)
        self.buddycast_core = BuddyCastCore(self.overlay_bridge, self.launchmany, self.data_handler, self.buddycast_interval, self.superpeer, self.metadata_handler, self.torrent_collecting_solution, self.bartercast_core, self.votecast_core, self.channelcast_core, self.log, self.amcrawler)
        self.data_handler.register_buddycast_core(self.buddycast_core)
        if start:
            self.start_time = now()
            self.overlay_bridge.add_task(self.data_handler.postInit, 0)
            self.overlay_bridge.add_task(self.doBuddyCast, 0.1)
            if self.data_handler.torrent_db.size() > 0:
                waitt = 1.0
            else:
                waitt = 3.0
            self.overlay_bridge.add_task(self.data_handler.initRemoteSearchPeers, waitt)
            self.overlay_bridge.add_task(self.channelcast_core.updateMySubscribedChannels, 30)
            print >> sys.stderr, 'BuddyCast starts up', waitt

    def doBuddyCast(self):
        if not self.running:
            return
        if debug:
            print >> sys.stderr, 'bc: doBuddyCast!', currentThread().getName()
        buddycast_interval = self.getCurrrentInterval()
        self.overlay_bridge.add_task(self.doBuddyCast, buddycast_interval)
        if not self.started:
            self.started = True
        self.buddycast_core.work()
        self.ranonce = True

    def pauseBuddyCast(self):
        self.running = False

    def restartBuddyCast(self):
        if self.registered and not self.running:
            self.running = True
            self.doBuddyCast()

    def getCurrrentInterval(self):
        past = now() - self.start_time
        if past < 120:
            if len(self.buddycast_core.connected_connectable_peers) < 10:
                interval = 0.2
            elif self.data_handler.get_npeers() < 20:
                interval = 2
            else:
                interval = 5
        elif past < 1800:
            if len(self.buddycast_core.connected_connectable_peers) < 10:
                interval = 2
            else:
                interval = 5
        elif past > 86400:
            interval = 60
        else:
            interval = 15
        return interval

    def handleMessage(self, permid, selversion, message):
        if not self.registered or not self.running:
            if DEBUG:
                print >> sys.stderr, "bc: handleMessage got message, but we're not enabled or running"
            return False
        t = message[0]
        if t == BUDDYCAST:
            return self.gotBuddyCastMessage(message[1:], permid, selversion)
        if t == KEEP_ALIVE:
            if message[1:] == '':
                return self.gotKeepAliveMessage(permid)
            else:
                return False
        elif t == VOTECAST:
            if DEBUG:
                print >> sys.stderr, 'bc: Received votecast message'
            if self.votecast_core != None:
                return self.votecast_core.gotVoteCastMessage(message[1:], permid, selversion)
        elif t == CHANNELCAST:
            if DEBUG:
                print >> sys.stderr, 'bc: Received channelcast message'
            if self.channelcast_core != None:
                return self.channelcast_core.gotChannelCastMessage(message[1:], permid, selversion)
        elif t == BARTERCAST:
            if DEBUG:
                print >> sys.stderr, 'bc: Received bartercast message'
            if self.bartercast_core != None:
                return self.bartercast_core.gotBarterCastMessage(message[1:], permid, selversion)
        else:
            if DEBUG:
                print >> sys.stderr, 'bc: wrong message to buddycast', ord(t), 'Round', self.buddycast_core.round
            return False

    def gotBuddyCastMessage(self, msg, permid, selversion):
        if self.registered and self.running:
            return self.buddycast_core.gotBuddyCastMessage(msg, permid, selversion)
        else:
            return False

    def gotKeepAliveMessage(self, permid):
        if self.registered and self.running:
            return self.buddycast_core.gotKeepAliveMessage(permid)
        else:
            return False

    def handleConnection(self, exc, permid, selversion, locally_initiated):
        if DEBUG:
            print >> sys.stderr, 'bc: handleConnection', exc, show_permid_short(permid), selversion, locally_initiated, currentThread().getName()
        if not self.registered:
            return
        if DEBUG:
            nconn = 0
            conns = self.buddycast_core.connections
            print >> sys.stderr, '\nbc: conn in buddycast', len(conns)
            for peer_permid in conns:
                _permid = show_permid_short(peer_permid)
                nconn += 1
                print >> sys.stderr, 'bc: ', nconn, _permid, conns[peer_permid]

        if self.running or exc is not None:
            self.buddycast_core.handleConnection(exc, permid, selversion, locally_initiated)

    def addMyPref(self, torrent):
        if self.registered:
            self.data_handler.addMyPref(torrent)

    def delMyPref(self, torrent):
        if self.registered:
            self.data_handler.delMyPref(torrent)


class BuddyCastCore():
    TESTASSERVER = False

    def __init__(self, overlay_bridge, launchmany, data_handler, buddycast_interval, superpeer, metadata_handler, torrent_collecting_solution, bartercast_core, votecast_core, channelcast_core, log = None, amcrawler = False):
        self.overlay_bridge = overlay_bridge
        self.launchmany = launchmany
        self.data_handler = data_handler
        self.buddycast_interval = buddycast_interval
        self.superpeer = superpeer
        self.log = log
        self.dialback = DialbackMsgHandler.getInstance()
        self.ip = self.data_handler.getMyIp()
        self.port = self.data_handler.getMyPort()
        self.permid = self.data_handler.getMyPermid()
        self.nameutf8 = self.data_handler.getMyName().encode('UTF-8')
        self.block_interval = 14400
        self.short_block_interval = 14400
        self.num_myprefs = 50
        self.max_collected_torrents = 50
        self.num_tbs = 10
        self.num_tb_prefs = 10
        self.num_rps = 10
        self.max_conn_cand = 100
        self.max_conn_tb = 10
        self.max_conn_rp = 10
        self.max_conn_up = 10
        self.bootstrap_num = 10
        self.bootstrap_interval = 300
        self.network_delay = self.buddycast_interval * 2
        self.check_period = 120
        self.num_search_cand = 10
        self.num_remote_peers_in_msg = 2
        self.send_block_list = {}
        self.recv_block_list = {}
        self.connections = {}
        self.connected_taste_buddies = []
        self.connected_random_peers = []
        self.connected_connectable_peers = {}
        self.connected_unconnectable_peers = {}
        self.connection_candidates = {}
        self.remote_search_peer_candidates = []
        self.target_type = 0
        self.next_initiate = 0
        self.round = 0
        self.bootstrapped = False
        self.bootstrap_time = 0
        self.total_bootstrapped_time = 0
        self.last_bootstrapped = now()
        self.start_time = now()
        self.last_check_time = 0
        self.metadata_handler = metadata_handler
        self.torrent_collecting = None
        if torrent_collecting_solution == BCCOLPOLICY_SIMPLE:
            self.torrent_collecting = SimpleTorrentCollecting(metadata_handler, data_handler)
        self.dnsindb = launchmany.secure_overlay.get_dns_from_peerdb
        if self.log:
            self.overlay_log = OverlayLogger.getInstance(self.log)
        self.bartercast_core = bartercast_core
        self.votecast_core = votecast_core
        self.channelcast_core = channelcast_core
        self.amcrawler = amcrawler

    def get_peer_info(self, target_permid, include_permid = True):
        if not target_permid:
            return ' None '
        dns = self.dnsindb(target_permid)
        if not dns:
            return ' None '
        try:
            ip = dns[0]
            port = dns[1]
            sim = self.data_handler.getPeerSim(target_permid)
            if include_permid:
                s_pid = show_permid_short(target_permid)
                return ' %s %s:%s %.3f ' % (s_pid,
                 ip,
                 port,
                 sim)
            return ' %s:%s %.3f' % (ip, port, sim)
        except:
            return ' ' + repr(dns) + ' '

    def work(self):
        try:
            self.round += 1
            if DEBUG:
                print >> sys.stderr, 'bc: Initiate exchange'
            self.print_debug_info('Active', 2)
            if self.log:
                nPeer, nPref, nCc, nBs, nBr, nSO, nCo, nCt, nCr, nCu = self.get_stats()
                self.overlay_log('BUCA_STA', self.round, (nPeer, nPref, nCc), (nBs, nBr), (nSO, nCo), (nCt, nCr, nCu))
            self.print_debug_info('Active', 3)
            self.updateSendBlockList()
            _now = now()
            if _now - self.last_check_time >= self.check_period:
                self.print_debug_info('Active', 4)
                self.keepConnections()
                gc.collect()
                self.last_check_time = _now
            if self.next_initiate > 0:
                self.print_debug_info('Active', 6)
                self.next_initiate -= 1
            else:
                if len(self.connection_candidates) == 0:
                    self.booted = self._bootstrap(self.bootstrap_num)
                    self.print_debug_info('Active', 9)
                if len(self.connection_candidates) > 0:
                    r, target_permid = self.selectTarget()
                    self.print_debug_info('Active', 11, target_permid, r=r)
                    self.startBuddyCast(target_permid)
            if debug:
                print
        except:
            print_exc()

    def _bootstrap(self, number):
        _now = now()
        if self.bootstrapped and _now - self.last_bootstrapped < self.bootstrap_interval:
            self.bootstrap_time = 0
            return -1
        send_block_list_ids = []
        for permid in self.send_block_list:
            peer_id = self.data_handler.getPeerID(permid)
            send_block_list_ids.append(peer_id)

        target_cands_ids = set(self.data_handler.peers) - set(send_block_list_ids)
        recent_peers_ids = self.selectRecentPeers(target_cands_ids, number, startfrom=self.bootstrap_time * number)
        for peer_id in recent_peers_ids:
            last_seen = self.data_handler.getPeerIDLastSeen(peer_id)
            self.addConnCandidate(self.data_handler.getPeerPermid(peer_id), last_seen)

        self.limitConnCandidate()
        self.bootstrap_time += 1
        self.total_bootstrapped_time += 1
        self.last_bootstrapped = _now
        if len(self.connection_candidates) < self.bootstrap_num:
            self.bootstrapped = True
        else:
            self.bootstrapped = False
        return 1

    def selectRecentPeers(self, cand_ids, number, startfrom = 0):
        if not cand_ids:
            return []
        peerids = []
        last_seens = []
        for peer_id in cand_ids:
            peerids.append(peer_id)
            last_seens.append(self.data_handler.getPeerIDLastSeen(peer_id))

        npeers = len(peerids)
        if npeers == 0:
            return []
        aux = zip(last_seens, peerids)
        aux.sort()
        aux.reverse()
        peers = []
        i = 0
        startfrom = startfrom % npeers
        endat = startfrom + number
        for _, peerid in aux[startfrom:endat]:
            peers.append(peerid)

        return peers

    def addConnCandidate(self, peer_permid, last_seen):
        if self.isBlocked(peer_permid, self.send_block_list) or peer_permid == self.permid:
            return
        self.connection_candidates[peer_permid] = last_seen

    def limitConnCandidate(self):
        if len(self.connection_candidates) > self.max_conn_cand:
            tmp_list = zip(self.connection_candidates.values(), self.connection_candidates.keys())
            tmp_list.sort()
            while len(self.connection_candidates) > self.max_conn_cand:
                ls, peer_permid = tmp_list.pop(0)
                self.removeConnCandidate(peer_permid)

    def removeConnCandidate(self, peer_permid):
        if peer_permid in self.connection_candidates:
            self.connection_candidates.pop(peer_permid)

    def updateSendBlockList(self):
        _now = now()
        for p in self.send_block_list.keys():
            if _now >= self.send_block_list[p] - self.network_delay:
                if debug:
                    print >> sys.stderr, 'bc: *** unblock peer in send block list' + self.get_peer_info(p) + 'expiration:', ctime(self.send_block_list[p])
                self.send_block_list.pop(p)

    def keepConnections(self):
        timeout_list = []
        for peer_permid in self.connections:
            if peer_permid in self.connected_connectable_peers or peer_permid in self.connected_unconnectable_peers:
                timeout_list.append(peer_permid)

        for peer_permid in timeout_list:
            self.sendKeepAliveMsg(peer_permid)

    def sendKeepAliveMsg(self, peer_permid):
        if self.isConnected(peer_permid):
            overlay_protocol_version = self.connections[peer_permid]
            if overlay_protocol_version >= OLPROTO_VER_THIRD:
                keepalive_msg = ''
                self.overlay_bridge.send(peer_permid, KEEP_ALIVE + keepalive_msg, self.keepaliveSendCallback)
            if debug:
                print >> sys.stderr, 'bc: *** Send keep alive to peer', self.get_peer_info(peer_permid), 'overlay version', overlay_protocol_version

    def isConnected(self, peer_permid):
        return peer_permid in self.connections

    def keepaliveSendCallback(self, exc, peer_permid, other = 0):
        if exc is None:
            pass
        else:
            if debug:
                print >> sys.stderr, 'bc: error - send keep alive msg', exc, self.get_peer_info(peer_permid), 'Round', self.round
            self.closeConnection(peer_permid, 'keepalive:' + str(exc))

    def gotKeepAliveMessage(self, peer_permid):
        if self.isConnected(peer_permid):
            if debug:
                print >> sys.stderr, 'bc: Got keep alive from', self.get_peer_info(peer_permid)
            return True
        else:
            if DEBUG:
                print >> sys.stderr, 'bc: error - got keep alive from a not connected peer. Round', self.round
            return False

    def selectTarget(self):

        def selectTBTarget():
            max_sim = (-1, None)
            for permid in self.connection_candidates:
                peer_id = self.data_handler.getPeerID(permid)
                if peer_id:
                    sim = self.data_handler.getPeerSim(permid)
                    max_sim = max(max_sim, (sim, permid))

            selected_permid = max_sim[1]
            if selected_permid is None:
                return
            else:
                return selected_permid

        def selectRPTarget():
            selected_permid = None
            while len(self.connection_candidates) > 0:
                selected_permid = sample(self.connection_candidates, 1)[0]
                selected_peer_id = self.data_handler.getPeerID(selected_permid)
                if selected_peer_id is None:
                    self.removeConnCandidate(selected_permid)
                    selected_permid = None
                elif selected_peer_id:
                    break

            return selected_permid

        self.target_type = 1 - self.target_type
        if self.target_type == 0:
            target_permid = selectTBTarget()
        else:
            target_permid = selectRPTarget()
        return (self.target_type, target_permid)

    def startBuddyCast(self, target_permid):
        if not target_permid or target_permid == self.permid:
            return
        if not self.isBlocked(target_permid, self.send_block_list):
            if debug:
                print >> sys.stderr, 'bc: connect a peer', show_permid_short(target_permid), currentThread().getName()
            self.overlay_bridge.connect(target_permid, self.buddycastConnectCallback)
            self.print_debug_info('Active', 12, target_permid)
            if self.log:
                dns = self.dnsindb(target_permid)
                if dns:
                    ip, port = dns
                    self.overlay_log('CONN_TRY', ip, port, show_permid(target_permid))
            self.print_debug_info('Active', 13, target_permid)
            self.removeConnCandidate(target_permid)
            self.print_debug_info('Active', 14, target_permid)
        elif DEBUG:
            print >> sys.stderr, 'buddycast: peer', self.get_peer_info(target_permid), 'is blocked while starting buddycast to it.', 'Round', self.round

    def buddycastConnectCallback(self, exc, dns, target_permid, selversion):
        if exc is None:
            self.addConnection(target_permid, selversion, True)
            try:
                self.print_debug_info('Active', 15, target_permid, selversion)
                self.createAndSendBuddyCastMessage(target_permid, selversion, active=True)
            except:
                print_exc()
                print >> sys.stderr, 'bc: error in reply buddycast msg', exc, dns, show_permid_short(target_permid), selversion, 'Round', self.round,

        elif debug:
            print >> sys.stderr, 'bc: warning - connecting to', show_permid_short(target_permid), exc, dns, ctime(now())

    def createAndSendBuddyCastMessage(self, target_permid, selversion, active):
        buddycast_data = self.createBuddyCastMessage(target_permid, selversion)
        if debug:
            print >> sys.stderr, 'bc: createAndSendBuddyCastMessage', len(buddycast_data), currentThread().getName()
        try:
            buddycast_data['permid'] = self.permid
            buddycast_data.pop('permid')
            buddycast_msg = bencode(buddycast_data)
        except:
            print_exc()
            print >> sys.stderr, 'error buddycast_data:', buddycast_data
            return

        if active:
            self.print_debug_info('Active', 16, target_permid)
        else:
            self.print_debug_info('Passive', 6, target_permid)
        self.overlay_bridge.send(target_permid, BUDDYCAST + buddycast_msg, self.buddycastSendCallback)
        self.blockPeer(target_permid, self.send_block_list, self.short_block_interval)
        self.removeConnCandidate(target_permid)
        if debug:
            print >> sys.stderr, '****************--------------' * 2
            print >> sys.stderr, 'sent buddycast message to', show_permid_short(target_permid), len(buddycast_msg)
        if active:
            self.print_debug_info('Active', 17, target_permid)
        else:
            self.print_debug_info('Passive', 7, target_permid)
        if self.bartercast_core != None and active:
            try:
                self.bartercast_core.createAndSendBarterCastMessage(target_permid, selversion, active)
            except:
                print_exc()

        if self.log:
            dns = self.dnsindb(target_permid)
            if dns:
                ip, port = dns
                if active:
                    MSG_ID = 'ACTIVE_BC'
                else:
                    MSG_ID = 'PASSIVE_BC'
                msg = repr(readableBuddyCastMsg(buddycast_data, selversion))
                self.overlay_log('SEND_MSG', ip, port, show_permid(target_permid), selversion, MSG_ID, msg)
        return buddycast_data

    def createBuddyCastMessage(self, target_permid, selversion, target_ip = None, target_port = None):
        try:
            target_ip, target_port = self.dnsindb(target_permid)
        except:
            if not self.TESTASSERVER:
                raise

        if not target_ip or not target_port:
            return {}
        my_pref = self.data_handler.getMyLivePreferences(selversion, self.num_myprefs)
        if debug:
            print >> sys.stderr, ' bc:Amended preference list is:', str(my_pref)
        taste_buddies = self.getTasteBuddies(self.num_tbs, self.num_tb_prefs, target_permid, target_ip, target_port, selversion)
        random_peers = self.getRandomPeers(self.num_rps, target_permid, target_ip, target_port, selversion)
        buddycast_data = {'ip': self.ip,
         'port': self.port,
         'name': self.nameutf8,
         'preferences': my_pref,
         'taste buddies': taste_buddies,
         'random peers': random_peers}
        if selversion >= OLPROTO_VER_THIRD:
            connectable = self.isConnectable()
            buddycast_data['connectable'] = connectable
        if selversion >= OLPROTO_VER_FOURTH:
            recent_collect = self.metadata_handler.getRecentlyCollectedTorrents(self.max_collected_torrents, selversion)
            buddycast_data['collected torrents'] = recent_collect
        if selversion >= OLPROTO_VER_SIXTH:
            npeers = self.data_handler.get_npeers()
            ntorrents = self.data_handler.get_ntorrents()
            nmyprefs = self.data_handler.get_nmyprefs()
            buddycast_data['npeers'] = npeers
            buddycast_data['nfiles'] = ntorrents
            buddycast_data['ndls'] = nmyprefs
        if selversion >= OLPROTO_VER_FIFTEENTH:
            session = Session.get_instance()
            myservices = session.get_active_services()
            buddycast_data['services'] = myservices
            print 'Sending BC for OL version', selversion
        return buddycast_data

    def getTasteBuddies(self, ntbs, ntbprefs, target_permid, target_ip, target_port, selversion):
        if not self.connected_taste_buddies:
            return []
        tb_list = self.connected_taste_buddies[:]
        if target_permid in tb_list:
            tb_list.remove(target_permid)
        peers = []
        for permid in tb_list:
            peer = deepcopy(self.connected_connectable_peers[permid])
            if peer['ip'] == target_ip and peer['port'] == target_port:
                continue
            peer['similarity'] = self.data_handler.getPeerSim(permid)
            peer['permid'] = permid
            peer['ip'] = str(peer['ip'])
            peers.append(peer)

        if selversion <= OLPROTO_VER_SECOND:
            for i in range(len(peers)):
                peers[i]['age'] = 0

        if selversion <= OLPROTO_VER_THIRD:
            for i in range(len(peers)):
                peers[i].pop('similarity')
                peers[i]['preferences'] = []

        if selversion >= OLPROTO_VER_FOURTH:
            for i in range(len(peers)):
                peers[i]['similarity'] = int(peers[i]['similarity'] + 0.5)

        for i in range(len(peers)):
            oversion = peers[i].pop('oversion')
            nfiles = peers[i].pop('num_torrents')
            if selversion >= OLPROTO_VER_SIXTH and oversion >= OLPROTO_VER_SIXTH and nfiles >= REMOTE_SEARCH_PEER_NTORRENTS_THRESHOLD:
                peers[i]['oversion'] = oversion
                peers[i]['nfiles'] = nfiles

        if selversion >= OLPROTO_VER_FIFTEENTH:
            for i in range(len(peers)):
                peers[i]['services'] = self.data_handler.getPeerServices(peers[i]['permid'])

        return peers

    def getRandomPeers(self, nrps, target_permid, target_ip, target_port, selversion):
        if not self.connected_random_peers:
            return []
        rp_list = self.connected_random_peers[:]
        if selversion >= OLPROTO_VER_SIXTH:
            remote_search_peers = self.getRemoteSearchPeers(self.num_remote_peers_in_msg)
            rp_list += remote_search_peers
            if len(rp_list) > nrps:
                rp_list = sample(rp_list, nrps)
        if target_permid in rp_list:
            rp_list.remove(target_permid)
        peers = []
        if DEBUG:
            print >> sys.stderr, 'bc: ******** rplist nconn', len(rp_list), len(self.connected_connectable_peers)
        for permid in rp_list:
            if permid not in self.connected_connectable_peers:
                continue
            peer = deepcopy(self.connected_connectable_peers[permid])
            if peer['ip'] == target_ip and peer['port'] == target_port:
                continue
            peer['similarity'] = self.data_handler.getPeerSim(permid)
            peer['permid'] = permid
            peer['ip'] = str(peer['ip'])
            peers.append(peer)

        if selversion <= OLPROTO_VER_SECOND:
            for i in range(len(peers)):
                peers[i]['age'] = 0

        if selversion <= OLPROTO_VER_THIRD:
            for i in range(len(peers)):
                peers[i].pop('similarity')

        if selversion >= OLPROTO_VER_FOURTH:
            for i in range(len(peers)):
                old_sim = peers[i]['similarity']
                if old_sim is None:
                    old_sim = 0.0
                peers[i]['similarity'] = int(old_sim + 0.5)

        for i in range(len(peers)):
            oversion = peers[i].pop('oversion')
            nfiles = peers[i].pop('num_torrents')
            if selversion >= OLPROTO_VER_SIXTH and oversion >= OLPROTO_VER_SIXTH and nfiles >= REMOTE_SEARCH_PEER_NTORRENTS_THRESHOLD:
                peers[i]['oversion'] = oversion
                peers[i]['nfiles'] = nfiles

        if selversion >= OLPROTO_VER_FIFTEENTH:
            for i in range(len(peers)):
                peers[i]['services'] = self.data_handler.getPeerServices(peers[i]['permid'])

        return peers

    def isConnectable(self):
        return bool(self.dialback.isConnectable())

    def buddycastSendCallback(self, exc, target_permid, other = 0):
        if exc is None:
            if debug:
                print >> sys.stderr, 'bc: *** msg was sent successfully to peer', self.get_peer_info(target_permid)
        else:
            if debug:
                print >> sys.stderr, 'bc: *** warning - error in sending msg to', self.get_peer_info(target_permid), exc
            self.closeConnection(target_permid, 'buddycast:' + str(exc))

    def blockPeer(self, peer_permid, block_list, block_interval = None):
        peer_id = peer_permid
        if block_interval is None:
            block_interval = self.block_interval
        unblock_time = now() + block_interval
        block_list[peer_id] = unblock_time

    def isBlocked(self, peer_permid, block_list):
        if self.TESTASSERVER:
            return False
        peer_id = peer_permid
        if peer_id not in block_list:
            return False
        unblock_time = block_list[peer_id]
        if now() >= unblock_time - self.network_delay:
            block_list.pop(peer_id)
            return False
        return True

    def gotBuddyCastMessage(self, recv_msg, sender_permid, selversion):
        if debug:
            print >> sys.stderr, 'bc: got and handle buddycast msg', currentThread().getName()
        if not sender_permid or sender_permid == self.permid:
            print >> sys.stderr, 'bc: error - got BuddyCastMsg from a None peer', sender_permid, recv_msg, 'Round', self.round
            return False
        blocked = self.isBlocked(sender_permid, self.recv_block_list)
        if blocked:
            if DEBUG:
                print >> sys.stderr, 'bc: warning - got BuddyCastMsg from a recv blocked peer', show_permid(sender_permid), 'Round', self.round
            return True
        if MAX_BUDDYCAST_LENGTH > 0 and len(recv_msg) > MAX_BUDDYCAST_LENGTH:
            print >> sys.stderr, 'bc: warning - got large BuddyCastMsg', len(recv_msg), 'Round', self.round
            return False
        active = self.isBlocked(sender_permid, self.send_block_list)
        if active:
            self.print_debug_info('Active', 18, sender_permid)
        else:
            self.print_debug_info('Passive', 2, sender_permid)
        buddycast_data = {}
        try:
            try:
                buddycast_data = bdecode(recv_msg)
            except ValueError as msg:
                try:
                    errmsg = str(msg)
                except:
                    errmsg = repr(msg)

                if DEBUG:
                    print >> sys.stderr, 'bc: warning, got invalid BuddyCastMsg:', errmsg, 'Round', self.round
                return False

            buddycast_data.update({'permid': sender_permid})
            try:
                validBuddyCastData(buddycast_data, 0, self.num_tbs, self.num_rps, self.num_tb_prefs, selversion)
            except RuntimeError as msg:
                try:
                    errmsg = str(msg)
                except:
                    errmsg = repr(msg)

                if DEBUG:
                    dns = self.dnsindb(sender_permid)
                    print >> sys.stderr, 'bc: warning, got invalid BuddyCastMsg:', errmsg, 'From', dns, 'Round', self.round
                return False

            dns = self.dnsindb(sender_permid)
            if dns != None:
                sender_ip = dns[0]
                sender_port = dns[1]
                buddycast_data.update({'ip': sender_ip})
                buddycast_data.update({'port': sender_port})
            if self.log:
                if active:
                    MSG_ID = 'ACTIVE_BC'
                else:
                    MSG_ID = 'PASSIVE_BC'
                msg = repr(readableBuddyCastMsg(buddycast_data, selversion))
                self.overlay_log('RECV_MSG', sender_ip, sender_port, show_permid(sender_permid), selversion, MSG_ID, msg)
            conn = buddycast_data.get('connectable', 0)
            self.handleBuddyCastMessage(sender_permid, buddycast_data, selversion)
            if active:
                conn = 1
            if active:
                self.print_debug_info('Active', 19, sender_permid)
            else:
                self.print_debug_info('Passive', 3, sender_permid)
            addto = self.addPeerToConnList(sender_permid, conn)
            if active:
                self.print_debug_info('Active', 20, sender_permid)
            else:
                self.print_debug_info('Passive', 4, sender_permid)
        except Exception as msg:
            print_exc()
            raise Exception, msg
            return True

        self.blockPeer(sender_permid, self.recv_block_list)
        collectedtorrents = buddycast_data.get('collected torrents', [])
        if selversion >= OLPROTO_VER_ELEVENTH:
            collected_infohashes = []
            for value in collectedtorrents:
                infohash = value['infohash']
                collected_infohashes.append(infohash)

        else:
            collected_infohashes = collectedtorrents
        if self.torrent_collecting and not self.superpeer:
            collected_infohashes += self.getPreferenceHashes(buddycast_data)
            self.torrent_collecting.trigger(sender_permid, selversion, collected_infohashes)
        if active:
            self.print_debug_info('Active', 21, sender_permid)
        else:
            self.print_debug_info('Passive', 5, sender_permid)
        if not active:
            self.replyBuddyCast(sender_permid, selversion)
        buf = dunno2unicode('"' + buddycast_data['name'] + '"')
        self.launchmany.set_activity(NTFY_ACT_RECOMMEND, buf)
        if DEBUG:
            print >> sys.stderr, 'bc: Got BUDDYCAST message from', self.get_peer_info(sender_permid), active
        return True

    def createPreferenceDictionaryList(self, buddycast_data):
        prefs = buddycast_data.get('preferences', [])
        if len(prefs) == 0:
            return []
        d = []
        try:
            if not type(prefs[0]) == list:
                d = [ dict({'infohash': pref}) for pref in prefs ]
                if buddycast_data['oversion'] >= OLPROTO_VER_EIGHTH:
                    if DEBUG:
                        print >> sys.stderr, 'buddycast: received OLPROTO_VER_EIGHTH buddycast data containing old style preferences. only ok if talking to an earlier non-release version'
                return d
            if buddycast_data['oversion'] >= OLPROTO_VER_ELEVENTH:
                d = [ dict({'infohash': pref[0],
                 'search_terms': pref[1],
                 'position': pref[2],
                 'reranking_strategy': pref[3],
                 'num_seeders': pref[4],
                 'num_leechers': pref[5],
                 'calc_age': pref[6],
                 'num_sources_seen': pref[7]}) for pref in prefs ]
            elif buddycast_data['oversion'] >= OLPROTO_VER_EIGHTH:
                d = [ dict({'infohash': pref[0],
                 'search_terms': pref[1],
                 'position': pref[2],
                 'reranking_strategy': pref[3]}) for pref in prefs ]
            else:
                raise RuntimeError, 'buddycast: unknown preference protocol, pref entries are lists but oversion= %s:\n%s' % (buddycast_data['oversion'], prefs)
            return d
        except Exception as msg:
            print_exc()
            raise Exception, msg
            return d

    def getPreferenceHashes(self, buddycast_data):
        return [ preference.get('infohash', '') for preference in buddycast_data.get('preferences', []) ]

    def handleBuddyCastMessage(self, sender_permid, buddycast_data, selversion):
        _now = now()
        cache_db_data = {'peer': {},
         'infohash': set(),
         'pref': [],
         'coll': []}
        cache_peer_data = {}
        tbs = buddycast_data.pop('taste buddies')
        rps = buddycast_data.pop('random peers')
        buddycast_data['oversion'] = selversion
        max_tb_sim = 1
        bc_data = [buddycast_data] + tbs + rps
        for peer in bc_data:
            peer_permid = peer['permid']
            if peer_permid == self.permid:
                continue
            age = max(peer.get('age', 0), 0)
            last_seen = _now - age
            old_last_seen = self.data_handler.getPeerLastSeen(peer_permid)
            last_seen = min(max(old_last_seen, last_seen), _now)
            oversion = peer.get('oversion', 0)
            nfiles = peer.get('nfiles', 0)
            self.addRemoteSearchPeer(peer_permid, oversion, nfiles, last_seen)
            cache_peer_data[peer_permid] = {}
            cache_peer_data[peer_permid]['last_seen'] = last_seen
            sim = peer.get('similarity', 0)
            max_tb_sim = max(max_tb_sim, sim)
            if sim > 0:
                cache_peer_data[peer_permid]['sim'] = sim
            if peer_permid != sender_permid:
                self.addConnCandidate(peer_permid, last_seen)
            new_peer_data = {}
            new_peer_data['ip'] = hostname_or_ip2ip(peer['ip'])
            new_peer_data['port'] = peer['port']
            new_peer_data['last_seen'] = last_seen
            if peer.has_key('name'):
                new_peer_data['name'] = dunno2unicode(peer['name'])
            if selversion >= OLPROTO_VER_FIFTEENTH:
                new_peer_data['services'] = peer['services']
                if new_peer_data['services'] == 2:
                    if DEBUG:
                        print '* learned about', show_permid_short(peer_permid), new_peer_data['ip'], 'from', buddycast_data['ip'], 'Complete data:', new_peer_data
            cache_db_data['peer'][peer_permid] = new_peer_data

        self.limitConnCandidate()
        if len(self.connection_candidates) > self.bootstrap_num:
            self.bootstrapped = True
        if selversion >= OLPROTO_VER_SIXTH:
            stats = {'num_peers': buddycast_data['npeers'],
             'num_torrents': buddycast_data['nfiles'],
             'num_prefs': buddycast_data['ndls']}
            cache_db_data['peer'][sender_permid].update(stats)
        cache_db_data['peer'][sender_permid]['last_buddycast'] = _now
        prefs = self.createPreferenceDictionaryList(buddycast_data)
        if selversion >= OLPROTO_VER_ELEVENTH:
            collecteds = self.createCollectedDictionaryList(buddycast_data, selversion)
            buddycast_data['collected torrents'] = collecteds
            infohashes = set(self.getCollectedHashes(buddycast_data, selversion))
        else:
            infohashes = set(buddycast_data.get('collected torrents', []))
        buddycast_data['preferences'] = prefs
        prefhashes = set(self.getPreferenceHashes(buddycast_data))
        infohashes = infohashes.union(prefhashes)
        cache_db_data['infohash'] = infohashes
        if prefs:
            cache_db_data['pref'] = prefs
        if selversion >= OLPROTO_VER_ELEVENTH:
            if collecteds:
                cache_db_data['coll'] = collecteds
        self.data_handler.handleBCData(cache_db_data, cache_peer_data, sender_permid, max_tb_sim, selversion, _now)

    def getCollectedHashes(self, buddycast_data, selversion):
        return [ collected.get('infohash', '') for collected in buddycast_data.get('collected torrents', []) ]

    def createCollectedDictionaryList(self, buddycast_data, selversion):
        collecteds = buddycast_data.get('collected torrents', [])
        if len(collecteds) == 0:
            return []
        d = []
        try:
            d = [ dict({'infohash': coll[0],
             'num_seeders': coll[1],
             'num_leechers': coll[2],
             'calc_age': coll[3],
             'num_sources_seen': coll[4]}) for coll in collecteds ]
            return d
        except Exception as msg:
            print_exc()
            raise Exception, msg
            return d

    def removeFromConnList(self, peer_permid):
        removed = 0
        if peer_permid in self.connected_connectable_peers:
            self.connected_connectable_peers.pop(peer_permid)
            try:
                self.connected_taste_buddies.remove(peer_permid)
            except ValueError:
                pass

            try:
                self.connected_random_peers.remove(peer_permid)
            except ValueError:
                pass

            removed = 1
        if peer_permid in self.connected_unconnectable_peers:
            self.connected_unconnectable_peers.pop(peer_permid)
            removed = 2
        return removed

    def addPeerToConnList(self, peer_permid, connectable = 0):
        self.removeFromConnList(peer_permid)
        if not self.isConnected(peer_permid):
            return
        _now = now()
        if connectable == 1:
            self.addPeerToConnCP(peer_permid, _now)
            addto = '(reachable peer)'
        else:
            self.addPeerToConnUP(peer_permid, _now)
            addto = '(peer deemed unreachable)'
        return addto

    def updateTBandRPList(self):
        nconnpeers = len(self.connected_connectable_peers)
        if nconnpeers == 0:
            self.connected_taste_buddies = []
            self.connected_random_peers = []
            return
        better_version_peers = 0
        recent_version_peers = 0
        tmplist = []
        tmpverlist = []
        tmplist2 = []
        tbs = []
        rps = []
        for permid in self.connected_connectable_peers:
            sim = self.data_handler.getPeerSim(permid)
            version = self.connected_connectable_peers[permid]['oversion']
            if sim > 0:
                tmplist.append([version, sim, permid])
            else:
                rps.append(permid)

        ntb = min((nconnpeers + 1) / 2, self.max_conn_tb)
        if len(tmplist) < ntb:
            cold_start_peers = P2PSimColdStart(self.connected_connectable_peers, tmplist, ntb - len(tmplist))
            tmplist.extend(cold_start_peers)
            for version, sim, permid in cold_start_peers:
                if permid in rps:
                    rps.remove(permid)

        tmplist.sort()
        tmplist.reverse()
        if len(tmplist) > 0:
            for version, sim, permid in tmplist:
                if version >= OLPROTO_VER_CURRENT and better_version_peers <= 3:
                    better_version_peers += 1
                    tmpverlist.append(permid)
                elif version >= OLPROTO_VER_EIGHTH and recent_version_peers <= 3:
                    recent_version_peers += 1
                    tmpverlist.append(permid)
                else:
                    tmplist2.append([sim, permid])

            tmplist2.sort()
            tmplist2.reverse()
            tbs = tmpverlist
            for sim, permid in tmplist2[:ntb - better_version_peers - recent_version_peers]:
                tbs.append(permid)

        ntb = len(tbs)
        if len(tmplist) > ntb:
            rps = [ permid for sim, permid in tmplist2[ntb - better_version_peers - recent_version_peers:] ] + rps
        tmplist = []
        if len(rps) > self.max_conn_rp:
            tmplist = []
            for permid in rps:
                connect_time = self.connected_connectable_peers[permid]['connect_time']
                tmplist.append([connect_time, permid])

            tmplist.sort()
            tmplist.reverse()
            rps = []
            for last_seen, permid in tmplist[:self.max_conn_rp]:
                rps.append(permid)

            for last_seen, permid in tmplist[self.max_conn_rp:]:
                self.connected_connectable_peers.pop(permid)

        self.connected_taste_buddies = tbs
        self.connected_random_peers = rps

    def addPeerToConnCP(self, peer_permid, conn_time):
        keys = ('ip', 'port', 'oversion', 'num_torrents')
        res = self.data_handler.getPeer(peer_permid, keys)
        peer = dict(zip(keys, res))
        peer['connect_time'] = conn_time
        self.connected_connectable_peers[peer_permid] = peer
        self.updateTBandRPList()

    def addNewPeerToConnList(self, conn_list, max_num, peer_permid, conn_time):
        if max_num <= 0 or len(conn_list) < max_num:
            conn_list[peer_permid] = conn_time
            return
        oldest_peer = (conn_time + 1, None)
        initial = 'abcdefghijklmnopqrstuvwxyz'
        separator = ':-)'
        for p in conn_list:
            _conn_time = conn_list[p]
            r = randint(0, self.max_conn_tb)
            name = initial[r] + separator + p
            to_cmp = (_conn_time, name)
            oldest_peer = min(oldest_peer, to_cmp)

        if conn_time >= oldest_peer[0]:
            out_peer = oldest_peer[1].split(separator)[1]
            conn_list.pop(out_peer)
            conn_list[peer_permid] = conn_time
            return out_peer
        else:
            return peer_permid

    def addPeerToConnUP(self, peer_permid, conn_time):
        ups = self.connected_unconnectable_peers
        if peer_permid not in ups:
            out_peer = self.addNewPeerToConnList(ups, self.max_conn_up, peer_permid, conn_time)
            if out_peer != peer_permid:
                return True
        return False

    def replyBuddyCast(self, target_permid, selversion):
        if not self.isConnected(target_permid):
            return
        self.createAndSendBuddyCastMessage(target_permid, selversion, active=False)
        self.print_debug_info('Passive', 8, target_permid)
        self.print_debug_info('Passive', 9, target_permid)
        self.next_initiate += 1
        self.print_debug_info('Passive', 10)

    def handleConnection(self, exc, permid, selversion, locally_initiated):
        if exc is None and permid != self.permid:
            self.addConnection(permid, selversion, locally_initiated)
        else:
            self.closeConnection(permid, 'overlayswarm:' + str(exc))
        if debug:
            print >> sys.stderr, 'bc: handle conn from overlay', exc, self.get_peer_info(permid), 'selversion:', selversion, 'local_init:', locally_initiated, ctime(now()), '; #connections:', len(self.connected_connectable_peers), '; #TB:', len(self.connected_taste_buddies), '; #RP:', len(self.connected_random_peers)

    def addConnection(self, peer_permid, selversion, locally_initiated):
        _now = now()
        if DEBUG:
            print >> sys.stderr, 'bc: addConnection', self.isConnected(peer_permid)
        if not self.isConnected(peer_permid):
            self.connections[peer_permid] = selversion
            addto = self.addPeerToConnList(peer_permid, locally_initiated)
            dns = self.get_peer_info(peer_permid, include_permid=False)
            buf = '%s %s' % (dns, addto)
            self.launchmany.set_activity(NTFY_ACT_MEET, buf)
            if self.torrent_collecting and not self.superpeer:
                try:
                    self.torrent_collecting.trigger(peer_permid, selversion)
                except:
                    print_exc()

            if debug:
                print >> sys.stderr, 'bc: add connection', self.get_peer_info(peer_permid), 'to', addto
            if self.log:
                dns = self.dnsindb(peer_permid)
                if dns:
                    ip, port = dns
                    self.overlay_log('CONN_ADD', ip, port, show_permid(peer_permid), selversion)

    def closeConnection(self, peer_permid, reason):
        if debug:
            print >> sys.stderr, 'bc: close connection:', self.get_peer_info(peer_permid)
        if self.isConnected(peer_permid):
            self.connections.pop(peer_permid)
        removed = self.removeFromConnList(peer_permid)
        if removed == 1:
            self.updateTBandRPList()
        if self.log:
            dns = self.dnsindb(peer_permid)
            if dns:
                ip, port = dns
                self.overlay_log('CONN_DEL', ip, port, show_permid(peer_permid), reason)

    def get_stats(self):
        nPeer = len(self.data_handler.peers)
        nPref = nPeer
        nCc = len(self.connection_candidates)
        nBs = len(self.send_block_list)
        nBr = len(self.recv_block_list)
        nSO = -1
        nCo = len(self.connections)
        nCt = len(self.connected_taste_buddies)
        nCr = len(self.connected_random_peers)
        nCu = len(self.connected_unconnectable_peers)
        return (nPeer,
         nPref,
         nCc,
         nBs,
         nBr,
         nSO,
         nCo,
         nCt,
         nCr,
         nCu)

    def print_debug_info(self, thread, step, target_permid = None, selversion = 0, r = 0, addto = ''):
        if not debug:
            return
        if DEBUG:
            print >> sys.stderr, 'bc: *****', thread, str(step), '-',
        if thread == 'Active':
            if step == 2:
                print >> sys.stderr, 'Working:', now() - self.start_time, 'seconds since start. Round', self.round, 'Time:', ctime(now())
                nPeer, nPref, nCc, nBs, nBr, nSO, nCo, nCt, nCr, nCu = self.get_stats()
                print >> sys.stderr, 'bc: *** Status: nPeer nPref nCc: %d %d %d  nBs nBr: %d %d  nSO nCo nCt nCr nCu: %d %d %d %d %d' % (nPeer,
                 nPref,
                 nCc,
                 nBs,
                 nBr,
                 nSO,
                 nCo,
                 nCt,
                 nCr,
                 nCu)
                if nSO != nCo:
                    print >> sys.stderr, 'bc: warning - nSo and nCo is inconsistent'
                if nCc > self.max_conn_cand or nCt > self.max_conn_tb or nCr > self.max_conn_rp or nCu > self.max_conn_up:
                    print >> sys.stderr, 'bc: warning - nCC or nCt or nCr or nCu overloads'
                _now = now()
                buf = ''
                i = 1
                for p in self.connected_taste_buddies:
                    buf += 'bc: %d taste buddies: ' % i + self.get_peer_info(p) + str(_now - self.connected_connectable_peers[p]['connect_time']) + ' version: ' + str(self.connections[p]) + '\n'
                    i += 1

                print >> sys.stderr, buf
                buf = ''
                i = 1
                for p in self.connected_random_peers:
                    buf += 'bc: %d random peers: ' % i + self.get_peer_info(p) + str(_now - self.connected_connectable_peers[p]['connect_time']) + ' version: ' + str(self.connections[p]) + '\n'
                    i += 1

                print >> sys.stderr, buf
                buf = ''
                i = 1
                for p in self.connected_unconnectable_peers:
                    buf += 'bc: %d unconnectable peers: ' % i + self.get_peer_info(p) + str(_now - self.connected_unconnectable_peers[p]) + ' version: ' + str(self.connections[p]) + '\n'
                    i += 1

                print >> sys.stderr, buf
                buf = ''
                totalsim = 0
                nsimpeers = 0
                minsim = 10000000000.0
                maxsim = 0
                sims = []
                for p in self.data_handler.peers:
                    sim = self.data_handler.peers[p][PEER_SIM_POS]
                    if sim > 0:
                        sims.append(sim)

                if sims:
                    minsim = min(sims)
                    maxsim = max(sims)
                    nsimpeers = len(sims)
                    totalsim = sum(sims)
                    if nsimpeers > 0:
                        meansim = totalsim / nsimpeers
                    else:
                        meansim = 0
                    print >> sys.stderr, 'bc: * sim peer: %d %.3f %.3f %.3f %.3f\n' % (nsimpeers,
                     totalsim,
                     meansim,
                     minsim,
                     maxsim)
            elif step == 3:
                print >> sys.stderr, 'check blocked peers: Round', self.round
            elif step == 4:
                print >> sys.stderr, 'keep connections with peers: Round', self.round
            elif step == 6:
                print >> sys.stderr, 'idle loop:', self.next_initiate
            elif step == 9:
                print >> sys.stderr, 'bootstrapping: select', self.bootstrap_num, 'peers recently seen from Mega Cache'
                if self.booted < 0:
                    print >> sys.stderr, 'bc: *** bootstrapped recently, so wait for a while'
                elif self.booted == 0:
                    print >> sys.stderr, 'bc: *** no peers to bootstrap. Try next time'
                else:
                    print >> sys.stderr, 'bc: *** bootstrapped, got', len(self.connection_candidates), 'peers in Cc. Times of bootstrapped', self.total_bootstrapped_time
                    buf = ''
                    for p in self.connection_candidates:
                        buf += 'bc: * cand:' + `p` + '\n'

                    buf += '\nbc: Remote Search Peer Candidates:\n'
                    for p in self.remote_search_peer_candidates:
                        buf += 'bc: * remote: %d ' % p[0] + self.get_peer_info(p[1]) + '\n'

                    print >> sys.stderr, buf
            elif step == 11:
                buf = 'select '
                if r == 0:
                    buf += 'a most similar taste buddy'
                else:
                    buf += 'a most likely online random peer'
                buf += ' from Cc for buddycast out\n'
                if target_permid:
                    buf += 'bc: *** got target %s sim: %s last_seen: %s' % (self.get_peer_info(target_permid), self.data_handler.getPeerSim(target_permid), ctime(self.data_handler.getPeerLastSeen(target_permid)))
                else:
                    buf += 'bc: *** no target to select. Skip this round'
                print >> sys.stderr, buf
            elif step == 12:
                print >> sys.stderr, 'connect a peer to start buddycast', self.get_peer_info(target_permid)
            elif step == 13:
                print >> sys.stderr, 'block connected peer in send block list', self.get_peer_info(target_permid)
            elif step == 14:
                print >> sys.stderr, 'remove connected peer from Cc', self.get_peer_info(target_permid)
            elif step == 15:
                print >> sys.stderr, 'peer is connected', self.get_peer_info(target_permid), 'overlay version', selversion, currentThread().getName()
            elif step == 16:
                print >> sys.stderr, 'create buddycast to send to', self.get_peer_info(target_permid)
            elif step == 17:
                print >> sys.stderr, 'send buddycast msg to', self.get_peer_info(target_permid)
            elif step == 18:
                print >> sys.stderr, 'receive buddycast message from peer %s' % self.get_peer_info(target_permid)
            elif step == 19:
                print >> sys.stderr, 'store peers from incoming msg to cache and db'
            elif step == 20:
                print >> sys.stderr, 'add connected peer %s to connection list %s' % (self.get_peer_info(target_permid), addto)
            elif step == 21:
                print >> sys.stderr, 'block connected peer in recv block list', self.get_peer_info(target_permid), self.recv_block_list[target_permid]
        if thread == 'Passive':
            if step == 2:
                print >> sys.stderr, 'receive buddycast message from peer %s' % self.get_peer_info(target_permid)
            elif step == 3:
                print >> sys.stderr, 'store peers from incoming msg to cache and db'
            elif step == 4:
                print >> sys.stderr, 'add connected peer %s to connection list %s' % (self.get_peer_info(target_permid), addto)
            elif step == 5:
                print >> sys.stderr, 'block connected peer in recv block list', self.get_peer_info(target_permid), self.recv_block_list[target_permid]
            elif step == 6:
                print >> sys.stderr, 'create buddycast to reply to', self.get_peer_info(target_permid)
            elif step == 7:
                print >> sys.stderr, 'reply buddycast msg to', self.get_peer_info(target_permid)
            elif step == 8:
                print >> sys.stderr, 'block connected peer in send block list', self.get_peer_info(target_permid), self.send_block_list[target_permid]
            elif step == 9:
                print >> sys.stderr, 'remove connected peer from Cc', self.get_peer_info(target_permid)
            elif step == 10:
                print >> sys.stderr, 'add idle loops', self.next_initiate
        sys.stdout.flush()
        sys.stderr.flush()
        if DEBUG:
            print >> sys.stderr, 'bc: *****', thread, str(step), '-',

    def getAllTasteBuddies(self):
        return self.connected_taste_buddies

    def addRemoteSearchPeer(self, permid, oversion, ntorrents, last_seen):
        if oversion >= OLPROTO_VER_SIXTH and ntorrents >= REMOTE_SEARCH_PEER_NTORRENTS_THRESHOLD:
            insort(self.remote_search_peer_candidates, [last_seen, permid, oversion])
            if len(self.remote_search_peer_candidates) > self.num_search_cand:
                self.remote_search_peer_candidates.pop(0)

    def getRemoteSearchPeers(self, npeers, minoversion = None):
        if len(self.remote_search_peer_candidates) > npeers:
            _peers = sample(self.remote_search_peer_candidates, npeers)
        else:
            _peers = self.remote_search_peer_candidates
        peers = []
        for p in _peers:
            last_seen, permid, selversion = p
            if minoversion is None or selversion >= minoversion:
                peers.append(permid)

        local_peers = self.data_handler.getLocalPeerList(max_peers=5, minoversion=minoversion)
        if DEBUG:
            print >> sys.stderr, 'bc: getRemoteSearchPeers: Selected %d local peers' % len(local_peers)
        return local_peers + peers


class DataHandler():

    def __init__(self, launchmany, overlay_bridge, max_num_peers = 2500):
        self.launchmany = launchmany
        self.overlay_bridge = overlay_bridge
        self.config = self.launchmany.session.sessconfig
        self.peer_db = launchmany.peer_db
        self.superpeer_db = launchmany.superpeer_db
        self.torrent_db = launchmany.torrent_db
        self.mypref_db = launchmany.mypref_db
        self.pref_db = launchmany.pref_db
        self.simi_db = launchmany.simi_db
        self.friend_db = launchmany.friend_db
        self.pops_db = launchmany.pops_db
        self.myfriends = set()
        self.myprefs = []
        self.peers = {}
        self.default_peer = [0, 0, None]
        self.permid = self.getMyPermid()
        self.ntorrents = 0
        self.last_check_ntorrents = 0
        self.max_num_peers = min(max(max_num_peers, 100), 2500)
        self.old_peer_num = 0
        self.buddycast_core = None
        self.all_peer_list = None
        self.num_peers_ui = None
        self.num_torrents_ui = None
        self.cached_updates = {'peer': {},
         'torrent': {}}
        self.launchmany.session.add_observer(self.sesscb_ntfy_myprefs, NTFY_MYPREFERENCES, [NTFY_INSERT, NTFY_DELETE])

    def commit(self):
        self.peer_db.commit()

    def register_buddycast_core(self, buddycast_core):
        self.buddycast_core = buddycast_core

    def getMyName(self, name = ''):
        return self.config.get('nickname', name)

    def getMyIp(self, ip = ''):
        return self.launchmany.get_ext_ip()

    def getMyPort(self, port = 0):
        return self.launchmany.listen_port

    def getMyPermid(self, permid = ''):
        return self.launchmany.session.get_permid()

    def getPeerID(self, permid):
        if isinstance(permid, int) and permid > 0:
            return permid
        else:
            return self.peer_db.getPeerID(permid)

    def getTorrentID(self, infohash):
        if isinstance(infohash, int) and infohash > 0:
            return infohash
        else:
            return self.torrent_db.getTorrentID(infohash)

    def getPeerPermid(self, peer_id):
        return self.peer_db.getPermid(peer_id)

    def getLocalPeerList(self, max_peers, minoversion = None):
        return self.peer_db.getLocalPeerList(max_peers, minoversion=minoversion)

    def postInit(self, delay = 4, batch = 50, update_interval = 10, npeers = None, updatesim = True):
        if npeers is None:
            npeers = self.max_num_peers
        self.updateMyPreferences()
        self.loadAllPeers(npeers)
        if updatesim:
            self.updateAllSim(delay, batch, update_interval)

    def updateMyPreferences(self, num_pref = None):
        res = self.mypref_db.getAll('torrent_id', order_by='creation_time desc', limit=num_pref)
        self.myprefs = [ p[0] for p in res ]

    def loadAllPeers(self, num_peers = None):
        peer_values = self.peer_db.getAll(['peer_id', 'similarity', 'last_seen'], order_by='last_connected desc', limit=num_peers)
        self.peers = dict(zip([ p[0] for p in peer_values ], [ [p[1], p[2], array('l', [])] for p in peer_values ]))

    def updateAllSim(self, delay = 4, batch = 50, update_interval = 10):
        self._updateAllPeerSim(delay, batch, update_interval)

    def cacheSimUpdates(self, update_table, updates, delay, batch, update_interval):
        self.cached_updates[update_table].update(updates)
        self.overlay_bridge.add_task(lambda : self.checkSimUpdates(batch, update_interval), delay, 'checkSimUpdates')

    def checkSimUpdates(self, batch, update_interval):
        last_update = 0
        if self.cached_updates['peer']:
            updates = []
            update_peers = self.cached_updates['peer']
            keys = update_peers.keys()
            shuffle(keys)
            for key in keys[:batch]:
                updates.append((update_peers.pop(key), key))

            self.overlay_bridge.add_task(lambda : self.peer_db.updatePeerSims(updates), last_update + update_interval, 'updatePeerSims')
            last_update += update_interval
        if self.cached_updates['torrent']:
            updates = []
            update_peers = self.cached_updates['torrent']
            keys = update_peers.keys()
            shuffle(keys)
            for key in keys[:batch]:
                updates.append((update_peers.pop(key), key))

            self.overlay_bridge.add_task(lambda : self.torrent_db.updateTorrentRelevances(updates), last_update + update_interval, 'updateTorrentRelevances')
            last_update += update_interval
        if self.cached_updates['peer'] or self.cached_updates['torrent']:
            self.overlay_bridge.add_task(lambda : self.checkSimUpdates(batch, update_interval), last_update + 0.001, 'checkSimUpdates')

    def _updateAllPeerSim(self, delay, batch, update_interval):
        updates = {}
        if len(self.myprefs) > 0:
            not_peer_id = self.getPeerID(self.permid)
            similarities = P2PSim_Full(self.simi_db.getPeersWithOverlap(not_peer_id, self.myprefs), len(self.myprefs))
            for peer_id in self.peers:
                if peer_id in similarities:
                    oldsim = self.peers[peer_id][PEER_SIM_POS]
                    sim = similarities[peer_id]
                    updates[peer_id] = sim

        if updates:
            self.cacheSimUpdates('peer', updates, delay, batch, update_interval)

    def _updateAllItemRel(self, delay, batch, update_interval):
        pass

    def sesscb_ntfy_myprefs(self, subject, changeType, objectID, *args):
        if DEBUG:
            print >> sys.stderr, 'bc: sesscb_ntfy_myprefs:', subject, changeType, `objectID`
        if subject == NTFY_MYPREFERENCES:
            infohash = objectID
            if changeType == NTFY_INSERT:
                op_my_pref_lambda = lambda : self.addMyPref(infohash)
            elif changeType == NTFY_DELETE:
                op_my_pref_lambda = lambda : self.delMyPref(infohash)
            self.overlay_bridge.add_task(op_my_pref_lambda, 0)

    def addMyPref(self, infohash):
        infohash_str = bin2str(infohash)
        torrentdata = self.torrent_db.getOne(('secret', 'torrent_id'), infohash=infohash_str)
        if not torrentdata:
            return
        secret = torrentdata[0]
        torrent_id = torrentdata[1]
        if secret:
            if DEBUG:
                print >> sys.stderr, 'bc: Omitting secret download: %s' % torrentdata.get('info', {}).get('name', 'unknown')
            return
        if torrent_id not in self.myprefs:
            insort(self.myprefs, torrent_id)
            self.old_peer_num = 0
            self.updateAllSim()

    def delMyPref(self, infohash):
        torrent_id = self.torrent_db.getTorrentID(infohash)
        if torrent_id in self.myprefs:
            self.myprefs.remove(torrent_id)
            self.old_peer_num = 0
            self.updateAllSim()

    def initRemoteSearchPeers(self, num_peers = 10):
        peer_values = self.peer_db.getAll(['permid',
         'oversion',
         'num_torrents',
         'last_seen'], order_by='last_seen desc', limit=num_peers)
        for p in peer_values:
            p = list(p)
            p[0] = str2bin(p[0])
            self.buddycast_core.addRemoteSearchPeer(*tuple(p))

    def getMyLivePreferences(self, selversion, num = 0):
        if selversion >= OLPROTO_VER_ELEVENTH:
            return self.mypref_db.getRecentLivePrefListOL11(num)
        elif selversion >= OLPROTO_VER_EIGHTH:
            return self.mypref_db.getRecentLivePrefListWithClicklog(num)
        else:
            return self.mypref_db.getRecentLivePrefList(num)

    def getPeerSim(self, peer_permid, read_db = False, raw = False):
        if read_db:
            sim = self.peer_db.getPeerSim(peer_permid)
        else:
            peer_id = self.getPeerID(peer_permid)
            if peer_id is None or peer_id not in self.peers:
                sim = 0
            else:
                sim = self.peers[peer_id][PEER_SIM_POS]
        if sim is None:
            sim = 0
        if not raw:
            return abs(sim)
        else:
            return sim

    def getPeerServices(self, peer_permid):
        services = self.peer_db.getPeerServices(peer_permid)
        return services

    def getPeerLastSeen(self, peer_permid):
        peer_id = self.getPeerID(peer_permid)
        return self.getPeerIDLastSeen(peer_id)

    def getPeerIDLastSeen(self, peer_id):
        if not peer_id or peer_id not in self.peers:
            return 0
        return self.peers[peer_id][PEER_LASTSEEN_POS]

    def getPeerPrefList(self, peer_permid):
        return self.pref_db.getPrefList(peer_permid)

    def _addPeerToCache(self, peer_permid, last_seen):
        if peer_permid == self.permid:
            return
        peer_id = self.getPeerID(peer_permid)
        if peer_id not in self.peers:
            sim = self.peer_db.getPeerSim(peer_permid)
            peerprefs = self.pref_db.getPrefList(peer_permid)
            self.peers[peer_id] = [last_seen, sim, array('l', peerprefs)]
        else:
            self.peers[peer_id][PEER_LASTSEEN_POS] = last_seen

    def _addPeerToDB(self, peer_permid, peer_data, commit = True):
        if peer_permid == self.permid:
            return
        new_peer_data = {}
        try:
            new_peer_data['permid'] = peer_data['permid']
            new_peer_data['ip'] = hostname_or_ip2ip(peer_data['ip'])
            new_peer_data['port'] = peer_data['port']
            new_peer_data['last_seen'] = peer_data['last_seen']
            if peer_data.has_key('name'):
                new_peer_data['name'] = dunno2unicode(peer_data['name'])
            self.peer_db.addPeer(peer_permid, new_peer_data, update_dns=True, commit=commit)
        except KeyError:
            print_exc()
            print >> sys.stderr, 'bc: _addPeerToDB has KeyError'
        except socket.gaierror:
            print >> sys.stderr, 'bc: _addPeerToDB cannot find host by name', peer_data['ip']
        except:
            print_exc()

    def addInfohashes(self, infohash_list, commit = True):
        for infohash in infohash_list:
            self.torrent_db.addInfohash(infohash, commit=False)

        if commit:
            self.torrent_db.commit()

    def addPeerPreferences(self, peer_permid, prefs, selversion, recvTime, commit = True):
        if peer_permid == self.permid:
            return 0
        cur_prefs = self.getPeerPrefList(peer_permid)
        if not cur_prefs:
            cur_prefs = []
        prefs2add = []
        pops2update = []
        for pref in prefs:
            infohash = pref['infohash']
            torrent_id = self.torrent_db.getTorrentID(infohash)
            if not torrent_id:
                print >> sys.stderr, 'buddycast: DB Warning: infohash', bin2str(infohash), 'should have been inserted into db, but was not found'
                continue
            pref['torrent_id'] = torrent_id
            if torrent_id not in cur_prefs:
                prefs2add.append(pref)
                cur_prefs.append(torrent_id)
            elif selversion >= OLPROTO_VER_ELEVENTH:
                pops2update.append(pref)

        if len(prefs2add) > 0:
            self.pref_db.addPreferences(peer_permid, prefs2add, recvTime, is_torrent_id=True, commit=commit)
            peer_id = self.getPeerID(peer_permid)
            self.updateSimilarity(peer_id, commit=commit)
        if len(pops2update) > 0:
            self.pops_db.addPopularityRecord(peer_permid, pops2update, selversion, recvTime, is_torrent_id=True, commit=commit)

    def addCollectedTorrentsPopularity(self, peer_permid, colls, selversion, recvTime, commit = True):
        if peer_permid == self.permid:
            return 0
        if selversion < OLPROTO_VER_ELEVENTH:
            return 0
        pops2update = []
        for coll in colls:
            infohash = coll['infohash']
            torrent_id = self.torrent_db.getTorrentID(infohash)
            if not torrent_id:
                print >> sys.stderr, 'buddycast: DB Warning: infohash', bin2str(infohash), 'should have been inserted into db, but was not found'
                continue
            coll['torrent_id'] = torrent_id
            pops2update.append(coll)

        if len(pops2update) > 0:
            self.pops_db.addPopularityRecord(peer_permid, pops2update, selversion, recvTime, is_torrent_id=True, commit=commit)

    def updateSimilarity(self, peer_id, update_db = True, commit = True):
        if len(self.myprefs) == 0:
            return
        sim = P2PSim_Single(self.simi_db.getOverlapWithPeer(peer_id, self.myprefs), len(self.myprefs))
        self.peers[peer_id][PEER_SIM_POS] = sim
        if update_db and sim > 0:
            self.peer_db.updatePeerSims([(sim, peer_id)], commit=commit)

    def getPeer(self, permid, keys = None):
        return self.peer_db.getPeer(permid, keys)

    def addRelativeSim(self, sender_permid, peer_permid, sim, max_sim):
        old_sim = self.getPeerSim(peer_permid, raw=True)
        if old_sim > 0:
            return
        old_sim = abs(old_sim)
        sender_sim = self.getPeerSim(sender_permid)
        new_sim = sender_sim * sim / max_sim
        if old_sim == 0:
            peer_sim = new_sim
        else:
            peer_sim = (new_sim + old_sim) / 2
        peer_sim = -1 * peer_sim
        peer_id = self.getPeerID(peer_permid)
        self.peers[peer_id][PEER_SIM_POS] = peer_sim

    def get_npeers(self):
        if self.num_peers_ui is None:
            return len(self.peers)
        else:
            return self.num_peers_ui

    def get_ntorrents(self):
        if self.num_torrents_ui is None:
            _now = now()
            if _now - self.last_check_ntorrents > 300:
                self.ntorrents = self.torrent_db.getNumberCollectedTorrents()
                self.last_check_ntorrents = _now
            return self.ntorrents
        else:
            return self.num_torrents_ui

    def get_nmyprefs(self):
        return len(self.myprefs)

    def handleBCData(self, cache_db_data, cache_peer_data, sender_permid, max_tb_sim, selversion, recvTime):
        ADD_PEER = 1
        UPDATE_PEER = 2
        ADD_INFOHASH = 3
        peer_data = cache_db_data['peer']
        db_writes = []
        for permid in peer_data:
            new_peer = peer_data[permid]
            old_peer = self.peer_db.getPeer(permid)
            if not old_peer:
                if permid == sender_permid:
                    new_peer['buddycast_times'] = 1
                db_writes.append((ADD_PEER, permid, new_peer))
            else:
                old_last_seen = old_peer['last_seen']
                new_last_seen = new_peer['last_seen']
                if permid == sender_permid:
                    if not old_peer['buddycast_times']:
                        new_peer['buddycast_times'] = 1
                    else:
                        new_peer['buddycast_times'] = +1
                if not old_last_seen or new_last_seen > old_last_seen + 14400:
                    for k in new_peer.keys():
                        if old_peer[k] == new_peer[k]:
                            new_peer.pop(k)

                if new_peer:
                    db_writes.append((UPDATE_PEER, permid, new_peer))

        for infohash in cache_db_data['infohash']:
            tid = self.torrent_db.getTorrentID(infohash)
            if tid is None:
                db_writes.append((ADD_INFOHASH, infohash))

        for item in db_writes:
            if item[0] == ADD_PEER:
                permid = item[1]
                new_peer = item[2]
                updateDNS = permid != sender_permid
                self.peer_db.addPeer(permid, new_peer, update_dns=updateDNS, commit=False)
            elif item[0] == UPDATE_PEER:
                permid = item[1]
                new_peer = item[2]
                updateDNS = permid != sender_permid
                if not updateDNS:
                    if 'ip' in new_peer:
                        del new_peer['ip']
                    if 'port' in new_peer:
                        del new_peer['port']
                self.peer_db.updatePeer(permid, commit=False, **new_peer)
            elif item[0] == ADD_INFOHASH:
                infohash = item[1]
                self.torrent_db.addInfohash(infohash, commit=False)

        self.torrent_db.commit()
        for item in db_writes:
            if item[0] == ADD_PEER or item[0] == UPDATE_PEER:
                permid = item[1]
                new_peer = item[2]
                last_seen = new_peer['last_seen']
                self._addPeerToCache(permid, last_seen)

        for permid in peer_data:
            if 'sim' in peer_data[permid]:
                sim = peer_data[permid]['sim']
                self.addRelativeSim(sender_permid, permid, sim, max_tb_sim)

        self.torrent_db.commit()
        if cache_db_data['pref']:
            self.addPeerPreferences(sender_permid, cache_db_data['pref'], selversion, recvTime, commit=True)
        if cache_db_data['coll']:
            self.addCollectedTorrentsPopularity(sender_permid, cache_db_data['coll'], selversion, recvTime, commit=True)
