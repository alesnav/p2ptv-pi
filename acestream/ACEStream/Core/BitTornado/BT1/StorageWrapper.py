#Embedded file name: ACEStream\Core\BitTornado\BT1\StorageWrapper.pyo
import sys
import pickle
import time
import binascii
import math
from traceback import print_stack, print_exc
from random import randrange
from copy import deepcopy
from threading import Lock, RLock, currentThread
from bisect import insort
from ACEStream.Core.Merkle.merkle import MerkleTree
from ACEStream.Core.Utilities.TSCrypto import sha
from ACEStream.Core.BitTornado.bitfield import Bitfield
from ACEStream.Core.BitTornado.clock import clock
from ACEStream.Core.BitTornado.bencode import bencode
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.Utilities.mp4metadata import clear_mp4_metadata_tag
from ACEStream.GlobalConfig import globalConfig
from ACEStream.Core.BitTornado.BT1.Storage import PieceBuffer
DEBUG = False
DEBUG_WRITE = False
DEBUG_HASHCHECK = False
DEBUG_REQUESTS = False
DEBUG2 = False
DEBUG_READ_PIECE = False
DEBUG_LIVE = False
DEBUG_ALLOC = False
DEBUG_ENCRYPTED_STORAGE = False
DEBUG_FLUSH = False
STATS_INTERVAL = 0.2
RARE_RAWSERVER_TASKID = -481

def dummy_status(fractionDone = None, activity = None):
    pass


class Olist:

    def __init__(self, l = []):
        self.d = {}
        for i in l:
            self.d[i] = 1

    def __len__(self):
        return len(self.d)

    def includes(self, i):
        return self.d.has_key(i)

    def add(self, i):
        self.d[i] = 1

    def extend(self, l):
        for i in l:
            self.d[i] = 1

    def pop(self, n = 0):
        k = self.d.keys()
        if n == 0:
            i = min(k)
        elif n == -1:
            i = max(k)
        else:
            k.sort()
            i = k[n]
        del self.d[i]
        return i

    def remove(self, i):
        if self.d.has_key(i):
            del self.d[i]


class fakeflag:

    def __init__(self, state = False):
        self.state = state

    def wait(self):
        pass

    def isSet(self):
        return self.state


class StorageWrapper:

    def __init__(self, infohash, videoinfo, storage, request_size, hashes, piece_size, root_hash, finished, failed, statusfunc = dummy_status, flag = fakeflag(), check_hashes = True, data_flunked = lambda x: None, piece_from_live_source_func = lambda i, d: None, backfunc = None, config = {}, unpauseflag = fakeflag(True), has_extra_files = False, replace_mp4_metatags = None, encryptfunc = None, encrypt_pieces = None):
        self.request_lock = Lock()
        self.videoinfo = videoinfo
        self.storage = storage
        self.request_size = long(request_size)
        self.hashes = hashes
        self.piece_size = long(piece_size)
        self.piece_length = long(piece_size)
        self.finished = finished
        self.report_failure = failed
        self.statusfunc = statusfunc
        self.flag = flag
        self.check_hashes = check_hashes
        self.data_flunked = data_flunked
        self.piece_from_live_source_func = piece_from_live_source_func
        self.backfunc = backfunc
        self.config = config
        self.unpauseflag = unpauseflag
        self.has_extra_files = has_extra_files
        self.encryptfunc = encryptfunc
        self.encrypt_pieces = encrypt_pieces
        self.encrypted_storage = encryptfunc is not None
        self.infohash = infohash
        self.log_prefix = 'sw::' + binascii.hexlify(infohash) + ':'
        self.app_type = globalConfig.get_mode()
        self.alloc_buf = chr(255) * self.piece_size
        self.replace_mp4_metatags = replace_mp4_metatags
        self.live_streaming = self.videoinfo['live']
        self.alloc_type = config.get('alloc_type', 'normal')
        if DEBUG:
            log(self.log_prefix + '__init__: videoinfo', self.videoinfo, 'alloc_type', self.alloc_type, 'replace_mp4_metatags', replace_mp4_metatags, 'files', storage.files)
        self.double_check = config.get('double_check', 0)
        self.triple_check = config.get('triple_check', 0)
        if self.triple_check:
            self.double_check = True
        self.bgalloc_enabled = False
        self.bgalloc_active = False
        self.total_length = storage.get_total_length()
        self.amount_left = self.total_length
        if self.total_length <= self.piece_size * (len(hashes) - 1):
            raise ValueError, 'bad data in responsefile - total too small'
        if self.total_length > self.piece_size * len(hashes):
            raise ValueError, 'bad data in responsefile - total too big'
        self.numactive = [0] * len(hashes)
        self.inactive_requests = [1] * len(hashes)
        self.amount_inactive = self.total_length
        self.amount_obtained = 0
        self.amount_desired = self.total_length
        self.have = Bitfield(len(hashes))
        self.have_cloaked_data = None
        self.blocked = [False] * len(hashes)
        self._blocked = [False] * len(hashes)
        self.blocked_holes = []
        self.blocked_movein = Olist()
        self.blocked_moveout = Olist()
        self.waschecked = [False] * len(hashes)
        self.places = {}
        self.holes = []
        self.stat_active = {}
        self.stat_new = {}
        self.dirty = {}
        self.stat_numflunked = 0
        self.stat_numdownloaded = 0
        self.stat_numfound = 0
        self.download_history = {}
        self.failed_pieces = {}
        self.out_of_place = 0
        self.write_buf_max = config['write_buffer_size'] * 1048576L
        self.write_buf_size = 0L
        self.write_buf = {}
        self.write_buf_list = []
        self.pieces_on_disk_at_startup = []
        self.merkle_torrent = root_hash is not None
        self.root_hash = root_hash
        if self.live_streaming:
            self.initial_hashes = None
        else:
            self.initial_hashes = deepcopy(self.hashes)
        if self.merkle_torrent:
            self.hashes_unpickled = False
            self.check_hashes = True
            self.merkletree = MerkleTree(self.piece_size, self.total_length, self.root_hash, None)
        else:
            self.hashes_unpickled = True
        self.initialize_tasks = [['checking existing data',
          0,
          self.init_hashcheck,
          self.hashcheckfunc], ['moving data',
          1,
          self.init_movedata,
          self.movedatafunc], ['allocating disk space',
          1,
          self.init_alloc,
          self.allocfunc]]
        self.initialize_done = None
        self.backfunc(self._bgsync, max(self.config['auto_flush'] * 60, 60))

    def _bgsync(self):
        if self.config['auto_flush']:
            self.sync()
        self.backfunc(self._bgsync, max(self.config['auto_flush'] * 60, 60))

    def old_style_init(self):
        while self.initialize_tasks:
            msg, done, init, next = self.initialize_tasks.pop(0)
            if init():
                self.statusfunc(activity=msg, fractionDone=done)
                t = clock() + STATS_INTERVAL
                x = 0
                while x is not None:
                    if t < clock():
                        t = clock() + STATS_INTERVAL
                        self.statusfunc(fractionDone=x)
                    self.unpauseflag.wait()
                    if self.flag.isSet():
                        return False
                    x = next()

        self.statusfunc(fractionDone=0)
        return True

    def initialize(self, donefunc, statusfunc = None):
        if DEBUG:
            log(self.log_prefix + 'initialize: enter, backfunc is', self.backfunc)
        self.initialize_done = donefunc
        if statusfunc is None:
            statusfunc = self.statusfunc
        self.initialize_status = statusfunc
        self.initialize_next = None
        self.backfunc(self._initialize, id=RARE_RAWSERVER_TASKID)

    def _initialize(self):
        if not self.unpauseflag.isSet():
            self.backfunc(self._initialize, 1)
            return
        if self.initialize_next:
            x = self.initialize_next()
            if x is None:
                self.initialize_next = None
            else:
                self.initialize_status(fractionDone=x)
        else:
            if not self.initialize_tasks:
                self.initialize_done(success=True)
                self.initialize_done = None
                return
            msg, done, init, next = self.initialize_tasks.pop(0)
            if DEBUG:
                log(self.log_prefix + '_initialize performing task', msg)
            if DEBUG:
                st = time.time()
            if init():
                self.initialize_status(activity=msg, fractionDone=done)
                self.initialize_next = next
            if DEBUG:
                et = time.time()
                diff = et - st
                log(self.log_prefix + '_initialize: task took', diff)
        self.backfunc(self._initialize)

    def init_hashcheck(self):
        if DEBUG_HASHCHECK:
            log(self.log_prefix + 'init_hashcheck: len(hashes)', len(self.hashes), 'amountleft', self.amount_left)
        if self.live_streaming:
            self.set_nohashcheck()
            return False
        if self.flag.isSet():
            if DEBUG_HASHCHECK:
                log(self.log_prefix + 'init_hashcheck: FLAG IS SET')
            return False
        self.check_list = []
        if not self.hashes or self.amount_left == 0:
            self.check_total = 0
            self.finished()
            if DEBUG_HASHCHECK:
                log(self.log_prefix + 'init_hashcheck: download finished')
            return False
        if DEBUG_HASHCHECK:
            log(self.log_prefix + 'init_hashcheck: self.places', self.places)
        self.check_targets = {}
        got = {}
        for p, v in self.places.iteritems():
            got[v] = 1

        if DEBUG_HASHCHECK:
            log(self.log_prefix + 'init_hashcheck: got', got)
        if len(self.places) == 0 and self.storage.get_length_initial_content() == 0L:
            if DEBUG_HASHCHECK:
                log(self.log_prefix + 'init_hashcheck: new VOD, set_nohashcheck')
            self.set_nohashcheck()
            return False
        for i in xrange(len(self.hashes)):
            if len(self.places) > 0:
                if self.places.has_key(i):
                    if self.have[i]:
                        if DEBUG_HASHCHECK:
                            log(self.log_prefix + 'init_hashcheck: have', i, 'from restored')
                        self.pieces_on_disk_at_startup.append(i)
                    self.check_targets[self.hashes[i]] = []
                    if self.places[i] == i:
                        if DEBUG_HASHCHECK:
                            log(self.log_prefix + 'init_hashcheck: self.places[%d] == %d, continue' % (i, i))
                        continue
                    else:
                        self.out_of_place += 1
                if got.has_key(i):
                    if DEBUG_HASHCHECK:
                        log(self.log_prefix + 'init_hashcheck: got.has_key(%d), continue' % i)
                    continue
            if self._waspre(i):
                if self.blocked[i]:
                    if DEBUG_HASHCHECK:
                        log(self.log_prefix + 'init_hashcheck: was preallocated, blocked[%d]' % i)
                    self.places[i] = i
                else:
                    if DEBUG_HASHCHECK:
                        log(self.log_prefix + 'init_hashcheck: was preallocated, add to checklist', i)
                    self.check_list.append(i)
                continue
            if not self.check_hashes:
                self.failed('file supposed to be complete on start-up, but data is missing')
                return False
            self.holes.append(i)
            if self.blocked[i] or self.check_targets.has_key(self.hashes[i]):
                self.check_targets[self.hashes[i]] = []
            else:
                self.check_targets[self.hashes[i]] = [i]

        self.check_total = len(self.check_list)
        self.check_numchecked = 0.0
        self.lastlen = self._piecelen(len(self.hashes) - 1)
        self.numchecked = 0.0
        if DEBUG_HASHCHECK:
            log(self.log_prefix + 'init_hashcheck: self.places', self.places)
            log(self.log_prefix + 'init_hashcheck: checking', self.check_list)
            log(self.log_prefix + 'init_hashcheck: return self.check_total > 0 is ', self.check_total > 0)
        return self.check_total > 0

    def set_nohashcheck(self):
        if DEBUG_HASHCHECK:
            log(self.log_prefix + 'set_nohashcheck: live or empty files, skipping')
        self.places = {}
        self.check_targets = {}
        self.check_list = []
        self.check_total = len(self.check_list)
        self.check_numchecked = 0.0
        self.lastlen = self._piecelen(len(self.hashes) - 1)
        self.numchecked = 0.0
        self.check_targets[self.hashes[0]] = [0]
        self.holes = range(len(self.hashes))

    def get_pieces_on_disk_at_startup(self):
        if DEBUG:
            log(self.log_prefix + 'get_pieces_on_disk_at_startup: self.places len', len(self.places), 'on disk', len(self.pieces_on_disk_at_startup))
        return self.pieces_on_disk_at_startup

    def _markgot(self, piece, pos):
        self.request_lock.acquire()
        try:
            if DEBUG:
                log(self.log_prefix + '_markgot: ' + str(piece) + ' at ' + str(pos))
            self.places[piece] = pos
            self.have[piece] = True
            self.pieces_on_disk_at_startup.append(piece)
            len = self._piecelen(piece)
            self.amount_obtained += len
            self.amount_left -= len
            self.amount_inactive -= len
            self.inactive_requests[piece] = None
            self.waschecked[piece] = self.check_hashes
            self.stat_numfound += 1
        finally:
            self.request_lock.release()

    def hashcheckfunc(self):
        try:
            if self.live_streaming:
                return
            if self.flag.isSet():
                return
            if not self.check_list:
                return
            i = self.check_list.pop(0)
            if not self.check_hashes:
                self._markgot(i, i)
            else:
                d1 = self.read_raw(i, i, 0, self.lastlen)
                if d1 is None:
                    return
                sh = sha(d1[:])
                d1.release()
                sp = sh.digest()
                d2 = self.read_raw(i, i, self.lastlen, self._piecelen(i) - self.lastlen)
                if d2 is None:
                    return
                sh.update(d2[:])
                d2.release()
                s = sh.digest()
                if DEBUG_HASHCHECK:
                    if s != self.hashes[i]:
                        log(self.log_prefix + 'hashcheckfunc: piece corrupt', i)
                if not self.hashes_unpickled:
                    if DEBUG_HASHCHECK:
                        log(self.log_prefix + 'hashcheckfunc: Merkle torrent, saving calculated hash', i)
                    self.initial_hashes[i] = s
                    self._markgot(i, i)
                elif s == self.hashes[i]:
                    self._markgot(i, i)
                elif self.check_targets.get(s) and self._piecelen(i) == self._piecelen(self.check_targets[s][-1]):
                    self._markgot(self.check_targets[s].pop(), i)
                    self.out_of_place += 1
                elif not self.have[-1] and sp == self.hashes[-1] and (i == len(self.hashes) - 1 or not self._waspre(len(self.hashes) - 1)):
                    self._markgot(len(self.hashes) - 1, i)
                    self.out_of_place += 1
                else:
                    self.places[i] = i
            self.numchecked += 1
            if self.amount_left == 0:
                if not self.hashes_unpickled:
                    self.merkletree = MerkleTree(self.piece_size, self.total_length, None, self.initial_hashes)
                    if self.merkletree.compare_root_hashes(self.root_hash):
                        if DEBUG_HASHCHECK:
                            log(self.log_prefix + 'hashcheckfunc: Merkle torrent, initial seeder')
                        self.hashes = self.initial_hashes
                    else:
                        if DEBUG_HASHCHECK:
                            log(self.log_prefix + 'hashcheckfunc: Merkle torrent, NOT a seeder')
                        self.failed('download corrupted, hash tree does not compute; please delete and restart')
                        return 1
                self.finished()
            return self.numchecked / self.check_total
        except Exception as e:
            log_exc()
            self.failed('download corrupted: ' + str(e) + '; please delete and restart')

    def init_movedata(self):
        if self.flag.isSet():
            return False
        if self.alloc_type != 'sparse':
            return False
        self.storage.top_off()
        self.movelist = []
        if self.out_of_place == 0:
            for i in self.holes:
                self.places[i] = i

            self.holes = []
            return False
        self.tomove = float(self.out_of_place)
        for i in xrange(len(self.hashes)):
            if not self.places.has_key(i):
                self.places[i] = i
            elif self.places[i] != i:
                self.movelist.append(i)

        self.holes = []
        return True

    def movedatafunc(self):
        if self.flag.isSet():
            return
        if not self.movelist:
            return
        i = self.movelist.pop(0)
        old = self.read_raw(i, self.places[i], 0, self._piecelen(i))
        if old is None:
            return
        if DEBUG:
            log(self.log_prefix + 'movedatafunc: i', i)
        if not self.write_raw(i, i, 0, old):
            return
        if self.double_check and self.have[i]:
            if self.triple_check:
                old.release()
                old = self.read_raw(i, i, 0, self._piecelen(i), flush_first=True)
                if old is None:
                    return
            if sha(old[:]).digest() != self.hashes[i]:
                self.failed('download corrupted, piece on disk failed triple check; please delete and restart')
                return
        old.release()
        self.places[i] = i
        self.tomove -= 1
        return self.tomove / self.out_of_place

    def init_alloc(self):
        if self.flag.isSet():
            return False
        if not self.holes:
            return False
        self.numholes = float(len(self.holes))
        ret = False
        if self.app_type == 'stream' or self.app_type == 'node':
            self.storage.top_off(8)
        if self.alloc_type == 'pre-allocate':
            self.bgalloc_enabled = True
            ret = True
        if self.alloc_type == 'background':
            self.bgalloc_enabled = True
        if self.bgalloc_enabled:
            self.backfunc(self._bgalloc, 0.1)
        if ret:
            return ret
        if self.blocked_moveout:
            return True
        return False

    def _allocfunc(self):
        while self.holes:
            n = self.holes.pop(0)
            if self.blocked[n]:
                if not self.blocked_movein:
                    self.blocked_holes.append(n)
                    continue
                if not self.places.has_key(n):
                    b = self.blocked_movein.pop(0)
                    oldpos = self._move_piece(b, n)
                    self.places[oldpos] = oldpos
                    return None
            if self.places.has_key(n):
                oldpos = self._move_piece(n, n)
                self.places[oldpos] = oldpos
                return None
            return n

    def allocfunc(self):
        if self.flag.isSet():
            return
        if self.blocked_moveout:
            self.bgalloc_active = True
            n = self._allocfunc()
            if n is not None:
                if self.blocked_moveout.includes(n):
                    self.blocked_moveout.remove(n)
                    b = n
                else:
                    b = self.blocked_moveout.pop(0)
                oldpos = self._move_piece(b, n)
                self.places[oldpos] = oldpos
            return len(self.holes) / self.numholes
        if self.holes and self.bgalloc_enabled:
            self.bgalloc_active = True
            n = self._allocfunc()
            if n is not None:
                if DEBUG:
                    log(self.log_prefix + 'allocfunc: n', n)
                self.write_raw(n, n, 0, self.alloc_buf[:self._piecelen(n)])
                self.places[n] = n
            return len(self.holes) / self.numholes
        self.bgalloc_active = False

    def bgalloc(self):
        if self.bgalloc_enabled:
            if not self.holes and not self.blocked_moveout and self.backfunc:
                self.backfunc(self.storage.flush)
        self.bgalloc_enabled = True
        return False

    def _bgalloc(self):
        self.allocfunc()
        if self.config.get('alloc_rate', 0) < 0.1:
            self.config['alloc_rate'] = 0.1
        self.backfunc(self._bgalloc, float(self.piece_size) / (self.config['alloc_rate'] * 1048576))

    def _waspre(self, piece):
        return self.storage.was_preallocated(piece * self.piece_size, self._piecelen(piece))

    def _piecelen(self, piece):
        if piece < len(self.hashes) - 1:
            return self.piece_size
        else:
            return self.total_length - piece * self.piece_size

    def get_amount_left(self):
        return self.amount_left

    def do_I_have_anything(self):
        return self.amount_left < self.total_length

    def _make_inactive(self, index):
        length = self._piecelen(index)
        requests = []
        x = 0
        while x + self.request_size < length:
            requests.append((x, self.request_size))
            x += self.request_size

        requests.append((x, length - x))
        if DEBUG_REQUESTS:
            log(self.log_prefix + '_make_inactive: index', index, 'req', requests)
        self.inactive_requests[index] = requests

    def is_endgame(self):
        return not self.amount_inactive

    def reset_endgame(self, requestlist):
        for index, begin, length in requestlist:
            self.request_lost(index, begin, length)

    def get_have_list(self):
        return self.have.tostring()

    def get_have_copy(self):
        return self.have.copy()

    def get_have_list_cloaked(self):
        if self.have_cloaked_data is None:
            newhave = Bitfield(copyfrom=self.have)
            unhaves = []
            n = min(randrange(2, 5), len(self.hashes))
            while len(unhaves) < n:
                unhave = randrange(min(32, len(self.hashes)))
                if unhave not in unhaves:
                    unhaves.append(unhave)
                    newhave[unhave] = False

            self.have_cloaked_data = (newhave.tostring(), unhaves)
        return self.have_cloaked_data

    def do_I_have(self, index):
        return self.have[index]

    def do_I_have_requests(self, index):
        ret = not not self.inactive_requests[index]
        return ret

    def is_unstarted(self, index):
        self.request_lock.acquire()
        try:
            return not self.have[index] and not self.numactive[index] and not self.dirty.has_key(index)
        finally:
            self.request_lock.release()

    def get_hash(self, index):
        return self.hashes[index]

    def get_stats(self):
        return (self.amount_obtained, self.amount_desired, self.have)

    def new_request(self, index):
        self.request_lock.acquire()
        try:
            if self.inactive_requests[index] is None:
                if DEBUG_REQUESTS:
                    log(self.log_prefix + 'new_request: inactive_requests is none: index', index, 'have', self.have[index], 'numactive', self.numactive[index], 'finished', len(self.dirty.get(index, [])), 'thread', currentThread().getName())
                return
            if self.inactive_requests[index] == 1:
                self._make_inactive(index)
            if len(self.inactive_requests[index]) == 0:
                if DEBUG_REQUESTS:
                    log(self.log_prefix + 'new_request: inactive_requests is empty: index', index, 'have', self.have[index], 'numactive', self.numactive[index], 'finished', len(self.dirty.get(index, [])), 'thread', currentThread().getName())
                return
            self.numactive[index] += 1
            self.stat_active[index] = 1
            if not self.dirty.has_key(index):
                self.stat_new[index] = 1
            r = self.inactive_requests[index].pop(0)
            self.amount_inactive -= r[1]
            if DEBUG_REQUESTS:
                log(self.log_prefix + 'new_request: index', index, 'have', self.have[index], 'inactive', len(self.inactive_requests[index]), 'numactive', self.numactive[index], 'finished', len(self.dirty.get(index, [])), 'amount_inactive', self.amount_inactive, 'thread', currentThread().getName())
            return r
        finally:
            self.request_lock.release()

    def get_all_piece_request(self, index):
        self.request_lock.acquire()
        try:
            if self.inactive_requests[index] is None:
                if DEBUG_REQUESTS:
                    log(self.log_prefix + 'get_all_piece_request: inactive_requests is none: index', index, 'have', self.have[index], 'numactive', self.numactive[index], 'finished', len(self.dirty.get(index, [])), 'thread', currentThread().getName())
                return
            if self.inactive_requests[index] == 1:
                self._make_inactive(index)
            rs = self.inactive_requests[index]
            self.numactive[index] += len(rs)
            self.stat_active[index] = 1
            if not self.dirty.has_key(index):
                self.stat_new[index] = 1
            ret = rs[:]
            while len(rs):
                r = rs.pop(0)
                self.amount_inactive -= r[1]

            if DEBUG_REQUESTS:
                log(self.log_prefix + 'get_all_piece_request: index', index, 'have', self.have[index], 'inactive', len(self.inactive_requests[index]), 'numactive', self.numactive[index], 'finished', len(self.dirty.get(index, [])), 'amount_inactive', self.amount_inactive, 'thread', currentThread().getName())
            return ret
        finally:
            self.request_lock.release()

    def get_finished_requests(self, index):
        self.request_lock.acquire()
        try:
            if self.have[index]:
                return
            ret = []
            if self.dirty.has_key(index):
                for begin, length in self.dirty[index].iteritems():
                    ret.append((begin, length))

                ret.sort(key=lambda x: x[0])
            return ret
        finally:
            self.request_lock.release()

    def get_unfinished_gaps(self, index):
        piece_len = self._piecelen(index)
        finished_requests = self.get_finished_requests(index)
        if finished_requests is None:
            return []
        gaps = []
        gap_start = 0
        gap_end = piece_len
        for begin, length in finished_requests:
            if begin == gap_start:
                gap_start = begin + length
            else:
                gap_end = begin
                gaps.append((gap_start, gap_end - 1))
                gap_start = begin + length
                gap_end = piece_len

        if gap_end == piece_len and gap_start < gap_end:
            gaps.append((gap_start, gap_end - 1))
        if DEBUG_REQUESTS:
            log(self.log_prefix + 'get_unfinished_gaps: finished_requests', finished_requests, 'gaps', gaps)
        return gaps

    def get_request(self, index, begin, length, lock = False):
        if lock:
            self.request_lock.acquire()
        try:
            if self.inactive_requests[index] == 1:
                self._make_inactive(index)
            try:
                i = self.inactive_requests[index].index((begin, length))
            except:
                if DEBUG_REQUESTS:
                    log(self.log_prefix + 'get_request: not found: index', index, 'begin', begin, 'length', length, 'inactive_requests[index]', self.inactive_requests[index], 'thread', currentThread().getName())
                return

            r = self.inactive_requests[index].pop(i)
            self.numactive[index] += 1
            self.stat_active[index] = 1
            if not self.dirty.has_key(index):
                self.stat_new[index] = 1
            self.amount_inactive -= r[1]
            if DEBUG_REQUESTS:
                log(self.log_prefix + 'get_request: index', index, 'begin', begin, 'length', length, 'numactive', self.numactive[index], 'inactive', len(self.inactive_requests[index]), 'thread', currentThread().getName())
            return r
        finally:
            if lock:
                self.request_lock.release()

    def preallocate_file(self, first_piece, last_piece):
        if DEBUG:
            log(self.log_prefix + 'preallocate_file: first', first_piece, 'last', last_piece)
        self.storage.preallocate_file(first_piece * self.piece_size, self.piece_size, True)
        self.storage.preallocate_file(last_piece * self.piece_size, self.piece_size, False)

    def write_raw(self, index, place, begin, data):
        try:
            if DEBUG_WRITE or DEBUG_FLUSH:
                st = time.time()
            if DEBUG_WRITE:
                log(self.log_prefix + 'write_raw: index', index, 'place', place, 'begin', begin, 'self.piece_size', self.piece_size)
            if self.encryptfunc is not None:
                if DEBUG_ENCRYPTED_STORAGE:
                    t = time.time()
                data = self.encryptfunc(index, data, True)
                if DEBUG_ENCRYPTED_STORAGE:
                    log(self.log_prefix + 'write_raw: encrypt data: index', index, 'place', place, 'begin', begin, 'len', len(data), 'time', time.time() - t)
            self.storage.write(self.piece_size * place + begin, data)
            if DEBUG_WRITE or DEBUG_FLUSH:
                log('sw::write_raw: time', '%.6f' % (time.time() - st), 'index', index, 'place', place, 'begin', begin, 'data', len(data))
            return True
        except IOError as e:
            log_exc()
            self.failed('IO Error: ' + str(e))
            return False

    def _write_to_buffer(self, piece, start, data):
        if not self.write_buf_max:
            if DEBUG_WRITE:
                log(self.log_prefix + '_write_to_buffer: write_buf_max is null: self.places', self.places, 'piece', piece, 'start', start, 'self.places[piece]', self.places[piece])
            return self.write_raw(piece, self.places[piece], start, data)
        self.write_buf_size += len(data)
        if DEBUG_WRITE:
            log(self.log_prefix + '_write_to_buffer: self.write_buf_size', self.write_buf_size, 'self.write_buf_max', self.write_buf_max)
        while self.write_buf_size > self.write_buf_max:
            old = self.write_buf_list.pop(0)
            if DEBUG_FLUSH:
                log('sw::_write_to_buffer: flush: piece', old, 'write_buf_size', self.write_buf_size, 'write_buf_max', self.write_buf_max, 'len(write_buf_list)', len(self.write_buf_list))
            if not self._flush_buffer(old, True):
                return False

        if self.write_buf.has_key(piece):
            self.write_buf_list.remove(piece)
        else:
            self.write_buf[piece] = []
        self.write_buf_list.append(piece)
        self.write_buf[piece].append((start, data))
        if DEBUG_FLUSH:
            log('sw::_write_to_buffer: append: piece', piece, 'start', start, 'len(data)', len(data), 'data', data[:20], data[-114:], 'write_buf_list', len(self.write_buf_list), 'write_buf', len(self.write_buf), 'write_buf[piece]', len(self.write_buf[piece]))
        return True

    def _flush_buffer(self, piece, popped = False):
        if not self.write_buf.has_key(piece):
            return True
        if not popped:
            self.write_buf_list.remove(piece)
        l = self.write_buf[piece]
        del self.write_buf[piece]
        l.sort()
        chunks = []
        data = ''
        data_len = 0
        last_start = l[0][0]
        for _start, buf in l:
            buf_len = len(buf)
            self.write_buf_size -= buf_len
            if last_start is not None and _start != last_start + data_len:
                chunks.append((last_start, data))
                data = ''
                data_len = 0
                last_start = _start
            data += buf
            data_len += buf_len

        if data_len > 0:
            chunks.append((last_start, data))
        if DEBUG_FLUSH:
            log('sw::_flush_buffer: dump chunks: piece', piece)
            for _start, buf in l:
                log('sw::_flush_buffer: write_buf: start', _start, 'len', len(buf))

            for _start, buf in chunks:
                log('sw::_flush_buffer: chunk: start', _start, 'len', len(buf))

        if not self.places.has_key(piece):
            if DEBUG:
                log(self.log_prefix + '_flush_buffer: skip flush, piece invalidated: piece', piece)
        else:
            for chunk in chunks:
                if DEBUG_WRITE or DEBUG_FLUSH:
                    log('sw::_flush_buffer: piece', piece, 'start', chunk[0], 'self.places[piece]', self.places[piece], 'len(data)', len(chunk[1]), 'data', chunk[1][:20], chunk[1][-114:])
                if not self.write_raw(piece, self.places[piece], chunk[0], chunk[1]):
                    return False

        return True

    def sync(self):
        spots = {}
        for p in self.write_buf_list:
            try:
                spots[self.places[p]] = p
            except KeyError:
                pass

        l = spots.keys()
        l.sort()
        for i in l:
            try:
                self._flush_buffer(spots[i])
            except:
                pass

        try:
            self.storage.sync()
        except IOError as e:
            self.failed('IO Error: ' + str(e))
        except OSError as e:
            self.failed('OS Error: ' + str(e))

    def _move_piece(self, index, newpos):
        oldpos = self.places[index]
        if DEBUG:
            log(self.log_prefix + '_move_piece: index', index, 'oldpos', oldpos, 'newpos', newpos)
        old = self.read_raw(index, oldpos, 0, self._piecelen(index))
        if old is None:
            return -1
        if not self.write_raw(index, newpos, 0, old):
            return -1
        self.places[index] = newpos
        if self.have[index] and (self.triple_check or self.double_check and index == newpos):
            if self.triple_check:
                old.release()
                old = self.read_raw(index, newpos, 0, self._piecelen(index), flush_first=True)
                if old is None:
                    return -1
            if sha(old[:]).digest() != self.hashes[index]:
                self.failed('download corrupted, piece on disk failed triple check; please delete and restart')
                return -1
        old.release()
        if self.blocked[index]:
            self.blocked_moveout.remove(index)
            if self.blocked[newpos]:
                self.blocked_movein.remove(index)
            else:
                self.blocked_movein.add(index)
        else:
            self.blocked_movein.remove(index)
            if self.blocked[newpos]:
                self.blocked_moveout.add(index)
            else:
                self.blocked_moveout.remove(index)
        return oldpos

    def _clear_space(self, index):
        if DEBUG2:
            log(self.log_prefix + '_clear_space: index', index)
            log(self.log_prefix + '_clear_space: self.holes', self.holes)
            log(self.log_prefix + '_clear_space: self.places', self.places)
            log(self.log_prefix + '_clear_space: self.blocked', self.blocked)
            log(self.log_prefix + '_clear_space: self.blocked_holes', self.blocked_holes)
            log(self.log_prefix + '_clear_space: self.blocked_movein', self.blocked_movein)
        if self.has_extra_files and not self.encrypted_storage:
            self.places[index] = index
            return False
        h = self.holes.pop(0)
        n = h
        if DEBUG2:
            log(self.log_prefix + '_clear_space:1: index', index, 'h', h, 'n', n, 'holes', self.holes, 'places', self.places)
        if self.blocked[n]:
            if not self.blocked_movein:
                self.blocked_holes.append(n)
                return True
            if not self.places.has_key(n):
                b = self.blocked_movein.pop(0)
                oldpos = self._move_piece(b, n)
                if oldpos < 0:
                    return False
                n = oldpos
        if self.places.has_key(n):
            oldpos = self._move_piece(n, n)
            if DEBUG2:
                log(self.log_prefix + '_clear_space: places has key: n', n, 'oldpos', oldpos)
            if oldpos < 0:
                return False
            n = oldpos
        if index == n or index in self.holes:
            if DEBUG2:
                log(self.log_prefix + '_clear_space:2: index', index, 'h', h, 'n', n, 'self.holes', self.holes)
            if n == h and self.app_type != 'stream' and self.app_type != 'node':
                self.write_raw(index, n, 0, self.alloc_buf[:self._piecelen(n)])
            self.places[index] = n
            if DEBUG2:
                log(self.log_prefix + '_clear_space: set place: places[%d]=%d' % (index, n))
            if self.blocked[n]:
                self.blocked_moveout.add(index)
            return False
        for p, v in self.places.iteritems():
            if v == index:
                break
        else:
            if DEBUG2:
                log(self.log_prefix + '_clear_space: sfailed: index', index, 'places', places)
            self.failed('download corrupted; please delete and restart')
            return False

        self._move_piece(p, n)
        if DEBUG2:
            log(self.log_prefix + '_clear_space: set place: places[%d]=%d' % (index, index))
        self.places[index] = index
        return False

    def piece_came_in(self, index, begin, hashlist, piece, source = None):
        self.request_lock.acquire()
        try:
            return self._piece_came_in(index, begin, hashlist, piece, source)
        finally:
            self.request_lock.release()

    def _piece_came_in(self, index, begin, hashlist, piece, source = None):
        chunk_length = len(piece)
        if self.have[index]:
            if DEBUG_REQUESTS:
                log(self.log_prefix + 'piece_came_in: piece is already completed: index', index, 'begin', begin, 'len', chunk_length, 'thread', currentThread().getName())
            return 2
        if self.inactive_requests[index] == 1 or (begin, chunk_length) in self.inactive_requests[index]:
            req = self.get_request(index, begin, chunk_length)
            if DEBUG_REQUESTS:
                log(self.log_prefix + 'piece_came_in: make inactive request: index', index, 'begin', begin, 'len', chunk_length, 'req', req, 'inactive', len(self.inactive_requests[index]), 'numactive', self.numactive[index], 'finished', len(self.dirty.get(index, [])), 'amount_inactive', self.amount_inactive, 'thread', currentThread().getName())
        if self.dirty.has_key(index) and self.dirty[index].has_key(begin):
            if DEBUG_REQUESTS:
                log(self.log_prefix + 'piece_came_in: request is already finished: index', index, 'begin', begin, 'len', chunk_length, 'thread', currentThread().getName())
            return 1
        if self.merkle_torrent and len(hashlist) > 0:
            if self.merkletree.check_hashes(hashlist):
                self.merkletree.update_hash_admin(hashlist, self.hashes)
            else:
                raise ValueError('bad list of hashes')
        if DEBUG_REQUESTS:
            log(self.log_prefix + 'piece_came_in: index', index, 'begin', begin, 'len', chunk_length, 'numactive', self.numactive[index], 'inactive', len(self.inactive_requests[index]), 'finished', len(self.dirty.get(index, [])), 'thread', currentThread().getName())
        if not self.places.has_key(index):
            while self._clear_space(index):
                pass

            if DEBUG or DEBUG_ENCRYPTED_STORAGE:
                log(self.log_prefix + 'piece_came_in: new place for ' + str(index) + ' at ' + str(self.places[index]))
        if self.flag.isSet():
            return 0
        if self.failed_pieces.has_key(index):
            old = self.read_raw(index, self.places[index], begin, chunk_length)
            if old is None:
                return 1
            if old[:].tostring() != piece:
                try:
                    self.failed_pieces[index][self.download_history[index][begin]] = 1
                except:
                    self.failed_pieces[index][None] = 1

            old.release()
        self.download_history.setdefault(index, {})[begin] = source
        if DEBUG and self.failed_pieces.has_key(index):
            log(self.log_prefix + 'piece_came_in: index', index, 'begin', begin, 'failed_pieces', self.failed_pieces[index], 'thread', currentThread().getName())
        if not self._write_to_buffer(index, begin, piece):
            if DEBUG:
                log(self.log_prefix + 'piece_came_in: index=%d: self._write_to_buffer returned False, return True' % index, 'thread', currentThread().getName())
            return 1
        self.amount_obtained += chunk_length
        self.dirty.setdefault(index, {})[begin] = chunk_length
        self.numactive[index] -= 1
        if not self.numactive[index] and self.stat_active.has_key(index):
            del self.stat_active[index]
        if self.stat_new.has_key(index):
            del self.stat_new[index]
        if DEBUG:
            log(self.log_prefix + 'piece_came_in: index', index, 'data', piece[:20], piece[-114:], 'inactive', len(self.inactive_requests[index]), 'numactive', self.numactive[index], 'finished', len(self.dirty[index]), 'thread', currentThread().name)
        if DEBUG:
            try:
                pass
            except:
                print_exc()

        if self.inactive_requests[index] or self.numactive[index]:
            return 1
        del self.dirty[index]
        if not self._flush_buffer(index):
            if DEBUG_WRITE:
                log(self.log_prefix + '_piece_came_in: _flush_buffer() failed: index', index)
            raise Exception('Cannot flush buffer')
        length = self._piecelen(index)
        data = self.read_raw(index, self.places[index], 0, length, flush_first=self.triple_check)
        if data is None:
            if DEBUG:
                log(self.log_prefix + 'piece_came_in: index', index, 'got piece but cannot read it from storage')
            raise Exception('Cannot read piece from storage')
        if DEBUG_REQUESTS:
            log(self.log_prefix + 'piece_came_in: index', index, 'got piece, self._piecelen(index)', length, 'len(data)', len(data), 'data', data[:20], data[-114:], 'thread', currentThread().name)
        if not self.live_streaming and self.replace_mp4_metatags:
            data_string = data.tostring()
            data_updated = False
            for tag in self.replace_mp4_metatags[:]:
                updated_data = clear_mp4_metadata_tag(tag, data_string)
                if updated_data is not None:
                    if DEBUG:
                        log(self.log_prefix + 'piece_came_in: remove mp4 metatags from piece: index', index, 'tag', tag)
                    self.replace_mp4_metatags.remove(tag)
                    if not self.write_raw(index, self.places[index], 0, updated_data):
                        raise Exception, 'Cannot write to storage'
                    data_string = updated_data
                    data_updated = True

            if data_updated:
                data.update(data_string)
        pieceok = False
        if self.live_streaming:
            if self.piece_from_live_source_func(index, data[:]):
                pieceok = True
            data.release()
        else:
            hash = sha(data[:]).digest()
            data.release()
            if hash == self.hashes[index]:
                pieceok = True
            elif DEBUG:
                log(self.log_prefix + 'piece_came_in: bad hash: hash', binascii.hexlify(hash), 'self.hashes[%d]' % index, binascii.hexlify(self.hashes[index]))
        if not pieceok:
            self.amount_obtained -= length
            self.data_flunked(length, index)
            self.inactive_requests[index] = 1
            self.amount_inactive += length
            self.stat_numflunked += 1
            self.failed_pieces[index] = {}
            allsenders = {}
            for d in self.download_history[index].values():
                allsenders[d] = 1

            if DEBUG:
                log(self.log_prefix + 'piece_came_in: hashcheck failed: index', index, 'begin', begin, 'allsenders', allsenders)
            if len(allsenders) == 1:
                culprit = allsenders.keys()[0]
                if culprit is not None:
                    culprit.failed(index, bump=True)
                del self.failed_pieces[index]
            if self.live_streaming:
                if DEBUG:
                    log(self.log_prefix + 'piece_came_in: kicking peer')
                raise ValueError('Arno quick fix: Unauth data unacceptable')
            return 0
        if DEBUG:
            log(self.log_prefix + '_piece_came_in: good piece: index', index, 'piecelen', length, 'amount_left', self.amount_left, 'thread', currentThread().getName())
        self.have[index] = True
        self.inactive_requests[index] = None
        self.waschecked[index] = True
        self.amount_left -= length
        self.stat_numdownloaded += 1
        for d in self.download_history[index].values():
            if d is not None:
                d.good(index)

        del self.download_history[index]
        if self.failed_pieces.has_key(index):
            for d in self.failed_pieces[index].keys():
                if d is not None:
                    d.failed(index)

            del self.failed_pieces[index]
        if self.amount_left == 0:
            self.finished()
        return 2

    def request_lost(self, index, begin, length):
        self.request_lock.acquire()
        try:
            if self.inactive_requests[index] is None or self.inactive_requests[index] == 1:
                if DEBUG_REQUESTS:
                    log(self.log_prefix + 'request_lost: inactive_requests was reset: index', index, 'begin', begin, 'len', length, 'inactive', self.inactive_requests[index], 'numactive', self.numactive[index], 'finished', self.dirty.get(index, None), 'thread', currentThread().getName())
                return
            if (begin, length) in self.inactive_requests[index]:
                if DEBUG_REQUESTS:
                    log(self.log_prefix + 'request_lost: request is inactive: index', index, 'begin', begin, 'len', length, 'inactive', len(self.inactive_requests[index]), 'numactive', self.numactive[index], 'finished', self.dirty.get(index, None), 'inactive_requests', self.inactive_requests[index], 'thread', currentThread().getName())
                return
            if self.dirty.has_key(index) and self.dirty[index].has_key(begin):
                if DEBUG_REQUESTS:
                    log(self.log_prefix + 'request_lost: request is finished: index', index, 'begin', begin, 'len', length, 'inactive', len(self.inactive_requests[index]), 'numactive', self.numactive[index], 'finished', self.dirty.get(index, None), 'inactive_requests', self.inactive_requests[index], 'thread', currentThread().getName())
                return
            insort(self.inactive_requests[index], (begin, length))
            self.amount_inactive += length
            self.numactive[index] -= 1
            if DEBUG_REQUESTS:
                log(self.log_prefix + 'request_lost: index', index, 'begin', begin, 'len', length, 'numactive', self.numactive[index], 'inactive', len(self.inactive_requests[index]), 'finished', len(self.dirty.get(index, [])), 'amount_inactive', self.amount_inactive, 'thread', currentThread().getName())
            if not self.numactive[index]:
                del self.stat_active[index]
                if self.stat_new.has_key(index):
                    del self.stat_new[index]
        except:
            log_exc()
        finally:
            self.request_lock.release()

    def get_piece(self, index, begin, length):
        pb = self.do_get_piece(index, begin, length)
        if self.merkle_torrent and pb is not None and begin == 0:
            hashlist = self.merkletree.get_hashes_for_piece(index)
        else:
            hashlist = []
        return [pb, hashlist]

    def do_get_piece(self, index, begin, length):
        if not self.have[index]:
            if DEBUG2:
                log(">>sw:do_get_piece: don't have piece", index)
            if DEBUG_READ_PIECE:
                log('>>read:sw:do_get_piece: dont have: index', index)
            return
        data = None
        if not self.waschecked[index]:
            if DEBUG_READ_PIECE:
                log('>>read:sw:do_get_piece: not checked, read whole piece: index', index)
            data = self.read_raw(index, self.places[index], 0, self._piecelen(index))
            if data is None:
                if DEBUG2:
                    log('>>sw:do_get_piece: return none 1: index', index)
                if DEBUG_READ_PIECE:
                    log('>>read:sw:do_get_piece: read none: index', index)
                return
            if not self.live_streaming and sha(data[:]).digest() != self.hashes[index]:
                if DEBUG2:
                    log('>>sw:do_get_piece: return none 2: index', index)
                if DEBUG_READ_PIECE:
                    log('>>read:sw:do_get_piece: hash failed: index', index)
                return
            self.waschecked[index] = True
            if length == -1 and begin == 0:
                if DEBUG_READ_PIECE:
                    log('>>read:sw:do_get_piece: return data: index', index, 'length', length, 'begin', begin)
                return data
        if length == -1:
            if begin > self._piecelen(index):
                if DEBUG2:
                    log('>>sw:do_get_piece: return none 3: index', index)
                if DEBUG_READ_PIECE:
                    log('>>read:sw:do_get_piece: begin > piecelen, return none: index', index, 'begin', begin, 'piecelen', self._piecelen(index))
                return
            length = self._piecelen(index) - begin
            if begin == 0:
                if DEBUG_READ_PIECE:
                    log('>>read:sw:do_get_piece: return read_raw(): index', index, 'begin', begin, 'piecelen', self._piecelen(index), 'length', length)
                return self.read_raw(index, self.places[index], 0, length)
        elif begin + length > self._piecelen(index):
            if DEBUG2:
                log('>>sw:do_get_piece: return none 4: index', index)
            if DEBUG_READ_PIECE:
                log('>>read:sw:do_get_piece: begin+length > piecelen, return none: index', index, 'begin', begin, 'piecelen', self._piecelen(index), 'length', length)
            return
        if data is not None:
            if DEBUG_READ_PIECE:
                t = time.time()
            s = data[begin:begin + length]
            if DEBUG_READ_PIECE:
                time_slice = time.time() - t
                t = time.time()
            data.release()
            if DEBUG_READ_PIECE:
                time_release = time.time() - t
                log('>>read:sw:do_get_piece: release data and return slice: index', index, 'begin', begin, 'piecelen', self._piecelen(index), 'length', length, 'time_slice', time_slice, 'time_release', time_release)
            return s
        if DEBUG_READ_PIECE:
            t = time.time()
        data = self.read_raw(index, self.places[index], begin, length)
        if DEBUG_READ_PIECE:
            time_read = time.time() - t
            log('>>read:sw:do_get_piece: final read_raw(): index', index, 'begin', begin, 'piecelen', self._piecelen(index), 'length', length, 'time_read', time_read)
        if data is None:
            if DEBUG2:
                log('>>sw:do_get_piece: return none 5: index', index)
            if DEBUG_READ_PIECE:
                log('>>read:sw:do_get_piece: final read_raw() returned none: index', index, 'begin', begin, 'piecelen', self._piecelen(index), 'length', length)
            return
        if DEBUG_READ_PIECE:
            t = time.time()
        s = data.getarray()
        if DEBUG_READ_PIECE:
            time_getarray = time.time() - t
            t = time.time()
        data.release()
        if DEBUG_READ_PIECE:
            time_release = time.time() - t
        if DEBUG2:
            log('>>sw:do_get_piece: len(s)', len(s))
        if DEBUG_READ_PIECE:
            time_release = time.time() - t
            log('>>read:sw:do_get_piece: final read_raw() finished: index', index, 'begin', begin, 'piecelen', self._piecelen(index), 'length', length, 'time_getarray', time_getarray, 'time_release', time_release)
        return s

    def read_raw(self, index, piece, begin, length, flush_first = False):
        try:
            if self.encryptfunc is None or self.live_streaming or index not in self.encrypt_pieces:
                data = self.storage.read(self.piece_size * piece + begin, length, flush_first)
            else:
                offset = begin % 16384
                if DEBUG_READ_PIECE or DEBUG_ENCRYPTED_STORAGE:
                    t = time.time()
                data = self.storage.read(self.piece_size * piece + begin - offset, length + offset, flush_first)
                if DEBUG_READ_PIECE or DEBUG_ENCRYPTED_STORAGE:
                    t = time.time() - t
                    log('>>read:sw:read_raw: index', index, 'piece', piece, 'begin', begin, 'length', length, 'offset', offset, 'data_len1', len(data), 'time_read', t)
                    t = time.time()
                data = self.encryptfunc(index, data, False)
                if DEBUG_READ_PIECE or DEBUG_ENCRYPTED_STORAGE:
                    t = time.time() - t
                    log('>>read:sw:read_raw: after decrypt: index', index, 'piece', piece, 'begin', begin, 'length', length, 'offset', offset, 'data_len1', len(data), 'time_decrypt', t)
                    t = time.time()
                if offset != 0:
                    data.trim(offset)
                    if DEBUG_READ_PIECE or DEBUG_ENCRYPTED_STORAGE:
                        t = time.time() - t
                        log('>>read:sw:read_raw: index', index, 'piece', piece, 'begin', begin, 'length', length, 'offset', offset, 'data_len2', len(data), 'time_trim', t)
            return data
        except IOError as e:
            if DEBUG:
                log(self.log_prefix + ':read_raw: io error: index', index, 'piece', piece, 'begin', begin, 'length', length)
            print_exc()
            self.failed('IO Error')
            return

    def set_file_readonly(self, n):
        try:
            self.storage.set_readonly(n)
        except IOError as e:
            self.failed('IO Error: ' + str(e))
        except OSError as e:
            self.failed('OS Error: ' + str(e))

    def has_data(self, index):
        return index not in self.holes and index not in self.blocked_holes

    def doublecheck_data(self, pieces_to_check):
        if not self.double_check:
            return True
        sources = []
        for p, v in self.places.iteritems():
            if pieces_to_check.has_key(v):
                sources.append(p)

        sources.sort()
        for index in sources:
            if self.have[index]:
                piece = self.read_raw(index, self.places[index], 0, self._piecelen(index), flush_first=True)
                if piece is None:
                    return False
                if sha(piece[:]).digest() != self.hashes[index]:
                    self.failed('download corrupted, piece on disk failed double check; please delete and restart')
                    return False
                piece.release()

        return True

    def reblock(self, new_blocked):
        if DEBUG2:
            log('>>>sw:reblock: new_blocked', new_blocked)
            log('>>>sw:reblock: self.blocked', self.blocked)
        for i in xrange(len(new_blocked)):
            if new_blocked[i] and not self._blocked[i]:
                length = self._piecelen(i)
                self.amount_desired -= length
                if DEBUG2:
                    log('>>>sw:reblock: block: i', i, 'amount_desired', self.amount_desired, 'amount_obtained', self.amount_obtained)
                if self.have[i]:
                    self.amount_obtained -= length
                    continue
                if self.inactive_requests[i] == 1:
                    self.amount_inactive -= length
                    continue
                inactive = 0
                for nb, nl in self.inactive_requests[i]:
                    inactive += nl

                self.amount_inactive -= inactive
                self.amount_obtained -= length - inactive
            if self._blocked[i] and not new_blocked[i]:
                length = self._piecelen(i)
                self.amount_desired += length
                if DEBUG2:
                    log('>>>sw:reblock: unblock: i', i, 'amount_desired', self.amount_desired, 'amount_obtained', self.amount_obtained)
                if self.have[i]:
                    self.amount_obtained += length
                    continue
                if self.inactive_requests[i] == 1:
                    self.amount_inactive += length
                    continue
                inactive = 0
                for nb, nl in self.inactive_requests[i]:
                    inactive += nl

                self.amount_inactive += inactive
                self.amount_obtained += length - inactive

        self._blocked = new_blocked
        self.blocked_movein = Olist()
        self.blocked_moveout = Olist()
        for p, v in self.places.iteritems():
            if p != v:
                if self.blocked[p] and not self.blocked[v]:
                    self.blocked_movein.add(p)
                elif self.blocked[v] and not self.blocked[p]:
                    self.blocked_moveout.add(p)

        self.holes.extend(self.blocked_holes)
        self.holes.sort()
        self.blocked_holes = []

    def pickle(self):
        if self.have.complete():
            if self.merkle_torrent:
                return {'pieces': 1,
                 'merkletree': pickle.dumps(self.merkletree)}
            else:
                return {'pieces': 1}
        pieces = Bitfield(len(self.hashes))
        places = []
        partials = []
        if DEBUG_HASHCHECK:
            log(self.log_prefix + 'pickle: len(self.places):', len(self.places))
            log(self.log_prefix + 'pickle: self.places:', self.places)
        for p in xrange(len(self.hashes)):
            if not self.places.has_key(p):
                continue
            h = self.have[p]
            pieces[p] = h
            pp = []
            if not self.live_streaming and self.dirty.has_key(p):
                for begin, length in self.dirty[p].iteritems():
                    pp.append((begin, length))

            if not h and not pp:
                places.extend([self.places[p], self.places[p]])
            elif self.places[p] != p:
                places.extend([p, self.places[p]])
            if h or not pp:
                continue
            pp.sort()
            r = []
            while len(pp) > 1:
                if pp[0][0] + pp[0][1] == pp[1][0]:
                    pp[0] = list(pp[0])
                    pp[0][1] += pp[1][1]
                    del pp[1]
                else:
                    r.extend(pp[0])
                    del pp[0]

            r.extend(pp[0])
            partials.extend([p, r])

        if DEBUG_HASHCHECK:
            log(self.log_prefix + 'pickle: count_have:', pieces.get_numtrue(), 'count_places:', len(places), 'count_partials:', len(partials))
        if self.merkle_torrent:
            return {'pieces': pieces.tostring(),
             'places': places,
             'partials': partials,
             'merkletree': pickle.dumps(self.merkletree)}
        else:
            return {'pieces': pieces.tostring(),
             'places': places,
             'partials': partials}

    def unpickle(self, data, valid_places):
        if self.live_streaming:
            return []
        got = {}
        places = {}
        dirty = {}
        download_history = {}
        stat_active = {}
        stat_numfound = self.stat_numfound
        amount_obtained = self.amount_obtained
        amount_inactive = self.amount_inactive
        amount_left = self.amount_left
        inactive_requests = [ x for x in self.inactive_requests ]
        restored_partials = []
        try:
            if data.has_key('merkletree'):
                try:
                    if DEBUG_HASHCHECK:
                        log(self.log_prefix + 'unpickle: Unpickling Merkle tree')
                    self.merkletree = pickle.loads(data['merkletree'])
                    self.hashes = self.merkletree.get_piece_hashes()
                    self.hashes_unpickled = True
                except Exception as e:
                    log_exc()

            if data['pieces'] == 1:
                have = Bitfield(len(self.hashes))
                for i in xrange(len(self.hashes)):
                    have[i] = True

                _places = []
                _partials = []
            else:
                have = Bitfield(len(self.hashes), data['pieces'])
                _places = data['places']
                _places = [ _places[x:x + 2] for x in xrange(0, len(_places), 2) ]
                _partials = data['partials']
                _partials = [ _partials[x:x + 2] for x in xrange(0, len(_partials), 2) ]
            for index, place in _places:
                if place not in valid_places:
                    continue
                places[index] = place
                got[index] = 1
                got[place] = 1

            if DEBUG_HASHCHECK:
                log(self.log_prefix + 'unpickle: places:', places)
                log(self.log_prefix + 'unpickle: _partials:', _partials)
                log(self.log_prefix + 'unpickle: got:', got)
                log(self.log_prefix + 'unpickle: have:', have.toboollist())
            for index in xrange(len(self.hashes)):
                if DEBUG_HASHCHECK:
                    log(self.log_prefix + 'unpickle: checking if we have piece', index)
                if have[index]:
                    if not places.has_key(index):
                        if index not in valid_places:
                            have[index] = False
                            continue
                        places[index] = index
                        got[index] = 1
                    length = self._piecelen(index)
                    amount_obtained += length
                    stat_numfound += 1
                    amount_inactive -= length
                    amount_left -= length
                    inactive_requests[index] = None

            for index, plist in _partials:
                if not places.has_key(index):
                    if index not in valid_places:
                        continue
                    places[index] = index
                    got[index] = 1
                plist = [ tuple(plist[x:x + 2]) for x in xrange(0, len(plist), 2) ]
                dirty[index] = {}
                for begin, length in plist:
                    while length > 0:
                        r = min(length, self.request_size)
                        dirty[index][begin] = r
                        begin += self.request_size
                        length -= self.request_size

                stat_active[index] = 1
                download_history[index] = {}
                length = self._piecelen(index)
                l = []
                if plist[0][0] > 0:
                    l.append((0, plist[0][0]))
                for i in xrange(len(plist) - 1):
                    end = plist[i][0] + plist[i][1]
                    l.append((end, plist[i + 1][0] - end))

                end = plist[-1][0] + plist[-1][1]
                if end < length:
                    l.append((end, length - end))
                ll = []
                amount_obtained += length
                amount_inactive -= length
                for nb, nl in l:
                    while nl > 0:
                        r = min(nl, self.request_size)
                        ll.append((nb, r))
                        amount_inactive += r
                        amount_obtained -= r
                        nb += self.request_size
                        nl -= self.request_size

                inactive_requests[index] = ll
                restored_partials.append(index)

        except:
            if DEBUG:
                log_exc()
            return []

        self.have = have
        self.places = places
        self.dirty = dirty
        self.download_history = download_history
        self.stat_active = stat_active
        self.stat_numfound = stat_numfound
        self.amount_obtained = amount_obtained
        self.amount_inactive = amount_inactive
        self.amount_left = amount_left
        self.inactive_requests = inactive_requests
        if DEBUG_HASHCHECK:
            log(self.log_prefix + 'unpickle: self.places', self.places)
            log(self.log_prefix + 'unpickle: restored_partials', restored_partials)
        return restored_partials

    def failed(self, s):
        self.report_failure(s)
        if self.initialize_done is not None:
            self.initialize_done(success=False)

    def live_invalidate(self, piece):
        self.request_lock.acquire()
        try:
            if DEBUG_LIVE:
                log(self.log_prefix + 'live_invalidate: piece', piece)
            length = self._piecelen(piece)
            oldhave = self.have[piece]
            self.have[piece] = False
            self.inactive_requests[piece] = 1
            if self.dirty.has_key(piece):
                del self.dirty[piece]
            self.amount_inactive += length
            if oldhave:
                self.amount_left += length
                self.amount_obtained -= length
            if self.places.has_key(piece):
                p = self.places[piece]
                if DEBUG_LIVE:
                    log(self.log_prefix + 'live_invalidate: clean up place', p)
                del self.places[piece]
                if DEBUG_LIVE:
                    pass
                self.holes.insert(0, p)
        except:
            log_exc()
        finally:
            self.request_lock.release()
