#Embedded file name: ACEStream\Core\Subtitles\PeerHaveManager.pyo
from __future__ import with_statement
import time
from ACEStream.Core.Subtitles.MetadataDomainObjects import Languages
import threading
PEERS_RESULT_LIMIT = 5
HAVE_VALIDITY_TIME = 604800
CLEANUP_PERIOD = -1

class PeersHaveManager(object):
    __single = None
    _singletonLock = threading.RLock()

    def __init__(self):
        with PeersHaveManager._singletonLock:
            PeersHaveManager.__single = self
        self._haveDb = None
        self._olBridge = None
        self._cleanupPeriod = CLEANUP_PERIOD
        self._haveValidityTime = HAVE_VALIDITY_TIME
        self._langsUtility = Languages.LanguagesProvider.getLanguagesInstance()
        self._firstCleanedUp = False
        self._registered = False

    @staticmethod
    def getInstance():
        with PeersHaveManager._singletonLock:
            if PeersHaveManager.__single == None:
                PeersHaveManager()
        return PeersHaveManager.__single

    def register(self, haveDb, olBridge):
        self._haveDb = haveDb
        self._olBridge = olBridge
        self._registered = True

    def isRegistered(self):
        return self._registered

    def getPeersHaving(self, channel, infohash, bitmask, limit = PEERS_RESULT_LIMIT):
        peersTuples = self._haveDb.getHaveEntries(channel, infohash)
        peers_length = len(peersTuples)
        length = peers_length if peers_length < limit else limit
        results = list()
        for i in range(length):
            peer_id, havemask, timestamp = peersTuples[i]
            if havemask & bitmask == bitmask:
                results.append(peer_id)

        if len(results) == 0:
            results.append(channel)
        return results

    def newHaveReceived(self, channel, infohash, peer_id, havemask):
        timestamp = int(time.time())
        self._haveDb.insertOrUpdateHave(channel, infohash, peer_id, havemask, timestamp)

    def retrieveMyHaveMask(self, channel, infohash):
        localSubtitlesDict = self._haveDb.getLocalSubtitles(channel, infohash)
        havemask = self._langsUtility.langCodesToMask(localSubtitlesDict.keys())
        return havemask

    def startupCleanup(self):
        if not self._firstCleanedUp:
            self._firstCleanedUp = True
            self._schedulePeriodicCleanup()

    def _schedulePeriodicCleanup(self):
        minimumAllowedTS = int(time.time()) - self._haveValidityTime
        self._haveDb.cleanupOldHave(minimumAllowedTS)
        if self._cleanupPeriod > 0:
            self._olBridge.add_task(self._schedulePeriodicCleanup, self._cleanupPeriod)
