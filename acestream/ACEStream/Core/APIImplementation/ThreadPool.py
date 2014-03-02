#Embedded file name: ACEStream\Core\APIImplementation\ThreadPool.pyo
import sys
import time
from traceback import print_exc
import threading
DEBUG = False

class ThreadPool:

    def __init__(self, numThreads):
        self.__threads = []
        self.__resizeLock = threading.Condition(threading.Lock())
        self.__taskCond = threading.Condition(threading.Lock())
        self.__tasks = []
        self.__isJoiningStopQueuing = False
        self.__isJoining = False
        self.setThreadCount(numThreads)

    def setThreadCount(self, newNumThreads):
        if self.__isJoining:
            return False
        self.__resizeLock.acquire()
        try:
            self.__setThreadCountNolock(newNumThreads)
        finally:
            self.__resizeLock.release()

        return True

    def __setThreadCountNolock(self, newNumThreads):
        while newNumThreads > len(self.__threads):
            newThread = ThreadPoolThread(self)
            self.__threads.append(newThread)
            newThread.start()

        while newNumThreads < len(self.__threads):
            self.__threads[0].goAway()
            del self.__threads[0]

    def getThreadCount(self):
        self.__resizeLock.acquire()
        try:
            return len(self.__threads)
        finally:
            self.__resizeLock.release()

    def queueTask(self, task, args = (), taskCallback = None):
        if self.__isJoining == True or self.__isJoiningStopQueuing:
            return False
        if not callable(task):
            return False
        self.__taskCond.acquire()
        try:
            self.__tasks.append((task, args, taskCallback))
            self.__taskCond.notifyAll()
            return True
        finally:
            self.__taskCond.release()

    def getNextTask(self):
        self.__taskCond.acquire()
        try:
            while self.__tasks == [] and not self.__isJoining:
                if DEBUG:
                    print >> sys.stderr, 'tp: getnext: wait for taks', threading.currentThread().name
                self.__taskCond.wait()
                if DEBUG:
                    print >> sys.stderr, 'tp: getnext: wait done: thread', threading.currentThread().name, 'tasks', len(self.__tasks), 'isJoining', self.__isJoining

            if self.__isJoining:
                return (None, None, None)
            return self.__tasks.pop(0)
        finally:
            self.__taskCond.release()

    def joinAll(self, waitForTasks = True, waitForThreads = True):
        if DEBUG:
            print >> sys.stderr, 'tp: joinAll'
        self.__isJoiningStopQueuing = True
        if waitForTasks:
            while self.__tasks != []:
                if DEBUG:
                    print >> sys.stderr, 'tp: wait for tasks, left', len(self.__tasks)
                time.sleep(0.1)

        self.__isJoining = True
        self.__resizeLock.acquire()
        try:
            self.__setThreadCountNolock(0)
            self.__isJoining = True
            if DEBUG:
                print >> sys.stderr, '>>tp: join: acquire'
            self.__taskCond.acquire()
            if DEBUG:
                print >> sys.stderr, '>>tp: join: acquire done'
            try:
                if DEBUG:
                    print >> sys.stderr, '>>tp: join: notify'
                self.__taskCond.notifyAll()
                if DEBUG:
                    print >> sys.stderr, '>>tp: join: notify done'
            finally:
                if DEBUG:
                    print >> sys.stderr, '>>tp: join: release'
                self.__taskCond.release()
                if DEBUG:
                    print >> sys.stderr, '>>tp: join: release done'

            if waitForThreads:
                for t in self.__threads:
                    if DEBUG:
                        print >> sys.stderr, 'tp: wait for thread', t.name
                    t.join()
                    if DEBUG:
                        print >> sys.stderr, 'tp: thread finished', t.name
                    del t

            if DEBUG:
                print >> sys.stderr, 'tp: reset isJoining'
            self.__isJoining = False
        finally:
            self.__resizeLock.release()


class ThreadPoolThread(threading.Thread):

    def __init__(self, pool):
        threading.Thread.__init__(self)
        self.setName('SessionPool' + self.getName())
        self.setDaemon(True)
        self.__pool = pool
        self.__isDying = False

    def run(self):
        while self.__isDying == False:
            try:
                cmd, args, callback = self.__pool.getNextTask()
                if cmd is None:
                    break
                elif callback is None:
                    cmd(*args)
                else:
                    callback(cmd(args))
            except:
                print_exc()

    def goAway(self):
        self.__isDying = True
