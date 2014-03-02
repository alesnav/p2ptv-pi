#Embedded file name: ACEStream\Core\SessionConfig.pyo
import sys
import copy
import pickle
from ACEStream.env import TS_ENV_PLATFORM
from ACEStream.Core.simpledefs import *
from ACEStream.Core.defaults import sessdefaults
from ACEStream.Core.Base import *
from ACEStream.Core.BitTornado.RawServer import autodetect_socket_style
from ACEStream.Core.Utilities.utilities import find_prog_in_PATH
from ACEStream.Core.Utilities.TSCrypto import AES_encrypt, AES_decrypt, m2_AES_encrypt, m2_AES_decrypt

class SessionConfigInterface():

    def __init__(self, sessconfig = None):
        if sessconfig is not None:
            self.sessconfig = sessconfig
            return
        self.sessconfig = {}
        self.sessconfig.update(sessdefaults)
        if sys.platform == 'win32':
            ffmpegname = 'ffmpeg.exe'
        else:
            ffmpegname = 'ffmpeg'
        ffmpegpath = find_prog_in_PATH(ffmpegname)
        if ffmpegpath is None:
            if sys.platform == 'win32':
                self.sessconfig['videoanalyserpath'] = ffmpegname
            elif sys.platform == 'darwin':
                self.sessconfig['videoanalyserpath'] = 'macbinaries/ffmpeg'
            else:
                self.sessconfig['videoanalyserpath'] = ffmpegname
        else:
            self.sessconfig['videoanalyserpath'] = ffmpegpath
        self.sessconfig['ipv6_binds_v4'] = autodetect_socket_style()

    def set_value(self, name, value):
        self.sessconfig[name] = value

    def get_value(self, name, default = None):
        return self.sessconfig.get(name, default)

    def set_buffer_dir(self, bufferdir):
        self.sessconfig['buffer_dir'] = bufferdir

    def get_buffer_dir(self):
        return self.sessconfig['buffer_dir']

    def set_ads_dir(self, path):
        self.sessconfig['ads_dir'] = path

    def get_ads_dir(self):
        return self.sessconfig['ads_dir']

    def set_state_dir(self, statedir):
        self.sessconfig['state_dir'] = statedir

    def get_state_dir(self):
        return self.sessconfig['state_dir']

    def set_install_dir(self, installdir):
        self.sessconfig['install_dir'] = installdir

    def get_install_dir(self):
        return self.sessconfig['install_dir']

    def set_permid_keypair_filename(self, keypairfilename):
        self.sessconfig['eckeypairfilename'] = keypairfilename

    def get_permid_keypair_filename(self):
        return self.sessconfig['eckeypairfilename']

    def set_listen_port(self, port):
        self.sessconfig['minport'] = port
        self.sessconfig['maxport'] = port

    def get_listen_port(self):
        return self.sessconfig['minport']

    def set_ip_for_tracker(self, value):
        self.sessconfig['ip'] = value

    def get_ip_for_tracker(self):
        return self.sessconfig['ip']

    def set_bind_to_addresses(self, value):
        self.sessconfig['bind'] = value

    def get_bind_to_addresses(self):
        return self.sessconfig['bind']

    def set_upnp_mode(self, value):
        self.sessconfig['upnp_nat_access'] = value

    def get_upnp_mode(self):
        return self.sessconfig['upnp_nat_access']

    def set_autoclose_timeout(self, value):
        self.sessconfig['timeout'] = value

    def get_autoclose_timeout(self):
        return self.sessconfig['timeout']

    def set_autoclose_check_interval(self, value):
        self.sessconfig['timeout_check_interval'] = value

    def get_autoclose_check_interval(self):
        return self.sessconfig['timeout_check_interval']

    def set_max_socket_connections(self, value):
        self.sessconfig['max_socket_connects'] = value

    def get_max_socket_connections(self):
        return self.sessconfig['max_socket_connects']

    def set_megacache(self, value):
        self.sessconfig['megacache'] = value

    def get_megacache(self):
        return self.sessconfig['megacache']

    def set_overlay(self, value):
        self.sessconfig['overlay'] = value

    def get_overlay(self):
        return self.sessconfig['overlay']

    def set_overlay_max_message_length(self, value):
        self.sessconfig['overlay_max_message_length'] = value

    def get_overlay_max_message_length(self):
        return self.sessconfig['overlay_max_message_length']

    def set_buddycast(self, value):
        self.sessconfig['buddycast'] = value

    def get_buddycast(self):
        return self.sessconfig['buddycast']

    def set_start_recommender(self, value):
        self.sessconfig['start_recommender'] = value

    def get_start_recommender(self):
        return self.sessconfig['start_recommender']

    def set_buddycast_interval(self, value):
        self.sessconfig['buddycast_interval'] = value

    def get_buddycast_interval(self):
        return self.sessconfig['buddycast_interval']

    def set_buddycast_collecting_solution(self, value):
        self.sessconfig['buddycast_collecting_solution'] = value

    def get_buddycast_collecting_solution(self):
        return self.sessconfig['buddycast_collecting_solution']

    def set_buddycast_max_peers(self, value):
        self.sessconfig['buddycast_max_peers'] = value

    def get_buddycast_max_peers(self):
        return self.sessconfig['buddycast_max_peers']

    def set_download_help(self, value):
        self.sessconfig['download_help'] = value

    def get_download_help(self):
        return self.sessconfig['download_help']

    def set_download_help_dir(self, value):
        self.sessconfig['download_help_dir'] = value

    def get_download_help_dir(self):
        return self.sessconfig['download_help_dir']

    def set_proxyservice_status(self, value):
        if value == PROXYSERVICE_OFF or value == PROXYSERVICE_ON:
            self.sessconfig['proxyservice_status'] = value
        else:
            self.sessconfig['proxyservice_status'] = PROXYSERVICE_OFF

    def get_proxyservice_status(self):
        return self.sessconfig['proxyservice_status']

    def set_torrent_collecting(self, value):
        self.sessconfig['torrent_collecting'] = value

    def get_torrent_collecting(self):
        return self.sessconfig['torrent_collecting']

    def set_torrent_collecting_max_torrents(self, value):
        self.sessconfig['torrent_collecting_max_torrents'] = value

    def get_torrent_collecting_max_torrents(self):
        return self.sessconfig['torrent_collecting_max_torrents']

    def set_torrent_collecting_dir(self, value):
        self.sessconfig['torrent_collecting_dir'] = value

    def get_torrent_collecting_dir(self):
        return self.sessconfig['torrent_collecting_dir']

    def set_torrent_collecting_rate(self, value):
        self.sessconfig['torrent_collecting_rate'] = value

    def get_torrent_collecting_rate(self):
        return self.sessconfig['torrent_collecting_rate']

    def set_torrent_checking(self, value):
        self.sessconfig['torrent_checking'] = value

    def get_torrent_checking(self):
        return self.sessconfig['torrent_checking']

    def set_torrent_checking_period(self, value):
        self.sessconfig['torrent_checking_period'] = value

    def get_torrent_checking_period(self):
        return self.sessconfig['torrent_checking_period']

    def set_stop_collecting_threshold(self, value):
        self.sessconfig['stop_collecting_threshold'] = value

    def get_stop_collecting_threshold(self):
        return self.sessconfig['stop_collecting_threshold']

    def set_dialback(self, value):
        self.sessconfig['dialback'] = value

    def get_dialback(self):
        return self.sessconfig['dialback']

    def set_social_networking(self, value):
        self.sessconfig['socnet'] = value

    def get_social_networking(self):
        return self.sessconfig['socnet']

    def set_nickname(self, value):
        self.sessconfig['nickname'] = value

    def get_nickname(self):
        return self.sessconfig['nickname']

    def set_mugshot(self, value, mime = 'image/jpeg'):
        self.sessconfig['mugshot'] = (mime, value)

    def get_mugshot(self):
        if self.sessconfig['mugshot'] is None:
            return (None, None)
        else:
            return self.sessconfig['mugshot']

    def set_peer_icon_path(self, value):
        self.sessconfig['peer_icon_path'] = value

    def get_peer_icon_path(self):
        return self.sessconfig['peer_icon_path']

    def set_remote_query(self, value):
        self.sessconfig['rquery'] = value

    def get_remote_query(self):
        return self.sessconfig['rquery']

    def set_bartercast(self, value):
        self.sessconfig['bartercast'] = value

    def get_bartercast(self):
        return self.sessconfig['bartercast']

    def set_video_analyser_path(self, value):
        self.sessconfig['videoanalyserpath'] = value

    def get_video_analyser_path(self):
        return self.sessconfig['videoanalyserpath']

    def set_internal_tracker(self, value):
        self.sessconfig['internaltracker'] = value

    def get_internal_tracker(self):
        return self.sessconfig['internaltracker']

    def set_internal_tracker_url(self, value):
        self.sessconfig['tracker_url'] = value

    def get_internal_tracker_url(self):
        return self.sessconfig['tracker_url']

    def set_mainline_dht(self, value):
        self.sessconfig['mainline_dht'] = value

    def get_mainline_dht(self):
        return self.sessconfig['mainline_dht']

    def set_tracker_allowed_dir(self, value):
        self.sessconfig['tracker_allowed_dir'] = value

    def get_tracker_allowed_dir(self):
        return self.sessconfig['tracker_allowed_dir']

    def set_tracker_allowed_list(self, value):
        self.sessconfig['tracker_allowed_list'] = value

    def get_tracker_allowed_list(self):
        return self.sessconfig['tracker_allowed_list']

    def set_tracker_allowed_controls(self, value):
        self.sessconfig['tracker_allowed_controls'] = value

    def get_tracker_allowed_controls(self):
        return self.sessconfig['tracker_allowed_controls']

    def set_tracker_allowed_ips(self, value):
        self.sessconfig['tracker_allowed_ips'] = value

    def get_tracker_allowed_ips(self):
        return self.sessconfig['tracker_allowed_ips']

    def set_tracker_banned_ips(self, value):
        self.sessconfig['tracker_banned_ips'] = value

    def get_tracker_banned_ips(self):
        return self.sessconfig['tracker_banned_ips']

    def set_tracker_only_local_override_ip(self, value):
        self.sessconfig['tracker_only_local_override_ip'] = value

    def get_tracker_only_local_override_ip(self):
        return self.sessconfig['tracker_only_local_override_ip']

    def set_tracker_parse_dir_interval(self, value):
        self.sessconfig['tracker_parse_dir_interval'] = value

    def get_tracker_parse_dir_interval(self):
        return self.sessconfig['tracker_parse_dir_interval']

    def set_tracker_scrape_allowed(self, value):
        self.sessconfig['tracker_scrape_allowed'] = value

    def get_tracker_scrape_allowed(self):
        return self.sessconfig['tracker_scrape_allowed']

    def set_tracker_allow_get(self, value):
        self.sessconfig['tracker_allow_get'] = value

    def get_tracker_allow_get(self):
        return self.sessconfig['tracker_allow_get']

    def set_tracker_favicon(self, value):
        self.sessconfig['tracker_favicon'] = value

    def get_tracker_favicon(self):
        return self.sessconfig['tracker_favicon']

    def set_tracker_show_infopage(self, value):
        self.sessconfig['tracker_show_infopage'] = value

    def get_tracker_show_infopage(self):
        return self.sessconfig['tracker_show_infopage']

    def set_tracker_infopage_redirect(self, value):
        self.sessconfig['tracker_infopage_redirect'] = value

    def get_tracker_infopage_redirect(self):
        return self.sessconfig['tracker_infopage_redirect']

    def set_tracker_show_names(self, value):
        self.sessconfig['tracker_show_names'] = value

    def get_tracker_show_names(self):
        return self.sessconfig['tracker_show_names']

    def set_tracker_keep_dead(self, value):
        self.sessconfig['tracker_keep_dead'] = value

    def get_tracker_keep_dead(self):
        return self.sessconfig['tracker_keep_dead']

    def set_tracker_reannounce_interval(self, value):
        self.sessconfig['tracker_reannounce_interval'] = value

    def get_tracker_reannounce_interval(self):
        return self.sessconfig['tracker_reannounce_interval']

    def set_tracker_response_size(self, value):
        self.sessconfig['tracker_response_size'] = value

    def get_tracker_response_size(self):
        return self.sessconfig['tracker_response_size']

    def set_tracker_nat_check(self, value):
        self.sessconfig['tracker_nat_check'] = value

    def get_tracker_nat_check(self):
        return self.sessconfig['tracker_nat_check']

    def set_tracker_dfile(self, value):
        self.sessconfig['tracker_dfile'] = value

    def get_tracker_dfile(self):
        return self.sessconfig['tracker_dfile']

    def set_tracker_dfile_format(self, value):
        self.sessconfig['tracker_dfile_format'] = value

    def get_tracker_dfile_format(self):
        return self.sessconfig['tracker_dfile_format']

    def set_tracker_save_dfile_interval(self, value):
        self.sessconfig['tracker_save_dfile_interval'] = value

    def get_tracker_save_dfile_interval(self):
        return self.sessconfig['tracker_save_dfile_interval']

    def set_tracker_logfile(self, value):
        self.sessconfig['tracker_logfile'] = value

    def get_tracker_logfile(self):
        return self.sessconfig['tracker_logfile']

    def set_tracker_min_time_between_log_flushes(self, value):
        self.sessconfig['tracker_min_time_between_log_flushes'] = value

    def get_tracker_min_time_between_log_flushes(self):
        return self.sessconfig['tracker_min_time_between_log_flushes']

    def set_tracker_log_nat_checks(self, value):
        self.sessconfig['tracker_log_nat_checks'] = value

    def get_tracker_log_nat_checks(self):
        return self.sessconfig['tracker_log_nat_checks']

    def set_tracker_hupmonitor(self, value):
        self.sessconfig['tracker_hupmonitor'] = value

    def get_tracker_hupmonitor(self):
        return self.sessconfig['tracker_hupmonitor']

    def set_tracker_socket_timeout(self, value):
        self.sessconfig['tracker_socket_timeout'] = value

    def get_tracker_socket_timeout(self):
        return self.sessconfig['tracker_socket_timeout']

    def set_tracker_timeout_downloaders_interval(self, value):
        self.sessconfig['tracker_timeout_downloaders_interval'] = value

    def get_tracker_timeout_downloaders_interval(self):
        return self.sessconfig['tracker_timeout_downloaders_interval']

    def set_tracker_timeout_check_interval(self, value):
        self.sessconfig['tracker_timeout_check_interval'] = value

    def get_tracker_timeout_check_interval(self):
        return self.sessconfig['tracker_timeout_check_interval']

    def set_tracker_min_time_between_cache_refreshes(self, value):
        self.sessconfig['tracker_min_time_between_cache_refreshes'] = value

    def get_tracker_min_time_between_cache_refreshes(self):
        return self.sessconfig['tracker_min_time_between_cache_refreshes']

    def set_tracker_multitracker_enabled(self, value):
        self.sessconfig['tracker_multitracker_enabled'] = value

    def get_tracker_multitracker_enabled(self):
        return self.sessconfig['tracker_multitracker_enabled']

    def set_tracker_multitracker_allowed(self, value):
        self.sessconfig['tracker_multitracker_allowed'] = value

    def get_tracker_multitracker_allowed(self):
        return self.sessconfig['tracker_multitracker_allowed']

    def set_tracker_multitracker_reannounce_interval(self, value):
        self.sessconfig['tracker_multitracker_reannounce_interval'] = value

    def get_tracker_multitracker_reannounce_interval(self):
        return self.sessconfig['tracker_multitracker_reannounce_interval']

    def set_tracker_multitracker_maxpeers(self, value):
        self.sessconfig['tracker_multitracker_maxpeers'] = value

    def get_tracker_multitracker_maxpeers(self):
        return self.sessconfig['tracker_multitracker_maxpeers']

    def set_tracker_aggregate_forward(self, value):
        self.sessconfig['tracker_aggregate_forward'] = value

    def get_tracker_aggregate_forward(self):
        return self.sessconfig['tracker_aggregate_forward']

    def set_tracker_aggregator(self, value):
        self.sessconfig['tracker_aggregator'] = value

    def get_tracker_aggregator(self):
        return self.sessconfig['tracker_aggregator']

    def set_tracker_multitracker_http_timeout(self, value):
        self.sessconfig['tracker_multitracker_http_timeout'] = value

    def get_tracker_multitracker_http_timeout(self):
        return self.sessconfig['tracker_multitracker_http_timeout']

    def set_superpeer(self, value):
        self.sessconfig['superpeer'] = value

    def get_superpeer(self):
        return self.sessconfig['superpeer']

    def set_superpeer_file(self, value):
        self.sessconfig['superpeer_file'] = value

    def get_superpeer_file(self):
        return self.sessconfig['superpeer_file']

    def set_overlay_log(self, value):
        self.sessconfig['overlay_log'] = value

    def get_overlay_log(self):
        return self.sessconfig['overlay_log']

    def set_coopdlconfig(self, dscfg):
        c = dscfg.copy()
        self.sessconfig['coopdlconfig'] = c.dlconfig

    def get_coopdlconfig(self):
        dlconfig = self.sessconfig['coopdlconfig']
        if dlconfig is None:
            return
        else:
            from ACEStream.Core.DownloadConfig import DownloadStartupConfig
            return DownloadStartupConfig(dlconfig)

    def set_nat_detect(self, value):
        self.sessconfig['nat_detect'] = value

    def set_puncturing_internal_port(self, puncturing_internal_port):
        self.sessconfig['puncturing_internal_port'] = puncturing_internal_port

    def set_stun_servers(self, stun_servers):
        self.sessconfig['stun_servers'] = stun_servers

    def set_pingback_servers(self, pingback_servers):
        self.sessconfig['pingback_servers'] = pingback_servers

    def get_nat_detect(self):
        return self.sessconfig['nat_detect']

    def get_puncturing_internal_port(self):
        return self.sessconfig['puncturing_internal_port']

    def get_stun_servers(self):
        return self.sessconfig['stun_servers']

    def get_pingback_servers(self):
        return self.sessconfig['pingback_servers']

    def set_crawler(self, value):
        self.sessconfig['crawler'] = value

    def get_crawler(self):
        return self.sessconfig['crawler']

    def set_multicast_local_peer_discovery(self, value):
        self.sessconfig['multicast_local_peer_discovery'] = value

    def get_multicast_local_peer_discovery(self):
        return self.sessconfig['multicast_local_peer_discovery']

    def set_votecast_recent_votes(self, value):
        self.sessconfig['votecast_recent_votes'] = value

    def get_votecast_recent_votes(self):
        return self.sessconfig['votecast_recent_votes']

    def set_votecast_random_votes(self, value):
        self.sessconfig['votecast_random_votes'] = value

    def get_votecast_random_votes(self):
        return self.sessconfig['votecast_random_votes']

    def set_channelcast_recent_own_subscriptions(self, value):
        self.sessconfig['channelcast_recent_own_subscriptions'] = value

    def get_channelcast_recent_own_subscriptions(self):
        return self.sessconfig['channelcast_recent_own_subscriptions']

    def set_channelcast_random_own_subscriptions(self, value):
        self.sessconfig['channelcast_random_own_subscriptions'] = value

    def get_channelcast_random_own_subscriptions(self):
        return self.sessconfig['channelcast_random_own_subscriptions']

    def set_ts_login(self, value):
        self.sessconfig['ts_login'] = value

    def get_ts_login(self):
        return self.sessconfig['ts_login']

    def set_ts_password(self, value):
        self.sessconfig['ts_password'] = value

    def get_ts_password(self):
        return self.sessconfig['ts_password']

    def set_authlevel(self, value):
        self.sessconfig['authlevel'] = value

    def get_authlevel(self):
        return self.sessconfig['authlevel']

    def set_ts_user_key(self, value):
        self.sessconfig['ts_user_key'] = value

    def get_ts_user_key(self):
        return self.sessconfig['ts_user_key']

    def set_subtitles_collecting(self, value):
        self.sessconfig['subtitles_collecting'] = value

    def get_subtitles_collecting(self):
        return self.sessconfig['subtitles_collecting']

    def set_subtitles_collecting_dir(self, value):
        self.sessconfig['subtitles_collecting_dir'] = value

    def get_subtitles_collecting_dir(self):
        return self.sessconfig['subtitles_collecting_dir']

    def set_subtitles_upload_rate(self, value):
        self.sessconfig['subtitles_upload_rate'] = value

    def get_subtitles_upload_rate(self):
        return self.sessconfig['subtitles_upload_rate']

    def set_dispersy(self, value):
        self.sessconfig['dispersy'] = value

    def get_dispersy(self):
        return self.sessconfig['dispersy']

    def set_dispersy_port(self, value):
        self.sessconfig['dispersy_port'] = value

    def get_dispersy_port(self):
        return self.sessconfig['dispersy_port']


class SessionStartupConfig(SessionConfigInterface, Copyable, Serializable):

    def __init__(self, sessconfig = None):
        SessionConfigInterface.__init__(self, sessconfig)

    def load(filename):
        f = open(filename, 'rb')
        data = f.read()
        f.close()
#        key = '__tssecret|35k2j'
#        if TS_ENV_PLATFORM == 'windows':
#            data = AES_decrypt(data, key)
#        else:
#            data = m2_AES_decrypt(data, key)
        sessconfig = pickle.loads(data)
        sscfg = SessionStartupConfig(sessconfig)
        return sscfg

    load = staticmethod(load)

    def save(self, filename):
        data = pickle.dumps(self.sessconfig)
#        key = '__tssecret|35k2j'
#        if TS_ENV_PLATFORM == 'windows':
#            data = AES_encrypt(data, key)
#        else:
#            data = m2_AES_encrypt(data, key)
        f = open(filename, 'wb')
        f.write(data)
        f.close()

    def copy(self):
        config = copy.copy(self.sessconfig)
        return SessionStartupConfig(config)
