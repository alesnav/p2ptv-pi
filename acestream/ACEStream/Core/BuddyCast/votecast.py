#Embedded file name: ACEStream\Core\BuddyCast\votecast.pyo
import sys
from time import time
from sets import Set
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
from ACEStream.Core.Statistics.Logger import OverlayLogger
from ACEStream.Core.BitTornado.BT1.MessageID import VOTECAST
from ACEStream.Core.CacheDB.CacheDBHandler import VoteCastDBHandler
from ACEStream.Core.Utilities.utilities import *
from ACEStream.Core.Overlay.permid import permid_for_user
from ACEStream.Core.CacheDB.sqlitecachedb import bin2str, str2bin
from ACEStream.Core.BuddyCast.moderationcast_util import *
from ACEStream.Core.Overlay.SecureOverlay import OLPROTO_VER_THIRTEENTH
from ACEStream.Core.CacheDB.Notifier import Notifier
from ACEStream.Core.simpledefs import NTFY_VOTECAST, NTFY_UPDATE
from ACEStream.Core.CacheDB.SqliteCacheDBHandler import PeerDBHandler
DEBUG_UI = False
DEBUG = False
debug = False
SINGLE_VOTECAST_LENGTH = 130

class VoteCastCore:
    TESTASSERVER = False

    def __init__(self, data_handler, secure_overlay, session, buddycast_interval_function, log = '', dnsindb = None):
        self.interval = buddycast_interval_function
        self.data_handler = data_handler
        self.dnsindb = dnsindb
        self.log = log
        self.peerdb = PeerDBHandler.getInstance()
        self.votecastdb = VoteCastDBHandler.getInstance()
        self.session = session
        self.my_permid = session.get_permid()
        self.max_length = SINGLE_VOTECAST_LENGTH * (session.get_votecast_random_votes() + session.get_votecast_recent_votes())
        self.buddycast_core = None
        self.notifier = Notifier.getInstance()
        if self.log:
            self.overlay_log = OverlayLogger.getInstance(self.log)

    def initialized(self):
        return self.buddycast_core is not None

    def createVoteCastMessage(self):
        pass

    def gotVoteCastMessage(self, recv_msg, sender_permid, selversion):
        if selversion < OLPROTO_VER_THIRTEENTH:
            if DEBUG:
                print >> sys.stderr, 'votecast: Do not receive from lower version peer:', selversion
            return True
        if DEBUG:
            print >> sys.stderr, 'votecast: Received a msg from ', show_permid_short(sender_permid)
        if not sender_permid or sender_permid == self.my_permid:
            if DEBUG:
                print >> sys.stderr, 'votecast: error - got votecastMsg from a None peer', show_permid_short(sender_permid), recv_msg
            return False
        if self.max_length > 0 and len(recv_msg) > self.max_length:
            if DEBUG:
                print >> sys.stderr, 'votecast: warning - got large voteCastHaveMsg; msg_size:', len(recv_msg)
            return False
        votecast_data = {}
        try:
            votecast_data = bdecode(recv_msg)
        except:
            print >> sys.stderr, 'votecast: warning, invalid bencoded data'
            return False

        if not validVoteCastMsg(votecast_data):
            print >> sys.stderr, 'votecast: warning, invalid votecast_message'
            return False
        self.handleVoteCastMsg(sender_permid, votecast_data)
        if self.log:
            dns = self.dnsindb(sender_permid)
            if dns:
                ip, port = dns
                MSG_ID = 'VOTECAST'
                msg = voteCastMsgToString(votecast_data)
                self.overlay_log('RECV_MSG', ip, port, show_permid(sender_permid), selversion, MSG_ID, msg)
        return True

    def handleVoteCastMsg(self, sender_permid, data):
        if DEBUG:
            print >> sys.stderr, 'votecast: Processing VOTECAST msg from: ', show_permid_short(sender_permid), '; data: ', repr(data)
        modified_channels = set()
        votes = []
        voter_id = self.peerdb.getPeerID(sender_permid)
        for key, value in data.items():
            channel_id = self.peerdb.getPeerID(key)
            vote = value['vote']
            time_stamp = value['time_stamp']
            votes.append((channel_id,
             voter_id,
             vote,
             time_stamp))
            modified_channels.add(channel_id)

        self.votecastdb.addVotes(votes)
        for channel_id in modified_channels:
            try:
                self.notifier.notify(NTFY_VOTECAST, NTFY_UPDATE, channel_id)
            except:
                print_exc()

        if DEBUG:
            print >> sys.stderr, 'votecast: Processing VOTECAST msg from: ', show_permid_short(sender_permid), 'DONE; data:'
