#Embedded file name: ACEStream\Core\APIImplementation\DownloadImpl.pyo
import sys
import os
import copy
import binascii
import hashlib
import pickle
import struct
import time
from traceback import print_stack, print_exc
from threading import RLock, Condition, Event, Thread, currentThread
from ACEStream.Core.DownloadState import DownloadState
from ACEStream.Core.DownloadConfig import DownloadStartupConfig
from ACEStream.Core.simpledefs import *
from ACEStream.Core.exceptions import *
from ACEStream.Core.osutils import *
from ACEStream.Core.APIImplementation.SingleDownload import SingleDownload
from ACEStream.Core.APIImplementation.DirectDownload import DirectDownload
import ACEStream.Core.APIImplementation.maketorrent as maketorrent
from ACEStream.Video.utils import videoextdefaults
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.Utilities.EncryptedStorage import EncryptedStorageStream
from ACEStream.GlobalConfig import globalConfig
DEBUG = False

class DownloadImpl:

    def __init__(self, dltype, session, tdef = None, main_url = None):
        self.dllock = RLock()
        self.dltype = dltype
        self.error = None
        self.progressbeforestop = 0.0
        self.session = session
        self.pstate_for_restart = None
        self.dlruntimeconfig = None
        self.starting = False
        self.sd = None
        self.dd = None
        if self.dltype == DLTYPE_TORRENT:
            if tdef is None:
                raise ValueError('Missing tdef')
            self.filepieceranges = []
            self.tdef = tdef.copy()
            self.tdef.readonly = True
            self.log_prefix = 'DownloadImpl::' + str(DLTYPE_TORRENT) + ':' + binascii.hexlify(self.tdef.get_infohash()) + ':'
            if tdef.can_save() != 1:
                self.encrypted_storage = False
            else:
                self.encrypted_storage = globalConfig.get_value('encrypted_storage')
        elif self.dltype == DLTYPE_DIRECT:
            if main_url is None:
                raise ValueError('Missing url')
            self.main_url = main_url
            self.urlhash = hashlib.sha1(main_url).digest()
            self.pstate_filename = None
            self.pstate_content_length = None
            self.log_prefix = 'DownloadImpl::' + str(DLTYPE_DIRECT) + ':' + binascii.hexlify(self.urlhash) + ':'
            self.encrypted_storage = False
        else:
            raise ValueError('Unknown download type ' + str(dltype))
        self.speed_stats = {'up_total': 0.0,
         'up_count': 0,
         'down_total': 0.0,
         'down_count': 0}

    def setup(self, dcfg = None, pstate = None, initialdlstatus = None, lmcreatedcallback = None, lmvodeventcallback = None):
        if self.dltype == DLTYPE_TORRENT:
            self._setup_torrent_download(dcfg, pstate, initialdlstatus, lmcreatedcallback, lmvodeventcallback)
        elif self.dltype == DLTYPE_DIRECT:
            self._setup_direct_download(dcfg, pstate, initialdlstatus, lmcreatedcallback, lmvodeventcallback)

    def _setup_direct_download(self, dcfg, pstate, initialdlstatus, lmcreatedcallback, lmvodeventcallback):
        self.dllock.acquire()
        try:
            if DEBUG:
                if pstate is None:
                    resumedata = None
                else:
                    resumedata = pstate['engineresumedata']
                log(self.log_prefix + '_setup_direct_download: resumedata', resumedata)
            if dcfg is None:
                cdcfg = DownloadStartupConfig()
            else:
                cdcfg = dcfg
            self.dlconfig = copy.copy(cdcfg.dlconfig)
            for k, v in self.session.get_current_startup_config_copy().sessconfig.iteritems():
                self.dlconfig.setdefault(k, v)

            if pstate is not None:
                if pstate.has_key('dlstate'):
                    self.progressbeforestop = pstate['dlstate'].get('progress', 0.0)
                path = None
                resumedata = pstate.get('engineresumedata', None)
                if resumedata is not None:
                    self.pstate_content_length = resumedata.get('size', None)
                    filename = resumedata.get('filename', None)
                    if filename is not None:
                        self.pstate_filename = os.path.join(self.dlconfig['saveas'], filename)
                        if DEBUG:
                            log(self.log_prefix + '_setup_direct_download: pstate_filename', self.pstate_filename)
            if initialdlstatus != DLSTATUS_STOPPED:
                if pstate is None or pstate['dlstate']['status'] != DLSTATUS_STOPPED:
                    self.starting = True
                    self.create_direct_download_engine(pstate, lmcreatedcallback, lmvodeventcallback)
            self.pstate_for_restart = pstate
        except Exception as e:
            log_exc()
            self.set_error(e)
        finally:
            self.dllock.release()

    def _setup_torrent_download(self, dcfg, pstate, initialdlstatus, lmcreatedcallback, lmvodeventcallback):
        self.dllock.acquire()
        try:
            torrentdef = self.get_def()
            metainfo = torrentdef.get_metainfo()
            self.correctedinfoname = fix_filebasename(torrentdef.get_name_as_unicode())
            if dcfg is not None and DEBUG:
                log(self.log_prefix + '_setup_torrent_download: selected_files', dcfg.dlconfig['selected_files'])
            if DEBUG:
                log(self.log_prefix + '_setup_torrent_download: piece size', metainfo['info']['piece length'])
            itrackerurl = self.session.get_internal_tracker_url()
            metainfo = self.tdef.get_metainfo()
            usingitracker = False
            if DEBUG:
                if pstate is None:
                    resumedata = None
                else:
                    resumedata = pstate['engineresumedata']
                log(self.log_prefix + '_setup_torrent_download: resumedata', resumedata)
            if itrackerurl.endswith('/'):
                slashless = itrackerurl[:-1]
            else:
                slashless = itrackerurl
            if 'announce' in metainfo and (metainfo['announce'] == itrackerurl or metainfo['announce'] == slashless):
                usingitracker = True
            elif 'announce-list' in metainfo:
                for tier in metainfo['announce-list']:
                    if itrackerurl in tier or slashless in tier:
                        usingitracker = True
                        break

            if usingitracker:
                if DEBUG:
                    log(self.log_prefix + '_setup_torrent_download: using internal tracker')
                self.session.add_to_internal_tracker(self.tdef)
            elif DEBUG:
                log(self.log_prefix + '_setup_torrent_download: not using internal tracker')
            if dcfg is None:
                cdcfg = DownloadStartupConfig()
            else:
                cdcfg = dcfg
            if cdcfg.is_hidden():
                cdcfg.set_max_conns(10)
                cdcfg.set_max_conns_to_initiate(10)
            self.dlconfig = copy.copy(cdcfg.dlconfig)
            for k, v in self.session.get_current_startup_config_copy().sessconfig.iteritems():
                self.dlconfig.setdefault(k, v)

            self.set_filepieceranges(metainfo)
            self.dlruntimeconfig = {}
            self.dlruntimeconfig['max_desired_upload_rate'] = 0
            self.dlruntimeconfig['max_desired_download_rate'] = 0
            if DEBUG:
                log(self.log_prefix + '_setup_torrent_download: initialdlstatus', `(self.tdef.get_name_as_unicode())`, initialdlstatus)
            self.dlconfig['cs_keys'] = self.tdef.get_cs_keys_as_ders()
            self.dlconfig['permid'] = self.session.get_permid()
            if self.dlconfig['cs_keys']:
                log(self.log_prefix + '_setup_torrent_download: this is a closed swarm')
            if pstate is not None and pstate.has_key('dlstate'):
                self.progressbeforestop = pstate['dlstate'].get('progress', 0.0)
            if initialdlstatus != DLSTATUS_STOPPED:
                if pstate is None or pstate['dlstate']['status'] != DLSTATUS_STOPPED:
                    self.starting = True
                    self.create_engine_wrapper(lmcreatedcallback, pstate, lmvodeventcallback, initialdlstatus)
            self.pstate_for_restart = pstate
            self.dllock.release()
        except Exception as e:
            log_exc()
            self.set_error(e)
            self.dllock.release()

    def create_direct_download_engine(self, pstate, lmcreatedcallback, lmvodeventcallback):
        config = copy.copy(self.dlconfig)
        fileinfo = {'destdir': config['saveas'],
         'filename': None,
         'size': None,
         'mimetype': None,
         'duration': None,
         'bitrate': None,
         'usercallback': None,
         'userevents': []}
        if self.dlconfig['mode'] == DLMODE_VOD:
            vod_usercallback_wrapper = lambda event, params: self.session.uch.perform_vod_usercallback(self, self.dlconfig['vod_usercallback'], event, params)
            fileinfo['usercallback'] = vod_usercallback_wrapper
            fileinfo['userevents'] = self.dlconfig['vod_userevents'][:]
        if pstate is not None:
            resumedata = pstate['engineresumedata']
        else:
            resumedata = None
        if self.dlconfig.has_key('direct_download_url'):
            download_url = self.dlconfig['direct_download_url']
        else:
            download_url = None
        finished_func = self.dlconfig.get('download_finished_callback', None)
        failed_func = self.dlconfig.get('download_failed_callback', None)
        if failed_func is not None:
            failed_func_wrapper = lambda err: failed_func(self, err)
        else:
            failed_func_wrapper = None
        network_create_direct_download_engine_lambda = lambda : self.network_create_direct_download_engine(self.main_url, download_url, self.urlhash, config, fileinfo, resumedata, lmcreatedcallback, lmvodeventcallback, finished_func, failed_func_wrapper)
        self.session.lm.rawserver.add_task(network_create_direct_download_engine_lambda, 0)

    def network_create_direct_download_engine(self, main_url, download_url, urlhash, config, fileinfo, pstate, lmcreatedcallback, lmvodeventcallback, finished_func, failed_func):
        self.dllock.acquire()
        try:
            multihandler = self.session.lm.multihandler
            self.dd = DirectDownload(main_url, download_url, urlhash, config, multihandler, fileinfo, pstate, lmvodeventcallback, self.set_error, finished_func, failed_func)
            self.starting = False
            if lmcreatedcallback is not None:
                lmcreatedcallback(self, self.dd, self.error, pstate)
        except Exception as e:
            self.set_error(e)
            if DEBUG:
                print_exc()
        finally:
            self.dllock.release()

    def create_engine_wrapper(self, lmcreatedcallback, pstate, lmvodeventcallback, initialdlstatus = None):
        if DEBUG:
            log(self.log_prefix + 'create_engine_wrapper: ---')
        infohash = self.get_def().get_infohash()
        metainfo = copy.deepcopy(self.get_def().get_metainfo())
        metainfo['info']['name'] = self.correctedinfoname
        if 'name.utf-8' in metainfo['info']:
            metainfo['info']['name.utf-8'] = self.correctedinfoname
        multihandler = self.session.lm.multihandler
        listenport = self.session.get_listen_port()
        vapath = self.session.get_video_analyser_path()
        kvconfig = copy.copy(self.dlconfig)
        kvconfig['initialdlstatus'] = initialdlstatus
        kvconfig['encrypted_storage'] = self.encrypted_storage
        live = self.get_def().get_live()
        vodfileindex = {'index': -1,
         'inpath': None,
         'bitrate': 0.0,
         'live': live,
         'usercallback': None,
         'userevents': [],
         'outpath': None}
        extra_vodfileindex = []
        if self.dlconfig['mode'] == DLMODE_VOD or self.dlconfig['video_source']:
            multi = False
            if 'files' in metainfo['info']:
                multi = True
            if multi and len(self.dlconfig['selected_files']) == 0:
                raise VODNoFileSelectedInMultifileTorrentException()
            if not multi:
                file = self.get_def().get_name()
                idx = -1
                bitrate = self.get_def().get_ts_bitrate()
                prebuf_pieces = self.get_def().get_ts_prebuf_pieces()
                if DEBUG:
                    log(self.log_prefix + 'create_engine_wrapper: single, file', file, 'idx', idx, 'bitrate', bitrate, 'prebuf_pieces', prebuf_pieces)
            else:
                file = self.dlconfig['selected_files'][0]
                idx = self.get_def().get_index_of_file_in_files(file)
                bitrate = self.get_def().get_ts_bitrate(idx)
                prebuf_pieces = self.get_def().get_ts_prebuf_pieces(idx)
                if DEBUG:
                    log(self.log_prefix + 'create_engine_wrapper: multi, file', file, 'idx', idx, 'bitrate', bitrate, 'prebuf_pieces', prebuf_pieces)
            mimetype = self.get_mimetype(file)
            vod_usercallback_wrapper = lambda event, params: self.session.uch.perform_vod_usercallback(self, self.dlconfig['vod_usercallback'], event, params)
            vodfileindex['index'] = idx
            vodfileindex['inpath'] = file
            vodfileindex['bitrate'] = bitrate
            vodfileindex['mimetype'] = mimetype
            vodfileindex['usercallback'] = vod_usercallback_wrapper
            vodfileindex['userevents'] = self.dlconfig['vod_userevents'][:]
            vodfileindex['prebuf_pieces'] = prebuf_pieces
            if DEBUG:
                log(self.log_prefix + 'create_engine_wrapper: vodfileindex', vodfileindex)
            if multi:
                extra_vodfileindex = self.init_extra_vodfileindexes(vod_usercallback_wrapper)
        elif live:
            raise LiveTorrentRequiresUsercallbackException()
        elif self.dlconfig['mode'] == DLMODE_SVC:
            multi = False
            if 'files' in metainfo['info']:
                multi = True
            if multi and len(self.dlconfig['selected_files']) == 0:
                raise VODNoFileSelectedInMultifileTorrentException()
            files = self.dlconfig['selected_files']
            idx = []
            for file in files:
                idx.append(self.get_def().get_index_of_file_in_files(file))

            bitrate = self.get_def().get_bitrate(files[0])
            mimetype = self.get_mimetype(file)
            vod_usercallback_wrapper = lambda event, params: self.session.uch.perform_vod_usercallback(self, self.dlconfig['vod_usercallback'], event, params)
            vodfileindex['index'] = idx
            vodfileindex['inpath'] = files
            vodfileindex['bitrate'] = bitrate
            vodfileindex['mimetype'] = mimetype
            vodfileindex['usercallback'] = vod_usercallback_wrapper
            vodfileindex['userevents'] = self.dlconfig['vod_userevents'][:]
        else:
            vodfileindex['mimetype'] = 'application/octet-stream'
        if DEBUG:
            log(self.log_prefix + 'create_engine_wrapper: vodfileindex', vodfileindex)
        network_create_engine_wrapper_lambda = lambda : self.network_create_engine_wrapper(infohash, metainfo, kvconfig, multihandler, listenport, vapath, vodfileindex, extra_vodfileindex, lmcreatedcallback, pstate, lmvodeventcallback)
        self.session.lm.rawserver.add_task(network_create_engine_wrapper_lambda, 0)

    def network_create_engine_wrapper(self, infohash, metainfo, kvconfig, multihandler, listenport, vapath, vodfileindex, extra_vodfileindex, lmcallback, pstate, lmvodeventcallback):
        self.dllock.acquire()
        try:
            self.sd = SingleDownload(infohash, metainfo, kvconfig, multihandler, self.session.lm.get_ext_ip, listenport, vapath, vodfileindex, extra_vodfileindex, self.set_error, pstate, lmvodeventcallback, self.session.lm.hashcheck_done)
            self.starting = False
            sd = self.sd
            exc = self.error
            if lmcallback is not None:
                lmcallback(self, sd, exc, pstate)
        finally:
            self.dllock.release()

    def got_duration(self, duration, from_player = True):
        self.dllock.acquire()
        try:
            if self.dltype == DLTYPE_TORRENT and self.sd is not None:
                self.sd.got_duration(duration, from_player)
            elif self.dltype == DLTYPE_DIRECT and self.dd is not None:
                self.dd.got_duration(duration, from_player)
        finally:
            self.dllock.release()

    def live_seek(self, pos):
        self.dllock.acquire()
        try:
            if self.dltype != DLTYPE_TORRENT:
                log(self.log_prefix + 'live_seek: not a p2p download')
                return
            if self.sd is None:
                log(self.log_prefix + 'live_seek: sd is none')
                return
            if not self.tdef.get_live():
                log(self.log_prefix + 'live_seek: not a live')
                return
            self.sd.live_seek(pos)
        finally:
            self.dllock.release()

    def got_metadata(self, metadata):
        self.dllock.acquire()
        try:
            if self.dltype == DLTYPE_TORRENT and self.sd is not None:
                if DEBUG:
                    log(self.log_prefix + 'got_metadata: metadata', metadata)
                self.sd.got_metadata(metadata)
        finally:
            self.dllock.release()

    def got_http_seeds(self, http_seeds):
        self.dllock.acquire()
        try:
            if self.dltype == DLTYPE_TORRENT and self.sd is not None:
                if DEBUG:
                    log(self.log_prefix + 'got_http_seeds: http_seeds', http_seeds)
                self.sd.got_http_seeds(http_seeds)
        finally:
            self.dllock.release()

    def init_extra_vodfileindexes(self, vod_usercallback_wrapper):
        extra_vodfileindex = []
        filelist = self.get_def().get_files()
        for fi in self.dlconfig['extra_files']:
            file = filelist[fi]
            if DEBUG:
                log(self.log_prefix + 'init_extra_vodfileindexes: add extra file fileindex:', fi, 'file', file)
            newvodfileindex = {'index': fi,
             'inpath': file,
             'bitrate': self.get_def().get_ts_bitrate(fi),
             'prebuf_pieces': self.get_def().get_ts_prebuf_pieces(fi),
             'live': self.get_def().get_live(),
             'usercallback': vod_usercallback_wrapper,
             'userevents': self.dlconfig['vod_userevents'][:],
             'outpath': None,
             'mimetype': self.get_mimetype(file)}
            extra_vodfileindex.append(newvodfileindex)

        return extra_vodfileindex

    def get_def(self):
        return self.tdef

    def update_tdef(self, tdef):
        if DEBUG:
            log(self.log_prefix + 'update_tdef: new infohash', binascii.hexlify(tdef.get_infohash()))
        self.tdef = tdef.copy()
        self.tdef.readonly = True

    def get_hash(self):
        if self.dltype == DLTYPE_TORRENT:
            return self.tdef.get_infohash()
        if self.dltype == DLTYPE_DIRECT:
            return self.urlhash

    def get_download_id(self):
        if self.sd is not None:
            return self.sd.get_download_id()
        elif self.dd is not None:
            return self.dd.get_download_id()
        else:
            return

    def set_state_callback(self, usercallback, getpeerlist = False):
        self.dllock.acquire()
        try:
            network_get_state_lambda = lambda : self.network_get_state(usercallback, getpeerlist)
            self.session.lm.rawserver.add_task(network_get_state_lambda, 0.0)
        finally:
            self.dllock.release()

    def network_get_state(self, usercallback, getpeerlist, sessioncalling = False):
        self.dllock.acquire()
        try:
            if self.dltype == DLTYPE_TORRENT:
                swarmcache = None
                if self.pstate_for_restart is not None and self.pstate_for_restart.has_key('dlstate'):
                    swarmcache = self.pstate_for_restart['dlstate'].get('swarmcache', None)
                if self.sd is None:
                    if self.starting:
                        status = DLSTATUS_WAITING4HASHCHECK
                    else:
                        status = DLSTATUS_STOPPED
                    if self.pstate_for_restart is not None and self.pstate_for_restart.has_key('dlstate'):
                        files_completed = self.pstate_for_restart['dlstate'].get('files_completed', None)
                    else:
                        files_completed = None
                    ds = DownloadState(self, status, self.error, self.progressbeforestop, swarmcache=swarmcache, files_completed=files_completed)
                else:
                    swarmcache = self.sd.get_swarmcache() or swarmcache
                    status, stats, logmsgs, coopdl_helpers, coopdl_coordinator, paused = self.sd.get_stats(getpeerlist)
                    if stats is not None and 'stats' in stats:
                        self.speed_stats['up_total'] += stats['up']
                        self.speed_stats['up_count'] += 1
                        self.speed_stats['down_total'] += stats['down']
                        self.speed_stats['down_count'] += 1
                    ds = DownloadState(self, status, self.error, 0.0, stats=stats, filepieceranges=self.filepieceranges, logmsgs=logmsgs, coopdl_helpers=coopdl_helpers, coopdl_coordinator=coopdl_coordinator, swarmcache=swarmcache, paused=paused)
                    self.progressbeforestop = ds.get_progress()
            elif self.dltype == DLTYPE_DIRECT:
                if self.dd is None:
                    if self.starting:
                        status = DLSTATUS_WAITING4HASHCHECK
                    else:
                        status = DLSTATUS_STOPPED
                    ds = DownloadState(self, status, self.error, self.progressbeforestop)
                else:
                    status, stats = self.dd.get_stats()
                    ds = DownloadState(self, status, self.error, 0.0, stats=stats)
                    self.progressbeforestop = ds.get_progress()
            if sessioncalling:
                return ds
            self.session.uch.perform_getstate_usercallback(usercallback, ds, self.sesscb_get_state_returncallback)
        finally:
            self.dllock.release()

    def sesscb_get_state_returncallback(self, usercallback, when, newgetpeerlist):
        self.dllock.acquire()
        try:
            if DEBUG:
                log(self.log_prefix + 'sesscb_get_state_returncallback: when', when, 'newgetpeerlist', newgetpeerlist)
            if when > 0.0:
                network_get_state_lambda = lambda : self.network_get_state(usercallback, newgetpeerlist)
                if self.sd is None:
                    self.session.lm.rawserver.add_task(network_get_state_lambda, when)
                else:
                    self.sd.dlrawserver.add_task(network_get_state_lambda, when)
        finally:
            self.dllock.release()

    def pause(self, pause, close_connections = False):
        if DEBUG:
            log(self.log_prefix + 'pause: pause', pause, 'close_connections', close_connections)
        self.dllock.acquire()
        try:
            network_pause_lambda = lambda : self.network_pause(pause, close_connections)
            self.session.lm.rawserver.add_task(network_pause_lambda, 0.0)
        finally:
            self.dllock.release()

    def network_pause(self, pause, close_connections):
        if DEBUG:
            log(self.log_prefix + 'network_pause: pause', pause, 'close_connections', close_connections)
        self.dllock.acquire()
        try:
            if self.sd is not None:
                self.sd.pause(pause, close_connections)
            elif self.dd is not None:
                pass
        finally:
            self.dllock.release()

    def stop(self):
        self.stop_remove(removestate=False, removecontent=False)

    def stop_remove(self, removestate = False, removecontent = False):
        if DEBUG:
            log(self.log_prefix + 'stop_remove: removestate', removestate, 'removecontent', removecontent)
        self.dllock.acquire()
        try:
            network_stop_lambda = lambda : self.network_stop(removestate, removecontent)
            self.session.lm.rawserver.add_task(network_stop_lambda, 0.0)
        finally:
            self.dllock.release()

    def network_stop(self, removestate, removecontent):
        if DEBUG:
            log(self.log_prefix + 'network_stop: ---')
        self.dllock.acquire()
        try:
            dlhash = self.get_hash()
            pstate = self.network_get_persistent_state()
            if self.sd is not None:
                pstate['engineresumedata'] = self.sd.shutdown()
                self.sd = None
                self.pstate_for_restart = pstate
                if DEBUG:
                    log(self.log_prefix + 'network_stop: shutdown self.sd and update self.pstate_for_restart: resumedata', pstate['engineresumedata'])
            elif self.dd is not None:
                pstate['engineresumedata'] = self.dd.shutdown()
                self.dd = None
                self.pstate_for_restart = pstate
                if pstate['engineresumedata'] is not None:
                    self.pstate_content_length = pstate['engineresumedata'].get('size', None)
                    filename = pstate['engineresumedata'].get('filename', None)
                    if filename is not None:
                        self.pstate_filename = os.path.join(self.dlconfig['saveas'], filename)
                if DEBUG:
                    log(self.log_prefix + 'network_stop: shutdown self.dd and update self.pstate_for_restart: resumedata', pstate['engineresumedata'])
            elif self.pstate_for_restart is not None:
                if DEBUG:
                    log(self.log_prefix + 'network_stop: Reusing previously saved engineresume data for checkpoint')
                pstate['engineresumedata'] = self.pstate_for_restart['engineresumedata']
            if removestate:
                if self.encrypted_storage:
                    contentdest = os.path.join(self.dlconfig['saveas'], binascii.hexlify(self.get_hash()))
                else:
                    contentdest = self.get_content_dest(False)
                if DEBUG:
                    log(self.log_prefix + 'network_stop: contentdest', contentdest)
                self.session.uch.perform_removestate_callback(self.dltype, dlhash, contentdest, removecontent)
            return (dlhash, pstate)
        finally:
            self.dllock.release()

    def restart(self, initialdlstatus = None, new_tdef = None):
        if DEBUG:
            log(self.log_prefix + 'restart: ---')
        self.dllock.acquire()
        try:
            self.starting = True
            if new_tdef is not None:
                self.update_tdef(new_tdef)
            network_restart_lambda = lambda : self.network_restart(initialdlstatus)
            self.session.lm.rawserver.add_task(network_restart_lambda, 0.0)
        finally:
            self.dllock.release()

    def network_restart(self, initialdlstatus = None):
        if DEBUG:
            if self.pstate_for_restart is None:
                resumedata = None
            else:
                resumedata = self.pstate_for_restart['engineresumedata']
            log(self.log_prefix + 'network_restart: pstate_for_restart', not not self.pstate_for_restart, 'resumedata', resumedata)
        self.dllock.acquire()
        try:
            if self.sd is not None and self.sd.dlmode != self.dlconfig['mode']:
                if DEBUG:
                    log(self.log_prefix + 'network_restart: sd is running in different mode, stop and restart: sd.dlmode', self.sd.dlmode, 'new_mode', self.dlconfig['mode'])
                self.network_stop(removestate=False, removecontent=False)
            if self.dltype == DLTYPE_TORRENT:
                if self.sd is None:
                    self.error = None
                    self.create_engine_wrapper(self.session.lm.network_engine_wrapper_created_callback, pstate=self.pstate_for_restart, lmvodeventcallback=self.session.lm.network_vod_event_callback, initialdlstatus=initialdlstatus)
                else:
                    if DEBUG:
                        log(self.log_prefix + 'network_restart: SingleDownload already running')
                    self.starting = False
                    metainfo = self.get_def().get_metainfo()
                    multi = False
                    if 'files' in metainfo['info']:
                        multi = True
                    vodfileindex = None
                    extra_vodfileindex = None
                    if self.dlconfig['mode'] == DLMODE_VOD:
                        if multi:
                            if multi and len(self.dlconfig['selected_files']) == 0:
                                raise VODNoFileSelectedInMultifileTorrentException()
                            file = self.dlconfig['selected_files'][0]
                            idx = self.get_def().get_index_of_file_in_files(file)
                            vod_usercallback_wrapper = lambda event, params: self.session.uch.perform_vod_usercallback(self, self.dlconfig['vod_usercallback'], event, params)
                            vodfileindex = {'index': idx,
                             'inpath': file,
                             'bitrate': self.get_def().get_ts_bitrate(idx),
                             'prebuf_pieces': self.get_def().get_ts_prebuf_pieces(idx),
                             'live': self.get_def().get_live(),
                             'usercallback': vod_usercallback_wrapper,
                             'userevents': self.dlconfig['vod_userevents'][:],
                             'outpath': None,
                             'mimetype': self.get_mimetype(file)}
                            extra_vodfileindex = self.init_extra_vodfileindexes(vod_usercallback_wrapper)
                        else:
                            vodfileindex = self.sd.dow.videoinfo
                            vodfileindex['bitrate'] = self.get_def().get_ts_bitrate()
                            vodfileindex['prebuf_pieces'] = self.get_def().get_ts_prebuf_pieces()
                    if DEBUG:
                        log(self.log_prefix + 'network_restart: vodfileindex', vodfileindex)
                        log(self.log_prefix + 'network_restart: extra_vodfileindex', extra_vodfileindex)
                    try:
                        self.sd.restart(initialdlstatus, vodfileindex, extra_vodfileindex, self.dlconfig['mode'], self.get_files_priority())
                    except:
                        log_exc()

            elif self.dltype == DLTYPE_DIRECT:
                if self.dd is None:
                    self.error = None
                    self.create_direct_download_engine(pstate=self.pstate_for_restart, lmcreatedcallback=self.session.lm.network_engine_wrapper_created_callback, lmvodeventcallback=self.session.lm.network_vod_event_callback)
                else:
                    self.error = None
                    self.starting = False
                    if self.dlconfig['mode'] == DLMODE_VOD:
                        vod_usercallback = lambda event, params: self.session.uch.perform_vod_usercallback(self, self.dlconfig['vod_usercallback'], event, params)
                    else:
                        vod_usercallback = None
                    finished_func = self.dlconfig.get('download_finished_callback', None)
                    failed_func = self.dlconfig.get('download_failed_callback', None)
                    if failed_func is not None:
                        failed_func_wrapper = lambda err: failed_func(self, err)
                    else:
                        failed_func_wrapper = None
                    self.dd.restart(self.dlconfig['mode'], vod_usercallback, finished_func, failed_func_wrapper)
        finally:
            self.dllock.release()

    def set_max_desired_speed(self, direct, speed):
        if self.dlruntimeconfig is None:
            return
        if DEBUG:
            log(self.log_prefix + 'set_max_desired_speed: direction', direct, 'speed', speed)
        self.dllock.acquire()
        if direct == UPLOAD:
            self.dlruntimeconfig['max_desired_upload_rate'] = speed
        else:
            self.dlruntimeconfig['max_desired_download_rate'] = speed
        self.dllock.release()

    def get_max_desired_speed(self, direct):
        if self.dlruntimeconfig is None:
            return 0
        self.dllock.acquire()
        try:
            if direct == UPLOAD:
                return self.dlruntimeconfig['max_desired_upload_rate']
            return self.dlruntimeconfig['max_desired_download_rate']
        finally:
            self.dllock.release()

    def get_dest_files(self, exts = None, get_all = False):
        if self.dltype == DLTYPE_DIRECT:
            if self.dd is not None:
                path = self.dd.get_dest_path()
            else:
                path = self.pstate_filename
            if path is None:
                return []
            else:
                return [(None, path)]
        elif self.dltype == DLTYPE_TORRENT:

            def get_ext(filename):
                prefix, ext = os.path.splitext(filename)
                if ext != '' and ext[0] == '.':
                    ext = ext[1:]
                return ext

            self.dllock.acquire()
            try:
                f2dlist = []
                metainfo = self.tdef.get_metainfo()
                if 'files' not in metainfo['info']:
                    file_path = self.get_content_dest()
                    ext = get_ext(file_path)
                    if exts is None or ext in exts:
                        if self.encrypted_storage:
                            file_path = os.path.join(self.dlconfig['saveas'], binascii.hexlify(self.get_hash()))
                        f2dlist.append((None, file_path))
                else:
                    if not get_all and len(self.dlconfig['selected_files']) > 0:
                        fnlist = []
                        for f_name in self.dlconfig['selected_files']:
                            f_index = self.tdef.get_index_of_file_in_files(f_name)
                            fnlist.append((f_name, f_index))

                    else:
                        fnlist = self.tdef.get_files_with_indexes(exts=exts)
                    for filename, fileindex in fnlist:
                        filerec = maketorrent.get_torrentfilerec_from_metainfo(filename, metainfo)
                        savepath = maketorrent.torrentfilerec2savefilename(filerec)
                        diskfn = maketorrent.savefilenames2finaldest(self.get_content_dest(), savepath)
                        ext = get_ext(diskfn)
                        if exts is None or ext in exts:
                            if self.encrypted_storage:
                                diskfn = os.path.join(self.dlconfig['saveas'], binascii.hexlify(self.get_hash()))
                            f2dtuple = (filename, diskfn)
                            f2dlist.append(f2dtuple)

                return f2dlist
            finally:
                self.dllock.release()

    def network_checkpoint(self):
        self.dllock.acquire()
        try:
            pstate = self.network_get_persistent_state()
            resumedata = None
            if self.dltype == DLTYPE_TORRENT and self.sd is not None:
                resumedata = self.sd.checkpoint()
            elif self.dltype == DLTYPE_DIRECT and self.dd is not None:
                resumedata = self.dd.checkpoint()
            pstate['engineresumedata'] = resumedata
            return (self.get_hash(), pstate)
        finally:
            self.dllock.release()

    def network_get_persistent_state(self):
        pstate = {}
        pstate['version'] = PERSISTENTSTATE_CURRENTVERSION
        if self.dltype == DLTYPE_TORRENT:
            pstate['metainfo'] = self.tdef.get_metainfo()
        elif self.dltype == DLTYPE_DIRECT:
            pstate['url'] = self.main_url
        dlconfig = copy.copy(self.dlconfig)
        dlconfig['vod_usercallback'] = None
        dlconfig['download_finished_callback'] = None
        dlconfig['download_failed_callback'] = None
        dlconfig['mode'] = DLMODE_NORMAL
        pstate['dlconfig'] = dlconfig
        pstate['dlstate'] = {}
        ds = self.network_get_state(None, True, sessioncalling=True)
        pstate['dlstate']['status'] = ds.get_status()
        pstate['dlstate']['progress'] = ds.get_progress()
        pstate['dlstate']['swarmcache'] = ds.get_swarmcache()
        pstate['dlstate']['files_completed'] = ds.get_files_completed()
        if DEBUG:
            log(self.log_prefix + 'network_get_persistent_state: status', dlstatus_strings[ds.get_status()], 'progress', ds.get_progress())
        pstate['engineresumedata'] = None
        return pstate

    def get_coopdl_role_object(self, role):
        role_object = None
        self.dllock.acquire()
        try:
            if self.sd is not None:
                role_object = self.sd.get_coopdl_role_object(role)
        finally:
            self.dllock.release()

        return role_object

    def set_error(self, e):
        self.dllock.acquire()
        self.error = e
        self.dllock.release()

    def set_filepieceranges(self, metainfo):
        selected_files = self.dlconfig['selected_files'][:]
        filelist = self.get_def().get_files()
        for fi in self.dlconfig['extra_files']:
            selected_files.append(filelist[fi])

        length, self.filepieceranges = maketorrent.get_length_filepieceranges_from_metainfo(metainfo, selected_files)
        if DEBUG:
            log(self.log_prefix + 'set_filepieceranges: self.selected_files', self.dlconfig['selected_files'], 'selected_files', selected_files, 'self.filepieceranges', self.filepieceranges)

    def get_content_dest(self, selected_file = False):
        if self.dltype == DLTYPE_TORRENT:
            filename = self.correctedinfoname
            if selected_file and len(self.dlconfig['selected_files']) == 1:
                filename = os.path.join(filename, self.dlconfig['selected_files'][0])
            return os.path.join(self.dlconfig['saveas'], filename)
        if self.dltype == DLTYPE_DIRECT:
            if self.dd is not None:
                path = self.dd.get_dest_path()
            else:
                path = self.pstate_filename
            return path

    def get_type(self):
        return self.dltype

    def get_content_length(self, selected_file = None):
        if self.dltype == DLTYPE_TORRENT:
            return self.tdef.get_length(selected_file)
        if self.dltype == DLTYPE_DIRECT:
            if self.dd is not None:
                return self.dd.get_content_length()
            else:
                return self.pstate_content_length
        else:
            raise ValueError('Unknown download type ' + str(self.dltype))

    def can_save_content(self):
        if self.dltype != DLTYPE_TORRENT:
            if DEBUG:
                log(self.log_prefix + ':can_save_content: not a torrent download, allow saving')
            return True
        return self.tdef.can_save()

    def save_content(self, save_path, save_index):
        save_type = self.can_save_content()
        if save_type == 0:
            return False
        log('>>>save_content: path', save_path, 'type', save_type)
        ds = self.network_get_state(usercallback=None, getpeerlist=False, sessioncalling=True)
        completed_files = ds.get_files_completed()
        try:
            file_completed = completed_files[save_index]
        except IndexError:
            if DEBUG:
                log(self.log_prefix + 'save_content: bad file index: infohash', binascii.hexlify(self.get_hash()), 'save_index', save_index, 'completed_files', completed_files)
            return False

        if not file_completed:
            if DEBUG:
                log(self.log_prefix + 'save_content: file is not completed: infohash', binascii.hexlify(self.get_hash()), 'save_index', save_index, 'completed_files', completed_files)
            return False
        content_path = os.path.join(self.dlconfig['saveas'], binascii.hexlify(self.get_hash()))
        if not os.path.isfile(content_path):
            if DEBUG:
                log(self.log_prefix + 'save_content: file not found: content_path', content_path)
            return False
        metainfo = self.tdef.get_metainfo()
        if 'files' not in metainfo['info']:
            file_length = self.tdef.get_length()
            offset = 0
        else:
            file_list = self.tdef.get_files_with_length()
            offset = 0
            for path, length, index in file_list:
                if index == save_index:
                    file_length = length
                    break
                offset += length

        if DEBUG:
            log(self.log_prefix + 'save_content: save_path', save_path, 'save_path', save_path, 'content_path', content_path, 'file_length', file_length, 'offset', offset)
        piecelen = self.tdef.get_piece_length()
        places = None
        if self.sd is not None and self.sd.dow is not None:
            places = self.sd.dow.storagewrapper.places.copy()
        out = None
        stream = None
        try:
            decrypt = save_type == 1
            tmp_save_path = save_path + '.part'
            out = open(tmp_save_path, 'wb')
            if not decrypt:
                duration = self.tdef.get_ts_duration(save_index)
                if duration is None:
                    duration = 0
                meta = {'hash': self.get_hash(),
                 'file_length': file_length,
                 'offset': offset,
                 'piecelen': piecelen,
                 'duration': duration,
                 'provider': self.tdef.get_provider()}
                meta_dump = pickle.dumps(meta)
                meta_len = len(meta_dump)
                out.write(struct.pack('l', meta_len))
                out.write(meta_dump)
                log('>>>save: write metadata: meta_len', meta_len, 'meta', meta, 'dump', meta_dump)
            t = time.time()
            read_size = piecelen
            stream = EncryptedStorageStream(content_path, self.get_hash(), file_length, offset, piecelen, places, decrypt)
            while True:
                buf = stream.read(read_size)
                if not buf:
                    break
                out.write(buf)

            log('>>>save: done: time', time.time() - t)
            log('>>>save: rename', tmp_save_path, 'to', save_path)
            out.close()
            out = None
            os.rename(tmp_save_path, save_path)
        except:
            log('>>>save: failed')
            print_exc()
        finally:
            if out is not None:
                out.close
            if stream is not None:
                stream.close()

        return True

    def get_mimetype(self, file):
        prefix, ext = os.path.splitext(file)
        ext = ext.lower()
        mimetype = None
        if sys.platform == 'win32':
            try:
                from ACEStream.Video.utils import win32_retrieve_video_play_command
                mimetype, playcmd = win32_retrieve_video_play_command(ext, file)
                if DEBUG:
                    log(self.log_prefix + 'get_mimetype: Win32 reg said MIME type is', mimetype)
            except:
                if DEBUG:
                    log_exc()

        else:
            try:
                import mimetypes
                homedir = get_home_dir()
                homemapfile = os.path.join(homedir, '.mimetypes')
                mapfiles = [homemapfile] + mimetypes.knownfiles
                mimetypes.init(mapfiles)
                mimetype, encoding = mimetypes.guess_type(file)
                if DEBUG:
                    log(self.log_prefix + 'get_mimetype: /etc/mimetypes+ said MIME type is', mimetype, file)
            except:
                log_exc()

        if mimetype is None:
            if ext == '.avi':
                mimetype = 'video/avi'
            elif ext == '.mpegts' or ext == '.ts':
                mimetype = 'video/mp2t'
            elif ext == '.mkv':
                mimetype = 'video/x-matroska'
            elif ext == '.ogg' or ext == '.ogv':
                mimetype = 'video/ogg'
            elif ext == '.oga':
                mimetype = 'audio/ogg'
            elif ext == '.webm':
                mimetype = 'video/webm'
            else:
                mimetype = 'video/mpeg'
        return mimetype
