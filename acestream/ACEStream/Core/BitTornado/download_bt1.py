#Embedded file name: ACEStream\Core\BitTornado\download_bt1.pyo
import sys
import os
import time
import re
import binascii
import hashlib
import array
from zurllib import urlopen
from base64 import b64encode
from urlparse import urlparse
from BT1.btformats import check_message
from BT1.Choker import Choker
from BT1.Storage import Storage
from BT1.StorageWrapper import StorageWrapper
from BT1.FileSelector import FileSelector
from BT1.Uploader import Upload
from BT1.Downloader import Downloader
from BT1.GetRightHTTPDownloader import GetRightHTTPDownloader
from BT1.HoffmanHTTPDownloader import HoffmanHTTPDownloader
from BT1.Connecter import Connecter
from RateLimiter import RateLimiter
from BT1.Encrypter import Encoder
from RawServer import RawServer, autodetect_socket_style
from BT1.Rerequester import Rerequester
from BT1.DownloaderFeedback import DownloaderFeedback
from RateMeasure import RateMeasure
from CurrentRateMeasure import Measure
from BT1.PiecePicker import PiecePicker
from BT1.Statistics import Statistics
from bencode import bencode, bdecode
from ACEStream.Core.Utilities.TSCrypto import block_encrypt, block_decrypt
from ACEStream.Core.Utilities.utilities import get_ip
from os import path, makedirs, listdir
from parseargs import parseargs, formatDefinitions, defaultargs
from socket import error as socketerror
from random import seed
from threading import Event
from clock import clock
from traceback import print_stack, print_exc
from ACEStream.Core.simpledefs import *
from ACEStream.Core.Merkle.merkle import create_fake_hashes
from ACEStream.Core.Utilities.unicode import bin2unicode, dunno2unicode
from ACEStream.Core.Video.PiecePickerStreaming import PiecePickerVOD
from ACEStream.Core.Video.VideoOnDemand import MovieOnDemandTransporter
from ACEStream.Core.APIImplementation.maketorrent import torrentfilerec2savefilename, savefilenames2finaldest
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.Utilities.EncryptedStorage import EncryptedStorageStream
from ACEStream.GlobalConfig import globalConfig
try:
    True
except:
    True = 1
    False = 0

DEBUG = False
DEBUG_ENCRYPTION = False

class BT1Download:

    def __init__(self, statusfunc, finfunc, errorfunc, excfunc, logerrorfunc, doneflag, config, response, infohash, id, rawserver, get_extip_func, port, videoanalyserpath):
        self.app_mode = globalConfig.get_mode()
        self.statusfunc = statusfunc
        self.finfunc = finfunc
        self.errorfunc = errorfunc
        self.excfunc = excfunc
        self.logerrorfunc = logerrorfunc
        self.doneflag = doneflag
        self.config = config
        self.response = response
        self.infohash = infohash
        if 'info' in self.response and 'private' in self.response['info'] and self.response['info']['private']:
            self.is_private_torrent = True
        else:
            self.is_private_torrent = False
        self.myid = id
        self.rawserver = rawserver
        self.get_extip_func = get_extip_func
        self.port = port
        self.info = self.response['info']
        self.tsmetadata = self.response.get('x-ts-properties', None)
        self.storage_secret = '8-90jm,2-=320fa&smnk/lsdgil,8as!8_'
        self.log_prefix = 'bt::' + binascii.hexlify(self.infohash) + ':'
        self.downloader_feedback = None
        self.has_extra_files = False
        self.live_streaming = self.info.has_key('live')
        if self.info.has_key('root hash') or self.live_streaming:
            self.pieces = create_fake_hashes(self.info)
        else:
            self.pieces = [ self.info['pieces'][x:x + 20] for x in xrange(0, len(self.info['pieces']), 20) ]
        self.len_pieces = len(self.pieces)
        self.piecesize = self.info['piece length']
        self.unpauseflag = Event()
        self.unpauseflag.set()
        self.downloader = None
        self.storagewrapper = None
        self.fileselector = None
        self.super_seeding_active = False
        self.filedatflag = Event()
        self.spewflag = Event()
        self.superseedflag = Event()
        self.whenpaused = None
        self.finflag = Event()
        self.rerequest = None
        self.tcp_ack_fudge = config['tcp_ack_fudge']
        self.svc_video = False
        self.play_video = config['mode'] == DLMODE_VOD
        self.am_video_source = bool(config['video_source'])
        self.use_g2g = self.play_video and 'live' not in response['info']
        self.videoinfo = None
        self.videostatus = None
        self.videoanalyserpath = videoanalyserpath
        self.voddownload = None
        self.update_avg_download_rate_period = 30
        self.check_avg_download_rate_period = 5
        self.avg_down_rate_counter = 0
        self.avg_down_rate_total = 0
        self.avg_down_rate = 0
        self.max_down_rate = 0
        self.selector_enabled = config['selector_enabled']
        if DEBUG:
            log(self.log_prefix + '__init__: selector_enabled', self.selector_enabled, 'priority', self.config['priority'], 'config', self.config)
        self.excflag = self.rawserver.get_exception_flag()
        self.failed = False
        self.checking = False
        self.starting = False
        self.started = False
        self.started_event = Event()
        self.helper = None
        self.coordinator = None
        self.rate_predictor = None
        try:
            if self.am_video_source:
                from ACEStream.Core.Video.VideoSource import PiecePickerSource
                self.picker = PiecePickerSource(self.len_pieces, config['rarest_first_cutoff'], config['rarest_first_priority_cutoff'], helper=self.helper, coordinator=self.coordinator)
            elif self.play_video:
                self.picker = PiecePickerVOD(self.len_pieces, config['rarest_first_cutoff'], config['rarest_first_priority_cutoff'], helper=self.helper, coordinator=self.coordinator, piecesize=self.piecesize)
            else:
                self.picker = PiecePicker(self.len_pieces, config['rarest_first_cutoff'], config['rarest_first_priority_cutoff'], helper=self.helper, coordinator=self.coordinator)
        except:
            log_exc()

        self.choker = Choker(config, rawserver.add_task, self.picker, self.finflag.isSet)

    def set_videoinfo(self, videoinfo, videostatus):
        self.videoinfo = videoinfo
        self.videostatus = videostatus
        if self.play_video:
            self.picker.set_videostatus(self.videostatus)

    def checkSaveLocation(self, loc):
        if self.info.has_key('length'):
            return path.exists(loc)
        for x in self.info['files']:
            if path.exists(path.join(loc, x['path'][0])):
                return True

        return False

    def saveAs(self, filefunc, pathfunc = None):

        def make(f, forcedir = False):
            if not forcedir:
                f = path.split(f)[0]
            if f != '' and not path.exists(f):
                makedirs(f)

        files = None
        storage_files = None
        piecelen = self.info['piece length']
        if self.info.has_key('length'):
            file_length = self.info['length']
            if self.config['encrypted_storage']:
                file_name = binascii.hexlify(self.infohash)
            elif self.config.has_key('saveas_filename') and self.config['saveas_filename'] is not None:
                file_name = self.config['saveas_filename']
            else:
                file_name = self.info['name']
            file = filefunc(file_name, file_length, self.config['saveas'], False, self.live_streaming)
            make(file)
            files = [(file, file_length)]
            if self.config['encrypted_storage']:
                storage_files = [(file, file_length)]
            first_piece = 0
            last_piece = file_length / piecelen
            pieceinfo = [(first_piece, last_piece)]
        else:
            file_length = 0L
            for x in self.info['files']:
                file_length += x['length']

            if self.config['encrypted_storage']:
                file_name = binascii.hexlify(self.infohash)
                file = filefunc(file_name, file_length, self.config['saveas'], False, self.live_streaming)
                make(file)
                storage_files = [(file, file_length)]
            else:
                dir_name = self.info['name']
                file = filefunc(dir_name, file_length, self.config['saveas'], True, self.live_streaming)
                if path.exists(file):
                    if not path.isdir(file):
                        raise IOError(file + 'is not a dir')
                    if listdir(file):
                        i = 0
                        existing = 0
                        for x in self.info['files']:
                            if self.config['encrypted_storage']:
                                savepath1 = str(i)
                                i += 1
                            else:
                                savepath1 = torrentfilerec2savefilename(x, 1)
                            if path.exists(path.join(file, savepath1)):
                                existing = 1

                        if not existing:
                            try:
                                file = path.join(file, dir_name)
                            except UnicodeDecodeError:
                                file = path.join(file, dunno2unicode(dir_name))

                            if path.exists(file) and not path.isdir(file):
                                if file.endswith('.torrent') or file.endswith(TRIBLER_TORRENT_EXT):
                                    prefix, ext = os.path.splitext(file)
                                    file = prefix
                                if path.exists(file) and not path.isdir(file):
                                    raise IOError("Can't create dir - " + dir_name)
                make(file, True)
                if pathfunc != None:
                    pathfunc(file)
            i = 0
            file_begin = 0
            files = []
            pieceinfo = []
            for x in self.info['files']:
                if self.config['encrypted_storage']:
                    full = file
                    i += 1
                else:
                    savepath = torrentfilerec2savefilename(x)
                    full = savefilenames2finaldest(file, savepath)
                files.append((full, x['length']))
                file_end = file_begin + x['length'] - 1
                first = file_begin / piecelen
                last = file_end / piecelen
                pieceinfo.append((first, last))
                file_begin += x['length']
                if not self.config['encrypted_storage']:
                    make(full)

        self.filename = file
        self.files = files
        self.storage_files = storage_files
        self.datalength = file_length
        self.pieceinfo = pieceinfo
        self.encrypt_pieces = {}
        for first, last in self.pieceinfo:
            self.encrypt_pieces[first] = 1
            self.encrypt_pieces[last] = 1

        if DEBUG:
            log(self.log_prefix + 'saveAs: file', file, 'files', self.files, 'pieceinfo', self.pieceinfo)
        return file

    def getFilename(self):
        return self.filename

    def get_dest(self, index):
        return self.files[index][0]

    def get_datalength(self):
        return self.datalength

    def _finished(self):
        try:
            if 'hidden' in self.config and self.config['hidden']:
                if DEBUG:
                    log(self.log_prefix + '_finished: set max connections for hidden download')
                self.setInitiate(1)
                self.setMaxConns(1)
        except:
            print_exc()

        self.finflag.set()
        try:
            self.storage.set_readonly()
        except (IOError, OSError) as e:
            self.errorfunc('trouble setting readonly at end - ' + str(e))

        if self.superseedflag.isSet():
            self._set_super_seed()
        self.choker.set_round_robin_period(max(self.config['round_robin_period'], self.config['round_robin_period'] * self.info['piece length'] / 200000))
        self.rerequest_complete()
        self.finfunc()

    def _data_flunked(self, amount, index):
        self.ratemeasure_datarejected(amount)
        if not self.doneflag.isSet():
            if DEBUG:
                log(self.log_prefix + '_data_flunked: piece %d failed hash check, re-downloading it' % index)

    def _piece_from_live_source(self, index, data):
        if self.videostatus.live_streaming and self.voddownload is not None:
            return self.voddownload.piece_from_live_source(index, data)
        else:
            return True

    def _failed(self, reason):
        self.failed = True
        self.doneflag.set()
        if reason is not None:
            self.errorfunc(reason)

    def initFiles(self, old_style = False, statusfunc = None, resumedata = None):
        if self.doneflag.isSet():
            return
        if not statusfunc:
            statusfunc = self.statusfunc
        disabled_files = None
        if self.selector_enabled:
            self.priority = self.config['priority']
            if self.priority:
                try:
                    self.priority = self.priority.split(',')
                    self.priority = [ int(p) for p in self.priority ]
                    for p in self.priority:
                        pass

                except:
                    raise ValueError('bad priority list given, ignored')
                    self.priority = None

            try:
                disabled_files = [ x == -1 for x in self.priority ]
                count_enabled_files = len([ x for x in self.priority if x != -1 ])
                self.has_extra_files = count_enabled_files > 1
            except:
                pass

        bufferdir = os.path.join(self.config['buffer_dir'], binascii.hexlify(self.infohash))
        if DEBUG:
            log(self.log_prefix + 'initFiles: bufferdir', bufferdir)
        if self.config['encrypted_storage']:
            files = self.storage_files
        else:
            files = self.files
        self.storage = Storage(self.infohash, files, self.info['piece length'], self.doneflag, self.config, disabled_files, bufferdir)
        if self.info.has_key('root hash'):
            root_hash = self.info['root hash']
        else:
            root_hash = None
        replace_mp4_metatags = None
        if self.tsmetadata is not None:
            replace = self.tsmetadata.get('rpmp4mt', None)
            if replace is not None:
                replace_mp4_metatags = []
                for idx, tags in replace.iteritems():
                    tags = tags.split(',')
                    for tag in tags:
                        if len(tag) == 0:
                            continue
                        if len(tag) > 100:
                            continue
                        if re.match('^[a-z-_]+$', tag) is None:
                            continue
                        if tag not in replace_mp4_metatags:
                            replace_mp4_metatags.append(tag)

                if DEBUG:
                    log(self.log_prefix + 'initFiles: configure replace_mp4_metatags: replace', replace, 'replace_mp4_metatags', replace_mp4_metatags)
        if self.config['encrypted_storage']:
            encryptfunc = self.encrypt_piece
        else:
            encryptfunc = None
        self.storagewrapper = StorageWrapper(self.infohash, self.videoinfo, self.storage, self.config['download_slice_size'], self.pieces, self.info['piece length'], root_hash, self._finished, self._failed, statusfunc, self.doneflag, self.config['check_hashes'], self._data_flunked, self._piece_from_live_source, self.rawserver.add_task, self.config, self.unpauseflag, has_extra_files=self.has_extra_files, replace_mp4_metatags=replace_mp4_metatags, encryptfunc=encryptfunc, encrypt_pieces=self.encrypt_pieces)
        if self.selector_enabled:
            files = self.files
            self.fileselector = FileSelector(files, self.info['piece length'], self.storage, self.storagewrapper, self.rawserver.add_task, self._failed)
            if resumedata:
                self.fileselector.unpickle(resumedata)
        self.checking = True
        if old_style:
            return self.storagewrapper.old_style_init()
        return self.storagewrapper.initialize

    def encrypt_piece(self, index, data, encrypt):
        if self.live_streaming:
            return data
        if not self.config['encrypted_storage']:
            return data
        is_str = isinstance(data, str)
        if index not in self.encrypt_pieces:
            return data
        if DEBUG_ENCRYPTION:
            log('enc>>> check encrypt', encrypt, 'index', index, 'encrypt_pieces', self.encrypt_pieces, 'is_str', is_str, 'input len', len(data), 'data', data[:20])
        try:
            key = self.storage_secret + hashlib.sha1(self.infohash).digest() + str(index) + '0' * (10 - len(str(index)))
            if DEBUG_ENCRYPTION:
                log('enc>>> encrypt index', index, 'key', key, 'keylen', len(key))
            if is_str:
                t = time.time()
                if encrypt:
                    data = block_encrypt(data, key)
                else:
                    data = block_decrypt(data, key)
                time_encrypt = time.time() - t
                time_update = 0
            else:
                t = time.time()
                if encrypt:
                    block_encrypt(data, key)
                else:
                    block_decrypt(data, key)
                time_encrypt = time.time() - t
                time_update = 0
            if DEBUG_ENCRYPTION:
                log('enc>>> output len', len(data), 'data', data[:20], 'time_encrypt', time_encrypt, 'time_update', time_update)
            return data
        except:
            print_exc()
            return data

    def _make_upload(self, connection, ratelimiter, totalup):
        return Upload(connection, ratelimiter, totalup, self.choker, self.storagewrapper, self.picker, self.config)

    def _kick_peer(self, connection):

        def k(connection = connection):
            connection.close()

        self.rawserver.add_task(k, 0)

    def _ban_peer(self, ip):
        self.encoder_ban(ip)

    def _received_raw_data(self, x):
        if self.tcp_ack_fudge:
            x = int(x * self.tcp_ack_fudge)
            self.ratelimiter.adjust_sent(x)

    def _received_data(self, x):
        self.short_downmeasure.update_rate(x)
        self.downmeasure.update_rate(x)
        self.p2pdownmeasure.update_rate(x)
        self.ratemeasure.data_came_in(x)

    def _received_http_data(self, x):
        self.short_downmeasure.update_rate(x)
        self.downmeasure.update_rate(x)
        self.httpdownmeasure.update_rate(x)
        self.ratemeasure.data_came_in(x)

    def _cancelfunc(self, pieces):
        self.downloader.cancel_piece_download(pieces)
        if self.ghttpdownloader is not None:
            self.ghttpdownloader.cancel_piece_download(pieces)
        if self.hhttpdownloader is not None:
            self.hhttpdownloader.cancel_piece_download(pieces)

    def _reqmorefunc(self, pieces):
        self.downloader.requeue_piece_download(pieces)

    def startEngine(self, ratelimiter = None, vodeventfunc = None):
        if DEBUG:
            log(self.log_prefix + 'startEngine: name', self.info['name'])
        if self.doneflag.isSet():
            return
        self.checking = False
        self.starting = True
        completeondisk = self.storagewrapper.get_amount_left() == 0
        if DEBUG:
            log(self.log_prefix + 'startEngine: complete on disk?', completeondisk, 'found', len(self.storagewrapper.get_pieces_on_disk_at_startup()))
        self.picker.fast_initialize(completeondisk)
        if not completeondisk:
            for i in self.storagewrapper.get_pieces_on_disk_at_startup():
                self.picker.complete(i)

        self.upmeasure = Measure(self.config['max_rate_period'], self.config['upload_rate_fudge'])
        self.downmeasure = Measure(self.config['max_rate_period'])
        self.short_downmeasure = Measure(5)
        self.p2pdownmeasure = Measure(self.config['max_rate_period'])
        self.httpdownmeasure = Measure(self.config['max_rate_period'])
        if ratelimiter:
            self.ratelimiter = ratelimiter
        else:
            self.ratelimiter = RateLimiter(self.rawserver.add_task, self.config['upload_unit_size'], self.setConns)
            self.ratelimiter.set_upload_rate(self.config['max_upload_rate'])
        self.ratemeasure = RateMeasure()
        self.ratemeasure_datarejected = self.ratemeasure.data_rejected
        self.downloader = Downloader(self.infohash, self.storagewrapper, self.picker, self.config['request_backlog'], self.config['max_rate_period'], self.len_pieces, self.config['download_slice_size'], self._received_data, self.config['snub_time'], self.config['auto_kick'], self._kick_peer, self._ban_peer, scheduler=self.rawserver.add_task)
        rate = self.config['max_download_rate']
        if self.config['auto_download_limit']:
            if self.videostatus.bitrate_set:
                rate = self.videostatus.bitrate / 1024 * 1.3
        if DEBUG:
            log(self.log_prefix + 'startEngine: set download rate', rate)
        self.downloader.set_download_rate(rate)
        self.picker.set_downloader(self.downloader)
        if self.coordinator is not None:
            self.coordinator.set_downloader(self.downloader)
        live_streaming = self.info.has_key('live')
        authorized_peers = []
        if live_streaming:
            if self.app_mode == 'node':
                source_node = globalConfig.get_value('source_node')
                support_nodes = globalConfig.get_value('support_nodes')
                if source_node is not None:
                    authorized_peers.append([source_node])
                if len(support_nodes):
                    authorized_peers.append(support_nodes)
            elif self.response.has_key('authorized-peers'):
                authorized_peers = self.response['authorized-peers']
                if DEBUG:
                    log(self.log_prefix + 'startEngine: got authorized peers from meta:', authorized_peers)
            else:
                tracker_url = self.response.get('announce', None)
                if DEBUG:
                    log(self.log_prefix + 'startEngine: set first tracker as an authorized peer: tracker_url', tracker_url)
                if tracker_url is not None:
                    try:
                        res = urlparse(tracker_url)
                        host = res.hostname
                        port = res.port
                        if port is None:
                            port = 80
                        tracker_ip = get_ip(host)
                        if DEBUG:
                            log(self.log_prefix + 'startEngine: set first tracker as an authorized peer: host', host, 'port', port, 'tracker_ip', tracker_ip)
                        if tracker_ip is not None:
                            authorized_peers.append([[tracker_ip, port]])
                    except:
                        print_exc()

        self.connecter = Connecter(self.response, self._make_upload, self.downloader, self.choker, self.len_pieces, self.piecesize, self.upmeasure, self.config, self.ratelimiter, self.info.has_key('root hash'), self.rawserver.add_task, self.coordinator, self.helper, self.get_extip_func, self.port, self.use_g2g, self.infohash, authorized_peers=authorized_peers, live_streaming=live_streaming, is_private_torrent=self.is_private_torrent)
        if 'hidden' in self.config and self.config['hidden']:
            limit_connections_queue = 400
        else:
            limit_connections_queue = 0
        self.encoder = Encoder(self.connecter, self.rawserver, self.myid, self.config['max_message_length'], self.rawserver.add_task, self.config['keepalive_interval'], self.infohash, self._received_raw_data, self.config, limit_connections_queue)
        self.encoder_ban = self.encoder.ban
        if 'initial peers' in self.response:
            if DEBUG:
                log(self.log_prefix + 'startEngine: Using initial peers', self.response['initial peers'])
            self.encoder.start_connections([ (address, 0) for address in self.response['initial peers'] ])
        if self.app_mode == 'node':
            to_start = []
            if globalConfig.get_value('allow_source_download'):
                source_node = globalConfig.get_value('source_node')
                if source_node is not None:
                    if DEBUG:
                        log(self.log_prefix + 'startEngine: connect to the source node:', source_node)
                    to_start.append((tuple(source_node), 0))
            if globalConfig.get_value('allow_support_download'):
                support_nodes = globalConfig.get_value('support_nodes')
                if len(support_nodes):
                    if DEBUG:
                        log(self.log_prefix + 'startEngine: connect to support nodes:', support_nodes)
                    to_start.extend([ (tuple(addr), 0) for addr in support_nodes ])
            if len(to_start):
                if DEBUG:
                    log(self.log_prefix + 'startEngine: start initial connections: to_start', to_start)
                self.encoder.start_connections(to_start)
        for ip in self.config['exclude_ips']:
            if DEBUG:
                log(self.log_prefix + 'startEngine: Banning ip: ' + str(ip))
            self.encoder_ban(ip)

        if self.helper is not None:
            from ACEStream.Core.ProxyService.RatePredictor import ExpSmoothRatePredictor
            self.helper.set_encoder(self.encoder)
            self.encoder.set_helper(self.helper)
            self.rate_predictor = ExpSmoothRatePredictor(self.rawserver, self.downmeasure, self.config['max_download_rate'])
            self.picker.set_rate_predictor(self.rate_predictor)
            self.rate_predictor.update()
        if self.coordinator is not None:
            self.coordinator.set_encoder(self.encoder)
        from ACEStream.Core.Session import Session
        session = Session.get_instance()
        self.ghttpdownloader = None
        url_list = []
        if self.response.has_key('url-list'):
            url_list.extend(self.response['url-list'])
        http_seeds = session.get_ts_http_seeds(self.infohash)
        if http_seeds is not None:
            if DEBUG:
                log(self.log_prefix + 'startEngine: got http seeds from session:', http_seeds)
            url_list.extend(http_seeds)
        if self.config.get('enable_http_support', True) and len(url_list) and not self.finflag.isSet():
            self.ghttpdownloader = GetRightHTTPDownloader(self.storagewrapper, self.picker, self.rawserver, self.finflag, self.logerrorfunc, self.downloader, self.config['max_rate_period'], self.infohash, self._received_http_data, self.connecter.got_piece)
            for url in url_list:
                if DEBUG:
                    log(self.log_prefix + 'startEngine: add http seed: url', url)
                self.ghttpdownloader.make_download(url)

            if self.config['mode'] == DLMODE_NORMAL:
                if DEBUG:
                    log(self.log_prefix + 'startEngine: start http in normal mode: completeondisk', completeondisk)
                self.ghttpdownloader.start_video_support()
        self.hhttpdownloader = HoffmanHTTPDownloader(self.storagewrapper, self.picker, self.rawserver, self.finflag, self.logerrorfunc, self.downloader, self.config['max_rate_period'], self.infohash, self._received_http_data, self.connecter.got_piece)
        if self.response.has_key('httpseeds') and not self.finflag.isSet():
            for u in self.response['httpseeds']:
                self.hhttpdownloader.make_download(u)

        if self.selector_enabled:
            self.fileselector.tie_in(self.picker, self._cancelfunc, self._reqmorefunc)
            if self.priority:
                self.fileselector.set_priorities_now(self.priority)
        if self.play_video:
            if self.picker.am_I_complete():
                if DEBUG:
                    log(self.log_prefix + 'startEngine: VOD requested, but file complete on disk: videoinfo', self.videoinfo)
                if self.config['encrypted_storage']:
                    filename = None
                    places = self.storagewrapper.places.copy()
                    stream = EncryptedStorageStream(self.videoinfo['outpath'], self.infohash, self.videostatus.selected_movie['size'], self.videostatus.selected_movie['offset'], self.videostatus.piecelen, places)
                else:
                    filename = self.videoinfo['outpath']
                    stream = None
                vodeventfunc(self.videoinfo, VODEVENT_START, {'complete': True,
                 'filename': filename,
                 'mimetype': self.videoinfo['mimetype'],
                 'stream': stream,
                 'length': self.videostatus.selected_movie['size'],
                 'bitrate': self.videoinfo['bitrate']})
            else:
                if DEBUG:
                    log(self.log_prefix + 'startEngine: Going into VOD mode: videoinfo', self.videoinfo)
                self.voddownload = MovieOnDemandTransporter(self, self.videostatus, self.videoinfo, self.videoanalyserpath, vodeventfunc, self.ghttpdownloader)
                if self.has_extra_files and not self.config['encrypted_storage']:
                    from ACEStream.Core.Session import Session
                    session = Session.get_instance()
                    preallocate_file = lambda : self.storagewrapper.preallocate_file(self.videostatus.first_piece, self.videostatus.last_piece)
                    session.uch.perform_usercallback(preallocate_file)
        elif DEBUG:
            log(self.log_prefix + 'startEngine: Going into standard mode')
        if self.am_video_source:
            from ACEStream.Core.Video.VideoSource import VideoSourceTransporter, RateLimitedVideoSourceTransporter
            if DEBUG:
                log(self.log_prefix + 'startEngine: Acting as VideoSource')
            if self.config['video_ratelimit']:
                print >> sys.stderr, 'set video ratelimit: ', self.config['video_ratelimit']
                self.videosourcetransporter = RateLimitedVideoSourceTransporter(self.config['video_ratelimit'], self.config['video_source'], self, self.config['video_source_authconfig'], self.config['video_source_restartstatefilename'])
            else:
                self.videosourcetransporter = VideoSourceTransporter(self.config['video_source'], self, self.config['video_source_authconfig'], self.config['video_source_restartstatefilename'])
            self.videosourcetransporter.start()
        elif DEBUG:
            log(self.log_prefix + 'startEngine: not a videosource')
        if not self.doneflag.isSet():
            if DEBUG:
                log(self.log_prefix + 'startEngine: set started flag')
            self.started = True
        self.starting = False
        self.started_event.set()
        self.reset_avg_download_rate()
        self.rawserver.add_task(self.update_avg_download_rate, self.update_avg_download_rate_period)
        self.rawserver.add_task(self.check_avg_download_rate, self.check_avg_download_rate_period)

    def got_duration(self, duration, from_player = True):
        if DEBUG:
            log(self.log_prefix + 'got_duration: duration', duration, 'from_player', from_player)
        if self.voddownload is not None:
            return self.voddownload.got_duration(duration, from_player)

    def live_seek(self, pos):
        if DEBUG:
            log(self.log_prefix + 'live_seek: pos', pos)
        if self.voddownload is None:
            log(self.log_prefix + 'live_seek: no voddownload')
            return
        self.voddownload.live_seek(pos)

    def got_metadata(self, metadata):
        if DEBUG:
            log(self.log_prefix + 'got_metadata: metadata', metadata, 'voddownload', self.voddownload)
        if self.voddownload is not None:
            self.voddownload.got_metadata(metadata)

    def got_http_seeds(self, http_seeds):
        if DEBUG:
            log(self.log_prefix + 'got_http_seeds: http_seeds', http_seeds, 'started', self.started, 'starting', self.starting, 'ghttpdownloader', self.ghttpdownloader)
        if not self.started:
            if self.starting:
                if DEBUG:
                    log(self.log_prefix + 'got_http_seeds: not started, but starting, wait for started event')
                self.started_event.wait(10.0)
            else:
                return
            if DEBUG:
                log(self.log_prefix + 'got_http_seeds: got started event: started', self.started)
            if not self.started:
                return
        if self.ghttpdownloader is None:
            if DEBUG:
                log(self.log_prefix + 'got_http_seeds: create ghttpdownloader: voddownload', self.voddownload)
            self.ghttpdownloader = GetRightHTTPDownloader(self.storagewrapper, self.picker, self.rawserver, self.finflag, self.logerrorfunc, self.downloader, self.config['max_rate_period'], self.infohash, self._received_http_data, self.connecter.got_piece)
            if self.voddownload is not None:
                if DEBUG:
                    log(self.log_prefix + 'got_http_seeds: attach ghttpdownloader to voddownload')
                self.voddownload.http_support = self.ghttpdownloader
                self.voddownload.http_support.set_voddownload(self.voddownload)
            if self.downloader_feedback is not None:
                self.downloader_feedback.ghttpdl = self.ghttpdownloader
        for url in http_seeds:
            if DEBUG:
                log(self.log_prefix + 'got_http_seeds: add http seed: url', url)
            self.ghttpdownloader.make_download(url)

        if self.config['mode'] == DLMODE_NORMAL:
            if DEBUG:
                log(self.log_prefix + 'got_http_seeds: start http in normal mode')
            self.ghttpdownloader.start_video_support()
        if self.voddownload is not None:
            self.voddownload.got_http_support()

    def restartEngine(self, vodfileindex, videostatus, vodeventfunc, dlmode, new_priority = None):
        if DEBUG:
            log(self.log_prefix + 'restartEngine: vodfileindex', vodfileindex, 'dlmode', dlmode, 'new_priority', new_priority, 'complete', self.picker.am_I_complete(), 'numgot', self.picker.numgot, 'numpieces', self.picker.numpieces)
        if dlmode == DLMODE_VOD and not self.play_video:
            raise Exception('cannot restart bt in vod mode')
        if not self.started:
            if DEBUG:
                log(self.log_prefix + 'restartEngine: not yet started, start engine')
            self.startEngine(vodeventfunc=vodeventfunc)
        if self.downloader is None:
            log(self.log_prefix + 'restartEngine: no downloader, engine not started, cannot restart')
            return
        self.videoinfo = vodfileindex
        self.videostatus = videostatus
        self.downloader.reset_have()
        if self.selector_enabled and new_priority is not None:
            self.priority = new_priority
            self.fileselector.set_priorities_now(self.priority)
        if self.play_video:
            self.picker.set_videostatus(self.videostatus)
            self.picker.num_skip_started_pieces = 10
            if self.picker.am_I_complete():
                if DEBUG:
                    log(self.log_prefix + 'restartEngine: VOD requested, but file complete on disk', self.videoinfo)
                if self.config['encrypted_storage']:
                    filename = None
                    stream = EncryptedStorageStream(self.videoinfo['outpath'], self.infohash, self.videostatus.selected_movie['size'], self.videostatus.selected_movie['offset'], self.videostatus.piecelen, self.storagewrapper.places)
                else:
                    filename = self.videoinfo['outpath']
                    stream = None
                vodeventfunc(self.videoinfo, VODEVENT_START, {'complete': True,
                 'filename': filename,
                 'mimetype': self.videoinfo['mimetype'],
                 'stream': stream,
                 'length': self.videostatus.selected_movie['size'],
                 'bitrate': self.videoinfo['bitrate']})
            else:
                if self.voddownload is not None:
                    self.voddownload.shutdown()
                    if DEBUG:
                        log(self.log_prefix + 'restartEngine: self.voddownload is not None, stop current download')
                self.voddownload = MovieOnDemandTransporter(self, self.videostatus, self.videoinfo, self.videoanalyserpath, vodeventfunc, self.ghttpdownloader)

    def set_player_buffer_time(self, value):
        if DEBUG:
            log(self.log_prefix + 'set_player_buffer_time:', value)
        self.config['player_buffer_time'] = value
        if self.voddownload is not None:
            self.voddownload.player_buffer_time = value

    def set_live_buffer_time(self, value):
        if DEBUG:
            log(self.log_prefix + 'set_live_buffer_time:', value)
        self.config['live_buffer_time'] = value
        if self.voddownload is not None:
            self.voddownload.live_buffer_time = value

    def set_wait_sufficient_speed(self, value):
        if DEBUG:
            log(self.log_prefix + 'set_wait_sufficient_speed:', value)
        self.config['wait_sufficient_speed'] = value
        if self.voddownload is not None:
            self.voddownload.wait_sufficient_speed = value
            self.voddownload.update_prebuffering()

    def set_auto_download_limit(self, value):
        if DEBUG:
            log(self.log_prefix + 'set_auto_download_limit:', value)
        self.config['auto_download_limit'] = value

    def set_http_support(self, value):
        if DEBUG:
            log(self.log_prefix + 'set_http_support:', value)
        self.config['enable_http_support'] = value

    def rerequest_complete(self):
        if self.rerequest:
            self.rerequest.announce(1)

    def rerequest_stopped(self):
        if self.rerequest:
            self.rerequest.announce(2)

    def startRerequester(self, paused = False):
        if DEBUG:
            log(self.log_prefix + 'startRerequester: paused', paused)
        if self.rerequest is None:
            self.rerequest = self.createRerequester()
            self.encoder.set_rerequester(self.rerequest)
        if self.app_mode == 'stream' and globalConfig.get_value('private_source'):
            log('bt::startRerequester: skip start for private source')
            paused = True
        if not paused:
            self.rerequest.start()

    def createRerequester(self, callback = None):
        if self.response.has_key('announce-list'):
            trackerlist = self.response['announce-list']
            for tier in range(len(trackerlist)):
                for t in range(len(trackerlist[tier])):
                    trackerlist[tier][t] = bin2unicode(trackerlist[tier][t])

        else:
            tracker = bin2unicode(self.response.get('announce', ''))
            if tracker:
                trackerlist = [[tracker]]
            else:
                trackerlist = [[]]
        if callback is None:
            callback = self.encoder.start_connections
        rerequest = Rerequester(trackerlist, self.config['rerequest_interval'], self.rawserver.add_task, self.encoder.how_many_connections, self.config['min_peers'], callback, self.rawserver.add_task, self.storagewrapper.get_amount_left, self.upmeasure.get_total, self.downmeasure.get_total, self.port, self.config['ip'], self.myid, self.infohash, self.config['http_timeout'], self.logerrorfunc, self.excfunc, self.config['max_initiate'], self.doneflag, self.upmeasure.get_rate, self.downmeasure.get_rate, self.unpauseflag, self.config, self.am_video_source, self.is_private_torrent)
        if self.play_video and self.voddownload is not None:
            rerequest.add_notifier(lambda x: self.voddownload.peers_from_tracker_report(len(x)))
        return rerequest

    def _init_stats(self):
        self.statistics = Statistics(self.upmeasure, self.downmeasure, self.httpdownmeasure, self.connecter, self.ghttpdownloader, self.hhttpdownloader, self.ratelimiter, self.filedatflag, self.encoder)
        if self.info.has_key('files'):
            self.statistics.set_dirstats(self.files, self.info['piece length'])

    def autoStats(self, displayfunc = None):
        if not displayfunc:
            displayfunc = self.statusfunc
        self._init_stats()
        DownloaderFeedback(self.choker, self.ghttpdownloader, self.hhttpdownloader, self.rawserver.add_task, self.upmeasure.get_rate, self.downmeasure.get_rate, self.httpdownmeasure.get_rate, self.ratemeasure, self.storagewrapper.get_stats, self.datalength, self.finflag, self.spewflag, self.statistics, displayfunc, self.config['display_interval'], infohash=self.infohash, voddownload=self.voddownload)

    def startStats(self):
        self._init_stats()
        self.spewflag.set()
        self.downloader_feedback = DownloaderFeedback(self.choker, self.ghttpdownloader, self.hhttpdownloader, self.rawserver.add_task, self.upmeasure.get_rate, self.downmeasure.get_rate, self.httpdownmeasure.get_rate, self.ratemeasure, self.storagewrapper.get_stats, self.datalength, self.finflag, self.spewflag, self.statistics, infohash=self.infohash, voddownload=self.voddownload)
        return self.downloader_feedback.gather

    def getPortHandler(self):
        return self.encoder

    def checkpoint(self):
        if self.fileselector and self.started:
            if DEBUG:
                log(self.log_prefix + 'checkpoint: return fileselector.pickle()')
            return self.fileselector.pickle()
        else:
            if DEBUG:
                log(self.log_prefix + 'checkpoint: return None, self.started', self.started)
            return None

    def shutdown(self):
        if self.checking or self.started:
            self.storagewrapper.sync()
            self.storage.close()
            self.rerequest_stopped()
        if DEBUG:
            log(self.log_prefix + 'shutdown: fileselector', self.fileselector, 'started', self.started, 'failed', self.failed)
        resumedata = None
        if self.fileselector and self.started:
            if not self.failed:
                self.fileselector.finish()
                resumedata = self.fileselector.pickle()
                if DEBUG:
                    log(self.log_prefix + 'shutdown: resumedata', resumedata)
        self.started = False
        if self.voddownload is not None:
            self.voddownload.shutdown()
        if self.am_video_source:
            self.videosourcetransporter.shutdown()
        return resumedata

    def reset_avg_download_rate(self):
        if DEBUG:
            log(self.log_prefix + 'reset_avg_download_rate:')
        self.avg_down_rate_counter = 0
        self.avg_down_rate_total = 0
        self.avg_down_rate = 0

    def update_avg_download_rate(self):
        if not self.started:
            return
        current_rate = self.downmeasure.get_rate()
        self.avg_down_rate_counter += 1
        self.avg_down_rate_total += current_rate
        self.avg_down_rate = self.avg_down_rate_total / self.avg_down_rate_counter
        if self.avg_down_rate > self.max_down_rate:
            self.max_down_rate = self.avg_down_rate
        if DEBUG:
            log(self.log_prefix + 'update_avg_download_rate: count', self.avg_down_rate_counter, 'avg_rate', self.avg_down_rate, 'current_rate', current_rate, 'max_rate', self.max_down_rate)
        self.rawserver.add_task(self.update_avg_download_rate, self.update_avg_download_rate_period)

    def check_avg_download_rate(self):
        if not self.started:
            if DEBUG:
                log(self.log_prefix + 'check_avg_download_rate: not started, stop checking')
            return
        if self.finflag.isSet():
            if DEBUG:
                log(self.log_prefix + 'check_avg_download_rate: download finished, stop checking')
            return
        current_rate = self.downmeasure.get_rate()
        if current_rate < self.avg_down_rate * 0.5:
            if DEBUG:
                log(self.log_prefix + 'check_avg_download_rate: current rate too small, do something: avg_rate', self.avg_down_rate, 'current_rate', current_rate)
            self.reset_avg_download_rate()
            if self.rerequest is not None:
                self.rerequest.check_network_connection()
        self.rawserver.add_task(self.check_avg_download_rate, self.check_avg_download_rate_period)

    def setUploadRate(self, rate, networkcalling = False):
        try:
            if self.live_streaming and self.app_mode != 'stream' and self.app_mode != 'node':
                if DEBUG:
                    log(self.log_prefix + 'setUploadRate: do not set upload limit on live')
                return

            def s(self = self, rate = rate):
                if DEBUG:
                    log(self.log_prefix + 'setUploadRate: set max upload rate:', rate)
                self.config['max_upload_rate'] = rate
                self.ratelimiter.set_upload_rate(rate)

            if networkcalling:
                s()
            else:
                self.rawserver.add_task(s)
        except AttributeError:
            pass

    def setConns(self, conns, conns2 = None, networkcalling = False):
        if not conns2:
            conns2 = conns
        try:

            def s(self = self, conns = conns, conns2 = conns2):
                self.config['min_uploads'] = conns
                self.config['max_uploads'] = conns2
                if conns > 30:
                    self.config['max_initiate'] = conns + 10

            if networkcalling:
                s()
            else:
                self.rawserver.add_task(s)
        except AttributeError:
            pass

    def setDownloadRate(self, rate = None, auto_limit = False, networkcalling = False):
        try:

            def s(self = self, rate = rate, auto_limit = auto_limit):
                current_rate = self.downloader.get_download_rate()
                if auto_limit:
                    if self.videostatus.bitrate_set:
                        rate = self.videostatus.bitrate / 1024 * 1.3
                    else:
                        rate = None
                if DEBUG:
                    log(self.log_prefix + 'setDownloadRate: current_rate', current_rate, 'new_rate', rate, 'auto', auto_limit)
                self.config['auto_download_limit'] = auto_limit
                if rate is not None:
                    self.config['max_download_rate'] = rate
                    self.downloader.set_download_rate(rate)
                return current_rate

            if networkcalling:
                return s()
            self.rawserver.add_task(s)
        except AttributeError:
            pass

    def startConnection(self, ip, port, id):
        self.encoder._start_connection((ip, port), id)

    def _startConnection(self, ipandport, id):
        self.encoder._start_connection(ipandport, id)

    def setInitiate(self, initiate, networkcalling = False):
        try:

            def s(self = self, initiate = initiate):
                self.config['max_initiate'] = initiate

            if networkcalling:
                s()
            else:
                self.rawserver.add_task(s)
        except AttributeError:
            pass

    def setMaxConns(self, nconns, networkcalling = False):
        try:

            def s(self = self, nconns = nconns):
                self.config['max_connections'] = nconns
                try:
                    self.encoder.max_connections = nconns
                except:
                    pass

            if networkcalling:
                s()
            else:
                self.rawserver.add_task(s)
        except AttributeError:
            pass

    def getConfig(self):
        return self.config

    def reannounce(self, special = None):
        try:

            def r(self = self, special = special):
                if special is None:
                    self.rerequest.announce()
                else:
                    self.rerequest.announce(specialurl=special)

            self.rawserver.add_task(r)
        except AttributeError:
            pass

    def getResponse(self):
        try:
            return self.response
        except:
            return None

    def isPaused(self):
        return not self.unpauseflag.isSet()

    def Pause(self, close_connections = False):
        if not self.unpauseflag.isSet():
            if DEBUG:
                log(self.log_prefix + 'Pause: already paused')
            return
        if DEBUG:
            log(self.log_prefix + 'Pause: ---')
        if not self.storagewrapper:
            return False
        self.unpauseflag.clear()
        unpause_lambda = lambda : self.onPause(close_connections)
        self.rawserver.add_task(unpause_lambda)
        return True

    def onPause(self, close_connections = False):
        if DEBUG:
            log(self.log_prefix + 'onPause: close_connections', close_connections)
        self.whenpaused = clock()
        if not self.downloader:
            return
        if close_connections:
            self.whenpaused -= 60
        self.downloader.pause(True)
        self.encoder.pause(True)
        self.choker.pause(True)
        if close_connections:
            self.encoder.close_all()

    def Unpause(self):
        if self.unpauseflag.isSet():
            if DEBUG:
                log(self.log_prefix + 'Unpause: not paused')
            return
        if DEBUG:
            log(self.log_prefix + 'Unpause: ---')
        self.unpauseflag.set()
        self.rawserver.add_task(self.onUnpause)

    def onUnpause(self):
        if not self.downloader:
            return
        self.downloader.pause(False)
        self.encoder.pause(False)
        self.choker.pause(False)
        hidden = self.config.get('hidden', False)
        if not hidden and self.rerequest and self.whenpaused and clock() - self.whenpaused > 60:
            if DEBUG:
                log(self.log_prefix + 'onUnpause: rerequest')
            self.rerequest.announce(3)

    def set_super_seed(self, networkcalling = False):
        self.superseedflag.set()
        if networkcalling:
            self._set_super_seed()
        else:
            self.rawserver.add_task(self._set_super_seed)

    def _set_super_seed(self):
        if not self.super_seeding_active and self.finflag.isSet():
            self.super_seeding_active = True
            self.logerrorfunc('        ** SUPER-SEED OPERATION ACTIVE **\n' + '  please set Max uploads so each peer gets 6-8 kB/s')

            def s(self = self):
                self.downloader.set_super_seed()
                self.choker.set_super_seed()

            self.rawserver.add_task(s)
            if self.finflag.isSet():

                def r(self = self):
                    self.rerequest.announce(3)

                self.rawserver.add_task(r)

    def am_I_finished(self):
        return self.finflag.isSet()

    def get_transfer_stats(self):
        return (self.upmeasure.get_total(), self.downmeasure.get_total())

    def get_moviestreamtransport(self):
        return self.voddownload
