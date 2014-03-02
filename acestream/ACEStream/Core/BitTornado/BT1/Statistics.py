#Embedded file name: ACEStream\Core\BitTornado\BT1\Statistics.pyo
from threading import Event
try:
    True
except:
    True = 1
    False = 0

class Statistics_Response:
    pass


class Statistics:

    def __init__(self, upmeasure, downmeasure, httpdownmeasure, connecter, ghttpdl, hhttpdl, ratelimiter, fdatflag, encoder):
        self.upmeasure = upmeasure
        self.downmeasure = downmeasure
        self.httpdownmeasure = httpdownmeasure
        self.connecter = connecter
        self.ghttpdl = ghttpdl
        self.hhttpdl = hhttpdl
        self.ratelimiter = ratelimiter
        self.downloader = connecter.downloader
        self.picker = connecter.downloader.picker
        self.storage = connecter.downloader.storage
        self.torrentmeasure = connecter.downloader.totalmeasure
        self.fdatflag = fdatflag
        self.encoder = encoder
        self.fdatactive = False
        self.piecescomplete = None
        self.placesopen = None
        self.storage_totalpieces = len(self.storage.hashes)

    def set_dirstats(self, files, piece_length):
        self.piecescomplete = 0
        self.placesopen = 0
        self.filelistupdated = Event()
        self.filelistupdated.set()
        frange = xrange(len(files))
        self.filepieces = [ [] for x in frange ]
        self.filepieces2 = [ [] for x in frange ]
        self.fileamtdone = [ 0.0 for x in frange ]
        self.filecomplete = [ False for x in frange ]
        self.fileinplace = [ False for x in frange ]
        start = 0L
        for i in frange:
            l = files[i][1]
            if l == 0:
                self.fileamtdone[i] = 1.0
                self.filecomplete[i] = True
                self.fileinplace[i] = True
            else:
                fp = self.filepieces[i]
                fp2 = self.filepieces2[i]
                for piece in range(int(start / piece_length), int((start + l - 1) / piece_length) + 1):
                    fp.append(piece)
                    fp2.append(piece)

                start += l

    def update(self, get_pieces_stats = False):
        s = Statistics_Response()
        s.upTotal = self.upmeasure.get_total()
        s.downTotal = self.downmeasure.get_total()
        s.httpDownTotal = self.httpdownmeasure.get_total()
        s.external_connection_made = self.connecter.external_connection_made
        if s.downTotal > 0:
            s.shareRating = float(s.upTotal) / s.downTotal
        elif s.upTotal == 0:
            s.shareRating = 0.0
        else:
            s.shareRating = -1.0
        s.torrentRate = self.torrentmeasure.get_rate()
        s.torrentTotal = self.torrentmeasure.get_total()
        s.numConCandidates = len(self.encoder.to_connect)
        s.numConInitiated = len(self.encoder.connections)
        s.numSeeds = self.picker.seeds_connected
        s.numOldSeeds = self.downloader.num_disconnected_seeds()
        s.numPeers = len(self.downloader.downloads) - s.numSeeds
        s.numCopies = 0.0
        for i in self.picker.crosscount:
            if i == 0:
                s.numCopies += 1
            else:
                s.numCopies += 1 - float(i) / self.picker.numpieces
                break

        if self.picker.done:
            s.numCopies2 = s.numCopies + 1
        else:
            s.numCopies2 = 0.0
            for i in self.picker.crosscount2:
                if i == 0:
                    s.numCopies2 += 1
                else:
                    s.numCopies2 += 1 - float(i) / self.picker.numpieces
                    break

        s.discarded = self.downloader.discarded
        s.httpSeeds = 0
        if self.ghttpdl is not None and (self.ghttpdl.is_video_support_enabled() or self.ghttpdl.is_proxy_enabled()):
            s.numSeeds += self.ghttpdl.seedsfound
            s.numOldSeeds += self.ghttpdl.seedsfound
            s.httpSeeds += self.ghttpdl.seedsfound
        if self.hhttpdl is not None and self.hhttpdl.is_video_support_enabled():
            s.numSeeds += self.hhttpdl.seedsfound
            s.numOldSeeds += self.hhttpdl.seedsfound
            s.httpSeeds += self.hhttpdl.seedsfound
        if s.numPeers == 0 or self.picker.numpieces == 0:
            s.percentDone = 0.0
        else:
            s.percentDone = 100.0 * (float(self.picker.totalcount) / self.picker.numpieces) / s.numPeers
        s.backgroundallocating = self.storage.bgalloc_active
        s.storage_totalpieces = len(self.storage.hashes)
        s.storage_active = len(self.storage.stat_active)
        s.storage_new = len(self.storage.stat_new)
        s.storage_dirty = len(self.storage.dirty)
        numdownloaded = self.storage.stat_numdownloaded
        s.storage_justdownloaded = numdownloaded
        s.storage_numcomplete = self.storage.stat_numfound + numdownloaded
        s.storage_numflunked = self.storage.stat_numflunked
        s.storage_isendgame = self.downloader.endgamemode
        if get_pieces_stats:
            s.storage_inactive_list = self.storage.inactive_requests[:]
            s.storage_active_list = self.storage.numactive[:]
            s.storage_dirty_list = [ len(self.storage.dirty.get(i, [])) for i in xrange(s.storage_totalpieces) ]
        s.peers_kicked = self.downloader.kicked.items()
        s.peers_banned = self.downloader.banned.items()
        try:
            s.upRate = int(self.ratelimiter.upload_rate / 1000)
        except:
            s.upRate = 0

        s.upSlots = self.ratelimiter.slots
        s.have = self.storage.get_have_copy()
        if self.piecescomplete is None:
            return s
        if self.fdatflag.isSet():
            if not self.fdatactive:
                self.fdatactive = True
        else:
            self.fdatactive = False
        if self.piecescomplete != self.picker.numgot:
            for i in xrange(len(self.filecomplete)):
                if self.filecomplete[i]:
                    continue
                oldlist = self.filepieces[i]
                newlist = [ piece for piece in oldlist if not self.storage.have[piece] ]
                if len(newlist) != len(oldlist):
                    self.filepieces[i] = newlist
                    self.fileamtdone[i] = (len(self.filepieces2[i]) - len(newlist)) / float(len(self.filepieces2[i]))
                    if not newlist:
                        self.filecomplete[i] = True
                    self.filelistupdated.set()

            self.piecescomplete = self.picker.numgot
        if self.filelistupdated.isSet() or self.placesopen != len(self.storage.places):
            for i in xrange(len(self.filecomplete)):
                if not self.filecomplete[i] or self.fileinplace[i]:
                    continue
                while self.filepieces2[i]:
                    piece = self.filepieces2[i][-1]
                    if self.storage.places[piece] != piece:
                        break
                    del self.filepieces2[i][-1]

                if not self.filepieces2[i]:
                    self.fileinplace[i] = True
                    self.storage.set_file_readonly(i)
                    self.filelistupdated.set()

            self.placesopen = len(self.storage.places)
        s.fileamtdone = self.fileamtdone
        s.filecomplete = self.filecomplete
        s.fileinplace = self.fileinplace
        s.filelistupdated = self.filelistupdated
        return s
