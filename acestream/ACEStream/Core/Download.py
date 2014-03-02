#Embedded file name: ACEStream\Core\Download.pyo
import sys
from traceback import print_exc, print_stack
from ACEStream.Core.simpledefs import *
from ACEStream.Core.defaults import *
from ACEStream.Core.exceptions import *
from ACEStream.Core.Base import *
from ACEStream.Core.APIImplementation.DownloadRuntimeConfig import DownloadRuntimeConfig
from ACEStream.Core.APIImplementation.DownloadImpl import DownloadImpl
from ACEStream.Core.APIImplementation.miscutils import *
from ACEStream.Core.osutils import *

class Download(DownloadRuntimeConfig, DownloadImpl):

    def __init__(self, dltype, session, tdef = None, main_url = None):
        DownloadImpl.__init__(self, dltype, session, tdef, main_url)

    def get_def(self):
        return DownloadImpl.get_def(self)

    def got_duration(self, duration, from_player = True):
        DownloadImpl.got_duration(self, duration, from_player)

    def got_metadata(self, metadata):
        DownloadImpl.got_metadata(self, metadata)

    def got_http_seeds(self, http_seeds):
        DownloadImpl.got_http_seeds(self, http_seeds)

    def set_state_callback(self, usercallback, getpeerlist = False):
        DownloadImpl.set_state_callback(self, usercallback, getpeerlist=getpeerlist)

    def stop(self):
        DownloadImpl.stop(self)

    def pause(self, pause, close_connections = False):
        DownloadImpl.pause(self, pause, close_connections)

    def restart(self, initialdlstatus = None, new_tdef = None):
        DownloadImpl.restart(self, initialdlstatus, new_tdef)

    def set_max_desired_speed(self, direct, speed):
        DownloadImpl.set_max_desired_speed(self, direct, speed)

    def get_max_desired_speed(self, direct):
        return DownloadImpl.get_max_desired_speed(self, direct)

    def get_dest_files(self, exts = None, get_all = False):
        return DownloadImpl.get_dest_files(self, exts, get_all)

    def ask_coopdl_helpers(self, permidlist):
        self.dllock.acquire()
        try:
            peerreclist = self.session.lm.peer_db.getPeers(permidlist, ['permid', 'ip', 'port'])
            if self.sd is not None:
                ask_coopdl_helpers_lambda = lambda : self.sd is not None and self.sd.ask_coopdl_helpers(peerreclist)
                self.session.lm.rawserver.add_task(ask_coopdl_helpers_lambda, 0)
            else:
                raise OperationNotPossibleWhenStoppedException()
        finally:
            self.dllock.release()

    def stop_coopdl_helpers(self, permidlist):
        self.dllock.acquire()
        try:
            peerreclist = self.session.lm.peer_db.getPeers(permidlist, ['permid', 'ip', 'port'])
            if self.sd is not None:
                stop_coopdl_helpers_lambda = lambda : self.sd is not None and self.sd.stop_coopdl_helpers(peerreclist)
                self.session.lm.rawserver.add_task(stop_coopdl_helpers_lambda, 0)
            else:
                raise OperationNotPossibleWhenStoppedException()
        finally:
            self.dllock.release()

    def set_seeding_policy(self, smanager):
        self.dllock.acquire()
        try:
            if self.sd is not None:
                set_seeding_smanager_lambda = lambda : self.sd is not None and self.sd.get_bt1download().choker.set_seeding_manager(smanager)
                self.session.lm.rawserver.add_task(set_seeding_smanager_lambda, 0)
            else:
                raise OperationNotPossibleWhenStoppedException()
        finally:
            self.dllock.release()

    def get_peer_id(self):
        self.dllock.acquire()
        try:
            if self.sd is not None:
                return self.sd.peerid
            return
        finally:
            self.dllock.release()
