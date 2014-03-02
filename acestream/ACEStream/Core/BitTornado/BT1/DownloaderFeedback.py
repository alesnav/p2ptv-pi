#Embedded file name: ACEStream\Core\BitTornado\BT1\DownloaderFeedback.pyo
import sys
from threading import Event
try:
    True
except:
    True = 1
    False = 0

DEBUG = False

class DownloaderFeedback:

    def __init__(self, choker, ghttpdl, hhttpdl, add_task, upfunc, downfunc, httpdownfunc, ratemeasure, leftfunc, file_length, finflag, sp, statistics, statusfunc = None, interval = None, infohash = None, voddownload = None):
        self.choker = choker
        self.ghttpdl = ghttpdl
        self.hhttpdl = hhttpdl
        self.add_task = add_task
        self.upfunc = upfunc
        self.downfunc = downfunc
        self.httpdownfunc = httpdownfunc
        self.ratemeasure = ratemeasure
        self.leftfunc = leftfunc
        self.file_length = file_length
        self.finflag = finflag
        self.sp = sp
        self.statistics = statistics
        self.lastids = []
        self.spewdata = None
        self.infohash = infohash
        self.voddownload = voddownload
        self.doneprocessing = Event()
        self.doneprocessing.set()
        if statusfunc:
            self.autodisplay(statusfunc, interval)

    def _rotate(self):
        cs = self.choker.connections
        for id in self.lastids:
            for i in xrange(len(cs)):
                if cs[i].get_id() == id:
                    return cs[i:] + cs[:i]

        return cs

    def spews(self):
        l = []
        cs = self._rotate()
        self.lastids = [ c.get_id() for c in cs ]
        for c in cs:
            a = {}
            a['id'] = c.get_readable_id()
            a['extended_version'] = c.extended_version or ''
            a['ip'] = c.get_ip()
            if c.is_locally_initiated():
                a['port'] = c.get_port()
            else:
                a['port'] = 0
            try:
                a['optimistic'] = c is self.choker.connections[0]
            except:
                a['optimistic'] = False

            if c.is_locally_initiated():
                a['direction'] = 'L'
            else:
                a['direction'] = 'R'
            u = c.get_upload()
            a['uprate'] = int(u.measure.get_rate())
            a['uinterested'] = u.is_interested()
            a['uchoked'] = u.is_choked()
            a['uhasqueries'] = u.has_queries()
            d = c.get_download()
            a['downrate'] = int(d.measure.get_rate())
            a['dinterested'] = d.is_interested()
            a['dchoked'] = d.is_choked()
            a['snubbed'] = d.is_snubbed(just_check=True)
            a['utotal'] = d.connection.upload.measure.get_total()
            a['dtotal'] = d.connection.download.measure.get_total()
            if d.connection.download.have:
                a['completed'] = float(len(d.connection.download.have) - d.connection.download.have.numfalse) / float(len(d.connection.download.have))
            else:
                a['completed'] = 1.0
            a['speed'] = d.connection.download.peermeasure.get_rate()
            a['g2g'] = c.use_g2g
            a['g2g_score'] = c.g2g_score()
            a['pex_received'] = c.pex_received
            a['last_requested_piece'] = c.last_requested_piece
            a['last_received_piece'] = c.last_received_piece
            l.append(a)

        if self.ghttpdl is not None:
            for dl in self.ghttpdl.get_downloads():
                if dl.goodseed:
                    a = {}
                    a['id'] = 'url list'
                    a['ip'] = dl.baseurl
                    if dl.is_proxy:
                        a['ip'] = 'p ' + a['ip']
                    a['optimistic'] = False
                    a['direction'] = 'L'
                    a['uprate'] = 0
                    a['uinterested'] = False
                    a['uchoked'] = False
                    if dl.active:
                        a['downrate'] = int(dl.measure.get_rate())
                    else:
                        a['downrate'] = 0
                    a['short_downrate'] = int(dl.short_measure.get_rate_noupdate())
                    a['dinterested'] = True
                    a['dchoked'] = not dl.active
                    a['snubbed'] = not dl.active
                    a['utotal'] = None
                    a['dtotal'] = dl.measure.get_total()
                    a['completed'] = 1.0
                    a['speed'] = dl.avg_speed
                    a['speed_proxy'] = dl.avg_speed_proxy
                    a['speed_non_proxy'] = dl.avg_speed_non_proxy
                    a['last_requested_piece'] = dl.last_requested_piece
                    a['last_received_piece'] = dl.last_received_piece
                    l.append(a)

        if self.hhttpdl is not None:
            for dl in self.hhttpdl.get_downloads():
                if dl.goodseed:
                    a = {}
                    a['id'] = 'http seed'
                    a['ip'] = dl.baseurl
                    a['optimistic'] = False
                    a['direction'] = 'L'
                    a['uprate'] = 0
                    a['uinterested'] = False
                    a['uchoked'] = False
                    a['downrate'] = int(dl.measure.get_rate())
                    a['dinterested'] = True
                    a['dchoked'] = not dl.active
                    a['snubbed'] = not dl.active
                    a['utotal'] = None
                    a['dtotal'] = dl.measure.get_total()
                    a['completed'] = 1.0
                    a['speed'] = None
                    l.append(a)

        return l

    def gather(self, displayfunc = None, getpeerlist = False):
        s = {'stats': self.statistics.update(get_pieces_stats=getpeerlist)}
        if getpeerlist:
            s['spew'] = self.spews()
        else:
            s['spew'] = None
        s['up'] = self.upfunc()
        if self.finflag.isSet():
            if DEBUG:
                print >> sys.stderr, '>>>stats: finflag is set'
            s['done'] = self.file_length
            s['down'] = 0.0
            s['httpdown'] = 0.0
            s['frac'] = 1.0
            s['wanted'] = 0
            s['time'] = 0
            s['vod'] = False
            s['vod_prebuf_frac'] = 1.0
            s['vod_playable'] = True
            s['vod_playable_after'] = 0.0
            s['vod_stats'] = {'harry': 1}
            if self.voddownload is not None:
                s['vod_stats'] = self.voddownload.get_stats()
            return s
        s['down'] = self.downfunc()
        if self.ghttpdl is not None and (self.ghttpdl.is_video_support_enabled() or self.ghttpdl.is_proxy_enabled()) or self.hhttpdl is not None and self.hhttpdl.is_video_support_enabled():
            s['httpdown'] = self.httpdownfunc()
        else:
            s['httpdown'] = 0.0
        obtained, desired, have = self.leftfunc()
        s['done'] = obtained
        s['wanted'] = desired
        if desired > 0:
            s['frac'] = float(obtained) / desired
        else:
            s['frac'] = 1.0
        if DEBUG:
            print >> sys.stderr, '>>>stats: obtained', obtained, 'desired', desired, 'frac', s['frac']
        if desired == obtained:
            s['time'] = 0
        else:
            s['time'] = self.ratemeasure.get_time_left(desired - obtained)
        if self.voddownload is not None:
            s['vod_prebuf_frac'] = self.voddownload.get_prebuffering_progress()
            s['vod_playable'] = self.voddownload.is_playable()
            s['vod_playable_after'] = self.voddownload.get_playable_after()
            s['vod'] = True
            s['vod_stats'] = self.voddownload.get_stats()
        else:
            s['vod_prebuf_frac'] = 0.0
            s['vod_playable'] = False
            s['vod_playable_after'] = float(2147483648L)
            s['vod'] = False
            s['vod_stats'] = {}
        return s

    def display(self, displayfunc):
        if not self.doneprocessing.isSet():
            return
        self.doneprocessing.clear()
        stats = self.gather()
        if self.finflag.isSet():
            displayfunc(dpflag=self.doneprocessing, upRate=stats['up'], statistics=stats['stats'], spew=stats['spew'])
        elif stats['time'] is not None:
            displayfunc(dpflag=self.doneprocessing, fractionDone=stats['frac'], sizeDone=stats['done'], downRate=stats['down'], upRate=stats['up'], statistics=stats['stats'], spew=stats['spew'], timeEst=stats['time'])
        else:
            displayfunc(dpflag=self.doneprocessing, fractionDone=stats['frac'], sizeDone=stats['done'], downRate=stats['down'], upRate=stats['up'], statistics=stats['stats'], spew=stats['spew'])

    def autodisplay(self, displayfunc, interval):
        self.displayfunc = displayfunc
        self.interval = interval
        self._autodisplay()

    def _autodisplay(self):
        self.add_task(self._autodisplay, self.interval)
        self.display(self.displayfunc)
