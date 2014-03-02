#Embedded file name: ACEStream\Core\NATFirewall\ConnectionCheck.pyo
import sys
from time import sleep
import thread
import random
from ACEStream.Core.NATFirewall.NatCheck import GetNATType
from ACEStream.Core.NATFirewall.TimeoutCheck import GetTimeout
DEBUG = False

class ConnectionCheck:
    __single = None

    def __init__(self, session):
        if ConnectionCheck.__single:
            raise RuntimeError, 'ConnectionCheck is singleton'
        ConnectionCheck.__single = self
        self._lock = thread.allocate_lock()
        self._running = False
        self.session = session
        self.permid = self.session.get_permid()
        self.nat_type = None
        self.nat_timeout = 0
        self._nat_callbacks = []
        self.natcheck_reply_callbacks = []

    @staticmethod
    def getInstance(*args, **kw):
        if ConnectionCheck.__single is None:
            ConnectionCheck(*args, **kw)
        return ConnectionCheck.__single

    def try_start(self, reply_callback = None):
        if reply_callback:
            self.natcheck_reply_callbacks.append(reply_callback)
        if DEBUG:
            if self._running:
                print >> sys.stderr, 'natcheckmsghandler: the thread is already running'
            else:
                print >> sys.stderr, 'natcheckmsghandler: starting the thread'
        if not self._running:
            thread.start_new_thread(self.run, ())
            while True:
                sleep(0)
                if self._running:
                    break

    def run(self):
        self._lock.acquire()
        self._running = True
        self._lock.release()
        try:
            self.nat_discovery()
        finally:
            self._lock.acquire()
            self._running = False
            self._lock.release()

    def timeout_check(self, pingback):
        return GetTimeout(pingback)

    def natcheck(self, in_port, server1, server2):
        nat_type, ex_ip, ex_port, in_ip = GetNATType(in_port, server1, server2)
        if DEBUG:
            print >> sys.stderr, 'NATCheck:', 'NAT Type: ' + nat_type[1]
        if DEBUG:
            print >> sys.stderr, 'NATCheck:', 'Public Address: ' + ex_ip + ':' + str(ex_port)
        if DEBUG:
            print >> sys.stderr, 'NATCheck:', 'Private Address: ' + in_ip + ':' + str(in_port)
        return (nat_type,
         ex_ip,
         ex_port,
         in_ip)

    def get_nat_type(self, callback = None):
        if self.nat_type:
            if callback:
                callback(self.nat_type)
            return self.nat_type
        else:
            if callback:
                self._nat_callbacks.append(callback)
            self.try_start()
            return 'Unknown NAT/Firewall'

    def _perform_nat_type_notification(self):
        nat_type = self.get_nat_type()
        callbacks = self._nat_callbacks
        self._nat_callbacks = []
        for callback in callbacks:
            try:
                callback(nat_type)
            except:
                pass

    def nat_discovery(self):
        in_port = self.session.get_puncturing_internal_port()
        stun_servers = self.session.get_stun_servers()
        random.seed()
        random.shuffle(stun_servers)
        stun1 = stun_servers[1]
        stun2 = stun_servers[0]
        pingback_servers = self.session.get_pingback_servers()
        random.shuffle(pingback_servers)
        if DEBUG:
            print >> sys.stderr, 'NATCheck:', 'Starting ConnectionCheck on %s %s %s' % (in_port, stun1, stun2)
        performed_nat_type_notification = False
        nat_type, ex_ip, ex_port, in_ip = self.natcheck(in_port, stun1, stun2)
        self.nat_type = nat_type[1]
        self._perform_nat_type_notification()
        performed_nat_type_notification = True
        if len(self.natcheck_reply_callbacks):
            if nat_type[0] > 0:
                for pingback in pingback_servers:
                    if DEBUG:
                        print >> sys.stderr, 'NatCheck: pingback is:', pingback
                    self.nat_timeout = self.timeout_check(pingback)
                    if self.nat_timeout <= 0:
                        break

                if DEBUG:
                    print >> sys.stderr, 'NATCheck: Nat UDP timeout is: ', str(self.nat_timeout)
            self.nat_params = [nat_type[1],
             nat_type[0],
             self.nat_timeout,
             ex_ip,
             int(ex_port),
             in_ip,
             in_port]
            if DEBUG:
                print >> sys.stderr, 'NATCheck:', str(self.nat_params)
            for reply_callback in self.natcheck_reply_callbacks:
                reply_callback(self.nat_params)

            self.natcheck_reply_callbacks = []
        if not performed_nat_type_notification:
            self._perform_nat_type_notification()
