#Embedded file name: ACEStream\Core\DownloadConfig.pyo
import sys
import os
import copy
import pickle
from types import StringType
from traceback import print_exc
from ACEStream.Core.simpledefs import *
from ACEStream.Core.defaults import *
from ACEStream.Core.exceptions import *
from ACEStream.Core.Base import *
from ACEStream.Core.APIImplementation.miscutils import *
from ACEStream.Core.osutils import getfreespace, get_desktop_dir

class DownloadConfigInterface():

    def __init__(self, dlconfig = None):
        if dlconfig is not None:
            self.dlconfig = dlconfig
            return
        self.dlconfig = {}
        self.dlconfig.update(dldefaults)
        self.dlconfig['saveas'] = get_default_dest_dir()

    def set_dest_dir(self, path):
        self.dlconfig['saveas'] = path

    def get_dest_dir(self):
        return self.dlconfig['saveas']

    def set_dest_name(self, filename):
        self.dlconfig['saveas_filename'] = filename

    def get_dest_name(self):
        return self.dlconfig['saveas_filename']

    def set_files_priority(self, priority_list):
        try:
            li = []
            for p in priority_list:
                p = int(p)
                li.append(str(p))

            self.dlconfig['priority'] = ','.join(li)
        except:
            print >> sys.stderr, '>>>priority_list', priority_list
            print_exc()
            self.dlconfig['priority'] = ''

    def get_files_priority(self):
        plist = self.dlconfig['priority']
        if not plist:
            return []
        return [ int(p) for p in plist.split(',') ]

    def set_hidden(self, hidden):
        self.dlconfig['hidden'] = hidden

    def is_hidden(self):
        if 'hidden' in self.dlconfig:
            return self.dlconfig['hidden']
        else:
            return False

    def set_extra(self, key, value):
        self.dlconfig.setdefault('extra', {})[key] = value

    def get_extra(self, key, default = None):
        try:
            return self.dlconfig['extra'][key]
        except:
            return default

    def set_direct_download_url(self, value):
        self.dlconfig['direct_download_url'] = value

    def get_direct_download_url(self):
        if self.dlconfig.has_key('direct_download_url'):
            return self.dlconfig['direct_download_url']
        else:
            return None

    def set_download_finished_callback(self, callback):
        self.dlconfig['download_finished_callback'] = callback

    def get_download_finished_callback(self):
        if self.dlconfig.has_key('download_finished_callback'):
            return self.dlconfig['download_finished_callback']
        else:
            return None

    def set_predownload(self, predownload):
        self.dlconfig['predownload'] = predownload

    def get_predownload(self):
        return self.dlconfig.get('predownload', False)

    def set_download_failed_callback(self, callback):
        self.dlconfig['download_failed_callback'] = callback

    def get_download_failed_callback(self):
        if self.dlconfig.has_key('download_failed_callback'):
            return self.dlconfig['download_failed_callback']
        else:
            return None

    def set_video_event_callback(self, usercallback, dlmode = DLMODE_VOD):
        self.dlconfig['mode'] = dlmode
        self.dlconfig['vod_usercallback'] = usercallback

    def set_video_events(self, events = []):
        self.dlconfig['vod_userevents'] = events[:]

    def set_video_source(self, videosource, authconfig = None, restartstatefilename = None):
        self.dlconfig['video_source'] = videosource
        if authconfig is None:
            from ACEStream.Core.LiveSourceAuthConfig import LiveSourceAuthConfig
            authconfig = LiveSourceAuthConfig(LIVE_AUTHMETHOD_NONE)
        self.dlconfig['video_source_authconfig'] = authconfig
        self.dlconfig['video_source_restartstatefilename'] = restartstatefilename

    def set_video_ratelimit(self, ratelimit):
        self.dlconfig['video_ratelimit'] = ratelimit

    def set_mode(self, mode):
        self.dlconfig['mode'] = mode

    def set_live_aux_seeders(self, seeders):
        self.dlconfig['live_aux_seeders'] = seeders

    def get_mode(self):
        return self.dlconfig['mode']

    def get_video_event_callback(self):
        return self.dlconfig['vod_usercallback']

    def get_video_events(self):
        return self.dlconfig['vod_userevents']

    def get_video_source(self):
        return self.dlconfig['video_source']

    def get_video_ratelimit(self):
        return self.dlconfig['video_ratelimit']

    def get_live_aux_seeders(self):
        return self.dlconfig['live_aux_seeders']

    def set_selected_files(self, files):
        if type(files) == StringType:
            files = [files]
        if self.dlconfig['mode'] == DLMODE_VOD and len(files) > 1:
            raise ValueError('In Video-On-Demand mode only 1 file can be selected for download')
        elif self.dlconfig['mode'] == DLMODE_SVC and len(files) < 2:
            raise ValueError('In SVC Video-On-Demand mode at least 2 files have to be selected for download')
        self.dlconfig['selected_files'] = files

    def set_extra_files(self, extra_files):
        self.dlconfig['extra_files'] = extra_files

    def set_auto_download_limit(self, value):
        self.dlconfig['auto_download_limit'] = value

    def get_auto_download_limit(self):
        return self.dlconfig['auto_download_limit']

    def set_wait_sufficient_speed(self, value):
        self.dlconfig['wait_sufficient_speed'] = value

    def get_wait_sufficient_speed(self):
        return self.dlconfig['wait_sufficient_speed']

    def set_http_support(self, value):
        self.dlconfig['enable_http_support'] = value

    def get_http_support(self):
        return self.dlconfig['enable_http_support']

    def get_selected_files(self):
        return self.dlconfig['selected_files']

    def set_max_speed(self, direct, speed, auto_limit = False):
        if direct == UPLOAD:
            self.dlconfig['max_upload_rate'] = speed
        else:
            self.dlconfig['max_download_rate'] = speed
            self.dlconfig['auto_download_limit'] = auto_limit

    def get_max_speed(self, direct):
        if direct == UPLOAD:
            return self.dlconfig['max_upload_rate']
        else:
            return self.dlconfig['max_download_rate']

    def set_player_buffer_time(self, value):
        self.dlconfig['player_buffer_time'] = value

    def get_player_buffer_time(self):
        return self.dlconfig['player_buffer_time']

    def set_live_buffer_time(self, value):
        self.dlconfig['live_buffer_time'] = value

    def get_live_buffer_time(self):
        return self.dlconfig['live_buffer_time']

    def set_max_conns_to_initiate(self, nconns):
        self.dlconfig['max_initiate'] = nconns

    def get_max_conns_to_initiate(self):
        return self.dlconfig['max_initiate']

    def set_max_conns(self, nconns):
        self.dlconfig['max_connections'] = nconns

    def get_max_conns(self):
        return self.dlconfig['max_connections']

    def get_coopdl_role(self):
        return self.dlconfig['coopdl_role']

    def set_coopdl_coordinator_permid(self, permid):
        self.dlconfig['coopdl_role'] = COOPDL_ROLE_HELPER
        self.dlconfig['coopdl_coordinator_permid'] = permid

    def get_coopdl_coordinator_permid(self):
        return self.dlconfig['coopdl_coordinator_permid']

    def set_proxy_mode(self, value):
        if value == PROXY_MODE_OFF or value == PROXY_MODE_PRIVATE or value == PROXY_MODE_SPEED:
            self.dlconfig['proxy_mode'] = value
        else:
            self.dlconfig['proxy_mode'] = PROXY_MODE_OFF

    def get_proxy_mode(self):
        return self.dlconfig['proxy_mode']

    def set_no_helpers(self, value):
        if value >= 0:
            self.dlconfig['max_helpers'] = value
        else:
            self.dlconfig['max_helpers'] = 0

    def get_no_helpers(self):
        return self.dlconfig['max_helpers']

    def set_max_uploads(self, value):
        self.dlconfig['max_uploads'] = value

    def get_max_uploads(self):
        return self.dlconfig['max_uploads']

    def set_keepalive_interval(self, value):
        self.dlconfig['keepalive_interval'] = value

    def get_keepalive_interval(self):
        return self.dlconfig['keepalive_interval']

    def set_download_slice_size(self, value):
        self.dlconfig['download_slice_size'] = value

    def get_download_slice_size(self):
        return self.dlconfig['download_slice_size']

    def set_upload_unit_size(self, value):
        self.dlconfig['upload_unit_size'] = value

    def get_upload_unit_size(self):
        return self.dlconfig['upload_unit_size']

    def set_request_backlog(self, value):
        self.dlconfig['request_backlog'] = value

    def get_request_backlog(self):
        return self.dlconfig['request_backlog']

    def set_max_message_length(self, value):
        self.dlconfig['max_message_length'] = value

    def get_max_message_length(self):
        return self.dlconfig['max_message_length']

    def set_max_slice_length(self, value):
        self.dlconfig['max_slice_length'] = value

    def get_max_slice_length(self):
        return self.dlconfig['max_slice_length']

    def set_max_rate_period(self, value):
        self.dlconfig['max_rate_period'] = value

    def get_max_rate_period(self):
        return self.dlconfig['max_rate_period']

    def set_upload_rate_fudge(self, value):
        self.dlconfig['upload_rate_fudge'] = value

    def get_upload_rate_fudge(self):
        return self.dlconfig['upload_rate_fudge']

    def set_tcp_ack_fudge(self, value):
        self.dlconfig['tcp_ack_fudge'] = value

    def get_tcp_ack_fudge(self):
        return self.dlconfig['tcp_ack_fudge']

    def set_rerequest_interval(self, value):
        self.dlconfig['rerequest_interval'] = value

    def get_rerequest_interval(self):
        return self.dlconfig['rerequest_interval']

    def set_min_peers(self, value):
        self.dlconfig['min_peers'] = value

    def get_min_peers(self):
        return self.dlconfig['min_peers']

    def set_http_timeout(self, value):
        self.dlconfig['http_timeout'] = value

    def get_http_timeout(self):
        return self.dlconfig['http_timeout']

    def set_check_hashes(self, value):
        self.dlconfig['check_hashes'] = value

    def get_check_hashes(self):
        return self.dlconfig['check_hashes']

    def set_alloc_type(self, value):
        self.dlconfig['alloc_type'] = value

    def get_alloc_type(self):
        return self.dlconfig['alloc_type']

    def set_alloc_rate(self, value):
        self.dlconfig['alloc_rate'] = value

    def get_alloc_rate(self):
        return self.dlconfig['alloc_rate']

    def set_buffer_reads(self, value):
        self.dlconfig['buffer_reads'] = value

    def get_buffer_reads(self):
        return self.dlconfig['buffer_reads']

    def set_write_buffer_size(self, value):
        self.dlconfig['write_buffer_size'] = value

    def get_write_buffer_size(self):
        return self.dlconfig['write_buffer_size']

    def set_breakup_seed_bitfield(self, value):
        self.dlconfig['breakup_seed_bitfield'] = value

    def get_breakup_seed_bitfield(self):
        return self.dlconfig['breakup_seed_bitfield']

    def set_snub_time(self, value):
        self.dlconfig['snub_time'] = value

    def get_snub_time(self):
        return self.dlconfig['snub_time']

    def set_rarest_first_cutoff(self, value):
        self.dlconfig['rarest_first_cutoff'] = value

    def get_rarest_first_cutoff(self):
        return self.dlconfig['rarest_first_cutoff']

    def set_rarest_first_priority_cutoff(self, value):
        self.dlconfig['rarest_first_priority_cutoff'] = value

    def get_rarest_first_priority_cutoff(self):
        return self.dlconfig['rarest_first_priority_cutoff']

    def set_min_uploads(self, value):
        self.dlconfig['min_uploads'] = value

    def get_min_uploads(self):
        return self.dlconfig['min_uploads']

    def set_max_files_open(self, value):
        self.dlconfig['max_files_open'] = value

    def get_max_files_open(self):
        return self.dlconfig['max_files_open']

    def set_round_robin_period(self, value):
        self.dlconfig['round_robin_period'] = value

    def get_round_robin_period(self):
        return self.dlconfig['round_robin_period']

    def set_super_seeder(self, value):
        self.dlconfig['super_seeder'] = value

    def get_super_seeder(self):
        return self.dlconfig['super_seeder']

    def set_security(self, value):
        self.dlconfig['security'] = value

    def get_security(self):
        return self.dlconfig['security']

    def set_auto_kick(self, value):
        self.dlconfig['auto_kick'] = value

    def get_auto_kick(self):
        return self.dlconfig['auto_kick']

    def set_double_check_writes(self, value):
        self.dlconfig['double_check'] = value

    def get_double_check_writes(self):
        return self.dlconfig['double_check']

    def set_triple_check_writes(self, value):
        self.dlconfig['triple_check'] = value

    def get_triple_check_writes(self):
        return self.dlconfig['triple_check']

    def set_lock_files(self, value):
        self.dlconfig['lock_files'] = value

    def get_lock_files(self):
        return self.dlconfig['lock_files']

    def set_lock_while_reading(self, value):
        self.dlconfig['lock_while_reading'] = value

    def get_lock_while_reading(self):
        return self.dlconfig['lock_while_reading']

    def set_auto_flush(self, value):
        self.dlconfig['auto_flush'] = value

    def get_auto_flush(self):
        return self.dlconfig['auto_flush']

    def set_exclude_ips(self, value):
        self.dlconfig['exclude_ips'] = value

    def get_exclude_ips(self):
        return self.dlconfig['exclude_ips']

    def set_ut_pex_max_addrs_from_peer(self, value):
        self.dlconfig['ut_pex_max_addrs_from_peer'] = value

    def get_ut_pex_max_addrs_from_peer(self):
        return self.dlconfig['ut_pex_max_addrs_from_peer']

    def set_poa(self, poa):
        if poa:
            from base64 import encodestring
            self.dlconfig['poa'] = encodestring(poa.serialize()).replace('\n', '')
            import sys
            print >> sys.stderr, 'POA is set:', self.dlconfig['poa']

    def get_poa(self):
        if 'poa' in self.dlconfig:
            if not self.dlconfig['poa']:
                raise Exception('No POA specified')
            from ACEStream.Core.ClosedSwarm import ClosedSwarm
            from base64 import decodestring
            print >> sys.stderr, 'get_poa:', self.dlconfig['poa']
            poa = ClosedSwarm.POA.deserialize(decodestring(self.dlconfig['poa']))
            return poa

    def set_same_nat_try_internal(self, value):
        self.dlconfig['same_nat_try_internal'] = value

    def get_same_nat_try_internal(self):
        return self.dlconfig['same_nat_try_internal']

    def set_unchoke_bias_for_internal(self, value):
        self.dlconfig['unchoke_bias_for_internal'] = value

    def get_unchoke_bias_for_internal(self):
        return self.dlconfig['unchoke_bias_for_internal']


class DownloadStartupConfig(DownloadConfigInterface, Serializable, Copyable):

    def __init__(self, dlconfig = None):
        DownloadConfigInterface.__init__(self, dlconfig)

    def load(filename):
        f = open(filename, 'rb')
        dlconfig = pickle.load(f)
        dscfg = DownloadStartupConfig(dlconfig)
        f.close()
        return dscfg

    load = staticmethod(load)

    def save(self, filename):
        f = open(filename, 'wb')
        pickle.dump(self.dlconfig, f)
        f.close()

    def copy(self):
        config = copy.copy(self.dlconfig)
        return DownloadStartupConfig(config)


def get_default_dest_dir():
    uhome = get_desktop_dir()
    return os.path.join(uhome, u'ACEStreamDownloads')
