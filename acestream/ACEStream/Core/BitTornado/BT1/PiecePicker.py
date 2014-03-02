#Embedded file name: ACEStream\Core\BitTornado\BT1\PiecePicker.pyo
import sys
import time
from threading import Lock
from random import randrange, shuffle
from traceback import extract_tb, print_stack, print_exc
from ACEStream.Core.BitTornado.clock import clock
from ACEStream.Core.BitTornado.bitfield import Bitfield
from ACEStream.Core.Utilities.logger import log, log_exc
try:
    True
except:
    True = 1
    False = 0

DEBUG = False

class PiecePicker:

    def __init__(self, numpieces, rarest_first_cutoff = 1, rarest_first_priority_cutoff = 3, priority_step = 20, helper = None, coordinator = None, rate_predictor = None):
        self.pplock = Lock()
        self.rarest_first_cutoff = rarest_first_cutoff
        self.priority_step = priority_step
        self.rarest_first_priority_cutoff = rarest_first_priority_cutoff + priority_step
        self.cutoff = rarest_first_priority_cutoff
        self.numpieces = numpieces
        self.started = []
        self.num_skip_started_pieces = 0
        self.totalcount = 0
        self.numhaves = [0] * numpieces
        self.priority = [1] * numpieces
        self.removed_partials = {}
        self.crosscount = [numpieces]
        self.crosscount2 = [numpieces]
        self.has = [0] * numpieces
        self.numgot = 0
        self.done = False
        self.peer_connections = {}
        self.seed_connections = {}
        self.seed_time = None
        self.superseed = False
        self.seeds_connected = 0
        self.helper = helper
        self.coordinator = coordinator
        self.rate_predictor = rate_predictor
        self.videostatus = None

    def _init_interests(self):
        self.interests = [ [] for x in xrange(self.priority_step) ]
        self.level_in_interests = [self.priority_step] * self.numpieces
        interests = range(self.numpieces)
        shuffle(interests)
        self.pos_in_interests = [0] * self.numpieces
        for i in xrange(self.numpieces):
            self.pos_in_interests[interests[i]] = i

        self.interests.append(interests)
        if DEBUG:
            log('pp::_init_interests: interests', self.interests)

    def got_piece(self, piece, begin, length):
        pass

    def check_outstanding_requests(self, downloads):
        pass

    def got_have(self, piece, connection = None):
        if DEBUG:
            log('pp::got_have: piece', piece)
        self.pplock.acquire()
        try:
            self.totalcount += 1
            numint = self.numhaves[piece]
            self.numhaves[piece] += 1
            self.crosscount[numint] -= 1
            if numint + 1 == len(self.crosscount):
                self.crosscount.append(0)
            self.crosscount[numint + 1] += 1
            if not self.done:
                numintplus = numint + self.has[piece]
                self.crosscount2[numintplus] -= 1
                if numintplus + 1 == len(self.crosscount2):
                    self.crosscount2.append(0)
                self.crosscount2[numintplus + 1] += 1
                numint = self.level_in_interests[piece]
                self.level_in_interests[piece] += 1
            if self.superseed:
                self.seed_got_haves[piece] += 1
                numint = self.level_in_interests[piece]
                self.level_in_interests[piece] += 1
            else:
                if self.has[piece]:
                    return True
                if self.priority[piece] == -1:
                    return False
            if numint == len(self.interests) - 1:
                self.interests.append([])
            self._shift_over(piece, self.interests[numint], self.interests[numint + 1])
            return False
        finally:
            self.pplock.release()

    def redirect_haves_to_coordinator(self, connection = None, helper_con = False, piece = None):
        if self.helper:
            if DEBUG:
                print >> sys.stderr, 'PiecePicker: proxy_got_have: sending haves to coordinator'
            piece_list = self.numhaves
            print 'sending piece_list=', piece_list
            self.helper.send_proxy_have(piece_list)
        else:
            return

    def lost_have(self, piece):
        if DEBUG:
            log('pp::lost_have: piece', piece)
        self.pplock.acquire()
        try:
            self.totalcount -= 1
            if self.totalcount < 0:
                self.totalcount = 0
            numint = self.numhaves[piece]
            if numint <= 0:
                return
            self.numhaves[piece] -= 1
            self.crosscount[numint] -= 1
            self.crosscount[numint - 1] += 1
            if not self.done:
                numintplus = numint + self.has[piece]
                self.crosscount2[numintplus] -= 1
                if numintplus > 0:
                    self.crosscount2[numintplus - 1] += 1
                numint = self.level_in_interests[piece]
                self.level_in_interests[piece] -= 1
            if self.superseed:
                numint = self.level_in_interests[piece]
                self.level_in_interests[piece] -= 1
            elif self.has[piece] or self.priority[piece] == -1:
                return
            self._shift_over(piece, self.interests[numint], self.interests[numint - 1])
        finally:
            self.pplock.release()

    def is_valid_piece(self, piece):
        return True

    def get_valid_range_iterator(self, skip_filter = False):
        return xrange(0, len(self.has))

    def invalidate_piece(self, piece):
        if DEBUG:
            log('pp::invalidate_piece: piece', piece)
        self.pplock.acquire()
        try:
            if not self.has[piece]:
                return
            self.has[piece] = 0
            self.numgot -= 1
            p = self.priority[piece]
            level = self.numhaves[piece] + self.priority_step * p
            self.level_in_interests[piece] = level
            while len(self.interests) < level + 1:
                self.interests.append([])

            l2 = self.interests[level]
            parray = self.pos_in_interests
            newp = randrange(len(l2) + 1)
            if newp == len(l2):
                parray[piece] = len(l2)
                l2.append(piece)
            else:
                old = l2[newp]
                parray[old] = len(l2)
                l2.append(old)
                l2[newp] = piece
                parray[piece] = newp
        finally:
            self.pplock.release()

    def _invalidate_piece_old(self, piece):
        self.pplock.acquire()
        try:
            if self.has[piece]:
                self.has[piece] = 0
                self.numgot -= 1
                p = self.priority[piece]
                level = self.numhaves[piece] + self.priority_step * p
                self.level_in_interests[piece] = level
                while len(self.interests) < level + 1:
                    self.interests.append([])

                l2 = self.interests[level]
                parray = self.pos_in_interests
                newp = randrange(len(l2) + 1)
                if newp == len(l2):
                    parray[piece] = len(l2)
                    l2.append(piece)
                else:
                    old = l2[newp]
                    parray[old] = len(l2)
                    l2.append(old)
                    l2[newp] = piece
                    parray[piece] = newp
            self.totalcount -= 1
            if self.totalcount < 0:
                self.totalcount = 0
            numint = self.numhaves[piece]
            if numint <= 0:
                return
            self.numhaves[piece] -= 1
            self.crosscount[numint] -= 1
            self.crosscount[numint - 1] += 1
            numintplus = numint
            self.crosscount2[numintplus] -= 1
            if numintplus > 0:
                self.crosscount2[numintplus - 1] += 1
            numint = self.level_in_interests[piece]
            self.level_in_interests[piece] -= 1
            self._shift_over(piece, self.interests[numint], self.interests[numint - 1])
        finally:
            self.pplock.release()

    def set_downloader(self, dl):
        self.downloader = dl

    def _shift_over(self, piece, l1, l2):
        try:
            parray = self.pos_in_interests
            p = parray[piece]
            q = l1[-1]
            l1[p] = q
            parray[q] = p
            del l1[-1]
            newp = randrange(len(l2) + 1)
            if newp == len(l2):
                parray[piece] = len(l2)
                l2.append(piece)
            else:
                old = l2[newp]
                parray[old] = len(l2)
                l2.append(old)
                l2[newp] = piece
                parray[piece] = newp
        except:
            if DEBUG:
                print_exc()

    def got_seed(self):
        self.seeds_connected += 1
        self.cutoff = max(self.rarest_first_priority_cutoff - self.seeds_connected, 0)

    def became_seed(self):
        self.pplock.acquire()
        try:
            self.got_seed()
            self.totalcount -= self.numpieces
            self.numhaves = [ i - 1 for i in self.numhaves ]
            if self.superseed or not self.done:
                self.level_in_interests = [ i - 1 for i in self.level_in_interests ]
                del self.interests[0]
            del self.crosscount[0]
            if not self.done:
                del self.crosscount2[0]
        except:
            if DEBUG:
                print_exc()
        finally:
            self.pplock.release()

    def lost_seed(self):
        self.seeds_connected -= 1
        self.cutoff = max(self.rarest_first_priority_cutoff - self.seeds_connected, 0)

    def requested(self, piece, begin = None, length = None):
        if DEBUG:
            log('pp::requested: piece', piece, 'begin', begin, 'length', length)
        if piece not in self.started:
            self.started.append(piece)

    def _remove_from_interests(self, piece, keep_partial = False):
        l = self.interests[self.level_in_interests[piece]]
        p = self.pos_in_interests[piece]
        q = l[-1]
        l[p] = q
        self.pos_in_interests[q] = p
        del l[-1]
        if DEBUG:
            log('pp::_remove_from_interests: piece', piece, 'keep_partial', keep_partial)
        try:
            self.started.remove(piece)
            if keep_partial:
                self.removed_partials[piece] = 1
        except ValueError:
            pass

    def complete(self, piece):
        if DEBUG:
            log('pp::complete: piece', piece)
        self.pplock.acquire()
        try:
            if self.has[piece]:
                return False
            self.has[piece] = 1
            self.numgot += 1
            if DEBUG:
                print >> sys.stderr, 'PiecePicker::complete: piece:', piece, 'self.numgot:', self.numgot, 'self.numpieces', self.numpieces
            if self.numgot == self.numpieces:
                if DEBUG:
                    print >> sys.stderr, 'PiecePicker::complete: self.done=True'
                self.done = True
                self.crosscount2 = self.crosscount
            else:
                numhaves = self.numhaves[piece]
                self.crosscount2[numhaves] -= 1
                if numhaves + 1 == len(self.crosscount2):
                    self.crosscount2.append(0)
                self.crosscount2[numhaves + 1] += 1
            self._remove_from_interests(piece)
            return True
        finally:
            self.pplock.release()

    def _proxynext(self, haves, wantfunc, complete_first, helper_con, willrequest = True, connection = None, proxyhave = None, lookatstarted = False, onlystarted = False):
        cutoff = self.numgot < self.rarest_first_cutoff
        complete_first = (complete_first or cutoff) and not haves.complete()
        best = None
        bestnum = 1073741824
        if lookatstarted:
            for i in self.started:
                if proxyhave == None:
                    proxyhave_i = False
                else:
                    proxyhave_i = proxyhave[i]
                if (haves[i] or proxyhave_i) and wantfunc(i) and (self.helper is None or helper_con or not self.helper.is_ignored(i)):
                    if self.level_in_interests[i] < bestnum:
                        best = i
                        bestnum = self.level_in_interests[i]

        if best is not None:
            if complete_first or cutoff and len(self.interests) > self.cutoff:
                return best
        if onlystarted:
            return best
        if haves.complete():
            r = [(0, min(bestnum, len(self.interests)))]
        elif cutoff and len(self.interests) > self.cutoff:
            r = [(self.cutoff, min(bestnum, len(self.interests))), (0, self.cutoff)]
        else:
            r = [(0, min(bestnum, len(self.interests)))]
        for lo, hi in r:
            for i in xrange(lo, hi):
                random_interests = []
                random_interests.extend(self.interests[i])
                shuffle(random_interests)
                for j in random_interests:
                    if proxyhave == None:
                        proxyhave_j = False
                    else:
                        proxyhave_j = proxyhave[j]
                    if (haves[j] or proxyhave_j) and wantfunc(j) and (self.helper is None or helper_con or not self.helper.is_ignored(j)):
                        return j

        if best is not None:
            return best

    def _next(self, haves, wantfunc, complete_first, helper_con, willrequest = True, connection = None, shuffle = True):
        cutoff = self.numgot < self.rarest_first_cutoff
        complete_first = (complete_first or cutoff) and not haves.complete()
        best = None
        bestnum = 1073741824
        for i in self.started:
            if haves[i] and wantfunc(i) and (self.helper is None or helper_con or not self.helper.is_ignored(i)):
                if self.level_in_interests[i] < bestnum:
                    best = i
                    bestnum = self.level_in_interests[i]

        if best is not None:
            if complete_first or cutoff and len(self.interests) > self.cutoff:
                return best
        if DEBUG:
            log('pp:_next: haves.complete()', haves.complete())
        if haves.complete():
            r = [(0, min(bestnum, len(self.interests)))]
        elif cutoff and len(self.interests) > self.cutoff:
            r = [(self.cutoff, min(bestnum, len(self.interests))), (0, self.cutoff)]
        else:
            r = [(0, min(bestnum, len(self.interests)))]
        if DEBUG:
            log('pp:_next: r', r, 'interests', self.interests)
        for lo, hi in r:
            for i in xrange(lo, hi):
                for j in self.interests[i]:
                    if haves[j] and wantfunc(j) and (self.helper is None or helper_con or not self.helper.is_ignored(j)):
                        return j

        if best is not None:
            return best

    def next(self, haves, wantfunc, sdownload, complete_first = False, helper_con = False, slowpieces = [], willrequest = True, connection = None, proxyhave = None, shuffle = True):
        while True:
            if helper_con:
                piece = self._proxynext(haves, wantfunc, complete_first, helper_con, willrequest=willrequest, connection=connection, proxyhave=None, lookatstarted=False)
                if piece is None:
                    piece = self._proxynext(haves, wantfunc, complete_first, helper_con, willrequest=willrequest, connection=connection, proxyhave=proxyhave, lookatstarted=False)
                    if piece is None:
                        if DEBUG:
                            print >> sys.stderr, 'PiecePicker: next: _next returned no pieces for proxyhave!',
                        break
                if DEBUG:
                    print >> sys.stderr, 'PiecePicker: next: helper None or helper conn, returning', piece
                    print >> sys.stderr, 'PiecePicker: next: haves[', piece, ']=', haves[piece]
                    print >> sys.stderr, 'PiecePicker: next: proxyhave[', piece, ']=', proxyhave[piece]
                if not haves[piece]:
                    self.coordinator.send_request_pieces(piece, connection.get_id())
                    return
                else:
                    return piece
            if self.helper is not None:
                piece = self._proxynext(haves, wantfunc, complete_first, helper_con, willrequest=willrequest, connection=connection, proxyhave=None, lookatstarted=True, onlystarted=True)
                if piece is not None:
                    if DEBUG:
                        print >> sys.stderr, 'PiecePicker: next: helper: continuing already started download for', requested_piece
                    return piece
                else:
                    requested_piece = self.helper.next_request()
                    if requested_piece is not None:
                        if DEBUG:
                            print >> sys.stderr, 'PiecePicker: next: helper: got request from coordinator for', requested_piece
                        return requested_piece
                    if DEBUG:
                        print >> sys.stderr, 'PiecePicker: next: helper: no piece pending'
                    return
            piece = self._next(haves, wantfunc, complete_first, helper_con, willrequest=willrequest, connection=connection, shuffle=shuffle)
            if piece is None:
                if DEBUG:
                    print >> sys.stderr, 'PiecePicker: next: _next returned no pieces!',
                break
            if DEBUG:
                print >> sys.stderr, 'PiecePicker: next: helper: an error occurred. Returning piece', piece
            return piece

        if self.rate_predictor and self.rate_predictor.has_capacity():
            return self._next(haves, wantfunc, complete_first, True, willrequest=willrequest, connection=connection)
        else:
            return

    def set_rate_predictor(self, rate_predictor):
        self.rate_predictor = rate_predictor

    def am_I_complete(self):
        return self.done

    def bump(self, piece):
        if DEBUG:
            log('pp::bump: piece', piece)
        self.pplock.acquire()
        try:
            l = self.interests[self.level_in_interests[piece]]
            pos = self.pos_in_interests[piece]
            del l[pos]
            l.append(piece)
            for i in range(pos, len(l)):
                self.pos_in_interests[l[i]] = i

            try:
                self.started.remove(piece)
            except:
                pass

        finally:
            self.pplock.release()

    def set_priority(self, piece, p):
        if DEBUG:
            log('pp::set_priority: piece', piece, 'p', p)
        self.pplock.acquire()
        try:
            if self.superseed:
                return False
            oldp = self.priority[piece]
            if oldp == p:
                return False
            self.priority[piece] = p
            if p == -1:
                if not self.has[piece]:
                    self._remove_from_interests(piece, True)
                return True
            if oldp == -1:
                level = self.numhaves[piece] + self.priority_step * p
                self.level_in_interests[piece] = level
                if self.has[piece]:
                    return True
                while len(self.interests) < level + 1:
                    self.interests.append([])

                l2 = self.interests[level]
                parray = self.pos_in_interests
                newp = randrange(len(l2) + 1)
                if newp == len(l2):
                    parray[piece] = len(l2)
                    l2.append(piece)
                else:
                    old = l2[newp]
                    parray[old] = len(l2)
                    l2.append(old)
                    l2[newp] = piece
                    parray[piece] = newp
                if self.removed_partials.has_key(piece):
                    del self.removed_partials[piece]
                    self.started.append(piece)
                return True
            numint = self.level_in_interests[piece]
            newint = numint + (p - oldp) * self.priority_step
            self.level_in_interests[piece] = newint
            if self.has[piece]:
                return False
            while len(self.interests) < newint + 1:
                self.interests.append([])

            self._shift_over(piece, self.interests[numint], self.interests[newint])
            return False
        finally:
            self.pplock.release()

    def is_blocked(self, piece):
        return self.priority[piece] < 0

    def set_superseed(self):
        self.superseed = True
        self.seed_got_haves = [0] * self.numpieces
        self._init_interests()

    def next_have(self, connection, looser_upload):
        if DEBUG:
            log('pp::next_have: ---')
        if self.seed_time is None:
            self.seed_time = clock()
            return
        if clock() < self.seed_time + 10:
            return
        if not connection.upload.super_seeding:
            return
        if connection in self.seed_connections:
            if looser_upload:
                num = 1
            else:
                num = 2
            if self.seed_got_haves[self.seed_connections[connection]] < num:
                return
            if not connection.upload.was_ever_interested:
                connection.upload.skipped_count += 1
                if connection.upload.skipped_count >= 3:
                    return -1
        for tier in self.interests:
            for piece in tier:
                if not connection.download.have[piece]:
                    seedint = self.level_in_interests[piece]
                    self.level_in_interests[piece] += 1
                    if seedint == len(self.interests) - 1:
                        self.interests.append([])
                    self._shift_over(piece, self.interests[seedint], self.interests[seedint + 1])
                    self.seed_got_haves[piece] = 0
                    self.seed_connections[connection] = piece
                    connection.upload.seed_have_list.append(piece)
                    return piece

        return -1

    def got_peer(self, connection):
        if DEBUG:
            log('pp::got_peer: ip', connection.get_ip())
        self.peer_connections[connection] = {'connection': connection}

    def lost_peer(self, connection):
        if DEBUG:
            log('pp::lost_peer: ip', connection.get_ip())
        if connection.download.have.complete():
            self.lost_seed()
        else:
            has = connection.download.have
            for i in xrange(0, self.numpieces):
                if has[i]:
                    self.lost_have(i)

        if connection in self.seed_connections:
            del self.seed_connections[connection]
        del self.peer_connections[connection]

    def fast_initialize(self, completeondisk):
        if completeondisk:
            self.has = [1] * self.numpieces
            self.numgot = self.numpieces
            self.done = True
            self.interests = [ [] for x in xrange(self.priority_step) ]
            self.interests.append([])
            self.level_in_interests = [self.priority_step] * self.numpieces
            self.pos_in_interests = [0] * self.numpieces
        else:
            self._init_interests()

    def print_complete(self):
        print >> sys.stderr, 'pp: self.numpieces', `(self.numpieces)`
        print >> sys.stderr, 'pp: self.started', `(self.started)`
        print >> sys.stderr, 'pp: self.totalcount', `(self.totalcount)`
        print >> sys.stderr, 'pp: self.numhaves', `(self.numhaves)`
        print >> sys.stderr, 'pp: self.priority', `(self.priority)`
        print >> sys.stderr, 'pp: self.removed_partials', `(self.removed_partials)`
        print >> sys.stderr, 'pp: self.crosscount', `(self.crosscount)`
        print >> sys.stderr, 'pp: self.crosscount2', `(self.crosscount2)`
        print >> sys.stderr, 'pp: self.has', `(self.has)`
        print >> sys.stderr, 'pp: self.numgot', `(self.numgot)`
        print >> sys.stderr, 'pp: self.done', `(self.done)`
        print >> sys.stderr, 'pp: self.peer_connections', `(self.peer_connections)`
        print >> sys.stderr, 'pp: self.seed_connections', `(self.seed_connections)`
        print >> sys.stderr, 'pp: self.seed_time', `(self.seed_time)`
        print >> sys.stderr, 'pp: self.superseed', `(self.superseed)`
        print >> sys.stderr, 'pp: self.seeds_connected', `(self.seeds_connected)`
        print >> sys.stderr, 'pp: self.interests', `(self.interests)`
        print >> sys.stderr, 'pp: self.level_in_interests', `(self.level_in_interests)`
        print >> sys.stderr, 'pp: self.pos_in_interests', `(self.pos_in_interests)`
