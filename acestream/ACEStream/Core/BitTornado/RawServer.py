#Embedded file name: ACEStream\Core\BitTornado\RawServer.pyo
from bisect import insort
from SocketHandler import SocketHandler
import socket
from cStringIO import StringIO
from traceback import print_exc
from select import error
from threading import Event, RLock, currentThread
from thread import get_ident
from clock import clock
import sys
import time
from ACEStream.Core.Utilities.logger import log, log_exc
try:
    True
except:
    True = 1
    False = 0

DEBUG = False
DEBUG2 = False
DEBUG_TASKS = False

def autodetect_ipv6():
    try:
        socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        res = 1
    except:
        res = 0

    if DEBUG2:
        log('rawserver::autodetect_ipv6:', res)
    return res


def autodetect_socket_style():
    if sys.platform.find('linux') < 0:
        res = 1
    else:
        try:
            f = open('/proc/sys/net/ipv6/bindv6only', 'r')
            dual_socket_style = int(f.read())
            f.close()
            res = int(not dual_socket_style)
        except:
            res = 0

    if DEBUG2:
        log('rawserver::autodetect_socket_style:', res)
    return res


READSIZE = 100000

class RawServer:

    def __init__(self, doneflag, timeout_check_interval, timeout, noisy = True, ipv6_enable = True, failfunc = lambda x: None, errorfunc = None, sockethandler = None, excflag = Event(), max_socket_connects = 1000):
        self.timeout_check_interval = timeout_check_interval
        self.timeout = timeout
        self.servers = {}
        self.single_sockets = {}
        self.dead_from_write = []
        self.doneflag = doneflag
        self.noisy = noisy
        self.failfunc = failfunc
        self.errorfunc = errorfunc
        self.exccount = 0
        self.funcs = []
        self.externally_added = []
        self.finished = Event()
        self.tasks_to_kill = []
        self.excflag = excflag
        self.lock = RLock()
        if DEBUG2:
            log('rawserver::__init__: timeout_check_interval', timeout_check_interval, 'timeout', timeout, 'ipv6_enable', ipv6_enable)
        if sockethandler is None:
            if DEBUG2:
                log('rawserver::__init__: create SocketHandler: max_socket_connects', max_socket_connects)
            sockethandler = SocketHandler(timeout, ipv6_enable, READSIZE, max_socket_connects)
        self.sockethandler = sockethandler
        self.thread_ident = None
        self.interrupt_socket = sockethandler.get_interrupt_socket()
        self.add_task(self.scan_for_timeouts, timeout_check_interval)

    def get_exception_flag(self):
        return self.excflag

    def _add_task(self, func, delay, id = None):
        if delay < 0:
            delay = 0
        insort(self.funcs, (clock() + delay, func, id))

    def add_task(self, func, delay = 0, id = None):
        if DEBUG_TASKS:
            log('rawserver::add_task: func', func, 'delay', delay)
        if delay < 0:
            delay = 0
        self.lock.acquire()
        self.externally_added.append((func, delay, id))
        if self.thread_ident != get_ident():
            self.interrupt_socket.interrupt()
        self.lock.release()

    def scan_for_timeouts(self):
        self.add_task(self.scan_for_timeouts, self.timeout_check_interval)
        self.sockethandler.scan_for_timeouts()

    def bind(self, port, bind = '', reuse = False, ipv6_socket_style = 1):
        result = self.sockethandler.bind(port, bind, reuse, ipv6_socket_style)
        return result

    def find_and_bind(self, first_try, minport, maxport, bind = '', reuse = False, ipv6_socket_style = 1, randomizer = False):
        result = self.sockethandler.find_and_bind(first_try, minport, maxport, bind, reuse, ipv6_socket_style, randomizer)
        return result

    def start_connection_raw(self, dns, socktype, handler = None):
        if DEBUG2:
            log('rawserver::start_connection_raw: dns', dns, 'socktype', socktype, 'handler', handler)
        return self.sockethandler.start_connection_raw(dns, socktype, handler)

    def start_connection(self, dns, handler = None, randomize = False):
        if DEBUG2:
            log('rawserver::start_connection: dns', dns, 'randomize', randomize, 'handler', handler)
        return self.sockethandler.start_connection(dns, handler, randomize)

    def get_stats(self):
        return self.sockethandler.get_stats()

    def pop_external(self):
        self.lock.acquire()
        while self.externally_added:
            a, b, c = self.externally_added.pop(0)
            self._add_task(a, b, c)

        self.lock.release()

    def listen_forever(self, handler):
        if DEBUG:
            log('rawserver::listen_forever: handler', handler)
        self.thread_ident = get_ident()
        self.sockethandler.set_handler(handler)
        try:
            while not self.doneflag.isSet():
                try:
                    self.pop_external()
                    self._kill_tasks()
                    if self.funcs:
                        period = self.funcs[0][0] + 0.001 - clock()
                    else:
                        period = 1073741824
                    if period < 0:
                        period = 0
                    events = self.sockethandler.do_poll(period)
                    if self.doneflag.isSet():
                        if DEBUG:
                            log('rawserver::listen_forever: stopping because done flag set')
                        return
                    while self.funcs and self.funcs[0][0] <= clock():
                        garbage1, func, id = self.funcs.pop(0)
                        if id in self.tasks_to_kill:
                            pass
                        try:
                            if DEBUG_TASKS:
                                if func.func_name != '_bgalloc':
                                    log('rawserver::listen_forever: run func:', func.func_name)
                                st = time.time()
                            func()
                            if DEBUG_TASKS:
                                et = time.time()
                                diff = et - st
                                log('rawserver::listen_forever:', func.func_name, 'took %.5f' % diff)
                        except (SystemError, MemoryError) as e:
                            self.failfunc(e)
                            return
                        except KeyboardInterrupt as e:
                            return
                        except error:
                            log('rawserver::listen_forever: func exception')
                            print_exc()
                        except Exception as e:
                            raise

                    self.sockethandler.close_dead()
                    self.sockethandler.handle_events(events)
                    if self.doneflag.isSet():
                        if DEBUG:
                            log('rawserver::listen_forever: stopping because done flag set2')
                        return
                    self.sockethandler.close_dead()
                except (SystemError, MemoryError) as e:
                    if DEBUG:
                        log('rawserver::listen_forever: SYS/MEM exception', e)
                    self.failfunc(e)
                    return
                except error:
                    if DEBUG:
                        log('rawserver::listen_forever: ERROR exception')
                        print_exc()
                    if self.doneflag.isSet():
                        return
                except KeyboardInterrupt as e:
                    self.failfunc(e)
                    return
                except Exception as e:
                    raise

        finally:
            self.finished.set()

    def is_finished(self):
        return self.finished.isSet()

    def wait_until_finished(self):
        self.finished.wait()

    def _kill_tasks(self):
        if self.tasks_to_kill:
            new_funcs = []
            for t, func, id in self.funcs:
                if id not in self.tasks_to_kill:
                    new_funcs.append((t, func, id))

            self.funcs = new_funcs
            self.tasks_to_kill = []

    def kill_tasks(self, id):
        self.tasks_to_kill.append(id)

    def exception(self, e, kbint = False):
        if not kbint:
            self.excflag.set()
        self.exccount += 1
        if self.errorfunc is None:
            print_exc()
        elif not kbint:
            self.errorfunc(e)

    def shutdown(self):
        if DEBUG:
            log('rawserver::shuwdown: ---')
        self.sockethandler.shutdown()

    def create_udpsocket(self, port, host):
        if DEBUG:
            log('rawserver::create_udpsocket: host', host, 'port', port)
        return self.sockethandler.create_udpsocket(port, host)

    def start_listening_udp(self, serversocket, handler):
        if DEBUG:
            log('rawserver::start_listening_udp: serversocket', serversocket, 'handler', handler)
        self.sockethandler.start_listening_udp(serversocket, handler)

    def stop_listening_udp(self, serversocket):
        if DEBUG:
            log('rawserver::stop_listening_udp: serversocket', serversocket)
        self.sockethandler.stop_listening_udp(serversocket)
