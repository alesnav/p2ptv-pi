#Embedded file name: ACEStream\Core\BitTornado\BT1\Rerequester.pyo
import sys
import socket
import random
import struct
import binascii
import urlparse
from ACEStream.Core.BitTornado.zurllib import urlopen
from urllib import quote
from btformats import check_peers
from ACEStream.Core.BitTornado.bencode import bdecode
from threading import Thread, Lock, currentThread
from cStringIO import StringIO
from traceback import print_exc, print_stack
from ACEStream.Core.Utilities.TSCrypto import sha
from ACEStream.Core.Utilities.utilities import test_network_connection
from time import time
from ACEStream.Core.simpledefs import *
from ACEStream.Core.Utilities.logger import log, log_exc
import ACEStream.Core.DecentralizedTracking.mainlineDHT as mainlineDHT
if mainlineDHT.dht_imported:
    from ACEStream.Core.DecentralizedTracking.pymdht.core.identifier import Id, IdError
try:
    from os import getpid
except ImportError:

    def getpid():
        return 1


try:
    True
except:
    True = 1
    False = 0

DEBUG = False
DEBUG_DHT = False
DEBUG_LOCK = False
DEBUG_CHECK_NETWORK_CONNECTION = False
DEBUG_ANNOUNCE = False
mapbase64 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.-'
keys = {}
basekeydata = str(getpid()) + repr(time()) + 'tracker'

def merge_announce(tracker, params):
    if '?' in tracker:
        return tracker + '&' + params[1:]
    else:
        return tracker + params


def add_key(tracker):
    key = ''
    for i in sha(basekeydata + tracker).digest()[-6:]:
        key += mapbase64[ord(i) & 63]

    keys[tracker] = key


def get_key(tracker):
    try:
        return '&key=' + keys[tracker]
    except:
        add_key(tracker)
        return '&key=' + keys[tracker]


class fakeflag():

    def __init__(self, state = False):
        self.state = state

    def wait(self):
        pass

    def isSet(self):
        return self.state


class Rerequester():

    def __init__(self, trackerlist, interval, sched, howmany, minpeers, connect, externalsched, amount_left, up, down, port, ip, myid, infohash, timeout, errorfunc, excfunc, maxpeers, doneflag, upratefunc, downratefunc, unpauseflag = fakeflag(True), config = None, am_video_source = False, is_private = False):
        self.excfunc = excfunc
        newtrackerlist = []
        for tier in trackerlist:
            if len(tier) > 1:
                random.shuffle(tier)
            newtrackerlist += [tier]

        self.trackerlist = newtrackerlist
        self.lastsuccessful = ''
        self.rejectedmessage = 'rejected by tracker - '
        self.port = port
        self.am_video_source = am_video_source
        self.network_check_url_list = []
        self.network_check_url_list.append(['http://google.com', None])
        for t in xrange(len(self.trackerlist)):
            for tr in xrange(len(self.trackerlist[t])):
                tracker_url = self.trackerlist[t][tr]
                if tracker_url != 'http://retracker.local/announce':
                    self.network_check_url_list.append([tracker_url, None])

        self.url = '?info_hash=%s&peer_id=%s&port=%s' % (quote(infohash), quote(myid), str(port))
        self.ip = ip
        self.myid = myid
        self.interval = interval
        self.last = None
        self.trackerid = None
        self.announce_interval = 1800
        self.sched = sched
        self.howmany = howmany
        self.minpeers = minpeers
        self.connect = connect
        self.externalsched = externalsched
        self.amount_left = amount_left
        self.up = up
        self.down = down
        self.timeout = timeout
        self.errorfunc = errorfunc
        self.maxpeers = maxpeers
        self.doneflag = doneflag
        self.upratefunc = upratefunc
        self.downratefunc = downratefunc
        self.unpauseflag = unpauseflag
        self.last_failed = True
        self.never_succeeded = True
        self.errorcodes = {}
        self.lock = SuccessLock(infohash)
        self.network_lock = Lock()
        self.special = None
        self.started = False
        self.stopped = False
        self.schedid = 'rerequest-' + binascii.hexlify(infohash) + '-'
        self.infohash = infohash
        self.log_prefix = 'rerequester::' + binascii.hexlify(self.infohash) + ':'
        if DEBUG:
            log(self.log_prefix + '__init__: ip', ip, 'port', self.port, 'myid', myid, 'quoted_id', quote(myid))
        if is_private:
            if DEBUG:
                log(self.log_prefix + '__init__: private torrent, disable DHT')
            self.dht = None
        else:
            self.dht = mainlineDHT.dht
        self.config = config
        self.notifiers = []

    def start(self):
        if not self.started:
            self.started = True
            self.sched(self.c, self.interval / 2, self.schedid + 'c')
            if DEBUG or DEBUG_ANNOUNCE:
                log(self.log_prefix + 'start: shed(c), self.interval', self.interval)
            if self.amount_left():
                event = 0
            else:
                event = 3
            if DEBUG or DEBUG_ANNOUNCE:
                log(self.log_prefix + 'start: call d(%d)' % event)
            self.d(event)
            self.init_check_network_connection()

    def c(self):
        if self.stopped:
            if DEBUG or DEBUG_ANNOUNCE:
                log(self.log_prefix + 'c: stopped, return')
            return
        if DEBUG or DEBUG_ANNOUNCE:
            log(self.log_prefix + 'c: self.unpauseflag.isSet()', self.unpauseflag.isSet(), 'self.howmany()', self.howmany(), 'self.minpeers', self.minpeers, 'thread', currentThread().name)
        if not self.unpauseflag.isSet() and self.howmany() < self.minpeers:
            if DEBUG or DEBUG_ANNOUNCE:
                log(self.log_prefix + 'c: call announce(3, _c)')
            self.announce(3, self._c)
        else:
            if DEBUG or DEBUG_ANNOUNCE:
                log(self.log_prefix + 'c: call _c()')
            self._c()

    def _c(self):
        if DEBUG or DEBUG_ANNOUNCE:
            log(self.log_prefix + '_c: sched c(), interval', self.interval, 'thread', currentThread().name)
        self.sched(self.c, self.interval)

    def d(self, event = 3):
        if self.stopped:
            if DEBUG or DEBUG_ANNOUNCE:
                log(self.log_prefix + 'd: stopped, return')
            return
        if not self.unpauseflag.isSet():
            if DEBUG or DEBUG_ANNOUNCE:
                log(self.log_prefix + 'd: unpauseflag is set, call _d() and return')
            self._d()
            return
        if DEBUG or DEBUG_ANNOUNCE:
            log(self.log_prefix + 'd: call announce(%d, _d)' % event, 'thread', currentThread().name)
        self.announce(event, self._d)

    def _d(self):
        if self.never_succeeded:
            if DEBUG or DEBUG_ANNOUNCE:
                log(self.log_prefix + '_d: never succeeded, shed d() in 60 seconds')
            self.sched(self.d, 60)
        else:
            self.sched(self.d, self.announce_interval)
            if DEBUG or DEBUG_ANNOUNCE:
                log(self.log_prefix + '_d: shed d(): announce_interval', self.announce_interval, 'thread', currentThread().name)

    def run_dht(self):
        if DEBUG:
            print >> sys.stderr, 'Rerequester::run_dht: call rerequest_dht()'
        self.rerequest_dht()
        self.sched(self.run_dht, 60, self.schedid + 'run_dht')

    def encoder_wants_new_peers(self):
        if self.am_video_source:
            if DEBUG or DEBUG_ANNOUNCE:
                log(self.log_prefix + 'encoder_wants_new_peers: do nothing for live source')
            return
        if DEBUG or DEBUG_ANNOUNCE:
            log(self.log_prefix + 'encoder_wants_new_peers: ---')
        task = lambda : self.announce()
        self.sched(task)

    def init_check_network_connection(self):
        t = Thread(target=self.check_network_connection, args=[False, 5, True])
        t.name = 'RerequestCheckNetwork' + t.name
        t.daemon = True
        if DEBUG_LOCK or DEBUG_ANNOUNCE:
            log(self.log_prefix + 'init_check_network_connection: start check_network_connection(): thread', t.name)
        t.start()

    def check_network_connection(self, announce = True, interval = 5, populate_url_list = False):
        if DEBUG_CHECK_NETWORK_CONNECTION:
            log(self.log_prefix + 'check_network_connection: announce', announce, 'populate_url_list', populate_url_list, 'interval', interval)
        if not self.network_lock.acquire(False):
            if DEBUG_CHECK_NETWORK_CONNECTION:
                log(self.log_prefix + 'check_network_connection: locked, return')
            return False
        for i in xrange(len(self.network_check_url_list)):
            url = self.network_check_url_list[i][0]
            ip = self.network_check_url_list[i][1]
            if DEBUG_CHECK_NETWORK_CONNECTION:
                log(self.log_prefix + 'check_network_connection: test', url, 'ip', ip)
            success = False
            if ip is None:
                ip = test_network_connection(url, getip=True)
                if DEBUG_CHECK_NETWORK_CONNECTION:
                    log(self.log_prefix + 'check_network_connection: query ip', ip)
                if ip is not None:
                    self.network_check_url_list[i][1] = ip
                    success = True
            else:
                if DEBUG_CHECK_NETWORK_CONNECTION:
                    log(self.log_prefix + 'check_network_connection: test by ip', ip)
                success = test_network_connection(host=ip)
            if populate_url_list:
                continue
            if success:
                if DEBUG_CHECK_NETWORK_CONNECTION:
                    log(self.log_prefix + 'check_network_connection: success', url)
                if announce:
                    announce_lambda = lambda : self.announce()
                    self.sched(announce_lambda)
                self.network_lock.release()
                return True
            if DEBUG_CHECK_NETWORK_CONNECTION:
                log(self.log_prefix + 'check_network_connection: failed', url)

        self.network_lock.release()
        if populate_url_list:
            return True
        if DEBUG_CHECK_NETWORK_CONNECTION:
            log(self.log_prefix + 'check_network_connection: all failed, possible there is no network, retry in ', interval, 'seconds')
        if not populate_url_list:
            task = lambda : self.check_network_connection(announce=True, interval=interval)
            self.sched(task, interval)
        return False

    def announce(self, event = 3, callback = lambda : None, specialurl = None):
        if ':' in self.ip:
            compact = 0
        else:
            compact = 1
        params = {}
        if specialurl is not None:
            s = self.url + '&uploaded=0&downloaded=0&left=1'
            if self.howmany() >= self.maxpeers:
                s += '&numwant=0'
                params['numwant'] = 0
            else:
                params['numwant'] = 200
                s += '&numwant=200'
                s += '&no_peer_id=1'
                if compact:
                    s += '&compact=1'
            self.last_failed = True
            self.special = specialurl
            params['uploaded'] = 0
            params['downloaded'] = 0
            params['left'] = 1
            self.rerequest(s, callback, params)
            return
        s = '%s&uploaded=%s&downloaded=%s&left=%s' % (self.url,
         str(self.up()),
         str(self.down()),
         str(self.amount_left()))
        params['uploaded'] = int(self.up())
        params['downloaded'] = int(self.down())
        params['left'] = int(self.amount_left())
        if self.last is not None:
            s += '&last=' + quote(str(self.last))
        if self.trackerid is not None:
            s += '&trackerid=' + quote(str(self.trackerid))
        if self.howmany() >= self.maxpeers:
            s += '&numwant=0'
            params['numwant'] = 0
        else:
            params['numwant'] = 200
            s += '&numwant=200'
            s += '&no_peer_id=1'
            if compact:
                s += '&compact=1'
        if event != 3:
            event_name = ['started', 'completed', 'stopped'][event]
            s += '&event=' + event_name
            params['event'] = event
        if event == 2:
            self.stopped = True
        if DEBUG or DEBUG_ANNOUNCE:
            log(self.log_prefix + 'announce: event', event, 'callback', callback, 'params', params, 'thread', currentThread().name)
        self.rerequest(s, callback, params)

    def snoop(self, peers, callback = lambda : None):
        params = {'event': 'stopped',
         'port': 0,
         'uploaded': 0,
         'downloaded': 0,
         'left': 1,
         'numwant': int(peers)}
        if DEBUG or DEBUG_ANNOUNCE:
            log(self.log_prefix + 'snoop: peers', peers, 'callback', callback, 'params', params, 'thread', currentThread().name)
        self.rerequest(self.url + '&event=stopped&port=0&uploaded=0&downloaded=0&left=1&tracker=1&numwant=' + str(peers), callback, params)

    def rerequest(self, s, callback, params):
        proxy_mode = self.config.get('proxy_mode', 0)
        if proxy_mode == PROXY_MODE_PRIVATE:
            if DEBUG:
                log(self.log_prefix + 'PROXY_MODE_PRIVATE, rerequest exited')
            return
        if DEBUG_ANNOUNCE:
            print_stack()
        if not self.lock.isready():

            def retry(self = self, s = s, callback = callback, params = params):
                self.rerequest(s, callback, params)

            self.sched(retry, 5)
            if DEBUG_LOCK or DEBUG_ANNOUNCE:
                log(self.log_prefix + 'rerequest: locked, retry in 5 seconds: s', s, 'callback', callback, 'params', params, 'thread', currentThread().name)
            return
        rq = Thread(target=self._rerequest, args=[s, callback, params])
        rq.name = 'TrackerRerequestA' + rq.name
        rq.daemon = True
        if DEBUG_LOCK or DEBUG_ANNOUNCE:
            log(self.log_prefix + 'rerequest: start new request: s', s, 'thread', rq.name)
        rq.start()

    def rerequest_dht(self):
        rq = Thread(target=self._dht_rerequest)
        rq.setName('RerequestDHT' + rq.getName())
        rq.setDaemon(True)
        rq.start()

    def _rerequest(self, s, callback, params):
        try:
            self.lock.start()

            def fail(self = self, callback = callback):
                self._fail(callback)

            if self.ip:
                try:
                    if ':' in self.ip:
                        urlip = '[' + self.ip + ']'
                        field = 'ipv6'
                    else:
                        urlip = self.ip
                        field = 'ip'
                    s += '&' + field + '=' + urlip
                except:
                    self.errorcodes['troublecode'] = 'unable to resolve: ' + self.ip
                    self.externalsched(fail)

            self.errorcodes = {}
            if self.special is None:
                if not self.dht:
                    if DEBUG_DHT:
                        log(self.log_prefix + '_rerequest: no DHT support loaded')
                elif self.am_video_source:
                    if DEBUG_DHT:
                        log(self.log_prefix + '_rerequest: disable dht for live source')
                else:
                    self._dht_rerequest()
                if DEBUG:
                    log(self.log_prefix + '_rerequest: current tracker list:', self.trackerlist)
                new_tracker_list = []
                for t in range(len(self.trackerlist)):
                    for tr in range(len(self.trackerlist[t])):
                        tracker = self.trackerlist[t][tr]
                        if DEBUG:
                            log(self.log_prefix + '_rerequest: trying tracker', tracker)
                        if DEBUG_LOCK:
                            log(self.log_prefix + '_rerequest: call rerequest_single(): tracker', tracker, 'thread', currentThread().name)
                        ret = self.rerequest_single(tracker, s, params)
                        if DEBUG_LOCK:
                            log(self.log_prefix + '_rerequest: rerequest_single() finished: ret', ret, 'tracker', tracker, 'thread', currentThread().name)
                        if ret and not self.last_failed:
                            new_tracker_list.insert(0, [tracker])
                        else:
                            new_tracker_list.append([tracker])

                if DEBUG:
                    log(self.log_prefix + '_rerequest: new tracker list:', new_tracker_list)
                self.trackerlist = new_tracker_list[:]
                if DEBUG_LOCK or DEBUG_ANNOUNCE:
                    log(self.log_prefix + '_rerequest: return: thread', currentThread().name)
                callback()
                return
            tracker = self.special
            self.special = None
            if self.rerequest_single(tracker, s, callback):
                callback()
                return
            self.externalsched(fail)
        except:
            self.exception(callback)
        finally:
            self.lock.finish()

    def _fail(self, callback):
        if self.upratefunc() < 100 and self.downratefunc() < 100 or not self.amount_left():
            for f in ['rejected', 'bad_data', 'troublecode']:
                if self.errorcodes.has_key(f):
                    r = self.errorcodes[f]
                    break
            else:
                r = 'Problem connecting to tracker - unspecified error:' + `(self.errorcodes)`

            self.errorfunc(r)
        self.last_failed = True
        if DEBUG_LOCK or DEBUG_ANNOUNCE:
            log(self.log_prefix + '_fail: give up: thread', currentThread().name)
        self.lock.give_up()
        self.externalsched(callback)

    def rerequest_single(self, t, s, params):
        l = self.lock.set()
        if t.startswith('udp'):
            target = self._rerequest_single_udp
            args = [t, params, l]
        else:
            target = self._rerequest_single
            args = [t, s + get_key(t), l]
        rq = Thread(target=target, args=args)
        rq.name = 'TrackerRerequestB' + rq.name
        rq.daemon = True
        if DEBUG_LOCK or DEBUG_ANNOUNCE:
            log(self.log_prefix + 'rerequest_single: start new thread: t', t, 'set_lock', l, 'thread', rq.name)
        rq.start()
        if DEBUG_LOCK:
            log(self.log_prefix + 'rerequest_single: wait for lock: thread', currentThread().name)
        self.lock.wait()
        if DEBUG_LOCK or DEBUG_ANNOUNCE:
            log(self.log_prefix + 'rerequest_single: wait for lock done: success', self.lock.success, 'thread', currentThread().name)
        if self.lock.success:
            self.lastsuccessful = t
            self.last_failed = False
            self.never_succeeded = False
            return True
        if not self.last_failed and self.lastsuccessful == t:
            self.last_failed = True
            self.lock.give_up()
            return True
        return False

    def _rerequest_single_udp(self, t, params, l):
        try:
            if self.ip:
                ip = self.ip
            else:
                ip = 0
            e = params.get('event', '')
            if e == 'completed':
                event = 1
            elif e == 'started':
                event = 2
            elif e == 'stopped':
                event = 3
            else:
                event = 0
            url = urlparse.urlparse(t)
            host = url.hostname
            port = url.port
            if port is None:
                port = 80
            interval, peers = self.udp_announce(host, port, infohash=self.infohash, peerid=self.myid, timeout=self.timeout, downloaded=params.get('downloaded', 0), left=params.get('left', 0), uploaded=params.get('uploaded', 0), event=0, ip=ip, key=0, num_want=params.get('numwant', 0), clport=self.port)
            peer_list = []
            for nip, port in peers:
                aip = socket.inet_ntoa(struct.pack('!I', nip))
                peer_list.append({'ip': aip,
                 'port': port})

            resp = {'interval': interval,
             'peers': peer_list}
            if self.lock.trip(l, True):
                if DEBUG_LOCK:
                    log(self.log_prefix + '_rerequest_single_udp: trip success, unwait: l', l, 't', t, 'thread', currentThread().name)
                self.lock.unwait(l)
            elif DEBUG_LOCK:
                log(self.log_prefix + '_rerequest_single_udp: trip success, no trip: l', l, 't', t, 'thread', currentThread().name)
            if DEBUG:
                log(self.log_prefix + '_rerequest_single_udp: resp', resp)

            def add(self = self, r = resp):
                self.postrequest(r, 'tracker=' + t, self.notifiers)

            self.externalsched(add)
        except:
            if self.lock.trip(l):
                if DEBUG_LOCK:
                    log(self.log_prefix + '_rerequest_single_udp: exception in udp announce, unwait: l', l, 't', t, 'thread', currentThread().name)
                self.lock.unwait(l)
            elif DEBUG_LOCK:
                log(self.log_prefix + '_rerequest_single_udp: exception in udp announce, no trip: l', l, 't', t, 'thread', currentThread().name)
            if DEBUG:
                print_exc()

    def _rerequest_single(self, t, s, l):
        try:
            closer = [None]

            def timedout(self = self, l = l, closer = closer):
                if self.lock.trip(l):
                    if DEBUG_LOCK:
                        log(self.log_prefix + '_rerequest_single:timedout: unwait: l', l, 't', t, 'thread', currentThread().name)
                    self.errorcodes['troublecode'] = 'Problem connecting to tracker - timeout exceeded'
                    self.lock.unwait(l)
                elif DEBUG_LOCK:
                    log(self.log_prefix + '_rerequest_single:timedout: no trip: l', l, 't', t, 'thread', currentThread().name)
                try:
                    closer[0]()
                except:
                    pass

            self.externalsched(timedout, self.timeout)
            err = None
            try:
                if DEBUG or DEBUG_ANNOUNCE:
                    log(self.log_prefix + '_rerequest_single: request tracker', merge_announce(t, s), 'thread', currentThread().name)
                h = urlopen(merge_announce(t, s), silent=True)
                closer[0] = h.close
                data = h.read()
            except (IOError, socket.error) as e:
                err = 'Problem connecting to tracker - ' + str(e)
                if DEBUG:
                    log(self.log_prefix + '_rerequest_single: failed to connect to tracker')
            except:
                err = 'Problem connecting to tracker'
                if DEBUG:
                    log(self.log_prefix + '_rerequest_single: failed to connect to tracker')

            try:
                h.close()
            except:
                pass

            if err:
                if self.lock.trip(l):
                    if DEBUG_LOCK:
                        log(self.log_prefix + '_rerequest_single: got error, unwait: l', l, 't', t, 'thread', currentThread().name, 'err', err)
                    self.errorcodes['troublecode'] = err
                    self.lock.unwait(l)
                elif DEBUG_LOCK:
                    log(self.log_prefix + '_rerequest_single: got error, no trip: l', l, 't', t, 'thread', currentThread().name, 'err', err)
                return
            if not data:
                if self.lock.trip(l):
                    if DEBUG_LOCK:
                        log(self.log_prefix + '_rerequest_single: no date, unwait: l', l, 't', t, 'thread', currentThread().name)
                    self.errorcodes['troublecode'] = 'no data from tracker'
                    self.lock.unwait(l)
                elif DEBUG_LOCK:
                    log(self.log_prefix + '_rerequest_single: no data, no trip: l', l, 't', t, 'thread', currentThread().name)
                return
            try:
                r = bdecode(data, sloppy=1)
                if DEBUG or DEBUG_ANNOUNCE:
                    log(self.log_prefix + '_rerequest_single: respose from tracker: t', t, 'r', r, 'thread', currentThread().name)
                check_peers(r)
            except ValueError as e:
                if DEBUG:
                    log_exc()
                if self.lock.trip(l):
                    if DEBUG_LOCK:
                        log(self.log_prefix + '_rerequest_single: exception while decoding data, unwait: l', l, 't', t, 'thread', currentThread().name)
                    self.errorcodes['bad_data'] = 'bad data from tracker - ' + str(e)
                    self.lock.unwait(l)
                elif DEBUG_LOCK:
                    log(self.log_prefix + '_rerequest_single: exception while decoding data, no trip: l', l, 't', t, 'thread', currentThread().name)
                return

            if r.has_key('failure reason'):
                if self.lock.trip(l):
                    if DEBUG_LOCK:
                        log(self.log_prefix + '_rerequest_single: got failure reason, unwait: l', l, 't', t, 'thread', currentThread().name)
                    self.errorcodes['rejected'] = self.rejectedmessage + r['failure reason']
                    self.lock.unwait(l)
                elif DEBUG_LOCK:
                    log(self.log_prefix + '_rerequest_single: got failure reason, no trip: l', l, 't', t, 'thread', currentThread().name)
                return
            if self.lock.trip(l, True):
                if DEBUG_LOCK:
                    log(self.log_prefix + '_rerequest_single: trip success, unwait: l', l, 't', t, 'thread', currentThread().name)
                self.lock.unwait(l)
            elif DEBUG_LOCK:
                log(self.log_prefix + '_rerequest_single: trip success, no trip: l', l, 't', t, 'thread', currentThread().name)

            def add(self = self, r = r):
                self.postrequest(r, 'tracker=' + t, self.notifiers)

            self.externalsched(add)
        except:
            print_exc()
            if self.lock.trip(l):
                if DEBUG_LOCK:
                    log(self.log_prefix + '_rerequest_single: got exception, unwait: l', l, 't', t, 'thread', currentThread().name)
                self.lock.unwait(l)

    def udp_announce(self, host, port, infohash, peerid, timeout = 15, downloaded = 0, left = 0, uploaded = 0, event = 0, ip = 0, key = 0, num_want = -1, clport = 1111):
        if DEBUG:
            log(self.log_prefix + 'udp_announce: host', host, 'port', port, 'infohash', infohash, 'peerid', peerid, 'event', event, 'ip', ip, 'clport', clport, 'num_want', num_want, 'key', key, 'timeout', timeout, 'downloaded', downloaded, 'uploaded', uploaded, 'left', left)
        action = {'connect': 0,
         'announce': 1,
         'scrape': 2,
         'error': 3}
        conn_head_size = 16
        announce_head_size = 20
        error_head_size = 8
        peer_size = 6
        default_connection = 4497486125440L
        transaction = random.randint(0, 999999)
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(timeout)
        connect_request_pack = struct.pack('>QLL', default_connection, action['connect'], transaction)
        udp_socket.sendto(connect_request_pack, (host, port))
        response = udp_socket.recv(512)
        resp_action = struct.unpack('>L', response[:4])[0]
        if resp_action != action['connect']:
            if resp_action == action['error']:
                errmsg_len = len(response) - error_head_size
                errmsg = struct.unpack('>' + str(errmsg_len) + 's', response[8:])[0]
                raise Exception(errmsg)
            raise Exception('got unexpect action')
        default_connection = struct.unpack('>Q', response[8:])[0]
        transaction = random.randint(0, 999999)
        announce_request_pack = struct.pack('>QLL20s20sQQQLLLlH', default_connection, action['announce'], transaction, infohash, peerid, downloaded, left, uploaded, event, ip, key, num_want, clport)
        udp_socket.sendto(announce_request_pack, (host, port))
        response = udp_socket.recv(1220)
        resp_action = struct.unpack('>L', response[:4])[0]
        if resp_action != action['announce']:
            if resp_action == action['error']:
                errmsg_len = len(response) - error_head_size
                errmsg = struct.unpack('>' + str(errmsg_len) + 's', response[8:])[0]
                raise Exception(errmsg)
            raise Exception('got unexpect action')
        resp_transaction = struct.unpack('>L', response[4:8])[0]
        if resp_transaction != transaction:
            raise Exception('got incorrect transaction')
        interval = struct.unpack('>L', response[8:12])[0]
        peers_in_response = (len(response) - announce_head_size) / peer_size
        i = 0
        peers = []
        while i < peers_in_response:
            peer_unpack = struct.unpack('>LH', response[i * peer_size + announce_head_size:(i + 1) * peer_size + announce_head_size])
            peers.append(peer_unpack)
            i = i + 1

        return (interval, peers)

    def _dht_rerequest(self):
        if DEBUG_DHT:
            log(self.log_prefix + '_dht_rerequest: infohash', self.infohash)
        try:
            info_hash_id = Id(self.infohash)
        except IdError:
            log(self.log_prefix + '_dht_rerequest: self.info_hash is not a valid identifier')
            return

        if 'dialback' in self.config and self.config['dialback']:
            if DEBUG_DHT:
                log(self.log_prefix + '_dht_rerequest: get_peers AND announce')
            self.dht.get_peers(self.infohash, info_hash_id, self._dht_got_peers, self.port)
            return
        if DEBUG_DHT:
            log(self.log_prefix + '_dht_rerequest: JUST get_peers, DO NOT announce')
        self.dht.get_peers(self.infohash, info_hash_id, self._dht_got_peers)

    def _dht_got_peers(self, infohash, peers):
        if DEBUG_DHT:
            if peers:
                log(self.log_prefix + 'DHT: Received', len(peers), 'peers', currentThread().getName())
            else:
                log(self.log_prefix + 'DHT: Received no peers', currentThread().getName())
        if not peers:
            return
        p = [ {'ip': peer[0],
         'port': peer[1]} for peer in peers ]
        if p:
            r = {'peers': p}

            def add(self = self, r = r):
                self.postrequest(r, 'dht')

            self.externalsched(add)

    def add_notifier(self, cb):
        self.notifiers.append(cb)

    def postrequest(self, r, source, notifiers = []):
        try:
            if source is None:
                source = ''
            if r.has_key('warning message'):
                if DEBUG:
                    log(self.log_prefix + 'postrequest: tracker warning:', r['warning message'])
                self.errorfunc('warning from tracker - ' + r['warning message'])
            self.announce_interval = r.get('interval', self.announce_interval)
            self.interval = r.get('min interval', self.interval)
            if DEBUG:
                log(self.log_prefix + 'postrequest: %s: announce min is' % source, self.announce_interval, self.interval)
            self.trackerid = r.get('tracker id', self.trackerid)
            self.last = r.get('last', self.last)
            peers = []
            p = r.get('peers')
            if p is not None:
                if type(p) == type(''):
                    for x in xrange(0, len(p), 6):
                        ip = '.'.join([ str(ord(i)) for i in p[x:x + 4] ])
                        port = ord(p[x + 4]) << 8 | ord(p[x + 5])
                        peers.append(((ip, port), 0))

                else:
                    for x in p:
                        peers.append(((x['ip'].strip(), x['port']), x.get('peer id', 0)))

            else:
                p = r.get('peers6')
                if type(p) == type(''):
                    for x in xrange(0, len(p), 18):
                        hexip = binascii.b2a_hex(p[x:x + 16])
                        ip = ''
                        for i in xrange(0, len(hexip), 4):
                            ip += hexip[i:i + 4]
                            if i + 4 != len(hexip):
                                ip += ':'

                        port = ord(p[x + 16]) << 8 | ord(p[x + 17])
                        peers.append(((ip, port), 0))

                else:
                    for x in p:
                        peers.append(((x['ip'].strip(), x['port']), x.get('peer id', 0)))

                log(self.log_prefix + 'Got IPv6 peer addresses, not yet supported, ignoring.')
                peers = []
            if DEBUG:
                log(self.log_prefix + 'postrequest: %s: Got peers' % source, peers)
            ps = len(peers) + self.howmany()
            if ps < self.maxpeers:
                if self.doneflag.isSet():
                    if r.get('num peers', 1000) - r.get('done peers', 0) > ps * 1.2:
                        self.last = None
                elif r.get('num peers', 1000) > ps * 1.2:
                    self.last = None
            if peers:
                random.shuffle(peers)
                if self.am_video_source:
                    if DEBUG:
                        log(self.log_prefix + 'postrequest: do not start connections for live source')
                else:
                    self.connect(peers)
                for notifier in notifiers:
                    notifier(peers)

        except:
            log(self.log_prefix + 'postrequest: error in postrequest')
            log_exc()

    def exception(self, callback):
        data = StringIO()
        print_exc(file=data)

        def r(s = data.getvalue(), callback = callback):
            if self.excfunc:
                self.excfunc(s)
            else:
                print s
            callback()

        self.externalsched(r)


class SuccessLock():

    def __init__(self, infohash = None):
        self.lock = Lock()
        self.pause = Lock()
        self.ready = Lock()
        self.code = 0L
        self.success = False
        self.finished = True
        self.log_prefix = 'rerequester:successlock::'
        if infohash is not None:
            self.log_prefix += binascii.hexlify(infohash) + ':'

    def start(self):
        if DEBUG_LOCK:
            log(self.log_prefix + 'start: acquire ready lock: thread', currentThread().name)
        self.ready.acquire()
        if DEBUG_LOCK:
            log(self.log_prefix + 'start: acquire ready lock done: thread', currentThread().name)
        self.success = False
        self.finished = False

    def finish(self):
        if DEBUG_LOCK:
            log(self.log_prefix + 'finish: release ready lock: thread', currentThread().name)
        self.ready.release()

    def isready(self):
        locked = self.ready.locked()
        if DEBUG_LOCK:
            log(self.log_prefix + 'isready: ready lock status: locked', locked, 'thread', currentThread().name)
        return not locked

    def set(self):
        if DEBUG_LOCK:
            log(self.log_prefix + 'set: acquire lock: thread', currentThread().name)
        self.lock.acquire()
        if DEBUG_LOCK:
            log(self.log_prefix + 'set: acquire lock done: thread', currentThread().name)
        if not self.pause.locked():
            if DEBUG_LOCK:
                log(self.log_prefix + 'set: pause is not locked, acquire: thread', currentThread().name)
            self.pause.acquire()
            if DEBUG_LOCK:
                log(self.log_prefix + 'set: pause acquire done: thread', currentThread().name)
        elif DEBUG_LOCK:
            log(self.log_prefix + 'set: pause is locked: thread', currentThread().name)
        self.first = True
        self.finished = False
        self.success = False
        self.code += 1L
        self.lock.release()
        if DEBUG_LOCK:
            log(self.log_prefix + 'set: release lock and return: first', self.first, 'code', self.code, 'thread', currentThread().name)
        return self.code

    def trip(self, code, s = False):
        if DEBUG_LOCK:
            log(self.log_prefix + 'trip: acquire lock: code', code, 's', s, 'self.code', self.code, 'self.finished', self.finished, 'thread', currentThread().name)
        self.lock.acquire()
        if DEBUG_LOCK:
            log(self.log_prefix + 'trip: acquire lock done: code', code, 's', s, 'self.code', self.code, 'self.finished', self.finished, 'thread', currentThread().name)
        try:
            if code == self.code and not self.finished:
                r = self.first
                self.first = False
                if s:
                    self.finished = True
                    self.success = True
                if DEBUG_LOCK:
                    log(self.log_prefix + 'trip: got match: code', code, 's', s, 'self.code', self.code, 'self.finished', self.finished, 'self.success', self.success, 'r', r, 'thread', currentThread().name)
                return r
            if DEBUG_LOCK:
                log(self.log_prefix + 'trip: no match: code', code, 'self.code', self.code, 'self.finished', self.finished, 'thread', currentThread().name)
        finally:
            self.lock.release()

    def give_up(self):
        self.lock.acquire()
        self.success = False
        self.finished = True
        if DEBUG_LOCK:
            log(self.log_prefix + 'give_up: self.success', self.success, 'self.finished', self.finished, 'thread', currentThread().name)
        self.lock.release()

    def wait(self):
        if DEBUG_LOCK:
            log(self.log_prefix + 'wait: acquire pause: thread', currentThread().name)
        self.pause.acquire()
        if DEBUG_LOCK:
            log(self.log_prefix + 'wait: acquire pause done: thread', currentThread().name)

    def unwait(self, code):
        if code == self.code and self.pause.locked():
            if DEBUG_LOCK:
                log(self.log_prefix + 'unwait: release pause: code', code, 'self.code', self.code, 'thread', currentThread().name)
            self.pause.release()
        elif DEBUG_LOCK:
            log(self.log_prefix + 'unwait: do not release pause: code', code, 'self.code', self.code, 'thread', currentThread().name)

    def isfinished(self):
        self.lock.acquire()
        x = self.finished
        self.lock.release()
        if DEBUG_LOCK:
            log(self.log_prefix + 'isfinished: x', x, 'thread', currentThread().name)
        return x
