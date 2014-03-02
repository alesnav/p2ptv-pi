#Embedded file name: ACEStream\Core\APIImplementation\DirectDownload.pyo
import os
import binascii
import time
import random
from threading import Event
from traceback import print_exc
from ACEStream.Core.simpledefs import *
from ACEStream.Core.DirectDownload.Storage import Storage
from ACEStream.Core.DirectDownload.Downloader import Downloader
from ACEStream.Core.DirectDownload.VODTransporter import VODTransporter
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False

class Statistics_Response:
    pass


class DirectDownload:

    def __init__(self, main_url, download_url, dlhash, config, multihandler, fileinfo, resumedata, vodeventcallback, set_error_func, finished_func, failed_func):
        self.main_url = main_url
        self.download_url = download_url
        self.dlhash = dlhash
        self.config = config
        self.dlmode = config['mode']
        self.fileinfo = fileinfo
        self.vodeventcallback = vodeventcallback
        self.set_error_func = set_error_func
        self.finished_func = finished_func
        self.failed_func = failed_func
        self.download_id = binascii.hexlify(self.dlhash) + '-' + str(long(time.time())) + '-' + str(random.randint(0, 100000))
        self.dldoneflag = Event()
        self.rawserver = multihandler.newRawServer(dlhash, self.dldoneflag)
        if download_url is not None:
            url = download_url
        else:
            url = main_url
        self.downloader = Downloader(url, dlhash, self.rawserver, self.failed)
        self.voddownload = None
        self.storage = None
        self.log_prefix = 'dd::' + binascii.hexlify(self.dlhash) + ':'
        predownload = self.config.get('predownload', False)
        if DEBUG:
            log(self.log_prefix + '__init__: predownload', predownload)
        if resumedata is None and predownload:
            self.downloader.predownload(self.init_predownloaded)
        else:
            callback = lambda content_length, mimetype: self.init(resumedata, content_length, mimetype)
            self.downloader.init(callback)

    def init_predownloaded(self, mimetype, filedata):
        if DEBUG:
            log(self.log_prefix + 'init_predownloaded: mimetype', mimetype, 'len', len(filedata))
        if self.dldoneflag.is_set():
            if DEBUG:
                log(self.log_prefix + 'init_predownloaded: done flag is set, exit')
            return
        ext = self.guess_extension_from_mimetype(mimetype)
        filename = binascii.hexlify(self.dlhash)
        if len(ext):
            filename += '.' + ext
        content_length = len(filedata)
        self.fileinfo['filename'] = filename
        self.fileinfo['size'] = content_length
        self.fileinfo['mimetype'] = mimetype
        temp_dir = os.path.join(self.config['buffer_dir'], binascii.hexlify(self.dlhash))
        if not os.path.isdir(temp_dir):
            os.mkdir(temp_dir)
        self.storage = Storage(self.dlhash, self.config, self.fileinfo, temp_dir, None, self.finished_callback, filedata=filedata)
        self.downloader.set_storage(self.storage)
        self.finished_callback()
        if self.dlmode == DLMODE_VOD:
            if DEBUG:
                log(self.log_prefix + 'init_predownloaded: starting in vod mode, but download is finished: fileinfo', self.fileinfo)
            self.vodeventcallback(self.fileinfo, VODEVENT_START, {'complete': True,
             'filename': self.storage.get_dest_path(),
             'mimetype': self.fileinfo['mimetype'],
             'stream': None,
             'length': self.storage.get_content_length(),
             'bitrate': self.fileinfo['bitrate']})

    def init(self, resumedata = None, content_length = None, mimetype = None):
        if DEBUG:
            log(self.log_prefix + 'init: resumedata', resumedata, 'content_length', content_length, 'mimetype', mimetype)
        if self.dldoneflag.is_set():
            if DEBUG:
                log(self.log_prefix + 'init: done flag is set, exit')
            return
        if content_length is None:
            content_length, mimetype = self.downloader.init()
        if resumedata is not None:
            if content_length != resumedata['size']:
                raise Exception('content length differs from resumedata')
            if mimetype != resumedata['mimetype']:
                raise Exception('mime type differs from resumedata')
            filename = resumedata['filename']
            duration = resumedata.get('duration', None)
            if duration:
                bitrate = content_length / duration
                self.fileinfo['duration'] = duration
                self.fileinfo['bitrate'] = bitrate
                if DEBUG:
                    log(self.log_prefix + '__init__: got duration from resumedata: main_url', self.main_url, 'duration', duration, 'bitrate', bitrate)
        else:
            ext = self.guess_extension_from_mimetype(mimetype)
            filename = binascii.hexlify(self.dlhash)
            if len(ext):
                filename += '.' + ext
        self.fileinfo['filename'] = filename
        self.fileinfo['size'] = content_length
        self.fileinfo['mimetype'] = mimetype
        temp_dir = os.path.join(self.config['buffer_dir'], binascii.hexlify(self.dlhash))
        if not os.path.isdir(temp_dir):
            os.mkdir(temp_dir)
        self.storage = Storage(self.dlhash, self.config, self.fileinfo, temp_dir, resumedata, self.finished_callback)
        self.downloader.set_storage(self.storage)
        completed = self.storage.is_finished()
        if completed:
            self.finished_callback()
        if self.dlmode == DLMODE_VOD:
            if completed:
                if DEBUG:
                    log(self.log_prefix + '__init__: starting in vod mode, but download is finished: fileinfo', self.fileinfo)
                self.vodeventcallback(self.fileinfo, VODEVENT_START, {'complete': True,
                 'filename': self.storage.get_dest_path(),
                 'mimetype': self.fileinfo['mimetype'],
                 'stream': None,
                 'length': self.storage.get_content_length(),
                 'bitrate': self.fileinfo['bitrate']})
            else:
                if DEBUG:
                    log(self.log_prefix + '__init__: starting in vod mode: fileinfo', self.fileinfo)
                self.voddownload = VODTransporter(self, self.dlhash, self.fileinfo, self.vodeventcallback)
                self.storage.add_got_data_observer(self.voddownload.got_data_observer)
        if not completed:
            self.downloader.start()

    def get_download_id(self):
        return self.download_id

    def guess_extension_from_mimetype(self, mimetype):
        if mimetype is None:
            mimetype = ''
        if mimetype == 'video/x-msvideo':
            ext = 'avi'
        elif mimetype == 'video/mp4':
            ext = 'mp4'
        elif mimetype == 'video/x-matroska':
            ext = 'mkv'
        elif mimetype == 'video/x-m4v':
            ext = 'm4v'
        elif mimetype == 'video/quicktime':
            ext = 'mov'
        elif mimetype == 'video/x-sgi-movie':
            ext = 'movie'
        elif mimetype == 'video/mpeg':
            ext = 'mpg'
        elif mimetype == 'application/ogg' or mimetype == 'video/ogg':
            ext = 'ogg'
        elif mimetype == 'video/x-flv':
            ext = 'flv'
        elif mimetype == 'video/webm':
            ext = 'webm'
        elif mimetype == 'video/x-ms-wmv':
            ext = 'wmv'
        else:
            if DEBUG:
                log(self.log_prefix + 'guess_extension_from_mimetype: unknown mimetype', mimetype)
            ext = 'mpg'
        if DEBUG:
            log(self.log_prefix + 'guess_extension_from_mimetype: mimetype', mimetype, 'ext', ext)
        return ext

    def finished_callback(self):
        if DEBUG:
            log(self.log_prefix + 'finished_callback: url', self.main_url)

        def _finished():
            if self.voddownload is not None:
                self.voddownload.complete()
            if self.finished_func is not None:
                self.finished_func(self.main_url, self.download_url, self.dlhash, self.fileinfo)

        self.rawserver.add_task(_finished, 0.0)

    def failed(self, err):
        if DEBUG:
            log(self.log_prefix + 'failed: url', self.main_url, 'err', err)
        if self.voddownload is not None:
            self.voddownload.shutdown()
            self.voddownload = None
        self.set_error_func(err)

        def _failed():
            if self.failed_func is not None:
                try:
                    self.failed_func(err)
                except:
                    if DEBUG:
                        print_exc()

        self.rawserver.add_task(_failed, 0.0)

    def got_duration(self, duration, from_player = True):
        if DEBUG:
            log(self.log_prefix + 'got_duration: main_url', self.main_url, 'duration', duration, 'fileinfo', self.fileinfo)
        if duration <= 0:
            if DEBUG:
                log(self.log_prefix + 'got_duration: bad duration')
            return
        cur_duration = self.fileinfo.get('duration', None)
        if cur_duration is not None:
            if cur_duration != duration:
                if DEBUG:
                    log(self.log_prefix + 'got_duration: duration does not match with metadata: main_url', self.main_url, 'cur_duration', cur_duration, 'duration', duration)
        else:
            bitrate = self.fileinfo['size'] / duration
            self.fileinfo['duration'] = duration
            self.fileinfo['bitrate'] = bitrate
            if self.voddownload is not None:
                self.voddownload.set_bitrate(bitrate)

    def get_stats(self):
        status = None
        stats = {}
        s = Statistics_Response()
        s.numSeeds = 0
        s.numPeers = 0
        s.httpSeeds = 0
        s.upTotal = 0
        s.downTotal = self.downloader.measure.get_total()
        s.httpDownTotal = s.downTotal
        stats['stats'] = s
        stats['up'] = 0
        if self.storage is None:
            stats['frac'] = 0
            finished = False
        else:
            stats['frac'] = self.storage.get_progress()
            finished = self.storage.is_finished()
        if finished:
            stats['vod_prebuf_frac'] = 1.0
            stats['vod_playable'] = True
            stats['vod_playable_after'] = 0.0
            stats['vod'] = False
            stats['down'] = 0
            stats['httpdown'] = 0
        else:
            s.numSeeds = 1
            s.httpSeeds = 1
            stats['down'] = self.downloader.measure.get_rate()
            stats['httpdown'] = stats['down']
            if self.voddownload is not None:
                stats['vod_prebuf_frac'] = self.voddownload.get_prebuffering_progress()
                stats['vod_playable'] = self.voddownload.is_playable()
                stats['vod_playable_after'] = self.voddownload.get_playable_after()
                stats['vod'] = True
            else:
                stats['vod_prebuf_frac'] = 0.0
                stats['vod_playable'] = False
                stats['vod_playable_after'] = float(2147483648L)
                stats['vod'] = False
        return (status, stats)

    def shutdown(self):
        if self.voddownload is not None:
            self.voddownload.shutdown()
            self.voddownload = None
        self.downloader.shutdown()
        if self.storage is not None:
            self.storage.close()
            self.storage = None
        self.dldoneflag.set()
        self.rawserver.shutdown()
        return self.checkpoint()

    def restart(self, dlmode, vodeventfunc, finished_func, failed_func):
        self.dlmode = dlmode
        self.fileinfo['usercallback'] = vodeventfunc
        self.finished_func = finished_func
        self.failed_func = failed_func
        if self.storage is None:
            try:
                self.init()
            except Exception as e:
                if DEBUG:
                    print_exc()
                self.failed(e)
                return

        if dlmode == DLMODE_VOD:
            if self.storage.is_finished():
                if DEBUG:
                    log(self.log_prefix + 'restart: restart in vod mode requested, but download is finished: fileinfo', self.fileinfo)
                self.vodeventcallback(self.fileinfo, VODEVENT_START, {'complete': True,
                 'filename': self.storage.get_dest_path(),
                 'mimetype': self.fileinfo['mimetype'],
                 'stream': None,
                 'length': self.storage.get_content_length(),
                 'bitrate': self.fileinfo['bitrate']})
            else:
                if self.voddownload is not None:
                    self.storage.remove_got_data_observer(self.voddownload.got_data_observer)
                    self.voddownload.shutdown()
                    self.voddownload = None
                    if DEBUG:
                        log(self.log_prefix + 'restart: voddownload is not None, stop current download')
                self.voddownload = VODTransporter(self, self.dlhash, self.fileinfo, self.vodeventcallback)
                self.storage.add_got_data_observer(self.voddownload.got_data_observer)
                if not self.downloader.is_running():
                    if DEBUG:
                        log(self.log_prefix + 'restart: downloader is not running, start it')
                    self.downloader.start()

    def checkpoint(self):
        if self.storage is None:
            return
        resumedata = self.storage.checkpoint()
        resumedata['mimetype'] = self.fileinfo['mimetype']
        resumedata['filename'] = self.fileinfo['filename']
        resumedata['duration'] = self.fileinfo['duration']
        return resumedata

    def get_dest_path(self):
        if self.storage is None:
            return
        return self.storage.get_dest_path()

    def get_content_length(self):
        if self.storage is None:
            return
        return self.storage.get_content_length()

    def set_wait_sufficient_speed(self, value):
        if self.voddownload is not None:
            self.voddownload.set_wait_sufficient_speed(value)

    def set_player_buffer_time(self, value):
        if self.voddownload is not None:
            self.voddownload.set_player_buffer_time(value)

    def set_live_buffer_time(self, value):
        if self.voddownload is not None:
            self.voddownload.set_live_buffer_time(value)
