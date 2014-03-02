#Embedded file name: ACEStream\Core\Video\PiecePickerStreaming.pyo
import sys
import time
import random
from traceback import print_stack
from ACEStream.Core.BitTornado.BT1.PiecePicker import PiecePicker
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.Utilities.odict import odict
from ACEStream.GlobalConfig import globalConfig
TEST_VOD_OVERRIDE = False
DEBUG = False
DEBUG_CHUNKS = False
DEBUGPP = False
DEBUG_LIVE = False
PERCENT_SWITCH_NEXT_FILE = 0.2

def rarest_first(has_dict, rarity_list, filter = lambda x: True, pick_first = False):
    choice = None
    rarity = None
    n = 0
    for k in (x for x in has_dict if filter(x)):
        r = rarity_list[k]
        if DEBUGPP:
            print >> sys.stderr, 'pps::rarest_first: k', k, 'r', r, 'rarity', rarity, 'n', n, 'choice', choice, 'pick_first', pick_first, 'has_dict', has_dict
        if pick_first:
            choice = k
            break
        if rarity is None or r < rarity:
            rarity = r
            n = 1
            choice = k
        elif r == rarity:
            n += 1
            if random.uniform(0, n) == 0:
                choice = k

    return choice


class PiecePickerStreaming(PiecePicker):
    MU = 4

    def __init__(self, numpieces, rarest_first_cutoff = 1, rarest_first_priority_cutoff = 3, priority_step = 20, helper = None, coordinator = None, rate_predictor = None, piecesize = 0):
        PiecePicker.__init__(self, numpieces, rarest_first_cutoff, rarest_first_priority_cutoff, priority_step, helper, coordinator, rate_predictor)
        self.maxhave = 0
        self.stats = {}
        self.stats['high'] = 0
        self.stats['mid'] = 0
        self.stats['low'] = 0
        self.transporter = None
        self.outstanding_requests = {}
        self.playing_delay = (5, 20, -0.5)
        buffering_delay = globalConfig.get_value('piece_picker_buffering_delay', None)
        if buffering_delay is not None:
            self.buffering_delay = buffering_delay
        else:
            self.buffering_delay = (7.5, 30, 10)
        self.is_interesting = self.is_interesting_normal
        self.extra_videostatus = []

    def set_transporter(self, transporter):
        self.transporter = transporter

    def set_videostatus(self, videostatus):
        videostatus.min_download_percent = PERCENT_SWITCH_NEXT_FILE
        self.update_videostatus(videostatus)
        self.videostatus = videostatus
        if self.videostatus.live_streaming:
            self.is_interesting = self.is_interesting_live
        else:
            self.is_interesting = self.is_interesting_vod
        self.videostatus.add_playback_pos_observer(self.change_playback_pos)

    def set_extra_videostatus(self, extra_videostatus):
        for videostatus in extra_videostatus:
            if DEBUG:
                print >> sys.stderr, 'PiecePickerStreaming::add_extra_videostatus:', videostatus.videoinfo['index']
            videostatus.min_download_percent = PERCENT_SWITCH_NEXT_FILE
            self.update_videostatus(videostatus)

        self.extra_videostatus = extra_videostatus

    def update_videostatus(self, videostatus):
        first, last = videostatus.download_range()
        for index in videostatus.generate_range((first, last)):
            if self.has[index]:
                videostatus.got_piece(index)

    def is_interesting_live(self, piece):
        return self.videostatus.in_download_range(piece) and not self.has[piece]

    def is_interesting_vod(self, piece):
        if self.has[piece]:
            return False
        if self.videostatus.first_piece <= piece <= self.videostatus.last_piece:
            return True
        for vs in self.extra_videostatus:
            if vs.in_download_range(piece):
                return True

        return False

    def is_interesting_normal(self, piece):
        return not self.has[piece]

    def change_playback_pos(self, oldpos, newpos):
        if oldpos is None:
            valid = self.is_interesting
            for d in self.peer_connections.values():
                interesting = odict()
                has = d['connection'].download.have
                for i in self.get_valid_range_iterator():
                    if has[i] and valid(i):
                        if DEBUGPP:
                            print >> sys.stderr, 'pps::change_playback_pos: add interesting: i', i
                        interesting[i] = 1

                if DEBUGPP:
                    print >> sys.stderr, 'pps::change_playback_pos: oldpos', oldpos, 'newpos', newpos, 'interesting', interesting
                d['interesting'] = interesting

        else:
            for d in self.peer_connections.values():
                if DEBUGPP:
                    print >> sys.stderr, 'pps::change_playback_pos: pop oldpos', oldpos
                d['interesting'].pop(oldpos, 0)

    def got_have(self, piece, connection = None):
        if DEBUG:
            print >> sys.stderr, 'pps::got_have: piece', piece
        self.maxhave = max(self.maxhave, piece)
        PiecePicker.got_have(self, piece, connection)
        if self.is_interesting(piece):
            self.peer_connections[connection]['interesting'][piece] = 1

    def got_seed(self):
        self.maxhave = self.numpieces
        PiecePicker.got_seed(self)

    def lost_have(self, piece):
        PiecePicker.lost_have(self, piece)

    def got_peer(self, connection):
        PiecePicker.got_peer(self, connection)
        self.peer_connections[connection]['interesting'] = odict()

    def lost_peer(self, connection):
        PiecePicker.lost_peer(self, connection)

    def got_piece(self, *request):
        if request in self.outstanding_requests:
            del self.outstanding_requests[request]
        if self.transporter:
            self.transporter.got_piece(*request)

    def complete(self, piece):
        if DEBUG:
            log('PiecePickerStreaming: complete:', piece)
        if not PiecePicker.complete(self, piece):
            return False
        if self.transporter:
            self.transporter.complete(piece)
        for request in self.outstanding_requests.keys():
            if request[0] == piece:
                del self.outstanding_requests[request]

        for d in self.peer_connections.itervalues():
            d['interesting'].pop(piece, 0)

        check_interests = False
        for vs in self.extra_videostatus:
            start_new_file = vs.got_piece(piece)
            if start_new_file and not check_interests:
                self.downloader.check_interests()
                check_interests = True

        return True

    def num_nonempty_neighbours(self):
        return len([ c for c in self.peer_connections if c.download.have.numfalse < c.download.have.length ])

    def pos_is_sustainable(self, fudge = 2):
        vs = self.videostatus
        if not vs.live_streaming:
            if DEBUG:
                print >> sys.stderr, 'PiecePickerStreaming: pos is sustainable: not streaming live'
            return True
        numconn = self.num_nonempty_neighbours()
        if not numconn:
            if DEBUG:
                print >> sys.stderr, 'PiecePickerStreaming: pos is sustainable: no neighbours with pieces'
            return True
        half = max(1, numconn / 2)
        skip = fudge
        for x in vs.generate_range(vs.download_range()):
            if skip > 0:
                skip -= 1
            elif self.numhaves[x] >= half:
                if DEBUG:
                    print >> sys.stderr, 'PiecePickerStreaming: pos is sustainable: piece %s @ %s>%s peers (fudge=%s)' % (x,
                     self.numhaves[x],
                     half,
                     fudge)
                return True

        if DEBUG:
            print >> sys.stderr, 'PiecePickerStreaming: pos is NOT sustainable playpos=%s fudge=%s numconn=%s half=%s numpeers=%s %s' % (vs.playback_pos,
             fudge,
             numconn,
             half,
             len(self.peer_connections),
             [ x.get_ip() for x in self.peer_connections ])
        return False

    def next(self, haves, wantfunc, sdownload, complete_first = False, helper_con = False, slowpieces = [], willrequest = True, connection = None, proxyhave = None, shuffle = True):

        def newwantfunc(piece):
            return piece not in slowpieces and wantfunc(piece)

        p = PiecePicker.next(self, haves, newwantfunc, sdownload, complete_first, helper_con, slowpieces=slowpieces, willrequest=willrequest, connection=connection, shuffle=shuffle)
        if DEBUGPP and self.videostatus.prebuffering:
            print >> sys.stderr, 'PiecePickerStreaming: original PP.next returns', p
        if p is None and not self.videostatus.live_streaming and self.am_I_complete() or TEST_VOD_OVERRIDE:
            if self.transporter is not None:
                self.transporter.notify_playable()
        return p

    def _next(self, haves, wantfunc, complete_first, helper_con, willrequest = True, connection = None, shuffle = True):
        if self.num_skip_started_pieces > 0:
            if DEBUG:
                log('num_skip_started_pieces', self.num_skip_started_pieces)
            self.num_skip_started_pieces -= 1
        else:
            cutoff = self.numgot < self.rarest_first_cutoff
            complete_first = complete_first or cutoff
            best = None
            bestnum = 1073741824
            for i in self.started:
                if haves[i] and wantfunc(i) and (self.helper is None or helper_con or not self.helper.is_ignored(i)):
                    if self.level_in_interests[i] < bestnum:
                        best = i
                        bestnum = self.level_in_interests[i]

            if best is not None:
                if best >= self.videostatus.playback_pos and (complete_first or cutoff and len(self.interests) > self.cutoff):
                    if self.videostatus.in_high_range(best):
                        if DEBUG:
                            log('pps::_next: return already started piece: index', best, 'started', self.started)
                        return best
                    if DEBUG:
                        log('pps::_next: already started piece not in high range: index', best, 'started', self.started)
        p = self.next_new(self.videostatus, haves, wantfunc, complete_first, helper_con, willrequest=willrequest, connection=connection, shuffle=shuffle)
        if DEBUG or DEBUG_LIVE:
            log('PiecePickerStreaming: next_new returns', p, 'num_skip_started_pieces', self.num_skip_started_pieces)
        if p is None:
            if self.videostatus.completed >= PERCENT_SWITCH_NEXT_FILE:
                if DEBUG:
                    print >> sys.stderr, 'PiecePickerStreaming::_next: p is none, ask for extra_videostatus'
                for vs in self.extra_videostatus:
                    if vs.completed >= 1.0:
                        if DEBUG:
                            print >> sys.stderr, 'PiecePickerStreaming::_next: extra_videostatus: vs.prebuffering', vs.prebuffering, 'vs.selected_movie', vs.selected_movie, 'this part is completed, try next'
                        continue
                    if DEBUG:
                        print >> sys.stderr, 'PiecePickerStreaming::_next: extra_videostatus: completed', vs.completed, 'vs.prebuffering', vs.prebuffering, 'vs.selected_movie', vs.selected_movie
                    p = self.next_new(vs, haves, wantfunc, complete_first, helper_con, willrequest=willrequest, connection=connection)
                    if p is not None:
                        break
                    if vs.completed < PERCENT_SWITCH_NEXT_FILE:
                        break

            elif DEBUG:
                print >> sys.stderr, 'PiecePickerStreaming::_next: p is none, but current part is not completed enough'
        if DEBUG:
            print >> sys.stderr, 'PiecePickerStreaming: next_new returns', p
        return p

    def check_outstanding_requests(self, downloads):
        if not self.transporter:
            return
        now = time.time()
        cancel_requests = []
        in_high_range = self.videostatus.in_high_range
        playing_mode = self.videostatus.playing and not self.videostatus.paused
        piece_due = self.transporter.piece_due
        if playing_mode:
            min_delay, max_delay, offset_delay = self.playing_delay
        else:
            min_delay, max_delay, offset_delay = self.buffering_delay
        if DEBUG:
            log('pps::check_outstanding_requests: num_downloads', len(downloads), 'num_outstanding_requests', len(self.outstanding_requests))
        for download in downloads:
            total_length = 0
            download_rate = download.get_short_term_rate()
            for piece_id, begin, length in download.active_requests:
                try:
                    time_request = self.outstanding_requests[piece_id, begin, length]
                except KeyError:
                    if DEBUG:
                        log('pps::check_outstanding_requests: not outstanding request: piece', piece_id, 'begin', begin, 'length', length)
                    continue

                total_length += length
                if now < time_request + min_delay:
                    if DEBUG:
                        log('pps::check_outstanding_requests: have time to complete: piece', piece_id, 'begin', begin, 'length', length, 'delay', now - time_request, 'min_delay', min_delay, 'now', now, 'time_request', time_request)
                    continue
                if in_high_range(piece_id) or self.videostatus.prebuffering and piece_id in self.videostatus.prebuf_needed_pieces:
                    if download_rate == 0:
                        if DEBUG:
                            log('pps::check_outstanding_requests:cancel: download not started yet for piece', piece_id, 'chunk', begin, 'on', download.ip)
                        cancel_requests.append((piece_id, begin, length))
                    else:
                        if playing_mode:
                            time_until_deadline = min(piece_due(piece_id), time_request + max_delay - now)
                        else:
                            time_until_deadline = time_request + max_delay - now
                        time_until_download = total_length / download_rate
                        if time_until_deadline < time_until_download - offset_delay:
                            if DEBUG:
                                log('pps::check_outstanding_requests:cancel: download speed too slow for piece', piece_id, 'chunk', begin, 'on', download.ip, 'Deadline in', time_until_deadline, 'while estimated download in', time_until_download)
                            cancel_requests.append((piece_id, begin, length))
                        elif DEBUG:
                            log('pps::check_outstanding_requests: no deadline: piece', piece_id, 'begin', begin, 'length', length, 'time_until_deadline', time_until_deadline, 'time_until_download', time_until_download, 'offset_delay', offset_delay)
                elif DEBUG:
                    log('pps::check_outstanding_requests: not in high range: piece', piece_id, 'begin', begin, 'length', length)

        if cancel_requests:
            if DEBUG:
                log('pps::check_outstanding_requests: cancel_requests', cancel_requests)
            try:
                self.downloader.cancel_requests(cancel_requests, allowrerequest=False)
            except:
                log_exc()

    def requested(self, *request):
        self.outstanding_requests[request] = time.time()
        return PiecePicker.requested(self, *request)

    def next_new(self, videostatus, haves, wantfunc, complete_first, helper_con, willrequest = True, connection = None, shuffle = True):
        vs = videostatus
        if DEBUGPP:
            x = []
            y = haves.toboollist()
            for i in xrange(len(y)):
                if y[i]:
                    x.append(i)

            if connection is None:
                ip = None
            else:
                ip = connection.get_ip()
            log('pps::next_new: ip', ip, 'shuffle', shuffle, 'haves', x)
        if vs.live_streaming:
            if vs.live_startpos is None:
                if DEBUG_LIVE:
                    log('pps::next_new: live not hooked in')
                return
            if connection:
                if DEBUGPP:
                    print >> sys.stderr, 'pps::next_new: got connection, return rarest first: vs.live_startpos', vs.live_startpos, 'ip', connection.get_ip(), 'interesting', self.peer_connections[connection]['interesting'], 'numhaves', self.numhaves
                p = rarest_first(self.peer_connections[connection]['interesting'], self.numhaves, wantfunc, pick_first=True)
                if DEBUGPP:
                    print >> sys.stderr, 'pps::next_new: piece', p
                return p

        def pick_first(f, t):
            for i in vs.generate_range((f, t)):
                if not haves[i] or self.has[i]:
                    if DEBUGPP:
                        print >> sys.stderr, 'PiecePickerStreaming::pick_first: not haves[i] or self.has[i] i:', i
                    continue
                if not wantfunc(i):
                    if DEBUGPP:
                        print >> sys.stderr, 'PiecePickerStreaming::pick_first: not wantfunc(i) i:', i
                    continue
                if self.helper is None or helper_con or not self.helper.is_ignored(i):
                    return i

        def pick_rarest_loop_over_small_range(range, shuffle = True):
            if shuffle:
                random.shuffle(range)
            for i in range:
                if not haves[i] or self.has[i]:
                    if DEBUGPP:
                        print >> sys.stderr, 'PiecePickerStreaming::pick_rarest_loop_over_small_range: not haves[i] or self.has[i]: i', i, 'shuffle', shuffle
                    continue
                if not wantfunc(i):
                    if DEBUGPP:
                        print >> sys.stderr, 'PiecePickerStreaming::pick_rarest_loop_over_small_range: not wantfunc(i): i', i, 'shuffle', shuffle
                    continue
                if self.helper is None or helper_con or not self.helper.is_ignored(i):
                    return i

        def pick_rarest_small_range(f, t, range = None, shuffle = True):
            d = vs.dist_range(f, t)
            if DEBUGPP:
                print >> sys.stderr, 'PiecePickerStreaming::pick_rarest_small_range: f:', f, 't:', t, 'd:', d, 'shuffle:', shuffle
            for level in xrange(len(self.interests)):
                piecelist = self.interests[level]
                if DEBUGPP:
                    print >> sys.stderr, 'PiecePickerStreaming::pick_rarest_small_range: level:', level, 'len(piecelist):', len(piecelist)
                if len(piecelist) > d:
                    if range is None:
                        xr = vs.generate_range((f, t))
                        range = []
                        range.extend(xr)
                    return pick_rarest_loop_over_small_range(range, shuffle)
                for i in piecelist:
                    if not vs.in_range(f, t, i):
                        if DEBUGPP:
                            print >> sys.stderr, 'PiecePickerStreaming::pick_rarest_small_range: not vs.in_range( f, t, i ) f:', f, 't:', t, 'i:', i
                        continue
                    if not haves[i] or self.has[i]:
                        if DEBUGPP:
                            print >> sys.stderr, 'PiecePickerStreaming::pick_rarest_small_range: not haves[i] or self.has[i] i:', i
                        continue
                    if not wantfunc(i):
                        if DEBUGPP:
                            print >> sys.stderr, 'PiecePickerStreaming::pick_rarest_small_range: not wantfunc(i) i:', i
                        continue
                    if self.helper is None or helper_con or not self.helper.is_ignored(i):
                        return i

        def pick_rarest(f, t):
            for piecelist in self.interests:
                for i in piecelist:
                    if not vs.in_range(f, t, i):
                        if DEBUGPP:
                            print >> sys.stderr, 'PiecePickerStreaming::pick_rarest: not vs.in_range( f, t, i ) f:', f, 't:', t, 'i:', i
                        continue
                    if not haves[i] or self.has[i]:
                        if DEBUGPP:
                            print >> sys.stderr, 'PiecePickerStreaming::pick_rarest: not haves[i] or self.has[i] i:', i
                        continue
                    if not wantfunc(i):
                        if DEBUGPP:
                            print >> sys.stderr, 'PiecePickerStreaming::pick_rarest: not wantfunc(i) i:', i
                        continue
                    if self.helper is None or helper_con or not self.helper.is_ignored(i):
                        return i

        first, last = vs.download_range()
        priority_first, priority_last = vs.get_high_range()
        if priority_first < priority_last:
            first = priority_first
            highprob_cutoff = vs.normalize(priority_last + 1)
            midprob_cutoff = vs.normalize(first + self.MU * vs.get_range_length(first, highprob_cutoff))
        else:
            highprob_cutoff = last
            midprob_cutoff = vs.normalize(first + self.MU * vs.high_prob_curr_pieces)
        if DEBUG:
            log('pps::next_new: first', first, 'last', last, 'priority_first', priority_first, 'priority_last', priority_last, 'highprob_cutoff', highprob_cutoff, 'midprob_cutoff', midprob_cutoff)
        if vs.live_streaming:
            allow_based_on_performance = connection.download.bad_performance_counter < 5
        elif connection:
            allow_based_on_performance = connection.download.bad_performance_counter < 1
        else:
            allow_based_on_performance = True
        choice = None
        if vs.prebuffering:
            f = first
            if vs.live_streaming:
                prebuf_pieces = self.transporter.max_prebuf_packets
            else:
                prebuf_pieces = vs.prebuf_pieces
            t = vs.normalize(first + prebuf_pieces)
            type = 'high'
            r = None
            if len(vs.prebuf_high_priority_pieces):
                high_priority = True
                r = vs.prebuf_high_priority_pieces[:]
                choice = pick_rarest_small_range(f, t, r, shuffle)
            if choice is None:
                high_priority = False
                r = vs.prebuf_needed_pieces[:]
                choice = pick_rarest_small_range(f, t, r, shuffle)
            if DEBUG:
                log('pps::next_new: pick piece for prebuffering: shuffle', shuffle, 'from', f, 'to', t, 'high_priority', high_priority, 'range', r, 'choice', choice)
        if choice is None:
            if vs.live_streaming:
                choice = pick_rarest_small_range(first, highprob_cutoff)
            else:
                choice = pick_first(first, highprob_cutoff)
                if DEBUG:
                    log('pps::next_new: pick_first(first=%d, highprob_cutoff=%d)' % (first, highprob_cutoff), 'choice', choice)
            type = 'high'
        if choice is None and not shuffle:
            choice = pick_first(first, last)
            if DEBUG:
                log('pps::next_new: no shuffle, download range: pick_first(first=%d, last=%d)' % (first, last), 'choice', choice)
            if choice is None:
                choice = pick_first(vs.first_piece, vs.last_piece)
                if DEBUG:
                    log('pps::next_new: no shuffle, whole range: pick_first(vs.first_piece=%d, vs.last_piece=%d)' % (vs.first_piece, vs.last_piece), 'choice', choice)
        if not allow_based_on_performance:
            high_priority_choice = choice
            choice = None
        if choice is None:
            choice = pick_rarest_small_range(highprob_cutoff, midprob_cutoff)
            if DEBUG:
                log('pps::next_new: pick_rarest_small_range(highprob_cutoff=%d, midprob_cutoff=%d)' % (highprob_cutoff, midprob_cutoff), 'choice', choice)
            type = 'mid'
        if choice is None:
            if vs.live_streaming:
                pass
            else:
                choice = pick_rarest(midprob_cutoff, last)
                if DEBUG:
                    log('pps::next_new: pick_rarest(midprob_cutoff=%d, last=%d)' % (midprob_cutoff, last), 'choice', choice)
            type = 'low'
        if choice and willrequest:
            self.stats[type] += 1
        if DEBUG:
            log('pps::next_new: picked piece %s [type=%s] [%d,%d,%d,%d]' % (`choice`,
             type,
             first,
             highprob_cutoff,
             midprob_cutoff,
             last))
        if choice is None and not allow_based_on_performance:
            if high_priority_choice:
                availability = 0
                for download in self.downloader.downloads:
                    if download.have[high_priority_choice] and not download.bad_performance_counter:
                        availability += 1

                if not availability:
                    if DEBUG:
                        log('pps:next_new: the bad_performance_counter says this is a bad peer... but we have nothing better... requesting piece', high_priority_choice, 'regardless.')
                    choice = high_priority_choice
        if not vs.live_streaming:
            if choice is None and not self.am_I_complete():
                if shuffle:
                    secondchoice = pick_rarest(vs.first_piece, vs.last_piece)
                else:
                    secondchoice = pick_first(vs.first_piece, vs.last_piece)
                if secondchoice is not None:
                    if DEBUG:
                        log('pps::next_new: picking skipped-over piece', secondchoice)
                    return secondchoice
        return choice

    def is_valid_piece(self, piece):
        is_valid = self.videostatus.in_valid_range(piece)
        if not is_valid:
            for vs in self.extra_videostatus:
                is_valid = vs.in_valid_range(piece)
                if is_valid:
                    break

        return is_valid

    def get_valid_range_iterator(self, skip_filter = False):
        if skip_filter:
            return PiecePicker.get_valid_range_iterator(self)
        if self.videostatus.live_streaming and self.videostatus.get_live_startpos() is None:
            if DEBUG:
                log('pps::get_valid_range_iterator: not hooked in, valid range set to total')
            return PiecePicker.get_valid_range_iterator(self)
        if DEBUG:
            log('pps::get_valid_range_iterator: live hooked in or VOD, valid range set to subset')
        return self.valid_range_generator()

    def valid_range_generator(self):
        first, last = self.videostatus.download_range()
        for x in self.videostatus.generate_range((first, last)):
            yield x

        for vs in self.extra_videostatus:
            first, last = vs.download_range()
            for x in vs.generate_range((first, last)):
                yield x

    def get_live_source_have(self, find_source = False):
        ret = None
        if find_source:
            source_have = None
            auth_peer_have = None
            for d in self.peer_connections.values():
                if d['connection'].is_live_source():
                    source_have = d['connection'].download.have
                    if DEBUG:
                        log('pps::get_live_source_have: found source: find_source', find_source, 'ip', d['connection'].get_ip())
                    break
                if auth_peer_have is None and d['connection'].is_live_authorized_peer():
                    auth_peer_have = d['connection'].download.have
                    if DEBUG:
                        log('pps::get_live_source_have: found authorized peer: find_source', find_source, 'ip', d['connection'].get_ip())

            if source_have is not None:
                ret = source_have
            else:
                ret = auth_peer_have
        else:
            for d in self.peer_connections.values():
                if d['connection'].is_live_authorized_peer():
                    ret = d['connection'].download.have
                    if DEBUG:
                        log('pps::get_live_source_have: found authorized peer: find_source', find_source, 'ip', d['connection'].get_ip())
                    break

        return ret

    def am_I_complete(self):
        return self.done and not TEST_VOD_OVERRIDE


PiecePickerVOD = PiecePickerStreaming
