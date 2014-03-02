#Embedded file name: ACEStream\Core\APIImplementation\SingleDownload.pyo
import sys
import os
import time
import copy
import pickle
import socket
import binascii
import random
from base64 import b64encode
from types import StringType, ListType, IntType
from traceback import print_stack
from threading import Event, Lock, currentThread
from ACEStream.Core.simpledefs import *
from ACEStream.Core.exceptions import *
from ACEStream.Core.BitTornado.__init__ import createPeerID
from ACEStream.Core.BitTornado.download_bt1 import BT1Download
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
from ACEStream.Core.Video.VideoStatus import VideoStatus
from ACEStream.Core.DecentralizedTracking.repex import RePEXer
from ACEStream.Core.Utilities.logger import log, log_exc
SPECIAL_VALUE = 481
DEBUG = False

class SingleDownload:

    def __init__(self, infohash, metainfo, kvconfig, multihandler, get_extip_func, listenport, videoanalyserpath, vodfileindex, extra_vodfileindex, set_error_func, pstate, lmvodeventcallback, lmhashcheckcompletecallback):
        self.dow = None
        self.set_error_func = set_error_func
        self.videoinfo = None
        self.videostatus = None
        self.metainfo = metainfo
        self.dlmode = kvconfig['mode']
        self.extra_vodfileindex = extra_vodfileindex
        self.lmvodeventcallback = lmvodeventcallback
        self.lmhashcheckcompletecallback = lmhashcheckcompletecallback
        self.logmsgs = []
        self._hashcheckfunc = None
        self._getstatsfunc = None
        self.infohash = infohash
        self.b64_infohash = b64encode(infohash)
        self.repexer = None
        self.log_prefix = 'sd::' + binascii.hexlify(self.infohash) + ':'
        self.lock = Lock()
        self.stopping = False
        self.download_id = binascii.hexlify(self.infohash) + '-' + str(long(time.time())) + '-' + str(random.randint(0, 100000))
        try:
            self.dldoneflag = Event()
            self.dlrawserver = multihandler.newRawServer(infohash, self.dldoneflag)
            self.lmvodeventcallback = lmvodeventcallback
            if pstate is not None:
                self.hashcheckfrac = pstate['dlstate']['progress']
            else:
                self.hashcheckfrac = 0.0
            self.peerid = createPeerID()
            self.dow = BT1Download(self.hashcheckprogressfunc, self.finishedfunc, self.fatalerrorfunc, self.nonfatalerrorfunc, self.logerrorfunc, self.dldoneflag, kvconfig, metainfo, infohash, self.peerid, self.dlrawserver, get_extip_func, listenport, videoanalyserpath)
            file = self.dow.saveAs(self.save_as)
            if vodfileindex is not None:
                index = vodfileindex['index']
                if index == -1:
                    index = 0
                outpathindex = self.dow.get_dest(index)
                vodfileindex['outpath'] = outpathindex
                self.videoinfo = vodfileindex
                if 'live' in metainfo['info']:
                    authparams = metainfo['info']['live']
                else:
                    authparams = None
                self.videostatus = VideoStatus(metainfo['info']['piece length'], self.dow.files, vodfileindex, authparams)
                self.videoinfo['status'] = self.videostatus
                self.dow.set_videoinfo(vodfileindex, self.videostatus)
            if DEBUG:
                log(self.log_prefix + '__init__: setting vodfileindex', vodfileindex)
            if kvconfig['initialdlstatus'] == DLSTATUS_REPEXING:
                if pstate is not None and pstate.has_key('dlstate'):
                    swarmcache = pstate['dlstate'].get('swarmcache', {})
                else:
                    swarmcache = {}
                self.repexer = RePEXer(self.infohash, swarmcache)
            else:
                self.repexer = None
            if pstate is None:
                resumedata = None
            else:
                resumedata = pstate['engineresumedata']
            self._hashcheckfunc = self.dow.initFiles(resumedata=resumedata)
        except Exception as e:
            self.fatalerrorfunc(e)

    def get_download_id(self):
        return self.download_id

    def set_extra_files(self, extra_vodfileindex):
        if self.dow is None:
            return
        if extra_vodfileindex is None:
            extra_vodfileindex = []
        extra_vs = []
        for vodfileindex in extra_vodfileindex:
            index = vodfileindex['index']
            if index == -1:
                index = 0
            vodfileindex['outpath'] = self.dow.get_dest(index)
            vs = VideoStatus(self.metainfo['info']['piece length'], self.dow.files, vodfileindex, authparams=None, is_extra=True)
            extra_vs.append(vs)

        self.dow.picker.set_extra_videostatus(extra_vs)

    def get_bt1download(self):
        return self.dow

    def save_as(self, name, length, saveas, isdir, islive = False):
        if DEBUG:
            log(self.log_prefix + 'save_as(', `name`, length, `saveas`, isdir, ')')
        try:
            if not os.access(saveas, os.F_OK):
                os.mkdir(saveas)
            path = os.path.join(saveas, name)
            if isdir and not os.path.isdir(path):
                os.mkdir(path)
            return path
        except Exception as e:
            self.fatalerrorfunc(e)

    def perform_hashcheck(self, complete_callback):
        if DEBUG:
            log(self.log_prefix + 'perform_hashcheck: thread', currentThread().getName())
        self.lock.acquire()
        try:
            self._getstatsfunc = SPECIAL_VALUE
            self.lmhashcheckcompletecallback = complete_callback
            if self._hashcheckfunc is None:
                if DEBUG:
                    log(self.log_prefix + 'perform_hashcheck: _hashcheckfunc is none, sd is shutted down: thread', currentThread().getName())
            else:
                if DEBUG:
                    log(self.log_prefix + 'perform_hashcheck: run _hashcheckfunc:', self._hashcheckfunc, 'thread', currentThread().getName())
                complete_callback_lambda = lambda sd = self, success = True: complete_callback(sd, success)
                self._hashcheckfunc(complete_callback_lambda)
        except Exception as e:
            self.fatalerrorfunc(e)
        finally:
            self.lock.release()

    def hashcheck_done(self):
        if DEBUG:
            log(self.log_prefix + 'hashcheck_done: dow', self.dow, 'thread', currentThread().getName())
        self.lock.acquire()
        try:
            if self.dow is None:
                log(self.log_prefix + 'hashcheck_done: dow is None, shutted down while hashchecking, skip start: thread', currentThread().getName())
                return
            if DEBUG:
                t = time.time()
            self.dow.startEngine(vodeventfunc=self.lmvodeventcallback)
            if DEBUG:
                log(self.log_prefix + 'hashcheck_done: dow.startEngine() time', time.time() - t)
            if DEBUG:
                t = time.time()
            self._getstatsfunc = self.dow.startStats()
            if DEBUG:
                log(self.log_prefix + 'hashcheck_done: dow.startStats() time', time.time() - t)
            if self.dlmode == DLMODE_VOD:
                self.set_extra_files(self.extra_vodfileindex)
            repexer = self.repexer
            if repexer is None:
                if DEBUG:
                    t = time.time()
                self.dow.startRerequester()
                if DEBUG:
                    log(self.log_prefix + 'hashcheck_done: dow.startRerequester() time', time.time() - t)
            else:
                self.hook_repexer()
            if DEBUG:
                t = time.time()
            self.dlrawserver.start_listening(self.dow.getPortHandler())
            if DEBUG:
                log(self.log_prefix + 'hashcheck_done: dlrawserver.start_listening() time', time.time() - t)
        except Exception as e:
            self.fatalerrorfunc(e)
        finally:
            self.lock.release()

    def set_max_speed(self, direct, speed, auto_limit = False, callback = None):
        if self.dow is not None:
            if DEBUG:
                log(self.log_prefix + 'set_max_speed: direction', direct, 'speed', speed)
            if direct == UPLOAD:
                self.dow.setUploadRate(speed, networkcalling=True)
            else:
                self.dow.setDownloadRate(rate=speed, auto_limit=auto_limit, networkcalling=True)
        if callback is not None:
            callback(direct, speed)

    def set_player_buffer_time(self, value):
        if self.dow is not None:
            if DEBUG:
                log(self.log_prefix + 'set_player_buffer_time:', value)
            self.dow.set_player_buffer_time(value)

    def set_live_buffer_time(self, value):
        if self.dow is not None:
            if DEBUG:
                log(self.log_prefix + 'set_live_buffer_time:', value)
            self.dow.set_live_buffer_time(value)

    def set_max_conns_to_initiate(self, nconns, callback):
        if self.dow is not None:
            if DEBUG:
                log(self.log_prefix + 'set_max_conns_to_initiate', `(self.dow.response['info']['name'])`)
            self.dow.setInitiate(nconns, networkcalling=True)
        if callback is not None:
            callback(nconns)

    def set_max_uploads(self, value):
        if self.dow is not None:
            if DEBUG:
                log(self.log_prefix + 'set_max_uploads:', value)
            self.dow.setConns(value)

    def set_max_conns(self, nconns, callback):
        if self.dow is not None:
            if DEBUG:
                log(self.log_prefix + 'set_max_conns', `(self.dow.response['info']['name'])`)
            self.dow.setMaxConns(nconns, networkcalling=True)
        if callback is not None:
            callback(nconns)

    def set_wait_sufficient_speed(self, value):
        if self.dow is not None:
            if DEBUG:
                log(self.log_prefix + 'set_wait_sufficient_speed:', value)
            self.dow.set_wait_sufficient_speed(value)

    def set_http_support(self, value):
        if self.dow is not None:
            if DEBUG:
                log(self.log_prefix + 'set_http_support:', value)
            self.dow.set_http_support(value)

    def get_stats(self, getpeerlist):
        logmsgs = self.logmsgs[:]
        coopdl_helpers = []
        coopdl_coordinator = None
        paused = False
        if self.dow is not None:
            paused = self.dow.isPaused()
            if self.dow.helper is not None:
                coopdl_coordinator = self.dow.helper.get_coordinator_permid()
            if self.dow.coordinator is not None:
                peerreclist = self.dow.coordinator.network_get_asked_helpers_copy()
                for peerrec in peerreclist:
                    coopdl_helpers.append(peerrec['permid'])

        if self._getstatsfunc is None:
            return (DLSTATUS_WAITING4HASHCHECK,
             None,
             logmsgs,
             coopdl_helpers,
             coopdl_coordinator,
             paused)
        elif self._getstatsfunc == SPECIAL_VALUE:
            stats = {}
            stats['frac'] = self.hashcheckfrac
            return (DLSTATUS_HASHCHECKING,
             stats,
             logmsgs,
             coopdl_helpers,
             coopdl_coordinator,
             paused)
        else:
            if self.repexer is not None:
                status = DLSTATUS_REPEXING
            else:
                status = None
            return (status,
             self._getstatsfunc(getpeerlist=getpeerlist),
             logmsgs,
             coopdl_helpers,
             coopdl_coordinator,
             paused)

    def get_infohash(self):
        return self.infohash

    def checkpoint(self):
        if self.dow is not None:
            return self.dow.checkpoint()
        else:
            return

    def shutdown(self, blocking = True):
        if DEBUG:
            log(self.log_prefix + 'shutdown: thread', currentThread().getName())
        resumedata = None
        if self.stopping:
            if DEBUG:
                log(self.log_prefix + 'shutdown: already stopping, exit: thread', currentThread().getName())
            return
        if DEBUG:
            log(self.log_prefix + 'shutdown, acquire lock: blocking', blocking, 'thread', currentThread().getName())
        locked = self.lock.acquire(blocking)
        if DEBUG:
            log(self.log_prefix + 'shutdown, got lock: locked', locked, 'thread', currentThread().getName())
        self.stopping = True
        try:
            if self.dow is not None:
                if self.repexer:
                    repexer = self.unhook_repexer()
                    repexer.repex_aborted(self.infohash, DLSTATUS_STOPPED)
                self.dldoneflag.set()
                self.dlrawserver.shutdown()
                resumedata = self.dow.shutdown()
                if DEBUG:
                    log(self.log_prefix + 'shutdown: resumedata', resumedata)
                self.dow = None
            if self._hashcheckfunc is not None:
                if DEBUG:
                    log(self.log_prefix + 'shutdown: reset _hashcheckfunc:', self._hashcheckfunc, 'thread', currentThread().getName())
                self._hashcheckfunc = None
            if self._getstatsfunc is None or self._getstatsfunc == SPECIAL_VALUE:
                log(self.log_prefix + 'shutdown: shutdown on hashcheck: _getstatsfunc', self._getstatsfunc, 'thread', currentThread().getName())
                self.lmhashcheckcompletecallback(self, success=False)
            elif DEBUG:
                log(self.log_prefix + 'shutdown: regular shutdown: _getstatsfunc', self._getstatsfunc, 'thread', currentThread().getName())
        finally:
            if DEBUG:
                log(self.log_prefix + 'shutdown, release lock: thread', currentThread().getName())
            self.stopping = False
            if locked:
                self.lock.release()

        return resumedata

    def got_duration(self, duration, from_player):
        if DEBUG:
            log(self.log_prefix + 'got_duration: duration', duration, 'from_player', from_player)
        if self.dow is not None:
            return self.dow.got_duration(duration, from_player)

    def live_seek(self, pos):
        if DEBUG:
            log(self.log_prefix + 'live_seek: pos', pos)
        if self.dow is None:
            log(self.log_prefix + 'live_seek: dow is none')
            return
        self.dow.live_seek(pos)

    def got_metadata(self, metadata):
        if DEBUG:
            log(self.log_prefix + 'got_metadata: metadata', metadata)
        if self.dow is not None:
            return self.dow.got_metadata(metadata)

    def got_http_seeds(self, http_seeds):
        if DEBUG:
            log(self.log_prefix + 'got_http_seeds: http_seeds', http_seeds)
        if self.dow is not None:
            return self.dow.got_http_seeds(http_seeds)

    def pause(self, pause, close_connections = False):
        self.lock.acquire()
        try:
            if self.dow is not None:
                if DEBUG:
                    log(self.log_prefix + 'pause: pause', pause, 'close_connections', close_connections)
                if pause:
                    self.dow.Pause(close_connections)
                else:
                    self.dow.Unpause()
                return
        finally:
            self.lock.release()

    def restart(self, initialdlstatus = None, vodfileindex = None, extra_vodfileindex = None, dlmode = None, new_priority = None):
        self.lock.acquire()
        try:
            if self.dow is None:
                if DEBUG:
                    log(self.log_prefix + 'restart: shutted down, skip restart')
                return
            if self._getstatsfunc is None or self._getstatsfunc == SPECIAL_VALUE:
                if DEBUG:
                    log(self.log_prefix + 'restart: hashchecking, skip restart')
                return
        finally:
            self.lock.release()

        if DEBUG:
            log(self.log_prefix + 'restart: vodfileindex', vodfileindex, 'initialdlstatus', initialdlstatus)
        self.dow.Unpause()
        if 'live' in self.metainfo['info']:
            authparams = self.metainfo['info']['live']
        else:
            authparams = None
        if self.repexer and initialdlstatus != DLSTATUS_REPEXING:
            repexer = self.unhook_repexer()
            repexer.repex_aborted(self.infohash, initialdlstatus)
        elif vodfileindex is not None:
            index = vodfileindex['index']
            if index == -1:
                index = 0
            outpathindex = self.dow.get_dest(index)
            vodfileindex['outpath'] = outpathindex
            videostatus = VideoStatus(self.metainfo['info']['piece length'], self.dow.files, vodfileindex, authparams)
            self.dow.restartEngine(vodfileindex, videostatus, self.lmvodeventcallback, dlmode, new_priority)
            self.set_extra_files(extra_vodfileindex)
            if DEBUG:
                log(self.log_prefix + 'restart: fileselector priorities:', self.dow.fileselector.get_priorities())
            self._getstatsfunc = self.dow.startStats()
        else:
            vodfileindex = self.dow.videoinfo
            videostatus = VideoStatus(self.metainfo['info']['piece length'], self.dow.files, vodfileindex, authparams)
            self.dow.restartEngine(vodfileindex, videostatus, self.lmvodeventcallback, dlmode)
            self._getstatsfunc = self.dow.startStats()

    def get_swarmcache(self):
        if self.repexer is not None:
            return self.repexer.get_swarmcache()[0]

    def hook_repexer(self):
        repexer = self.repexer
        if repexer is None:
            return
        if self.dow is None:
            return
        self.dow.Pause()
        self.dow.startRerequester(paused=True)
        connecter, encoder = self.dow.connecter, self.dow.encoder
        connecter.repexer = repexer
        encoder.repexer = repexer
        rerequest = self.dow.createRerequester(repexer.rerequester_peers)
        repexer.repex_ready(self.infohash, connecter, encoder, rerequest)

    def unhook_repexer(self):
        repexer = self.repexer
        if repexer is None:
            return
        self.repexer = None
        if self.dow is not None:
            connecter, encoder = self.dow.connecter, self.dow.encoder
            connecter.repexer = None
            encoder.repexer = None
            self.dow.startRerequester()
            self.dow.Unpause()
        return repexer

    def ask_coopdl_helpers(self, peerreclist):
        if self.dow is not None:
            self.dow.coordinator.send_ask_for_help(peerreclist)

    def stop_coopdl_helpers(self, peerreclist):
        if self.dow is not None:
            self.dow.coordinator.send_stop_helping(peerreclist, force=True)

    def get_coopdl_role_object(self, role):
        if self.dow is not None:
            if role == COOPDL_ROLE_COORDINATOR:
                return self.dow.coordinator
            else:
                return self.dow.helper
        else:
            return

    def hashcheckprogressfunc(self, activity = '', fractionDone = 0.0):
        self.hashcheckfrac = fractionDone

    def finishedfunc(self):
        if DEBUG:
            log(self.log_prefix + 'finishedfunc called: download is complete *******************************')

    def fatalerrorfunc(self, data):
        log(self.log_prefix + ':fatalerrorfunc called', data)
        if type(data) == StringType:
            log(self.log_prefix + 'LEGACY CORE FATAL ERROR', data)
            print_stack()
            self.set_error_func(ACEStreamLegacyException(data))
        else:
            log_exc()
            self.set_error_func(data)
        self.shutdown(blocking=False)

    def nonfatalerrorfunc(self, e):
        log(self.log_prefix + 'nonfatalerrorfunc called', e)

    def logerrorfunc(self, msg):
        t = time.time()
        self.logmsgs.append((t, msg))
        if len(self.logmsgs) > 10:
            self.logmsgs.pop(0)
