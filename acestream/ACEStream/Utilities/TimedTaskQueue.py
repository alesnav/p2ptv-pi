#Embedded file name: ACEStream\Utilities\TimedTaskQueue.pyo
import sys
from threading import Thread, Condition
from traceback import print_exc, print_stack, format_stack
from time import time
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False
DEBUG_STACK = False

class TimedTaskQueue:
    __single = None

    def __init__(self, nameprefix = 'TimedTaskQueue', isDaemon = True, debug = False):
        self.debug = debug
        self.cond = Condition()
        self.queue = []
        self.count = 0.0
        self.thread = Thread(target=self.run)
        self.thread.setDaemon(isDaemon)
        self.thread.setName(nameprefix + self.thread.getName())
        self.thread.start()
        if DEBUG_STACK:
            self.callstack = {}

    def add_task(self, task, t = 0, id = None, pos = None):
        if task is None:
            print_stack()
        self.cond.acquire()
        when = time() + t
        if DEBUG_STACK:
            self.callstack[self.count] = format_stack()
        if id != None:
            self.queue = filter(lambda item: item[3] != id, self.queue)
        item = (when,
         self.count,
         task,
         id)
        if pos is None:
            self.queue.append(item)
        else:
            self.queue.insert(pos, item)
        self.count += 1.0
        self.cond.notify()
        self.cond.release()
        if DEBUG or self.debug:
            log('ttqueue:add_task: t', t, 'task', task, 'id', id, 'len(queue)', len(self.queue))

    def run(self):
        while True:
            task = None
            timeout = None
            flag = False
            self.cond.acquire()
            while True:
                while len(self.queue) == 0 or flag:
                    flag = False
                    if timeout is None:
                        self.cond.wait()
                    else:
                        self.cond.wait(timeout)

                self.queue.sort()
                when, count, task, id = self.queue[0]
                now = time()
                if now < when:
                    timeout = when - now
                    if DEBUG or self.debug:
                        log('ttqueue::run: event not due: timeout', timeout, 'task', task)
                    flag = True
                else:
                    self.queue.pop(0)
                    if DEBUG or self.debug:
                        log('ttqueue::run: event due: task', task, 'len(queue)', len(self.queue))
                    if DEBUG_STACK:
                        stack = self.callstack.pop(count)
                    break

            self.cond.release()
            try:
                if task == 'stop':
                    break
                elif task == 'quit':
                    if len(self.queue) == 0:
                        break
                    else:
                        when, count, task, id = self.queue[-1]
                        t = when - time() + 0.001
                        self.add_task('quit', t)
                else:
                    t = time()
                    task()
                    if DEBUG or self.debug:
                        log('ttqueue::run: task finished: time', time() - t, 'task', task)
            except:
                log_exc()
                if DEBUG_STACK:
                    print >> sys.stderr, '<<<<<<<<<<<<<<<<'
                    print >> sys.stderr, 'TASK QUEUED FROM'
                    print >> sys.stderr, ''.join(stack)
                    print >> sys.stderr, '>>>>>>>>>>>>>>>>'

        if DEBUG:
            log('ttqueue::run: exit loop')
