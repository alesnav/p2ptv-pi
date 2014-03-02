#Embedded file name: ACEStream\Core\APIImplementation\LaunchManyCore.pyo
import sys
import os
import pickle
import socket
import binascii
import hashlib
import time
import traceback
from threading import Event, Thread, enumerate, currentThread
from traceback import print_stack, print_exc
from ACEStream.Core.BitTornado.RawServer import RawServer
from ACEStream.Core.BitTornado.ServerPortHandler import MultiHandler
from ACEStream.Core.BitTornado.BT1.track import Tracker
from ACEStream.Core.BitTornado.HTTPHandler import HTTPHandler, DummyHTTPHandler
from ACEStream.Core.simpledefs import *
from ACEStream.Core.exceptions import *
from ACEStream.Core.Download import Download
from ACEStream.Core.DownloadConfig import DownloadStartupConfig
from ACEStream.Core.TorrentDef import TorrentDef
from ACEStream.Core.NATFirewall.guessip import get_my_wan_ip
from ACEStream.Core.NATFirewall.UPnPThread import UPnPThread
from ACEStream.Core.NATFirewall.UDPPuncture import UDPHandler
from ACEStream.Core.DecentralizedTracking import mainlineDHT
from ACEStream.Core.DecentralizedTracking.MagnetLink.MagnetLink import MagnetHandler
from ACEStream.Core.Utilities.logger import log, log_exc
import ACEStream.Core.CacheDB.cachedb as cachedb
from ACEStream.Core.CacheDB.sqlitecachedb import SQLiteCacheDB
from ACEStream.Core.CacheDB.SqliteCacheDBHandler import MyDBHandler, TorrentDBHandler, Url2TorrentDBHandler, AdID2InfohashDBHandler, TsPlayersDBHandler, TsMetadataDBHandler, UserProfileDBHandler
from ACEStream.Category.Category import Category
from ACEStream.Core.NATFirewall.DialbackMsgHandler import DialbackMsgHandler
from ACEStream.Core.BitTornado.BT1.Encrypter import incompletecounter
from ACEStream.Core.Utilities.TSCrypto import m2_AES_encrypt, m2_AES_decrypt
if sys.platform == 'win32':
    SOCKET_BLOCK_ERRORCODE = 10035
else:
    import errno
    SOCKET_BLOCK_ERRORCODE = errno.EWOULDBLOCK
SPECIAL_VALUE = 481
DEBUG = False
PROFILE = False

class ACEStreamLaunchMany(Thread):

    def __init__(self, network_thread_daemon = True):
        Thread.__init__(self)
        self.daemon = network_thread_daemon
        self.name = 'Network' + self.name

    def register(self, session, sesslock):
        self.session = session
        self.sesslock = sesslock
        self.downloads = {DLTYPE_TORRENT: {},
         DLTYPE_DIRECT: {}}
        config = session.sessconfig
        self.locally_guessed_ext_ip = self.guess_ext_ip_from_local_info()
        self.upnp_ext_ip = None
        self.dialback_ext_ip = None
        self.yourip_ext_ip = None
        self.udppuncture_handler = None
        self.sessdoneflag = Event()
        self.hashcheck_queue = []
        self.sdownloadtohashcheck = None
        self.upnp_thread = None
        self.upnp_type = config['upnp_nat_access']
        self.nat_detect = config['nat_detect']
        self.rawserver = RawServer(self.sessdoneflag, config['timeout_check_interval'], config['timeout'], ipv6_enable=config['ipv6_enabled'], failfunc=self.rawserver_fatalerrorfunc, errorfunc=self.rawserver_nonfatalerrorfunc, max_socket_connects=config['max_socket_connects'])
        self.rawserver.add_task(self.rawserver_keepalive, 1)
        self.listen_port = self.rawserver.find_and_bind(0, config['minport'], config['maxport'], config['bind'], reuse=True, ipv6_socket_style=config['ipv6_binds_v4'], randomizer=config['random_port'])
        if DEBUG:
            log('LM::register: got listen port', self.listen_port)
        self.multihandler = MultiHandler(self.rawserver, self.sessdoneflag)
        self.shutdownstarttime = None
        if config['megacache']:
            cachedb.init(config, self.rawserver_fatalerrorfunc)
            self.my_db = MyDBHandler.getInstance()
            self.torrent_db = TorrentDBHandler.getInstance()
            torrent_collecting_dir = os.path.abspath(config['torrent_collecting_dir'])
            self.torrent_db.register(Category.getInstance(), torrent_collecting_dir)
            self.url2torrent_db = Url2TorrentDBHandler.getInstance()
            self.adid2infohash_db = AdID2InfohashDBHandler.getInstance()
            self.tsplayers_db = TsPlayersDBHandler.getInstance()
            self.tsmetadata_db = TsMetadataDBHandler.getInstance()
            self.user_profile_db = UserProfileDBHandler.getInstance()
            self.peer_db = None
            self.mypref_db = None
            self.pref_db = None
            self.superpeer_db = None
            self.crawler_db = None
            self.seedingstats_db = None
            self.seedingstatssettings_db = None
            self.friendship_statistics_db = None
            self.friend_db = None
            self.bartercast_db = None
            self.votecast_db = None
            self.channelcast_db = None
            self.mm = None
            self.richmetadataDbHandler = None
        else:
            config['overlay'] = 0
            config['torrent_checking'] = 0
            self.my_db = None
            self.peer_db = None
            self.torrent_db = None
            self.mypref_db = None
            self.pref_db = None
            self.superpeer_db = None
            self.crawler_db = None
            self.seedingstats_db = None
            self.seedingstatssettings_db = None
            self.friendship_statistics_db = None
            self.friend_db = None
            self.bartercast_db = None
            self.votecast_db = None
            self.channelcast_db = None
            self.mm = None
            self.richmetadataDbHandler = None
            self.url2torrent_db = None
        if config['overlay']:
            raise RuntimeError, 'Overlay should not be enabled'
            from ACEStream.Core.Overlay.SecureOverlay import SecureOverlay
            from ACEStream.Core.Overlay.OverlayThreadingBridge import OverlayThreadingBridge
            from ACEStream.Core.Overlay.OverlayApps import OverlayApps
            from ACEStream.Core.RequestPolicy import FriendsCoopDLOtherRQueryQuotumCrawlerAllowAllRequestPolicy
            self.secure_overlay = SecureOverlay.getInstance()
            self.secure_overlay.register(self, config['overlay_max_message_length'])
            self.overlay_apps = OverlayApps.getInstance()
            policy = FriendsCoopDLOtherRQueryQuotumCrawlerAllowAllRequestPolicy(self.session)
            self.overlay_bridge = OverlayThreadingBridge.getInstance()
            self.overlay_bridge.register_bridge(self.secure_overlay, self.overlay_apps)
            self.overlay_apps.register(self.overlay_bridge, self.session, self, config, policy)
            self.overlay_bridge.start_listening()
            if config['multicast_local_peer_discovery']:
                self.setup_multicast_discovery()
        else:
            self.secure_overlay = None
            self.overlay_apps = None
            config['buddycast'] = 0
            config['download_help'] = 0
            config['socnet'] = 0
            config['rquery'] = 0
            try:
                some_dialback_handler = DialbackMsgHandler.getInstance()
                some_dialback_handler.register_yourip(self)
            except:
                if DEBUG:
                    log_exc()

        if config['megacache'] or config['overlay']:
            Category.getInstance(config['install_dir'])
        self.internaltracker = None
        if config['internaltracker']:
            self.internaltracker = Tracker(config, self.rawserver)
            if self.session.app_http_handler is None:
                self.httphandler = HTTPHandler(self.internaltracker.get, config['tracker_min_time_between_log_flushes'])
            else:
                self.session.app_http_handler.set_default_http_handler(self.internaltracker.get)
                self.httphandler = HTTPHandler(self.session.app_http_handler.get, config['tracker_min_time_between_log_flushes'])
        elif self.session.app_http_handler is not None:
            self.httphandler = HTTPHandler(self.session.app_http_handler.get, 60)
        else:
            self.httphandler = DummyHTTPHandler()
        self.multihandler.set_httphandler(self.httphandler)
        if config['mainline_dht']:
            mainlineDHT.init(('127.0.0.1', self.listen_port), config['state_dir'])
        if config['torrent_checking']:
            if config['mainline_dht']:
                from ACEStream.Core.DecentralizedTracking.mainlineDHTChecker import mainlineDHTChecker
                c = mainlineDHTChecker.getInstance()
                c.register(mainlineDHT.dht)
            self.torrent_checking_period = config['torrent_checking_period']
            self.rawserver.add_task(self.run_torrent_check, self.torrent_checking_period)
        if config['magnetlink']:
            MagnetHandler.get_instance(self.rawserver)
        self.dispersy = None
        self.session.dispersy_member = None

    def start_dispersy(self):

        class DispersySocket(object):

            def __init__(self, rawserver, dispersy, port, ip = '0.0.0.0'):
                while True:
                    try:
                        self.socket = rawserver.create_udpsocket(port, ip)
                    except socket.error as error:
                        port += 1
                        continue

                    break

                self.rawserver = rawserver
                self.rawserver.start_listening_udp(self.socket, self)
                self.dispersy = dispersy

            def get_address(self):
                return self.socket.getsockname()

            def data_came_in(self, packets):
                if packets:
                    try:
                        self.dispersy.data_came_in(packets)
                    except:
                        log_exc()
                        raise

            def send(self, address, data):
                try:
                    self.socket.sendto(data, address)
                except socket.error as error:
                    if error[0] == SOCKET_BLOCK_ERRORCODE:
                        self.sendqueue.append((data, address))
                        self.rawserver.add_task(self.process_sendqueue, 0.1)

        config = self.session.sessconfig
        sqlite_db_path = os.path.join(config['state_dir'], u'sqlite')
        if not os.path.isdir(sqlite_db_path):
            os.makedirs(sqlite_db_path)
        self.dispersy = Dispersy.get_instance(self.dispersy_rawserver, sqlite_db_path)
        self.dispersy.socket = DispersySocket(self.rawserver, self.dispersy, config['dispersy_port'])
        from ACEStream.Core.Overlay.permid import read_keypair
        keypair = read_keypair(self.session.get_permid_keypair_filename())
        from ACEStream.Core.dispersy.crypto import ec_to_public_bin, ec_to_private_bin
        from ACEStream.Core.dispersy.member import MyMember
        self.session.dispersy_member = MyMember(ec_to_public_bin(keypair), ec_to_private_bin(keypair))
        AllChannelCommunity.load_communities(self.session.dispersy_member)
        communities = ChannelCommunity.load_communities()
        self.session.uch.notify(NTFY_DISPERSY, NTFY_STARTED, None)

    def add(self, tdef, dscfg, pstate = None, initialdlstatus = None):
        self.sesslock.acquire()
        try:
            if not tdef.is_finalized():
                raise ValueError('TorrentDef not finalized')
            infohash = tdef.get_infohash()
            if infohash in self.downloads[DLTYPE_TORRENT]:
                raise DuplicateDownloadException()
            if self.session.get_megacache():
                self.session.update_ts_metadata(tdef)
            d = Download(DLTYPE_TORRENT, self.session, tdef=tdef)
            if pstate is None and not tdef.get_live():
                pstate = self.load_download_pstate_noexc(DLTYPE_TORRENT, infohash)
                if pstate is not None:
                    if DEBUG:
                        log('LM::add: loaded pstate on startup: status', dlstatus_strings[pstate['dlstate']['status']], 'progress', pstate['dlstate']['progress'])
            self.downloads[DLTYPE_TORRENT][infohash] = d
            if DEBUG:
                log('LM::add: new download: infohash', infohash)
            d.setup(dscfg, pstate, initialdlstatus, self.network_engine_wrapper_created_callback, self.network_vod_event_callback)
            return d
        finally:
            self.sesslock.release()

    def add_direct_download(self, main_url, dcfg, pstate = None, initialdlstatus = None):
        self.sesslock.acquire()
        try:
            dlhash = hashlib.sha1(main_url).digest()
            if dlhash in self.downloads[DLTYPE_DIRECT]:
                raise DuplicateDownloadException()
            d = Download(DLTYPE_DIRECT, self.session, main_url=main_url)
            self.downloads[DLTYPE_DIRECT][dlhash] = d
            if pstate is None:
                pstate = self.load_download_pstate_noexc(DLTYPE_DIRECT, dlhash)
                if pstate is not None:
                    if DEBUG:
                        log('lm::add: loaded pstate on startup: status', dlstatus_strings[pstate['dlstate']['status']], 'progress', pstate['dlstate']['progress'])
            d.setup(dcfg, pstate, initialdlstatus, self.network_engine_wrapper_created_callback, self.network_vod_event_callback)
            return d
        finally:
            self.sesslock.release()

    def network_engine_wrapper_created_callback(self, download, download_engine, exc, pstate):
        if exc is None:
            try:
                if download_engine is not None:
                    dltype = download.get_type()
                    if dltype == DLTYPE_TORRENT:
                        self.queue_for_hashcheck(download_engine)
                        live = download.get_def().get_live()
                    elif dltype == DLTYPE_DIRECT:
                        live = False
                    if pstate is None and not live:
                        dlhash, pstate = download.network_checkpoint()
                        self.save_download_pstate(dltype, dlhash, pstate)
                else:
                    raise ACEStreamException('lm: network_engine_wrapper_created_callback: download_engine is None!')
            except Exception as e:
                log_exc()
                download.set_error(e)

    def remove(self, d, removecontent = False):
        self.sesslock.acquire()
        try:
            dltype = d.get_type()
            if DEBUG:
                log('lm::remove: d', d, 'type', dltype, 'removecontent', removecontent)
            d.stop_remove(removestate=True, removecontent=removecontent)
            dlhash = d.get_hash()
            del self.downloads[dltype][dlhash]
            if DEBUG:
                log('lm::remove: done: len(self.downloads)', len(self.downloads[dltype]))
        except:
            log_exc()
        finally:
            self.sesslock.release()

    def get_downloads(self, dltype):
        self.sesslock.acquire()
        try:
            return self.downloads[dltype].values()
        finally:
            self.sesslock.release()

    def get_download(self, dltype, infohash):
        self.sesslock.acquire()
        try:
            if infohash in self.downloads[dltype]:
                return self.downloads[dltype][infohash]
            return
        finally:
            self.sesslock.release()

    def download_exists(self, dltype, infohash):
        self.sesslock.acquire()
        try:
            return infohash in self.downloads[dltype]
        finally:
            self.sesslock.release()

    def rawserver_fatalerrorfunc(self, e):
        if DEBUG:
            print >> sys.stderr, 'tlm: RawServer fatal error func called', e
        log_exc()

    def rawserver_nonfatalerrorfunc(self, e):
        if DEBUG:
            print >> sys.stderr, 'tlm: RawServer non fatal error func called', e
        log_exc()

    def _run(self):
        try:
            self.start_upnp()
            self.start_multicast()
            self.multihandler.listen_forever()
        except Exception as e:
            log_exc()
            self.session.on_error(e)
        finally:
            if self.internaltracker is not None:
                self.internaltracker.save_state()
            self.stop_upnp()
            self.rawserver.shutdown()
            self.session.on_stop()

    def rawserver_keepalive(self):
        self.rawserver.add_task(self.rawserver_keepalive, 1)

    def tracker_rescan_dir(self):
        if self.internaltracker is not None:
            self.internaltracker.parse_allowed(source='Session')

    def queue_for_hashcheck(self, sd):
        if hash:
            self.hashcheck_queue.append(sd)
            self.hashcheck_queue.sort(singledownload_size_cmp)
        if not self.sdownloadtohashcheck:
            self.dequeue_and_start_hashcheck()
        elif DEBUG:
            log('lm::queue_for_hashcheck: another sd is checked: checked', binascii.hexlify(self.sdownloadtohashcheck.infohash), 'queued', binascii.hexlify(sd.infohash), 'thread', currentThread().getName())

    def dequeue_and_start_hashcheck(self):
        self.sdownloadtohashcheck = self.hashcheck_queue.pop(0)
        if DEBUG:
            log('lm::dequeue_and_start_hashcheck: infohash', binascii.hexlify(self.sdownloadtohashcheck.infohash), 'thread', currentThread().getName())
        self.sdownloadtohashcheck.perform_hashcheck(self.hashcheck_done)

    def hashcheck_done(self, sd, success = True):
        if DEBUG:
            infohash = binascii.hexlify(sd.infohash)
            log('lm::hashcheck_done: success', success, 'infohash', infohash, 'len_queue', len(self.hashcheck_queue), 'thread', currentThread().getName())
        if success:
            if DEBUG:
                t = time.time()
            sd.hashcheck_done()
            if DEBUG:
                log('lm::hashcheck_done: sd.hashcheck_done() finished, time', time.time() - t)
        try:
            self.hashcheck_queue.remove(sd)
            if DEBUG:
                log('lm::hashcheck_done: sd removed from queue: infohash', binascii.hexlify(sd.infohash), 'thread', currentThread().getName())
        except:
            if DEBUG:
                log('lm::hashcheck_done: sd not found in queue: infohash', binascii.hexlify(sd.infohash), 'thread', currentThread().getName())

        if DEBUG:
            log('lm::hashcheck_done: len(queue)', len(self.hashcheck_queue), 'thread', currentThread().getName())
        if self.hashcheck_queue:
            self.dequeue_and_start_hashcheck()
        else:
            self.sdownloadtohashcheck = None

    def set_download_states_callback(self, usercallback, getpeerlist, when = 0.0):
        network_set_download_states_callback_lambda = lambda : self.network_set_download_states_callback(usercallback, getpeerlist)
        self.rawserver.add_task(network_set_download_states_callback_lambda, when)

    def network_set_download_states_callback(self, usercallback, getpeerlist):
        self.sesslock.acquire()
        try:
            dllist = []
            dllist.extend(self.downloads[DLTYPE_TORRENT].values())
            dllist.extend(self.downloads[DLTYPE_DIRECT].values())
        finally:
            self.sesslock.release()

        dslist = []
        for d in dllist:
            ds = d.network_get_state(None, getpeerlist, sessioncalling=True)
            dslist.append(ds)

        self.session.uch.perform_getstate_usercallback(usercallback, dslist, self.sesscb_set_download_states_returncallback)

    def sesscb_set_download_states_returncallback(self, usercallback, when, newgetpeerlist):
        if when > 0.0:
            self.set_download_states_callback(usercallback, newgetpeerlist, when=when)

    def load_checkpoint(self, initialdlstatus = None):
        self.sesslock.acquire()
        try:
            for dltype in [DLTYPE_TORRENT, DLTYPE_DIRECT]:
                path = self.session.get_downloads_pstate_dir(dltype)
                filelist = os.listdir(path)
                for basename in filelist:
                    filename = os.path.join(path, basename)
                    if DEBUG:
                        log('lm::load_checkpoint: found file: dltype', dltype, 'filename', filename, 'initialdlstatus', initialdlstatus)
                    self.resume_download(dltype, filename, initialdlstatus)

        finally:
            self.sesslock.release()

    def load_download_pstate_noexc(self, dltype, dlhash):
        try:
            path = self.session.get_downloads_pstate_dir(dltype)
            basename = binascii.hexlify(dlhash) + '.pickle'
            filename = os.path.join(path, basename)
            return self.load_download_pstate(filename)
        except Exception as e:
            return None

    def resume_download(self, dltype, filename, initialdlstatus = None):
        try:
            pstate = self.load_download_pstate(filename)
            if DEBUG:
                log('lm::resume_download: dltype', dltype, 'filename', filename, 'dlconfig', pstate['dlconfig'])
            if DEBUG:
                log('lm::resume_download: status', dlstatus_strings[pstate['dlstate']['status']], 'progress', pstate['dlstate']['progress'])
                if pstate['engineresumedata'] is None:
                    log('lm::resume_download: resumedata None')
                else:
                    log('lm::resume_download: resumedata len', len(pstate['engineresumedata']))
            dscfg = DownloadStartupConfig(dlconfig=pstate['dlconfig'])
            if dltype == DLTYPE_TORRENT:
                tdef = TorrentDef.load_from_dict(pstate['metainfo'])
                d = self.add(tdef, dscfg, pstate, initialdlstatus)
            elif dltype == DLTYPE_DIRECT:
                main_url = pstate['url']
                d = self.add_direct_download(main_url, dscfg, pstate, initialdlstatus)
            if initialdlstatus == DLSTATUS_STOPPED:
                dest_files = d.get_dest_files(get_all=True)
                if DEBUG:
                    log('lm::resume_download: check dest files: dest_files', dest_files)
                got_existing_file = False
                for filename, savepath in dest_files:
                    if os.path.exists(savepath):
                        got_existing_file = True
                        break

                if not got_existing_file:
                    if DEBUG:
                        log('lm::resume_download: none of the files exists, remove this download')
                    self.remove(d, removecontent=True)
        except Exception as e:
            if DEBUG:
                log('lm::resume_download: failed to load checkpoint: filename', filename)
                print_exc()
            try:
                if os.access(filename, os.F_OK):
                    os.remove(filename)
            except:
                print_exc()

    def checkpoint(self, stop = False, checkpoint = True, gracetime = 2.0):
        dllist = []
        dllist.extend(self.downloads[DLTYPE_TORRENT].values())
        dllist.extend(self.downloads[DLTYPE_DIRECT].values())
        if DEBUG:
            log('LM::checkpoint: count', len(dllist))
        network_checkpoint_callback_lambda = lambda : self.network_checkpoint_callback(dllist, stop, checkpoint, gracetime)
        self.rawserver.add_task(network_checkpoint_callback_lambda, 0.0)

    def network_checkpoint_callback(self, dllist, stop, checkpoint, gracetime):
        if checkpoint:
            for d in dllist:
                if DEBUG:
                    log('lm::network_checkpoint_callback: hash', binascii.hexlify(d.get_hash()))
                if stop:
                    dlhash, pstate = d.network_stop(False, False)
                else:
                    dlhash, pstate = d.network_checkpoint()
                if d.get_type() == DLTYPE_TORRENT:
                    live = d.get_def().get_live()
                else:
                    live = False
                if not live:
                    try:
                        self.save_download_pstate(d.get_type(), dlhash, pstate)
                    except Exception as e:
                        self.rawserver_nonfatalerrorfunc(e)

        if stop:
            if self.shutdownstarttime is not None:
                now = time.time()
                diff = now - self.shutdownstarttime
                if diff < gracetime:
                    if DEBUG:
                        print >> sys.stderr, 'tlm: shutdown: delaying for early shutdown tasks', gracetime - diff
                    delay = gracetime - diff
                    network_shutdown_callback_lambda = lambda : self.network_shutdown()
                    self.rawserver.add_task(network_shutdown_callback_lambda, delay)
                    return
            self.network_shutdown()

    def early_shutdown(self):
        self.shutdownstarttime = time.time()
        if self.overlay_apps is not None:
            self.overlay_bridge.add_task(self.overlay_apps.early_shutdown, 0)
        if self.udppuncture_handler is not None:
            self.udppuncture_handler.shutdown()

    def network_shutdown(self):
        try:
            if self.peer_db is not None:
                db = SQLiteCacheDB.getInstance()
                db.commit()
            mainlineDHT.deinit()
            if DEBUG:
                ts = enumerate()
                log('LM::network_shutdown: number of threads still running', len(ts))
                for t in ts:
                    log('LM::network_shutdown: thread still running', t.name, 'daemon', t.daemon, 'instance', t)

        except:
            log_exc()

        self.sessdoneflag.set()
        self.session.uch.shutdown()

    def save_download_pstate(self, dltype, dlhash, pstate):
        basename = binascii.hexlify(dlhash) + '.pickle'
        filename = os.path.join(self.session.get_downloads_pstate_dir(dltype), basename)
        if DEBUG:
            log('LM::save_download_pstate: filename', filename, 'pstate', pstate)
        key = 'Hf9Jfn8*;@sg,9q/'
        data = pickle.dumps(pstate)
        data = m2_AES_encrypt(data, key)
        data = chr(45) + chr(3) + chr(89) + chr(120) + data
        f = open(filename, 'wb')
        f.write(data)
        f.close()

    def load_download_pstate(self, filename):
        f = open(filename, 'rb')
        try:
            data = f.read()
        except:
            raise
        finally:
            f.close()

        if data[:4] == chr(45) + chr(3) + chr(89) + chr(120):
            data = data[4:]
            key = 'Hf9Jfn8*;@sg,9q/'
            data = m2_AES_decrypt(data, key)
        pstate = pickle.loads(data)
        return pstate

    def guess_ext_ip_from_local_info(self):
        try:
            ip = get_my_wan_ip()
            if DEBUG:
                log('lm::guess_ext_ip_from_local_info: result of get_my_wan_ip()', ip)
            if ip is None:
                host = socket.gethostbyname_ex(socket.gethostname())
                if DEBUG:
                    log('lm::guess_ext_ip_from_local_info: try to find ip from host: hostname', socket.gethostname(), 'result', host)
                ipaddrlist = host[2]
                for ip in ipaddrlist:
                    return ip

                return '127.0.0.1'
            return ip
        except:
            return '127.0.0.1'

    def run(self):
        if PROFILE:
            fname = 'profile-%s' % self.getName()
            import cProfile
            cProfile.runctx('self._run()', globals(), locals(), filename=fname)
            import pstats
            print >> sys.stderr, 'profile: data for %s' % self.getName()
            pstats.Stats(fname, stream=sys.stderr).sort_stats('cumulative').print_stats(20)
        else:
            self._run()

    def start_upnp(self):
        if DEBUG:
            log('lm::start_upnp: upnp_type', self.upnp_type, 'locally_guessed_ext_ip', self.locally_guessed_ext_ip, 'listen_port', self.listen_port)
        self.set_activity(NTFY_ACT_UPNP)
        self.upnp_thread = UPnPThread(self.upnp_type, self.locally_guessed_ext_ip, self.listen_port, self.upnp_failed_callback, self.upnp_got_ext_ip_callback)
        self.upnp_thread.start()

    def stop_upnp(self):
        if self.upnp_type > 0:
            if DEBUG:
                log('lm::stop_upnp: ---')
            self.upnp_thread.shutdown()

    def upnp_failed_callback(self, upnp_type, listenport, error_type, exc = None, listenproto = 'TCP'):
        if DEBUG:
            log('lm::upnp_failed_callback: upnp_type', upnp_type, 'listenport', listenport, 'listenproto', listenproto, 'error_type', error_type, 'exc', str(exc))

    def upnp_got_ext_ip_callback(self, ip):
        self.sesslock.acquire()
        self.upnp_ext_ip = ip
        self.sesslock.release()
        if DEBUG:
            log('lm::upnp_got_ext_ip_callback: ip', ip)

    def dialback_got_ext_ip_callback(self, ip):
        self.sesslock.acquire()
        self.dialback_ext_ip = ip
        self.sesslock.release()
        if DEBUG:
            log('lm::dialback_got_ext_ip_callback: ip', ip)

    def yourip_got_ext_ip_callback(self, ip):
        self.sesslock.acquire()
        self.yourip_ext_ip = ip
        self.sesslock.release()
        if DEBUG:
            log('lm::yourip_got_ext_ip_callback: ip', ip)

    def get_ext_ip(self, unknowniflocal = False):
        self.sesslock.acquire()
        try:
            if self.dialback_ext_ip is not None:
                return self.dialback_ext_ip
            if self.upnp_ext_ip is not None:
                return self.upnp_ext_ip
            if self.yourip_ext_ip is not None:
                return self.yourip_ext_ip
            if unknowniflocal:
                return
            return self.locally_guessed_ext_ip
        finally:
            self.sesslock.release()

    def get_int_ip(self):
        self.sesslock.acquire()
        try:
            return self.locally_guessed_ext_ip
        finally:
            self.sesslock.release()

    def dialback_reachable_callback(self):
        self.session.uch.notify(NTFY_REACHABLE, NTFY_INSERT, None, '')

    def set_activity(self, type, str = '', arg2 = None):
        self.session.uch.notify(NTFY_ACTIVITIES, NTFY_INSERT, type, str, arg2)

    def network_vod_event_callback(self, videoinfo, event, params):
        if DEBUG:
            log('lm::network_vod_event_callback: event %s, params %s' % (event, params))
        try:
            videoinfo['usercallback'](event, params)
        except:
            log_exc()

    def update_torrent_checking_period(self):
        if self.overlay_apps and self.overlay_apps.metadata_handler:
            ntorrents = self.overlay_apps.metadata_handler.num_torrents
            if ntorrents > 0:
                self.torrent_checking_period = min(max(86400 / ntorrents, 15), 300)

    def run_torrent_check(self):
        self.update_torrent_checking_period()
        self.rawserver.add_task(self.run_torrent_check, self.torrent_checking_period)
        try:
            from ACEStream.TrackerChecking.TorrentChecking import TorrentChecking
            t = TorrentChecking()
            t.start()
        except Exception as e:
            log_exc()
            self.rawserver_nonfatalerrorfunc(e)

    def get_coopdl_role_object(self, infohash, role):
        role_object = None
        self.sesslock.acquire()
        try:
            if infohash in self.downloads:
                d = self.downloads[infohash]
                role_object = d.get_coopdl_role_object(role)
        finally:
            self.sesslock.release()

        return role_object

    def h4xor_reset_init_conn_counter(self):
        self.rawserver.add_task(self.network_h4xor_reset, 0)

    def network_h4xor_reset(self):
        if DEBUG:
            log('lm::network_h4xor_reset: resetting outgoing TCP connection rate limiter', incompletecounter.c)
        incompletecounter.c = 0

    def setup_multicast_discovery(self):
        mc_config = {'permid': self.session.get_permid(),
         'multicast_ipv4_address': '224.0.1.43',
         'multicast_ipv6_address': 'ff02::4124:1261:ffef',
         'multicast_port': '32109',
         'multicast_enabled': True,
         'multicast_ipv4_enabled': True,
         'multicast_ipv6_enabled': False,
         'multicast_announce': True}
        from ACEStream.Core.Overlay.SecureOverlay import OLPROTO_VER_CURRENT
        from ACEStream.Core.Multicast import Multicast
        self.mc_channel = Multicast(mc_config, self.overlay_bridge, self.listen_port, OLPROTO_VER_CURRENT, self.peer_db)
        self.mc_channel.addAnnounceHandler(self.mc_channel.handleOVERLAYSWARMAnnounce)
        self.mc_sock = self.mc_channel.getSocket()
        self.mc_sock.setblocking(0)

    def start_multicast(self):
        if not self.session.get_overlay() or not self.session.get_multicast_local_peer_discovery():
            return
        self.rawserver.start_listening_udp(self.mc_sock, self.mc_channel)
        print >> sys.stderr, 'mcast: Sending node announcement'
        params = [self.session.get_listen_port(), self.secure_overlay.olproto_ver_current]
        self.mc_channel.sendAnnounce(params)


def singledownload_size_cmp(x, y):
    if x is None and y is None:
        return 0
    elif x is None:
        return 1
    elif y is None:
        return -1
    a = x.get_bt1download()
    b = y.get_bt1download()
    if a is None and b is None:
        return 0
    elif a is None:
        return 1
    elif b is None:
        return -1
    elif a.get_datalength() == b.get_datalength():
        return 0
    elif a.get_datalength() < b.get_datalength():
        return -1
    else:
        return 1
