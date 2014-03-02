#Embedded file name: ACEStream\Core\Video\VideoOnDemand.pyo
import sys
import random
import ctypes
import binascii
import collections
import os
import base64
import os, sys, time
import re
from base64 import b64encode
from math import ceil
from threading import Event, Condition, currentThread, Lock
from traceback import print_exc, print_stack
from tempfile import mkstemp
from ACEStream.GlobalConfig import globalConfig
from ACEStream.Core.BitTornado.CurrentRateMeasure import Measure
from ACEStream.Core.Video.MovieTransport import MovieTransport, MovieTransportStreamWrapper
from ACEStream.Core.simpledefs import *
from ACEStream.Core.osutils import *
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.Video.LiveSourceAuth import ECDSAAuthenticator, RSAAuthenticator, AuthStreamWrapper, VariableReadAuthStreamWrapper
DEBUG = False
DEBUG_EXTENDED = False
DEBUG_HOOKIN = False
DEBUG_BUFFERING = False
DEBUG_SKIP_METADATA = False
DEBUG_READ_PIECE = False
REPORT_PIECES = False
DO_MEDIAINFO_ANALYSIS = True
MEDIAINFO_NOT_FINISHED = 0
MEDIAINFO_SUCCESS = 1
MEDIAINFO_FAILED = 2
DEFAULT_READ_SIZE = 1048576
OUTBUF_MIN_SIZE_ENABLED = False
OUTBUF_MIN_SIZE_COEFF = 2
DEBUG_NO_PREBUFFERING = False
SKIP_UNDERRUN_TIMEOUT = 10.0
SPEED_GAIN_TIMEOUT = 10.0
MIN_HTTP_PROXY_SPEED_START = 0.7
MIN_HTTP_PROXY_SPEED_FAIL = 0.7

class PieceStats:

    def __init__(self):
        self.pieces = {}
        self.completed = {}

    def set(self, piece, stat, value, firstonly = True):
        if piece not in self.pieces:
            self.pieces[piece] = {}
        try:
            if firstonly and stat in self.pieces[piece]:
                return
            self.pieces[piece][stat] = value
        except KeyError:
            pass
        except:
            print exc()

    def complete(self, piece):
        self.completed[piece] = 1

    def reset(self):
        for x in self.completed:
            self.pieces.pop(x, 0)

        self.completed = {}

    def pop_completed(self):
        completed = {}
        for x in self.completed.keys():
            completed[x] = self.pieces.pop(x, {})

        self.completed = {}
        return completed


class MovieOnDemandTransporter(MovieTransport):
    PREBUF_SEC_LIVE = 10.0
    PREBUF_SEC_VOD = 10.0
    REFILL_INTERVAL = 0.1
    VLC_BUFFER_SIZE = 0
    PIECE_DUE_SKEW = 0.1 + VLC_BUFFER_SIZE
    MINPLAYBACKRATE = 32 * 1024
    PREBUF_REHOOKIN_SECS = 5.0
    MAX_POP_TIME = 10

    def __init__(self, bt1download, videostatus, videoinfo, videoanalyserpath, vodeventfunc, httpsupport = None):
        from ACEStream.Core.Session import Session
        session = Session.get_instance()
        self.app_mode = globalConfig.get_mode()
        self.MAX_POP_TIME = globalConfig.get_value('vod_live_max_pop_time', 10)
        self.b64_infohash = b64encode(bt1download.infohash)
        self.log_prefix = 'vod::' + binascii.hexlify(bt1download.infohash) + ':'
        metainfo = bt1download.response
        self.wait_sufficient_speed = bt1download.config.get('wait_sufficient_speed', False)
        self.enable_http_proxy = bt1download.config.get('enable_http_proxy', True)
        self.player_buffer_time = bt1download.config.get('player_buffer_time', 5)
        self.live_buffer_time = bt1download.config.get('live_buffer_time', 10)
        self.p2p_current_rate = None
        self.mediainfo = None
        self.mediainfo_next_piece = None
        self.mediainfo_pos = 0
        self.mediainfo_finished = False
        self.mediainfo_status = MEDIAINFO_NOT_FINISHED
        self.mediainfo_lock = Lock()
        if bt1download.has_extra_files:
            extra = '1'
        else:
            extra = '0'
        if videoinfo['index'] == -1:
            index = 0
        else:
            index = videoinfo['index']
        self.report_media_id = self.b64_infohash + '|' + extra + '|' + str(index) + '|' + str(time.time()) + '.' + str(random.randint(0, 100000))
        if DEBUG:
            log('vod::__init__: b64_infohash', self.b64_infohash, 'report_media_id', self.report_media_id)
        self.report_playback_events = {'vod-time-total': 0,
         'prebuf_pieces': [],
         'vod-report-prebuf-pieces': not videostatus.got_prebuf_pieces,
         'vod-report-duration': not videostatus.bitrate_set}

        def set_nat(nat):
            pass

        self._complete = False
        self.filestream = None
        self.videoinfo = videoinfo
        self.bt1download = bt1download
        self.piecepicker = bt1download.picker
        self.rawserver = bt1download.rawserver
        self.storagewrapper = bt1download.storagewrapper
        self.fileselector = bt1download.fileselector
        self.vodeventfunc = vodeventfunc
        videostatus.prebuffering = True
        self.videostatus = vs = videostatus
        self.playback_started = False
        self.start_playback = None
        self.http_support = httpsupport
        if self.http_support is not None:
            self.http_support.set_voddownload(self)
        self.traker_peers_report = None
        self.sustainable_counter = sys.maxint
        self.paused_pos = None
        self.refill_buffer_counter = 0
        self.overall_rate = Measure(10)
        self.high_range_rate = Measure(2)
        self.has = self.piecepicker.has
        self.pieces_in_buffer = self.videostatus.numhave
        self.data_ready = Condition()
        self.proxy_cond = Condition()
        self.proxy_buf_observers = []
        self.outbuf_minsize = None
        self.delay_p2p_start = False
        self.wait_proxy_flag = False
        self.outbuf_history = []
        if not vs.bitrate_set or not vs.got_prebuf_pieces:
            metadata = session.get_ts_metadata_from_db(self.bt1download.infohash)
            if DEBUG:
                log('vod::__init__: no initial metadata, get from session: metadata', metadata)
            if metadata is not None:
                self.got_metadata(metadata, update_prebuffering=False)
        elif DEBUG:
            log('vod::__init__: got initial metadata')
        self.got_http_support()
        if vs.bitrate_set:
            self.doing_mediainfo_analysis = False
        elif vs.live_streaming:
            self.doing_mediainfo_analysis = False
        else:
            self.doing_mediainfo_analysis = DO_MEDIAINFO_ANALYSIS
        if vs.live_streaming:
            piecesneeded = vs.time_to_pieces(self.live_buffer_time)
        else:
            piecesneeded = self.videostatus.prebuf_pieces
        if vs.wraparound:
            self.max_prebuf_packets = min(int(vs.wraparound_delta * 0.75), piecesneeded)
            vs.live_buffer_pieces = self.max_prebuf_packets
        else:
            self.max_prebuf_packets = min(vs.movie_numpieces, piecesneeded)
        if DEBUG:
            log('vod::__init__: want', self.max_prebuf_packets, 'pieces for prebuffering')
        self.nreceived = 0
        if DEBUG:
            log('vod::__init__: setting MIME type to', self.videoinfo['mimetype'])
        self.set_mimetype(self.videoinfo['mimetype'])
        self.stat_playedpieces = 0
        self.stat_latepieces = 0
        self.stat_droppedpieces = 0
        self.stat_stalltime = 0.0
        self.stat_prebuffertime = 0.0
        self.stat_pieces = PieceStats()
        self.stream_start = True
        self.stream_pos = 0
        self.curpiece = ''
        self.curpiece_pos = 0
        self.outbuf = []
        self.stat_outbuf = []
        self.proxy_buf = {}
        self.stat_proxy_buf = {}
        self.outbuflen = None
        self.outbufpos = None
        self.last_start = None
        self.last_resume = None
        self.skip_underrun_timeout = None
        self.last_pop = None
        self.reset_bitrate_prediction()
        self.lasttime = 0
        self.prebufprogress = 0.0
        self.prebufstart = time.time()
        self.playable = False
        self.usernotified = False
        if vs.live_streaming:
            if vs.authparams is not None and vs.authparams['authmethod'] == LIVE_AUTHMETHOD_ECDSA:
                self.authenticator = ECDSAAuthenticator(vs.first_piecelen, vs.movie_numpieces, pubkeypem=vs.authparams['pubkey'])
                vs.sigsize = vs.piecelen - self.authenticator.get_content_blocksize()
            elif vs.authparams is not None and vs.authparams['authmethod'] == LIVE_AUTHMETHOD_RSA:
                self.authenticator = RSAAuthenticator(vs.first_piecelen, vs.movie_numpieces, pubkeypem=vs.authparams['pubkey'], max_age=vs.pieces_to_time(vs.wraparound_delta * 2))
                vs.sigsize = vs.piecelen - self.authenticator.get_content_blocksize()
            else:
                self.authenticator = None
                vs.sigsize = 0
        else:
            self.authenticator = None
        self.video_refillbuf_rawtask()
        self.piecepicker.set_transporter(self)
        if vs.live_streaming:
            self.live_streaming_timer()
        else:
            self.complete_from_persistent_state(self.storagewrapper.get_pieces_on_disk_at_startup())
        self.update_prebuffering()
        if self.app_mode == 'node':
            self.videostatus.pausable = False
            import threading

            class FakeReader(threading.Thread):

                def __init__(self, movie):
                    threading.Thread.__init__(self)
                    self.movie = movie

                def run(self):
                    self.movie.start()
                    while not self.movie.done():
                        self.movie.read()

            t = FakeReader(self)
            t.start()

    def calc_live_startpos(self, prebufsize = 2, have = False):
        vs = self.videostatus
        curpos = vs.get_live_startpos()
        if DEBUG_HOOKIN:
            log('vod::calc_live_startpos: have', have, 'curpos', curpos)
        if have:
            numseeds = 0
            numhaves = self.piecepicker.has
            totalhaves = self.piecepicker.numgot
            sourcehave = None
            threshold = 1
        else:
            numseeds = self.piecepicker.seeds_connected
            numhaves = self.piecepicker.numhaves
            totalhaves = self.piecepicker.totalcount
            sourcehave = self.piecepicker.get_live_source_have(find_source=self.app_mode == 'node')
            if DEBUG_HOOKIN:
                if sourcehave is not None:
                    if DEBUG_HOOKIN:
                        log('vod::calc_live_offset: source have numtrue', sourcehave.get_numtrue())
                    if sourcehave.get_numtrue() < 10:
                        if DEBUG_HOOKIN:
                            log('vod::calc_live_offset: too few pieces on the source, discard')
                        sourcehave = None
            if self.app_mode == 'node' and sourcehave is None:
                if DEBUG_HOOKIN:
                    log('vod::calc_live_offset: no connection to the source, wait')
                return False
            numconns = self.piecepicker.num_nonempty_neighbours()
            if self.app_mode != 'node' and sourcehave is not None and numconns >= 30:
                if DEBUG_HOOKIN:
                    log('vod::calc_live_offset: got some peers, use vote system: numconns', numconns)
                sourcehave = None
            if sourcehave is None:
                threshold = max(2, numconns / 2)
                if DEBUG_HOOKIN:
                    log('vod::calc_live_offset: vote hook: numconns', numconns, 'threshold', threshold)
            else:
                if DEBUG_HOOKIN:
                    log('vod::calc_live_offset: hook on source')
                threshold = 1
        FUDGE = prebufsize
        if numseeds == 0 and totalhaves == 0:
            if DEBUG_HOOKIN:
                log('vod::calc_live_offset: no pieces')
            return False
        bpiece = vs.first_piece
        epiece = vs.last_piece
        if DEBUG_HOOKIN:
            log('vod::calc_live_offset: bpiece', bpiece, 'epiece', epiece)
        if not vs.wraparound:
            if numseeds > 0 or numhaves[epiece] > 0:
                if DEBUG_HOOKIN:
                    log('vod::calc_live_offset: vod mode')
                vs.set_live_startpos(0)
                return True
        maxnum = None
        minnum = None
        if sourcehave is None:
            inspecthave = numhaves
        else:
            inspecthave = sourcehave
        for i in xrange(epiece, bpiece - 1, -1):
            have_me = have_source = have_neighbours = False
            if self.piecepicker.has[i]:
                have_me = True
            elif sourcehave is not None and sourcehave[i]:
                have_source = True
            elif inspecthave[i] >= threshold:
                have_neighbours = True
            if have_me or have_source or have_neighbours:
                maxnum = i
                if DEBUG_HOOKIN:
                    if have_neighbours:
                        log('vod::calc_live_startpos: chosing max piece %d as it is owned by %d>=%d neighbours (prewrap)' % (i, inspecthave[i], threshold))
                    if have_source:
                        log('vod:calc_live_startpos: chosing max piece %d as it is owned by the source (prewrap)' % i)
                    if have_me:
                        log('vod:calc_live_startpos: chosing max piece %d as it is owned by me (prewrap)' % i)
                break

        for i in xrange(bpiece, epiece - 1):
            have_me = have_source = have_neighbours = False
            if self.piecepicker.has[i]:
                have_me = True
            elif sourcehave is not None and sourcehave[i]:
                have_source = True
            elif inspecthave[i] >= threshold:
                have_neighbours = True
            if have_me or have_source or have_neighbours:
                minnum = i
                if DEBUG_HOOKIN:
                    if have_neighbours:
                        log('vod::calc_live_startpos: chosing min piece %d as it is owned by %d>=%d neighbours (prewrap)' % (i, inspecthave[i], threshold))
                    if have_source:
                        log('vod:calc_live_startpos: chosing min piece %d as it is owned by the source (prewrap)' % i)
                    if have_me:
                        log('vod:calc_live_startpos: chosing min piece %d as it is owned by me (prewrap)' % i)
                break

        if maxnum is None:
            if DEBUG_HOOKIN:
                log('vod::calc_live_startpos: failed to find quorum for any piece')
            return False
        if minnum is None:
            minnum = vs.normalize(maxnum - vs.wraparound_delta)
            if DEBUG_HOOKIN:
                log('vod::calc_live_startpos: failed to find min piece, use wraparound assumption: minnum', minnum, 'wraparound_delta', vs.wraparound_delta)
        if vs.wraparound and maxnum > epiece - vs.wraparound_delta:
            delta_left = vs.wraparound_delta - (epiece - maxnum)
            for i in xrange(vs.first_piece + delta_left - 1, vs.first_piece - 1, -1):
                have_me = have_source = have_neighbours = False
                if self.piecepicker.has[i]:
                    have_me = True
                elif sourcehave is not None and sourcehave[i]:
                    have_source = True
                elif inspecthave[i] >= threshold:
                    have_neighbours = True
                if have_me or have_source or have_neighbours:
                    maxnum = i
                    if DEBUG_HOOKIN:
                        if have_neighbours:
                            log('vod::calc_live_startpos: chosing max piece %d as it is owned by %d>=%d neighbours (wrap)' % (i, inspecthave[i], threshold))
                        if have_source:
                            log('vod:calc_live_startpos: chosing max piece %d as it is owned by the source (wrap)' % i)
                        if have_me:
                            log('vod:calc_live_startpos: chosing max piece %d as it is owned by me (wrap)' % i)
                    break

        if vs.wraparound and minnum < bpiece + vs.wraparound_delta:
            delta_left = vs.wraparound_delta - (minnum - bpiece)
            for i in xrange(vs.last_piece - delta_left + 1, vs.last_piece + 1):
                have_me = have_source = have_neighbours = False
                if self.piecepicker.has[i]:
                    have_me = True
                elif sourcehave is not None and sourcehave[i]:
                    have_source = True
                elif inspecthave[i] >= threshold:
                    have_neighbours = True
                if have_me or have_source or have_neighbours:
                    minnum = i
                    if DEBUG_HOOKIN:
                        if have_neighbours:
                            log('vod::calc_live_startpos: chosing min piece %d as it is owned by %d>=%d neighbours (wrap)' % (i, inspecthave[i], threshold))
                        if have_source:
                            log('vod:calc_live_startpos: chosing min piece %d as it is owned by the source (wrap)' % i)
                        if have_me:
                            log('vod:calc_live_startpos: chosing min piece %d as it is owned by me (wrap)' % i)
                    break

        if DEBUG_HOOKIN:
            log('vod::calc_live_offset: window size: min', minnum, 'max', maxnum)
        if not have:
            vs.live_first_piece = minnum
            vs.live_last_piece = maxnum
            if vs.dist_range(minnum, maxnum) > vs.live_hook_left_offset_min:
                vs.live_first_piece_with_offset = vs.normalize(minnum + vs.live_hook_left_offset_min)
            else:
                vs.live_first_piece_with_offset = minnum
            if self.authenticator is not None and self.authenticator.startts is not None:
                vs.live_last_ts = long(self.authenticator.startts)
            else:
                vs.live_last_ts = long(time.time())
            time_offset = vs.pieces_to_time(vs.dist_range(minnum, maxnum))
            vs.live_first_ts = vs.live_last_ts - time_offset
            if DEBUG_HOOKIN:
                log('vod::calc_live_startpos: time_offset', time_offset, 'last_ts', vs.live_last_ts, 'first_ts', vs.live_first_ts)
        rehook = True
        oldstartpos = vs.get_live_startpos()
        if oldstartpos is None:
            hook_type = 'right'
            fudge_right = self.max_prebuf_packets
            hook_at = vs.normalize(maxnum - fudge_right)
        else:
            if have:
                fudge_left = 0
            else:
                fudge_left = vs.live_hook_left_offset
            fudge_right = 0
            if vs.dist_range(minnum, maxnum) <= vs.live_hook_left_offset_min:
                range_from = minnum
            else:
                range_from = minnum + vs.live_hook_left_offset_min
            range_to = maxnum + 2
            if not vs.in_range(range_from, range_to, oldstartpos):
                dist_min = vs.dist_range(oldstartpos, range_from)
                dist_max = vs.dist_range(maxnum, oldstartpos)
                if dist_min < dist_max:
                    hook_type = 'left'
                    hook_at = vs.normalize(minnum + fudge_left)
                else:
                    hook_type = 'right'
                    hook_at = vs.normalize(maxnum - fudge_right)
                if DEBUG_HOOKIN:
                    log('vod::calc_live_startpos: rehook: hook_type', hook_type, 'hook_at', hook_at, 'oldstarpos', oldstartpos, 'min', minnum, 'max', maxnum, 'fudge_left', fudge_left, 'fudge_right', fudge_right, 'range_from', range_from, 'range_to', range_to, 'dist_min', dist_min, 'dist_max', dist_max)
                if hook_type == 'right' and dist_max < 10:
                    if DEBUG_HOOKIN:
                        log('vod::calc_live_startpos: keep old startpos: startpos', oldstartpos, 'min', minnum, 'max', maxnum, 'dist_max', dist_max)
                    rehook = False
                elif hook_type == 'left':
                    vs.live_hook_left_offset += vs.live_hook_left_offset_step
                    if vs.live_hook_left_offset > vs.live_hook_left_offset_max:
                        vs.live_hook_left_offset = vs.live_hook_left_offset_max
                    if DEBUG_HOOKIN:
                        log('vod::calc_live_startpos: increase left hook offset:', vs.live_hook_left_offset)
            else:
                if DEBUG_HOOKIN:
                    log('vod::calc_live_startpos: already have startpos: startpos', oldstartpos, 'min', minnum, 'max', maxnum)
                rehook = False
        if not rehook:
            vs.playback_pos_is_live = vs.in_range(vs.normalize(maxnum - self.max_prebuf_packets * 1.5), vs.normalize(maxnum + 2), oldstartpos)
            if DEBUG_HOOKIN:
                log('vod::calc_live_startpos: is_live', vs.playback_pos_is_live, 'max', maxnum, 'prebuf', self.max_prebuf_packets, 'range', maxnum - self.max_prebuf_packets * 1.5, 'oldstartpos', oldstartpos)
            return True
        if vs.playback_pos_is_live is None:
            vs.playback_pos_is_live = True
        if DEBUG_HOOKIN:
            hook_at_old = hook_at
        while not inspecthave[hook_at]:
            if hook_type == 'left':
                hook_at = vs.normalize(hook_at - 1)
            else:
                hook_at = vs.normalize(hook_at + 1)

        if DEBUG_HOOKIN and hook_at != hook_at_old:
            log('vod::calc_live_offset: correct hook point basing on have: hook_at_old', hook_at_old, 'hook_at', hook_at)
        if self.app_mode == 'node':
            log('vod: hook at piece', hook_at)
        elif DEBUG:
            print >> sys.stderr, 'vod: === HOOKIN piece', hook_at, 'have', have
        invalidate_range = vs.set_live_startpos(hook_at)
        if invalidate_range is not None:
            if DEBUG:
                log('vod::calc_live_offset: invalidate piece range')
            for i in invalidate_range:
                self.live_invalidate_piece(vs.live_piece_to_invalidate(i))

        if vs.playing:
            self.start(0, force=True)
        return True

    def live_seek(self, pos):
        vs = self.videostatus
        r = vs.live_get_window_range()
        if r is None:
            if DEBUG:
                log('vod::live_seek: window range is not set')
            return False
        if pos == -1:
            pos = r[1] - self.max_prebuf_packets
            if DEBUG:
                log('vod::live_seek: seek to live: pos', pos, 'max', r[1], 'max_prebuf_packets', self.max_prebuf_packets)
        if not vs.in_range(r[0], r[1], pos):
            if DEBUG:
                log('vod::live_seek: seek pos out of window: range', r, 'pos', pos)
            return False
        if DEBUG:
            log('vod::live_seek: pos', pos, 'playing', vs.playing)
        vs.set_live_startpos(pos)
        if vs.playing:
            self.start(0, force=True, network_calling=False)
        return True

    def live_streaming_timer(self):
        nextt = 1
        try:
            self.calc_live_startpos(self.max_prebuf_packets, False)
        except:
            log_exc()
        finally:
            self.rawserver.add_task(self.live_streaming_timer, nextt)

    def read_from_buffer(self, pos, numbytes = None):
        vs = self.videostatus
        piece_index, piece_offset = self.piecepos_from_bytepos(vs, pos)
        if DEBUG:
            log('vod::read_from_buffer: pos', pos, 'numbytes', numbytes, 'piece_index', piece_index, 'piece_offset', piece_offset)
        data = ''
        for i in xrange(piece_index, vs.last_piece + 1):
            piece = self.get_piece(i)
            if piece is None:
                break
            if piece_offset > 0:
                chunk = piece[piece_offset:]
                piece_offset = 0
            else:
                chunk = piece
            data += chunk
            pos += len(chunk)
            if DEBUG:
                log('vod::read_from_buffer: got whole piece: index', i, 'chunk_len', len(piece), 'data_len', len(data), 'pos', pos)
            if numbytes is not None and len(data) >= numbytes:
                if DEBUG:
                    log('vod::read_from_buffer: got enough data: numbytes', numbytes, 'data_len', len(data))
                return data

        self.proxy_cond.acquire()
        try:
            for bstart, bdata in self.proxy_buf.iteritems():
                bend = bstart + len(bdata) - 1
                if bstart <= pos <= bend:
                    offset_from = pos - bstart
                    if numbytes is None:
                        chunk = bdata[offset_from:]
                        data += chunk
                        if DEBUG:
                            log('vod::read_from_buffer: got data from proxy buffer, read whole data: pos', pos, 'bstart', bstart, 'bend', bend, 'chunk:[%d:]:%d' % (offset_from, len(chunk)), 'data_len', len(data))
                    else:
                        offset_to = offset_from + numbytes - len(data)
                        chunk = bdata[offset_from:offset_to]
                        data += chunk
                        if DEBUG:
                            log('vod::read_from_buffer: got data from proxy buffer, read data slice: pos', pos, 'bstart', bstart, 'bend', bend, 'numbytes', numbytes, 'chunk:[%d:%d]:%d' % (offset_from, offset_to, len(chunk)), 'data_len', len(data))
                    break

            return data
        finally:
            self.proxy_cond.release()

    def mediainfo_analyze(self):
        self.mediainfo_lock.acquire()
        try:
            if self.mediainfo_finished:
                return self.mediainfo_status
            return self._mediainfo_analyze()
        except:
            if DEBUG:
                log('vod::mediainfo_analyze: failed - unexcpected exception')
            log_exc()
            self.mediainfo_finished = True
            self.mediainfo_status = MEDIAINFO_FAILED
            return self.mediainfo_status
        finally:
            self.mediainfo_lock.release()

    def _mediainfo_analyze(self):

        def notify(pos):
            if DEBUG:
                log('vod::mediainfo_analyze: notification from proxy buf: pos', pos)
            self.rawserver.add_task(self.update_prebuffering, 0.1)

        vs = self.videostatus
        if self.mediainfo is None:
            try:
                from ACEStream.Core.Video.MediaInfo import MediaInfo
                self.mediainfo = MediaInfo()
                self.mediainfo_next_piece = vs.first_piece
                self.mediainfo_pos = 0
                self.videostatus.add_missing_piece(self.mediainfo_next_piece, True)
                self.report_playback_events['prebuf_pieces'].append(self.mediainfo_next_piece)
                self.mediainfo.Open_Buffer_Init(vs.selected_movie['size'])
                if DEBUG:
                    log('vod::mediainfo_analyze: init mediainfo: next_piece', self.mediainfo_next_piece, 'pos', self.mediainfo_pos)
            except:
                if DEBUG:
                    log('vod::mediainfo_analyze: failed to init mediainfo')
                log_exc()
                self.mediainfo_finished = True
                self.mediainfo_status = MEDIAINFO_FAILED
                return self.mediainfo_status

        seek = False
        seek_requests = 0
        max_seek_requests = 25
        mediainfo_finished = False
        total_data_length = 0
        self.mediainfo_pos = 0
        self.mediainfo.Open_Buffer_Init(vs.selected_movie['size'])
        while True:
            data = self.read_from_buffer(self.mediainfo_pos, vs.piecelen)
            if not data:
                break
            data_length = len(data)
            total_data_length += data_length
            ret = self.mediainfo.Open_Buffer_Continue(data, data_length)
            if DEBUG:
                log('vod::mediainfo_analyze: feed data to mediainfo: pos', self.mediainfo_pos, 'data_len', data_length, 'ret', ret)
            if ret & 8:
                if DEBUG:
                    log('vod::mediainfo_analyze: got enough info')
                mediainfo_finished = True
                break
            offset = self.mediainfo.Open_Buffer_Continue_GoTo_Get()
            seek = False
            if offset == ctypes.c_uint64(-1).value:
                self.mediainfo_pos += data_length
            else:
                if seek_requests >= max_seek_requests:
                    if DEBUG:
                        log('vod::mediainfo_analyze: max seek requests exceeded: seek_requests', seek_requests, 'max_seek_requests', max_seek_requests)
                    self.mediainfo_finished = True
                    self.mediainfo_status = MEDIAINFO_FAILED
                    return self.mediainfo_status
                seek_requests += 1
                if offset >= vs.selected_movie['size']:
                    if DEBUG:
                        log('vod::mediainfo_analyze: failed - offset request out of range: offset', offset, 'size', vs.selected_movie['size'])
                    self.mediainfo_finished = True
                    self.mediainfo_status = MEDIAINFO_FAILED
                    return self.mediainfo_status
                if offset == self.mediainfo_pos:
                    if DEBUG:
                        log('vod::mediainfo_analyze: loop seek requested, ignore: mediainfo_pos', self.mediainfo_pos, 'offset', offset)
                    self.mediainfo_pos += data_length
                else:
                    seek = True
                    self.mediainfo_pos = offset
                    self.mediainfo.Open_Buffer_Init(vs.selected_movie['size'], offset)
                    if DEBUG:
                        log('vod::mediainfo_analyze: seek request: offset', offset)

        self.mediainfo.Open_Buffer_Finalize()
        if self.mediainfo_pos == 0:
            return MEDIAINFO_NOT_FINISHED
        format = self.mediainfo.Get(0, 0, 'Format')
        if DEBUG:
            log('vod::mediainfo_analyze: format', format)
        if not mediainfo_finished and format in ('BDAV', 'MPEG-TS', 'AVI'):
            duration = ''
        else:
            duration = self.mediainfo.Get(0, 0, 'Duration')
            if len(duration):
                if DEBUG:
                    log('vod::mediainfo_analyze: got general duration', duration)
            else:
                duration = self.mediainfo.Get(1, 0, 'Duration')
                if len(duration):
                    if DEBUG:
                        log('vod::mediainfo_analyze: got video duration', duration)
                else:
                    duration = self.mediainfo.Get(2, 0, 'Duration')
                    if len(duration):
                        if DEBUG:
                            log('vod::mediainfo_analyze: got audio duration', duration)
        if len(duration) == 0:
            if DEBUG:
                log('vod::mediainfo_analyze: failed - empty duration')
            if total_data_length >= vs.selected_movie['size'] * 0.1:
                if DEBUG:
                    log('vod::mediainfo_analyze: do not try to get duration anymore: total_data_length', total_data_length, 'size', vs.selected_movie['size'])
                self.mediainfo_finished = True
                self.mediainfo_status = MEDIAINFO_FAILED
                return self.mediainfo_status
            piece_index, _ = self.piecepos_from_bytepos(vs, self.mediainfo_pos)
            if piece_index != self.mediainfo_next_piece:
                self.mediainfo_next_piece = piece_index
                if DEBUG:
                    log('vod::mediainfo_analyze: add missing piece: pos', self.mediainfo_pos, 'next_piece', self.mediainfo_next_piece)
                self.videostatus.add_missing_piece(self.mediainfo_next_piece, True)
                if self.report_playback_events['vod-report-prebuf-pieces']:
                    self.report_playback_events['prebuf_pieces'].append(self.mediainfo_next_piece)
            self.proxy_cond.acquire()
            self.proxy_buf_observers.append((self.mediainfo_pos, notify))
            self.proxy_cond.release()
            if self.http_support is not None:
                if DEBUG:
                    log('vod::mediainfo_analyze: start proxy: pos', self.mediainfo_pos)
                self.start_proxy(pos=self.mediainfo_pos, seek=seek)
            return MEDIAINFO_NOT_FINISHED
        try:
            duration = int(float(duration))
        except:
            log_exc()
            if DEBUG:
                log('vod::mediainfo_analyze: failed - bad duration', duration)
            self.mediainfo_status = MEDIAINFO_FAILED
            self.mediainfo_finished = True
            return self.mediainfo_status

        format_max_bitrate = {'MPEG-4': 3145728,
         'Flash Video': 524288,
         'MPEG-PS': 3145728,
         'BDAV': 10485760,
         'MPEG-TS': 10485760,
         'AVI': 3145728,
         'Matroska': 3145728}
        if format_max_bitrate.has_key(format):
            max_allowed_bitrate = format_max_bitrate[format]
        else:
            max_allowed_bitrate = 10485760
        skip_duration = False
        movie_size = self.videostatus.selected_movie['size']
        bitrate = movie_size / duration * 1000
        if DEBUG:
            log('vod::mediainfo_analyze: check duration: format', format, 'duration', duration, 'bitrate', bitrate, 'max_allowed_bitrate', max_allowed_bitrate)
        if bitrate > max_allowed_bitrate:
            skip_duration = True
            if DEBUG:
                log('vod::mediainfo_analyze: skip duration: format', format, 'duration', duration, 'bitrate', bitrate, 'max_allowed_bitrate', max_allowed_bitrate)
        if not skip_duration:
            self.got_duration(duration / 1000)
        vs.got_prebuf_pieces = True
        self.mediainfo_finished = True
        self.mediainfo_status = MEDIAINFO_SUCCESS
        return self.mediainfo_status

    def _old_mediainfo_analyze(self):
        vs = self.videostatus
        if self.mediainfo is None:
            try:
                from ACEStream.Core.Video.MediaInfo import MediaInfo
                self.mediainfo = MediaInfo()
                self.mediainfo_next_piece = vs.first_piece
                self.videostatus.add_missing_piece(self.mediainfo_next_piece, True)
                self.report_playback_events['prebuf_pieces'].append(self.mediainfo_next_piece)
                self.mediainfo.Open_Buffer_Init(vs.selected_movie['size'])
                log('MEDIAINFO vod::mediainfo_analyze: init mediainfo: next_piece', self.mediainfo_next_piece)
            except:
                log('MEDIAINFO vod::mediainfo_analyze: failed to init mediainfo')
                log_exc()
                self.mediainfo_finished = True
                self.mediainfo_status = MEDIAINFO_FAILED
                return self.mediainfo_status

        while True:
            piece = self.get_piece(self.mediainfo_next_piece)
            if piece is None:
                return MEDIAINFO_NOT_FINISHED
            if self.mediainfo_piece_offset >= len(piece):
                log('MEDIAINFO vod::mediainfo_analyze: failed - piece offset overflow: piece', self.mediainfo_next_piece, 'len', len(piece), 'offset', self.mediainfo_piece_offset)
                self.mediainfo_finished = True
                self.mediainfo_status = MEDIAINFO_FAILED
                return self.mediainfo_status
            ret = self.mediainfo.Open_Buffer_Continue(piece[self.mediainfo_piece_offset:], len(piece) - self.mediainfo_piece_offset)
            log('MEDIAINFO vod::mediainfo_analyze: feed piece to mediainfo: piece', self.mediainfo_next_piece, 'ret', ret)
            if ret & 8:
                log('MEDIAINFO vod::mediainfo_analyze: got enough info')
                break
            offset = self.mediainfo.Open_Buffer_Continue_GoTo_Get()
            if offset == ctypes.c_uint64(-1).value:
                self.mediainfo_next_piece += 1
                self.mediainfo_piece_offset = 0
            else:
                if offset < vs.first_piecelen:
                    self.mediainfo_next_piece = vs.first_piece
                    self.mediainfo_piece_offset = offset
                else:
                    bytepos = offset - vs.first_piecelen
                    self.mediainfo_next_piece = vs.first_piece + bytepos / vs.piecelen + 1
                    self.mediainfo_piece_offset = bytepos % vs.piecelen
                if self.mediainfo_next_piece > vs.last_piece:
                    log('MEDIAINFO vod::mediainfo_analyze: failed - offset request out of range: offset', offset, 'next_piece', self.mediainfo_next_piece, 'last_piece', vs.last_piece)
                    self.mediainfo_finished = True
                    self.mediainfo_status = MEDIAINFO_FAILED
                    return self.mediainfo_status
                self.mediainfo.Open_Buffer_Init(vs.selected_movie['size'], offset)
                log('MEDIAINFO vod::mediainfo_analyze: seek request: offset', offset, 'piece_offset', self.mediainfo_piece_offset, 'size', vs.selected_movie['size'], 'next_piece', self.mediainfo_next_piece)
            log('MEDIAINFO vod::mediainfo_analyze: add missing piece', self.mediainfo_next_piece)
            self.videostatus.add_missing_piece(self.mediainfo_next_piece, True)
            if self.report_playback_events['vod-report-prebuf-pieces']:
                self.report_playback_events['prebuf_pieces'].append(self.mediainfo_next_piece)

        self.mediainfo.Open_Buffer_Finalize()
        duration = self.mediainfo.Get(0, 0, 'Duration')
        if len(duration):
            log('MEDIAINFO vod::mediainfo_analyze: got general duration', duration)
        else:
            duration = self.mediainfo.Get(1, 0, 'Duration')
            if len(duration):
                log('MEDIAINFO vod::mediainfo_analyze: got video duration', duration)
            else:
                duration = self.mediainfo.Get(2, 0, 'Duration')
                if len(duration):
                    log('MEDIAINFO vod::mediainfo_analyze: got audio duration', duration)
        if len(duration) == 0:
            log('MEDIAINFO vod::mediainfo_analyze: failed - empty duration')
            self.mediainfo_status = MEDIAINFO_FAILED
            return self.mediainfo_status
        try:
            self.got_duration(int(duration) / 1000.0)
        except:
            log('MEDIAINFO vod::mediainfo_analyze: failed - bad duration', duration)
            self.mediainfo_status = MEDIAINFO_FAILED
            return self.mediainfo_status

        vs.got_prebuf_pieces = True
        self.mediainfo_finished = True
        self.mediainfo_status = MEDIAINFO_SUCCESS
        return self.mediainfo_status

    def peers_from_tracker_report(self, num_peers):
        if DEBUG:
            log('vod::peers_from_tracker_report: Got from tracker:', num_peers)
        if self.traker_peers_report is None:
            self.traker_peers_report = num_peers
        else:
            self.traker_peers_report += num_peers

    def update_prebuffering(self, received_piece = None):
        vs = self.videostatus
        if DEBUG_NO_PREBUFFERING:
            self.data_ready.acquire()
            vs.prebuffering = False
            self.notify_playable()
            self.data_ready.notify()
            self.data_ready.release()
        if not vs.prebuffering:
            return
        if vs.live_streaming and vs.live_startpos is None:
            return
        if received_piece:
            self.nreceived += 1
        gotall = None
        if self.doing_mediainfo_analysis:
            mi_status = self.mediainfo_analyze()
            if mi_status == MEDIAINFO_NOT_FINISHED:
                gotall = False
            elif mi_status == MEDIAINFO_SUCCESS:
                log('MEDIAINFO vod::update_prebuffering: mediainfo success, stop prebuffering')
                self.doing_mediainfo_analysis = False
                vs.set_prebuf_pieces([])
            elif mi_status == MEDIAINFO_FAILED:
                log("MEDIAINFO vod::update_prebuffering: mediainfo failed, don't analyze anymore")
                self.doing_mediainfo_analysis = False
                gotall = False
        if gotall is not None:
            if DEBUG:
                log('vod::update_prebuffering: wait until mediainfo finishes')
            prebufrange = vs.prebuf_needed_pieces
            missing_pieces = filter(lambda i: not self.have_piece(i), prebufrange)
            self.prebufprogress = float(len(prebufrange) - len(missing_pieces)) / float(len(prebufrange))
        elif vs.live_streaming:
            f = vs.get_live_startpos()
            downrate = self.bt1download.downmeasure.get_rate_noupdate()
            if DEBUG:
                log('vod::update_prebuffering: downrate', downrate)
            if self.have_piece(f) and downrate >= vs.bitrate * 1.3:
                if DEBUG:
                    log('vod::update_prebuffering: enough speed, stop prebuffering: bitrate', vs.bitrate, 'downrate', downrate)
                gotall = True
                self.prebufprogress = 1.0
            else:
                prebufrange = vs.generate_range((f, vs.normalize(f + self.max_prebuf_packets)))
                missing_pieces = filter(lambda i: not self.have_piece(i), prebufrange)
                gotall = not missing_pieces
                self.prebufprogress = float(self.max_prebuf_packets - len(missing_pieces)) / float(self.max_prebuf_packets)
                if DEBUG:
                    log('vod::update_prebuffering:live: prebufrange', prebufrange, 'missing_pieces', missing_pieces, 'prebufprogress', self.prebufprogress)
        else:
            if self.has_http_support():
                hp_total = vs.high_priority_length()
                hp_left = vs.high_priority_pieces()
                missing_pieces = vs.prebuf_high_priority_pieces
                gotall = hp_left == 0
                if hp_total > 0:
                    self.prebufprogress = (hp_total - hp_left) / float(hp_total)
                else:
                    self.prebufprogress = 1.0
            else:
                prebufrange = vs.prebuf_needed_pieces
                missing_pieces = filter(lambda i: not self.have_piece(i), prebufrange)
                self.prebufprogress = float(len(prebufrange) - len(missing_pieces)) / float(len(prebufrange))
                gotall = not missing_pieces
            if DEBUG:
                log('vod::update_prebuffering: Already got', self.prebufprogress * 100.0, '% of prebuffer')
                if not gotall:
                    log('vod::update_prebuffering: Still need pieces', missing_pieces, 'for prebuffering')
            if vs.dropping:
                if not gotall and 0 not in missing_pieces and self.nreceived > self.max_prebuf_packets:
                    perc = float(self.max_prebuf_packets) / 10.0
                    if float(len(missing_pieces)) < perc or self.nreceived > 2 * self.max_prebuf_packets:
                        gotall = True
                        if DEBUG:
                            log('vod::update_prebuffering: Forcing stop of prebuffering, less than', perc, 'missing, or got 2N packets already')
        if gotall and self.enough_buffer():
            self.stat_prebuffertime = time.time() - self.prebufstart
            if DEBUG:
                log('vod::update_prebuffering: prebuffering done: time', self.stat_prebuffertime, 'p2p_current_rate', self.p2p_current_rate, 'thread', currentThread().getName())
            self.data_ready.acquire()
            vs.prebuffering = False
            self.notify_playable()
            self.data_ready.notify()
            self.data_ready.release()
        elif DEBUG:
            log('vod::update_prebuffering: not done: gotall', gotall, 'enough_buffer', self.enough_buffer())

    def got_have(self, piece):
        vs = self.videostatus
        self.stat_pieces.set(piece, 'known', time.time())

    def got_piece(self, piece_id, begin, length):
        if self.videostatus.in_high_range(piece_id):
            self.high_range_rate.update_rate(length)

    def complete_from_persistent_state(self, myhavelist):
        vs = self.videostatus
        for piece in myhavelist:
            vs.got_piece(piece)
            if vs.in_download_range(piece):
                self.pieces_in_buffer += 1

        self.update_prebuffering()

    def complete(self, piece, downloaded = True):
        if DEBUG:
            log('vod::complete: piece', piece)
        elif globalConfig.get_value('vod_show_pieces', False):
            print >> sys.stderr, 'node: complete piece', piece
        vs = self.videostatus
        vs.got_piece(piece)
        if vs.live_streaming:
            i = vs.live_piece_to_invalidate(piece)
            if DEBUG:
                log('vod::complete: invalidate old live piece:', i)
            self.live_invalidate_piece(i)
        if not globalConfig.get_value('encrypted_storage') and not self._complete and self.piecepicker.am_I_complete():
            self._complete = True
            filename = self.videoinfo['outpath']
            self.data_ready.acquire()
            try:
                self.filestream = open(filename, 'rb')
                self.filestream.seek(self.stream_pos)
                if DEBUG:
                    log('vod::complete: open file and seek: path', filename, 'stream_pos', self.stream_pos)
            finally:
                self.data_ready.release()

        if vs.wraparound:
            pass
        self.stat_pieces.set(piece, 'complete', time.time())
        if downloaded:
            self.overall_rate.update_rate(vs.real_piecelen(piece))
        if vs.in_download_range(piece):
            self.pieces_in_buffer += 1
        else:
            if DEBUG:
                log('vod: piece %d too late [pos=%d]' % (piece, vs.playback_pos))
            self.stat_latepieces += 1
        self.update_prebuffering(piece)
        self.proxy_buffer_got_piece(piece)
        if self.http_support is not None:
            self.http_support.got_piece(piece)

    def set_pos(self, pos):
        vs = self.videostatus
        oldpos = min(vs.playback_pos, vs.last_piece)
        vs.playback_pos = pos
        vs.playback_pos_real = pos
        if vs.wraparound:
            self.pieces_in_buffer = 0
            for i in vs.generate_range(vs.download_range()):
                if self.has[i]:
                    self.pieces_in_buffer += 1

        else:
            for i in xrange(oldpos, pos + 1):
                if self.has[i]:
                    self.pieces_in_buffer -= 1

            for i in xrange(pos, oldpos + 1):
                if self.has[i]:
                    self.pieces_in_buffer += 1

    def inc_pos(self):
        vs = self.videostatus
        if self.has[vs.playback_pos]:
            self.pieces_in_buffer -= 1
        vs.inc_playback_pos()

    def make_report_pos(self, vs, playback_pos = None, last_read_pos = None):
        if playback_pos is None:
            playback_pos = vs.playback_pos
        if last_read_pos is None:
            last_read_pos = vs.last_read_pos
        return str(last_read_pos) + '/' + str(playback_pos) + '/' + str(vs.first_piece) + '/' + str(vs.last_piece)

    def got_metadata(self, metadata, update_prebuffering = True):
        try:
            if DEBUG_SKIP_METADATA:
                return
            if self.videostatus.bitrate_set and self.videostatus.got_prebuf_pieces:
                if DEBUG:
                    log('vod::got_metadata: metadata is already set')
                return
            index = self.videoinfo['index']
            if index == -1:
                index = 0
            if DEBUG:
                log('vod::got_metadata: index', index, 'metadata', metadata)
            duration = None
            prebuf_pieces = None
            if metadata.has_key('duration'):
                for k, v in metadata['duration'].iteritems():
                    try:
                        idx = int(k[1:])
                        if idx == index:
                            duration = int(v)
                            break
                    except:
                        pass

            if metadata.has_key('prebuf_pieces'):
                for k, v in metadata['prebuf_pieces'].iteritems():
                    try:
                        idx = int(k[1:])
                        if idx == index:
                            prebuf_pieces = [ int(x) for x in v.split(',') ]
                            break
                    except:
                        pass

            if DEBUG:
                log('vod::got_metadata: index', index, 'duration', duration, 'prebuf_pieces', prebuf_pieces)
            if duration is None and prebuf_pieces is None:
                return
            if not self.videostatus.bitrate_set and duration is not None:
                self.got_duration(duration)
                self.doing_mediainfo_analysis = False
            if not self.videostatus.got_prebuf_pieces and prebuf_pieces is not None:
                self.videostatus.set_prebuf_pieces(prebuf_pieces)
            if update_prebuffering:
                self.update_prebuffering()
        except:
            if DEBUG:
                print_exc()

    def got_duration(self, duration, from_player = False):
        if DEBUG:
            log('vod::got_duration: duration', duration, 'from_player', from_player)
        vs = self.videostatus
        if not vs.bitrate_set and duration > 0:
            vs.set_duration(duration)
            if OUTBUF_MIN_SIZE_ENABLED:
                self.outbuf_minsize = int(vs.bitrate / OUTBUF_MIN_SIZE_COEFF)
            if self.has_http_support():
                proxy = self.http_support.is_proxy_enabled(return_proxy=True)
                if proxy is not None:
                    speed_data = {'min_speed_start': None,
                     'min_speed_fail': vs.bitrate * MIN_HTTP_PROXY_SPEED_FAIL,
                     'timeout': SPEED_GAIN_TIMEOUT,
                     'callback': self.proxy_speed_callback}
                    proxy.set_speed_data(speed_data)
            vs.update_player_buffer_pieces(self.player_buffer_time * 3)
        if from_player:
            self.playback_started = True
            self.unpause_p2p()
            if not vs.live_streaming:
                report_data = {}
                if self.report_playback_events['vod-report-duration']:
                    if DEBUG:
                        log('vod::got_duration: report duration:', duration)
                    self.report_playback_events['vod-report-duration'] = False
                    report_data['duration'] = duration
                if self.report_playback_events['vod-report-prebuf-pieces']:
                    prebuf_pieces = self.report_prebuf_pieces()
                    if prebuf_pieces is None:
                        report_data['prebuf_pieces'] = '0'
                    else:
                        report_data['prebuf_pieces'] = prebuf_pieces
                    if DEBUG:
                        log('vod::got_duration: report prebuf pieces:', report_data['prebuf_pieces'])
                if len(report_data):
                    report_data['index'] = self.videoinfo['index']
                    self.videoinfo['usercallback'](VODEVENT_METADATA, report_data)
                    return self.videoinfo['index']

    def got_http_support(self):
        if not self.has_http_support():
            return
        vs = self.videostatus
        if DEBUG:
            log(self.log_prefix + 'got_http_support: prebuffering', vs.prebuffering)
        if not vs.prebuffering:
            return
        if OUTBUF_MIN_SIZE_ENABLED:
            self.outbuf_minsize = int(vs.bitrate / OUTBUF_MIN_SIZE_COEFF)
        vs.update_player_buffer_pieces(self.player_buffer_time * 3)
        self.pause_p2p()
        if not self.have_piece(vs.first_piece):
            reserve = 1
            if vs.bitrate_set:
                min_speed_start = None
                min_speed_fail = vs.bitrate * MIN_HTTP_PROXY_SPEED_FAIL
            else:
                min_speed_start = None
                min_speed_fail = 81920
            speed = {'min_speed_start': min_speed_start,
             'min_speed_fail': min_speed_fail,
             'timeout': SPEED_GAIN_TIMEOUT,
             'callback': self.proxy_speed_callback}
            self.start_proxy(pos=0, speed=speed)
        else:
            self.delay_p2p_start = True
            self.http_support.start_video_support()

            def p2p_start(self = self):
                if DEBUG:
                    log('vod::__init__:p2p_start: restore p2p rate: p2p_current_rate', self.p2p_current_rate)
                self.delay_p2p_start = False
                self.unpause_p2p()

            self.rawserver.add_task(p2p_start, 10.0)

    def report_prebuf_pieces(self):
        if not self.report_playback_events['vod-report-prebuf-pieces']:
            return None
        if len(self.report_playback_events['prebuf_pieces']) == 0:
            return None
        vs = self.videostatus
        if DEBUG:
            log('vod::report_prebuf_pieces: playback started, prebuf pieces:', self.report_playback_events['prebuf_pieces'])
        self.report_playback_events['vod-report-prebuf-pieces'] = False
        p = list(set(self.report_playback_events['prebuf_pieces']))
        p.sort()
        p = [ x for x in p if x >= vs.first_piece + vs.prebuf_pieces ]
        if DEBUG:
            log('vod::report_playback_pos: playback started, extra pieces:', p)
        if len(p) == 0:
            return None
        prebuf_pieces_string = ','.join([ str(x) for x in p ])
        return prebuf_pieces_string

    def report_playback_pos(self, pos, oldpos = None):
        try:
            vs = self.videostatus
            if vs.live_streaming:
                return
            percent = float(pos - vs.first_piece + 1) / float(vs.last_piece - vs.first_piece + 1)
            if DEBUG:
                log('vod::report_playback_pos: pos', pos, 'percent', percent, 'time', self.report_playback_events['vod-time-total'], 'playback_started', self.playback_started)
            if self.report_playback_events['vod-report-prebuf-pieces']:
                if not self.playback_started:
                    self.report_playback_events['prebuf_pieces'].append(pos)
            if not self.playback_started:
                return
            event = None
            if percent >= 1:
                event = 'vod-playback-complete'
            elif percent >= 0.75:
                event = 'vod-playback-75'
            elif percent >= 0.5:
                event = 'vod-playback-50'
            elif percent >= 0.25:
                event = 'vod-playback-25'
            else:
                event = 'vod-playback-start'
            if event is None:
                return
            if event in self.report_playback_events:
                return
            self.report_playback_events[event] = time.time()
            if DEBUG:
                log('vod::report_playback_pos: report event', event)
        except:
            log_exc()

    def start_playback_timer(self):
        if 'vod-time-start' in self.report_playback_events:
            self.report_playback_events['vod-time-total'] += time.time() - self.report_playback_events['vod-time-start']
            if DEBUG_EXTENDED:
                log('vod::start_playback_timer: got start', self.report_playback_events['vod-time-start'], 'total', self.report_playback_events['vod-time-total'])
        elif DEBUG_EXTENDED:
            log('vod::start_playback_timer: no prev start, time', self.report_playback_events['vod-time-total'])
        self.report_playback_events['vod-time-start'] = time.time()

    def stop_playback_timer(self):
        if 'vod-time-start' in self.report_playback_events:
            self.report_playback_events['vod-time-total'] += time.time() - self.report_playback_events['vod-time-start']
            if DEBUG_EXTENDED:
                log('vod::stop_playback_timer: clear start time, start', self.report_playback_events['vod-time-start'], 'total', self.report_playback_events['vod-time-total'])
            del self.report_playback_events['vod-time-start']

    def expected_download_time(self):
        vs = self.videostatus
        if vs.wraparound:
            return float(2147483648L)
        pieces_left = vs.last_piece - vs.playback_pos - self.pieces_in_buffer
        if DEBUG_EXTENDED:
            log('vod::expected_download_time: self.pieces_in_buffer', self.pieces_in_buffer, 'pieces_left', pieces_left)
        if pieces_left <= 0:
            return 0.0
        uncompleted_pieces = filter(lambda i: not self.storagewrapper.do_I_have(i), vs.generate_download_range())
        if not uncompleted_pieces:
            return 0.0
        total_length = vs.get_download_range_length()
        uncompleted_length = len(uncompleted_pieces)
        expected_download_speed = self.bt1download.downmeasure.get_rate() / 1.1
        if DEBUG_EXTENDED:
            log('vod::expected_download_time: total_length', total_length, 'uncompleted_length', uncompleted_length, 'expected_download_speed', expected_download_speed)
        if expected_download_speed < 0.1:
            return float(2147483648L)
        download_time = pieces_left * vs.piecelen / expected_download_speed
        if DEBUG_EXTENDED:
            log('vod::expected_download_time: download_time', int(download_time), 'speed', ceil(expected_download_speed / 1024), 'hr', self.high_range_rate.get_rate(), 'or', ceil(self.overall_rate.get_rate() / 1024))
        return download_time

    def expected_playback_time(self):
        vs = self.videostatus
        if vs.wraparound:
            return float(2147483648L)
        pieces_to_play = vs.last_piece - vs.playback_pos + 1
        if pieces_to_play <= 0:
            return 0.0
        if not vs.bitrate_set:
            return float(2147483648L)
        playback_time = pieces_to_play * vs.piecelen / vs.bitrate
        if DEBUG_EXTENDED:
            log('vod::expected_playback_time: playback_time', playback_time, 'pieces_to_play', pieces_to_play, 'piecelen', vs.piecelen, 'bitrate', vs.bitrate)
        return playback_time

    def expected_buffering_time(self):
        download_time = self.expected_download_time()
        playback_time = self.expected_playback_time()
        if DEBUG_EXTENDED:
            log('vod::expected_buffering_time: download_time', download_time, 'playback_time', playback_time)
        if download_time > float(1073741824) and playback_time > float(1073741824):
            return float(2147483648L)
        return abs(download_time - playback_time)

    def enough_buffer(self):
        if self.videostatus.wraparound:
            return True
        if not self.videostatus.bitrate_set:
            return True
        if not self.wait_sufficient_speed:
            return True
        expected_download_time = self.expected_download_time()
        expected_playback_time = self.expected_playback_time()
        if DEBUG:
            log('vod::enough_buffer: expected_download_time', expected_download_time, 'expected_playback_time', expected_playback_time)
        return max(0.0, expected_download_time - expected_playback_time) == 0.0

    def size(self):
        if self.videostatus.get_wraparound():
            return None
        else:
            return self.videostatus.selected_movie['size']

    def has_http_support(self, min_speed = None):
        if self.http_support is None:
            return False
        return self.http_support.can_support(min_speed)

    def start_proxy(self, pos, seek = True, speed = None, respect_reserved_pieces = False):
        if not self.enable_http_proxy:
            return False
        if not self.has_http_support():
            return False
        if pos >= self.videostatus.selected_movie['size']:
            if DEBUG:
                log('vod::start_proxy: skip start, pos too high: pos', pos, 'size', self.videostatus.selected_movie['size'])
            return False
        proxy_data = self.http_support.start_proxy(pos=pos, seek=seek, callback_failed=self.proxy_failed_callback, speed=speed, respect_reserved_pieces=respect_reserved_pieces)
        if proxy_data is None:
            return False
        return True

    def stop_proxy(self, stop_support = True, finish_piece = False):
        if DEBUG:
            log('vod::stop_proxy: stop_support', stop_support, 'finish_piece', finish_piece)
        self.proxy_cond.acquire()
        try:
            if self.p2p_current_rate is not None and not self.delay_p2p_start:
                if DEBUG:
                    log('vod::stop_proxy: restore p2p rate: p2p_current_rate', self.p2p_current_rate)
                self.bt1download.setDownloadRate(self.p2p_current_rate, networkcalling=True)
                self.p2p_current_rate = None
            if stop_support and self.http_support is not None:
                self.http_support.stop_proxy(finish_piece=finish_piece)
            self.proxy_cond.notify()
        finally:
            self.proxy_cond.release()

    def http_support_request_piece(self, httpseed):
        if self.playback_started and self.bt1download.downloader.has_downloaders():
            range_name = 'high'
            r = self.videostatus.generate_high_range(min_size=4)
        else:
            range_name = 'download'
            r = self.videostatus.generate_download_range()
        while True:
            for index in r:
                if not self.has[index]:
                    if DEBUG:
                        if self.storagewrapper.inactive_requests[index] is None or self.storagewrapper.inactive_requests[index] == 1:
                            inactive = self.storagewrapper.inactive_requests[index]
                        else:
                            inactive = len(self.storagewrapper.inactive_requests[index])
                        due = self.piece_due(index) - time.time()
                        log('vod::http_support_request_piece: incompleted piece: index', index, 'numactive', self.storagewrapper.numactive[index], 'inactive', inactive, 'finished', len(self.storagewrapper.dirty.get(index, [])), 'due', due, 'url', httpseed.baseurl)
                    if self.storagewrapper.do_I_have_requests(index):
                        if DEBUG:
                            log('vod::http_support_request_piece: got piece with inactive requests: index', index, 'url', httpseed.baseurl)
                        return index
                elif DEBUG:
                    log('vod::http_support_request_piece: completed piece: index', index, 'url', httpseed.baseurl)

            if range_name == 'download':
                r = xrange(self.videostatus.first_piece, self.videostatus.last_piece + 1)
                if DEBUG:
                    log('vod::http_support_request_piece: got all pieces in %s range, try whole range' % range_name)
                range_name = 'whole'
            else:
                break

        if DEBUG:
            log('vod::http_support_request_piece: got all pieces in %s range, return None' % range_name)

    def proxy_buffer_got_piece(self, index):
        self.proxy_cond.acquire()
        try:
            swallow = []
            vs = self.videostatus
            piece_start, piece_end = self.bytepos_from_piecepos(vs, index)
            for bstart, bdata in self.proxy_buf.iteritems():
                bend = bstart + len(bdata) - 1
                if bstart <= piece_start <= bend:
                    swallow_pos = bstart
                    swallow_from = piece_start
                    swallow_to = min(bend, piece_end)
                    swallow.append((swallow_pos, swallow_from, swallow_to))
                elif bstart <= piece_end <= bend:
                    swallow_pos = bstart
                    swallow_from = bstart
                    swallow_to = min(bend, piece_end)
                    swallow.append((swallow_pos, swallow_from, swallow_to))

            for swallow_pos, swallow_from, swallow_to in swallow:
                bstart = swallow_pos
                bend = bstart + len(self.proxy_buf[bstart]) - 1
                if swallow_from == bstart and swallow_to == bend:
                    if DEBUG:
                        log('vod::proxy_buffer_got_piece: swallow whole chunk: bstart', bstart, 'bend', bend, 'swallow_pos', swallow_pos, 'swallow_from', swallow_from, 'swallow_to', swallow_to)
                    del self.proxy_buf[bstart]
                elif swallow_from == bstart and swallow_to < bend:
                    offset = swallow_to - bstart
                    newpos = swallow_to + 1
                    data = self.proxy_buf[bstart][offset:]
                    if DEBUG:
                        log('vod::proxy_buffer_got_piece: swallow chunk start: bstart', bstart, 'bend', bend, 'swallow_pos', swallow_pos, 'swallow_from', swallow_from, 'swallow_to', swallow_to, 'offset', offset, 'newpos', newpos, 'newlen', len(data))
                    del self.proxy_buf[bstart]
                    self.proxy_buf[newpos] = data
                elif swallow_from > bstart and swallow_to == bend:
                    offset = swallow_from - bstart
                    data = self.proxy_buf[bstart][:offset]
                    if DEBUG:
                        log('vod::proxy_buffer_got_piece: swallow chunk end: bstart', bstart, 'bend', bend, 'swallow_pos', swallow_pos, 'swallow_from', swallow_from, 'swallow_to', swallow_to, 'offset', offset, 'newlen', len(data))
                    self.proxy_buf[bstart] = data
                elif swallow_from > bstart and swallow_to < bend:
                    offset1 = swallow_from - bstart
                    data1 = self.proxy_buf[bstart][:offset1]
                    offset2 = bend - swallow_to
                    data2 = self.proxy_buf[bstart][-offset2:]
                    newpos = swallow_to + 1
                    if DEBUG:
                        log('vod::proxy_buffer_got_piece: swallow chunk middle: bstart', bstart, 'bend', bend, 'swallow_pos', swallow_pos, 'swallow_from', swallow_from, 'swallow_to', swallow_to, 'offset1', offset1, 'offset2', offset2, 'newpos', newpos, 'newlen1', len(data1), 'newlen2', len(data2))
                    self.proxy_buf[bstart] = data1
                    self.proxy_buf[newpos] = data2
                elif DEBUG:
                    log('vod::proxy_buffer_got_piece: !!!cannot swallow!!!: bstart', bstart, 'bend', bend, 'swallow_pos', swallow_pos, 'swallow_from', swallow_from, 'swallow_to', swallow_to)

            if len(swallow) > 0:
                self.stat_proxy_buf = self.proxy_buf.copy()
        finally:
            self.proxy_cond.release()

    def got_proxy_data(self, pos, data):
        t = time.time()
        self.proxy_cond.acquire()
        try:
            length = len(data)
            skip = False
            seek_pos = None
            piece_index, _ = self.piecepos_from_bytepos(self.videostatus, pos)
            if self.have_piece(piece_index):
                missing_piece = None
                for i in xrange(piece_index + 1, self.videostatus.last_piece + 1):
                    if not self.have_piece(i):
                        missing_piece = i
                        seek_pos, _ = self.bytepos_from_piecepos(self.videostatus, missing_piece)
                        break

                if DEBUG:
                    log('vod::got_proxy_data: existing piece, skip: pos', pos, 'len', length, 'index', piece_index, 'next_missing_piece', missing_piece, 'seek_pos', seek_pos)
                skip = True
            elif self.proxy_buf.has_key(pos):
                if len(self.proxy_buf[pos]) >= length:
                    seek_pos = pos + len(self.proxy_buf[pos])
                    if DEBUG:
                        log('vod::got_proxy_data: existing pos, skip: pos', pos, 'len', length, 'blen', len(self.proxy_buf[pos]), 'seek_pos', seek_pos)
                    skip = True
                else:
                    self.proxy_buf[pos] = data
            else:
                updated_chunk_start = None
                updated_chunk_end = None
                for bpos, bdata in self.proxy_buf.iteritems():
                    start = bpos
                    end = bpos + len(bdata) - 1
                    if bpos <= pos <= end + 1:
                        if pos + length <= end + 1:
                            seek_pos = end + 1
                            if DEBUG:
                                log('vod::got_proxy_data: found in existing data, skip: pos', pos, 'length', length, 'start', start, 'end', end, 'seek_pos', seek_pos)
                            skip = True
                        else:
                            offset = end - pos + 1
                            self.proxy_buf[bpos] += data[offset:]
                            updated_chunk_start = bpos
                            updated_chunk_end = bpos + len(self.proxy_buf[bpos]) - 1
                        break

                if updated_chunk_end is not None:
                    swallow = []
                    for bpos, bdata in self.proxy_buf.iteritems():
                        if bpos == updated_chunk_start:
                            continue
                        if updated_chunk_start <= bpos <= updated_chunk_end:
                            end = bpos + len(bdata) - 1
                            if end > updated_chunk_end:
                                offset = end - updated_chunk_end
                                self.proxy_buf[updated_chunk_start] += bdata[-offset:]
                            swallow.append(bpos)

                    for pos in swallow:
                        if DEBUG:
                            log('vod::got_proxy_data: swallow: pos', pos)
                        del self.proxy_buf[pos]

                elif not skip:
                    self.proxy_buf[pos] = data
            if not skip:
                self.stat_proxy_buf = self.proxy_buf.copy()
                if self.proxy_buf_observers:
                    new_observers = []
                    for i in xrange(len(self.proxy_buf_observers)):
                        opos, notify_func = self.proxy_buf_observers.pop(0)
                        if pos <= opos < pos + length - 1:
                            notify_func(pos)
                        else:
                            new_observers.append((opos, notify_func))

                    self.proxy_buf_observers = new_observers
                self.proxy_cond.notify()
            return seek_pos
        finally:
            self.proxy_cond.release()

    def pause_p2p(self):
        if self.bt1download.unpauseflag.isSet():
            if DEBUG:
                log('vod::pause_p2p: ---')
            self.bt1download.Pause(close_connections=True)
            return True
        return False

    def unpause_p2p(self):
        if not self.bt1download.unpauseflag.isSet():
            if DEBUG:
                log('vod::unpause_p2p: ---')
            self.bt1download.Unpause()
            return True
        return False

    def proxy_failed_callback(self):
        if DEBUG:
            log('vod::proxy_failed_callback: ---')
        self.wait_proxy_flag = False
        self.http_support.start_video_support()
        self.unpause_p2p()
        if self.p2p_current_rate is not None:
            if DEBUG:
                log('vod::proxy_failed_callback: restore p2p rate: p2p_current_rate', self.p2p_current_rate)
            self.bt1download.setDownloadRate(self.p2p_current_rate, networkcalling=True)
            self.p2p_current_rate = None

    def read(self, numbytes = None):
        self.data_ready.acquire()
        try:
            if self.filestream:
                if numbytes is None:
                    numbytes = DEFAULT_READ_SIZE
                if DEBUG:
                    log('vod::read: read from filestream: numbytes', numbytes, 'filestream', self.filestream, 'thread', currentThread().getName())
                data = self.filestream.read(numbytes)
            else:
                if not self.curpiece:
                    if DEBUG_BUFFERING:
                        log('vod::read: pop curpiece: stream_start', self.stream_start)
                    if self.videostatus.live_streaming:
                        numbytes = None
                    piecetup = self.pop(numbytes, find_mpegps_start=False)
                    self.stream_start = False
                    if piecetup is None:
                        if DEBUG:
                            log('vod::read: return none')
                        return
                    index, pos, self.curpiece = piecetup
                    if not self.videostatus.live_streaming:
                        pass
                    self.curpiece_pos = self.stream_pos - pos
                    self.start_playback_timer()
                    if DEBUG_EXTENDED:
                        log('vod::read: popped data: index', index, 'pos', pos, 'stream_pos', self.stream_pos, 'curpiece_pos', self.curpiece_pos, 'len', len(self.curpiece))
                elif DEBUG_BUFFERING:
                    log('vod::read: got curpiece')
                data = self.curpiece
                self.curpiece = ''
                self.curpiece_pos = None
            self.stream_pos += len(data)
            if DEBUG:
                log('vod::read: update stream pos: stream_pos', self.stream_pos, 'len(data)', len(data), 'thread', currentThread().getName())
        finally:
            self.data_ready.release()

        return data

    def piecepos_from_bytepos(self, vs, bytepos, check_last = True):
        if bytepos < vs.first_piecelen:
            piece = vs.first_piece
            offset = bytepos
        else:
            newbytepos = bytepos - vs.first_piecelen
            piece = vs.first_piece + newbytepos / vs.piecelen + 1
            offset = newbytepos % vs.piecelen
            if piece == vs.last_piece and offset >= vs.last_piecelen:
                piece += 1
        if check_last and piece > vs.last_piece:
            piece = vs.last_piece
            offset = vs.last_piecelen
        return (piece, offset)

    def bytepos_from_piecepos(self, vs, piece):
        if piece == vs.first_piece:
            start = 0
            length = vs.first_piecelen
        elif piece == vs.last_piece:
            start = (piece - vs.first_piece - 1) * vs.piecelen + vs.first_piecelen
            length = vs.last_piecelen
        else:
            start = (piece - vs.first_piece - 1) * vs.piecelen + vs.first_piecelen
            length = vs.piecelen
        return (start, start + length - 1)

    def start(self, bytepos = 0, force = False, network_calling = True):
        if DEBUG:
            log('vod::start: bytepos', bytepos, 'playing', self.videostatus.playing, 'force', force)
        vs = self.videostatus
        if vs.playing and not force:
            return
        self.data_ready.acquire()
        try:
            if self._complete:
                if self.filestream is None:
                    if DEBUG:
                        log('vod::start: open file: path', self.videoinfo['outpath'])
                    self.filestream = open(self.videoinfo['outpath'], 'rb')
                if DEBUG:
                    log('vod::start: seek file: pos', bytepos)
                self.filestream.seek(bytepos)
                self.stream_pos = bytepos
                vs.playing = True
                if vs.paused:
                    if DEBUG:
                        log('vod::start: paused at start, resume')
                    self.resume()
                return
            if vs.live_streaming:
                if not force:
                    self.calc_live_startpos(self.max_prebuf_packets, True)
                piece = vs.playback_pos
                offset = 0
            else:
                piece, offset = self.piecepos_from_bytepos(vs, bytepos)
            self.start_playback_timer()
            if DEBUG:
                log('vod::start: pos', bytepos, 'piece', piece, 'force', force, 'thread', currentThread().getName())
            self.stream_start = True
            self.stream_pos = bytepos
            self.curpiece = ''
            self.curpiece_pos = None
            self.set_pos(piece)
            self.outbuf = []
            self.stat_outbuf = []
            self.outbuflen = 0
            self.outbufpos = self.stream_pos
            self.last_pop = time.time()
            self.last_start = time.time()
            self.last_resume = None
            self.reset_bitrate_prediction()
            vs.playing = True
            self.playbackrate = Measure(60)
            if vs.paused:
                if DEBUG:
                    log('vod::start: paused at start, resume')
                self.resume()
            self.paused_pos = None
        finally:
            self.data_ready.release()

        if network_calling:
            self.update_prebuffering()
            self.refill_buffer()
        else:
            self.rawserver.add_task(self.update_prebuffering, 0)
            self.rawserver.add_task(self.refill_buffer, 0)

    def shutdown(self):
        if DEBUG:
            log('vod::shutdown')
        self.stop()
        if self.http_support is not None:
            self.http_support.stop_video_support(shutdown=True)
            self.stop_proxy()

    def stop(self, seek = False):
        self.stop_playback_timer()
        vs = self.videostatus
        if DEBUG:
            log('vod::stop: thread', currentThread().getName())
        if not vs.playing:
            return
        self.data_ready.acquire()
        self.outbuf = []
        self.stat_outbuf = []
        self.outbuflen = 0
        self.outbufpos = None
        self.last_pop = None
        vs.prebuffering = False
        self.paused_pos = None
        self.wait_proxy_flag = False
        if not seek:
            vs.playing = False
            vs.paused = False
            self.stop_proxy()
            if self.filestream is not None:
                if DEBUG:
                    log('vod::stop: close filestream')
                self.filestream.close()
                self.filestream = None
        self.data_ready.notify()
        self.data_ready.release()
        if DEBUG_BUFFERING:
            log('DEBUG_BUFFERING vod::stop: empty buffer')

    def pause(self, autoresume = False):
        vs = self.videostatus
        self.paused_pos = vs.playback_pos
        if not vs.playing or not vs.pausable:
            return
        if vs.paused:
            vs.autoresume = autoresume
            return
        self.stop_playback_timer()
        if DEBUG:
            log('vod::pause (autoresume: %s)' % autoresume)
        vs.paused = True
        vs.autoresume = autoresume
        self.paused_at = time.time()
        self.videoinfo['usercallback'](VODEVENT_PAUSE, {'autoresume': autoresume})

    def resume(self):
        vs = self.videostatus
        self.paused_pos = None
        self.last_resume = time.time()
        if not self.wait_proxy_flag:
            if self.unpause_p2p():
                log('vod::resume: unpause bt1')
        if not vs.playing or not vs.paused or not vs.pausable:
            return
        self.start_playback_timer()
        if DEBUG:
            log('vod::resume')
        vs.paused = False
        vs.autoresume = False
        self.stat_stalltime += time.time() - self.paused_at
        self.addtime_bitrate_prediction(time.time() - self.paused_at)
        self.videoinfo['usercallback'](VODEVENT_RESUME, {})
        self.update_prebuffering()
        self.refill_buffer()

    def autoresume(self, testfunc = lambda : True):
        vs = self.videostatus
        if not vs.playing or not vs.paused or not vs.autoresume:
            if DEBUG:
                log('vod::autoresume: exit: playing', vs.playing, 'paused', vs.paused, 'autoresume', vs.autoresume)
            return
        if DEBUG:
            log('vod::autoresume: run testfunc')
        if not testfunc():
            self.rawserver.add_task(lambda : self.autoresume(testfunc), 0.3)
            return
        if DEBUG:
            log('vod::autoresume: resume')
        self.resume()

    def done(self):
        vs = self.videostatus
        if not vs.playing:
            return True
        if vs.wraparound:
            return False
        return self.outbufpos == vs.selected_movie['size'] and len(self.outbuf) == 0 and len(self.curpiece) == 0 and self.curpiece_pos is None

    def seek(self, pos, whence = os.SEEK_SET):
        vs = self.videostatus
        length = self.size()
        self.data_ready.acquire()
        try:
            if vs.live_streaming:
                self.stream_start = True
                raise ValueError('seeking not possible for live')
            if whence == os.SEEK_SET:
                abspos = pos
            elif whence == os.SEEK_END:
                if pos > 0:
                    raise ValueError('seeking beyond end of stream')
                else:
                    abspos = length + pos
            else:
                raise ValueError('seeking does not currently support SEEK_CUR')
            if self._complete:
                if self.filestream is None:
                    if DEBUG:
                        log('vod::seek: open file:', self.videoinfo['outpath'])
                    self.filestream = open(self.videoinfo['outpath'], 'rb')
                if DEBUG:
                    log('vod::seek: seek file: pos', pos)
                self.filestream.seek(pos)
                self.stream_pos = pos
            else:
                self.stop(seek=True)
                self.start(pos, force=True)
        finally:
            self.data_ready.release()

    def get_mimetype(self):
        return self.mimetype

    def set_mimetype(self, mimetype):
        self.mimetype = mimetype

    def available(self):
        self.data_ready.acquire()
        try:
            return self.outbuflen
        finally:
            self.data_ready.release()

    def have_piece(self, piece):
        return self.piecepicker.has[piece]

    def get_piece(self, piece):
        vs = self.videostatus
        if not self.have_piece(piece):
            return
        begin = 0
        length = vs.piecelen
        if piece == vs.first_piece:
            begin = vs.movie_range[0][1]
            length -= begin
        if piece == vs.last_piece:
            cutoff = vs.piecelen - (vs.movie_range[1][1] + 1)
            length -= cutoff
        if DEBUG_READ_PIECE:
            t = time.time()
        data = self.storagewrapper.do_get_piece(piece, begin, length)
        if data is None:
            if DEBUG_READ_PIECE:
                log('>>>read:vod:get_piece: sw returned none: piece', piece, 'begin', begin, 'length', length)
            return
        if DEBUG_READ_PIECE:
            t = time.time() - t
            log('>>read:vod:get_piece: index', piece, 'begin', begin, 'length', length, 'time', t, 'data', data[:20])
            if piece == 0:
                log('>>read:vod:get_piece: index', piece, 'begin', begin, 'length', length, 'time', t, 'data1', data[:20], 'data2', data[-40:])
        return data.tostring()

    def reset_bitrate_prediction(self):
        self.start_playback = None
        self.last_playback = None
        self.history_playback = collections.deque()

    def addtime_bitrate_prediction(self, seconds):
        if self.start_playback is not None:
            self.start_playback['local_ts'] += seconds

    def valid_piece_data(self, i, piece):
        if not piece:
            return False
        if not self.start_playback or self.authenticator is None:
            return True
        s = self.start_playback
        seqnum = self.authenticator.get_seqnum(piece)
        source_ts = self.authenticator.get_rtstamp(piece)
        if seqnum < s['absnr'] or source_ts < s['source_ts']:
            print >> sys.stderr, 'vod: trans: **** INVALID PIECE #%s **** seqnum=%d but we started at seqnum=%d, ts=%f but we started at %f' % (i,
             seqnum,
             s['absnr'],
             source_ts,
             s['source_ts'])
            return True
        return True

    def update_bitrate_prediction(self, i, piece):
        if self.authenticator is not None:
            seqnum = self.authenticator.get_seqnum(piece)
            source_ts = self.authenticator.get_rtstamp(piece)
        else:
            seqnum = i
            source_ts = 0
        d = {'nr': i,
         'absnr': seqnum,
         'local_ts': time.time(),
         'source_ts': source_ts}
        if self.start_playback is None:
            self.start_playback = d
        if self.last_playback and self.last_playback['absnr'] > d['absnr']:
            return
        self.last_playback = d
        MAX_HIST_LEN = 600
        self.history_playback.append(d)
        while source_ts - self.history_playback[0]['source_ts'] > MAX_HIST_LEN:
            self.history_playback.popleft()

        if DEBUG_EXTENDED:
            vs = self.videostatus
            first, last = self.history_playback[0], self.history_playback[-1]
            if first['source_ts'] and first != last:
                divd = last['source_ts'] - first['source_ts']
                if divd == 0:
                    divd = 1e-06
                bitrate = '%.2f kbps' % (8.0 / 1024 * (vs.piecelen - vs.sigsize) * (last['absnr'] - first['absnr']) / divd,)
            else:
                bitrate = '%.2f kbps (external info)' % (8.0 / 1024 * vs.bitrate)
            log('vod: trans: %i: pushed at t=%.2f, age is t=%.2f, bitrate = %s' % (i,
             d['local_ts'] - self.start_playback['local_ts'],
             d['source_ts'] - self.start_playback['source_ts'],
             bitrate))

    def piece_due(self, i):
        if self.start_playback is None:
            return float(2147483648L)
        else:
            s = self.start_playback
            l = self.last_playback
            vs = self.videostatus
            if not vs.wraparound and i < l['nr']:
                return time.time()
            piecedist = (i - l['nr']) % vs.movie_numpieces
            if s['source_ts']:
                first, last = self.history_playback[0], self.history_playback[-1]
                if first != last and first['source_ts'] != last['source_ts']:
                    bitrate = 1.0 * vs.piecelen * (last['absnr'] - first['absnr']) / (last['source_ts'] - first['source_ts'])
                else:
                    bitrate = vs.bitrate
                return s['local_ts'] + l['source_ts'] - s['source_ts'] + piecedist * vs.piecelen / bitrate - self.PIECE_DUE_SKEW
            if vs.live_streaming:
                return time.time() + 60.0
            i = piecedist + (l['absnr'] - s['absnr'])
            if s['nr'] == vs.first_piece:
                bytepos = vs.first_piecelen + (i - 1) * vs.piecelen
            else:
                bytepos = i * vs.piecelen
            return s['local_ts'] + bytepos / vs.bitrate - self.PIECE_DUE_SKEW

    def max_buffer_size(self):
        buffer_time = max(self.player_buffer_time, 5.0)
        vs = self.videostatus
        if vs.dropping:
            return max(0, 2 * int(buffer_time * vs.bitrate))
        else:
            return max(262144, vs.piecelen * 2, 2 * int(buffer_time * vs.bitrate))

    def proxy_speed_callback(self, proxy, proxy_speed, time_to_finish_piece):
        vs = self.videostatus
        if vs.bitrate_set:
            bitrate = vs.bitrate
        else:
            bitrate = None
        http_support_info = self.http_support.get_info()
        if DEBUG:
            log('vod::proxy_speed_callback: proxy_speed', proxy_speed, 'bitrate', bitrate, 'time_to_finish_piece', time_to_finish_piece, 'playback_started', self.playback_started, 'http_support_info', http_support_info)
        self.wait_proxy_flag = False
        stop_proxy = True
        finish_piece = True
        start_support = True
        if stop_proxy:
            min_speed = self.min_http_support_speed()
            if proxy_speed >= min_speed:
                start_support = True
            else:
                start_support = False
            finish_piece = start_support
        if stop_proxy and not finish_piece:
            proxy.is_proxy = False
        if self.has_http_support():
            if self.playback_started:
                min_speed = self.min_http_support_speed()
            else:
                min_speed = None
            if DEBUG:
                log('vod::proxy_speed_callback: start http support: min_speed', min_speed)
            self.http_support.start_video_support(min_speed=min_speed)
        if self.playback_started:
            self.unpause_p2p()
        elif not self.delay_p2p_start:
            self.delay_p2p_start = True

            def p2p_start(self = self):
                self.delay_p2p_start = False
                if self.playback_started:
                    return
                if self.videostatus.bitrate_set:
                    bitrate = self.videostatus.bitrate
                else:
                    bitrate = None
                http_support_info = self.http_support.get_info()
                if bitrate is None or http_support_info['avg_speed_all'] < bitrate:
                    if DEBUG:
                        log('vod::proxy_speed_callback:p2p_start: start p2p: http_support_info', http_support_info, 'bitrate', bitrate)
                    self.unpause_p2p()

            if DEBUG:
                log('vod::proxy_speed_callback: schedule p2p start in 10 seconds')
            self.rawserver.add_task(p2p_start, 10.0)
        return (stop_proxy, finish_piece, start_support)

    def min_http_support_speed(self):
        return self.bt1download.downmeasure.get_rate() / 5

    def refill_buffer(self):
        self.data_ready.acquire()
        try:
            self._refill_buffer()
        except:
            print_exc()
        finally:
            self.data_ready.release()

    def _refill_buffer(self):
        vs = self.videostatus
        self.refill_buffer_counter += 1
        if self.refill_buffer_counter > 10:
            self.refill_buffer_counter = 0
        if vs.prebuffering or vs.paused or not vs.playing or self.done():
            return
        mx = self.max_buffer_size()
        now = time.time()

        def push_piece(index, data):
            self.update_bitrate_prediction(index, data)
            self.stat_playedpieces += 1
            self.stat_pieces.set(index, 'tobuffer', time.time())
            piece_start, piece_end = self.bytepos_from_piecepos(vs, index)
            if not self.videostatus.live_streaming:
                pass
            if not self.videostatus.live_streaming and piece_end < self.outbufpos:
                if DEBUG:
                    log('vod::push_piece: skip piece, too late: index', index, 'piece_start', piece_start, 'piece_end', piece_end, 'outbufpos', self.outbufpos, 'len', len(data))
                return
            if not self.videostatus.live_streaming and piece_start < self.outbufpos:
                offset = self.outbufpos - piece_start
                data = data[offset:]
                if DEBUG:
                    log('vod::push_piece: trim piece: index', index, 'piece_start', piece_start, 'piece_end', piece_end, 'outbufpos', self.outbufpos, 'offset', offset, 'len', len(data))
                piece_start = self.outbufpos
            self.outbuf.append((index, piece_start, data))
            self.stat_outbuf.append((index, piece_start, len(data)))
            self.outbuflen += len(data)
            self.outbufpos += len(data)
            self.inc_pos()
            if DEBUG_BUFFERING:
                log('vod::push_piece: playback_pos', vs.playback_pos, 'index', index, 'outbuflen', self.outbuflen, 'outbufpos', self.outbufpos, 'paused', vs.paused)
            if not vs.paused:
                self.data_ready.notify()

        def push_data(pos, data):
            piece_index, piece_offset = self.piecepos_from_bytepos(vs, pos)
            self.outbuf.append((piece_index, pos, data))
            self.stat_outbuf.append((piece_index, pos, len(data)))
            self.outbuflen += len(data)
            self.outbufpos += len(data)
            piece_index, piece_offset = self.piecepos_from_bytepos(vs, self.outbufpos, False)
            if piece_index > vs.playback_pos:
                if DEBUG:
                    log('vod::push_data: playback pos changed: curpos', vs.playback_pos, 'newpos', piece_index)
                if piece_index == vs.playback_pos + 1:
                    self.inc_pos()
                else:
                    self.set_pos(piece_index)
            if DEBUG:
                log('vod::push_data: pos', pos, 'len', len(data), 'outbufpos', self.outbufpos)
            if not vs.paused:
                self.data_ready.notify()

        def drop(i):
            if DEBUG:
                print >> sys.stderr, 'vod: trans: %d: dropped pos=%d; deadline expired %.2f sec ago !!!!!!!!!!!!!!!!!!!!!!' % (i, vs.playback_pos, time.time() - self.piece_due(i))
            self.stat_droppedpieces += 1
            self.stat_pieces.complete(i)
            self.inc_pos()

        def buffer_underrun():
            if self.outbuf_minsize is None:
                min_size = 1
            else:
                min_size = self.outbuf_minsize
            if self.outbuflen < min_size and (self.start_playback is None or now - self.start_playback['local_ts'] > 1.0):
                if DEBUG:
                    log('vod::refill_buffer:buffer_underrun: got underrun: self.outbuflen', self.outbuflen, 'self.start_playback', self.start_playback, 'now', now)
                if self.skip_underrun_timeout is not None:
                    if self.last_resume is not None and now - self.last_resume < self.skip_underrun_timeout:
                        if DEBUG:
                            log('vod::refill_buffer:buffer_underrun: recent resume, skip pause: now', now, 'last_resume', self.last_resume, 'skip_underrun_timeout', self.skip_underrun_timeout)
                        return False
                    self.skip_underrun_timeout = None
                return True
            return False

        def fill_from_pieces():
            got_piece = False
            for piece in vs.generate_range(vs.download_range()):
                if self.outbuflen > mx:
                    break
                ihavepiece = self.has[piece]
                forcedrop = False
                if ihavepiece:
                    data = self.get_piece(piece)
                    if not self.valid_piece_data(piece, data):
                        log("should gave this piece but it's missing", piece)
                        forcedrop = True
                        ihavepiece = False
                if ihavepiece:
                    if DEBUG_EXTENDED:
                        log('vod: trans: BUFFER STATUS (max %.0f): %.0f kbyte' % (mx / 1024.0, self.outbuflen / 1024.0))
                    push_piece(piece, data)
                    got_piece = True
                else:
                    if not vs.dropping and forcedrop:
                        print >> sys.stderr, "vod: trans: DROPPING INVALID PIECE #%s, even though we shouldn't drop anything." % piece
                    if forcedrop:
                        if forcedrop or time.time() >= self.piece_due(piece) or vs.pausable and buffer_underrun() and sustainable():
                            drop(piece)
                        elif DEBUG:
                            print >> sys.stderr, 'vod: trans: %d: due in %.2fs  pos=%d' % (piece, self.piece_due(piece) - time.time(), vs.playback_pos)
                        break
                    else:
                        if DEBUG:
                            log('vod: trans: %d: not enough pieces to fill buffer.' % piece)
                        break

            return got_piece

        def fill_from_proxy():
            self.proxy_cond.acquire()
            try:
                for bstart, bdata in self.proxy_buf.iteritems():
                    bend = bstart + len(bdata) - 1
                    if bstart <= self.outbufpos <= bend:
                        offset_from = self.outbufpos - bstart
                        offset_to = offset_from + mx - self.outbuflen
                        data = bdata[offset_from:]
                        if DEBUG:
                            log('vod::refill_buffer: push data from proxy: outbufpos', self.outbufpos, 'bstart', bstart, 'bend', bend, 'offset_from', offset_from, 'offset_to', offset_to)
                        push_data(self.outbufpos, data)
                        break

            except:
                log_exc()
            finally:
                self.proxy_cond.release()

        if vs.live_streaming:

            def sustainable():
                if self.paused_pos is None:
                    self.paused_pos = vs.playback_pos
                self.sustainable_counter += 1
                if self.sustainable_counter > 10:
                    self.sustainable_counter = 0
                    high_range_length = vs.get_high_range_length()
                    have_length = len(filter(lambda n: self.has[n], vs.generate_range((self.paused_pos, self.paused_pos + high_range_length))))
                    if DEBUG:
                        log('vod::refill_buffer:sustainable: self.sustainable_counter', self.sustainable_counter, 'paused_pos', self.paused_pos, 'high_range_length', high_range_length, 'have_length', have_length)
                    self.prebufprogress = min(1.0, float(have_length) / max(1, high_range_length))
                    ready = have_length >= high_range_length
                else:
                    ready = False
                    num_immediate_packets = 0
                    high_range_length = vs.get_high_range_length()
                    for piece in vs.generate_range((self.paused_pos, vs.normalize(self.paused_pos + high_range_length))):
                        try:
                            if self.has[piece]:
                                num_immediate_packets += 1
                                if num_immediate_packets >= high_range_length:
                                    break
                            else:
                                break
                        except IndexError:
                            if DEBUG:
                                log('>>>vod:refill: index out of range: piece', piece, 'paused_pos', self.paused_pos, 'high_range_length', high_range_length, 'len(has)', len(self.has))

                    else:
                        self.prebufprogress = 1.0
                        ready = True

                    if DEBUG:
                        log('vod:refill_buffer:sustainable: sustainable_counter', self.sustainable_counter, 'high_range_length', high_range_length, 'paused_pos', self.paused_pos, 'num_immediate_packets', num_immediate_packets)
                    if not ready:
                        ready = num_immediate_packets >= high_range_length
                    if not ready:
                        min_buffer = min(self.max_prebuf_packets, high_range_length)
                        downrate = self.bt1download.downmeasure.get_rate_noupdate()
                        if downrate >= vs.bitrate * 1.3 and num_immediate_packets >= min_buffer:
                            if DEBUG:
                                log('vod::refill_buffer:sustainable: enough speed, stop buffering: downrate', downrate, 'bitrate', vs.bitrate, 'min_buffer', min_buffer, 'num_immediate_packets', num_immediate_packets)
                            ready = True
                return ready

        else:

            def sustainable():
                has_http_support = self.has_http_support()
                if has_http_support:
                    proxy = self.http_support.is_proxy_enabled(return_proxy=True)
                else:
                    proxy = None
                if proxy is not None and not proxy.is_stopping():
                    left = vs.selected_movie['size'] - self.outbufpos
                    if left == 0:
                        if DEBUG:
                            log('vod::sustainable: no data left, resume: outbufpos', self.outbufpos)
                        self.prebufprogress = 1.0
                        ready = True
                    else:
                        proxy_speed = max(1, proxy.short_measure.get_rate_noupdate())
                        enough_speed = vs.bitrate * 1.3
                        if proxy_speed < enough_speed:
                            k = int((1.3 - proxy_speed / float(vs.bitrate)) * 10)
                            buffer_time = 10 + k * 5
                            if DEBUG:
                                log('>>> vod::sustainable: k', k, 'proxy_speed', proxy_speed, 'enough_speed', enough_speed, 'bitrate', vs.bitrate)
                        else:
                            buffer_time = 5
                        need = int(buffer_time * vs.bitrate)
                        if self.outbuf_minsize is not None:
                            need += self.outbuf_minsize * 3
                        if left < need:
                            need = left
                        avail = self.get_available_length(self.stream_pos)
                        ready = avail >= need
                        if ready and proxy_speed < enough_speed:
                            if DEBUG:
                                log('vod::sustainable: reset wait_proxy_flag flag on ready: proxy_speed', proxy_speed, 'enough_speed', enough_speed)
                            self.wait_proxy_flag = False
                            self.stop_proxy(finish_piece=True)
                        self.skip_underrun_timeout = 1
                        self.prebufprogress = min(1.0, avail / float(need))
                        if DEBUG:
                            log('vod::sustainable: buffer_time', buffer_time, 'proxy_speed', proxy_speed, 'need', need, 'avail', avail, 'outbuf_minsize', self.outbuf_minsize, 'left', left, 'outbuflen', self.outbuflen, 'ready', ready, 'stream_pos', self.stream_pos, 'outbufpos', self.outbufpos, 'progress', self.prebufprogress)
                else:
                    if self.http_support is not None:
                        self.http_support.start_video_support(min_speed=self.min_http_support_speed())
                    if self.paused_pos is None:
                        self.paused_pos = vs.playback_pos
                    self.sustainable_counter += 1
                    if self.sustainable_counter > 10:
                        self.sustainable_counter = 0
                        high_range_length = vs.get_high_range_length()
                        have_length = len(filter(lambda n: self.has[n], vs.generate_range((self.paused_pos, self.paused_pos + high_range_length))))
                        if DEBUG:
                            log('vod::refill_buffer:sustainable: self.sustainable_counter', self.sustainable_counter, 'high_range_length', high_range_length, 'have_length', have_length)
                        self.prebufprogress = min(1.0, float(have_length) / max(1, high_range_length))
                        ready = have_length >= high_range_length
                    else:
                        ready = False
                        num_immediate_packets = 0
                        high_range_length = vs.get_high_range_length()
                        for piece in vs.generate_range((self.paused_pos, self.paused_pos + high_range_length)):
                            if self.has[piece]:
                                num_immediate_packets += 1
                                if num_immediate_packets >= high_range_length:
                                    break
                            else:
                                break
                        else:
                            self.prebufprogress = 1.0
                            ready = True

                        if DEBUG:
                            log('vod:refill_buffer:sustainable: sustainable_counter', self.sustainable_counter, 'high_range_length', high_range_length, 'paused_pos', self.paused_pos, 'num_immediate_packets', num_immediate_packets)
                        if not ready:
                            ready = num_immediate_packets >= high_range_length
                return ready

        if self.outbuflen < mx:
            fill_from_proxy()
            while self.outbuflen < mx:
                got_piece = fill_from_pieces()
                if not got_piece:
                    break
                fill_from_proxy()

        if self.refill_buffer_counter == 0 and self.wait_proxy_flag:
            history_len = 5
            stable_size = int(vs.bitrate) * self.player_buffer_time * 2
            is_stable = False
            hlen = len(self.outbuf_history)
            if hlen >= history_len:
                for i in xrange(hlen - history_len, hlen):
                    if self.outbuf_history[i] < stable_size:
                        break
                else:
                    is_stable = True

            log('vod::refill_buffer: waiting for proxy: is_stable', is_stable, 'outbuflen', self.outbuflen, 'buffer_time', self.outbuflen / vs.bitrate, 'history_len', history_len, 'stable_size', stable_size, 'history', self.outbuf_history)
            if is_stable:
                self.wait_proxy_flag = False
                self.outbuf_history = []
                self.stop_proxy(finish_piece=True)
                self.unpause_p2p()
                self.http_support.start_video_support(min_speed=self.min_http_support_speed())
            else:
                self.outbuf_history.append(self.outbuflen)
        now = time.time()
        if self.outbuf_minsize is None:
            min_size = 1
        else:
            min_size = self.outbuf_minsize
        skip_http_start = False
        if self.outbuflen < min_size and self.has_http_support():
            if self.playback_started:
                speed = {'min_speed_start_proxy': vs.bitrate * 0.7,
                 'min_speed_start_non_proxy': vs.bitrate * 0.5,
                 'min_speed_start': vs.bitrate * 0.5,
                 'min_speed_fail': vs.bitrate * 0.8,
                 'timeout': 6,
                 'callback': self.proxy_speed_callback}
            else:
                speed = {'min_speed_start': self.min_http_support_speed(),
                 'min_speed_fail': vs.bitrate * MIN_HTTP_PROXY_SPEED_FAIL,
                 'timeout': SPEED_GAIN_TIMEOUT,
                 'callback': self.proxy_speed_callback}
            if DEBUG:
                log('vod::refill_buffer: buffer low, start proxy: outbufpos', self.outbufpos, 'playback_started', self.playback_started, 'outbuflen', self.outbuflen, 'mx', mx, 'speed', speed)
            respect_reserved_pieces = not self.playback_started
            if self.start_proxy(pos=self.outbufpos, speed=speed, respect_reserved_pieces=respect_reserved_pieces):
                if self.playback_started:
                    if DEBUG:
                        log('vod::refill_buffer: proxy started, stop others')
                    self.wait_proxy_flag = True
                    self.outbuf_history = []
                    self.pause_p2p()
                    self.http_support.stop_video_support(stop=True)
                    skip_http_start = True
        if not self.playback_started and not vs.live_streaming:
            return

        def high_range_underrun():
            for piece in vs.generate_high_range():
                if not self.has[piece]:
                    break
            else:
                return None

            if DEBUG_BUFFERING:
                log('vod::high_range_underrun: missing hr piece', piece)
            return piece

        missing_high_range_piece = high_range_underrun()
        if not skip_http_start and not self.wait_proxy_flag and self.playback_started and self.has_http_support() and self.refill_buffer_counter == 0:
            if self.done():
                self.http_support.stop_video_support()
            elif missing_high_range_piece is not None:
                min_speed = self.min_http_support_speed()
                self.http_support.start_video_support(min_speed=min_speed)
            elif not self.bt1download.downloader.has_downloaders():
                min_speed = self.min_http_support_speed()
                self.http_support.start_video_support(min_speed=min_speed)
            else:
                self.http_support.stop_video_support()
        if vs.pausable and buffer_underrun():
            sus = sustainable()
            if not sus:
                if DEBUG:
                    log('vod::refill_buffer: BUFFER UNDERRUN -- PAUSING')
                self.prebufprogress = 0.0
                self.pause(autoresume=True)
                self.rawserver.add_task(lambda : self.autoresume(sustainable), 0.3)
                if self.start_playback is not None:
                    vs.increase_high_range()
                else:
                    try:
                        high_range_length = vs.get_high_range_length()
                        pieces = [ p for p in vs.generate_range((self.paused_pos, vs.normalize(self.paused_pos + high_range_length))) ]
                        if DEBUG:
                            log('vod::refill_buffer: cancel pieces out of high range: paused_pos', self.paused_pos, 'high_range_length', high_range_length, 'pieces', pieces)
                        self.bt1download.downloader.cancel_piece_download(pieces, allowrerequest=True, include_pieces=True)
                    except:
                        print_exc()

                    if self.has_http_support():
                        self.http_support.playback_pos_changed(vs.playback_pos)

    def get_available_length(self, pos):
        vs = self.videostatus
        avail_len = 0
        p = pos
        self.proxy_cond.acquire()
        try:
            for bstart, bdata in self.proxy_buf.iteritems():
                bend = bstart + len(bdata) - 1
                if bstart <= p <= bend:
                    length = bend - p + 1
                    avail_len += length
                    p += length
                    if DEBUG:
                        log('vod::get_available_length: got from proxy before piece data: pos', pos, 'p', p, 'len', length, 'avail', avail_len, 'bstart', bstart, 'bend', bend)
                    break

            while True:
                got_piece_data = False
                index, offset = self.piecepos_from_bytepos(vs, p)
                if DEBUG:
                    log('vod::get_available_length: check piece: p', p, 'index', index, 'offset', offset)
                for i in xrange(index, vs.last_piece + 1):
                    if self.have_piece(i):
                        if i == vs.last_piece:
                            length = vs.last_piecelen
                        elif i == vs.first_piece:
                            length = vs.first_piecelen
                        else:
                            length = vs.piecelen
                        if i == index:
                            length -= offset
                        avail_len += length
                        p += length
                        if DEBUG:
                            log('vod::get_available_length: got from piece: pos', pos, 'p', p, 'len', length, 'avail', avail_len, 'piece', i)
                        got_piece_data = True
                    else:
                        if DEBUG:
                            log('vod::get_available_length: no piece: p', p, 'index', i)
                        break
                else:
                    if DEBUG:
                        log('vod::get_available_length: reached last piece, break')
                    break

                if not got_piece_data:
                    break
                for bstart, bdata in self.proxy_buf.iteritems():
                    bend = bstart + len(bdata) - 1
                    if bstart <= p <= bend:
                        length = bend - p + 1
                        avail_len += length
                        if DEBUG:
                            log('vod::get_available_length: got from proxy after piece data: pos', pos, 'p', p, 'len', length, 'avail', avail_len, 'bstart', bstart, 'bend', bend)
                        break

        finally:
            self.proxy_cond.release()

        if DEBUG:
            log('vod::get_available_length: pos', pos, 'avail', avail_len)
        return avail_len

    def video_refillbuf_rawtask(self):
        self.refill_buffer()
        self.rawserver.add_task(self.video_refillbuf_rawtask, self.REFILL_INTERVAL)

    def pop(self, max_size = None, find_mpegps_start = False):
        vs = self.videostatus
        while True:
            while vs.prebuffering and not self.done():
                self.data_ready.wait()

            while not self.outbuf and not self.done():
                self.data_ready.wait()

            if self.outbuf_minsize is not None and (self.last_resume is None or time.time() - self.last_resume >= SKIP_UNDERRUN_TIMEOUT):
                while self.outbuflen < self.outbuf_minsize and self.outbufpos < vs.selected_movie['size'] and not self.done():
                    self.data_ready.wait()

                max_size = min(max_size, self.outbuflen - self.outbuf_minsize * 3)
                if max_size < self.outbuf_minsize:
                    max_size = self.outbuf_minsize
                if DEBUG:
                    log('vod::pop: adjust max size: outbuflen', self.outbuflen, 'min_size', self.outbuf_minsize, 'max_size', max_size)
            if not self.outbuf:
                if DEBUG:
                    log('vod::pop: return none')
                piecetup = None
            else:
                bad_piece = False
                start_pos = None
                total_length = 0
                total_data = ''
                last_index = None
                if DEBUG:
                    log('vod::pop: read data from outbuf')
                while self.outbuf:
                    piecetup = self.outbuf.pop(0)
                    self.stat_outbuf.pop(0)
                    index, pos, data = piecetup
                    if find_mpegps_start:
                        sync_bytes = chr(0) + chr(0) + chr(1) + chr(186)
                        packet_start = data.find(sync_bytes)
                        log('>>>pop: find mpeg-ps packet start: sync_bytes', sync_bytes, 'pos', packet_start)
                        if packet_start == -1:
                            log('>>>pop: mpeg-ps: skip piece')
                            bad_piece = True
                            break
                        data = data[packet_start:]
                        log('>>>pop: mpeg-ps: got piece: len', len(data), 'data', data[:40])
                    length = len(data)
                    if DEBUG:
                        log('vod::pop: index', index)
                    if max_size is not None and total_length + length > max_size:
                        offset = total_length + length - max_size
                        newpos = pos + length - offset
                        newdata = data[-offset:]
                        data = data[:-offset]
                        oldlength = length
                        length = len(data)
                        if DEBUG:
                            log('vod::pop: trim chunk to max size: pos', pos, 'oldlen', oldlength, 'max_size', max_size, 'offset', offset, 'total_len', total_length, 'newlen', length, 'newpos', newpos)
                        self.outbuf.insert(0, (index, newpos, newdata))
                        self.stat_outbuf.insert(0, (index, newpos, len(newdata)))
                    if start_pos is None:
                        start_pos = pos
                    total_data += data
                    last_index = index
                    total_length += length
                    self.outbuflen -= length
                    self.playbackrate.update_rate(length)
                    vs.last_read_pos = index
                    vs.playback_pos_real = index
                    self.report_playback_pos(index)
                    if DEBUG_BUFFERING:
                        log('vod::pop: outbufpos', self.outbufpos, 'piece', index, 'pos', pos, 'start_pos', start_pos, 'len', length, 'total_len', total_length, 'min_size', self.outbuf_minsize, 'max_size', max_size, 'outbuflen', self.outbuflen)
                    if not vs.live_streaming and not start_pos <= self.stream_pos <= start_pos + total_length:
                        if DEBUG:
                            log('vod::pop: wrong piece popped, discard: stream_pos', self.stream_pos, 'piece', index, 'start_pos', start_pos, 'total_len', total_length)
                        bad_piece = True
                        break
                    if max_size is None:
                        break
                    if total_length >= max_size:
                        if DEBUG:
                            log('vod::pop: stop popping, max size reached: total_length', total_length, 'max_size', max_size)
                        break

                if bad_piece:
                    continue
                piecetup = (last_index, start_pos, total_data)
            break

        self.last_pop = time.time()
        outbuflen = self.outbuflen
        if False and piecetup is not None and vs.pausable:
            limit = int(self.player_buffer_time * vs.bitrate)
            if outbuflen < limit:
                if outbuflen > 0:
                    delay = min(0.1, 0.2 * outbuflen / limit)
                else:
                    delay = 0.1
                if DEBUG:
                    log('vod::pop: delaying pop to player: outbuflen', outbuflen, 'delay', delay)
                time.sleep(delay)
        return piecetup

    def notify_playable(self):
        self.prebufprogress = 1.0
        self.playable = True
        if self.usernotified:
            return
        self.usernotified = True
        mimetype = self.get_mimetype()
        complete = self.piecepicker.am_I_complete()
        if complete:
            endstream = None
            filename = self.videoinfo['outpath']
        else:
            stream = MovieTransportStreamWrapper(self)
            if self.videostatus.live_streaming and self.videostatus.authparams['authmethod'] != LIVE_AUTHMETHOD_NONE:
                intermedstream = AuthStreamWrapper(stream, self.authenticator)
                endstream = VariableReadAuthStreamWrapper(intermedstream, self.authenticator.get_piece_length())
            else:
                endstream = stream
            filename = None
        if DEBUG:
            log('vod::notify_playable: calling', self.vodeventfunc)
        try:
            self.vodeventfunc(self.videoinfo, VODEVENT_START, {'complete': complete,
             'filename': filename,
             'mimetype': mimetype,
             'stream': endstream,
             'length': self.size(),
             'bitrate': self.videostatus.bitrate})
        except:
            log_exc()

    def get_stats(self):
        s = {'played': self.stat_playedpieces,
         'late': self.stat_latepieces,
         'dropped': self.stat_droppedpieces,
         'stall': self.stat_stalltime,
         'pos': self.videostatus.playback_pos,
         'prebuf': self.stat_prebuffertime,
         'pp': self.piecepicker.stats,
         'videostatus': self.piecepicker.videostatus,
         'extra_videostatus': self.piecepicker.extra_videostatus,
         'pieces': self.stat_pieces.pop_completed(),
         'firstpiece': self.videostatus.first_piece,
         'npieces': self.videostatus.movie_numpieces,
         'numhave': self.videostatus.numhave,
         'completed': self.videostatus.completed,
         'outbuf': self.stat_outbuf[:],
         'proxybuf': self.stat_proxy_buf}
        return s

    def get_prebuffering_progress(self):
        return self.prebufprogress

    def is_playable(self):
        if not self.playable or self.videostatus.prebuffering:
            self.playable = self.prebufprogress == 1.0 and self.enough_buffer()
        return self.playable

    def get_playable_after(self):
        return self.expected_buffering_time()

    def get_duration(self):
        return 1.0 * self.videostatus.selected_movie['size'] / self.videostatus.bitrate

    def live_invalidate_piece(self, index):
        if DEBUG:
            log('vod::live_invalidate_piece: index', index)
        self.piecepicker.downloader.live_invalidate(index)
        self.videostatus.live_invalidate_piece(index)

    def live_invalidate_piece_globally(self, piece, mevirgin = False):
        raise Exception, 'old method'
        self.piecepicker.invalidate_piece(piece)
        self.piecepicker.downloader.live_invalidate(piece, mevirgin)

    def live_invalidate_piece_ranges_globally(self, toinvalidateranges, toinvalidateset):
        raise Exception, 'old method'
        for s, e in toinvalidateranges:
            for piece in xrange(s, e + 1):
                self.piecepicker.invalidate_piece(piece)

        self.piecepicker.downloader.live_invalidate_ranges(toinvalidateranges, toinvalidateset)

    def piece_from_live_source(self, index, data):
        if self.authenticator is not None:
            return self.authenticator.verify(data, index=index)
        else:
            return True
