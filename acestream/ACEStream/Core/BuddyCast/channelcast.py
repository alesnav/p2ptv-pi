#Embedded file name: ACEStream\Core\BuddyCast\channelcast.pyo
import sys
import threading
from time import time, ctime, sleep
from zlib import compress, decompress
from binascii import hexlify
from traceback import print_exc, print_stack
from types import StringType, ListType, DictType
from random import randint, sample, seed, random, shuffle
from sha import sha
from sets import Set
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
from ACEStream.Core.Statistics.Logger import OverlayLogger
from ACEStream.Core.BitTornado.BT1.MessageID import CHANNELCAST, BUDDYCAST
from ACEStream.Core.CacheDB.CacheDBHandler import ChannelCastDBHandler, VoteCastDBHandler
from ACEStream.Core.Utilities.unicode import str2unicode
from ACEStream.Core.Utilities.utilities import *
from ACEStream.Core.Overlay.permid import permid_for_user, sign_data, verify_data
from ACEStream.Core.CacheDB.sqlitecachedb import SQLiteCacheDB, bin2str, str2bin, NULL
from ACEStream.Core.CacheDB.Notifier import Notifier
from ACEStream.Core.SocialNetwork.RemoteTorrentHandler import RemoteTorrentHandler
from ACEStream.Core.SocialNetwork.RemoteQueryMsgHandler import RemoteQueryMsgHandler
from ACEStream.Core.BuddyCast.moderationcast_util import *
from ACEStream.Core.Overlay.SecureOverlay import OLPROTO_VER_THIRTEENTH, OLPROTO_VER_FOURTEENTH
from ACEStream.Core.simpledefs import NTFY_CHANNELCAST, NTFY_UPDATE
from ACEStream.Core.Subtitles.RichMetadataInterceptor import RichMetadataInterceptor
from ACEStream.Core.CacheDB.MetadataDBHandler import MetadataDBHandler
from ACEStream.Core.Subtitles.PeerHaveManager import PeersHaveManager
from ACEStream.Core.Subtitles.SubtitlesSupport import SubtitlesSupport
DEBUG = False
NUM_OWN_RECENT_TORRENTS = 15
NUM_OWN_RANDOM_TORRENTS = 10
NUM_OTHERS_RECENT_TORRENTS = 15
NUM_OTHERS_RECENT_TORRENTS = 10
RELOAD_FREQUENCY = 7200

class ChannelCastCore:
    __single = None
    TESTASSERVER = False

    def __init__(self, data_handler, overlay_bridge, session, buddycast_interval_function, log = '', dnsindb = None):
        self.interval = buddycast_interval_function
        self.data_handler = data_handler
        self.dnsindb = dnsindb
        self.log = log
        self.overlay_bridge = overlay_bridge
        self.channelcastdb = ChannelCastDBHandler.getInstance()
        self.votecastdb = VoteCastDBHandler.getInstance()
        self.rtorrent_handler = RemoteTorrentHandler.getInstance()
        self.session = session
        self.my_permid = session.get_permid()
        self.network_delay = 30
        self.buddycast_core = None
        if self.log:
            self.overlay_log = OverlayLogger.getInstance(self.log)
            self.dnsindb = self.data_handler.get_dns_from_peerdb
        self.notifier = Notifier.getInstance()
        self.metadataDbHandler = MetadataDBHandler.getInstance()
        subtitleSupport = SubtitlesSupport.getInstance()
        self.peersHaveManger = PeersHaveManager.getInstance()
        if not self.peersHaveManger.isRegistered():
            self.peersHaveManger.register(self.metadataDbHandler, self.overlay_bridge)

    def initialized(self):
        return self.buddycast_core is not None

    def getInstance(*args, **kw):
        if ChannelCastCore.__single is None:
            ChannelCastCore(*args, **kw)
        return ChannelCastCore.__single

    getInstance = staticmethod(getInstance)

    def gotChannelCastMessage(self, recv_msg, sender_permid, selversion):
        if selversion < OLPROTO_VER_THIRTEENTH:
            if DEBUG:
                print >> sys.stderr, 'channelcast: Do not receive from lower version peer:', selversion
            return True
        if DEBUG:
            print >> sys.stderr, 'channelcast: Received a msg from ', show_permid_short(sender_permid)
            print >> sys.stderr, 'channelcast: my_permid=', show_permid_short(self.my_permid)
        if not sender_permid or sender_permid == self.my_permid:
            if DEBUG:
                print >> sys.stderr, 'channelcast: warning - got channelcastMsg from a None/Self peer', show_permid_short(sender_permid), recv_msg
            return False
        channelcast_data = {}
        try:
            channelcast_data = bdecode(recv_msg)
        except:
            print >> sys.stderr, 'channelcast: warning, invalid bencoded data'
            return False

        if not validChannelCastMsg(channelcast_data):
            print >> sys.stderr, 'channelcast: invalid channelcast_message'
            return False
        for ch in channelcast_data.values():
            if isinstance(ch['publisher_name'], str):
                ch['publisher_name'] = str2unicode(ch['publisher_name'])
            if isinstance(ch['torrentname'], str):
                ch['torrentname'] = str2unicode(ch['torrentname'])

        self.handleChannelCastMsg(sender_permid, channelcast_data)
        if self.log:
            dns = self.dnsindb(sender_permid)
            if dns:
                ip, port = dns
                MSG_ID = 'CHANNELCAST'
                msg = repr(channelcast_data)
                self.overlay_log('RECV_MSG', ip, port, show_permid(sender_permid), selversion, MSG_ID, msg)
        if self.TESTASSERVER:
            self.createAndSendChannelCastMessage(sender_permid, selversion)
        return True

    def handleChannelCastMsg(self, sender_permid, data):
        self._updateChannelInternal(sender_permid, None, data)

    def updateChannel(self, query_permid, query, hits):
        if DEBUG:
            print >> sys.stderr, 'channelcast: sending message to', bin2str(query_permid), query, len(hits)
        return self._updateChannelInternal(query_permid, query, hits)

    def _updateChannelInternal(self, query_permid, query, hits):
        listOfAdditions = list()
        return listOfAdditions
        all_spam_channels = self.votecastdb.getChannelsWithNegVote(None)
        permid_channel_id = self.channelcastdb.getPermChannelIdDict()
        for k, v in hits.items():
            if v['publisher_id'] not in permid_channel_id:
                permid_channel_id[v['publisher_id']] = self.channelcastdb.on_channel_from_channelcast(v['publisher_id'], v['publisher_name'])
            v['channel_id'] = permid_channel_id[v['publisher_id']]
            if v['channel_id'] in all_spam_channels:
                continue
            hit = (v['channel_id'],
             v['publisher_name'],
             v['infohash'],
             'NAME UNKNOWN',
             v['time_stamp'])
            listOfAdditions.append(hit)

        self._updateChannelcastDB(query_permid, query, hits, listOfAdditions)
        return listOfAdditions

    def _updateChannelcastDB(self, query_permid, query, hits, listOfAdditions):
        if DEBUG:
            print >> sys.stderr, 'channelcast: updating channelcastdb', query, len(hits)
        channel_ids = Set()
        infohashes = Set()
        for hit in listOfAdditions:
            channel_ids.add(hit[0])
            infohashes.add(hit[2])

        my_favorites = self.votecastdb.getChannelsWithPosVote(bin2str(self.my_permid))
        for channel_id in my_favorites:
            if channel_id in channel_ids:
                self.updateAChannel(channel_id, [query_permid])

        self.channelcastdb.on_torrents_from_channelcast(listOfAdditions)
        missing_infohashes = {}
        for channel_id in channel_ids:
            for infohash in self.channelcastdb.selectTorrentsToCollect(channel_id):
                missing_infohashes[infohash] = channel_id

        def notify(channel_id):
            self.notifier.notify(NTFY_CHANNELCAST, NTFY_UPDATE, channel_id)

        for infohash, channel_id in missing_infohashes.iteritems():
            if infohash in infohashes:
                self.rtorrent_handler.download_torrent(query_permid, infohash, lambda infohash, metadata, filename: notify(channel_id), 2)
            else:
                self.rtorrent_handler.download_torrent(query_permid, infohash, lambda infohash, metadata, filename: notify(channel_id), 3)

    def updateMySubscribedChannels(self):
        subscribed_channels = self.channelcastdb.getMySubscribedChannels()
        for channel in subscribed_channels:
            permid = self.channelcastdb.getPermidForChannel(channel[0])
            self.updateAChannel(permid)

        self.overlay_bridge.add_task(self.updateMySubscribedChannels, RELOAD_FREQUENCY)

    def updateAChannel(self, publisher_id, peers = None):
        if peers == None:
            peers = RemoteQueryMsgHandler.getInstance().get_connected_peers(OLPROTO_VER_THIRTEENTH)
        shuffle(peers)
        self.overlay_bridge.add_task(lambda : self._sequentialQueryPeers(publisher_id, peers))

    def _sequentialQueryPeers(self, publisher_id, peers):

        def seqtimeout(permid):
            if peers and permid == peers[0][0]:
                peers.pop(0)
                dorequest()

        def seqcallback(query_permid, query, hits):
            self.updateChannel(query_permid, query, hits)
            if peers and query_permid == peers[0][0]:
                peers.pop(0)
                dorequest()

        def dorequest():
            if peers:
                permid, selversion = peers[0]
                q = 'CHANNEL p ' + publisher_id
                self.session.query_peers(q, [permid], usercallback=seqcallback)
                self.overlay_bridge.add_task(lambda : seqtimeout(permid), 30)

        peers = peers[:]
        dorequest()
