#Embedded file name: ACEStream\Core\DecentralizedTracking\repex.pyo
import sys
import os
from time import time as ts_now
from random import shuffle
from traceback import print_exc, print_stack
from threading import RLock, Condition, Event, Thread, currentThread
from binascii import b2a_hex
from ACEStream.Core.simpledefs import *
from ACEStream.Core.exceptions import *
from ACEStream.Core.osutils import *
from ACEStream.Core.DecentralizedTracking.ut_pex import check_ut_pex_peerlist
DEBUG = False
REPEX_DISABLE_BOOTSTRAP = False
REPEX_SWARMCACHE_SIZE = 4
REPEX_STORED_PEX_SIZE = 5
REPEX_PEX_MINSIZE = 1
REPEX_INTERVAL = 20 * 60
REPEX_MIN_INTERVAL = 5 * 60
REPEX_PEX_MSG_MAX_PEERS = 200
REPEX_LISTEN_TIME = 50
REPEX_INITIAL_SOCKETS = 4
REPEX_MAX_SOCKETS = 8
REPEX_SCAN_INTERVAL = 1 * 60

class RePEXerInterface():

    def repex_ready(self, infohash, connecter, encoder, rerequester):
        pass

    def repex_aborted(self, infohash, dlstatus = None):
        pass

    def rerequester_peers(self, peers):
        pass

    def connection_timeout(self, connection):
        pass

    def connection_closed(self, connection):
        pass

    def connection_made(self, connection, ext_support):
        pass

    def got_extend_handshake(self, connection, version = None):
        pass

    def got_ut_pex(self, connection, d):
        pass


def c2infohash_dns(connection):
    infohash = connection.connecter.infohash
    if hasattr(connection, 'got_ut_pex'):
        encr_connection = connection.connection
    else:
        encr_connection = connection
    dns = encr_connection.dns
    return (infohash, dns)


def swarmcache_ts(swarmcache):
    ts = None
    if swarmcache:
        ts = max((v['last_seen'] for v in swarmcache.values()))
    return ts


class RePEXer(RePEXerInterface):
    _observers = []
    lock = RLock()

    @classmethod
    def attach_observer(cls, observer):
        cls.lock.acquire()
        try:
            cls._observers.append(observer)
        finally:
            cls.lock.release()

    @classmethod
    def detach_observer(cls, observer):
        cls.lock.acquire()
        try:
            cls._observers.remove(observer)
        finally:
            cls.lock.release()

    def __init__(self, infohash, swarmcache):
        self.infohash = infohash
        self.connecter = None
        self.encoder = None
        self.rerequest = None
        self.starting_peertable = swarmcache
        self.final_peertable = None
        self.to_pex = []
        self.active_sockets = 0
        self.max_sockets = REPEX_INITIAL_SOCKETS
        self.attempted = set()
        self.live_peers = {}
        self.bt_connectable = set()
        self.bt_ext = set()
        self.bt_pex = set()
        self.dns2version = {}
        self.onlinecount = 0
        self.shufflecount = 0
        self.datacost_bandwidth_keys = ['no_pex_support',
         'no_pex_msg',
         'pex',
         'other']
        self.datacost_counter_keys = ['connection_attempts',
         'connections_made',
         'bootstrap_peers',
         'pex_connections']
        self.datacost = {}
        self.datacost['no_pex_support'] = (0, 0)
        self.datacost['no_pex_msg'] = (0, 0)
        self.datacost['pex'] = (0, 0)
        self.datacost['other'] = (0, 0)
        self.datacost['connection_attempts'] = 0
        self.datacost['connections_made'] = 0
        self.datacost['bootstrap_peers'] = 0
        self.datacost['pex_connections'] = 0
        self.requesting_tracker = False
        self.bootstrap_counter = 0
        self.is_closing = False
        self.done = False
        self.aborted = False
        self.ready = False
        self.ready_ts = -1
        self.end_ts = -1
        if self.starting_peertable is None:
            print >> sys.stderr, 'RePEXer: __init__: swarmcache was None, defaulting to {}'
            self.starting_peertable = {}

    def repex_ready(self, infohash, connecter, encoder, rerequester):
        if infohash != self.infohash:
            print >> sys.stderr, 'RePEXer: repex_ready: wrong infohash:', b2a_hex(infohash)
            return
        if self.done:
            print >> sys.stderr, 'RePEXer: repex_ready: already done'
            return
        if DEBUG:
            print >> sys.stderr, 'RePEXer: repex_ready:', b2a_hex(infohash)
        self.ready = True
        self.ready_ts = ts_now()
        self.connecter = connecter
        self.encoder = encoder
        self.rerequest = rerequester
        self.to_pex = self.starting_peertable.keys()
        self.max_sockets = REPEX_INITIAL_SOCKETS
        for dns in self.starting_peertable:
            self.to_pex.extend([ pexdns for pexdns, flags in self.starting_peertable[dns].get('pex', []) ])

        self.connect_queue()

    def repex_aborted(self, infohash, dlstatus):
        if self.done:
            return
        if infohash != self.infohash:
            print >> sys.stderr, 'RePEXer: repex_aborted: wrong infohash:', b2a_hex(infohash)
            return
        if DEBUG:
            if dlstatus is None:
                status_string = str(None)
            else:
                status_string = dlstatus_strings[dlstatus]
            print >> sys.stderr, 'RePEXer: repex_aborted:', b2a_hex(infohash), status_string
        self.done = True
        self.aborted = True
        self.end_ts = ts_now()
        for observer in self._observers:
            observer.repex_aborted(self, dlstatus)

    def rerequester_peers(self, peers):
        self.requesting_tracker = False
        if peers is not None:
            numpeers = len(peers)
        else:
            numpeers = -1
        if DEBUG:
            print >> sys.stderr, 'RePEXer: rerequester_peers: received %s peers' % numpeers
        if numpeers > 0:
            self.to_pex.extend([ dns for dns, id in peers ])
            self.datacost['bootstrap_peers'] += numpeers
        self.connect_queue()

    def connection_timeout(self, connection):
        infohash, dns = c2infohash_dns(connection)
        if infohash != self.infohash or dns is None:
            return
        if DEBUG:
            print >> sys.stderr, 'RePEXer: connection_timeout: %s:%s' % dns

    def connection_closed(self, connection):
        self.active_sockets -= 1
        if self.active_sockets < 0:
            self.active_sockets = 0
        infohash, dns = c2infohash_dns(connection)
        c = None
        if hasattr(connection, 'got_ut_pex'):
            c = connection
            connection = c.connection
        if infohash != self.infohash or dns is None:
            return
        if DEBUG:
            print >> sys.stderr, 'RePEXer: connection_closed: %s:%s' % dns
        singlesocket = connection.connection
        success = False
        costtype = 'other'
        if c is not None:
            if c.pex_received > 0:
                costtype = 'pex'
                success = True
            elif not c.supports_extend_msg('ut_pex'):
                costtype = 'no_pex_support'
            elif c.pex_received == 0:
                costtype = 'no_pex_msg'
        if costtype:
            d, u = self.datacost[costtype]
            d += singlesocket.data_received
            u += singlesocket.data_sent
            self.datacost[costtype] = (d, u)
        if dns in self.starting_peertable:
            if success:
                self.onlinecount += 1
                self.live_peers[dns]['prev'] = True
            else:
                self.shufflecount += 1
        if dns in self.starting_peertable and not success or self.initial_peers_checked():
            self.max_sockets = REPEX_MAX_SOCKETS
        self.connect_queue()

    def connection_made(self, connection, ext_support):
        infohash, dns = c2infohash_dns(connection)
        if infohash != self.infohash or dns is None:
            return
        if DEBUG:
            print >> sys.stderr, 'RePEXer: connection_made: %s:%s ext_support = %s' % (dns + (ext_support,))
        self.datacost['connections_made'] += 1
        self.bt_connectable.add(dns)
        if ext_support:
            self.bt_ext.add(dns)

            def auto_close(connection = connection.connection, dns = dns):
                if not connection.closed:
                    if DEBUG:
                        print >> sys.stderr, 'RePEXer: auto_close: %s:%s' % dns
                    try:
                        connection.close()
                    except AssertionError as e:
                        if DEBUG:
                            print >> sys.stderr, 'RePEXer: auto_close:', `e`
                        self.connection_closed(connection)

            self.connecter.sched(auto_close, REPEX_LISTEN_TIME)
        else:
            connection.close()

    def got_extend_handshake(self, connection, version = None):
        infohash, dns = c2infohash_dns(connection)
        ut_pex_support = connection.supports_extend_msg('ut_pex')
        if infohash != self.infohash or dns is None:
            return
        if DEBUG:
            print >> sys.stderr, 'RePEXer: got_extend_handshake: %s:%s version = %s ut_pex_support = %s' % (dns + (`version`, ut_pex_support))
        if ut_pex_support:
            self.bt_pex.add(dns)
        else:
            connection.close()
        self.dns2version[dns] = version

    def got_ut_pex(self, connection, d):
        infohash, dns = c2infohash_dns(connection)
        is_tribler_peer = connection.is_tribler_peer()
        added = check_ut_pex_peerlist(d, 'added')[:REPEX_PEX_MSG_MAX_PEERS]
        addedf = map(ord, d.get('addedf', []))[:REPEX_PEX_MSG_MAX_PEERS]
        addedf.extend([0] * (len(added) - len(addedf)))
        IS_SEED = 2
        IS_SAME = 4
        if infohash != self.infohash or dns is None:
            return
        if DEBUG:
            print >> sys.stderr, 'RePEXer: got_ut_pex: %s:%s pex_size = %s' % (dns + (len(added),))
        for i in range(len(added) - 1, -1, -1):
            if added[i][0].startswith('0.'):
                added.pop(i)
                addedf.pop(i)

        if len(added) >= REPEX_PEX_MINSIZE:
            if not is_tribler_peer:
                addedf = [ flag & ~IS_SAME for flag in addedf ]
            picks = range(len(added))
            shuffle(picks)
            pex_peers = [ (added[i], addedf[i]) for i in picks[:REPEX_STORED_PEX_SIZE] ]
            self.live_peers[dns] = {'last_seen': ts_now(),
             'pex': pex_peers,
             'version': self.dns2version[dns]}
        self.datacost['pex_connections'] += 1
        connection.close()

    def initial_peers_checked(self):
        return len(self.starting_peertable) == self.onlinecount + self.shufflecount

    def connect(self, dns, id = 0):
        if dns in self.attempted:
            return
        if DEBUG:
            print >> sys.stderr, 'RePEXer: connecting: %s:%s' % dns
        self.active_sockets += 1
        self.datacost['connection_attempts'] += 1
        self.attempted.add(dns)
        if not self.encoder.start_connection(dns, id, forcenew=True):
            print >> sys.stderr, 'RePEXer: connecting failed: %s:%s' % dns
            self.active_sockets -= 1
            self.datacost['connection_attempts'] -= 1
            if dns in self.starting_peertable:
                self.shufflecount += 1

    def next_peer_from_queue(self):
        if self.can_connect() and self.to_pex:
            return self.to_pex.pop(0)
        else:
            return None

    def can_connect(self):
        return self.active_sockets < self.max_sockets

    def connect_queue(self):
        if DEBUG:
            print >> sys.stderr, 'RePEXer: connect_queue: active_sockets: %s' % self.active_sockets
        if self.done or self.is_closing or not self.can_connect():
            return
        if self.initial_peers_checked() and len(self.live_peers) >= REPEX_SWARMCACHE_SIZE:
            self.is_closing = True
            self.encoder.close_all()
            if self.active_sockets == 0:
                self.send_done()
            return
        peer = self.next_peer_from_queue()
        while peer is not None:
            self.connect(peer)
            peer = self.next_peer_from_queue()

        if self.active_sockets == 0 and self.initial_peers_checked():
            if self.bootstrap_counter == 0:
                self.bootstrap()
            elif not self.requesting_tracker:
                self.send_done()
        if DEBUG:
            print >> sys.stderr, 'RePEXer: connect_queue: active_sockets: %s' % self.active_sockets

    def bootstrap(self):
        if DEBUG:
            print >> sys.stderr, 'RePEXer: bootstrap'
        self.bootstrap_counter += 1
        proxy_mode = self.connecter.config.get('proxy_mode', 0)
        if proxy_mode == PROXY_MODE_PRIVATE:
            self.rerequester_peers(None)
            return
        if REPEX_DISABLE_BOOTSTRAP or self.rerequest is None:
            self.rerequester_peers(None)
            return
        if self.rerequest.trackerlist in [[], [[]]]:
            self.rerequester_peers(None)
            return
        self.requesting_tracker = True

        def tracker_callback(self = self):
            if self.requesting_tracker:
                self.requesting_tracker = False
                self.rerequester_peers(None)

        self.rerequest.announce(callback=tracker_callback)

    def get_swarmcache(self):
        if self.done:
            swarmcache = self.final_peertable
        else:
            swarmcache = self.starting_peertable
        ts = swarmcache_ts(swarmcache)
        return (swarmcache, ts)

    def send_done(self):
        self.done = True
        self.end_ts = ts_now()
        swarmcache = dict(self.live_peers)
        to_delete = max(len(swarmcache) - REPEX_SWARMCACHE_SIZE, 0)
        deleted = 0
        for dns in swarmcache.keys():
            if deleted == to_delete:
                break
            if dns not in self.starting_peertable:
                del swarmcache[dns]
                deleted += 1

        shufflepeers = {}
        for dns in self.starting_peertable:
            if dns not in swarmcache:
                shufflepeers[dns] = (dns in self.bt_connectable, dns in self.bt_pex, self.starting_peertable[dns].get('last_seen', 0))

        self.final_peertable = swarmcache
        for observer in self._observers:
            if DEBUG:
                print >> sys.stderr, 'RePEXer: send_done: calling repex_done on', `observer`
            try:
                observer.repex_done(self, swarmcache, self.shufflecount, shufflepeers, self.bootstrap_counter, self.datacost)
            except:
                print_exc()

    def __str__(self):
        if self.done and self.aborted:
            status = 'ABORTED'
        elif self.done:
            status = 'DONE'
        elif self.ready:
            status = 'REPEXING'
        else:
            status = 'WAITING'
        infohash = '[%s]' % b2a_hex(self.infohash)
        summary = ''
        table = ''
        datacost = ''
        if self.done and not self.aborted:
            infohash = '\n    ' + infohash
            swarmcache = self.final_peertable
            summary = '\n    table size/shuffle/bootstrap %s/%s/%s' % (len(swarmcache), self.shufflecount, self.bootstrap_counter)
            prev_peers = set(self.starting_peertable.keys())
            cur_peers = set(swarmcache.keys())
            for dns in sorted(set.symmetric_difference(prev_peers, cur_peers)):
                if dns in cur_peers:
                    table += '\n        A: %s:%s' % dns
                else:
                    table += '\n        D: %s:%s - BT/PEX %s/%s' % (dns + (dns in self.bt_connectable, dns in self.bt_pex))

            table += '\n'
            datacost = '    datacost:\n        %s(%s)/%s BT(PEX) connections made, received %s bootstrap peers\n'
            datacost %= (self.datacost['connections_made'],
             self.datacost['pex_connections'],
             self.datacost['connection_attempts'],
             self.datacost['bootstrap_peers'])
            for k in self.datacost_bandwidth_keys:
                v = self.datacost[k]
                datacost += '          %s: %s bytes down / %s bytes up\n' % (k.ljust(16), str(v[0]).rjust(6), str(v[1]).rjust(6))

        return '<RePEXer(%s)%s%s%s%s>' % (status,
         infohash,
         summary,
         table,
         datacost)


class RePEXerStatusCallback():

    def repex_aborted(self, repexer, dlstatus = None):
        pass

    def repex_done(self, repexer, swarmcache, shufflecount, shufflepeers, bootstrapcount, datacost):
        pass


class RePEXScheduler(RePEXerStatusCallback):
    __single = None
    lock = RLock()

    @classmethod
    def getInstance(cls, *args, **kw):
        if cls.__single is None:
            cls.lock.acquire()
            try:
                if cls.__single is None:
                    cls.__single = cls(*args, **kw)
            finally:
                cls.lock.release()

        return cls.__single

    def __init__(self):
        if self.__single != None:
            raise RuntimeError, 'RePEXScheduler is singleton'
        from ACEStream.Core.Session import Session
        self.session = Session.get_instance()
        self.lock = RLock()
        self.active = False
        self.current_repex = None
        self.downloads = {}
        self.last_attempts = {}

    def start(self):
        if DEBUG:
            print >> sys.stderr, 'RePEXScheduler: start'
        self.lock.acquire()
        try:
            if self.active:
                return
            self.active = True
            self.session.set_download_states_callback(self.network_scan)
            RePEXer.attach_observer(self)
        finally:
            self.lock.release()

    def stop(self):
        if DEBUG:
            print >> sys.stderr, 'RePEXScheduler: stop'
        self.lock.acquire()
        try:
            if not self.active:
                return
            RePEXer.detach_observer(self)
            self.active = False
            self.session.set_download_states_callback(self.network_stop_repex)
        finally:
            self.lock.release()

    def network_scan(self, dslist):
        if DEBUG:
            print >> sys.stderr, 'RePEXScheduler: network_scan: %s DownloadStates' % len(dslist)
        self.lock.acquire()
        exception = None
        try:
            if not self.active or self.current_repex is not None:
                return (-1, False)
            now = ts_now()
            found_infohash = None
            found_download = None
            found_age = -1
            for ds in dslist:
                download = ds.get_download()
                infohash = download.tdef.get_infohash()
                debug_msg = None
                if DEBUG:
                    print >> sys.stderr, 'RePEXScheduler: network_scan: checking', `(download.tdef.get_name_as_unicode())`
                if ds.get_status() == DLSTATUS_STOPPED and ds.get_progress() == 1.0:
                    age = now - (swarmcache_ts(ds.get_swarmcache()) or 0)
                    last_attempt_ago = now - self.last_attempts.get(infohash, 0)
                    if last_attempt_ago < REPEX_MIN_INTERVAL:
                        debug_msg = '...too soon to try again, last attempt was %ss ago' % last_attempt_ago
                    elif age < REPEX_INTERVAL:
                        debug_msg = '...SwarmCache too fresh: %s seconds' % age
                    elif age >= REPEX_INTERVAL:
                        debug_msg = '...suitable for RePEX!'
                        if age > found_age:
                            found_download = download
                            found_infohash = infohash
                            found_age = age
                else:
                    debug_msg = '...not repexable: %s %s%%' % (dlstatus_strings[ds.get_status()], ds.get_progress() * 100)
                if DEBUG:
                    print >> sys.stderr, 'RePEXScheduler: network_scan:', debug_msg

            if found_download is None:
                if DEBUG:
                    print >> sys.stderr, 'RePEXScheduler: network_scan: nothing found yet'
                return (REPEX_SCAN_INTERVAL, False)
            if DEBUG:
                print >> sys.stderr, 'RePEXScheduler: network_scan: found %s, starting RePEX phase.' % `(found_download.tdef.get_name_as_unicode())`
            self.current_repex = found_infohash
            self.downloads[found_infohash] = found_download
            found_download.set_mode(DLMODE_NORMAL)
            found_download.restart(initialdlstatus=DLSTATUS_REPEXING)
            return (-1, False)
        except Exception as e:
            exception = e
        finally:
            self.lock.release()

        if exception is not None:
            raise exception

    def network_stop_repex(self, dslist):
        if DEBUG:
            print >> sys.stderr, 'RePEXScheduler: network_stop_repex:'
        for d in [ ds.get_download() for ds in dslist if ds.get_status() == DLSTATUS_REPEXING ]:
            if DEBUG:
                print >> sys.stderr, '\t...', `(d.tdef.get_name_as_unicode())`
            d.stop()

        return (-1, False)

    def repex_aborted(self, repexer, dlstatus = None):
        if DEBUG:
            if dlstatus is None:
                status_string = str(None)
            else:
                status_string = dlstatus_strings[dlstatus]
            print >> sys.stderr, 'RePEXScheduler: repex_aborted:', b2a_hex(repexer.infohash), status_string
        self.current_repex = None
        self.last_attempts[repexer.infohash] = ts_now()
        self.session.set_download_states_callback(self.network_scan)

    def repex_done(self, repexer, swarmcache, shufflecount, shufflepeers, bootstrapcount, datacost):
        if DEBUG:
            print >> sys.stderr, 'RePEXScheduler: repex_done: %s\n\ttable size/shuffle/bootstrap %s/%s/%s' % (b2a_hex(repexer.infohash),
             len(swarmcache),
             shufflecount,
             bootstrapcount)
        self.current_repex = None
        self.last_attempts[repexer.infohash] = ts_now()
        self.downloads[repexer.infohash].stop()
        self.session.set_download_states_callback(self.network_scan)


class RePEXLogger(RePEXerStatusCallback):
    __single = None
    lock = RLock()

    @classmethod
    def getInstance(cls, *args, **kw):
        if cls.__single is None:
            cls.lock.acquire()
            try:
                if cls.__single is None:
                    cls.__single = cls(*args, **kw)
            finally:
                cls.lock.release()

        return cls.__single

    def __init__(self):
        if self.__single != None:
            raise RuntimeError, 'RePEXLogger is singleton'
        self.repexlog = RePEXLogDB.getInstance()
        self.active = False

    def start(self):
        if DEBUG:
            print >> sys.stderr, 'RePEXLogger: start'
        self.lock.acquire()
        try:
            if self.active:
                return
            self.active = True
            RePEXer.attach_observer(self)
        finally:
            self.lock.release()

    def stop(self):
        if DEBUG:
            print >> sys.stderr, 'RePEXLogger: stop'
        self.lock.acquire()
        try:
            if not self.active:
                return
            RePEXer.detach_observer(self)
            self.active = False
        finally:
            self.lock.release()

    def repex_aborted(self, repexer, dlstatus = None):
        if dlstatus is None:
            status_string = str(None)
        else:
            status_string = dlstatus_strings[dlstatus]
        if DEBUG:
            print >> sys.stderr, 'RePEXLogger: repex_aborted:', b2a_hex(repexer.infohash), status_string

    def repex_done(self, repexer, swarmcache, shufflecount, shufflepeers, bootstrapcount, datacost):
        if DEBUG:
            print >> sys.stderr, 'RePEXLogger: repex_done: %s' % repexer
        self.repexlog.storeSwarmCache(repexer.infohash, swarmcache, (shufflecount,
         shufflepeers,
         bootstrapcount,
         datacost), timestamp=repexer.ready_ts, endtimestamp=repexer.end_ts, commit=True)


class RePEXLogDB():
    __single = None
    lock = RLock()
    PEERDB_FILE = 'repexlog.pickle'
    PEERDB_VERSION = '0.7'
    MAX_HISTORY = 20480

    @classmethod
    def getInstance(cls, *args, **kw):
        if cls.__single is None:
            cls.lock.acquire()
            try:
                if cls.__single is None:
                    cls.__single = cls(*args, **kw)
            finally:
                cls.lock.release()

        return cls.__single

    def __init__(self, session):
        if self.__single != None:
            raise RuntimeError, 'RePEXLogDB is singleton'
        state_dir = session.get_state_dir()
        self.db = os.path.join(state_dir, self.PEERDB_FILE)
        if not os.path.exists(self.db):
            self.version = self.PEERDB_VERSION
            self.history = []
        else:
            import cPickle as pickle
            f = open(self.db, 'rb')
            tuple = pickle.load(f)
            self.version, self.history = tuple
            f.close()

    def commit(self):
        self.lock.acquire()
        try:
            import cPickle as pickle
            f = open(self.db, 'wb')
            pickle.dump((self.version, self.history), f)
            f.close()
        finally:
            self.lock.release()

    def storeSwarmCache(self, infohash, swarmcache, stats = None, timestamp = -1, endtimestamp = -1, commit = False):
        if DEBUG:
            print >> sys.stderr, 'RePEXLogDB: storeSwarmCache: DEBUG:\n\t%s\n\t%s\n\t%s' % (b2a_hex(infohash), '', '')
        self.lock.acquire()
        try:
            self.history.append((infohash,
             swarmcache,
             stats,
             timestamp,
             endtimestamp))
            if len(self.history) > self.MAX_HISTORY:
                del self.history[:-self.MAX_HISTORY]
            if commit:
                self.commit()
        finally:
            self.lock.release()

    def getHistoryAndCleanup(self):
        self.lock.acquire()
        try:
            res = self.history
            self.history = []
            self.commit()
            return res
        finally:
            self.lock.release()


class RePEXerTester(RePEXerStatusCallback):

    def __init__(self):
        from ACEStream.Core.Session import Session
        self.session = Session.get_instance()
        self.peerdb = RePEXLogDB.getInstance()
        self.downloads = {}
        self.swarmcaches = {}
        self.repexers = {}
        RePEXer.attach_observer(self)

    def stopped_download(self, tdef, dcfg):
        d = self.session.start_download(tdef, dcfg)
        d.stop()
        self.downloads[d.tdef.get_infohash()] = d
        return d

    def test_repex(self, download, swarmcache = None):
        download.stop()
        self.downloads[download.tdef.get_infohash()] = download
        if swarmcache is not None:

            def hack_into_pstate(d = download, swarmcache = swarmcache):
                d.pstate_for_restart.setdefault('dlstate', {})['swarmcache'] = swarmcache

            self.session.lm.rawserver.add_task(hack_into_pstate, 0.0)
        download.set_mode(DLMODE_NORMAL)
        download.restart(initialdlstatus=DLSTATUS_REPEXING)

    def repex_aborted(self, repexer, dlstatus = None):
        if dlstatus is None:
            status_string = str(None)
        else:
            status_string = dlstatus_strings[dlstatus]
        print >> sys.stderr, 'RePEXerTester: repex_aborted:', `repexer`, status_string
        download = self.downloads[repexer.infohash]
        self.repexers.setdefault(download, []).append(repexer)
        self.swarmcaches.setdefault(download, []).append(None)

    def repex_done(self, repexer, swarmcache, shufflecount, shufflepeers, bootstrapcount, datacost):
        download = self.downloads[repexer.infohash]
        print >> sys.stderr, 'RePEXerTester: repex_done: %s' % repexer
        self.repexers.setdefault(download, []).append(repexer)
        self.swarmcaches.setdefault(download, []).append(swarmcache)
        self.peerdb.storeSwarmCache(repexer.infohash, swarmcache, (shufflecount,
         shufflepeers,
         bootstrapcount,
         datacost), timestamp=repexer.ready_ts, endtimestamp=repexer.end_ts, commit=True)
