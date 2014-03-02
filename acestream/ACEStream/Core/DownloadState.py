#Embedded file name: ACEStream\Core\DownloadState.pyo
import time
import sys
from traceback import print_exc, print_stack
from ACEStream.Core.simpledefs import *
from ACEStream.Core.defaults import *
from ACEStream.Core.exceptions import *
from ACEStream.Core.Base import *
from ACEStream.Core.DecentralizedTracking.repex import REPEX_SWARMCACHE_SIZE
DEBUG = False

class DownloadState(Serializable):

    def __init__(self, download, status, error, progress, stats = None, filepieceranges = None, logmsgs = None, coopdl_helpers = [], coopdl_coordinator = None, peerid = None, videoinfo = None, swarmcache = None, paused = False, files_completed = None):
        self.download = download
        self.filepieceranges = filepieceranges
        self.logmsgs = logmsgs
        self.vod_status_msg = None
        self.coopdl_helpers = coopdl_helpers
        self.coopdl_coordinator = coopdl_coordinator
        self.dltype = self.download.get_type()
        self.paused = paused
        self.files_completed = files_completed
        if swarmcache is not None:
            self.swarmcache = dict(swarmcache)
        else:
            self.swarmcache = None
        self.time = time.time()
        if stats is None:
            self.error = error
            self.progress = progress
            if self.error is not None:
                self.status = DLSTATUS_STOPPED_ON_ERROR
            else:
                self.status = status
            self.stats = None
        elif error is not None:
            self.error = error
            self.progress = 0.0
            self.status = DLSTATUS_STOPPED_ON_ERROR
            self.stats = None
        elif status is not None and status != DLSTATUS_REPEXING:
            self.error = error
            self.status = status
            if self.status == DLSTATUS_WAITING4HASHCHECK:
                self.progress = 0.0
            else:
                self.progress = stats['frac']
            self.stats = None
        else:
            self.error = None
            self.progress = stats['frac']
            if stats['frac'] == 1.0:
                self.status = DLSTATUS_SEEDING
            else:
                self.status = DLSTATUS_DOWNLOADING
            self.stats = stats
            if self.dltype == DLTYPE_DIRECT:
                self.haveslice = None
            elif self.dltype == DLTYPE_TORRENT:
                statsobj = self.stats['stats']
                if self.filepieceranges is None:
                    self.haveslice = statsobj.have
                else:
                    totalpieces = 0
                    for t, tl, f in self.filepieceranges:
                        diff = tl - t
                        totalpieces += diff

                    haveslice = [False] * totalpieces
                    haveall = True
                    index = 0
                    for t, tl, f in self.filepieceranges:
                        for piece in range(t, tl):
                            haveslice[index] = statsobj.have[piece]
                            if haveall and haveslice[index] == False:
                                haveall = False
                            index += 1

                    self.haveslice = haveslice
            if status is not None and status == DLSTATUS_REPEXING:
                self.status = DLSTATUS_REPEXING

    def get_download(self):
        return self.download

    def get_progress(self):
        return self.progress

    def get_files_completed(self):
        if self.stats is None:
            return self.files_completed
        try:
            return self.stats['stats'].filecomplete[:]
        except AttributeError:
            if self.status == DLSTATUS_SEEDING:
                filecomplete = [True]
            else:
                filecomplete = [False]
            return filecomplete

    def get_status(self):
        return self.status

    def get_error(self):
        return self.error

    def get_paused(self):
        return self.paused

    def get_current_speed(self, direct, bytes = False):
        if self.stats is None:
            return 0.0
        if direct == UPLOAD:
            speed = self.stats['up']
        else:
            speed = self.stats['down']
        if not bytes:
            speed /= 1024.0
        return speed

    def get_http_speed(self):
        if self.stats is None:
            return 0.0
        return self.stats['httpdown'] / 1024.0

    def get_total_transferred(self, direct):
        if self.stats is None:
            return 0L
        elif direct == UPLOAD:
            return self.stats['stats'].upTotal
        else:
            return self.stats['stats'].downTotal

    def get_http_transferred(self):
        if self.stats is None:
            return 0L
        return self.stats['stats'].httpDownTotal

    def get_eta(self):
        if self.stats is None:
            return 0.0
        else:
            return self.stats['time']

    def get_num_con_candidates(self):
        if self.stats is None:
            return 0
        if self.dltype != DLTYPE_TORRENT:
            return 0
        statsobj = self.stats['stats']
        return statsobj.numConCandidates

    def get_num_con_initiated(self):
        if self.stats is None:
            return 0
        if self.dltype != DLTYPE_TORRENT:
            return 0
        statsobj = self.stats['stats']
        return statsobj.numConInitiated

    def get_num_peers(self):
        if self.stats is None:
            return 0
        statsobj = self.stats['stats']
        return statsobj.numSeeds + statsobj.numPeers

    def get_http_peers(self):
        if self.stats is None:
            return 0
        return self.stats['stats'].httpSeeds

    def get_num_nonseeds(self):
        if self.stats is None:
            return 0
        statsobj = self.stats['stats']
        return statsobj.numPeers

    def get_num_seeds_peers(self):
        if self.stats is None or not self.stats.has_key('spew') or self.stats['spew'] is None:
            return (None, None)
        total = len(self.stats['spew'])
        seeds = len([ i for i in self.stats['spew'] if i['completed'] == 1.0 ])
        return (seeds, total - seeds)

    def get_pieces_complete(self):
        if self.stats is None:
            return []
        elif self.haveslice is None:
            return []
        else:
            return self.haveslice

    def get_vod_prebuffering_progress(self):
        if self.stats is None:
            if self.status == DLSTATUS_STOPPED and self.progress == 1.0:
                return 1.0
            else:
                return 0.0
        else:
            return self.stats['vod_prebuf_frac']

    def is_vod(self):
        if self.stats is None:
            return False
        else:
            return self.stats['vod']

    def get_vod_playable(self):
        if self.stats is None:
            return False
        else:
            return self.stats['vod_playable']

    def get_vod_playable_after(self):
        if self.stats is None:
            return float(2147483648L)
        else:
            return self.stats['vod_playable_after']

    def get_vod_stats(self):
        if self.stats is None:
            return {}
        elif not self.stats.has_key('vod_stats'):
            return {}
        else:
            return self.stats['vod_stats']

    def get_stats(self):
        if self.stats is None:
            return {}
        else:
            return self.stats['stats']

    def get_log_messages(self):
        if self.logmsgs is None:
            return []
        else:
            return self.logmsgs

    def get_peerlist(self):
        if self.stats is None or 'spew' not in self.stats or self.stats['spew'] is None:
            return []
        else:
            return self.stats['spew']

    def get_coopdl_helpers(self):
        if self.coopdl_helpers is None:
            return []
        else:
            return self.coopdl_helpers

    def get_coopdl_coordinator(self):
        return self.coopdl_coordinator

    def get_swarmcache(self):
        if self.dltype != DLTYPE_TORRENT:
            return {}
        swarmcache = {}
        if self.status == DLSTATUS_REPEXING and self.swarmcache is not None:
            swarmcache = self.swarmcache
        elif self.status in [DLSTATUS_DOWNLOADING, DLSTATUS_SEEDING]:
            peerlist = [ p for p in self.get_peerlist() if p['direction'] == 'L' and p.get('pex_received', 0) ][:REPEX_SWARMCACHE_SIZE]
            swarmcache = {}
            for peer in peerlist:
                dns = (peer['ip'], peer['port'])
                swarmcache[dns] = {'last_seen': self.time,
                 'pex': []}

            if self.swarmcache is not None:
                for dns in self.swarmcache.keys()[:REPEX_SWARMCACHE_SIZE - len(swarmcache)]:
                    swarmcache[dns] = self.swarmcache[dns]

        elif self.swarmcache is not None:
            swarmcache = self.swarmcache
        return swarmcache
