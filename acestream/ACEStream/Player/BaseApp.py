#Embedded file name: ACEStream\Player\BaseApp.pyo
import os
import sys
import time
import shutil
import urllib
import hashlib
import binascii
import random
import subprocess
import struct
import pickle
import cookielib
from operator import itemgetter
from base64 import b64encode, encodestring
from types import DictType, StringType
if sys.platform == 'win32':
    import win32file
    import win32api
    from ACEStream.Core.Utilities.win32regchecker import Win32RegChecker, HKLM, HKCU
from threading import enumerate, currentThread, Lock, Timer
from traceback import print_stack, print_exc
from ACEStream.Video.utils import svcextdefaults
from ACEStream.Core.Utilities.odict import odict
from ACEStream.Core.Utilities.timeouturlopen import urlOpenTimeout
if sys.platform == 'darwin':
    os.chdir(os.path.abspath(os.path.dirname(sys.argv[0])))
from ACEStream.__init__ import DEFAULT_SESSION_LISTENPORT
from ACEStream.version import VERSION, VERSION_REV
from ACEStream.env import TS_ENV_PLATFORM
from ACEStream.GlobalConfig import globalConfig
from ACEStream.Core.API import *
from ACEStream.Policies.RateManager import UserDefinedMaxAlwaysOtherwiseEquallyDividedRateManager
from ACEStream.Utilities.Instance2Instance import *
from ACEStream.Utilities.TimedTaskQueue import TimedTaskQueue
from ACEStream.Core.BitTornado.__init__ import createPeerID
from ACEStream.Video.utils import videoextdefaults
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.Utilities.unicode import unicode2str_safe
#from ACEStream.Core.Ads.Manager import AdManager
from ACEStream.Core.TS.Service import TSService
from ACEStream.Core.Utilities.mp4metadata import clear_mp4_metadata_tags_from_file
#from ACEStream.Core.Statistics.GoogleAnalytics import GoogleAnalytics
#from ACEStream.Core.Statistics.TNS import TNS, TNSNotAllowedException
#from ACEStream.Core.Statistics.Settings import RemoteStatisticsSettings
#from ACEStream.Core.Statistics.TrafficStatistics import TrafficStatistics
from ACEStream.Core.APIImplementation.FakeDownload import FakeDownload
from ACEStream.Utilities.HardwareIdentity import get_hardware_key
from ACEStream.Utilities.LSO import LSO
if sys.platform == 'win32':
    TNS_ENABLED = True
else:
    TNS_ENABLED = False
DEVELOPER_MODE = False
DEBUG = False
DEBUG_AD_STORAGE = False
DEBUG_HIDDEN_DOWNLOADS = False
DEBUG_SERVICE_REQUESTS = False
DEBUG_STATS_TO_FILE = False
DEBUG_PREMIUM = False
RATELIMITADSL = True
DOWNLOADSPEED = 600
DEFAULT_DISKSPACE_LIMIT = 10737418240L
DEFAULT_DOWNLOAD_RATE_LIMIT = 100000000000.0
DOWNLOAD_STATES_DISPLAY_INTERVAL = 600
SHOW_HIDDEN_DOWNLOADS_INFO = False
MIN_PROGRESS_KEEP = 0.001
DOWNLOAD_STATS_INTERVAL = 1800
PREMIUM_PREVIEW_TIMEOUT = 15
CHECK_AUTH_INTERVAL_REGULAR = 3600
CHECK_AUTH_INTERVAL_ERROR = 600
CHECK_AUTH_INTERVAL_PREMIUM = 60
CHECK_AUTH_MAX_ERRORS = 5
CHECK_PRELOAD_ADS_INTERVAL = 86400
CLEANUP_HIDDEN_DOWNLOADS_INTERVAL = 86400
DEFAULT_PLAYER_BUFFER_TIME = 2
DEFAULT_LIVE_BUFFER_TIME = 10
CACHE_DIR_NAME = '_acestream_cache_'
DEFAULT_AD_STORAGE_LIMIT = 536870912L
AD_STORAGE_LIMIT_SMALL = 536870912L
AD_STORAGE_LIMIT_BIG = 1073741824L
AD_STORAGE_MIN_FREE_SPACE = 52428800L
AD_STORAGE_MAX_AGE = 2592000

class BaseApp(InstanceConnectionHandler):

    def __init__(self, wrapper, redirectstderrout, appname, appversion, params, installdir, i2i_port, session_port):
        self.apptype = globalConfig.get_value('apptype')
        self.ext_version = self.check_integrity()
        if DEVELOPER_MODE:
            self.ext_version = True
        debug_level = 0
        skip_metadata = False
        skip_mediainfo = False
        use_libavi = False
        if self.apptype == 'torrentstream':
            encrypted_storage = False
            self.registry_key = 'TorrentStream'
        else:
            encrypted_storage = False
            self.registry_key = 'ACEStream'
        ip = None
        vod_live_max_pop_time = None
        piece_picker_buffering_delay = None
        try:
            for param in params:
                if param.startswith('--debug='):
                    _, level = param.split('=')
                    debug_level = int(level)
                elif param == '--skip-metadata':
                    skip_metadata = True
                elif param == '--skip-mediainfo':
                    skip_mediainfo = True
                elif param == '--use-libavi':
                    use_libavi = True
                elif param.startswith('--vod-live-max-pop-time='):
                    _, vod_live_max_pop_time = param.split('=')
                elif param.startswith('--buffering-delay='):
                    _, piece_picker_buffering_delay = param.split('=')

        except:
            print_exc()

        self.debug_systray = False
        self.debug_level = 0
        self.ip = ip
        globalConfig.set_value('encrypted_storage', encrypted_storage)
        globalConfig.set_value('use_libavi', use_libavi)
        if vod_live_max_pop_time is not None:
            try:
                vod_live_max_pop_time = int(vod_live_max_pop_time)
                if vod_live_max_pop_time < 1:
                    vod_live_max_pop_time = 1
                globalConfig.set_value('vod_live_max_pop_time', vod_live_max_pop_time)
            except:
                pass

        if piece_picker_buffering_delay is not None:
            try:
                a = piece_picker_buffering_delay.split(',')
                if len(a) >= 2:
                    _min = int(a[0])
                    _max = int(a[1])
                    if len(a) >= 3:
                        _offset = int(a[2])
                    else:
                        _offset = 0
                    piece_picker_buffering_delay = (_min, _max, _offset)
                    if DEBUG:
                        log('baseapp::__init__: piece_picker_buffering_delay', piece_picker_buffering_delay)
                    globalConfig.set_value('piece_picker_buffering_delay', piece_picker_buffering_delay)
            except:
                pass

        self.set_debug_level(debug_level)
        ACEStream.Core.Video.VideoOnDemand.DEBUG_SKIP_METADATA = skip_metadata
        ACEStream.Core.Video.VideoStatus.DEBUG_SKIP_METADATA = skip_metadata
        ACEStream.Core.Video.VideoOnDemand.DO_MEDIAINFO_ANALYSIS = not skip_mediainfo
        if DEBUG_STATS_TO_FILE:
            self.debug_counter = 0
        self.appname = appname
        self.appversion = appversion
        self.params = params
        self.installdir = installdir
        self.i2i_port = i2i_port
        self.session_port = session_port
        self.error = None
        self.s = None
        self.wrapper = wrapper
        self.auth_data = {'last_success': None,
         'errors': 0}
        self.playerconfig = {}
        self.download_states_display_counter = 0
        self.user_profile = None
        self.downloads_in_vodmode = {}
        self.downloads_in_admode = {}
        self.dlinfo_lock = Lock()
        self.cleanup_hidden_downloads_lock = Lock()
        self.check_preload_ads_lock = Lock()
        self.timers = {}
        self.playing_premium_content = False
        self.download_stats = {}
        self.last_download_stats = 0
        self.max_download_rate = 0
        self.max_upload_rate = 0
        self.avg_download_rate = 0
        self.avg_download_rate_sum = 0
        self.avg_download_rate_count = 0
        self.avg_upload_rate = 0
        self.avg_upload_rate_sum = 0
        self.avg_upload_rate_count = 0
        self.ratelimiter = None
        self.ratelimit_update_count = 0
        self.playermode = DLSTATUS_DOWNLOADING
        self.getpeerlistcount = 2
        self.shuttingdown = False
        self.tqueue = TimedTaskQueue(nameprefix='BGTaskQueue')
        self.OnInitBase()
        if self.i2i_port == 0:
            port_file = os.path.join(self.installdir, 'acestream.port')
        else:
            port_file = None
        self.i2i_listen_server = Instance2InstanceServer(self.i2i_port, self, timeout=86400.0, port_file=port_file)
        self.i2i_listen_server.start()
        InstanceConnectionHandler.__init__(self, self.i2ithread_readlinecallback)
        self.check_license()

    def check_license(self):
        try:
            path = os.path.join(self.installdir, '..', 'LICENSE.txt')
            if not os.path.isfile(path):
                return
            size = os.path.getsize(path)
            if size < 1024:
                return
            import locale
            lang_code, encoding = locale.getdefaultlocale()
            lang_code = lang_code.lower()
            if lang_code.startswith('en'):
                lang_code = 'en'
            elif lang_code.startswith('ru'):
                lang_code = 'ru'
            else:
                lang_code = 'en'
            if lang_code == 'ru':
                txt = '\xd0\x9b\xd0\xb8\xd1\x86\xd0\xb5\xd0\xbd\xd0\xb7\xd0\xb8\xd0\xbe\xd0\xbd\xd0\xbd\xd0\xbe\xd0\xb5 \xd1\x81\xd0\xbe\xd0\xb3\xd0\xbb\xd0\xb0\xd1\x88\xd0\xb5\xd0\xbd\xd0\xb8\xd0\xb5 \xd0\xbf\xd1\x80\xd0\xb5\xd0\xb4\xd1\x81\xd1\x82\xd0\xb0\xd0\xb2\xd0\xbb\xd0\xb5\xd0\xbd\xd0\xbe \xd0\xbd\xd0\xb0 \xd1\x81\xd0\xb0\xd0\xb9\xd1\x82\xd0\xb5: http://www.acestream.org/license'
            else:
                txt = 'License agreement presented on the site: http://www.acestream.org/license'
            f = open(path, 'w')
            f.write(txt)
            f.close()
        except:
            pass

    def test_ads(self):
        affiliate_id = 0
        zone_id = 0
        developer_id = 0
        include_interruptable_ads = False
        provider_key = None
        provider_content_id = None
        content_ext = 'mp4'
        content_duration = 3600
        user_login = self.s.get_ts_login()
        content_id = '1234567890123456789012345678901234567890'
        ads = self.ad_manager.get_ads(device_id=self.device_id, user_login=user_login, user_level=2, content_type=DLTYPE_TORRENT, content_id=content_id, content_ext=content_ext, content_duration=content_duration, affiliate_id=affiliate_id, zone_id=zone_id, developer_id=developer_id, include_interruptable_ads=include_interruptable_ads, is_live=False, user_profile=self.user_profile, provider_key=provider_key, provider_content_id=provider_content_id)
        print >> sys.stderr, '>>>test_ads:', ads

    def set_debug_level(self, debug_level):
        if not DEVELOPER_MODE:
            return
        if debug_level == self.debug_level:
            return
        self.debug_level = debug_level
        log('set_debug_level:', debug_level)
        ACEStream.Plugin.BackgroundProcess.DEBUG2 = debug_level == -1 or debug_level & 1 != 0
        ACEStream.Player.BaseApp.DEBUG = debug_level == -1 or debug_level & 1 != 0
        ACEStream.Core.Session.DEBUG = debug_level == -1 or debug_level & 1 != 0
        ACEStream.Player.BaseApp.DEBUG_HIDDEN_DOWNLOADS = debug_level == -1 or debug_level & 1 != 0
        ACEStream.Player.BaseApp.DEBUG_AD_STORAGE = debug_level == -1 or debug_level & 1 != 0
        ACEStream.Player.BaseApp.DEBUG_SERVICE_REQUESTS = debug_level == -1 or debug_level & 1 != 0
        ACEStream.Player.BaseApp.DEBUG_PREMIUM = debug_level == -1 or debug_level & 1 != 0
        ACEStream.Player.BaseApp.SHOW_HIDDEN_DOWNLOADS_INFO = debug_level == -1 or debug_level & 1 != 0
        ACEStream.Core.Ads.Manager.DEBUG = debug_level == -1 or debug_level & 1 != 0
        ACEStream.Core.TS.Service.DEBUG = debug_level == -1 or debug_level & 1 != 0
        ACEStream.Core.APIImplementation.DirectDownload.DEBUG = debug_level == -1 or debug_level & 2 != 0
        ACEStream.Core.APIImplementation.DownloadImpl.DEBUG = debug_level == -1 or debug_level & 2 != 0
        ACEStream.Core.APIImplementation.LaunchManyCore.DEBUG = debug_level == -1 or debug_level & 2 != 0
        ACEStream.Core.APIImplementation.SingleDownload.DEBUG = debug_level == -1 or debug_level & 2 != 0
        ACEStream.Core.BitTornado.download_bt1.DEBUG = debug_level == -1 or debug_level & 2 != 0
        ACEStream.Core.BitTornado.BT1.GetRightHTTPDownloader.DEBUG = debug_level == -1 or debug_level & 2 != 0
        ACEStream.Core.DirectDownload.Downloader.DEBUG = debug_level == -1 or debug_level & 2 != 0
        ACEStream.Core.DirectDownload.Storage.DEBUG = debug_level == -1 or debug_level & 2 != 0
        ACEStream.Core.DirectDownload.VODTransporter.DEBUG = debug_level == -1 or debug_level & 2 != 0
        ACEStream.Core.Statistics.GoogleAnalytics.DEBUG = debug_level == -1 or debug_level & 2 != 0
        ACEStream.Core.TorrentDef.DEBUG = False
        ACEStream.Core.TS.domutils.DEBUG = False
        ACEStream.Core.Utilities.mp4metadata.DEBUG = debug_level == -1 or debug_level & 2 != 0
        ACEStream.Video.VideoServer.DEBUGLOCK = debug_level == -1 or debug_level & 2 != 0
        ACEStream.Core.Video.PiecePickerStreaming.DEBUG = debug_level == -1 or debug_level & 4 != 0
        ACEStream.Core.Video.PiecePickerStreaming.DEBUGPP = debug_level == -1 or debug_level & 4 != 0
        ACEStream.Core.BitTornado.SocketHandler.DEBUG = debug_level == -1 or debug_level & 8 != 0
        ACEStream.Core.BitTornado.BT1.Choker.DEBUG = debug_level == -1 or debug_level & 8 != 0
        ACEStream.Core.BitTornado.BT1.Connecter.DEBUG = debug_level == -1 or debug_level & 8 != 0
        ACEStream.Core.BitTornado.BT1.Connecter.DEBUG_UT_PEX = debug_level == -1 or debug_level & 8 != 0
        ACEStream.Core.BitTornado.BT1.Downloader.DEBUG = debug_level == -1 or debug_level & 8 != 0
        ACEStream.Core.BitTornado.BT1.Uploader.DEBUG = debug_level == -1 or debug_level & 8 != 0
        ACEStream.Core.BitTornado.BT1.Encrypter.DEBUG = debug_level == -1 or debug_level & 8 != 0
        ACEStream.Core.BitTornado.BT1.Encrypter.DEBUG_CLOSE = debug_level == -1 or debug_level & 8 != 0
        ACEStream.Core.BitTornado.BT1.Rerequester.DEBUG = debug_level == -1 or debug_level & 8 != 0
        ACEStream.Core.BitTornado.BT1.Rerequester.DEBUG_DHT = debug_level == -1 or debug_level & 8 != 0
        ACEStream.Core.BitTornado.BT1.Rerequester.DEBUG_CHECK_NETWORK_CONNECTION = debug_level == -1 or debug_level & 8 != 0
        ACEStream.Core.Video.VideoOnDemand.DEBUG_HOOKIN = debug_level == -1 or debug_level & 16 != 0
        ACEStream.Core.Video.LiveSourceAuth.DEBUG = debug_level == -1 or debug_level & 16 != 0
        ACEStream.Core.Video.PiecePickerStreaming.DEBUG_LIVE = debug_level == -1 or debug_level & 16 != 0
        ACEStream.Core.BitTornado.BT1.StorageWrapper.DEBUG_LIVE = debug_level == -1 or debug_level & 16 != 0
        try:
            ACEStream.Core.Video.VideoSource.DEBUG = debug_level == -1 or debug_level & 16 != 0
        except:
            pass

        ACEStream.Core.Video.VideoOnDemand.DEBUG = debug_level == -1 or debug_level & 32 != 0
        ACEStream.Core.Video.VideoStatus.DEBUG = debug_level == -1 or debug_level & 32 != 0
        ACEStream.Video.VideoServer.DEBUG = debug_level == -1 or debug_level & 32 != 0
        ACEStream.Video.VideoServer.DEBUGCONTENT = debug_level == -1 or debug_level & 32 != 0
        ACEStream.Core.NATFirewall.NatCheck.DEBUG = debug_level == -1 or debug_level & 64 != 0
        ACEStream.Core.NATFirewall.UPnPThread.DEBUG = debug_level == -1 or debug_level & 64 != 0
        ACEStream.Core.NATFirewall.UDPPuncture.DEBUG = debug_level == -1 or debug_level & 64 != 0
        ACEStream.Core.NATFirewall.upnp.DEBUG = debug_level == -1 or debug_level & 64 != 0
        ACEStream.Core.NATFirewall.ConnectionCheck.DEBUG = debug_level == -1 or debug_level & 64 != 0
        ACEStream.Core.BitTornado.natpunch.DEBUG = debug_level == -1 or debug_level & 64 != 0
        ACEStream.Player.BaseApp.DEBUG_STATS_TO_FILE = debug_level == -1 or debug_level & 128 != 0
        ACEStream.WebUI.WebUI.DEBUG = debug_level == -1 or debug_level & 256 != 0
        ACEStream.Core.BitTornado.RawServer.DEBUG = debug_level == -1 or debug_level & 512 != 0
        ACEStream.Core.BitTornado.RawServer.DEBUG2 = debug_level == -1 or debug_level & 512 != 0
        ACEStream.Core.BitTornado.ServerPortHandler.DEBUG = debug_level == -1 or debug_level & 512 != 0
        ACEStream.Core.BitTornado.ServerPortHandler.DEBUG2 = debug_level == -1 or debug_level & 512 != 0
        ACEStream.Core.BitTornado.HTTPHandler.DEBUG = debug_level == -1 or debug_level & 512 != 0
        ACEStream.Core.BitTornado.HTTPHandler.DEBUG2 = debug_level == -1 or debug_level & 512 != 0
        ACEStream.Core.BitTornado.SocketHandler.DEBUG = debug_level == -1 or debug_level & 512 != 0
        ACEStream.Core.BitTornado.SocketHandler.DEBUG2 = debug_level == -1 or debug_level & 512 != 0
        ACEStream.Core.BitTornado.BT1.StorageWrapper.DEBUG = debug_level == -1 or debug_level & 8192 != 0
        ACEStream.Core.BitTornado.BT1.StorageWrapper.DEBUG_WRITE = False
        ACEStream.Core.BitTornado.BT1.StorageWrapper.DEBUG_HASHCHECK = debug_level == -1 or debug_level & 8192 != 0
        ACEStream.Core.BitTornado.BT1.StorageWrapper.DEBUG_REQUESTS = debug_level == -1 or debug_level & 8192 != 0
        ACEStream.Core.BitTornado.BT1.FileSelector.DEBUG = debug_level == -1 or debug_level & 8192 != 0
        ACEStream.Core.BitTornado.download_bt1.DEBUG_ENCRYPTION = debug_level == -1 or debug_level & 8192 != 0
        ACEStream.Core.BitTornado.BT1.Storage.DEBUG = debug_level == -1 or debug_level & 16384 != 0
        ACEStream.Core.BitTornado.BT1.Storage.DEBUG_RESTORE = debug_level == -1 or debug_level & 16384 != 0
        ACEStream.Core.Utilities.EncryptedStorage.DEBUG = debug_level == -1 or debug_level & 32768 != 0
        ACEStream.Core.BitTornado.BT1.StorageWrapper.DEBUG_ENCRYPTED_STORAGE = debug_level == -1 or debug_level & 32768 != 0
        ACEStream.Core.BitTornado.download_bt1.DEBUG_ENCRYPTION = debug_level == -1 or debug_level & 32768 != 0
        ACEStream.Core.CacheDB.SqliteCacheDBHandler.DEBUG = debug_level == -1 or debug_level & 65536 != 0
        ACEStream.Utilities.LSO.DEBUG = debug_level == -1 or debug_level & 131072 != 0
        ACEStream.Core.Statistics.Settings.DEBUG = debug_level == -1 or debug_level & 131072 != 0
        ACEStream.Core.Statistics.TNS.DEBUG = debug_level == -1 or debug_level & 131072 != 0
        ACEStream.Core.Statistics.TrafficStatistics.DEBUG = debug_level == -1 or debug_level & 131072 != 0

    def OnInitBase(self):
        state_dir = Session.get_default_state_dir()
        self.state_dir = state_dir
        if DEBUG:
            log('baseapp::init: state_dir', state_dir)
        if globalConfig.get_mode() != 'client_console':
            from ACEStream.Player.UtilityStub import UtilityStub
            self.utility = UtilityStub(self.installdir, state_dir)
            self.utility.app = self
        log('build', VERSION_REV)
        log('version', VERSION)
        self.iconpath = os.path.join(self.installdir, 'data', 'images', 'engine.ico')
        self.logopath = os.path.join(self.installdir, 'data', 'images', 'logo.png')
        self.load_playerconfig(state_dir)
        self.statFrame = None
        self.live_frame = None
        self.init_hardware_key()
        cfgfilename = Session.get_default_config_filename(state_dir)
        if DEBUG:
            log('baseapp::init: session config', cfgfilename)
        try:
            self.sconfig = SessionStartupConfig.load(cfgfilename)
            if self.session_port != DEFAULT_SESSION_LISTENPORT:
                if DEBUG:
                    log('baseapp::init: non-default port specified, overwrite saved session port:', self.session_port)
                self.sconfig.set_listen_port(self.session_port)
            elif DEBUG:
                log('baseapp::init: use session saved port', self.sconfig.get_listen_port())
        except:
            if DEBUG:
                log('baseapp::init: cannot load config file', cfgfilename, 'Use default config')
            self.sconfig = SessionStartupConfig()
            self.sconfig.set_state_dir(state_dir)
            self.sconfig.set_listen_port(self.session_port)

        self.configure_session()
        self.s = Session(self.sconfig, on_error=self.on_error)
        self.s.set_download_states_callback(self.sesscb_states_callback)
        self.device_id = b64encode(self.s.get_permid())
        node_id = self.device_id
        if self.hardware_key is not None:
            node_id += ':' + self.hardware_key
        self.node_id = hashlib.sha1(node_id).hexdigest()
        #self.traffic_stats = TrafficStatistics(TrafficStatistics.NODE_CLIENT, self.node_id)
        if RATELIMITADSL:
            self.ratelimiter = UserDefinedMaxAlwaysOtherwiseEquallyDividedRateManager()
            self.ratelimiter.set_global_max_speed(DOWNLOAD, DOWNLOADSPEED)
            self.ratelimiter.set_global_max_speed(UPLOAD, 90)
        try:
            self.s.load_checkpoint(initialdlstatus=DLSTATUS_STOPPED)
        except:
            log_exc()

        #ga = lambda : GoogleAnalytics.send_event('client', 'startup', VERSION)
        #self.run_delayed(ga)
        self.tsservice = TSService(self)
        #self.run_delayed(self.check_auth_level, 0.1)
        self.cookie_file = os.path.join(self.state_dir, 'cookies.pickle')
        self.cookie_jar = cookielib.CookieJar()
        self.load_cookies()
        #self.stat_settings = RemoteStatisticsSettings()
        #self.run_delayed(self.check_statistics_settings, 1)
        if TNS_ENABLED:
            try:
                lso = LSO('source.mmi.bemobile.ua', 'mmi')
                self.tns_uid = lso.get_uid()
            except:
                if DEBUG:
                    print_exc()

        #self.check_user_profile()
        #self.ad_manager = AdManager(self, self.cookie_jar)
        if TS_ENV_PLATFORM == 'dune':
            default_enabled = False
        else:
            default_enabled = True
        #preload_ads_enabled = self.get_preload_ads_enabled(default_enabled)
        #if DEBUG:
            #log('baseapp::init: preload_ads_enabled', preload_ads_enabled)
        #self.run_delayed(self.cleanup_hidden_downloads_task, 1.0)
        self.run_delayed(self.remove_unknown_downloads, 20.0)
        #self.run_delayed(self.check_preload_ads, 1.0, 'check_preload_ads')
        if sys.platform == 'win32':
            self.run_delayed(self.start_updater, 60.0)
        disk_cache_limit = self.get_playerconfig('disk_cache_limit')
        if disk_cache_limit is None:
            content_dir = self.get_default_destdir()
            total, avail, used = self.get_disk_info(content_dir)
            if total is not None:
                disk_cache_limit = long(total * 0.5)
            else:
                disk_cache_limit = DEFAULT_DISKSPACE_LIMIT
            self.set_playerconfig('disk_cache_limit', disk_cache_limit)
            if DEBUG:
                log('baseapp::init: set disk_cache_limit:', disk_cache_limit)
        elif DEBUG:
            log('baseapp::init: got disk_cache_limit:', disk_cache_limit)
        ad_storage_limit = self.get_playerconfig('ad_storage_limit')
        if ad_storage_limit is None:
            ads_dir = self.s.get_ads_dir()
            total, avail, used = self.get_disk_info(ads_dir)
            if total is not None:
                if avail < 10485760:
                    ad_storage_limit = AD_STORAGE_LIMIT_SMALL
                else:
                    ad_storage_limit = AD_STORAGE_LIMIT_BIG
            else:
                ad_storage_limit = DEFAULT_AD_STORAGE_LIMIT
            self.set_playerconfig('ad_storage_limit', ad_storage_limit)
            if DEBUG:
                log('baseapp::init: set ad_storage_limit:', ad_storage_limit)
        elif DEBUG:
            log('baseapp::init: got ad_storage_limit:', ad_storage_limit)
        self.set_playerconfig('enable_http_support', True)
        if DEBUG_STATS_TO_FILE:
            try:
                for f in os.listdir(self.installdir):
                    if f.startswith('stat_snapshot_'):
                        os.remove(os.path.join(self.installdir, f))

            except:
                pass

    def on_error(self, exception):
        try:
            errmsg = str(exception)
        except:
            errmsg = 'Unexpected error'

        try:
            self.wrapper.on_error(errmsg, exit=True)
        except:
            print_exc()

    def run_delayed(self, func, delay = 0.0, task_id = None, daemon = True, args = []):
        if task_id is not None:
            if self.timers.has_key(task_id):
                self.timers[task_id].cancel()
        t = Timer(delay, func, args)
        if task_id is not None:
            self.timers[task_id] = t
        t.daemon = daemon
        t.name = 'Timer-' + t.name
        t.start()
        return t

    def start_updater(self):
        if sys.platform != 'win32':
            return
        if self.apptype == 'torrentstream':
            exename = 'tsupdate.exe'
        else:
            exename = 'ace_update.exe'
        updater_path = os.path.join(self.installdir, '..', 'updater', exename)
        if DEBUG:
            log('baseapp::start_updater: updater_path', updater_path)
        if os.path.exists(updater_path):
            try:
                subprocess.Popen(updater_path, close_fds=True)
            except:
                if DEBUG:
                    print_exc()

    def remove_unknown_downloads(self):
        try:
            known_files = []
            downloads = self.s.get_all_downloads()
            for d in downloads:
                if not d.is_hidden():
                    continue
                destfiles = d.get_dest_files(get_all=True)
                if destfiles:
                    for filename, savepath in destfiles:
                        known_files.append(savepath)

            path = self.s.get_ads_dir()
            filelist = os.listdir(path)
            if DEBUG_AD_STORAGE:
                log('baseapp::remove_unknown_downloads: known_files', known_files, 'filelist', filelist)
            for basename in filelist:
                filename = os.path.join(path, basename)
                if filename not in known_files:
                    if DEBUG_AD_STORAGE:
                        log('baseapp::remove_unknown_downloads: remove: filename', filename)
                    os.remove(filename)

        except:
            if DEBUG:
                print_exc()

    def get_ad_storage_limit(self):
        ad_storage_limit = self.get_playerconfig('ad_storage_limit', DEFAULT_AD_STORAGE_LIMIT)
        ads_dir = self.s.get_ads_dir()
        total, avail, used = self.get_disk_info(ads_dir)
        if avail is None:
            avail = ad_storage_limit + AD_STORAGE_MIN_FREE_SPACE
            if DEBUG_AD_STORAGE:
                log('baseapp::get_ad_storage_limit: failed to get disk info, set fake avail: avail', avail)
        if avail < ad_storage_limit + AD_STORAGE_MIN_FREE_SPACE:
            storage_limit = avail - AD_STORAGE_MIN_FREE_SPACE
        else:
            storage_limit = ad_storage_limit
        if DEBUG_AD_STORAGE:
            log('baseapp::get_ad_storage_limit: storage_limit', storage_limit, 'total', total, 'avail', avail, 'used', used)
        return storage_limit

    def cleanup_unused_ad_downloads(self, keep_hash_list):
        if DEBUG_AD_STORAGE:
            log('baseapp::cleanup_unused_ad_downloads: keep_hash_list', keep_hash_list)
        downloads = self.s.get_all_downloads()
        for d in downloads:
            if not d.is_hidden():
                continue
            if d.get_hash() not in keep_hash_list:
                if DEBUG_AD_STORAGE:
                    log('baseapp::cleanup_unused_ad_downloads: remove unused download: hash', binascii.hexlify(d.get_hash()))
                self.s.remove_download(d, removecontent=True)

    def cleanup_hidden_downloads_task(self):
        self.cleanup_hidden_downloads()
        self.run_delayed(self.cleanup_hidden_downloads_task, CLEANUP_HIDDEN_DOWNLOADS_INTERVAL)

    def cleanup_hidden_downloads(self, needed = 0, priority = -1):
        self.cleanup_hidden_downloads_lock.acquire()
        try:
            total_size = 0
            dllist = []
            downloads = self.s.get_all_downloads()
            for d in downloads:
                if not d.is_hidden():
                    continue
                destfiles = d.get_dest_files(get_all=True)
                download_priority = d.get_extra('priority', 0)
                download_size = d.get_content_length()
                download_last_access = 0
                for filename, savepath in destfiles:
                    if os.path.exists(savepath):
                        stat = os.stat(savepath)
                        if stat.st_ctime > download_last_access:
                            download_last_access = stat.st_ctime

                last_seen = self.get_ad_last_seen(d.get_hash())
                if last_seen is not None:
                    download_last_access = last_seen
                if download_size > 0:
                    total_size += download_size
                    dlinfo = (download_last_access,
                     download_priority,
                     download_size,
                     d)
                    dllist.append(dlinfo)

            dllist.sort(key=itemgetter(1, 0))
            storage_limit = self.get_ad_storage_limit()
            free_up = total_size + needed - storage_limit
            if DEBUG_AD_STORAGE:
                log('baseapp::cleanup_hidden_downloads: storage_limit', storage_limit, 'total_size', total_size, 'needed', needed, 'free_up', free_up, 'dllist', dllist)
            for last_access, dlpriority, size, d in dllist:
                remove = False
                if priority != -1 and dlpriority >= priority:
                    if DEBUG_AD_STORAGE:
                        log('baseapp::cleanup_hidden_downloads: do not remove download with higher priority: hash', binascii.hexlify(d.get_hash()), 'dlpriority', dlpriority, 'priority', priority)
                    continue
                if d in self.downloads_in_vodmode:
                    if DEBUG_AD_STORAGE:
                        log('baseapp::cleanup_hidden_downloads: do not remove playing download: hash', binascii.hexlify(d.get_hash()))
                    continue
                is_ad = False
                for maind_d, ads in self.downloads_in_admode.iteritems():
                    if d in ads:
                        is_ad = True
                        break

                if is_ad:
                    if DEBUG_AD_STORAGE:
                        log('baseapp::cleanup_hidden_downloads: do not remove download in admode: hash', binascii.hexlify(d.get_hash()))
                    continue
                now = long(time.time())
                if last_access < now - AD_STORAGE_MAX_AGE:
                    if DEBUG_AD_STORAGE:
                        log('baseapp::cleanup_hidden_downloads: remove outdated download: hash', binascii.hexlify(d.get_hash()), 'last_access', last_access, 'now', now, 'max_age', AD_STORAGE_MAX_AGE)
                    remove = True
                if not remove and free_up > 0:
                    remove = True
                    free_up -= size
                    if DEBUG_AD_STORAGE:
                        log('baseapp::cleanup_hidden_downloads: remove download to free space: hash', binascii.hexlify(d.get_hash()), 'size', size, 'free_up', free_up)
                if remove:
                    self.s.remove_download(d, removecontent=True)

            if DEBUG_AD_STORAGE:
                log('baseapp::cleanup_hidden_downloads: done: free_up', free_up)
            return free_up <= 0
        except:
            log_exc()
        finally:
            self.cleanup_hidden_downloads_lock.release()

    def check_auth_level(self, forceconnect = False):
        got_error = False
        try:
            ts_login = unicode2str_safe(self.s.get_ts_login())
            ts_password = unicode2str_safe(self.s.get_ts_password())
            if len(ts_login) == 0 or len(ts_password) == 0:
                self.s.set_authlevel(0)
                return
            if self.auth_data['last_success'] is None or forceconnect:
                action = 'cn'
            else:
                action = 'chk'
            new_authlevel = self.tsservice.get_user_level(ts_login, ts_password, action, self.device_id, self.hardware_key)
            if new_authlevel is not None:
                self.auth_data['last_success'] = time.time()
                self.auth_data['errors'] = 0
                if DEBUG:
                    log('baseapp::check_auth_level: got user level:', new_authlevel)
            else:
                got_error = True
                self.auth_data['errors'] += 1
                log('baseapp::check_auth_level: failed, error count', self.auth_data['errors'])
                if self.auth_data['errors'] >= CHECK_AUTH_MAX_ERRORS:
                    log('baseapp::check_auth_level: max errors reached, reset user level')
                    new_authlevel = 0
            if new_authlevel is not None:
                current_authlevel = self.s.get_authlevel()
                if new_authlevel != current_authlevel:
                    if DEBUG:
                        log('baseapp::check_auth_level: set new user level: current', current_authlevel, 'new', new_authlevel)
                    self.s.set_authlevel(new_authlevel)
                    for socket, ic in self.singsock2ic.iteritems():
                        ic.auth(new_authlevel)

        except:
            if DEBUG:
                log_exc()
        finally:
            if got_error:
                interval = CHECK_AUTH_INTERVAL_ERROR
                if DEBUG:
                    log('baseapp::check_auth_level: got error, next try in', interval)
            elif self.playing_premium_content:
                interval = CHECK_AUTH_INTERVAL_PREMIUM
                if DEBUG:
                    log('baseapp::check_auth_level: got premium, next try in', interval)
            else:
                interval = CHECK_AUTH_INTERVAL_REGULAR
                if DEBUG:
                    log('baseapp::check_auth_level: regular next try in', interval)
            self.run_delayed(self.check_auth_level, interval, task_id='check_auth_level')

    def configure_session(self):
        self.sconfig.set_install_dir(self.installdir)
        if self.ip is not None:
            if DEBUG:
                log('baseapp::configure_session: set ip', self.ip)
            self.sconfig.set_ip_for_tracker(self.ip)
        self.sconfig.set_megacache(True)
        self.sconfig.set_max_socket_connections(self.get_playerconfig('total_max_connects', 200))
        self.sconfig.set_overlay(False)
        self.sconfig.set_torrent_checking(False)
        self.sconfig.set_buddycast(False)
        self.sconfig.set_download_help(False)
        self.sconfig.set_torrent_collecting(False)
        self.sconfig.set_dialback(False)
        self.sconfig.set_social_networking(False)
        self.sconfig.set_remote_query(False)
        self.sconfig.set_bartercast(False)
        self.sconfig.set_crawler(False)
        self.sconfig.set_multicast_local_peer_discovery(False)
        self.sconfig.set_subtitles_collecting(False)

    def _get_poa(self, tdef):
        from ACEStream.Core.ClosedSwarm import ClosedSwarm, PaymentIntegration
        print >> sys.stderr, 'Swarm_id:', encodestring(tdef.infohash).replace('\n', '')
        try:
            poa = ClosedSwarm.trivial_get_poa(self.s.get_state_dir(), self.s.get_permid(), tdef.infohash)
            poa.verify()
            if not poa.torrent_id == tdef.infohash:
                raise Exception('Bad POA - wrong infohash')
            print >> sys.stderr, 'Loaded poa from ', self.s.get_state_dir()
        except:
            swarm_id = encodestring(tdef.infohash).replace('\n', '')
            my_id = encodestring(self.s.get_permid()).replace('\n', '')
            try:
                poa = PaymentIntegration.wx_get_poa(None, swarm_id, my_id, swarm_title=tdef.get_name())
            except Exception as e:
                print >> sys.stderr, 'Failed to get POA:', e
                poa = None

        try:
            ClosedSwarm.trivial_save_poa(self.s.get_state_dir(), self.s.get_permid(), tdef.infohash, poa)
        except Exception as e:
            print >> sys.stderr, 'Failed to save POA', e

        if poa:
            if not poa.torrent_id == tdef.infohash:
                raise Exception('Bad POA - wrong infohash')
        return poa

    def start_download(self, tdef, dlfile, extra_files_indexes = [], developer_id = 0, affiliate_id = 0, zone_id = 0, poa = None, supportedvodevents = None):
        if poa:
            from ACEStream.Core.ClosedSwarm import ClosedSwarm
            if not poa.__class__ == ClosedSwarm.POA:
                raise InvalidPOAException('Not a POA')
        destdir = self.get_default_destdir()
        try:
            enough_space = True
            length = tdef.get_length([dlfile])
            if tdef.get_live():
                length = long(length / 8 * 1.2)
            if not self.free_up_diskspace_by_downloads(tdef.get_infohash(), length):
                log('BaseApp::start_download: Not enough free diskspace')
                enough_space = False
        except:
            log_exc()

        if not enough_space:
            raise Exception('Not enough disk space')
        dcfg = DownloadStartupConfig()
        dcfg.set_max_conns(self.get_playerconfig('download_max_connects', 50))
        if poa:
            dcfg.set_poa(poa)
            print >> sys.stderr, 'POA:', dcfg.get_poa()
        else:
            dcfg.set_poa(None)
        if supportedvodevents is None:
            supportedvodevents = self.get_supported_vod_events()
        if DEBUG:
            log('BaseApp::start_download: supportedvodevents', supportedvodevents)
        dcfg.set_video_events(supportedvodevents)
        prefix, ext = os.path.splitext(dlfile)
        if ext != '' and ext[0] == '.':
            content_ext = ext[1:]
        else:
            content_ext = ''
        content_duration = None
        if tdef.is_multifile_torrent():
            svcdlfiles = self.is_svc(dlfile, tdef)
            if svcdlfiles is not None:
                dcfg.set_video_event_callback(self.sesscb_vod_event_callback, dlmode=DLMODE_SVC)
                dcfg.set_selected_files(svcdlfiles)
            else:
                dcfg.set_video_event_callback(self.sesscb_vod_event_callback)
                dcfg.set_selected_files([dlfile])
                dcfg.set_extra_files(extra_files_indexes)
                try:
                    p = [-1] * len(tdef.get_files())
                    total_duration = 0
                    content_length = 0
                    videofiles = tdef.get_files(exts=videoextdefaults)
                    for videofile in videofiles:
                        idx = tdef.get_index_of_file_in_files(videofile)
                        if videofile == dlfile or idx in extra_files_indexes:
                            p[idx] = 1
                            content_length += tdef.get_length(videofile)
                            duration = tdef.get_ts_duration(idx)
                            if duration is not None:
                                total_duration += duration

                    if total_duration > 0:
                        content_duration = total_duration
                    idx = tdef.get_index_of_file_in_files(dlfile)
                    if DEBUG:
                        log('BaseApp::start_download: bitrate', tdef.get_ts_bitrate(idx))
                    dcfg.set_files_priority(p)
                    if DEBUG:
                        log('BaseApp::start_download: got multi: dlfile', dlfile, 'priority', dcfg.get_files_priority, 'bitrate', tdef.get_ts_bitrate(idx), 'size', content_length, 'duration', content_duration, 'ext', content_ext)
                except:
                    log_exc()

        else:
            dcfg.set_video_event_callback(self.sesscb_vod_event_callback)
            content_duration = tdef.get_ts_duration()
            content_length = tdef.get_length()
            if DEBUG:
                log('BaseApp::start_download: got single: bitrate', tdef.get_ts_bitrate(), 'size', content_length, 'duration', content_duration, 'ext', content_ext)
        if content_duration is None:
            content_duration = self.guess_duration_from_size(content_length)
            if DEBUG:
                log('baseapp::start_download: guess duration: size', content_length, 'duration', content_duration)
        if tdef.get_live():
            include_interruptable_ads = False
        else:
            include_interruptable_ads = self.get_playerconfig('enable_interruptable_ads', True)
        newd_params = {}
        provider_key = tdef.get_provider()
        provider_content_id = tdef.get_content_id()
        premium = tdef.get_premium()
        if premium != 0 and provider_key is not None:
            if DEBUG_PREMIUM:
                log('baseapp::start_download: check premium status: provider_key', provider_key, 'content_id', provider_content_id)
            if self.check_premium_status(provider_key, provider_content_id, tdef.get_infohash()):
                newd_params['premium'] = True
                newd_params['report_interval'] = 60
                newd_params['user_check_interval'] = 60
                auth_level = self.s.get_authlevel()
                if DEBUG_PREMIUM:
                    log('baseapp::start_download: got premium content: provider_key', provider_key, 'content_id', provider_content_id, 'auth_level', auth_level)
                if auth_level < 2:
                    newd_params['user_check_interval'] = 15

        dcfg.set_dest_dir(destdir)
        rate = self.get_playerconfig('total_max_download_rate', DEFAULT_DOWNLOAD_RATE_LIMIT)
        if DEBUG:
            log('BaseApp::start_download: set download limit to', rate, 'Kb/s')
        dcfg.set_max_speed(DOWNLOAD, rate, self.get_playerconfig('auto_download_limit', False))
        dcfg.set_wait_sufficient_speed(self.get_playerconfig('wait_sufficient_speed', False))
        dcfg.set_http_support(self.get_playerconfig('enable_http_support', True))
        dcfg.set_player_buffer_time(self.get_playerconfig('player_buffer_time', DEFAULT_PLAYER_BUFFER_TIME))
        dcfg.set_live_buffer_time(self.get_playerconfig('live_buffer_time', DEFAULT_LIVE_BUFFER_TIME))
        infohash = tdef.get_infohash()
        newd = None
        for d in self.s.get_downloads():
            if d.get_def().get_infohash() == infohash:
                log('BaseApp::start_download: Reusing old duplicate download', infohash)
                newd = d
                if poa:
                    d.set_poa(poa)

        self.s.lm.h4xor_reset_init_conn_counter()
        initialdlstatus = None
        got_uninterruptable_ad = False


        if newd is None:
            log('BaseApp::start_download: starting new download: infohash', infohash, 'initialdlstatus', initialdlstatus)
            newd = self.s.start_download(tdef, dcfg, initialdlstatus)
        else:
            newd.set_video_events(self.get_supported_vod_events())
            newd.set_wait_sufficient_speed(dcfg.get_wait_sufficient_speed())
            newd.set_http_support(dcfg.get_http_support())
            newd.set_max_speed(UPLOAD, dcfg.get_max_speed(UPLOAD))
            newd.set_max_speed(DOWNLOAD, dcfg.get_max_speed(DOWNLOAD), dcfg.get_auto_download_limit())
            newd.set_max_conns(self.get_playerconfig('download_max_connects', 50))
            svcdlfiles = self.is_svc(dlfile, tdef)
            if svcdlfiles is not None:
                newd.set_video_event_callback(self.sesscb_vod_event_callback, dlmode=DLMODE_SVC)
                newd.set_selected_files(svcdlfiles)
            else:
                newd.set_video_event_callback(self.sesscb_vod_event_callback)
                newd.set_player_buffer_time(self.get_playerconfig('player_buffer_time', DEFAULT_PLAYER_BUFFER_TIME))
                newd.set_live_buffer_time(self.get_playerconfig('live_buffer_time', DEFAULT_LIVE_BUFFER_TIME))
                if tdef.is_multifile_torrent():
                    newd.set_selected_files([dlfile])
                    newd.set_extra_files(extra_files_indexes)
                    newd.set_files_priority(dcfg.get_files_priority())
            if initialdlstatus is None:
                if DEBUG:
                    log('BaseApp::start_download: restarting existing download: infohash', binascii.hexlify(infohash))
                newd.restart(new_tdef=tdef)
            else:
                ds = newd.network_get_state(usercallback=None, getpeerlist=False, sessioncalling=True)
                if ds.get_status != DLSTATUS_STOPPED:
                    if DEBUG:
                        log('BaseApp::start_download: existing download is active, stop it and wait for ads: infohash', binascii.hexlify(infohash))
                    newd.stop()
                elif DEBUG:
                    log('BaseApp::start_download: skip restarting existing download, wait for ads: infohash', binascii.hexlify(infohash))
        if DEBUG:
            log('BaseApp::start_download: saving content to', newd.get_dest_files())
        self.dlinfo_lock.acquire()
        try:
            if newd in self.downloads_in_vodmode:
                self.downloads_in_vodmode[newd].update(newd_params)
            else:
                newd_params['start'] = time.time()
                newd_params['download_id'] = hashlib.sha1(b64encode(self.s.get_ts_login()) + b64encode(tdef.get_infohash()) + str(time.time()) + str(random.randint(1, sys.maxint))).hexdigest()
                if TNS_ENABLED:
                    if self.stat_settings.check_content('tns', tdef):
                        try:
                            newd_params['tns'] = TNS(self.stat_settings.get_url_list('tns'), self.stat_settings.get_options('tns'), self.tns_uid, self.cookie_jar, tdef)
                            newd_params['tns'].start()
                        except TNSNotAllowedException:
                            pass
                        except:
                            if DEBUG:
                                print_exc()

                    elif DEBUG:
                        log('baseapp::start_download: tns disabled: infohash', binascii.hexlify(tdef.get_infohash()))
                self.downloads_in_vodmode[newd] = newd_params
            if newd in self.downloads_in_admode:
                if DEBUG:
                    log('baseapp::start_ad_downloads: remove old ad downloads on start')
                del self.downloads_in_admode[newd]

        finally:
            self.dlinfo_lock.release()

        #func = lambda : GoogleAnalytics.send_event('client', 'play', VERSION)
        #self.run_delayed(func)
        return newd

    def guess_duration_from_size(self, content_length):
        if content_length >= 734003200:
            content_duration = 5400
        elif content_length >= 314572800:
            content_duration = 2700
        elif content_length >= 104857600:
            content_duration = 900
        else:
            content_duration = 300
        return content_duration

    def start_ad_download_when_seeding(self, d, main_d):
        if DEBUG:
            log('baseapp::start_ad_download_when_seeding: main', binascii.hexlify(main_d.get_hash()), 'ad', binascii.hexlify(d.get_hash()))
        if main_d not in self.downloads_in_admode:
            if DEBUG:
                log('baseapp::start_ad_download_when_seeding: main download is not in admode, exit')
            return
        ds = d.network_get_state(usercallback=None, getpeerlist=False, sessioncalling=True)
        dlstatus = ds.get_status()
        if dlstatus != DLSTATUS_SEEDING:
            if DEBUG:
                log('baseapp::start_ad_download_when_seeding: not seeding, reschedule: dlstatus', dlstatus, 'main', binascii.hexlify(main_d.get_hash()), 'ad', binascii.hexlify(d.get_hash()))
            start_ad_download_when_seeding_lambda = lambda : self.start_ad_download_when_seeding(d, main_d)
            self.run_delayed(start_ad_download_when_seeding_lambda, 1.0)
            return
        if DEBUG:
            log('baseapp::start_ad_download_when_seeding: ad download is seeding, restart')
        d.set_video_event_callback(lambda d, event, params: self.sesscb_vod_event_callback(d, event, params, main_d))
        d.set_player_buffer_time(1)
        d.set_max_conns(10)
        d.set_max_conns_to_initiate(10)
        d.set_hidden(True)
        d.restart()

    def start_direct_download(self, main_url, download_url, developer_id, affiliate_id, zone_id):
        destdir = self.get_default_destdir()
        urlhash = hashlib.sha1(main_url).digest()
        if DEBUG:
            log('baseapp::start_direct_download: urlhash', binascii.hexlify(urlhash), 'main_url', main_url)
        newd = self.s.get_download(DLTYPE_DIRECT, urlhash)
        content_duration = 0
        if newd is not None:
            content_size = newd.get_content_length()
            if content_size is not None:
                content_duration = self.guess_duration_from_size(content_size)
        ads = self.ad_manager.get_ads(device_id=self.device_id, user_login=self.s.get_ts_login(), user_level=self.s.get_authlevel(), content_type=DLTYPE_DIRECT, content_id=binascii.hexlify(urlhash), content_ext='', content_duration=content_duration, affiliate_id=affiliate_id, zone_id=zone_id, developer_id=developer_id, include_interruptable_ads=self.get_playerconfig('enable_interruptable_ads', True), user_profile=self.user_profile)
        if ads == False:
            if DEBUG:
                log('baseapp::start_direct_download: failed to get ads, exit')
            raise Exception, 'Cannot start playback'
        initialdlstatus = None
        got_uninterruptable_ad = False
        if len(ads):
            for ad in ads:
                if not ad['interruptable']:
                    got_uninterruptable_ad = True
                    break

            if got_uninterruptable_ad:
                initialdlstatus = DLSTATUS_STOPPED
        if newd is None:
            dcfg = DownloadStartupConfig()
            dcfg.set_dest_dir(destdir)
            dcfg.set_wait_sufficient_speed(self.get_playerconfig('wait_sufficient_speed', False))
            dcfg.set_player_buffer_time(self.get_playerconfig('player_buffer_time', DEFAULT_PLAYER_BUFFER_TIME))
            dcfg.set_live_buffer_time(self.get_playerconfig('live_buffer_time', DEFAULT_LIVE_BUFFER_TIME))
            dcfg.set_video_event_callback(self.sesscb_vod_event_callback)
            dcfg.set_direct_download_url(download_url)
            dcfg.set_download_finished_callback(lambda url, download_url, urlhash, fileinfo, developer_id = developer_id, affiliate_id = affiliate_id, zone_id = zone_id: self.direct_download_finished(url, download_url, urlhash, fileinfo, developer_id, affiliate_id, zone_id))
            newd = self.s.start_direct_download(main_url, dcfg, initialdlstatus)
        else:
            newd.set_wait_sufficient_speed(self.get_playerconfig('wait_sufficient_speed', False))
            newd.set_player_buffer_time(self.get_playerconfig('player_buffer_time', DEFAULT_PLAYER_BUFFER_TIME))
            newd.set_live_buffer_time(self.get_playerconfig('live_buffer_time', DEFAULT_LIVE_BUFFER_TIME))
            newd.set_video_event_callback(self.sesscb_vod_event_callback)
            newd.set_direct_download_url(download_url)
            newd.set_download_finished_callback(lambda url, download_url, urlhash, fileinfo, developer_id = developer_id, affiliate_id = affiliate_id, zone_id = zone_id: self.direct_download_finished(url, download_url, urlhash, fileinfo, developer_id, affiliate_id, zone_id))
            if initialdlstatus is None:
                if DEBUG:
                    log('BaseApp::start_direct_download: restarting existing download: urlhash', binascii.hexlify(urlhash))
                newd.restart()
            else:
                ds = newd.network_get_state(usercallback=None, getpeerlist=False, sessioncalling=True)
                if ds.get_status != DLSTATUS_STOPPED:
                    if DEBUG:
                        log('BaseApp::start_direct_download: existing download is active, stop it and wait for ads: urlhash', binascii.hexlify(urlhash))
                    newd.stop()
                elif DEBUG:
                    log('BaseApp::start_direct_download: skip restarting existing download, wait for ads: urlhash', binascii.hexlify(urlhash))
        self.dlinfo_lock.acquire()
        try:
            self.downloads_in_vodmode[newd] = {}
            if newd in self.downloads_in_admode:
                if DEBUG:
                    log('baseapp::start_ad_downloads: remove old ad downloads on start')
                del self.downloads_in_admode[newd]
            if len(ads):
                if got_uninterruptable_ad:
                    if DEBUG:
                        log('baseapp::start_download: got uninterruptable ad, start ads immediatelly')
                    self.start_ad_downloads(newd, ads)
                else:
                    if DEBUG:
                        log('baseapp::start_download: no uninterruptable ad, start ads when main started')
                    start_ad_downloads_when_main_started_lambda = lambda : self.start_ad_downloads_when_main_started(newd, ads)
                    self.run_delayed(start_ad_downloads_when_main_started_lambda, 0.5)
        finally:
            self.dlinfo_lock.release()

        func = lambda : GoogleAnalytics.send_event('client', 'play', VERSION)
        self.run_delayed(func)
        return newd

    def get_encrypted_file_metainfo(self, path):
        f = None
        try:
            f = open(path, 'rb')
            meta_len = f.read(4)
            meta_len, = struct.unpack('l', meta_len)
            if DEBUG:
                log('baseapp::get_encrypted_file_metainfo: meta_len', meta_len)
            meta = f.read(meta_len)
            meta = pickle.loads(meta)
            if DEBUG:
                log('baseapp::get_encrypted_file_metainfo: meta', meta)
            offset_fix = 4 + meta_len - meta['offset']
            return (meta, offset_fix)
        finally:
            if f is not None:
                f.close()

    def play_encrypted_file(self, path, affiliate_id = 0, zone_id = 0, developer_id = 0):
        if DEBUG:
            log('baseapp::play_encrypted_file: path', path)
        if not os.path.isfile(path):
            if DEBUG:
                log('baseapp::play_encrypted_file: play_encrypted_file')
        meta, offset_fix = self.get_encrypted_file_metainfo(path)
        content_duration = meta['duration']
        if content_duration == 0:
            content_duration = self.guess_duration_from_size(meta['file_length'])
        ads = self.ad_manager.get_ads(device_id=self.device_id, user_login=self.s.get_ts_login(), user_level=self.s.get_authlevel(), content_type=DLTYPE_ENCRYPTED_FILE, content_id=binascii.hexlify(meta['hash']), content_ext='', content_duration=content_duration, affiliate_id=affiliate_id, zone_id=zone_id, developer_id=developer_id, include_interruptable_ads=False, provider_key=meta['provider'], user_profile=self.user_profile)
        if ads == False:
            if DEBUG:
                log('baseapp::play_encrypted_file: failed to get ads, exit')
            raise Exception, 'Cannot start playback'
        got_uninterruptable_ad = False
        if len(ads):
            for ad in ads:
                if not ad['interruptable']:
                    got_uninterruptable_ad = True
                    break

        newd = FakeDownload(DLTYPE_ENCRYPTED_FILE, path, meta, offset_fix, self.sesscb_vod_event_callback)
        self.dlinfo_lock.acquire()
        try:
            self.downloads_in_vodmode[newd] = {}
            if newd in self.downloads_in_admode:
                if DEBUG:
                    log('baseapp::play_encrypted_file: remove old ad downloads on start')
                del self.downloads_in_admode[newd]
            if len(ads) and got_uninterruptable_ad:
                if DEBUG:
                    log('baseapp::play_encrypted_file: got uninterruptable ad, start ads immediatelly')
                self.start_ad_downloads(newd, ads)
            else:
                newd.restart()
        finally:
            self.dlinfo_lock.release()

        return newd

    def direct_download_finished(self, url, download_url, urlhash, fileinfo, developer_id, affiliate_id, zone_id):
        try:
            if DEBUG:
                log('baseapp::direct_download_finished: url', url, 'download_url', download_url, 'fileinfo', fileinfo, 'd', developer_id, 'a', affiliate_id, 'z', zone_id)
            path = os.path.join(fileinfo['destdir'], fileinfo['filename'])
            piecelen = 524288
            tracker = 'http://tracker.publicbt.com:80/announce'
            trackers = [['http://t1.torrentstream.net:2710/announce'],
             ['http://t2.torrentstream.net:2710/announce'],
             ['http://tracker.publicbt.com:80/announce'],
             ['http://tracker.openbittorrent.com:80/announce']]
            if DEBUG:
                log('baseapp::direct_download_finished: create torrent: path', path, 'piecelen', piecelen, 'trackers', trackers)
            if fileinfo['mimetype'] == 'video/mp4':
                cleared_mp4_metatags = clear_mp4_metadata_tags_from_file(path, ['gssd', 'gshh'])
                if DEBUG:
                    log('baseapp::direct_download_finished: cleared_mp4_metatags', cleared_mp4_metatags)
            else:
                cleared_mp4_metatags = []
            tdef = TorrentDef()
            tdef.add_content(path)
            tdef.set_piece_length(piecelen)
            tdef.set_tracker(tracker)
            tdef.set_tracker_hierarchy(trackers)
            if download_url is None:
                tdef.set_urllist([url])
            if fileinfo.has_key('duration') and fileinfo['duration'] is not None:
                tdef.set_ts_duration(0, fileinfo['duration'])
            if len(cleared_mp4_metatags):
                tdef.set_ts_replace_mp4_metatags(0, ','.join(cleared_mp4_metatags))
            tdef.finalize()
            infohash = tdef.get_infohash()
            if not self.s.download_exists(DLTYPE_TORRENT, infohash):
                if DEBUG:
                    log('baseapp::direct_download_finished: add new torrent to downloads')
                dcfg = DownloadStartupConfig()
                dcfg.set_dest_dir(fileinfo['destdir'])
                d = self.s.start_download(tdef, dcfg)
            elif DEBUG:
                log('baseapp::direct_download_finished: torrent already exists in downloads: infohash', binascii.hexlify(infohash))
            player_id, torrent_checksum = self.send_torrent_to_server(tdef, developer_id, affiliate_id, zone_id)
            if player_id is not None:
                self.save_player_data_to_db(player_id, torrent_checksum, infohash, developer_id, affiliate_id, zone_id)
            self.save_url2torrent(url, infohash)
            self.s.save_ts_metadata_db(infohash, tdef.get_ts_metadata())
        except:
            if DEBUG:
                print_exc()

    def got_ts_metadata(self, tdef, metadata):
        if len(metadata) == 0:
            return
        if DEBUG:
            log('baseapp::got_ts_metadata: infohash', binascii.hexlify(tdef.get_infohash()), 'metadata', metadata)
        if metadata.has_key('duration'):
            tdef.set_ts_duration(metadata['index'], metadata['duration'])
        if metadata.has_key('prebuf_pieces'):
            tdef.set_ts_prebuf_pieces(metadata['index'], metadata['prebuf_pieces'])
        self.s.save_ts_metadata_db(tdef.get_infohash(), tdef.get_ts_metadata())
        self.save_ts_metadata_server(tdef.get_infohash(), tdef.get_ts_metadata())

    def save_ts_metadata_server(self, infohash, metadata):
        if metadata is None:
            return
        if DEBUG:
            log('baseapp::save_ts_metadata_server: infohash', binascii.hexlify(infohash), 'metadata', metadata)
        lambda_save_ts_metadata_server = lambda : self._save_ts_metadata_server(infohash, metadata)
        self.run_delayed(lambda_save_ts_metadata_server)

    def _save_ts_metadata_server(self, infohash, metadata):
        if DEBUG:
            log('baseapp::_save_ts_metadata_server: infohash', binascii.hexlify(infohash), 'metadata', metadata)
        try:
            self.tsservice.send_metadata(infohash, metadata)
        except:
            if DEBUG:
                log_exc()

    def send_torrent_to_server(self, tdef, developer_id = 0, affiliate_id = 0, zone_id = 0):
        if DEBUG_SERVICE_REQUESTS:
            log('baseapp::send_torrent_to_server: infohash', binascii.hexlify(tdef.get_infohash()), 'd', developer_id, 'a', affiliate_id, 'z', zone_id)
        torrent_data = tdef.save()
        torrent_checksum = hashlib.sha1(torrent_data).digest()
        protected = tdef.get_protected()
        if protected:
            infohash = tdef.get_infohash()
        else:
            infohash = None
        player_id = self.tsservice.send_torrent(torrent_data, developer_id, affiliate_id, zone_id, protected, infohash)
        if player_id is None:
            return
        if DEBUG_SERVICE_REQUESTS:
            log('baseapp::send_torrent_to_server: torrent saved: infohash', binascii.hexlify(tdef.get_infohash()), 'checksum', binascii.hexlify(torrent_checksum), 'd', developer_id, 'a', affiliate_id, 'z', zone_id, 'player_id', player_id)
        self.save_player_data_to_db(player_id, torrent_checksum, tdef.get_infohash(), developer_id, affiliate_id, zone_id)
        return (player_id, torrent_checksum)

    def update_torrent(self, tdef, developer_id = 0, affiliate_id = 0, zone_id = 0):
        lambda_update_torrent = lambda : self._update_torrent(tdef, developer_id, affiliate_id, zone_id)
        self.run_delayed(lambda_update_torrent)

    def _update_torrent(self, tdef, developer_id, affiliate_id, zone_id):
        try:
            torrent_data = tdef.save()
            torrent_checksum = hashlib.sha1(torrent_data).digest()
            ret = self.tsservice.check_torrent(torrent_checksum=torrent_checksum, infohash=tdef.get_infohash(), developer_id=developer_id, affiliate_id=affiliate_id, zone_id=zone_id)
            if ret is None:
                if DEBUG_SERVICE_REQUESTS:
                    log('baseapp::_update_torrent: check_torrent failed')
                return
            player_id, metadata, http_seeds = ret
            if DEBUG_SERVICE_REQUESTS:
                log('baseapp::_update_torrent: torrent saved: infohash', binascii.hexlify(tdef.get_infohash()), 'checksum', binascii.hexlify(torrent_checksum), 'player_id', player_id, 'metadata', metadata, 'http_seeds', http_seeds)
            if player_id is None:
                player_id, torrent_checksum = self.send_torrent_to_server(tdef, developer_id, affiliate_id, zone_id)
            else:
                self.save_player_data_to_db(player_id, torrent_checksum, tdef.get_infohash(), developer_id, affiliate_id, zone_id)
            if metadata is not None:
                self.s.save_ts_metadata_db(tdef.get_infohash(), metadata)
                try:
                    for d in self.s.get_downloads():
                        if d.get_hash() == tdef.get_infohash():
                            if DEBUG_SERVICE_REQUESTS:
                                log('baseapp::_update_torrent: send metadata to download: hash', binascii.hexlify(d.get_hash()), 'metadata', metadata)
                            d.got_metadata(metadata)

                except:
                    pass

            if http_seeds is not None:
                self.s.set_ts_http_seeds(tdef.get_infohash(), http_seeds)
                try:
                    for d in self.s.get_downloads():
                        if d.get_hash() == tdef.get_infohash():
                            if DEBUG_SERVICE_REQUESTS:
                                log('baseapp::_update_torrent: send http seeds to download: hash', binascii.hexlify(d.get_hash()), 'http_seeds', http_seeds)
                            d.got_http_seeds(http_seeds)

                except:
                    pass

        except:
            if DEBUG:
                log_exc()

    def get_torrent_from_server(self, infohash = None, player_id = None):
        if infohash is None and player_id is None:
            raise ValueError, 'infohash or player id must be specified'
        if infohash is not None and player_id is not None:
            raise ValueError, 'Both infohash and player id cannot be specified at the same time'
        if DEBUG_SERVICE_REQUESTS:
            if infohash is not None:
                log('baseapp::get_torrent_from_server: infohash', binascii.hexlify(infohash))
            elif player_id is not None:
                log('baseapp::get_torrent_from_server: player_id', player_id)
        player_data = self.tsservice.get_torrent(infohash=infohash, player_id=player_id)
        if player_data is None:
            return
        tdef = player_data['tdef']
        self.s.save_torrent_local(tdef, player_data['checksum'])
        self.s.save_ts_metadata_db(tdef.get_infohash(), tdef.get_ts_metadata())
        return player_data

    def get_torrent_from_adid(self, adid):
        infohash = self.get_infohash_from_adid(adid)
        if infohash is None:
            return
        ret = self.get_torrent_by_infohash(infohash)
        if ret is None:
            return
        return ret['tdef']

    def get_infohash_from_adid(self, adid):
        infohash = None
        infohash = self.get_infohash_from_adid_db(adid)
        if infohash is not None:
            return infohash
        infohash = self.get_infohash_from_adid_server(adid)
        if infohash is not None:
            self.save_adid2infohash_db(adid, infohash)
            return infohash

    def get_infohash_from_adid_db(self, adid):
        if DEBUG_SERVICE_REQUESTS:
            t = time.time()
        db = self.s.open_dbhandler(NTFY_ADID2INFOHASH)
        if db is None:
            return
        infohash = db.get(adid)
        self.s.close_dbhandler(db)
        if DEBUG_SERVICE_REQUESTS:
            log('baseapp::get_infohash_from_adid_db: adid', adid, 'infohash', infohash, 'time', time.time() - t)
        return infohash

    def get_ad_last_seen(self, infohash):
        db = self.s.open_dbhandler(NTFY_ADID2INFOHASH)
        if db is None:
            return
        last_seen = db.get_last_seen(infohash)
        self.s.close_dbhandler(db)
        if DEBUG_SERVICE_REQUESTS:
            log('baseapp::get_ad_last_seen: infohash', binascii.hexlify(infohash), 'last_seen', last_seen)
        return last_seen

    def get_infohash_from_adid_server(self, adid):
        return self.tsservice.get_infohash_from_adid(adid)

    def save_adid2infohash_db(self, adid, infohash):
        if DEBUG_SERVICE_REQUESTS:
            log('baseapp::save_adid2infohash_db: adid', adid, 'infohash', binascii.hexlify(infohash))
        db = self.s.open_dbhandler(NTFY_ADID2INFOHASH)
        if db is None:
            if DEBUG_SERVICE_REQUESTS:
                log('baseapp::save_adid2infohash_db: no db')
            return
        db.put(adid, infohash)
        self.s.close_dbhandler(db)

    def get_torrent_from_url(self, url):
        infohash = self.get_infohash_from_url(url)
        if infohash is None:
            return
        ret = self.get_torrent_by_infohash(infohash)
        if ret is None:
            return
        return ret['tdef']

    def get_infohash_from_url(self, url):
        infohash = None
        infohash = self.get_infohash_from_url_db(url)
        if infohash is not None:
            return infohash
        infohash = self.get_infohash_from_url_server(url)
        if infohash is not None:
            self.save_url2torrent_db(url, infohash)
            return infohash

    def get_infohash_from_url_db(self, url):
        db = self.s.open_dbhandler(NTFY_URL2TORRENT)
        if db is None:
            return
        infohash = db.get(url)
        self.s.close_dbhandler(db)
        if DEBUG_SERVICE_REQUESTS:
            log('baseapp::get_infohash_from_url: url', url, 'infohash', infohash)
        return infohash

    def get_infohash_from_url_server(self, url):
        return self.tsservice.get_infohash_from_url(url)

    def save_url2torrent(self, url, infohash):
        try:
            self.save_url2torrent_db(url, infohash)
        except:
            log_exc()

        try:
            self.save_url2torrent_server(url, infohash)
        except:
            log_exc()

    def save_url2torrent_db(self, url, infohash):
        if DEBUG_SERVICE_REQUESTS:
            log('baseapp::save_url2torrent: url', url, 'infohash', binascii.hexlify(infohash))
        db = self.s.open_dbhandler(NTFY_URL2TORRENT)
        if db is None:
            if DEBUG_SERVICE_REQUESTS:
                log('baseapp::save_url2torrent: no db')
            return
        db.put(url, infohash)
        self.s.close_dbhandler(db)

    def save_url2torrent_server(self, url, infohash):
        self.tsservice.save_url2infohash(url, infohash)

    def get_torrent_from_db(self, checksum = None, infohash = None):
        if checksum is None and infohash is None:
            return
        torrent_db = None
        tdef = None
        try:
            if DEBUG_SERVICE_REQUESTS:
                t = time.time()
            torrent_db = self.s.open_dbhandler(NTFY_TORRENTS)
            if torrent_db is None:
                return
            if checksum is not None:
                torrent = torrent_db.getTorrent(checksum=checksum, keys=['torrent_file_name'])
            else:
                torrent = torrent_db.getTorrent(infohash=infohash, keys=['torrent_file_name'])
            if DEBUG_SERVICE_REQUESTS:
                log('baseapp::get_torrent_from_db: infohash', infohash, 'checksum', checksum, 'torrent', torrent, 'time', time.time() - t)
            if torrent is None:
                return
            torrent_dir = torrent_db.getTorrentDir()
            path = os.path.join(torrent_dir, torrent['torrent_file_name'])
            if os.path.exists(path):
                if DEBUG_SERVICE_REQUESTS:
                    t = time.time()
                tdef = TorrentDef.load(path)
                if DEBUG_SERVICE_REQUESTS:
                    log('baseapp::get_torrent_from_db: load torrent from file: path', path, 'time', time.time() - t)
            else:
                if DEBUG_SERVICE_REQUESTS:
                    log('baseapp::get_torrent_from_db: torrent file removed, update db: path', path)
                torrent_db.deleteTorrent(infohash)
            return {'tdef': tdef,
             'infohash': torrent['infohash'],
             'checksum': torrent['checksum']}
        except:
            log_exc()
            return
        finally:
            if torrent_db is not None:
                self.s.close_dbhandler(torrent_db)

    def get_torrent_by_infohash(self, infohash):
        if DEBUG_SERVICE_REQUESTS:
            t = time.time()
        ret = self.get_torrent_from_db(infohash=infohash)
        if ret is not None:
            if DEBUG_SERVICE_REQUESTS:
                log('baseapp::get_torrent_by_infohash: got from db: infohash', binascii.hexlify(infohash), 'time', time.time() - t)
            return {'tdef': ret['tdef'],
             'checksum': ret['checksum']}
        if DEBUG_SERVICE_REQUESTS:
            t = time.time()
        player_data = self.get_torrent_from_server(infohash=infohash)
        if player_data is not None:
            if DEBUG_SERVICE_REQUESTS:
                log('baseapp::get_torrent_by_infohash: got from server: infohash', binascii.hexlify(infohash), 'time', time.time() - t)
            return {'tdef': player_data['tdef'],
             'checksum': player_data['checksum']}
        if DEBUG_SERVICE_REQUESTS:
            log('baseapp::get_torrent_by_infohash: not found: infohash', binascii.hexlify(infohash))

    def get_player_data_from_db(self, player_id):
        try:
            db = self.s.open_dbhandler(NTFY_TS_PLAYERS)
            if db is None:
                return
            player_data = db.get(player_id)
            if DEBUG_SERVICE_REQUESTS:
                log('baseapp::get_player_data_from_db: player_id', player_id, 'player_data', player_data)
            return player_data
        except:
            log_exc()
            return
        finally:
            if db is not None:
                self.s.close_dbhandler(db)

    def get_player_id_from_db(self, checksum, infohash, developer_id, affiliate_id, zone_id):
        try:
            db = self.s.open_dbhandler(NTFY_TS_PLAYERS)
            if db is None:
                return
            player_id = db.getPlayerId(checksum, infohash, developer_id, affiliate_id, zone_id)
            if DEBUG_SERVICE_REQUESTS:
                log('baseapp::get_player_id_from_db: player_id', player_id, 'checksum', checksum, 'infohash', binascii.hexlify(infohash), 'developer_id', developer_id, 'affiliate_id', affiliate_id, 'zone_id', zone_id)
            return player_id
        except:
            log_exc()
            return
        finally:
            if db is not None:
                self.s.close_dbhandler(db)

    def save_player_data_to_db(self, player_id, checksum, infohash, developer_id, affiliate_id, zone_id):
        if DEBUG_SERVICE_REQUESTS:
            log('baseapp::save_player_data_to_db: player_id', player_id, 'checksum', binascii.hexlify(checksum), 'infohash', binascii.hexlify(infohash), 'developer_id', developer_id, 'affiliate_id', affiliate_id, 'zone_id', zone_id)
        try:
            db = self.s.open_dbhandler(NTFY_TS_PLAYERS)
            if db is None:
                return
            db.put(player_id, checksum, infohash, developer_id, affiliate_id, zone_id)
        except:
            log_exc()
        finally:
            if db is not None:
                self.s.close_dbhandler(db)

    def get_player_data(self, player_id):
        player_data = self.get_player_data_from_db(player_id)
        if player_data is not None:
            ret = self.get_torrent_from_db(checksum=player_data['checksum'])
            if ret is not None:
                if DEBUG_SERVICE_REQUESTS:
                    log('baseapp::get_player_data: got from db: player_id', player_id, 'checksum', binascii.hexlify(player_data['checksum']), 'player_data', player_data)
                player_data['tdef'] = ret['tdef']
                return player_data
        player_data = self.get_torrent_from_server(player_id=player_id)
        if player_data is not None:
            if DEBUG_SERVICE_REQUESTS:
                log('baseapp::get_player_data: got from server: player_id', player_id, 'checksum', binascii.hexlify(player_data['checksum']), 'player_data', player_data)
            self.save_player_data_to_db(player_id, player_data['checksum'], player_data['tdef'].get_infohash(), player_data['developer_id'], player_data['affiliate_id'], player_data['zone_id'])
            return player_data
        if DEBUG_SERVICE_REQUESTS:
            log('baseapp::get_player_data: not found: player_id', player_id)

    def check_user_profile(self):
        if self.user_profile is None:
            self.user_profile = self.get_user_profile()
        return self.user_profile is not None

    def get_user_profile(self):
        db = None
        try:
            db = self.s.open_dbhandler(NTFY_USER_PROFILE)
            if db is None:
                return
            profile = db.get_active_profile()
            if DEBUG_SERVICE_REQUESTS:
                log('baseapp::get_user_profile: profile', str(profile))
            return profile
        except:
            log_exc()
            return
        finally:
            if db is not None:
                self.s.close_dbhandler(db)

    def sesscb_vod_event_callback(self, d, event, params, main_download = None):
        pass

    def get_supported_vod_events(self):
        pass

    def get_drive_list(self):
        try:
            drives = win32api.GetLogicalDriveStrings()
            drives = [ drivestr for drivestr in drives.split('\x00') if drivestr ]
            return drives
        except:
            return []

    def format_drive_name(self, drive):
        if drive is None:
            return ''
        if len(drive) < 2:
            return ''
        drive = drive[:2].lower()
        if not drive.endswith(':'):
            return ''
        return drive

    def get_disk_info(self, path):
        try:
            folder = os.path.dirname(path)
            if sys.platform == 'win32':
                free_bytes, total_bytes, _ = win32file.GetDiskFreeSpaceEx(folder)
                used_bytes = total_bytes - free_bytes
            else:
                st = os.statvfs(folder)
                free_bytes = st.f_bavail * st.f_frsize
                total_bytes = st.f_blocks * st.f_frsize
                used_bytes = (st.f_blocks - st.f_bfree) * st.f_frsize
            return (total_bytes, free_bytes, used_bytes)
        except:
            if DEBUG:
                log('baseapp::get_disk_info: cannot get disk info: path', path)
            return (None, None, None)

    def free_up_diskspace_by_downloads(self, infohash = None, needed = 0):
        disk_cache_limit = self.get_playerconfig('disk_cache_limit', DEFAULT_DISKSPACE_LIMIT)
        content_dir = self.get_default_destdir()
        total, avail, used = self.get_disk_info(content_dir)
        if avail is None:
            if disk_cache_limit == 0:
                if DEBUG:
                    log('baseapp::free_up_diskspace_by_downloads: cannot get disk info and disk cache is unlimited')
                return True
            avail = disk_cache_limit
        if DEBUG:
            log('BaseApp::free_up_diskspace_by_downloads: needed', needed, 'avail', avail, 'disk_cache_limit', disk_cache_limit)
        if disk_cache_limit < needed < avail:
            if DEBUG:
                log('BaseApp::free_up_diskspace_by_downloads: no cleanup for bigguns')
            return True
        inuse = 0L
        timelist = []
        if self.apptype == 'acestream':
            known_files = []
        for d in self.s.get_downloads():
            destfiles = d.get_dest_files(exts=videoextdefaults, get_all=True)
            if self.apptype == 'acestream':
                for filename, savepath in destfiles:
                    if os.path.exists(savepath):
                        known_files.append(savepath)

            if infohash is not None and infohash == d.get_hash():
                continue
            if d in self.downloads_in_vodmode:
                continue
            if d.is_hidden():
                continue
            if DEBUG:
                log('BaseApp::free_up_diskspace_by_downloads: downloaded content', destfiles)
            dinuse = 0L
            max_ctime = 0
            for filename, savepath in destfiles:
                dirname = os.path.dirname(savepath)
                if dirname != content_dir:
                    if DEBUG:
                        log('baseapp::free_up_diskspace_by_downloads: skip dir:', dirname)
                    continue
                if os.path.exists(savepath):
                    stat = os.stat(savepath)
                    dinuse += stat.st_size
                    if stat.st_ctime > max_ctime:
                        max_ctime = stat.st_ctime

            if dinuse > 0:
                inuse += dinuse
                timerec = (max_ctime, dinuse, d)
                timelist.append(timerec)

        if self.apptype == 'acestream':
            try:
                filelist = os.listdir(content_dir)
            except:
                if DEBUG:
                    print_exc()
                filelist = []

            if DEBUG:
                log('baseapp::free_up_diskspace_by_downloads: known_files', known_files, 'filelist', filelist)
            for basename in filelist:
                try:
                  basename = basename.decode('utf-8')
                except:
                  pass
                if basename == '.lock':
                    continue
                if infohash is not None and basename == binascii.hexlify(infohash):
                    if DEBUG:
                        log('baseapp::free_up_diskspace_by_downloads: keep file: basename', basename, 'infohash', binascii.hexlify(infohash))
                    continue
                filename = os.path.join(content_dir, basename)
                if filename not in known_files:
                    if DEBUG:
                        log('baseapp::free_up_diskspace_by_downloads: remove unknown file: filename', filename)
                    try:
                        os.remove(filename)
                    except:
                        if DEBUG:
                            print_exc()

        if disk_cache_limit == 0:
            limit = avail
        else:
            limit = min(avail, disk_cache_limit)
        if inuse + needed < limit:
            if DEBUG:
                log('BaseApp::free_up_diskspace_by_downloads: enough avail: inuse', inuse, 'needed', needed, 'limit', limit, 'avail', avail)
            return True
        timelist.sort()
        if DEBUG:
            log('baseapp::free_up_diskspace_by_downloads: timelist', timelist)
        to_free = inuse + needed - limit
        if DEBUG:
            log('baseapp::free_up_diskspace_by_downloads: to_free', to_free, 'limit', limit, 'inuse', inuse, 'needed', needed)
        for ctime, dinuse, d in timelist:
            if DEBUG:
                log('baseapp::free_up_diskspace_by_downloads: remove download: hash', binascii.hexlify(d.get_hash()), 'dinuse', dinuse, 'ctime', ctime)
            self.s.remove_download(d, removecontent=True)
            to_free -= dinuse
            if DEBUG:
                log('baseapp::free_up_diskspace_by_downloads: remove done: to_free', to_free, 'limit', limit, 'inuse', inuse, 'needed', needed)
            if to_free <= 0:
                return True

        return False

    def sesscb_states_callback(self, dslist):
        if self.debug_systray:
            getpeerlist = True
            haspeerlist = True
        else:
            getpeerlist = False
            haspeerlist = False
        gui_states_callback_wrapper_lambda = lambda : self.gui_states_callback_wrapper(dslist, haspeerlist)
        self.run_delayed(gui_states_callback_wrapper_lambda)
        return (1.0, getpeerlist)

    def gui_states_callback_wrapper(self, dslist, haspeerlist):
        try:
            self.gui_states_callback(dslist, haspeerlist)
        except:
            log_exc()

    def gui_states_callback(self, dslist, haspeerlist):
        if self.shuttingdown:
            return ({},
             [],
             0,
             0)
        playermode = self.playermode
        totalspeed = {UPLOAD: 0.0,
         DOWNLOAD: 0.0}
        totalhelping = 0
        display_stats = self.download_states_display_counter % DOWNLOAD_STATES_DISPLAY_INTERVAL == 0
        self.download_states_display_counter += 1
        all_dslist = {}
        playing_dslist = {}
        hidden_dslist = {}
        all_playing_are_seeding = True
        playing_premium_content = False
        self.dlinfo_lock.acquire()
        try:
            for ds in dslist:
                d = ds.get_download()
                all_dslist[d] = ds
                is_vod_download = False
                vod_download_params = None
                if d.is_hidden():
                    hidden_dslist[d] = ds
                if d in self.downloads_in_vodmode:
                    is_vod_download = True
                    vod_download_params = self.downloads_in_vodmode[d]
                    playing_dslist[d] = ds
                    if all_playing_are_seeding and ds.get_status() != DLSTATUS_SEEDING:
                        all_playing_are_seeding = False
                if is_vod_download and vod_download_params.get('premium', False):
                    playing_premium_content = True
                    provider_key = d.get_def().get_provider()
                    provider_content_id = d.get_def().get_content_id()
                    if not self.report_premium_download(provider_key, provider_content_id, vod_download_params):
                        if time.time() > vod_download_params['start'] + PREMIUM_PREVIEW_TIMEOUT and not vod_download_params.has_key('stopped_preview'):
                            if DEBUG_PREMIUM:
                                log('baseapp::gui_states_callback: user auth failed for premium content, stop')
                            vod_download_params['stopped_preview'] = True
                            self.stop_download(d, 'http://acestream.net/embed/premium', 'This content is available for premium users only')
                if DEBUG and display_stats:
                    log('baseapp::gui_states_callback: dlinfo: vod=%i type=%d hash=%s hidden=%i priority=%d status=%s paused=%i progress=%.1f%% error=%s' % (is_vod_download,
                     d.get_type(),
                     binascii.hexlify(d.get_hash()),
                     d.is_hidden(),
                     d.get_extra('priority', 0),
                     dlstatus_strings[ds.get_status()],
                     ds.get_paused(),
                     100.0 * ds.get_progress(),
                     ds.get_error()))
                self.update_download_stats(ds)
                if not d.is_hidden() or SHOW_HIDDEN_DOWNLOADS_INFO:
                    for dir in [UPLOAD, DOWNLOAD]:
                        totalspeed[dir] += ds.get_current_speed(dir)

                    totalhelping += ds.get_num_peers()

            for main_download, ad_downloads in self.downloads_in_admode.iteritems():
                if not playing_dslist.has_key(main_download):
                    if DEBUG:
                        log('baseapp::gui_states_callback: main download in ad mode is not in vod downloads: infohash', binascii.hexlify(main_download.get_hash()))
                else:
                    main_ds = playing_dslist[main_download]
                    if main_ds.get_status() == DLSTATUS_STOPPED:
                        all_ads_completed = True
                        for d in ad_downloads.keys():
                            if not all_dslist.has_key(d):
                                if DEBUG:
                                    log('baseapp::gui_states_callback: ad download not found in downloads: infohash', binascii.hexlify(d.get_hash()))
                            else:
                                ds = all_dslist[d]
                                if DEBUG:
                                    log('baseapp::gui_states_callback: check ad download: main', binascii.hexlify(main_download.get_hash()), 'ad', binascii.hexlify(d.get_hash()), 'status', ds.get_status(), 'progress', ds.get_progress())
                                status = ds.get_status()
                                if status == DLSTATUS_STOPPED_ON_ERROR:
                                    ad_downloads[d]['failed'] = True
                                elif status == DLSTATUS_STOPPED:
                                    if DEBUG:
                                        log('!!!! baseapp::gui_states_callback: ad download is stopped, mark as failed !!!!')
                                    ad_downloads[d]['failed'] = True
                                elif status == DLSTATUS_SEEDING:
                                    ad_downloads[d]['completed'] = True
                                else:
                                    all_ads_completed = False

                        if all_ads_completed:
                            if DEBUG:
                                log('baseapp::gui_states_callback: all ads are completed, restart download: infohash', binascii.hexlify(main_download.get_hash()))
                            main_download.restart()

        finally:
            self.dlinfo_lock.release()

        if haspeerlist:
            try:
                for ds in playing_dslist.values():
                    peerlist = ds.get_peerlist()
                    vodstats = ds.get_vod_stats()
                    stats = ds.get_stats()
                    if peerlist and self.statFrame:
                        self.statFrame.updateStats(spew=peerlist, statistics=stats, vod_stats=vodstats)
                    if DEBUG_STATS_TO_FILE:
                        self.save_state_to_file(spew=peerlist, statistics=stats, vod_stats=vodstats)
                    break

            except:
                log_exc()

        if self.live_frame is not None:
            try:
                for ds in playing_dslist.values():
                    peerlist = ds.get_peerlist()
                    vodstats = ds.get_vod_stats()
                    stats = ds.get_stats()
                    self.live_frame.update(spew=peerlist, statistics=stats, vod_stats=vodstats)
                    break

            except:
                print_exc()

        txt = self.appname + '\n\n'
        txt += 'DL: %.1f\n' % totalspeed[DOWNLOAD]
        txt += 'UL:   %.1f\n' % totalspeed[UPLOAD]
        txt += 'Helping: %d\n' % totalhelping
        self.OnSetSysTrayTooltip(txt)
        if totalspeed[DOWNLOAD] > self.max_download_rate:
            self.max_download_rate = totalspeed[DOWNLOAD]
        if totalspeed[UPLOAD] > self.max_upload_rate:
            self.max_upload_rate = totalspeed[UPLOAD]
        self.avg_download_rate_sum += totalspeed[DOWNLOAD]
        self.avg_download_rate_count += 1
        self.avg_download_rate = self.avg_download_rate_sum / float(self.avg_download_rate_count)
        self.avg_upload_rate_sum += totalspeed[UPLOAD]
        self.avg_upload_rate_count += 1
        self.avg_upload_rate = self.avg_upload_rate_sum / float(self.avg_upload_rate_count)
        if self.playing_premium_content != playing_premium_content:
            if DEBUG_PREMIUM:
                log('baseapp::gui_states_callback: playing_premium_content changed to', playing_premium_content)
            self.playing_premium_content = playing_premium_content
            if playing_premium_content:
                self.run_delayed(self.check_auth_level, 1.0, task_id='check_auth_level')
        if all_playing_are_seeding:
            if self.get_playerconfig('enable_interruptable_ads', True):
                max_progress = -1
                max_priority = -1
                download_to_restart = None
                for d, ds in hidden_dslist.iteritems():
                    status = ds.get_status()
                    if status == DLSTATUS_STOPPED or status == DLSTATUS_STOPPED_ON_ERROR:
                        priority = d.get_extra('priority', 0)
                        if ds.get_progress() == 1.0:
                            if DEBUG_HIDDEN_DOWNLOADS:
                                log('baseapp::gui_states_callback: restart completed hidden download: hash', binascii.hexlify(d.get_hash()), 'status', dlstatus_strings[status], 'progress', ds.get_progress())
                            d.restart()
                        elif priority > max_priority:
                            download_to_restart = d
                            max_progress = ds.get_progress()
                            max_priority = priority
                        elif ds.get_progress() > max_progress:
                            download_to_restart = d
                            max_progress = ds.get_progress()
                            max_priority = priority
                    elif status == DLSTATUS_HASHCHECKING or ds.get_progress() != 1.0:
                        if DEBUG_HIDDEN_DOWNLOADS:
                            log('baseapp::gui_states_callback: got running hidden download: hash', binascii.hexlify(d.get_hash()), 'status', dlstatus_strings[status], 'progress', ds.get_progress())
                        download_to_restart = None
                        break

                if download_to_restart is not None:
                    max_speed = self.get_playerconfig('max_download_rate', 0)
                    if max_speed == 0:
                        max_speed = self.max_download_rate
                    limit_speed = max_speed / 3
                    download_to_restart.set_max_speed(DOWNLOAD, limit_speed)
                    if DEBUG_HIDDEN_DOWNLOADS:
                        ds = hidden_dslist[download_to_restart]
                        log('baseapp::gui_states_callback: restart hidden download: hash', binascii.hexlify(download_to_restart.get_hash()), 'status', dlstatus_strings[ds.get_status()], 'progress', ds.get_progress(), 'max_speed', max_speed, 'limit_speed', limit_speed)
                    download_to_restart.restart()
            if playermode == DLSTATUS_DOWNLOADING:
                if DEBUG:
                    log('BaseApp::gui_states_callback: all playing download are seeding, restart others')
                    t = time.time()
                self.restart_other_downloads()
                if DEBUG:
                    log('BaseApp::gui_states_callback: restart others: time', time.time() - t)
        elif playermode == DLSTATUS_SEEDING:
            if DEBUG:
                log('BaseApp::gui_states_callback: not all playing download are seeding, stop others')
                t = time.time()
            self.stop_other_downloads()
            if DEBUG:
                log('BaseApp::gui_states_callback: stop others: time', time.time() - t)
        if len(playing_dslist) == 0:
            return ({},
             [],
             0,
             0)
        return (all_dslist,
         playing_dslist.values(),
         totalhelping,
         totalspeed)

    def update_download_stats(self, ds, force = False):
        return
        try:
            if not force and time.time() - self.last_download_stats < DOWNLOAD_STATS_INTERVAL:
                return
            self.last_download_stats = time.time()
            d = ds.get_download()
            download_id = d.get_download_id()
            if download_id is None:
                return
            if d.get_type() != DLTYPE_TORRENT:
                return
            tdef = d.get_def()
            if not self.stat_settings.check_content('ts', tdef):
                return
            downloaded = ds.get_total_transferred(DOWNLOAD)
            uploaded = ds.get_total_transferred(UPLOAD)
            if not self.download_stats.has_key(download_id):
                self.download_stats[download_id] = {'downloaded': 0,
                 'uploaded': 0}
            if self.download_stats[download_id]['downloaded'] != downloaded or self.download_stats[download_id]['uploaded'] != uploaded:
                self.download_stats[download_id]['downloaded'] = downloaded
                self.download_stats[download_id]['uploaded'] = uploaded
                infohash = binascii.hexlify(tdef.get_infohash())
                provider_key = tdef.get_provider()
                provider_content_id = tdef.get_content_id()
                self.traffic_stats.send_event(download_id, 'keepalive', downloaded, uploaded, infohash, provider_key, provider_content_id)
        except:
            if DEBUG:
                print_exc()

    def save_state_to_file(self, spew, statistics = None, vod_stats = None):
        info = ''
        if spew is not None:
            tot_uprate = 0.0
            tot_downrate = 0.0
            tot_downloaded = 0
            for x in range(len(spew)):
                peerdata = [''] * 17
                if spew[x]['optimistic'] == 1:
                    a = '*'
                else:
                    a = ' '
                peerdata[0] = a
                peerdata[2] = spew[x]['ip'].ljust(15)
                peerdata[3] = spew[x]['direction']
                peerdata[4] = ('%.0f kB/s' % (float(spew[x]['uprate']) / 1000)).ljust(10)
                tot_uprate += spew[x]['uprate']
                if spew[x]['uinterested'] == 1:
                    a = '*'
                else:
                    a = ' '
                peerdata[5] = a
                if spew[x]['uchoked'] == 1:
                    a = '*'
                else:
                    a = ' '
                peerdata[6] = a
                bitrate = None
                if vod_stats['videostatus'] is not None:
                    bitrate = vod_stats['videostatus'].bitrate
                str_downrate = '%.0f' % (spew[x]['downrate'] / 1024.0)
                if 'short_downrate' in spew[x]:
                    if bitrate is None:
                        str_downrate += ' (%.0f)' % (spew[x]['short_downrate'] / 1024 / 0.0)
                    else:
                        str_downrate += ' (%.0f, %.1f)' % (spew[x]['short_downrate'] / 1024.0, spew[x]['short_downrate'] / float(bitrate))
                peerdata[7] = str_downrate.ljust(15)
                tot_downrate += spew[x]['downrate']
                if spew[x]['dinterested'] == 1:
                    a = '*'
                else:
                    a = ' '
                peerdata[8] = a
                if spew[x]['dchoked'] == 1:
                    a = '*'
                else:
                    a = ' '
                peerdata[9] = a
                if spew[x]['snubbed'] == 1:
                    a = '*'
                else:
                    a = ' '
                peerdata[10] = a
                tot_downloaded += spew[x]['dtotal']
                peerdata[11] = ('%.2f MiB' % (float(spew[x]['dtotal']) / 1048576)).ljust(10)
                if spew[x]['utotal'] is not None:
                    a = '%.2f MiB' % (float(spew[x]['utotal']) / 1048576)
                else:
                    a = ''
                peerdata[12] = a.ljust(10)
                peerdata[13] = ('%.1f%%' % (float(int(spew[x]['completed'] * 1000)) / 10)).ljust(5)
                if spew[x]['speed'] is not None:
                    a = '%.0f' % (float(spew[x]['speed']) / 1024)
                    if 'speed_proxy' in spew[x]:
                        a += ' | p:%.0f' % (float(spew[x]['speed_proxy']) / 1024)
                    if 'speed_non_proxy' in spew[x]:
                        a += ' | r:%.0f' % (float(spew[x]['speed_non_proxy']) / 1024)
                else:
                    a = ''
                peerdata[14] = a.ljust(15)
                peerdata[15] = str(spew[x]['last_requested_piece']).ljust(4)
                peerdata[16] = str(spew[x]['last_received_piece']).ljust(4)
                info += '\t'.join(peerdata) + '\n'

            info += '\n\nTOTALS: up=' + '%.0f kB/s' % (float(tot_uprate) / 1024) + ' down=' + '%.0f kB/s' % (float(tot_downrate) / 1024) + ' downloaded=' + '%.2f MiB' % (float(tot_downloaded) / 1048576) + '\n\n'
        if vod_stats is not None:
            for pos, data in vod_stats['proxybuf'].iteritems():
                length = len(data)
                info += str(pos) + ' '
                for i in xrange(length / 131072):
                    info += '-'

                info += str(pos + length - 1) + '\n'

            info += 'buf: ' + str(vod_stats['outbuf']) + '\n'
            if vod_stats['videostatus'] is not None:
                vs = vod_stats['videostatus']
                info += ' >> idx: ' + str(vs.fileindex)
                info += ', br: ' + str(vs.bitrate / 1024)
                info += ', len: ' + str(vs.piecelen / 1024)
                info += ', first: ' + str(vs.first_piece)
                info += ', last: ' + str(vs.last_piece)
                info += ', have: ' + str(vs.numhave)
                info += ', comp: %.2f' % vs.completed
                info += ', prebuf: ' + str(vs.prebuffering)
                info += ', pos: ' + str(vs.playback_pos)
                info += ', hp: ' + str(vs.prebuf_high_priority_pieces)
                info += ', pp: ' + str(vs.prebuf_missing_pieces)
                have = vs.have[:]
                have.sort()
                info += ', pieces: ' + str(have)
            for vs in vod_stats['extra_videostatus']:
                info += '\n   index: ' + str(vs.fileindex)
                info += ', first piece: ' + str(vs.first_piece)
                info += ', last piece: ' + str(vs.last_piece)
                info += ', numhave: ' + str(vs.numhave)
                info += ', completed: %.2f' % vs.completed
                info += ', prebuf: ' + str(vs.prebuffering)
                info += ', hp: ' + str(vs.prebuf_high_priority_pieces)
                info += ', pp: ' + str(vs.prebuf_missing_pieces)
                have = vs.have[:]
                have.sort()
                info += ', pieces: ' + str(have)

        if statistics is not None:
            for piece in xrange(len(statistics.storage_inactive_list)):
                inactive = statistics.storage_inactive_list[piece]
                if inactive is None:
                    inactive = 'all'
                elif inactive == 1:
                    inactive = 'none'
                else:
                    inactive = str(len(inactive))
                info += '\n' + str(piece) + ': inactive=' + inactive + ' active=' + str(statistics.storage_active_list[piece]) + ' dirty=' + str(statistics.storage_dirty_list[piece])

        if len(info):
            self.debug_counter += 1
            try:
                filename = 'stat_snapshot_' + str(self.debug_counter).rjust(4, '0') + '_' + str(int(time.time())) + '.txt'
                f = open(os.path.join(self.installdir, filename), 'w')
                f.write(info)
                f.close()
            except:
                raise

    def OnSetSysTrayTooltip(self, txt):
        try:
            self.wrapper.set_icon_tooltip(txt)
        except:
            pass

    def restart_other_downloads(self):
        if self.shuttingdown:
            return
        if DEBUG:
            log('baseapp::restart_other_downloads: ---')
        self.playermode = DLSTATUS_SEEDING
        self.ratelimiter = UserDefinedMaxAlwaysOtherwiseEquallyDividedRateManager()
        self.set_ratelimits()
        dlist = self.s.get_downloads()
        for d in dlist:
            if d.is_hidden():
                ds = d.network_get_state(usercallback=None, getpeerlist=False, sessioncalling=True)
                if ds.get_status() != DLSTATUS_STOPPED:
                    if DEBUG_HIDDEN_DOWNLOADS:
                        log('baseapp::restart_other_downloads: unpause hidden download: hash', binascii.hexlify(d.get_hash()))
                    d.pause(False)
                continue
            if d not in self.downloads_in_vodmode:
                ds = d.network_get_state(usercallback=None, getpeerlist=False, sessioncalling=True)
                if ds.get_status() == DLSTATUS_STOPPED and ds.get_progress() == 1.0:
                    if DEBUG:
                        log('baseapp::restart_other_downloads: start seeding: infohash', binascii.hexlify(d.get_hash()))
                    d.set_mode(DLMODE_NORMAL)
                    d.restart()
                else:
                    d.pause(False)

    def stop_other_downloads(self):
        if self.shuttingdown:
            return
        if DEBUG:
            log('baseapp::stop_other_downloads: ---')
        self.playermode = DLSTATUS_DOWNLOADING
        dlist = self.s.get_downloads()
        for d in dlist:
            if d in self.downloads_in_vodmode:
                continue
            is_ad = False
            for maind_d, ads in self.downloads_in_admode.iteritems():
                if d in ads:
                    is_ad = True
                    break

            if is_ad:
                continue
            ds = d.network_get_state(usercallback=None, getpeerlist=False, sessioncalling=True)
            if ds.get_status() == DLSTATUS_STOPPED:
                continue
            if DEBUG:
                log('baseapp::stop_other_downloads: stop: infohash', binascii.hexlify(d.get_hash()), 'status', dlstatus_strings[ds.get_status()], 'progress', ds.get_progress())
            if ds.get_status() == DLSTATUS_SEEDING:
                d.pause(True, close_connections=True)
            else:
                d.stop()

    def stop_hidden_downloads(self):
        if self.shuttingdown:
            return
        if DEBUG_HIDDEN_DOWNLOADS:
            log('baseapp::stop_hidden_downloads: ---')
        dlist = self.s.get_downloads()
        for d in dlist:
            if not d.is_hidden():
                continue
            if d in self.downloads_in_vodmode:
                continue
            is_ad = False
            for maind_d, ads in self.downloads_in_admode.iteritems():
                if d in ads:
                    is_ad = True
                    break

            if is_ad:
                continue
            ds = d.network_get_state(usercallback=None, getpeerlist=False, sessioncalling=True)
            if ds.get_status() == DLSTATUS_STOPPED:
                if ds.get_progress() == 0.0:
                    if DEBUG_HIDDEN_DOWNLOADS:
                        log('baseapp::stop_hidden_downloads: remove: infohash', binascii.hexlify(d.get_hash()), 'status', dlstatus_strings[ds.get_status()], 'progress', ds.get_progress())
                    self.s.remove_download(d, removecontent=True)
                continue
            if DEBUG_HIDDEN_DOWNLOADS:
                log('baseapp::stop_hidden_downloads: stop: infohash', binascii.hexlify(d.get_hash()))
            d.stop()

    def remove_downloads_in_vodmode_if_not_complete(self):
        if DEBUG:
            log('BaseApp::remove_downloads_in_vodmode_if_not_complete: Removing playing download if not complete')
        for d in self.downloads_in_vodmode:
            d.set_state_callback(self.sesscb_remove_playing_callback)

    def sesscb_remove_playing_callback(self, ds):
        if DEBUG:
            d = ds.get_download()
            dlhash = binascii.hexlify(d.get_hash())
            log('BaseApp::sesscb_remove_playing_callback: type', d.get_type(), 'hash', dlhash, 'status', dlstatus_strings[ds.get_status()], 'progress', ds.get_progress())
        self.update_download_stats(ds, True)
        d = ds.get_download()
        if d.get_type() == DLTYPE_TORRENT:
            live = d.get_def().get_live()
        else:
            live = False
        if live:
            remove_content = True
        elif ds.get_status() == DLSTATUS_DOWNLOADING and ds.get_progress() >= MIN_PROGRESS_KEEP:
            remove_content = False
        elif ds.get_status() == DLSTATUS_SEEDING:
            remove_content = False
        elif ds.get_status() == DLSTATUS_HASHCHECKING:
            remove_content = False
        else:
            remove_content = True
        if not remove_content:
            if ds.get_status() == DLSTATUS_SEEDING:
                can_remove = self.can_remove_playing_download(d)
                if can_remove:
                    self.remove_download_info(d)
                if DEBUG:
                    log('baseapp::sesscb_remove_playing_callback: download is seeding, do not stop: dlhash', dlhash, 'remove_dlinfo', can_remove)
            else:
                if DEBUG:
                    log('BaseApp::sesscb_remove_playing_callback: keeping: dlhash', dlhash)
                remove_playing_download_lambda = lambda : self.remove_playing_download(d, removecontent=False, stop=True)
                self.run_delayed(remove_playing_download_lambda, 0.1)
        else:
            if DEBUG:
                log('BaseApp::sesscb_remove_playing_callback: voting for removing: dlhash', dlhash)
            if self.shuttingdown:
                if DEBUG:
                    log('BaseApp::sesscb_remove_playing_callback: shuttingdown, call remove_playing_download immediately')
                self.remove_playing_download(d, removecontent=True)
            else:
                if DEBUG:
                    log('BaseApp::sesscb_remove_playing_callback: schedule remove_playing_download')
                remove_playing_download_lambda = lambda : self.remove_playing_download(d, removecontent=True)
                self.run_delayed(remove_playing_download_lambda, 0.1)
        return (-1.0, False)

    def remove_playing_download(self, d, removecontent):
        if self.s is not None:
            if DEBUG:
                log('BaseApp::remove_playing_download: dlhash', binascii.hexlify(d.get_hash()), 'removecontent', removecontent)
            try:
                self.s.remove_download(d, removecontent)
                self.remove_download_info(d)
            except:
                log_exc()

        elif DEBUG:
            log('BaseApp::remove_playing_download: s is None')

    def stop_playing_download(self, d):
        if DEBUG:
            log('BaseApp::stop_playing_download: dlhash', binascii.hexlify(d.get_hash()))
        try:
            d.stop()
            self.remove_download_info(d)
        except:
            log_exc()

    def remove_download_info(self, d):
        if DEBUG:
            log('baseapp::remove_download_info: remove download: hash', binascii.hexlify(d.get_hash()))
        if d in self.downloads_in_vodmode:
            params = self.downloads_in_vodmode[d]
            if params.has_key('tns'):
                if DEBUG:
                    log('baseapp::remove_download_info: stop tns: hash', binascii.hexlify(d.get_hash()))
                params['tns'].stop()
            del self.downloads_in_vodmode[d]
        if d in self.downloads_in_admode:
            del self.downloads_in_admode[d]

    def set_ratelimits(self):
        uploadrate = float(self.get_playerconfig('total_max_upload_rate', 0))
        if DEBUG:
            log('BaseApp::set_ratelimits: Setting max upload rate to', uploadrate)
        if self.ratelimiter is not None:
            self.ratelimiter.set_global_max_speed(UPLOAD, uploadrate)
            self.ratelimiter.set_global_max_seedupload_speed(uploadrate)

    def ratelimit_callback(self, dslist):
        if self.ratelimiter is None:
            return
        adjustspeeds = False
        if self.ratelimit_update_count % 4 == 0:
            adjustspeeds = True
        self.ratelimit_update_count += 1
        if adjustspeeds:
            self.ratelimiter.add_downloadstatelist(dslist)
            self.ratelimiter.adjust_speeds()

    def load_playerconfig(self, state_dir):
        self.playercfgfilename = os.path.join(state_dir, 'playerconf.pickle')
        self.playerconfig = {}
        if not os.path.isfile(self.playercfgfilename):
            return
        try:
            f = open(self.playercfgfilename, 'rb')
            self.playerconfig = pickle.load(f)
            f.close()
        except:
            print_exc()
            self.playerconfig = {}

    def save_playerconfig(self):
        try:
            f = open(self.playercfgfilename, 'wb')
            pickle.dump(self.playerconfig, f)
            f.close()
        except:
            log_exc()

    def set_playerconfig(self, key, value):
        if self.playerconfig.has_key(key):
            old_value = self.playerconfig[key]
        else:
            old_value = None
        self.playerconfig[key] = value
        if key == 'total_max_upload_rate':
            try:
                self.set_ratelimits()
            except:
                log_exc()

        return old_value

    def update_playerconfig(self, changed_config_params):
        if 'enable_interruptable_ads' in changed_config_params:
            value = self.get_playerconfig('enable_interruptable_ads')
            if DEBUG:
                log('baseapp::update_playerconfig: enable_interruptable_ads changed: value', value)
            if value:
                self.run_delayed(self.check_preload_ads, 3.0, 'check_preload_ads')
            else:
                self.run_delayed(self.stop_hidden_downloads, 3.0)
        if 'disk_cache_limit' in changed_config_params:
            if DEBUG:
                log('baseapp::update_playerconfig: disk cache limit changed:', self.get_playerconfig('disk_cache_limit'))
            self.free_up_diskspace_by_downloads()
        for d in self.downloads_in_vodmode:
            d.set_wait_sufficient_speed(self.get_playerconfig('wait_sufficient_speed'))
            d.set_http_support(self.get_playerconfig('enable_http_support'))
            d.set_player_buffer_time(self.get_playerconfig('player_buffer_time'))
            d.set_live_buffer_time(self.get_playerconfig('live_buffer_time'))
            d.set_max_speed(UPLOAD, self.get_playerconfig('total_max_upload_rate'))
            d.set_max_speed(DOWNLOAD, self.get_playerconfig('total_max_download_rate'), self.get_playerconfig('auto_download_limit'))
            d.set_max_conns(self.get_playerconfig('download_max_connects'))

    def get_playerconfig(self, key, default = None):
        if key in self.playerconfig:
            return self.playerconfig[key]
        return default

    def OnExit(self):
        log('BaseApp::OnExit:', currentThread().getName())
        self.shuttingdown = True
        self.remove_downloads_in_vodmode_if_not_complete()
        if self.max_download_rate > 0:
            if DEBUG:
                log('baseapp::onexit: save max down rate:', self.max_download_rate)
            self.set_playerconfig('max_download_rate', self.max_download_rate)
        self.save_playerconfig()
        self.i2i_listen_server.shutdown()
        if globalConfig.get_mode() != 'client_console':
            time.sleep(2)
        if self.s is not None:
            try:
                state_dir = self.s.get_state_dir()
                cfgfilename = Session.get_default_config_filename(state_dir)
                if DEBUG:
                    log('baseapp::onexit: save SessionStartupConfig to', cfgfilename)
                scfg = SessionStartupConfig.load(cfgfilename)
                scfg.set_authlevel(self.s.get_authlevel())
                scfg.save(cfgfilename)
            except:
                pass

            self.s.shutdown(hacksessconfcheckpoint=False)
        self.save_cookies()
        if DEBUG:
            self.debug_threads()

    def debug_threads_task(self):
        try:
            self.debug_threads()
        finally:
            self.run_delayed(self.debug_threads_task, 600)

    def debug_threads(self):
        log('baseapp::debug_threads: ---')
        count = 0
        for t in enumerate():
            log('baseapp::debug_threads: thread is running', t.name, 'daemon', t.daemon)
            count += 1

        log('baseapp::debug_threads: count', count)

    def clear_session_state(self):
        try:
            if self.s is not None:
                dlist = self.s.get_downloads(DLTYPE_TORRENT)
                for d in dlist:
                    if not d.is_hidden():
                        self.s.remove_download(d, removecontent=True)

                dlist = self.s.get_downloads(DLTYPE_DIRECT)
                for d in dlist:
                    if not d.is_hidden():
                        self.s.remove_download(d, removecontent=True)

            if self.apptype == 'acestream':
                time.sleep(3)
                path = self.get_default_destdir()
                shutil.rmtree(path, True)
                if DEBUG:
                    log('baseapp::clear_session_state: delete cache dir:', path)
        except:
            log_exc()

        time.sleep(1)

    def show_error(self, msg):
        log('baseapp::show_error:', msg)

    def get_default_destdir(self):
        dest_dir = self.get_playerconfig('download_dir')
        if dest_dir is not None:
            if DEBUG:
                print >> sys.stderr, 'get_default_destdir: get from config:', dest_dir, type(dest_dir)
        elif sys.platform == 'win32':
            registry = Win32RegChecker()
            dest_dir = registry.readKey(HKCU, 'Software\\' + self.registry_key, 'DataDir', ignore_errors=True)
            if dest_dir is None:
                dest_dir = registry.readKey(HKLM, 'Software\\' + self.registry_key, 'DataDir', ignore_errors=True)
            if DEBUG:
                print >> sys.stderr, 'get_default_destdir: get from registry:', dest_dir, type(dest_dir)
        if self.apptype == 'acestream':
            if sys.platform == 'win32' and dest_dir is not None:
                if len(dest_dir) < 2:
                    dest_dir = None
                else:
                    drive = dest_dir[:2]
                    if not drive.endswith(':'):
                        dest_dir = None
                    else:
                        dest_dir = os.path.join(drive + '\\', CACHE_DIR_NAME)
            if not self.check_dest_dir(dest_dir, make_hidden=True):
                dest_dir = self.select_dest_dir()
                if DEBUG:
                    log('baseapp::get_default_destdir: check_dest_dir() failed, selected:', dest_dir)
        else:
            if dest_dir is not None:
                if not self.check_dest_dir(dest_dir, make_hidden=False):
                    dest_dir = None
            if dest_dir is None:
                state_dir = Session.get_default_state_dir()
                dest_dir = os.path.join(state_dir, 'downloads')
                if not self.check_dest_dir(dest_dir, make_hidden=False):
                    dest_dir = None
            if dest_dir is None and sys.platform != 'win32':
                dest_dir = os.path.join('/tmp', '.ACEStream', 'downloads')
                if not self.check_dest_dir(dest_dir, make_hidden=False):
                    dest_dir = None
        if dest_dir is None:
            raise Exception, 'Cannot select dest dir'
        self.set_playerconfig('download_dir', dest_dir)
        return dest_dir

    def check_dest_dir(self, dest_dir, make_hidden):
        if dest_dir is None:
            return False
        if not os.path.isdir(dest_dir):
            if DEBUG:
                log('baseapp::check_dest_dir: dest dir is not a directory:', dest_dir)
            try:
                os.makedirs(dest_dir)
            except:
                if DEBUG:
                    log('baseapp::check_dest_dir: failed to create dest dir:', dest_dir)
                return False

            if make_hidden and sys.platform == 'win32':
                try:
                    p = os.popen('attrib +h ' + dest_dir)
                    p.close()
                except:
                    if DEBUG:
                        print_exc()

        try:
            lock = os.path.join(dest_dir, '.lock')
            f = open(lock, 'w')
            f.close()
        except:
            if DEBUG:
                log('baseapp::check_dest_dir: cannot write to dest dir:', dest_dir)
            return False

        return True

    def select_dest_dir(self):
        dest_dir = None
        if sys.platform == 'win32':
            candidates = []
            drive_list = self.get_drive_list()
            if DEBUG:
                log('>>>drive_list', drive_list)
            for drive in drive_list:
                if DEBUG:
                    log('>>>drive1', drive)
                drive = self.format_drive_name(drive) + '\\'
                if DEBUG:
                    log('>>>drive2', drive)
                total, free, used = self.get_disk_info(drive)
                if free is not None:
                    path = os.path.join(drive, CACHE_DIR_NAME)
                    candidates.append((free, path))

            candidates.sort(reverse=True)
            if DEBUG:
                log('baseapp::select_dest_dir: candidates', candidates)
            for free, path in candidates:
                if self.check_dest_dir(path, True):
                    dest_dir = path
                    break

        else:
            state_dir = Session.get_default_state_dir()
            path = os.path.join(state_dir, 'cache')
            if self.check_dest_dir(path, True):
                dest_dir = path
            if dest_dir is None:
                path = os.path.join('/tmp', '.ACEStream', 'cache')
                if self.check_dest_dir(path, make_hidden=True):
                    dest_dir = path
        if DEBUG:
            log('baseapp::select_dest_dir: dest dir selected:', dest_dir)
        return dest_dir

    def get_preload_ads_enabled(self, default_value = True):
        enabled = self.get_playerconfig('enable_interruptable_ads')
        if enabled is None:
            if sys.platform == 'win32':
                registry = Win32RegChecker()
                enabled = registry.readKey(HKCU, 'Software\\' + self.registry_key, 'EnablePreload', ignore_errors=True)
                if DEBUG:
                    log('baseapp::get_preload_ads_enabled: get from registry HKCU:', enabled)
                if enabled is None:
                    enabled = registry.readKey(HKLM, 'Software\\' + self.registry_key, 'EnablePreload', ignore_errors=True)
                    if DEBUG:
                        log('baseapp::get_preload_ads_enabled: get from registry HKLM:', enabled)
                if enabled is None:
                    enabled = default_value
                else:
                    try:
                        enabled = int(enabled)
                        enabled = enabled != 0
                    except:
                        enabled = default_value

            else:
                enabled = default_value
            self.set_playerconfig('enable_interruptable_ads', enabled)
        elif DEBUG:
            log('baseapp::get_preload_ads_enabled: get from config:', enabled)
        return enabled

    def is_svc(self, dlfile, tdef):
        svcfiles = None
        if tdef.is_multifile_torrent():
            enhancement = tdef.get_files(exts=svcextdefaults)
            if enhancement:
                enhancement.sort()
                if tdef.get_length(enhancement[0]) == tdef.get_length(dlfile):
                    svcfiles = [dlfile]
                    svcfiles.extend(enhancement)
        return svcfiles

    def i2ithread_readlinecallback(self, ic, cmd):
        pass

    def make_provider_stream_cache_key(self, provider_key, infohash, device_id, user_login, user_password, user_key):
        return '-'.join([provider_key,
         binascii.hexlify(infohash),
         device_id,
         user_login,
         hashlib.sha1(user_password).hexdigest(),
         user_key])

    def update_provider_stream_cache(self, provider_key, infohash, device_id, user_login, user_password, user_key):
        key = self.make_provider_stream_cache_key(provider_key, infohash, device_id, user_login, user_password, user_key)
        if DEBUG:
            log('baseapp::update_provider_stream_cache: save data to provider stream cache: key', key)
        self.provider_stream_cache.setdefault(key, {'last_success': 0})
        self.provider_stream_cache[key]['last_success'] = time.time()

    def check_provider_stream_cache(self, provider_key, infohash, device_id, user_login, user_password, user_key):
        key = self.make_provider_stream_cache_key(provider_key, infohash, device_id, user_login, user_password, user_key)
        if key not in self.provider_stream_cache:
            return False
        else:
            last_success = self.provider_stream_cache[key]['last_success']
            if DEBUG:
                log('baseapp::check_provider_stream_cache: got data from provider stream cache: key', key, 'last_success', last_success)
            if time.time() - last_success > STREAM_CACHE_TTL:
                if DEBUG:
                    log('baseapp::check_provider_stream_cache: data from provider stream cache expired: key', key, 'last_success', last_success)
                del self.provider_stream_cache[key]
                return False
            if DEBUG:
                log('baseapp::check_provider_stream_cache: got valid data from provider stream cache: key', key, 'last_success', last_success)
            return True

    def load_cookies(self):
        try:
            f = open(self.cookie_file, 'r')
            data = pickle.load(f)
            f.close()
            for c in data:
                if DEBUG:
                    log('baseapp::load_cookies: add cookie:', c)
                self.cookie_jar.set_cookie(c)

            return True
        except:
            if DEBUG:
                log('baseapp::load_cookies: cannot load cookies file:', self.cookie_file)
            return False

    def save_cookies(self):
        try:
            cookies = []
            for c in self.cookie_jar:
                cookies.append(c)

            if DEBUG:
                log('baseapp::save_cookies: file', self.cookie_file, 'cookies', cookies)
            f = open(self.cookie_file, 'w')
            pickle.dump(cookies, f)
            f.close()
            return True
        except:
            if DEBUG:
                log('baseapp::save_cookies: cannot save to file', self.cookie_file)
            return False

    def check_premium_status(self, provider_key, content_id, infohash):
        if content_id is None:
            if DEBUG_PREMIUM:
                log('baseapp::check_premium_status: empty content id')
            return False
        status = self.tsservice.check_premium_status(provider_key, content_id, infohash)
        if DEBUG_PREMIUM:
            log('baseapp::check_premium_status: provider_key', provider_key, 'content_id', content_id, 'status', status)
        if status is None:
            if DEBUG_PREMIUM:
                log('baseapp::check_premium_status: request failed, consider premium: provider_key', provider_key, 'content_id', content_id)
            return True
        return status == 1

    def report_premium_download(self, provider_key, content_id, params):
        report = False
        check_user = False
        user_ok = True
        if not params.has_key('last_report'):
            if DEBUG_PREMIUM:
                log('baseapp::report_premium_download: not yet reported')
            report = True
        elif params['last_report'] < time.time() - params['report_interval']:
            if DEBUG_PREMIUM:
                log('baseapp::report_premium_download: time to report: last', params['last_report'], 'now', time.time(), 'interval', params['report_interval'])
            report = True
        if not params.has_key('last_user_check'):
            if DEBUG_PREMIUM:
                log('baseapp::report_premium_download: user not checked')
            check_user = True
        elif params['last_user_check'] < time.time() - params['user_check_interval']:
            if DEBUG_PREMIUM:
                log('baseapp::report_premium_download: time to check user: last', params['last_user_check'], 'now', time.time(), 'interval', params['user_check_interval'])
            check_user = True
        if report:
            params['last_report'] = time.time()
            user_login = self.s.get_ts_login()
            self.tsservice.report_premium_download(params['download_id'], provider_key, content_id, user_login)
        if check_user:
            params['last_user_check'] = time.time()
            user_level = self.s.get_authlevel()
            if user_level != 2:
                if DEBUG_PREMIUM:
                    log('baseapp::report_premium_download: user auth failed: level', user_level)
                user_ok = False
        return user_ok

    def check_statistics_settings(self):
        if DEBUG:
            log('baseapp::check_statistics_settings: ---')
        try:
            timeout = self.stat_settings.check_settings()
            self.traffic_stats.set_url_list(self.stat_settings.get_url_list('ts'))
        except:
            if DEBUG:
                print_exc()
            timeout = 3600
        finally:
            if DEBUG:
                log('baseapp::check_statistics_settings: next run in', timeout)
            self.run_delayed(self.check_statistics_settings, timeout)

    def tns_send_event(self, d, event, event_data = None, delay = 0):
        try:
            if d in self.downloads_in_vodmode:
                dparams = self.downloads_in_vodmode[d]
                if dparams.has_key('tns'):
                    dparams['tns'].send_event(event, event_data, delay)
        except:
            print_exc()

    def init_hardware_key(self):
        try:
            self.hardware_key = get_hardware_key()
            if DEBUG:
                log('baseapp::init_hardware_key: got key:', self.hardware_key)
        except:
            if DEBUG:
                print_exc()
            self.hardware_key = None

    def check_integrity(self):
        if sys.platform != 'win32':
            return True
        if not self.check_string('.Torrent Stream', '64048011141141110101' + '1611230380611411101790901'):
            if DEVELOPER_MODE:
                log('string failed')
            return False
        selfpath = sys.argv[0]
        exename = os.path.basename(selfpath)
        if self.apptype == 'torrentstream':
            check_exe1 = 'tsengine.exe'
            check_exe2 = 'tsengine'
            check_exe3 = '61151110101130150' + '1011101640101021101'
            check_exe4 = '61151110' + '1011301501011101'
        else:
            check_exe1 = 'ace_engine.exe'
            check_exe2 = 'ace_engine'
            check_exe3 = '79099010159' + '0101011301501011101640101021101'
            check_exe4 = '790990101590101011' + '301501011101'
        if exename != check_exe1 and exename != check_exe2:
            if DEVELOPER_MODE:
                log('exename failed:', exename)
            return False
        if not (self.check_string(exename, check_exe3) or self.check_string(exename, check_exe4)):
            if DEVELOPER_MODE:
                log('exename failed 2')
            return False
        base = os.path.abspath(os.path.dirname(selfpath))
        if DEVELOPER_MODE:
            log('selfpath', selfpath, 'exename', exename, 'base', base)
        files = []
        files.append({'path': 'lib\\pycompat27.pyd',
         'path2': '801501890290211121990111901211790611050550640211121001'})
        files.append({'path': '..\\updater\\tsupdate.exe',
         'path2': '640640290711211001790611101411290611511711211001790611101640101021101'})
        files.append({'path': '..\\player\\npts_plugin.dll',
         'path2': '640640290211801790121101411290011211611511590211801711301501011640001801801'})
        files.append({'path': '..\\player\\tsplayer.exe',
         'path2': '640640290211801790121101411290611511211801790121101411640101021101'})
        files.append({'path': 'python27.dll',
         'path2': '211121611401111011050550640001801801',
         'check': '4cad50ea762261d7f1361f7095cc6c740c2aa1b6',
         'check2': '250990790001350840101790550450050050450940001550201940150450940201550840750350990990450990550250840990050790790940890450'})
        files.append({'path': 'lib\\_ctypes.pyd',
         'path2': '801501890290590990611121211101511640211121001',
         'check': '616293e45730b2d4b49002d65cac9fb319c44aa2',
         'check2': '450940450050750150101250350550150840890050001250890250750840840050001450350990790990750201890150940750990250250790790050'})
        files.append({'path': 'lib\\_hashlib.pyd',
         'path2': '801501890290590401790511401801501890640211121001',
         'check': '3e5e42e2ff2bfdfa36fad0a14d18a5508717ee47',
         'check2': '150101350101250050101050201201050890201001201790150450201790001840790940250001940650790350350840650550940550101101250550'})
        files.append({'path': 'lib\\_socket.pyd',
         'path2': '801501890290590511111990701101611640211121001',
         'check': '95deea9dbbf5c19d8042439bd676c2c3e6b47328',
         'check2': '750350001101101790750001890890201350990940750001650840250050250150750890001450550450990050990150101450890250550150050650'})
        files.append({'path': 'lib\\_sqlite3.pyd',
         'path2': '801501890290590511311801501611101150640211121001',
         'check': 'dc0dadc7e0a73ca83c7f6fa21e807b5eb8ff67e1',
         'check2': '001990840001790001990550101840790550150990790650150990550201450201790050940101650840550890350101890650201201450550101940'})
        files.append({'path': 'lib\\_ssl.pyd',
         'path2': '801501890290590511511801640211121001',
         'check': '7d656f10b4d9d7f6d55caaa626e5975422637466',
         'check2': '550001450350450201940840890250001750001550201450001350350990790790790450050450101350750550350250050050450150550250450450'})
        files.append({'path': 'lib\\LIBEAY32.dll',
         'path2': '801501890290670370660960560980150050640001801801',
         'check': '3fc80784b3f0714a1859521f990965b949a71536',
         'check2': '150201990650840550650250890150201840550940250790940650350750350050940201750750840750450350890750250750790550940350150450'})
        files.append({'path': 'lib\\M2Crypto.__m2crypto.pyd',
         'path2': '801501890290770050760411121211611111640590590901050990411121211611111640211121001',
         'check': '01a2dbcfe59602b45fa9c389cb604570ca71dbf1',
         'check2': '840940790050001890990201101350750450840050890250350201790750990150650750990890450840250350550840990790550940001890201940'})
        files.append({'path': 'lib\\pycompat.pyd',
         'path2': '801501890290211121990111901211790611640211121001',
         'check': 'e282471605acb12f842fe1047ca445e819297762',
         'check2': '101050650050250550940450840350790990890940050201650250050201101940840250550990790250250350101650940750050750550550450050'})
        files.append({'path': 'lib\\SSLEAY32.dll',
         'path2': '801501890290380380670960560980150050640001801801',
         'check': '42323e4435bc986c45c9a2b841e7da7b6a98b228',
         'check2': '250050150050150101250250150350890990750650450990250350990750790050890650250940101550001790550890450790750650890050050650'})
        files.append({'path': 'lib\\wxbase28uh_vc.dll',
         'path2': '801501890290911021890790511101050650711401590811990640001801801',
         'check': '22a7683af988f5d0bef8abe4934dba03a093f21d',
         'check2': '050050790550450650150790201750650650201350001840890101201650790890101250750150250001890790840150790840750150201050940001'})
        files.append({'path': 'lib\\wxmsw28uh_adv_vc.dll',
         'path2': '801501890290911021901511911050650711401590790001811590811990640001801801',
         'check': 'd0aac3f14afe9c0bedc9a906b4dd6981597a8685',
         'check2': '001840790790990150201940250790201101750990840890101001990750790750840450890250001001450750650940350750550790650450650350'})
        files.append({'path': 'tsengine.exe',
         'path2': '611511101011301501011101640101021101',
         'check': '1a77f3cf03b882514683af1d6d2f9f0480a4bf2e',
         'check2': '940790550550201150990201840150890650650050350940250450650150790201940001450001050201750201840250650840790250890201050101'})
        files.append({'path': 'tsengine_stream.exe',
         'path2': '611511101011301501011101590511611411101790901640101021101',
         'check': '0c28965c60bae004e0c8a0a79f070dce266f6e33',
         'check2': '840990050650750450350990450840890790101840840250101840990650790840790550750201840550840001990101050450450201450101150150'})
        return self.check_files(base, files)

    def check_files(self, base, files):
        for f in files:
            do_check = f.has_key('check')
            if not self.check_string(f['path'], f['path2']):
                if DEVELOPER_MODE:
                    log('path failed:', f['path'])
                return False
            if do_check and not self.check_string(f['check'], f['check2']):
                if DEVELOPER_MODE:
                    log('check failed:', f['check'])
                return False
            path = os.path.join(base, f['path'])
            if not self.file_exists(path):
                if DEVELOPER_MODE:
                    log('not found:', path)
                return False
            if do_check:
                check = self.file_checksum(path)
                if check != f['check']:
                    if DEVELOPER_MODE:
                        log('checksum failed:', path, f['check'], check)
                    return False

        return True

    def check_string(self, s, check):
        s1 = self.get_string(check)
        if s1 != s:
            if DEVELOPER_MODE:
                log('check string failed:', s, s1)
            return False
        return True

    def get_string(self, s, padding = 3):
        return ''.join([ chr(int(s[i:i + padding][::-1])) for i in xrange(0, len(s), padding) ])

    def file_exists(self, path):
        if not os.path.isfile(path):
            return False
        try:
            f = open(path, 'rb')
            f.close()
        except:
            return False

        return True

    def file_checksum(self, path):
        f = None
        try:
            f = open(path, 'rb')
            h = hashlib.sha1()
            got_data = False
            while True:
                buf = f.read(4096)
                if not buf:
                    break
                got_data = True
                h.update(buf)

            if not got_data:
                return ''
            return h.hexdigest()
        except:
            if DEBUG:
                print_exc()
            return ''
        finally:
            if f is not None:
                f.close()
