#Embedded file name: ACEStream\Core\BitTornado\BT1\Downloader.pyo
import sys
import time
from traceback import print_exc, print_stack
from threading import currentThread
from ACEStream.Core.BitTornado.CurrentRateMeasure import Measure
from ACEStream.Core.BitTornado.bitfield import Bitfield
from random import shuffle
from base64 import b64encode
from ACEStream.Core.BitTornado.clock import clock
from ACEStream.Core.DecentralizedTracking.repex import REPEX_LISTEN_TIME
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.GlobalConfig import globalConfig
try:
    from ACEStream.Core.ProxyService.Helper import SingleDownloadHelperInterface
except ImportError:

    class SingleDownloadHelperInterface():

        def __init__(self):
            pass


try:
    True
except:
    True = 1
    False = 0

DEBUG = False
DEBUG2 = False
DEBUGBF = False
DEBUG_CHUNKS = False
EXPIRE_TIME = 60 * 60

def debug_format_have(have, convert = True):
    x = []
    if convert:
        y = have.toboollist()
    else:
        y = have[:]
    for i in xrange(len(y)):
        if y[i]:
            x.append(i)

    have_ranges = []
    if len(x):
        p = None
        f = None
        t = None
        for i in sorted(x):
            if p is None:
                f = i
            elif i != p + 1:
                t = p
                have_ranges.append((f, t))
                f = i
            p = i

        have_ranges.append((f, i))
    return have_ranges


if DEBUG_CHUNKS:
    _ident_letters = {}
    _ident_letter_pool = None

    def get_ident_letter(download):
        global _ident_letter_pool
        if download.ip not in _ident_letters:
            if not _ident_letter_pool:
                _ident_letter_pool = [ chr(c) for c in range(ord('a'), ord('z') + 1) ] + [ chr(c) for c in range(ord('A'), ord('Z') + 1) ]
            _ident_letters[download.ip] = _ident_letter_pool.pop(0)
        return _ident_letters[download.ip]


    def print_chunks(downloader, pieces, before = (), after = (), compact = True):
        if pieces:
            do_I_have = downloader.storage.do_I_have
            do_I_have_requests = downloader.storage.do_I_have_requests
            inactive_requests = downloader.storage.inactive_requests
            piece_size = downloader.storage.piece_length
            chunk_size = downloader.storage.request_size
            chunks_per_piece = int(piece_size / chunk_size)
            if compact:
                request_map = {}
                for download in downloader.downloads:
                    for piece, begin, length in download.active_requests:
                        if piece not in request_map:
                            request_map[piece] = 0
                        request_map[piece] += 1

                def print_chunks_helper(piece_id):
                    if do_I_have(piece_id):
                        return '#'
                    if do_I_have_requests(piece_id):
                        return '-'
                    if piece_id in request_map:
                        return str(min(9, request_map[piece_id]))
                    return '?'

            else:
                request_map = {}
                for download in downloader.downloads:
                    for piece, begin, length in download.active_requests:
                        if piece not in request_map:
                            request_map[piece] = ['-'] * chunks_per_piece
                        index = int(begin / chunk_size)
                        if request_map[piece][index] == '-':
                            request_map[piece][index] = get_ident_letter(download)
                        elif type(request_map[piece][index]) is str:
                            request_map[piece][index] = 2
                        else:
                            request_map[piece][index] += 1
                        request_map[piece][int(begin / chunk_size)] = get_ident_letter(download)

                def print_chunks_helper(piece_id):
                    if do_I_have(piece_id):
                        return '#' * chunks_per_piece
                    if piece_id in request_map:
                        if piece_id in inactive_requests and type(inactive_requests[piece_id]) is list:
                            for begin, length in inactive_requests[piece_id]:
                                request_map[piece_id][int(begin / chunk_size)] = ' '

                        return ''.join([ str(c) for c in request_map[piece_id] ])
                    return '-' * chunks_per_piece

            if before:
                s_before = before[0]
            else:
                s_before = ''
            if after:
                s_after = after[-1]
            else:
                s_after = ''
            print >> sys.stderr, 'Outstanding %s:%d:%d:%s [%s|%s|%s]' % (s_before,
             pieces[0],
             pieces[-1],
             s_after,
             ''.join(map(print_chunks_helper, before)),
             ''.join(map(print_chunks_helper, pieces)),
             ''.join(map(print_chunks_helper, after)))
        else:
            print >> sys.stderr, 'Outstanding 0:0 []'


else:

    def print_chunks(downloader, pieces, before = (), after = (), compact = True):
        pass


class PerIPStats():

    def __init__(self, ip):
        self.numgood = 0
        self.bad = {}
        self.numconnections = 0
        self.lastdownload = None
        self.peerid = None


class BadDataGuard():

    def __init__(self, download):
        self.download = download
        self.ip = download.ip
        self.downloader = download.downloader
        self.stats = self.downloader.perip[self.ip]
        self.lastindex = None

    def failed(self, index, bump = False):
        self.stats.bad.setdefault(index, 0)
        self.downloader.gotbaddata[self.ip] = 1
        self.stats.bad[index] += 1
        if DEBUG:
            print >> sys.stderr, 'BadDataGuard::failed: index', index, 'ip', self.ip, 'bad[index]', self.stats.bad[index], 'len(bad)', len(self.stats.bad)
        if len(self.stats.bad) > 1:
            if self.download is not None:
                self.downloader.try_kick(self.download)
            elif self.stats.numconnections == 1 and self.stats.lastdownload is not None:
                self.downloader.try_kick(self.stats.lastdownload)
        if len(self.stats.bad) >= 3 and len(self.stats.bad) > int(self.stats.numgood / 30):
            self.downloader.try_ban(self.ip)
        elif bump:
            self.downloader.picker.bump(index)

    def good(self, index):
        if index != self.lastindex:
            self.stats.numgood += 1
            self.lastindex = index


class SingleDownload(SingleDownloadHelperInterface):

    def __init__(self, downloader, connection):
        SingleDownloadHelperInterface.__init__(self)
        self.downloader = downloader
        self.connection = connection
        self.choked = True
        self.interested = False
        self.active_requests = []
        self.measure = Measure(downloader.max_rate_period)
        self.peermeasure = Measure(downloader.max_rate_period)
        self.raw_have = Bitfield(downloader.numpieces)
        self.have = Bitfield(downloader.numpieces)
        self.last = -1000
        self.last2 = -1000
        self.example_interest = None
        self.backlog = 2
        self.ip = connection.get_ip()
        self.guard = BadDataGuard(self)
        self.app_mode = globalConfig.get_mode()
        self.white_list = None
        self.black_list = None
        self.app_mode = globalConfig.get_mode()
        if self.app_mode == 'node':
            source_node = globalConfig.get_value('source_node')
            support_nodes = globalConfig.get_value('support_nodes')
            if not globalConfig.get_value('allow_peers_download'):
                self.white_list = set()
                if source_node is not None and globalConfig.get_value('allow_source_download'):
                    self.white_list.add(source_node[0])
                if len(support_nodes) and globalConfig.get_value('allow_support_download'):
                    self.white_list.update([ addr[0] for addr in support_nodes ])
            else:
                self.black_list = set()
                if source_node is not None and not globalConfig.get_value('allow_source_download'):
                    self.black_list.add(source_node[0])
                if len(support_nodes) and not globalConfig.get_value('allow_support_download'):
                    self.black_list.update([ addr[0] for addr in support_nodes ])
                if len(self.black_list) == 0:
                    self.black_list = None
            if DEBUG:
                log('download::__init__: white_list', self.white_list, 'black_list', self.black_list)
        self.helper = downloader.picker.helper
        self.proxy_have = Bitfield(downloader.numpieces)
        self.short_term_measure = Measure(5)
        self.bad_performance_counter = 0

    def _backlog(self, just_unchoked):
        self.backlog = int(min(2 + int(4 * self.measure.get_rate() / self.downloader.chunksize), 2 * just_unchoked + self.downloader.queue_limit()))
        if DEBUG:
            log('downloader::sd::_backlog: backlog', self.backlog, 'rate', self.measure.get_rate(), 'chunksize', self.downloader.chunksize, 'just_unchoked', just_unchoked, 'queue_limit', self.downloader.queue_limit())
        if self.backlog > 50:
            self.backlog = int(max(50, self.backlog * 0.075))
            if DEBUG:
                log('downloader::sd::_backlog: fix backlog', self.backlog)
        return self.backlog

    def disconnected(self):
        self.downloader.lost_peer(self)
        if self.have.complete() and self.downloader.storage.is_endgame():
            self.downloader.add_disconnected_seed(self.connection.get_readable_id())
        self._letgo()
        self.guard.download = None

    def _letgo(self):
        if self.downloader.queued_out.has_key(self):
            del self.downloader.queued_out[self]
        if not self.active_requests:
            return
        if self.downloader.endgamemode:
            self.active_requests = []
            return
        lost = {}
        for index, begin, length in self.active_requests:
            self.downloader.storage.request_lost(index, begin, length)
            lost[index] = 1

        lost = lost.keys()
        self.active_requests = []
        if self.downloader.paused:
            return
        ds = [ d for d in self.downloader.downloads if not d.choked ]
        shuffle(ds)
        for d in ds:
            d._request_more()

        for d in self.downloader.downloads:
            if d.choked and not d.interested:
                for l in lost:
                    if d.have[l] and self.downloader.storage.do_I_have_requests(l):
                        d.send_interested()
                        break

    def got_choke(self):
        if not self.choked:
            if DEBUG:
                log('downloader::got_choke: got choke: ip', self.connection.get_ip())
            self.choked = True
            self._letgo()
        elif DEBUG:
            log('downloader::got_choke: already choked: ip', self.connection.get_ip())

    def got_unchoke(self):
        if self.choked:
            if DEBUG:
                log('downloader::got_unchoke: got unchoke: ip', self.connection.get_ip(), 'interested', self.interested)
            self.choked = False
            if self.interested:
                self._request_more(new_unchoke=True)
            self.last2 = clock()
        elif DEBUG:
            log('downloader::got_unchoke: already unchoked: ip', self.connection.get_ip())

    def is_choked(self):
        return self.choked

    def is_interested(self):
        return self.interested

    def send_interested(self):
        if not self.interested:
            if DEBUG:
                log('downloader::send_interested: send interested: ip', self.connection.get_ip())
            self.interested = True
            self.connection.send_interested()
        elif DEBUG:
            log('downloader::send_interested: already interested: ip', self.connection.get_ip())

    def send_not_interested(self):
        if self.interested:
            if DEBUG:
                log('downloader::send_not_interested: send not interested: ip', self.connection.get_ip())
            self.interested = False
            self.connection.send_not_interested()
        elif DEBUG:
            log('downloader::send_not_interested: already not interested: ip', self.connection.get_ip())

    def got_piece(self, index, begin, hashlist, piece):
        if self.bad_performance_counter:
            self.bad_performance_counter -= 1
            if DEBUG:
                print >> sys.stderr, 'decreased bad_performance_counter to', self.bad_performance_counter
        length = len(piece)
        try:
            self.active_requests.remove((index, begin, length))
        except ValueError:
            self.downloader.discarded += length
            return False

        if self.downloader.endgamemode:
            self.downloader.all_requests.remove((index, begin, length))
            if DEBUG:
                print >> sys.stderr, 'Downloader: got_piece: removed one request from all_requests', len(self.downloader.all_requests), 'remaining'
        self.last = clock()
        self.last2 = clock()
        self.measure.update_rate(length)
        self.short_term_measure.update_rate(length)
        self.downloader.measurefunc(length)
        if not self.downloader.storage.piece_came_in(index, begin, hashlist, piece, self.guard):
            self.downloader.piece_flunked(index)
            return False
        self.downloader.picker.got_piece(index, begin, length)
        if self.downloader.storage.do_I_have(index):
            self.downloader.picker.complete(index)
        if self.downloader.endgamemode:
            for d in self.downloader.downloads:
                if d is not self:
                    if d.interested:
                        if d.choked:
                            d.fix_download_endgame()
                        else:
                            try:
                                d.active_requests.remove((index, begin, length))
                            except ValueError:
                                continue

                            d.connection.send_cancel(index, begin, length)
                            d.fix_download_endgame()

        self._request_more()
        self.downloader.check_complete(index)
        self.connection.total_downloaded += length
        return self.downloader.storage.do_I_have(index)

    def helper_forces_unchoke(self):
        self.choked = False

    def _request_more(self, new_unchoke = False, slowpieces = []):
        if self.helper is not None and self.is_frozen_by_helper():
            if DEBUG:
                print >> sys.stderr, 'Downloader: _request_more: blocked, returning'
            return
        if self.app_mode == 'node':
            ip = self.connection.get_ip()
            if DEBUG:
                log('download::_request_more: check ip', ip)
            if self.white_list is not None and ip not in self.white_list:
                if DEBUG:
                    log('download::_request_more: peer is not in the white list: ip', ip)
                return
            if self.black_list is not None and ip in self.black_list:
                if DEBUG:
                    log('download::_request_more: peer is in the black list: ip', ip)
                return
        if self.choked:
            if DEBUG:
                print >> sys.stderr, 'Downloader: _request_more: choked, returning'
            return
        if self.connection.connection.is_coordinator_con():
            if DEBUG:
                print >> sys.stderr, 'Downloader: _request_more: coordinator conn'
            return
        if self.downloader.endgamemode:
            self.fix_download_endgame(new_unchoke)
            if DEBUG:
                print >> sys.stderr, 'Downloader: _request_more: endgame mode, returning'
            return
        if self.downloader.paused:
            if DEBUG:
                print >> sys.stderr, 'Downloader: _request_more: paused, returning'
            return
        if len(self.active_requests) >= self._backlog(new_unchoke):
            if DEBUG:
                log('downloader::_request_more: more req than unchoke (active req: %d >= backlog: %d), download_rate=%d' % (len(self.active_requests), self._backlog(new_unchoke), self.downloader.download_rate))
            if self.downloader.download_rate:
                wait_period = self.downloader.chunksize / self.downloader.download_rate / 2.0
                if wait_period > 1.0:
                    if DEBUG:
                        print >> sys.stderr, 'Downloader: waiting for %f s to call _request_more again' % wait_period
                    self.downloader.scheduler(self._request_more, wait_period)
            if not (self.active_requests or self.backlog):
                if DEBUG:
                    print >> sys.stderr, 'Downloader::_request_more: queue out download'
                self.downloader.queued_out[self] = 1
            return
        lost_interests = []
        while len(self.active_requests) < self.backlog:
            interest = self.downloader.picker.next(self.have, self.downloader.storage.do_I_have_requests, self, self.downloader.too_many_partials(), self.connection.connection.is_helper_con(), slowpieces=slowpieces, connection=self.connection, proxyhave=self.proxy_have)
            diff = -1
            if DEBUG:
                print >> sys.stderr, 'Downloader: _request_more: next() returned', interest, 'took %.5f' % diff
            if interest is None:
                break
            if self.helper and self.downloader.storage.inactive_requests[interest] is None:
                self.connection.send_have(interest)
                break
            if self.helper and self.downloader.storage.inactive_requests[interest] == []:
                break
            self.example_interest = interest
            self.send_interested()
            loop = True
            while len(self.active_requests) < self.backlog and loop:
                request = self.downloader.storage.new_request(interest)
                if request is None:
                    log('downloader::_request_more: new_request returned none: index', interest)
                    lost_interests.append(interest)
                    break
                begin, length = request
                if DEBUG:
                    log('downloader::_request_more: new_request', interest, begin, length, 'to', self.connection.connection.get_ip(), self.connection.connection.get_port())
                self.downloader.picker.requested(interest, begin, length)
                self.active_requests.append((interest, begin, length))
                self.connection.send_request(interest, begin, length)
                self.downloader.chunk_requested(length)
                if not self.downloader.storage.do_I_have_requests(interest):
                    loop = False
                    lost_interests.append(interest)

        if not self.active_requests:
            self.send_not_interested()
        if lost_interests:
            for d in self.downloader.downloads:
                if d.active_requests or not d.interested:
                    continue
                if d.example_interest is not None and self.downloader.storage.do_I_have_requests(d.example_interest):
                    continue
                for lost in lost_interests:
                    if d.have[lost]:
                        break
                else:
                    continue

                interest = self.downloader.picker.next(d.have, self.downloader.storage.do_I_have_requests, self, self.downloader.too_many_partials(), self.connection.connection.is_helper_con(), willrequest=False, connection=self.connection, proxyhave=self.proxy_have)
                diff = -1
                if DEBUG:
                    print >> sys.stderr, 'Downloader: _request_more: next()2 returned', interest, 'took %.5f' % diff
                if interest is not None:
                    if self.helper and self.downloader.storage.inactive_requests[interest] is None:
                        self.connection.send_have(interest)
                        break
                    if self.helper and self.downloader.storage.inactive_requests[interest] == []:
                        break
                if interest is None:
                    d.send_not_interested()
                else:
                    d.example_interest = interest

        if not self.downloader.endgamemode and self.downloader.storage.is_endgame() and not (self.downloader.picker.videostatus and self.downloader.picker.videostatus.live_streaming):
            self.downloader.start_endgame()

    def fix_download_endgame(self, new_unchoke = False):
        if self.downloader.paused or self.connection.connection.is_coordinator_con():
            if DEBUG:
                print >> sys.stderr, 'Downloader: fix_download_endgame: paused', self.downloader.paused, 'or is_coordinator_con', self.connection.connection.is_coordinator_con()
            return
        if len(self.active_requests) >= self._backlog(new_unchoke):
            if not (self.active_requests or self.backlog) and not self.choked:
                self.downloader.queued_out[self] = 1
            if DEBUG:
                print >> sys.stderr, 'Downloader: fix_download_endgame: returned'
            return
        want = [ a for a in self.downloader.all_requests if self.have[a[0]] and a not in self.active_requests and (self.helper is None or self.connection.connection.is_helper_con() or not self.helper.is_ignored(a[0])) ]
        if not (self.active_requests or want):
            self.send_not_interested()
            if DEBUG:
                print >> sys.stderr, 'Downloader: fix_download_endgame: not interested'
            return
        if want:
            self.send_interested()
        if self.choked:
            if DEBUG:
                print >> sys.stderr, 'Downloader: fix_download_endgame: choked'
            return
        shuffle(want)
        del want[self.backlog - len(self.active_requests):]
        self.active_requests.extend(want)
        for piece, begin, length in want:
            if self.helper is None or self.connection.connection.is_helper_con() or self.helper.reserve_piece(piece, self):
                self.connection.send_request(piece, begin, length)
                self.downloader.chunk_requested(length)

    def got_invalidate(self, index):
        if DEBUG:
            log('downloader::got_invalidate: index', index)
        if not self.have[index]:
            return
        self.have[index] = False
        self.downloader.picker.lost_have(index)

    def got_have(self, index):
        if index == self.downloader.numpieces - 1:
            self.downloader.totalmeasure.update_rate(self.downloader.storage.total_length - (self.downloader.numpieces - 1) * self.downloader.storage.piece_length)
            self.peermeasure.update_rate(self.downloader.storage.total_length - (self.downloader.numpieces - 1) * self.downloader.storage.piece_length)
        else:
            self.downloader.totalmeasure.update_rate(self.downloader.storage.piece_length)
            self.peermeasure.update_rate(self.downloader.storage.piece_length)
        self.raw_have[index] = True
        if not self.downloader.picker.is_valid_piece(index):
            if DEBUG:
                print >> sys.stderr, 'Downloader::got_have: invalid piece: index', index, 'ip', self.connection.get_ip()
        if self.downloader.picker.videostatus and self.downloader.picker.videostatus.live_streaming and not self.connection.supports_piece_invalidate():
            i = self.downloader.picker.videostatus.live_piece_to_invalidate(index)
            if DEBUG:
                log('downloader::got_have: invalidate old piece: i', i, 'ip', self.connection.get_ip())
            self.got_invalidate(i)
        if self.have[index]:
            return
        self.have[index] = True
        self.downloader.picker.got_have(index, self.connection)
        if DEBUG:
            print >> sys.stderr, '>>>debug: got have:', self.connection.get_ip(), 'piece', index, 'have', debug_format_have(self.have), 'choked', self.choked, 'interested', self.interested
        self.downloader.aggregate_and_send_haves()
        if self.have.complete():
            self.downloader.picker.became_seed()
            if self.downloader.picker.am_I_complete():
                self.downloader.add_disconnected_seed(self.connection.get_readable_id())
                self.connection.close()
                return
        if self.downloader.endgamemode:
            self.fix_download_endgame()
        elif not self.downloader.paused and not self.downloader.picker.is_blocked(index) and self.downloader.storage.do_I_have_requests(index):
            if not self.choked:
                if DEBUG:
                    log('downloader::got_have: not choked, request more')
                self._request_more()
            else:
                if DEBUG:
                    log('downloader::got_have: choked, send interested')
                self.send_interested()
        elif DEBUG:
            print >> sys.stderr, 'downloader::got_have: do not request more: paused', self.downloader.paused, 'is_blocked', self.downloader.picker.is_blocked(index), 'have_requests', self.downloader.storage.do_I_have_requests(index)

    def _check_interests(self):
        if self.interested or self.downloader.paused:
            return
        for i in xrange(len(self.have)):
            if self.have[i] and not self.downloader.picker.is_blocked(i) and (self.downloader.endgamemode or self.downloader.storage.do_I_have_requests(i)):
                self.send_interested()
                return

    def got_have_bitfield(self, have):
        if self.downloader.picker.am_I_complete() and have.complete():
            if self.downloader.super_seeding:
                self.connection.send_bitfield(have.tostring())
            self.connection.try_send_pex()

            def auto_close():
                self.connection.close()
                self.downloader.add_disconnected_seed(self.connection.get_readable_id())

            self.downloader.scheduler(auto_close, REPEX_LISTEN_TIME)
            return
        if DEBUGBF:
            st = time.time()
        self.raw_have = have
        if have.complete():
            self.downloader.picker.got_seed()
        else:
            activerangeiterators = []
            if self.downloader.picker.videostatus and self.downloader.picker.videostatus.live_streaming and self.downloader.picker.videostatus.get_live_startpos() is None:
                activeranges = have.get_active_ranges()
                if len(activeranges) == 0:
                    activerangeiterators = [self.downloader.picker.get_valid_range_iterator()]
                else:
                    for s, e in activeranges:
                        activerangeiterators.append(xrange(s, e + 1))

            else:
                activerangeiterators = [self.downloader.picker.get_valid_range_iterator(skip_filter=True)]
            if DEBUGBF:
                print >> sys.stderr, 'Downloader: got_have_field: live: Filtering bitfield', activerangeiterators
            if DEBUGBF:
                print >> sys.stderr, 'Downloader: got_have_field: live or normal filter'
            validhave = Bitfield(self.downloader.numpieces)
            for iterator in activerangeiterators:
                for i in iterator:
                    if have[i]:
                        validhave[i] = True
                        self.downloader.picker.got_have(i, self.connection)

            if DEBUG:
                print >> sys.stderr, '>>>debug: got bitfield:', self.connection.get_ip(), 'have', debug_format_have(have)
                print >> sys.stderr, '>>>debug: got bitfield:', self.connection.get_ip(), 'validhave', debug_format_have(validhave)
            self.downloader.aggregate_and_send_haves()
            have = validhave
        if DEBUGBF:
            et = time.time()
            diff = et - st
            print >> sys.stderr, 'Download: got_have_field: took', diff
        self.have = have
        if self.downloader.endgamemode and not self.downloader.paused:
            for piece, begin, length in self.downloader.all_requests:
                if self.have[piece]:
                    self.send_interested()
                    break

            return
        self._check_interests()

    def reset_have(self):
        if DEBUG:
            print >> sys.stderr, 'Downloader::reset_have: before self.have:', self.have.toboollist()
        validhave = Bitfield(self.downloader.numpieces)
        for i in self.downloader.picker.get_valid_range_iterator():
            if self.raw_have[i]:
                validhave[i] = True

        self.have = validhave
        if DEBUG:
            print >> sys.stderr, 'Downloader::reset_have: after self.have:', self.have.toboollist()

    def get_rate(self):
        return self.measure.get_rate()

    def get_short_term_rate(self):
        return self.short_term_measure.get_rate()

    def is_snubbed(self, just_check = False):
        if not self.choked and not just_check and self.app_mode != 'node' and clock() - self.last2 > self.downloader.snub_time and not self.connection.connection.is_helper_con() and not self.connection.connection.is_coordinator_con():
            for index, begin, length in self.active_requests:
                self.connection.send_cancel(index, begin, length)

            self.got_choke()
        return clock() - self.last > self.downloader.snub_time

    def peer_is_complete(self):
        return self.have.complete()


class Downloader():

    def __init__(self, infohash, storage, picker, backlog, max_rate_period, numpieces, chunksize, measurefunc, snub_time, kickbans_ok, kickfunc, banfunc, scheduler = None):
        self.infohash = infohash
        self.b64_infohash = b64encode(infohash)
        self.storage = storage
        self.picker = picker
        self.backlog = backlog
        self.max_rate_period = max_rate_period
        self.measurefunc = measurefunc
        self.totalmeasure = Measure(max_rate_period * storage.piece_length / storage.request_size)
        self.numpieces = numpieces
        self.chunksize = chunksize
        self.snub_time = snub_time
        self.kickfunc = kickfunc
        self.banfunc = banfunc
        self.disconnectedseeds = {}
        self.downloads = []
        self.perip = {}
        self.gotbaddata = {}
        self.kicked = {}
        self.banned = {}
        self.kickbans_ok = kickbans_ok
        self.kickbans_halted = False
        self.super_seeding = False
        self.endgamemode = False
        self.endgame_queued_pieces = []
        self.all_requests = []
        self.discarded = 0L
        self.download_rate = 0
        self.bytes_requested = 0
        self.last_time = clock()
        self.queued_out = {}
        self.requeueing = False
        self.paused = False
        self.scheduler = scheduler
        self.scheduler(self.dlr_periodic_check, 1)
        if self.picker is not None:
            if self.picker.helper is not None:
                self.picker.helper.set_downloader(self)

    def dlr_periodic_check(self):
        self.picker.check_outstanding_requests(self.downloads)
        ds = [ d for d in self.downloads if not d.choked ]
        shuffle(ds)
        if DEBUG:
            print >> sys.stderr, 'Downloader::dlr_periodic_check: total downloads', len(self.downloads), ', not choked', len(ds)
        for d in ds:
            d._request_more()

        self.scheduler(self.dlr_periodic_check, 1)

    def get_download_rate(self):
        return self.download_rate / 1000

    def set_download_rate(self, rate):
        self.download_rate = rate * 1000
        self.bytes_requested = 0

    def queue_limit(self):
        if not self.download_rate:
            return 100000000000.0
        t = clock()
        self.bytes_requested -= (t - self.last_time) * self.download_rate
        self.last_time = t
        if not self.requeueing and self.queued_out and self.bytes_requested < 0:
            self.requeueing = True
            q = self.queued_out.keys()
            shuffle(q)
            self.queued_out = {}
            for d in q:
                d._request_more()

            self.requeueing = False
        if -self.bytes_requested > 5 * self.download_rate:
            self.bytes_requested = -5 * self.download_rate
        ql = max(int(-self.bytes_requested / self.chunksize), 0)
        return ql

    def chunk_requested(self, size):
        self.bytes_requested += size

    external_data_received = chunk_requested

    def make_download(self, connection):
        ip = connection.get_ip()
        if DEBUG:
            print >> sys.stderr, 'Downloader::make_download: ip', ip
        if self.perip.has_key(ip):
            perip = self.perip[ip]
        else:
            perip = self.perip.setdefault(ip, PerIPStats(ip))
        perip.peerid = connection.get_readable_id()
        perip.numconnections += 1
        d = SingleDownload(self, connection)
        perip.lastdownload = d
        self.downloads.append(d)
        return d

    def reset_have(self):
        if DEBUG:
            print >> sys.stderr, 'Downloader::reset_have: !!!!!!!!!!!!! DISABLED !!!!!!!!!!!!!!!!!!!!'

    def check_interests(self):
        for d in self.downloads:
            d._check_interests()

    def piece_flunked(self, index):
        if self.paused:
            return
        if self.endgamemode:
            if self.downloads:
                while self.storage.do_I_have_requests(index):
                    request = self.storage.new_request(index)
                    if request is None:
                        break
                    nb, nl = request
                    self.all_requests.append((index, nb, nl))

                for d in self.downloads:
                    d.fix_download_endgame()

                return
            self._reset_endgame()
            return
        ds = [ d for d in self.downloads if not d.choked ]
        shuffle(ds)
        for d in ds:
            d._request_more()

        ds = [ d for d in self.downloads if not d.interested and d.have[index] ]
        for d in ds:
            d.example_interest = index
            d.send_interested()

    def has_downloaders(self):
        return len(self.downloads)

    def lost_peer(self, download):
        ip = download.ip
        self.perip[ip].numconnections -= 1
        if self.perip[ip].lastdownload == download:
            self.perip[ip].lastdownload = None
        self.downloads.remove(download)
        if self.endgamemode and not self.downloads:
            self._reset_endgame()

    def _reset_endgame(self):
        if DEBUG:
            print >> sys.stderr, 'Downloader: _reset_endgame'
        self.storage.reset_endgame(self.all_requests)
        self.endgamemode = False
        self.all_requests = []
        self.endgame_queued_pieces = []

    def add_disconnected_seed(self, id):
        self.disconnectedseeds[id] = clock()

    def num_disconnected_seeds(self):
        expired = []
        for id, t in self.disconnectedseeds.items():
            if clock() - t > EXPIRE_TIME:
                expired.append(id)

        for id in expired:
            del self.disconnectedseeds[id]

        return len(self.disconnectedseeds)

    def _check_kicks_ok(self):
        if len(self.gotbaddata) > 10:
            self.kickbans_ok = False
            self.kickbans_halted = True
        return self.kickbans_ok and len(self.downloads) > 2

    def try_kick(self, download):
        log('downloader::try_kick: ip', download.ip)
        if self._check_kicks_ok():
            download.guard.download = None
            ip = download.ip
            id = download.connection.get_readable_id()
            self.kicked[ip] = id
            self.perip[ip].peerid = id
            self.kickfunc(download.connection)

    def try_ban(self, ip):
        log('downloader::try_ban: ip', ip)
        if self._check_kicks_ok():
            self.banfunc(ip)
            self.banned[ip] = self.perip[ip].peerid
            if self.kicked.has_key(ip):
                del self.kicked[ip]

    def set_super_seed(self):
        self.super_seeding = True

    def check_complete(self, index):
        if self.endgamemode and not self.all_requests:
            self.endgamemode = False
        if self.endgame_queued_pieces and not self.endgamemode:
            self.requeue_piece_download()
        if self.picker.am_I_complete():
            for download in self.downloads:
                if download.have.complete():
                    download.connection.send_have(index)
                    self.add_disconnected_seed(download.connection.get_readable_id())
                    download.connection.close()

            return True
        return False

    def too_many_partials(self):
        return len(self.storage.dirty) > len(self.downloads) / 2

    def cancel_requests(self, requests, allowrerequest = True):
        slowpieces = [ piece_id for piece_id, _, _ in requests ]
        if DEBUG:
            log('downloader::cancel_requests: endgamemode', self.endgamemode, 'allowrerequest', allowrerequest, 'requests', requests)
        if self.endgamemode:
            if self.endgame_queued_pieces:
                for piece_id, _, _ in requests:
                    if not self.storage.do_I_have(piece_id):
                        try:
                            self.endgame_queued_pieces.remove(piece_id)
                        except:
                            pass

            if not allowrerequest:
                self.all_requests = [ request for request in self.all_requests if request not in requests ]
                if DEBUG2:
                    log('downloader::cancel_requests: update all_requests, count:', len(self.all_requests))
        for download in self.downloads:
            hit = False
            for request in download.active_requests:
                if request in requests:
                    hit = True
                    if DEBUG2:
                        log('downloader:cancel_requests: canceling', request, 'on', download.ip, 'endgamemode', self.endgamemode)
                    download.connection.send_cancel(*request)
                    if not self.endgamemode:
                        self.storage.request_lost(*request)

            if hit:
                download.bad_performance_counter += 1
                if DEBUG:
                    log('downloader:cancel_requests: increase bad_performance_counter:', download.bad_performance_counter)
                download.active_requests = [ request for request in download.active_requests if request not in requests ]
                if allowrerequest:
                    download._request_more()
                elif download.bad_performance_counter < 5:
                    download._request_more(slowpieces=slowpieces)
                elif download.bad_performance_counter < 10:
                    self.try_kick(download)
                else:
                    self.try_ban(download.ip)
            if not self.endgamemode and download.choked:
                download._check_interests()

    def cancel_piece_download(self, pieces, allowrerequest = True, include_pieces = False):
        if DEBUG:
            log('downloader::cancel_piece_download: pieces', pieces, 'allowrerequest', allowrerequest, 'include_pieces', include_pieces, 'endgamemode', self.endgamemode, 'thread', currentThread().name)
        if self.endgamemode:
            if self.endgame_queued_pieces:
                if include_pieces:
                    try:
                        self.endgame_queued_pieces = [ p for p in self.endgame_queued_pieces if p in pieces ]
                    except:
                        pass

                else:
                    for piece in pieces:
                        try:
                            self.endgame_queued_pieces.remove(piece)
                        except:
                            pass

            if allowrerequest:
                for index, nb, nl in self.all_requests:
                    if include_pieces:
                        cancel = index not in pieces
                    else:
                        cancel = index in pieces
                    if cancel:
                        self.storage.request_lost(index, nb, nl)

            else:
                new_all_requests = []
                for index, nb, nl in self.all_requests:
                    if index in pieces:
                        self.storage.request_lost(index, nb, nl)
                    else:
                        new_all_requests.append((index, nb, nl))

                self.all_requests = new_all_requests
                if DEBUG:
                    print >> sys.stderr, 'Downloader: cancel_piece_download: all_requests', len(self.all_requests), 'remaining'
        for d in self.downloads:
            hit = False
            for index, nb, nl in d.active_requests:
                if include_pieces:
                    cancel = index not in pieces
                else:
                    cancel = index in pieces
                if cancel:
                    if DEBUG:
                        log('downloader::cancel_piece_download: piece:', index, nb, nl)
                    hit = True
                    d.connection.send_cancel(index, nb, nl)
                    if not self.endgamemode:
                        self.storage.request_lost(index, nb, nl)

            if hit:
                if include_pieces:
                    d.active_requests = [ r for r in d.active_requests if r[0] in pieces ]
                else:
                    d.active_requests = [ r for r in d.active_requests if r[0] not in pieces ]
                if not allowrerequest:
                    d._request_more(slowpieces=pieces)
                else:
                    d._request_more()
            if not self.endgamemode and d.choked:
                d._check_interests()

    def requeue_piece_download(self, pieces = []):
        if self.endgame_queued_pieces:
            for piece in pieces:
                if piece not in self.endgame_queued_pieces:
                    self.endgame_queued_pieces.append(piece)

            pieces = self.endgame_queued_pieces
        if self.endgamemode:
            if self.all_requests:
                self.endgame_queued_pieces = pieces
                return
            self.endgamemode = False
            self.endgame_queued_pieces = None
        ds = [ d for d in self.downloads ]
        shuffle(ds)
        for d in ds:
            if d.choked:
                d._check_interests()
            else:
                d._request_more()

    def start_endgame(self):
        self.endgamemode = True
        for d in self.downloads:
            if d.active_requests:
                pass
            for request in d.active_requests:
                self.all_requests.append(request)

        for d in self.downloads:
            d.fix_download_endgame()

        if DEBUG:
            print >> sys.stderr, 'Downloader: start_endgame: we have', len(self.all_requests), 'requests remaining'

    def pause(self, flag):
        self.paused = flag
        if flag:
            for d in self.downloads:
                for index, begin, length in d.active_requests:
                    d.connection.send_cancel(index, begin, length)

                d._letgo()
                d.send_not_interested()

            if self.endgamemode:
                self._reset_endgame()
        else:
            shuffle(self.downloads)
            for d in self.downloads:
                d._check_interests()
                if d.interested and not d.choked:
                    d._request_more()

    def live_invalidate(self, piece, mevirgin = False):
        if DEBUG:
            log('downloader::live_invalidate: piece', piece)
        for d in self.downloads:
            d.connection.send_invalidate(piece)

        if not mevirgin:
            self.picker.invalidate_piece(piece)
            self.storage.live_invalidate(piece)
        if DEBUG:
            log('downloader::live_invalidate: storage.have', debug_format_have(self.storage.have))
            log('downloader::live_invalidate: picker.has', debug_format_have(self.picker.has, False))

    def live_invalidate_ranges(self, toinvalidateranges, toinvalidateset):
        if len(toinvalidateranges) == 1:
            s, e = toinvalidateranges[0]
            emptyrange = [ False for piece in xrange(s, e + 1) ]
            for d in self.downloads:
                newhave = d.have[0:s] + emptyrange + d.have[e + 1:]
                d.have = Bitfield(length=len(newhave), fromarray=newhave)

        else:
            s1, e1 = toinvalidateranges[0]
            s2, e2 = toinvalidateranges[1]
            emptyrange1 = [ False for piece in xrange(s1, e1 + 1) ]
            emptyrange2 = [ False for piece in xrange(s2, e2 + 1) ]
            for d in self.downloads:
                newhave = emptyrange1 + d.have[e1 + 1:s2] + emptyrange2
                d.have = Bitfield(length=len(newhave), fromarray=newhave)

    def aggregate_and_send_haves(self):
        if self.picker.helper:
            if DEBUG:
                print >> sys.stderr, 'Downloader: aggregate_and_send_haves: helper None or helper conn'
            haves_vector = [None] * len(self.downloads)
            for i in range(0, len(self.downloads)):
                haves_vector[i] = self.downloads[i].have

            aggregated_haves = Bitfield(self.numpieces)
            for piece in range(0, self.numpieces):
                aggregated_value = False
                for d in range(0, len(self.downloads)):
                    aggregated_value = aggregated_value or haves_vector[d][piece]

                aggregated_haves[piece] = aggregated_value

            self.picker.helper.send_proxy_have(aggregated_haves)
