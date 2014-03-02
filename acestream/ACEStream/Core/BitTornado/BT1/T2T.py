#Embedded file name: ACEStream\Core\BitTornado\BT1\T2T.pyo
from Rerequester import Rerequester
from urllib import quote
from threading import Event
from random import randrange
import __init__
try:
    True
except:
    True = 1
    False = 0

DEBUG = False

def excfunc(x):
    print x


class T2TConnection:

    def __init__(self, myid, tracker, hash, interval, peers, timeout, rawserver, disallow, isdisallowed):
        self.tracker = tracker
        self.interval = interval
        self.hash = hash
        self.operatinginterval = interval
        self.peers = peers
        self.rawserver = rawserver
        self.disallow = disallow
        self.isdisallowed = isdisallowed
        self.active = True
        self.busy = False
        self.errors = 0
        self.rejected = 0
        self.trackererror = False
        self.peerlists = []
        self.rerequester = Rerequester([[tracker]], interval, rawserver.add_task, lambda : 0, peers, self.addtolist, rawserver.add_task, lambda : 1, 0, 0, 0, '', myid, hash, timeout, self.errorfunc, excfunc, peers, Event(), lambda : 0, lambda : 0)
        if self.isactive():
            rawserver.add_task(self.refresh, randrange(int(self.interval / 10), self.interval))

    def isactive(self):
        if self.isdisallowed(self.tracker):
            self.deactivate()
        return self.active

    def deactivate(self):
        self.active = False

    def refresh(self):
        if not self.isactive():
            return
        self.lastsuccessful = True
        self.newpeerdata = []
        if DEBUG:
            print 'contacting %s for info_hash=%s' % (self.tracker, quote(self.hash))
        self.rerequester.snoop(self.peers, self.callback)

    def callback(self):
        self.busy = False
        if self.lastsuccessful:
            self.errors = 0
            self.rejected = 0
            if self.rerequester.announce_interval > 3 * self.interval:
                self.peers = int(self.peers * (self.rerequester.announce_interval / self.interval))
            self.operatinginterval = self.rerequester.announce_interval
            if DEBUG:
                print '%s with info_hash=%s returned %d peers' % (self.tracker, quote(self.hash), len(self.newpeerdata))
            self.peerlists.append(self.newpeerdata)
            self.peerlists = self.peerlists[-10:]
        if self.isactive():
            self.rawserver.add_task(self.refresh, self.operatinginterval)

    def addtolist(self, peers):
        for peer in peers:
            self.newpeerdata.append((peer[1], peer[0][0], peer[0][1]))

    def errorfunc(self, r):
        self.lastsuccessful = False
        if DEBUG:
            print "%s with info_hash=%s gives error: '%s'" % (self.tracker, quote(self.hash), r)
        if r == self.rerequester.rejectedmessage + 'disallowed':
            if DEBUG:
                print ' -- disallowed - deactivating'
            self.deactivate()
            self.disallow(self.tracker)
            return
        if r[:8].lower() == 'rejected':
            self.rejected += 1
            if self.rejected == 3:
                if DEBUG:
                    print ' -- rejected 3 times - deactivating'
                self.deactivate()
            return
        self.errors += 1
        if self.errors >= 3:
            self.operatinginterval += self.interval
            if DEBUG:
                print ' -- lengthening interval to ' + str(self.operatinginterval) + ' seconds'

    def harvest(self):
        x = []
        for list in self.peerlists:
            x += list

        self.peerlists = []
        return x


class T2TList:

    def __init__(self, enabled, trackerid, interval, maxpeers, timeout, rawserver):
        self.enabled = enabled
        self.trackerid = trackerid
        self.interval = interval
        self.maxpeers = maxpeers
        self.timeout = timeout
        self.rawserver = rawserver
        self.list = {}
        self.torrents = {}
        self.disallowed = {}
        self.oldtorrents = []

    def parse(self, allowed_list):
        if not self.enabled:
            return
        newlist = {}
        for hash, data in allowed_list.items():
            if data.has_key('announce-list'):
                for tier in data['announce-list']:
                    for tracker in tier:
                        self.disallowed.setdefault(tracker, False)
                        newlist.setdefault(tracker, {})
                        newlist[tracker][hash] = None

        for tracker, hashdata in self.list.items():
            for hash, t2t in hashdata.items():
                if not newlist.has_key(tracker) or not newlist[tracker].has_key(hash):
                    t2t.deactivate()
                    self.oldtorrents += [t2t]
                else:
                    newlist[tracker][hash] = t2t

            if not newlist.has_key(tracker):
                self.disallowed[tracker] = False

        self.list = newlist
        newtorrents = {}
        for tracker, hashdata in newlist.items():
            for hash, t2t in hashdata.items():
                if t2t is None:
                    hashdata[hash] = T2TConnection(self.trackerid, tracker, hash, self.interval, self.maxpeers, self.timeout, self.rawserver, self._disallow, self._isdisallowed)
                newtorrents.setdefault(hash, [])
                newtorrents[hash] += [hashdata[hash]]

        self.torrents = newtorrents

    def _disallow(self, tracker):
        self.disallowed[tracker] = True

    def _isdisallowed(self, tracker):
        return self.disallowed[tracker]

    def harvest(self, hash):
        harvest = []
        if self.enabled:
            for t2t in self.torrents[hash]:
                harvest += t2t.harvest()

        return harvest
