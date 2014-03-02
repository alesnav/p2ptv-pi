#Embedded file name: ACEStream\Core\RequestPolicy.pyo
from ACEStream.Core.simpledefs import *
from ACEStream.Core.exceptions import *
from ACEStream.Core.BitTornado.BT1.MessageID import *
DEBUG = False
MAX_QUERIES_FROM_RANDOM_PEER = 1000

class AbstractRequestPolicy:

    def __init__(self):
        pass

    def allowed(self, permid, messageID):
        raise NotYetImplementedException()


class AllowAllRequestPolicy(AbstractRequestPolicy):

    def allowed(self, permid, messageID):
        return self.allowAllRequestsAllPeers(permid, messageID)

    def allowAllRequestsAllPeers(self, permid, messageID):
        return True


class CommonRequestPolicy(AbstractRequestPolicy):

    def __init__(self, session):
        self.session = session
        self.friendsdb = session.open_dbhandler(NTFY_FRIENDS)
        self.peerdb = session.open_dbhandler(NTFY_PEERS)
        AbstractRequestPolicy.__init__(self)

    def isFriend(self, permid):
        fs = self.friendsdb.getFriendState(permid)
        return fs == FS_MUTUAL or fs == FS_I_INVITED

    def isSuperPeer(self, permid):
        return permid in self.session.lm.superpeer_db.getSuperPeers()

    def isCrawler(self, permid):
        return permid in self.session.lm.crawler_db.getCrawlers()

    def benign_random_peer(self, permid):
        if MAX_QUERIES_FROM_RANDOM_PEER > 0:
            nqueries = self.get_peer_nqueries(permid)
            return nqueries < MAX_QUERIES_FROM_RANDOM_PEER
        else:
            return True

    def get_peer_nqueries(self, permid):
        peer = self.peerdb.getPeer(permid)
        if peer is None:
            return 0
        else:
            return peer['num_queries']


class AllowFriendsRequestPolicy(CommonRequestPolicy):

    def allowed(self, permid, messageID):
        if messageID in (CRAWLER_REQUEST, CRAWLER_REPLY):
            return self.isCrawler(permid)
        else:
            return self.allowAllRequestsFromFriends(permid, messageID)

    def allowAllRequestsFromFriends(self, permid, messageID):
        return self.isFriend(permid)


class FriendsCoopDLOtherRQueryQuotumCrawlerAllowAllRequestPolicy(CommonRequestPolicy):

    def allowed(self, permid, messageID):
        if messageID == CRAWLER_REQUEST:
            return self.isCrawler(permid)
        elif messageID == QUERY and not (self.isFriend(permid) or self.benign_random_peer(permid)):
            return False
        else:
            return True
