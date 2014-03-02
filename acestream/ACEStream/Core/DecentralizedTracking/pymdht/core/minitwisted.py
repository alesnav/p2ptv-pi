#Embedded file name: ACEStream\Core\DecentralizedTracking\pymdht\core\minitwisted.pyo
import sys
import socket
import threading
import ptime as time
import logging
from floodbarrier import FloodBarrier
logger = logging.getLogger('dht')
BUFFER_SIZE = 1024

class Task(object):

    def __init__(self, delay, callback_fs, *args, **kwds):
        self.delay = delay
        if callable(callback_fs):
            self.callback_fs = [callback_fs]
        else:
            self.callback_fs = callback_fs
        self.args = args
        self.kwds = kwds
        self.call_time = time.time() + self.delay
        self._cancelled = False

    @property
    def cancelled(self):
        return self._cancelled

    def fire_callbacks(self):
        if not self._cancelled:
            for callback_f in self.callback_fs:
                callback_f(*self.args, **self.kwds)

        del self.callback_fs
        del self.args
        del self.kwds

    def cancel(self):
        self._cancelled = True


class TaskManager(object):

    def __init__(self):
        self.tasks = {}
        self.next_task = None

    def add(self, task):
        ms_delay = int(task.delay * 1000)
        self.tasks.setdefault(ms_delay, []).append(task)
        if self.next_task is None or task.call_time < self.next_task.call_time:
            self.next_task = task

    def _get_next_task(self):
        next_task = None
        for _, task_list in self.tasks.items():
            task = task_list[0]
            if next_task is None:
                next_task = task
            if task.call_time < next_task.call_time:
                next_task = task

        return next_task

    def consume_task(self):
        current_time = time.time()
        if self.next_task is None:
            return
        if self.next_task.call_time > current_time:
            return
        task = self.next_task
        ms_delay = int(self.next_task.delay * 1000)
        del self.tasks[ms_delay][0]
        if not self.tasks[ms_delay]:
            del self.tasks[ms_delay]
        self.next_task = self._get_next_task()
        return task


class ThreadedReactor(threading.Thread):

    def __init__(self, task_interval = 0.1, floodbarrier_active = True):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.stop_flag = False
        self._lock = threading.RLock()
        self.task_interval = task_interval
        self.floodbarrier_active = floodbarrier_active
        self.tasks = TaskManager()
        if self.floodbarrier_active:
            self.floodbarrier = FloodBarrier()

    def run(self):
        try:
            self._protected_run()
        except:
            logger.critical('MINITWISTED CRASHED')
            logger.exception('MINITWISTED CRASHED')

    def _protected_run(self):
        last_task_run = time.time()
        stop_flag = self.stop_flag
        while not stop_flag:
            timeout_raised = False
            try:
                data, addr = self.s.recvfrom(BUFFER_SIZE)
            except AttributeError:
                logger.warning('udp_listen has not been called')
                time.sleep(self.task_interval)
                timeout_raised = True
            except socket.timeout:
                timeout_raised = True
            except socket.error as e:
                logger.warning('Got socket.error when receiving data:\n%s' % e)
            else:
                ip_is_blocked = self.floodbarrier_active and self.floodbarrier.ip_blocked(addr[0])
                if ip_is_blocked:
                    logger.warning('%s blocked' % `addr`)
                else:
                    self.datagram_received_f(data, addr)

            if timeout_raised or time.time() - last_task_run > self.task_interval:
                self._lock.acquire()
                try:
                    while True:
                        task = self.tasks.consume_task()
                        if task is None:
                            break
                        task.fire_callbacks()

                    stop_flag = self.stop_flag
                finally:
                    self._lock.release()

        logger.debug('Reactor stopped')

    def stop(self):
        self._lock.acquire()
        try:
            self.stop_flag = True
        finally:
            self._lock.release()

        time.sleep(self.task_interval)

    def listen_udp(self, port, datagram_received_f):
        self.datagram_received_f = datagram_received_f
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.s.settimeout(self.task_interval)
        my_addr = ('', port)
        self.s.bind(my_addr)
        return self.s

    def call_later(self, delay, callback_fs, *args, **kwds):
        self._lock.acquire()
        try:
            task = Task(delay, callback_fs, *args, **kwds)
            self.tasks.add(task)
        finally:
            self._lock.release()

        return task

    def call_now(self, callback_f, *args, **kwds):
        return self.call_later(0, callback_f, *args, **kwds)

    def sendto(self, data, addr):
        self._lock.acquire()
        try:
            bytes_sent = self.s.sendto(data, addr)
            if bytes_sent != len(data):
                logger.critical('Just %d bytes sent out of %d (Data follows)' % (bytes_sent, len(data)))
                logger.critical('Data: %s' % data)
        except socket.error:
            logger.warning('Got socket.error when sending data to %r\n%r' % (addr, data))
        finally:
            self._lock.release()


class ThreadedReactorSocketError(ThreadedReactor):

    def listen_udp(self, delay, callback_f, *args, **kwds):
        self.s = _SocketMock()


class ThreadedReactorMock(object):

    def __init__(self, task_interval = 0.1):
        pass

    def start(self):
        pass

    stop = start

    def listen_udp(self, port, data_received_f):
        self.s = _SocketMock()
        return self.s

    def call_later(self, delay, callback_f, *args, **kwds):
        return Task(delay, callback_f, *args, **kwds)

    def sendto(self, data, addr):
        pass


class _SocketMock(object):

    def sendto(self, data, addr):
        if len(data) > BUFFER_SIZE:
            return BUFFER_SIZE
        raise socket.error

    def recvfrom(self, buffer_size):
        raise socket.error
