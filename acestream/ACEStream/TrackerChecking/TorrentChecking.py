#Embedded file name: ACEStream\TrackerChecking\TorrentChecking.pyo
import sys
import threading
from threading import Thread
from random import sample
from time import time
from ACEStream.Core.BitTornado.bencode import bdecode
from ACEStream.TrackerChecking.TrackerChecking import trackerChecking
from ACEStream.Core.CacheDB.sqlitecachedb import safe_dict
from ACEStream.Core.CacheDB.CacheDBHandler import TorrentDBHandler
from ACEStream.Core.DecentralizedTracking.mainlineDHTChecker import mainlineDHTChecker
DEBUG = False

class TorrentChecking(Thread):

    def __init__(self, infohash = None):
        Thread.__init__(self)
        self.setName('TorrentChecking' + self.getName())
        if DEBUG:
            print >> sys.stderr, 'TorrentChecking: Started torrentchecking', threading.currentThread().getName()
        self.setDaemon(True)
        self.infohash = infohash
        self.retryThreshold = 10
        self.gnThreashold = 0.9
        self.mldhtchecker = mainlineDHTChecker.getInstance()
        self.db_thread = None

    def selectPolicy(self):
        policies = ['oldest', 'random', 'popular']
        return sample(policies, 1)[0]

    def readTorrent(self, torrent):
        try:
            torrent_path = torrent['torrent_path']
            f = open(torrent_path, 'rb')
            _data = f.read()
            f.close()
            data = bdecode(_data)
            del data['info']
            torrent['info'] = data
            return torrent
        except Exception:
            return torrent

    def run(self):
        try:
            if DEBUG:
                print >> sys.stderr, 'Torrent Checking: RUN', threading.currentThread().getName()
            event = threading.Event()
            return_value = safe_dict()
            return_value['event'] = event
            return_value['torrent'] = None
            if self.infohash is None:
                policy = self.selectPolicy()
                if self.db_thread:
                    self.db_thread.add_task(lambda : TorrentDBHandler.getInstance().selectTorrentToCheck(policy=policy, return_value=return_value))
                else:
                    TorrentDBHandler.getInstance().selectTorrentToCheck(policy=policy, return_value=return_value)
            elif self.db_thread:
                self.db_thread.add_task(lambda : TorrentDBHandler.getInstance().selectTorrentToCheck(infohash=self.infohash, return_value=return_value))
            else:
                TorrentDBHandler.getInstance().selectTorrentToCheck(infohash=self.infohash, return_value=return_value)
            event.wait(60.0)
            torrent = return_value['torrent']
            if DEBUG:
                print >> sys.stderr, 'Torrent Checking: get value from DB:', torrent
            if not torrent:
                return
            if self.infohash is None and torrent['ignored_times'] > 0:
                if DEBUG:
                    print >> sys.stderr, 'Torrent_checking: torrent: %s' % torrent
                kw = {'ignored_times': torrent['ignored_times'] - 1}
                if self.db_thread:
                    self.db_thread.add_task(lambda : TorrentDBHandler.getInstance().updateTracker(torrent['infohash'], kw))
                else:
                    TorrentDBHandler.getInstance().updateTracker(torrent['infohash'], kw)
                return
            torrent = self.readTorrent(torrent)
            if 'info' not in torrent:
                if self.db_thread:
                    self.db_thread.add_task(lambda : TorrentDBHandler.getInstance().deleteTorrent(torrent['infohash']))
                else:
                    TorrentDBHandler.getInstance().deleteTorrent(torrent['infohash'])
                return
            if DEBUG:
                print >> sys.stderr, 'Tracker Checking'
            trackerChecking(torrent)
            self.mldhtchecker.lookup(torrent['infohash'])
            self.updateTorrentInfo(torrent)
            kw = {'last_check_time': int(time()),
             'seeder': torrent['seeder'],
             'leecher': torrent['leecher'],
             'status': torrent['status'],
             'ignored_times': torrent['ignored_times'],
             'retried_times': torrent['retried_times']}
            if DEBUG:
                print >> sys.stderr, 'Torrent Checking: selectTorrentToCheck:', kw
            if self.db_thread:
                self.db_thread.add_task(lambda : TorrentDBHandler.getInstance().updateTorrent(torrent['infohash'], **kw))
            else:
                TorrentDBHandler.getInstance().updateTorrent(torrent['infohash'], **kw)
        finally:
            if not self.db_thread:
                TorrentDBHandler.getInstance().close()

    def updateTorrentInfo(self, torrent):
        if torrent['status'] == 'good':
            torrent['ignored_times'] = 0
        elif torrent['status'] == 'unknown':
            if torrent['retried_times'] > self.retryThreshold:
                torrent['ignored_times'] = 0
                torrent['status'] = 'dead'
            else:
                torrent['retried_times'] += 1
                torrent['ignored_times'] = torrent['retried_times']
        elif torrent['status'] == 'dead':
            if torrent['retried_times'] < self.retryThreshold:
                torrent['retried_times'] += 1

    def tooMuchRetry(self, torrent):
        if torrent['retried_times'] > self.retryThreshold:
            return True
        return False


if __name__ == '__main__':
    from ACEStream.Core.CacheDB.sqlitecachedb import init as init_db, str2bin
    configure_dir = sys.argv[1]
    config = {}
    config['state_dir'] = configure_dir
    config['install_dir'] = '.'
    config['peer_icon_path'] = '.'
    init_db(config)
    t = TorrentChecking()
    t.start()
    t.join()
    infohash_str = 'TkFX5S4qd2DPW63La/VObgOH/Nc='
    infohash = str2bin(infohash_str)
    del t
    t = TorrentChecking(infohash)
    t.start()
    t.join()
