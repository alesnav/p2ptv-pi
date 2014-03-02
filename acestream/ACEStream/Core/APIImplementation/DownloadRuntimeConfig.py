#Embedded file name: ACEStream\Core\APIImplementation\DownloadRuntimeConfig.pyo
import sys
import binascii
from ACEStream.Core.simpledefs import *
from ACEStream.Core.DownloadConfig import DownloadConfigInterface
from ACEStream.Core.exceptions import OperationNotPossibleAtRuntimeException
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False

class DownloadRuntimeConfig(DownloadConfigInterface):

    def set_max_speed(self, direct, speed, auto_limit = False):
        if DEBUG:
            log('DownloadRuntimeConfig::set_max_speed:', binascii.hexlify(self.get_hash()), direct, speed, auto_limit)
        self.dllock.acquire()
        try:
            if self.sd is not None:
                set_max_speed_lambda = lambda : self.sd is not None and self.sd.set_max_speed(direct, speed, auto_limit)
                self.session.lm.rawserver.add_task(set_max_speed_lambda, 0)
            DownloadConfigInterface.set_max_speed(self, direct, speed, auto_limit)
        finally:
            self.dllock.release()

    def get_max_speed(self, direct):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_max_speed(self, direct)
        finally:
            self.dllock.release()

    def set_player_buffer_time(self, value):
        if DEBUG:
            log('DownloadRuntimeConfig::set_player_buffer_time', binascii.hexlify(self.get_hash()), value)
        self.dllock.acquire()
        try:
            if self.sd is not None:
                set_player_buffer_time_lambda = lambda : self.sd is not None and self.sd.set_player_buffer_time(value)
                self.session.lm.rawserver.add_task(set_player_buffer_time_lambda, 0)
            if self.dd is not None:
                set_player_buffer_time_lambda = lambda : self.dd is not None and self.dd.set_player_buffer_time(value)
                self.session.lm.rawserver.add_task(set_player_buffer_time_lambda, 0)
            DownloadConfigInterface.set_player_buffer_time(self, value)
        finally:
            self.dllock.release()

    def get_player_buffer_time(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_player_buffer_time(self)
        finally:
            self.dllock.release()

    def set_live_buffer_time(self, value):
        if DEBUG:
            log('DownloadRuntimeConfig::set_live_buffer_time', binascii.hexlify(self.get_hash()), value)
        self.dllock.acquire()
        try:
            if self.sd is not None:
                set_live_buffer_time_lambda = lambda : self.sd is not None and self.sd.set_live_buffer_time(value)
                self.session.lm.rawserver.add_task(set_live_buffer_time_lambda, 0)
            if self.dd is not None:
                set_live_buffer_time_lambda = lambda : self.dd is not None and self.dd.set_live_buffer_time(value)
                self.session.lm.rawserver.add_task(set_live_buffer_time_lambda, 0)
            DownloadConfigInterface.set_live_buffer_time(self, value)
        finally:
            self.dllock.release()

    def get_live_buffer_time(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_live_buffer_time(self)
        finally:
            self.dllock.release()

    def set_wait_sufficient_speed(self, value):
        if DEBUG:
            log('DownloadRuntimeConfig::set_wait_sufficient_speed:', binascii.hexlify(self.get_hash()), value)
        self.dllock.acquire()
        try:
            if self.sd is not None:
                set_wait_sufficient_speed_lambda = lambda : self.sd is not None and self.sd.set_wait_sufficient_speed(value)
                self.session.lm.rawserver.add_task(set_wait_sufficient_speed_lambda, 0)
            if self.dd is not None:
                set_wait_sufficient_speed_lambda = lambda : self.dd is not None and self.dd.set_wait_sufficient_speed(value)
                self.session.lm.rawserver.add_task(set_wait_sufficient_speed_lambda, 0)
            DownloadConfigInterface.set_wait_sufficient_speed(self, value)
        finally:
            self.dllock.release()

    def get_wait_sufficient_speed(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_wait_sufficient_speed(self)
        finally:
            self.dllock.release()

    def get_auto_download_limit(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_auto_download_limit(self)
        finally:
            self.dllock.release()

    def get_http_support(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_http_support(self)
        finally:
            self.dllock.release()

    def is_hidden(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.is_hidden(self)
        finally:
            self.dllock.release()

    def set_hidden(self, hidden):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_hidden(self, hidden)
        finally:
            self.dllock.release()

    def get_extra(self, key, default = None):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_extra(self, key, default)
        finally:
            self.dllock.release()

    def set_extra(self, key, value):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_extra(self, key, value)
        finally:
            self.dllock.release()

    def set_direct_download_url(self, value):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_direct_download_url(self, value)
        finally:
            self.dllock.release()

    def set_download_finished_callback(self, value):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_download_finished_callback(self, value)
        finally:
            self.dllock.release()

    def set_download_failed_callback(self, value):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_download_failed_callback(self, value)
        finally:
            self.dllock.release()

    def set_predownload(self, value):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_predownload(self, value)
        finally:
            self.dllock.release()

    def get_files_priority(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_files_priority(self)
        finally:
            self.dllock.release()

    def set_files_priority(self, priority_list):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_files_priority(self, priority_list)
        finally:
            self.dllock.release()

    def set_dest_dir(self, path):
        raise OperationNotPossibleAtRuntimeException()

    def set_video_event_callback(self, usercallback, dlmode = DLMODE_VOD):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_video_event_callback(self, usercallback, dlmode=dlmode)
        finally:
            self.dllock.release()

    def set_video_events(self, events):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_video_events(self, events)
        finally:
            self.dllock.release()

    def set_mode(self, mode):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_mode(self, mode)
        finally:
            self.dllock.release()

    def get_mode(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_mode(self)
        finally:
            self.dllock.release()

    def get_video_event_callback(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_video_event_callback(self)
        finally:
            self.dllock.release()

    def get_video_events(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_video_events(self)
        finally:
            self.dllock.release()

    def set_selected_files(self, files):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_selected_files(self, files)
            self.set_filepieceranges(self.tdef.get_metainfo())
        finally:
            self.dllock.release()

    def set_extra_files(self, extra_files):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_extra_files(self, extra_files)
        finally:
            self.dllock.release()

    def get_selected_files(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_selected_files(self)
        finally:
            self.dllock.release()

    def set_max_conns_to_initiate(self, nconns):
        self.dllock.acquire()
        try:
            if self.sd is not None:
                set_max_conns2init_lambda = lambda : self.sd is not None and self.sd.set_max_conns_to_initiate(nconns, None)
                self.session.lm.rawserver.add_task(set_max_conns2init_lambda, 0.0)
            DownloadConfigInterface.set_max_conns_to_initiate(self, nconns)
        finally:
            self.dllock.release()

    def get_max_conns_to_initiate(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_max_conns_to_initiate(self)
        finally:
            self.dllock.release()

    def set_max_conns(self, nconns):
        self.dllock.acquire()
        try:
            if self.sd is not None:
                set_max_conns_lambda = lambda : self.sd is not None and self.sd.set_max_conns(nconns, None)
                self.session.lm.rawserver.add_task(set_max_conns_lambda, 0.0)
            DownloadConfigInterface.set_max_conns(self, nconns)
        finally:
            self.dllock.release()

    def get_max_conns(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_max_conns(self)
        finally:
            self.dllock.release()

    def set_max_uploads(self, value):
        self.dllock.acquire()
        try:
            if self.sd is not None:
                set_max_uploads_lambda = lambda : self.sd is not None and self.sd.set_max_uploads(value)
                self.session.lm.rawserver.add_task(set_max_uploads_lambda, 0.0)
            DownloadConfigInterface.set_max_uploads(self, value)
        finally:
            self.dllock.release()

    def get_max_uploads(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_max_uploads(self)
        finally:
            self.dllock.release()

    def set_keepalive_interval(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_keepalive_interval(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_keepalive_interval(self)
        finally:
            self.dllock.release()

    def set_download_slice_size(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_download_slice_size(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_download_slice_size(self)
        finally:
            self.dllock.release()

    def set_upload_unit_size(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_upload_unit_size(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_upload_unit_size(self)
        finally:
            self.dllock.release()

    def set_request_backlog(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_request_backlog(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_request_backlog(self)
        finally:
            self.dllock.release()

    def set_max_message_length(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_max_message_length(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_max_message_length(self)
        finally:
            self.dllock.release()

    def set_max_slice_length(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_max_slice_length(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_max_slice_length(self)
        finally:
            self.dllock.release()

    def set_max_rate_period(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_max_rate_period(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_max_rate_period(self)
        finally:
            self.dllock.release()

    def set_upload_rate_fudge(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_upload_rate_fudge(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_upload_rate_fudge(self)
        finally:
            self.dllock.release()

    def set_tcp_ack_fudge(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_tcp_ack_fudge(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_tcp_ack_fudge(self)
        finally:
            self.dllock.release()

    def set_rerequest_interval(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_rerequest_interval(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_rerequest_interval(self)
        finally:
            self.dllock.release()

    def set_min_peers(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_min_peers(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_min_peers(self)
        finally:
            self.dllock.release()

    def set_http_timeout(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_http_timeout(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_http_timeout(self)
        finally:
            self.dllock.release()

    def set_check_hashes(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_check_hashes(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_check_hashes(self)
        finally:
            self.dllock.release()

    def set_alloc_type(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_alloc_type(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_alloc_type(self)
        finally:
            self.dllock.release()

    def set_alloc_rate(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_alloc_rate(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_alloc_rate(self)
        finally:
            self.dllock.release()

    def set_buffer_reads(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_buffer_reads(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_buffer_reads(self)
        finally:
            self.dllock.release()

    def set_write_buffer_size(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_write_buffer_size(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_write_buffer_size(self)
        finally:
            self.dllock.release()

    def set_breakup_seed_bitfield(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_breakup_seed_bitfield(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_breakup_seed_bitfield(self)
        finally:
            self.dllock.release()

    def set_snub_time(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_snub_time(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_snub_time(self)
        finally:
            self.dllock.release()

    def set_rarest_first_cutoff(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_rarest_first_cutoff(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_rarest_first_cutoff(self)
        finally:
            self.dllock.release()

    def set_rarest_first_priority_cutoff(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_rarest_first_priority_cutoff(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_rarest_first_priority_cutoff(self)
        finally:
            self.dllock.release()

    def set_min_uploads(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_min_uploads(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_min_uploads(self)
        finally:
            self.dllock.release()

    def set_max_files_open(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_max_files_open(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_max_files_open(self)
        finally:
            self.dllock.release()

    def set_round_robin_period(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_round_robin_period(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_round_robin_period(self)
        finally:
            self.dllock.release()

    def set_super_seeder(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_super_seeder(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_super_seeder(self)
        finally:
            self.dllock.release()

    def set_security(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_security(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_security(self)
        finally:
            self.dllock.release()

    def set_auto_kick(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_auto_kick(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_auto_kick(self)
        finally:
            self.dllock.release()

    def set_double_check_writes(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_double_check_writes(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_double_check_writes(self)
        finally:
            self.dllock.release()

    def set_triple_check_writes(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_triple_check_writes(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_triple_check_writes(self)
        finally:
            self.dllock.release()

    def set_lock_files(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_lock_files(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_lock_files(self)
        finally:
            self.dllock.release()

    def set_lock_while_reading(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_lock_while_reading(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_lock_while_reading(self)
        finally:
            self.dllock.release()

    def set_auto_flush(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_auto_flush(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_auto_flush(self)
        finally:
            self.dllock.release()

    def set_exclude_ips(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_exclude_ips(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_exclude_ips(self)
        finally:
            self.dllock.release()

    def set_ut_pex_max_addrs_from_peer(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_ut_pex_max_addrs_from_peer(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_ut_pex_max_addrs_from_peer(self)
        finally:
            self.dllock.release()

    def set_poa(self, poa):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_poa(self, poa)
        finally:
            self.dllock.release()

    def get_poa(self, poa):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_poa(self)
        finally:
            self.dllock.release()

    def set_same_nat_try_internal(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_same_nat_try_internal(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_same_nat_try_internal(self)
        finally:
            self.dllock.release()

    def set_unchoke_bias_for_internal(self, value):
        raise OperationNotPossibleAtRuntimeException()

    def get_unchoke_bias_for_internal(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_unchoke_bias_for_internal(self)
        finally:
            self.dllock.release()

    def set_proxy_mode(self, value):
        self.dllock.acquire()
        try:
            DownloadConfigInterface.set_proxy_mode(self, value)
        finally:
            self.dllock.release()

    def get_proxy_mode(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_proxy_mode(self)
        finally:
            self.dllock.release()

    def set_no_helpers(self, value):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.set_no_helpers(self, value)
        finally:
            self.dllock.release()

    def get_no_helpers(self):
        self.dllock.acquire()
        try:
            return DownloadConfigInterface.get_no_helpers(self)
        finally:
            self.dllock.release()
