#Embedded file name: ACEStream\Core\BitTornado\piecebuffer.pyo
from array import array
from threading import Lock
try:
    True
except:
    True = 1
    False = 0

DEBUG = False
if DEBUG:
    import sys
    from traceback import print_stack

class SingleBuffer:

    def __init__(self, pool):
        self.pool = pool
        self.buf = array('c')
        self.seq = 0
        if DEBUG:
            print >> sys.stderr, '>>pb:create'

    def init(self):
        if DEBUG:
            print >> sys.stderr, '>>pb:init: count', self.pool.count
        self.length = 0

    def append(self, s):
        l = self.length + len(s)
        self.buf[self.length:l] = array('c', s)
        self.length = l
        if DEBUG:
            print >> sys.stderr, '>>pb:append: seq', self.seq, 'len', self.length, 'real', len(self.buf)

    def __len__(self):
        return self.length

    def __getslice__(self, a, b):
        if b > self.length:
            b = self.length
        if b < 0:
            b += self.length
        if a == 0 and b == self.length and len(self.buf) == b:
            return self.buf
        return self.buf[a:b]

    def getarray(self):
        return self.buf[:self.length]

    def release(self):
        if DEBUG:
            print >> sys.stderr, '>>pb:release: seq', self.seq, 'count', self.pool.count
        self.pool.release(self)

    def tostring(self):
        return self.getarray().tostring()

    def update(self, s, pos = None):
        if pos is None:
            pos = 0
        data_len = len(s)
        if DEBUG:
            pass
        self.buf[pos:pos + data_len] = array('c', s)
        if DEBUG:
            print >> sys.stderr, '>>pb:update: seq', self.seq, 'pos', pos, 'data_len', data_len, 'len', self.length, 'real', len(self.buf)

    def trim(self, a = None, b = None):
        if a is None:
            a = 0
        if b is None:
            b = self.length
        if b > self.length:
            b = self.length
        if b < 0:
            b += self.length
        if a == 0 and b == self.length and len(self.buf) == b:
            return
        self.length = int(b - a)
        self.buf[:self.length] = self.buf[a:b]
        if DEBUG:
            print >> sys.stderr, '>>pb:trim: seq', self.seq, 'len', self.length, 'real', len(self.buf)


class BufferPool:

    def __init__(self):
        self.pool = []
        self.lock = Lock()
        if DEBUG:
            self.count = 0

    def new(self):
        self.lock.acquire()
        if self.pool:
            x = self.pool.pop()
        else:
            x = SingleBuffer(self)
            if DEBUG:
                self.count += 1
                x.seq = self.count
        x.init()
        self.lock.release()
        return x

    def release(self, x):
        self.pool.append(x)


_pool = BufferPool()
PieceBuffer = _pool.new
