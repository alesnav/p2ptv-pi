#Embedded file name: ACEStream\Core\Video\VideoStatus.pyo
import sys
from math import ceil, floor
from ACEStream.Core.simpledefs import *
from threading import currentThread, Lock
from traceback import print_exc
from ACEStream.Core.Utilities.logger import log, log_exc
LIVE_WRAPAROUND = True
DEBUG = False
DEBUG_SKIP_METADATA = False

class VideoStatus():

    def __init__(self, piecelen, fileinfo, videoinfo, authparams, is_extra = False):
        self.piecelen = piecelen
        self.sigsize = 0
        self.fileinfo = fileinfo
        self.videoinfo = videoinfo
        self.authparams = authparams
        self.piecelock = Lock()
        self.high_prob_curr_time = 20
        self.high_prob_curr_time_limit = (10, 180, 10)
        self.high_prob_curr_pieces = 6
        self.high_prob_curr_pieces_limit = (4, 50, 4)
        index = self.videoinfo['index']
        if index == -1:
            index = 0
        self.fileindex = index
        movie_offset = sum((filesize for _, filesize in fileinfo[:index] if filesize))
        movie_name = fileinfo[index][0]
        movie_size = fileinfo[index][1]
        self.selected_movie = {'offset': movie_offset,
         'name': movie_name,
         'size': movie_size}
        movie_begin = movie_offset
        movie_end = movie_offset + movie_size - 1
        self.movie_range = ((movie_begin / piecelen, movie_begin % piecelen), (movie_end / piecelen, movie_end % piecelen))
        self.first_piecelen = piecelen - self.movie_range[0][1]
        self.last_piecelen = self.movie_range[1][1] + 1
        self.first_piece = self.movie_range[0][0]
        self.last_piece = self.movie_range[1][0]
        self.movie_numpieces = self.last_piece - self.first_piece + 1
        self.completed = 0.0
        self.can_be_downloaded = not is_extra
        self.min_download_percent = 0.0
        self.is_extra = is_extra
        self.numhave = 0
        self.have = []
        if DEBUG:
            log('VideoStatus:__init__: index', index, 'movie_offset', movie_offset, 'movie_size', movie_size, 'self.first_piece', self.first_piece, 'self.last_piece', self.last_piece, 'self.movie_numpieces', self.movie_numpieces)
        self.live_streaming = videoinfo['live']
        self.live_startpos = None
        self.live_first_piece = None
        self.live_first_piece_with_offset = None
        self.live_last_piece = None
        self.live_first_ts = None
        self.live_last_ts = None
        self.live_buffer_pieces = 0
        self.playback_pos_is_live = True
        self.playback_pos_observers = []
        self.wraparound = self.live_streaming and LIVE_WRAPAROUND
        self.wraparound_delta = max(4, self.movie_numpieces / 8)
        self.playback_pos = self.first_piece
        self.playback_pos_real = self.playback_pos
        self.last_read_pos = None
        if self.live_streaming:
            self.set_bitrate(videoinfo['bitrate'])
            self.live_hook_left_offset_min = self.time_to_pieces(10)
            self.live_hook_left_offset = self.live_hook_left_offset_min
            self.live_hook_left_offset_step = self.live_hook_left_offset
            self.live_hook_left_offset_max = self.wraparound_delta
        elif not DEBUG_SKIP_METADATA and videoinfo['bitrate']:
            if DEBUG:
                log('vs::__init__: got bitrate', videoinfo['bitrate'])
            self.set_bitrate(videoinfo['bitrate'])
        else:
            if movie_size < 52428800:
                fake_bitrate = 64
            elif movie_size < 104857600:
                fake_bitrate = 128
            elif movie_size < 1073741824:
                fake_bitrate = 256
            else:
                fake_bitrate = 512
            self.set_bitrate(fake_bitrate * 1024, True)
        mimetype = None
        if 'mimetype' in self.videoinfo:
            mimetype = self.videoinfo['mimetype']
        self.prebuf_extra_pieces = None
        self.got_prebuf_pieces = False
        self.prebuf_high_priority_pieces = []
        self.prebuf_high_priority_length = 0
        self.prebuf_needed_pieces = []
        if self.live_streaming:
            self.prebuf_missing_pieces = []
        else:
            high_range_len = self.get_high_range_length()
            self.prebuf_pieces = min(self.movie_numpieces, 2 * high_range_len)
            self.prebuf_needed_pieces.extend(self.generate_range((self.first_piece, self.first_piece + self.prebuf_pieces)))
            if DEBUG:
                log('vs::__init__: set needed pieces: total_pieces', self.movie_numpieces, 'high_range_len', high_range_len, 'prebuf_pieces', self.prebuf_pieces, 'prebuf_needed_pieces', self.prebuf_needed_pieces)
            if not DEBUG_SKIP_METADATA and videoinfo.has_key('prebuf_pieces') and videoinfo['prebuf_pieces']:
                try:
                    self.prebuf_extra_pieces = [ int(x) for x in videoinfo['prebuf_pieces'].split(',') ]
                    if len(self.prebuf_extra_pieces) == 1 and self.prebuf_extra_pieces[0] == 0:
                        self.prebuf_extra_pieces = []
                    self.got_prebuf_pieces = True
                    if DEBUG:
                        log('vs::__init__: got prebuf pieces', videoinfo['prebuf_pieces'], 'extra', self.prebuf_extra_pieces)
                except:
                    log_exc()

            if not self.got_prebuf_pieces:
                self.prebuf_extra_pieces = []
                if mimetype == 'video/mpeg' or mimetype == 'video/mp4':
                    p = int(floor(self.last_piece * 0.997))
                    self.prebuf_extra_pieces.extend(self.generate_range((p, self.last_piece + 1)))
                elif not mimetype.startswith('audio'):
                    tail = 0
                    if movie_size > 1073741824:
                        tail = int(ceil(8388608 / self.piecelen))
                    elif movie_size > 524288000:
                        tail = int(ceil(7340032 / self.piecelen))
                    elif movie_size > 157286400:
                        tail = int(ceil(4194304 / self.piecelen))
                    else:
                        tail = int(ceil(2097152 / self.piecelen))
                    if tail > 0:
                        self.prebuf_extra_pieces.extend(self.generate_range((self.last_piece - tail + 1, self.last_piece + 1)))
                    if DEBUG:
                        log('vs::__init__: set extra pieces: movie_size', movie_size, 'mimetype', mimetype, 'tail', tail, 'prebuf_extra_pieces', self.prebuf_extra_pieces)
            self.prebuf_needed_pieces.extend(self.prebuf_extra_pieces)
            self.prebuf_needed_pieces = list(set(self.prebuf_needed_pieces))
            self.prebuf_needed_pieces.sort()
            self.prebuf_missing_pieces = self.prebuf_needed_pieces[:]
        if DEBUG:
            log('vs::__init__: prebuf configuration: mimetype', mimetype, 'size', movie_size, 'piecelen', self.piecelen, 'first', self.first_piece, 'last', self.last_piece, 'needed', self.prebuf_needed_pieces)
        if self.live_streaming:
            self.dropping = True
        else:
            self.dropping = False
        self.playing = False
        self.paused = False
        self.autoresume = False
        self.prebuffering = True
        self.pausable = VODEVENT_PAUSE in videoinfo['userevents'] and VODEVENT_RESUME in videoinfo['userevents']

    def add_high_priority_pieces(self, pieces):
        self.piecelock.acquire()
        try:
            if DEBUG:
                log('vs::add_high_priority_pieces:', pieces, 'thread', currentThread().getName())
            self.prebuf_high_priority_length += len(pieces)
            for index in pieces:
                if index in self.have:
                    continue
                if index not in self.prebuf_high_priority_pieces:
                    self.prebuf_high_priority_pieces.append(index)

        finally:
            self.piecelock.release()

    def set_high_priority_pieces(self, pieces):
        self.piecelock.acquire()
        try:
            if DEBUG:
                log('vs::set_high_priority_pieces:', pieces, 'thread', currentThread().getName())
            self.prebuf_high_priority_length = len(pieces)
            self.prebuf_high_priority_pieces = []
            for index in pieces:
                if index in self.have:
                    continue
                self.prebuf_high_priority_pieces.append(index)

        finally:
            self.piecelock.release()

    def add_missing_piece(self, index, high_priority = False):
        self.piecelock.acquire()
        try:
            if DEBUG:
                log('vs::add_missing_piece:', index, 'high_priority', high_priority, 'thread', currentThread().getName())
            if index in self.have:
                return
            if high_priority and index not in self.prebuf_high_priority_pieces:
                self.prebuf_high_priority_pieces.append(index)
                self.prebuf_high_priority_length += 1
            if index not in self.prebuf_needed_pieces:
                self.prebuf_needed_pieces.append(index)
                self.prebuf_missing_pieces.append(index)
                if not self.prebuffering:
                    self.prebuffering = True
        finally:
            self.piecelock.release()

    def add_missing_piece_range(self, pieces, high_priority = False):
        self.piecelock.acquire()
        try:
            if DEBUG:
                log('vs::add_missing_piece_range:', pieces, 'high_priority', high_priority, 'thread', currentThread().getName())
            for index in pieces:
                if index in self.have:
                    continue
                if high_priority and index not in self.prebuf_high_priority_pieces:
                    self.prebuf_high_priority_pieces.append(index)
                    self.prebuf_high_priority_length += 1
                if index not in self.prebuf_needed_pieces:
                    self.prebuf_needed_pieces.append(index)
                    self.prebuf_missing_pieces.append(index)
                    if not self.prebuffering:
                        self.prebuffering = True

        finally:
            self.piecelock.release()

    def high_priority_pieces(self):
        self.piecelock.acquire()
        try:
            return len(self.prebuf_high_priority_pieces)
        finally:
            self.piecelock.release()

    def high_priority_length(self):
        self.piecelock.acquire()
        try:
            return self.prebuf_high_priority_length
        finally:
            self.piecelock.release()

    def got_piece(self, index):
        self.piecelock.acquire()
        try:
            if index in self.have:
                return
            start_new_file = False
            if DEBUG:
                log('vs::got_piece: index', index, 'thread', currentThread().getName())
            if self.in_download_range(index):
                self.have.append(index)
                self.numhave += 1
                self.completed = self.numhave / float(self.movie_numpieces)
                if not self.can_be_downloaded and self.completed >= self.min_download_percent:
                    self.can_be_downloaded = True
                    start_new_file = True
                if index in self.prebuf_high_priority_pieces:
                    self.prebuf_high_priority_pieces.remove(index)
                if len(self.prebuf_missing_pieces):
                    try:
                        if index in self.prebuf_missing_pieces:
                            self.prebuf_missing_pieces.remove(index)
                        if len(self.prebuf_missing_pieces) == 0 and self.is_extra:
                            self.prebuffering = False
                    except:
                        pass

            elif DEBUG:
                log('vs::got_piece: piece not in download range: index', index)
            return start_new_file
        finally:
            self.piecelock.release()

    def live_invalidate_piece(self, index):
        self.piecelock.acquire()
        try:
            if index in self.have:
                if DEBUG:
                    log('vs::live_invalidate_piece: index', index)
                self.have.remove(index)
                self.numhave -= 1
        finally:
            self.piecelock.release()

    def add_playback_pos_observer(self, observer):
        self.playback_pos_observers.append(observer)

    def real_piecelen(self, x):
        if x == self.first_piece:
            return self.first_piecelen
        elif x == self.last_piece:
            return self.last_piecelen
        else:
            return self.piecelen

    def set_bitrate(self, bitrate, fake_bitrate = False):
        self.bitrate_set = not fake_bitrate
        self.bitrate = bitrate
        self.piece_per_sec = float(bitrate) / self.piecelen
        if DEBUG:
            log('vs::set_bitrate: bitrate', bitrate, 'fake', fake_bitrate, 'piece_per_sec', self.piece_per_sec)

    def set_duration(self, duration):
        try:
            self.set_bitrate(self.selected_movie['size'] / duration)
        except:
            log_exc()

    def set_prebuf_pieces(self, prebuf_extra_pieces):
        self.piecelock.acquire()
        try:
            if DEBUG:
                log('vs::set_prebuf_pieces: prebuf_extra_pieces', prebuf_extra_pieces)
            prebuf_needed_pieces = []
            prebuf_pieces = min(self.movie_numpieces, 2 * self.get_high_range_length())
            prebuf_needed_pieces.extend(self.generate_range((self.first_piece, self.first_piece + prebuf_pieces)))
            if len(prebuf_extra_pieces) == 1 and prebuf_extra_pieces[0] == 0:
                prebuf_extra_pieces = []
            prebuf_needed_pieces.extend(prebuf_extra_pieces)
            prebuf_needed_pieces = list(set(prebuf_needed_pieces))
            prebuf_needed_pieces.sort()
            prebuf_missing_pieces = filter(lambda i: i not in self.have, prebuf_needed_pieces)
            if DEBUG:
                log('vs::set_prebuf_pieces: prebuf_pieces', prebuf_pieces, 'prebuf_needed_pieces', prebuf_needed_pieces, 'prebuf_missing_pieces', prebuf_missing_pieces)
            self.prebuf_pieces = prebuf_pieces
            self.prebuf_needed_pieces = prebuf_needed_pieces
            self.prebuf_missing_pieces = prebuf_missing_pieces
        except:
            if DEBUG:
                print_exc()
        finally:
            self.piecelock.release()

    def update_player_buffer_pieces(self, player_buffer_time):
        count = self.time_to_pieces(player_buffer_time)
        buffer_pieces = []
        last = min(self.first_piece + count, self.last_piece + 1)
        buffer_pieces.extend(self.generate_range((self.first_piece, last)))
        self.set_high_priority_pieces(buffer_pieces)
        if DEBUG:
            log('vs::update_player_buffer_pieces: buffer_pieces', buffer_pieces, 'player_buffer_time', player_buffer_time, 'bitrate', self.bitrate)

    def set_live_startpos(self, pos):
        invalidate_range = None
        if self.live_startpos is not None:
            dist1 = self.dist_range(self.live_startpos, pos)
            dist2 = self.dist_range(pos, self.live_startpos)
            if DEBUG:
                log('vs::set_live_startpos: check range: curpos', self.live_startpos, 'newpos', pos, 'dist1', dist1, 'dist2', dist2)
            if dist1 <= dist2:
                if dist1 > 1:
                    invalidate_range = self.generate_range((self.live_startpos, pos))
            elif dist2 > 1:
                invalidate_range = self.generate_range((pos, self.live_startpos))
        self.live_startpos = pos
        self.playback_pos = pos
        self.playback_pos_real = pos
        for o in self.playback_pos_observers:
            o(None, pos)

        return invalidate_range

    def get_live_startpos(self):
        return self.live_startpos

    def generate_range(self, (f, t)):
        if self.wraparound and f > t:
            for x in xrange(f, self.last_piece + 1):
                yield x

            for x in xrange(self.first_piece, t):
                yield x

        else:
            for x in xrange(f, t):
                yield x

    def dist_range(self, f, t):
        if f > t:
            return self.last_piece - f + t - self.first_piece
        else:
            return t - f

    def in_range(self, f, t, x):
        if self.wraparound and f > t:
            return self.first_piece <= x < t or f <= x <= self.last_piece
        else:
            return f <= x < t

    def inc_playback_pos(self):
        oldpos = self.playback_pos
        self.playback_pos += 1
        if self.playback_pos > self.last_piece:
            if self.wraparound:
                self.playback_pos = self.first_piece
            else:
                self.playback_pos = self.last_piece + 1
        if self.live_streaming and self.live_startpos is not None:
            self.live_startpos = self.playback_pos
        for o in self.playback_pos_observers:
            o(oldpos, self.playback_pos)

    def in_download_range(self, x):
        if self.wraparound:
            wraplen = self.playback_pos + self.wraparound_delta - self.last_piece
            if wraplen > 0:
                return self.first_piece <= x < self.first_piece + wraplen or self.playback_pos <= x <= self.last_piece
            return self.playback_pos <= x < self.playback_pos + self.wraparound_delta
        else:
            return self.first_piece <= x <= self.last_piece

    def in_valid_range(self, piece):
        if self.live_streaming:
            if self.live_startpos is None:
                return True
            else:
                begin, end = self.live_get_valid_range()
                ret = self.in_range(begin, end, piece)
                if DEBUG and not ret:
                    log('vs::in_valid_range: not in valid range:', begin, '<', piece, '<', end)
                return ret
        else:
            return self.first_piece <= piece <= self.last_piece

    def live_get_valid_range(self):
        begin = self.normalize(self.playback_pos - self.wraparound_delta)
        end = self.normalize(self.playback_pos + self.wraparound_delta)
        return (begin, end)

    def live_get_window_range(self):
        if self.live_first_piece is None or self.live_last_piece is None:
            return
        return (self.live_first_piece, self.live_last_piece)

    def live_piece_to_invalidate(self, last_piece = None):
        if last_piece is None:
            last_piece = self.playback_pos
        return self.normalize(last_piece - self.wraparound_delta)

    def get_range_diff(self, oldrange, newrange):
        rlist = []
        if oldrange[0] == 0 and oldrange[1] == self.movie_numpieces - 1:
            if newrange[0] < newrange[1]:
                a = (oldrange[0], newrange[0] - 1)
                b = (newrange[1] + 1, oldrange[1])
                rlist = [a, b]
                return (None, rlist)
            else:
                a = (newrange[1] + 1, newrange[0] - 1)
                rlist = [a]
                return (None, rlist)
        oldset = range2set(oldrange, self.movie_numpieces)
        newset = range2set(newrange, self.movie_numpieces)
        return (oldset - newset, rlist)

    def normalize(self, x):
        if self.first_piece <= x <= self.last_piece:
            return x
        elif self.wraparound:
            return (x - self.first_piece) % self.movie_numpieces + self.first_piece
        else:
            return max(self.first_piece, min(x, self.last_piece))

    def time_to_pieces(self, sec):
        return int(ceil(sec * self.piece_per_sec))

    def size_to_pieces(self, size):
        return int(ceil(size / self.piecelen))

    def pieces_to_time(self, pieces):
        return int(ceil(pieces / self.piece_per_sec))

    def download_range(self):
        first = self.playback_pos
        if self.wraparound:
            wraplen = first + self.wraparound_delta + 1 - self.last_piece
            if wraplen > 0:
                last = self.first_piece + wraplen
            else:
                last = first + self.wraparound_delta + 1
        else:
            last = self.last_piece + 1
        return (first, last)

    def get_wraparound(self):
        return self.wraparound

    def increase_high_range(self, factor = 1):
        self.high_prob_curr_time += factor * self.high_prob_curr_time_limit[2]
        if self.high_prob_curr_time > self.high_prob_curr_time_limit[1]:
            self.high_prob_curr_time = self.high_prob_curr_time_limit[1]
        self.high_prob_curr_pieces += int(factor * self.high_prob_curr_pieces_limit[2])
        if self.high_prob_curr_pieces > self.high_prob_curr_pieces_limit[1]:
            self.high_prob_curr_pieces = self.high_prob_curr_pieces_limit[1]
        if DEBUG:
            log('vs::change_high_range: increase,', self.high_prob_curr_time, 'seconds or', self.high_prob_curr_pieces, 'pieces')

    def decrease_high_range(self, factor = 1):
        self.high_prob_curr_time -= factor * self.high_prob_curr_time_limit[2]
        if self.high_prob_curr_time < self.high_prob_curr_time_limit[0]:
            self.high_prob_curr_time = self.high_prob_curr_time_limit[0]
        self.high_prob_curr_pieces -= int(factor * self.high_prob_curr_pieces_limit[2])
        if self.high_prob_curr_pieces < self.high_prob_curr_pieces_limit[0]:
            self.high_prob_curr_pieces = self.high_prob_curr_pieces_limit[0]
        if DEBUG:
            log('vs::change_high_range: decrease,', self.high_prob_curr_time, 'seconds or', self.high_prob_curr_pieces, 'pieces')

    def set_high_range(self, seconds = None, pieces = None):
        if seconds:
            self.high_prob_curr_time = seconds
        if pieces:
            self.high_prob_curr_pieces = pieces

    def get_high_range(self, min_size = None):
        first, _ = self.download_range()
        if self.prebuf_extra_pieces is not None and first in self.prebuf_extra_pieces:
            return (first, first + 1)
        pieces_needed = min(self.time_to_pieces(self.high_prob_curr_time), self.high_prob_curr_pieces)
        if min_size is not None:
            pieces_needed = max(pieces_needed, min_size)
        last = min(self.last_piece, first + pieces_needed, first + self.high_prob_curr_pieces_limit[1])
        return (first, last)

    def in_high_range(self, piece):
        first, last = self.get_high_range()
        return self.in_range(first, last, piece)

    def get_range_length(self, first, last):
        if self.wraparound and first > last:
            return self.last_piece - first + last - self.first_piece
        else:
            return last - first

    def get_high_range_length(self):
        first, last = self.get_high_range()
        return self.get_range_length(first, last)

    def generate_high_range(self, min_size = None):
        first, last = self.get_high_range(min_size)
        return self.generate_range((first, last))

    def generate_download_range(self):
        first, last = self.download_range()
        return self.generate_range((first, last))

    def get_download_range_length(self):
        first, last = self.download_range()
        return self.get_range_length(first, last)


def range2set(_range, maxrange):
    if _range[0] <= _range[1]:
        _set = set(xrange(_range[0], _range[1] + 1))
    else:
        _set = set(xrange(_range[0], maxrange)) | set(range(0, _range[1] + 1))
    return _set
