#Embedded file name: ACEStream\Core\Session.pyo
import os
import sys
import copy
import hashlib
import binascii
import urllib
from threading import RLock
from ACEStream.__init__ import LIBRARYNAME
from ACEStream.GlobalConfig import globalConfig
from ACEStream.Core.simpledefs import *
from ACEStream.Core.defaults import sessdefaults
from ACEStream.Core.Base import *
from ACEStream.Core.SessionConfig import *
from ACEStream.Core.DownloadConfig import get_default_dest_dir
from ACEStream.Core.Utilities.utilities import find_prog_in_PATH
from ACEStream.Core.APIImplementation.SessionRuntimeConfig import SessionRuntimeConfig
from ACEStream.Core.APIImplementation.LaunchManyCore import ACEStreamLaunchMany
from ACEStream.Core.APIImplementation.UserCallbackHandler import UserCallbackHandler
from ACEStream.Core.osutils import get_appstate_dir
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.NATFirewall.ConnectionCheck import ConnectionCheck
GOTM2CRYPTO = False
try:
    import M2Crypto
    import ACEStream.Core.Overlay.permid as permidmod
    GOTM2CRYPTO = True
except ImportError:
    pass

DEBUG = False

class Session(SessionRuntimeConfig):
    __single = None

    def __init__(self, scfg = None, ignore_singleton = False, on_error = lambda e: None, on_stop = lambda : None, app_http_handler = None, network_thread_daemon = True):
        if not ignore_singleton:
            if Session.__single:
                raise RuntimeError, 'Session is singleton'
            Session.__single = self
        self.sesslock = RLock()
        self.on_error = on_error
        self.on_stop = on_stop
        self.app_http_handler = app_http_handler
        first_run = False
        if scfg is None:
            try:
                state_dir = Session.get_default_state_dir()
                cfgfilename = Session.get_default_config_filename(state_dir)
                scfg = SessionStartupConfig.load(cfgfilename)
            except:
                log_exc()
                scfg = SessionStartupConfig()

            self.sessconfig = scfg.sessconfig
        else:
            self.sessconfig = copy.copy(scfg.sessconfig)
        state_dir = self.sessconfig['state_dir']
        if state_dir is None:
            state_dir = Session.get_default_state_dir()
            self.sessconfig['state_dir'] = state_dir
        if not os.path.isdir(state_dir):
            first_run = True
            os.makedirs(state_dir)
        collected_torrent_dir = self.sessconfig['torrent_collecting_dir']
        if not collected_torrent_dir:
            collected_torrent_dir = os.path.join(self.sessconfig['state_dir'], STATEDIR_TORRENTCOLL_DIR)
            self.sessconfig['torrent_collecting_dir'] = collected_torrent_dir
        collected_subtitles_dir = self.sessconfig.get('subtitles_collecting_dir', None)
        if not collected_subtitles_dir:
            collected_subtitles_dir = os.path.join(self.sessconfig['state_dir'], STATEDIR_SUBSCOLL_DIR)
            self.sessconfig['subtitles_collecting_dir'] = collected_subtitles_dir
        if not os.path.exists(collected_torrent_dir):
            first_run = True
            os.makedirs(collected_torrent_dir)
        buffer_dir = self.sessconfig.get('buffer_dir', None)
        if not buffer_dir:
            buffer_dir = os.path.join(self.sessconfig['state_dir'], STATEDIR_BUFFER_DIR)
            self.sessconfig['buffer_dir'] = buffer_dir
        if not os.path.exists(buffer_dir):
            first_run = True
            os.makedirs(buffer_dir)
        ads_dir = self.sessconfig.get('ads_dir', None)
        if not ads_dir:
            ads_dir = os.path.join(self.sessconfig['state_dir'], STATEDIR_ADS_DIR)
            self.sessconfig['ads_dir'] = ads_dir
        if not os.path.exists(ads_dir):
            first_run = True
            os.makedirs(ads_dir)
        if 'ts_login' in self.sessconfig:
            if first_run and len(self.sessconfig['ts_login']) == 0:
                self.sessconfig['ts_login'] = 'test'
        else:
            self.sessconfig['ts_login'] = sessdefaults['ts_login']
        if 'ts_password' in self.sessconfig:
            if first_run and len(self.sessconfig['ts_password']) == 0:
                self.sessconfig['ts_password'] = 'test'
        else:
            self.sessconfig['ts_password'] = sessdefaults['ts_password']
        if 'ts_user_key' not in self.sessconfig:
            self.sessconfig['ts_user_key'] = sessdefaults['ts_user_key']
        if 'max_socket_connects' not in self.sessconfig:
            self.sessconfig['max_socket_connects'] = sessdefaults['max_socket_connects']
        if not self.sessconfig['peer_icon_path']:
            self.sessconfig['peer_icon_path'] = os.path.join(self.sessconfig['state_dir'], STATEDIR_PEERICON_DIR)
        if GOTM2CRYPTO:
            permidmod.init()
            pairfilename = os.path.join(self.sessconfig['state_dir'], 'ec.pem')
            if self.sessconfig['eckeypairfilename'] is None:
                self.sessconfig['eckeypairfilename'] = pairfilename
            if os.access(self.sessconfig['eckeypairfilename'], os.F_OK):
                self.keypair = permidmod.read_keypair(self.sessconfig['eckeypairfilename'])
            else:
                self.keypair = permidmod.generate_keypair()
                pubfilename = os.path.join(self.sessconfig['state_dir'], 'ecpub.pem')
                permidmod.save_keypair(self.keypair, pairfilename)
                permidmod.save_pub_key(self.keypair, pubfilename)
        else:
            self.keypair = None
        dlpstatedir = os.path.join(self.sessconfig['state_dir'], STATEDIR_DLPSTATE_DIR)
        if not os.path.isdir(dlpstatedir):
            os.mkdir(dlpstatedir)
        dl_direct_pstatedir = os.path.join(self.sessconfig['state_dir'], STATEDIR_DLDIRECT_PSTATE_DIR)
        if not os.path.isdir(dl_direct_pstatedir):
            os.mkdir(dl_direct_pstatedir)
        trackerdir = self.get_internal_tracker_dir()
        if not os.path.isdir(trackerdir):
            os.mkdir(trackerdir)
        if self.sessconfig['tracker_dfile'] is None:
            self.sessconfig['tracker_dfile'] = os.path.join(trackerdir, 'tracker.db')
        if self.sessconfig['tracker_allowed_dir'] is None:
            self.sessconfig['tracker_allowed_dir'] = trackerdir
        if self.sessconfig['tracker_logfile'] is None:
            if sys.platform == 'win32':
                sink = 'nul'
            else:
                sink = '/dev/null'
            self.sessconfig['tracker_logfile'] = sink
        if self.sessconfig['superpeer_file'] is None:
            self.sessconfig['superpeer_file'] = os.path.join(self.sessconfig['install_dir'], LIBRARYNAME, 'Core', 'superpeer.txt')
        if 'crawler_file' not in self.sessconfig or self.sessconfig['crawler_file'] is None:
            self.sessconfig['crawler_file'] = os.path.join(self.sessconfig['install_dir'], LIBRARYNAME, 'Core', 'Statistics', 'crawler.txt')
        if self.sessconfig['overlay'] and self.sessconfig['download_help']:
            if self.sessconfig['download_help_dir'] is None:
                self.sessconfig['download_help_dir'] = os.path.join(get_default_dest_dir(), DESTDIR_COOPDOWNLOAD)
            if not os.path.isdir(self.sessconfig['download_help_dir']):
                os.makedirs(self.sessconfig['download_help_dir'])
        if self.sessconfig['peer_icon_path'] is None:
            self.sessconfig['peer_icon_path'] = os.path.join(self.sessconfig['state_dir'], STATEDIR_PEERICON_DIR)
            if not os.path.isdir(self.sessconfig['peer_icon_path']):
                os.mkdir(self.sessconfig['peer_icon_path'])
        for key, defvalue in sessdefaults.iteritems():
            if key not in self.sessconfig:
                self.sessconfig[key] = defvalue

        if 'live_aux_seeders' not in self.sessconfig:
            self.sessconfig['live_aux_seeders'] = sessdefaults['live_aux_seeders']
        if 'nat_detect' not in self.sessconfig:
            self.sessconfig['nat_detect'] = sessdefaults['nat_detect']
        if 'puncturing_internal_port' not in self.sessconfig:
            self.sessconfig['puncturing_internal_port'] = sessdefaults['puncturing_internal_port']
        if 'stun_servers' not in self.sessconfig:
            self.sessconfig['stun_servers'] = sessdefaults['stun_servers']
        if 'pingback_servers' not in self.sessconfig:
            self.sessconfig['pingback_servers'] = sessdefaults['pingback_servers']
        if 'mainline_dht' not in self.sessconfig:
            self.sessconfig['mainline_dht'] = sessdefaults['mainline_dht']
        self.http_seeds = {}
        self.save_pstate_sessconfig()
        self.uch = UserCallbackHandler(self)
        self.lm = ACEStreamLaunchMany(network_thread_daemon)
        self.lm.register(self, self.sesslock)
        self.lm.start()

    def get_instance(*args, **kw):
        if Session.__single is None:
            Session(*args, **kw)
        return Session.__single

    get_instance = staticmethod(get_instance)

    def get_default_state_dir():
        if globalConfig.get_value('apptype', '') == 'torrentstream':
            homedirpostfix = '.Torrent Stream'
        else:
            homedirpostfix = '.ACEStream'
        appdir = get_appstate_dir()
        statedir = os.path.join(appdir, homedirpostfix)
        return statedir

    get_default_state_dir = staticmethod(get_default_state_dir)

    def get_listen_port(self):
        return self.lm.listen_port

    def start_download(self, tdef, dcfg = None, initialdlstatus = None):
        return self.lm.add(tdef, dcfg, initialdlstatus=initialdlstatus)

    def start_direct_download(self, main_url, dcfg = None, initialdlstatus = None):
        return self.lm.add_direct_download(main_url, dcfg, initialdlstatus=initialdlstatus)

    def resume_download_from_file(self, filename):
        raise NotYetImplementedException()

    def get_all_downloads(self):
        downloads = []
        downloads.extend(self.lm.get_downloads(DLTYPE_TORRENT))
        downloads.extend(self.lm.get_downloads(DLTYPE_DIRECT))
        return downloads

    def get_downloads(self, type = DLTYPE_TORRENT):
        return self.lm.get_downloads(type)

    def get_download(self, type, infohash):
        return self.lm.get_download(type, infohash)

    def download_exists(self, type, infohash):
        return self.lm.download_exists(type, infohash)

    def remove_download(self, d, removecontent = False):
        self.lm.remove(d, removecontent=removecontent)

    def set_download_states_callback(self, usercallback, getpeerlist = False):
        self.lm.set_download_states_callback(usercallback, getpeerlist)

    def get_permid(self):
        self.sesslock.acquire()
        try:
            if self.keypair is None:
                return ''
            return str(self.keypair.pub().get_der())
        finally:
            self.sesslock.release()

    def get_external_ip(self):
        return self.lm.get_ext_ip()

    def get_externally_reachable(self):
        from ACEStream.Core.NATFirewall.DialbackMsgHandler import DialbackMsgHandler
        return DialbackMsgHandler.getInstance().isConnectable()

    def get_current_startup_config_copy(self):
        self.sesslock.acquire()
        try:
            sessconfig = copy.copy(self.sessconfig)
            return SessionStartupConfig(sessconfig=sessconfig)
        finally:
            self.sesslock.release()

    def get_internal_tracker_url(self):
        self.sesslock.acquire()
        try:
            url = self.sessconfig.get('tracker_url', None)
            if url is not None:
                return url
            ip = self.lm.get_ext_ip()
            port = self.get_listen_port()
            url = 'http://' + ip + ':' + str(port) + '/announce/'
            self.sessconfig['tracker_url'] = url
            return url
        finally:
            self.sesslock.release()

    def get_internal_tracker_dir(self):
        self.sesslock.acquire()
        try:
            if self.sessconfig['state_dir'] is None:
                return
            return os.path.join(self.sessconfig['state_dir'], STATEDIR_ITRACKER_DIR)
        finally:
            self.sesslock.release()

    def add_to_internal_tracker(self, tdef):
        self.sesslock.acquire()
        try:
            infohash = tdef.get_infohash()
            filename = self.get_internal_tracker_torrentfilename(infohash)
            tdef.save(filename)
            if DEBUG:
                log('session::add_to_int_tracker: filename', filename, 'url-compat', tdef.get_url_compat())
            self.lm.tracker_rescan_dir()
        finally:
            self.sesslock.release()

    def remove_from_internal_tracker(self, tdef):
        infohash = tdef.get_infohash()
        self.remove_from_internal_tracker_by_infohash(infohash)

    def remove_from_internal_tracker_by_infohash(self, infohash):
        self.sesslock.acquire()
        try:
            filename = self.get_internal_tracker_torrentfilename(infohash)
            if DEBUG:
                print >> sys.stderr, 'Session: removing itracker entry', filename
            if os.access(filename, os.F_OK):
                os.remove(filename)
            self.lm.tracker_rescan_dir()
        finally:
            self.sesslock.release()

    def add_observer(self, func, subject, changeTypes = [NTFY_UPDATE, NTFY_INSERT, NTFY_DELETE], objectID = None):
        self.uch.notifier.add_observer(func, subject, changeTypes, objectID)

    def remove_observer(self, func):
        self.uch.notifier.remove_observer(func)

    def open_dbhandler(self, subject):
        self.sesslock.acquire()
        try:
            if not self.get_megacache():
                return
            if subject == NTFY_PEERS:
                return self.lm.peer_db
            if subject == NTFY_TORRENTS:
                return self.lm.torrent_db
            if subject == NTFY_PREFERENCES:
                return self.lm.pref_db
            if subject == NTFY_SUPERPEERS:
                return self.lm.superpeer_db
            if subject == NTFY_FRIENDS:
                return self.lm.friend_db
            if subject == NTFY_MYPREFERENCES:
                return self.lm.mypref_db
            if subject == NTFY_BARTERCAST:
                return self.lm.bartercast_db
            if subject == NTFY_SEEDINGSTATS:
                return self.lm.seedingstats_db
            if subject == NTFY_SEEDINGSTATSSETTINGS:
                return self.lm.seedingstatssettings_db
            if subject == NTFY_VOTECAST:
                return self.lm.votecast_db
            if subject == NTFY_SEARCH:
                return self.lm.search_db
            if subject == NTFY_TERM:
                return self.lm.term_db
            if subject == NTFY_CHANNELCAST:
                return self.lm.channelcast_db
            if subject == NTFY_RICH_METADATA:
                return self.lm.richmetadataDbHandler
            if subject == NTFY_URL2TORRENT:
                return self.lm.url2torrent_db
            if subject == NTFY_ADID2INFOHASH:
                return self.lm.adid2infohash_db
            if subject == NTFY_TS_PLAYERS:
                return self.lm.tsplayers_db
            if subject == NTFY_TS_METADATA:
                return self.lm.tsmetadata_db
            if subject == NTFY_USER_PROFILE:
                return self.lm.user_profile_db
            raise ValueError('Cannot open DB subject: ' + subject)
        finally:
            self.sesslock.release()

    def close_dbhandler(self, dbhandler):
        dbhandler.close()

    def set_overlay_request_policy(self, reqpol):
        self.sesslock.acquire()
        try:
            overlay_loaded = self.sessconfig['overlay']
        finally:
            self.sesslock.release()

        if overlay_loaded:
            self.lm.overlay_apps.setRequestPolicy(reqpol)
        elif DEBUG:
            print >> sys.stderr, 'Session: overlay is disabled, so no overlay request policy needed'

    def load_checkpoint(self, initialdlstatus = None):
        self.lm.load_checkpoint(initialdlstatus)

    def checkpoint(self):
        self.checkpoint_shutdown(stop=False, checkpoint=True, gracetime=None, hacksessconfcheckpoint=False)

    def shutdown(self, checkpoint = True, gracetime = 2.0, hacksessconfcheckpoint = True):
        self.lm.early_shutdown()
        self.checkpoint_shutdown(stop=True, checkpoint=checkpoint, gracetime=gracetime, hacksessconfcheckpoint=hacksessconfcheckpoint)

    def has_shutdown(self):
        return self.lm.sessdoneflag.isSet()

    def get_downloads_pstate_dir(self, dltype):
        self.sesslock.acquire()
        try:
            if dltype == DLTYPE_TORRENT:
                path = STATEDIR_DLPSTATE_DIR
            elif dltype == DLTYPE_DIRECT:
                path = STATEDIR_DLDIRECT_PSTATE_DIR
            else:
                raise ValueError('Unknonw download type ' + str(dltype))
            return os.path.join(self.sessconfig['state_dir'], path)
        finally:
            self.sesslock.release()

    def save_torrent_local(self, tdef, checksum):
        save_name = binascii.hexlify(tdef.get_infohash()) + '.torrent'
        torrent_dir = self.get_torrent_collecting_dir()
        save_path = os.path.join(torrent_dir, save_name)
        if DEBUG:
            log('session::save_torrent_local: save torrent: save_path', save_path, 'checksum', binascii.hexlify(checksum))
        torrent_data = tdef.save(save_path)
        extra_info = {'status': 'good'}
        extra_info['filename'] = save_name
        extra_info['checksum'] = checksum
        db = self.open_dbhandler(NTFY_TORRENTS)
        if db is None:
            return
        try:
            db.addExternalTorrent(tdef, source='', extra_info=extra_info)
        except:
            if DEBUG:
                log_exc()
        finally:
            self.close_dbhandler(db)

    def get_ts_http_seeds(self, infohash):
        self.sesslock.acquire()
        try:
            if infohash in self.http_seeds:
                return self.http_seeds[infohash]
            return
        finally:
            self.sesslock.release()

    def set_ts_http_seeds(self, infohash, http_seeds):
        self.sesslock.acquire()
        try:
            self.http_seeds[infohash] = http_seeds
        finally:
            self.sesslock.release()

    def get_ts_metadata_from_db(self, infohash):
        if DEBUG:
            log('session::get_ts_metadata_from_db: infohash', binascii.hexlify(infohash))
        db = self.open_dbhandler(NTFY_TS_METADATA)
        if db is None:
            return
        try:
            return db.get(infohash)
        except:
            log_exc()
            return
        finally:
            if db is not None:
                self.close_dbhandler(db)

    def save_ts_metadata_db(self, infohash, metadata):
        if metadata is None:
            return
        if DEBUG:
            log('session::save_ts_metadata_db: infohash', binascii.hexlify(infohash), 'metadata', metadata)
        db = self.open_dbhandler(NTFY_TS_METADATA)
        if db is None:
            return
        try:
            db.put(infohash, metadata)
        except:
            log_exc()
        finally:
            if db is not None:
                self.close_dbhandler(db)

    def update_ts_metadata(self, tdef):
        metadata = self.get_ts_metadata_from_db(tdef.get_infohash())
        if DEBUG:
            log('session::update_ts_metadata: infohash', binascii.hexlify(tdef.get_infohash()), 'metadata', metadata)
        if metadata is None:
            return
        tdef_metadata = tdef.get_ts_metadata()
        if tdef_metadata is None:
            tdef_metadata = {}
        if DEBUG:
            log('session::update_ts_metadata: before update: infohash', binascii.hexlify(tdef.get_infohash()), 'metadata', metadata, 'tdef_metadata', tdef_metadata)
        tdef_metadata.update(metadata)
        if DEBUG:
            log('session::update_ts_metadata: after update: infohash', binascii.hexlify(tdef.get_infohash()), 'tdef_metadata', tdef_metadata)
        tdef.set_ts_metadata(tdef_metadata)

    def query_connected_peers(self, query, usercallback, max_peers_to_query = None):
        self.sesslock.acquire()
        try:
            if self.sessconfig['overlay']:
                if not (query.startswith('SIMPLE ') or query.startswith('SIMPLE+METADATA ')) and not query.startswith('CHANNEL '):
                    raise ValueError('Query does not start with SIMPLE or SIMPLE+METADATA or CHANNEL (%s)' % query)
                from ACEStream.Core.SocialNetwork.RemoteQueryMsgHandler import RemoteQueryMsgHandler
                rqmh = RemoteQueryMsgHandler.getInstance()
                rqmh.send_query(query, usercallback, max_peers_to_query=max_peers_to_query)
            else:
                raise OperationNotEnabledByConfigurationException('Overlay not enabled')
        finally:
            self.sesslock.release()

    def query_peers(self, query, peers, usercallback):
        self.sesslock.acquire()
        try:
            if self.sessconfig['overlay']:
                if not (query.startswith('SIMPLE ') or query.startswith('SIMPLE+METADATA ')) and not query.startswith('CHANNEL '):
                    raise ValueError('Query does not start with SIMPLE or SIMPLE+METADATA or CHANNEL')
                from ACEStream.Core.SocialNetwork.RemoteQueryMsgHandler import RemoteQueryMsgHandler
                rqmh = RemoteQueryMsgHandler.getInstance()
                rqmh.send_query_to_peers(query, peers, usercallback)
            else:
                raise OperationNotEnabledByConfigurationException('Overlay not enabled')
        finally:
            self.sesslock.release()

    def download_torrentfile_from_peer(self, permid, infohash, usercallback, prio = 0):
        self.sesslock.acquire()
        try:
            if self.sessconfig['overlay']:
                from ACEStream.Core.SocialNetwork.RemoteTorrentHandler import RemoteTorrentHandler
                rtorrent_handler = RemoteTorrentHandler.getInstance()
                rtorrent_handler.download_torrent(permid, infohash, usercallback, prio)
            else:
                raise OperationNotEnabledByConfigurationException('Overlay not enabled')
        finally:
            self.sesslock.release()

    def checkpoint_shutdown(self, stop, checkpoint, gracetime, hacksessconfcheckpoint):
        self.sesslock.acquire()
        try:
            if hacksessconfcheckpoint:
                try:
                    self.save_pstate_sessconfig()
                except Exception as e:
                    self.lm.rawserver_nonfatalerrorfunc(e)

            if DEBUG:
                print >> sys.stderr, 'Session: checkpoint_shutdown'
            self.lm.checkpoint(stop=stop, checkpoint=checkpoint, gracetime=gracetime)
        finally:
            self.sesslock.release()

    def save_pstate_sessconfig(self):
        sscfg = self.get_current_startup_config_copy()
        cfgfilename = Session.get_default_config_filename(sscfg.get_state_dir())
        sscfg.save(cfgfilename)

    def get_default_config_filename(state_dir):
        return os.path.join(state_dir, STATEDIR_SESSCONFIG)

    get_default_config_filename = staticmethod(get_default_config_filename)

    def get_internal_tracker_torrentfilename(self, infohash):
        trackerdir = self.get_internal_tracker_dir()
        basename = binascii.hexlify(infohash) + '.torrent'
        return os.path.join(trackerdir, basename)

    def get_nat_type(self, callback = None):
        self.sesslock.acquire()
        try:
            return ConnectionCheck.getInstance(self).get_nat_type(callback=callback)
        finally:
            self.sesslock.release()

    def send_friendship_message(self, permid, mtype, approved = None):
        self.sesslock.acquire()
        try:
            if self.sessconfig['overlay']:
                if mtype == F_FORWARD_MSG:
                    raise ValueError('User cannot send FORWARD messages directly')
                from ACEStream.Core.SocialNetwork.FriendshipMsgHandler import FriendshipMsgHandler
                fmh = FriendshipMsgHandler.getInstance()
                params = {}
                if approved is not None:
                    params['response'] = int(approved)
                fmh.anythread_send_friendship_msg(permid, mtype, params)
            else:
                raise OperationNotEnabledByConfigurationException('Overlay not enabled')
        finally:
            self.sesslock.release()

    def set_friendship_callback(self, usercallback):
        self.sesslock.acquire()
        try:
            if self.sessconfig['overlay']:
                from ACEStream.Core.SocialNetwork.FriendshipMsgHandler import FriendshipMsgHandler
                fmh = FriendshipMsgHandler.getInstance()
                fmh.register_usercallback(usercallback)
            else:
                raise OperationNotEnabledByConfigurationException('Overlay not enabled')
        finally:
            self.sesslock.release()

    def get_subtitles_support_facade(self):
        try:
            return self.lm.overlay_apps.subtitle_support
        except:
            return None

    def get_active_services(self):
        my_services = 0
        proxy_status = self.sessconfig['proxyservice_status']
        if proxy_status == PROXYSERVICE_ON:
            proxy = 2
        else:
            proxy = 0
        my_services = my_services | proxy
        return my_services
