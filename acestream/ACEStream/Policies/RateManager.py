#Embedded file name: ACEStream\Policies\RateManager.pyo
import sys
from sets import Set
from threading import RLock
from traceback import print_exc
from ACEStream.Core.simpledefs import *
DEBUG = False

class RateManager:

    def __init__(self):
        self.lock = RLock()
        self.statusmap = {}
        self.currenttotal = {}
        self.dset = Set()
        self.clear_downloadstates()

    def add_downloadstate(self, ds):
        if DEBUG:
            print >> sys.stderr, 'RateManager: add_downloadstate', `(ds.get_download().get_def().get_infohash())`
        self.lock.acquire()
        try:
            d = ds.get_download()
            if d not in self.dset:
                self.statusmap[ds.get_status()].append(ds)
                for dir in [UPLOAD, DOWNLOAD]:
                    self.currenttotal[dir] += ds.get_current_speed(dir)

                self.dset.add(d)
            return len(self.dset)
        finally:
            self.lock.release()

    def add_downloadstatelist(self, dslist):
        for ds in dslist:
            self.add_downloadstate(ds)

    def adjust_speeds(self):
        self.lock.acquire()
        try:
            self.calc_and_set_speed_limits(DOWNLOAD)
            self.calc_and_set_speed_limits(UPLOAD)
            self.clear_downloadstates()
        finally:
            self.lock.release()

    def clear_downloadstates(self):
        self.statusmap[DLSTATUS_ALLOCATING_DISKSPACE] = []
        self.statusmap[DLSTATUS_WAITING4HASHCHECK] = []
        self.statusmap[DLSTATUS_HASHCHECKING] = []
        self.statusmap[DLSTATUS_DOWNLOADING] = []
        self.statusmap[DLSTATUS_SEEDING] = []
        self.statusmap[DLSTATUS_STOPPED] = []
        self.statusmap[DLSTATUS_STOPPED_ON_ERROR] = []
        self.statusmap[DLSTATUS_REPEXING] = []
        for dir in [UPLOAD, DOWNLOAD]:
            self.currenttotal[dir] = 0

        self.dset.clear()

    def calc_and_set_speed_limits(self, direct):
        pass


class UserDefinedMaxAlwaysOtherwiseEquallyDividedRateManager(RateManager):

    def __init__(self):
        RateManager.__init__(self)
        self.global_max_speed = {}
        self.global_max_speed[UPLOAD] = 0.0
        self.global_max_speed[DOWNLOAD] = 0.0
        self.global_max_seedupload_speed = 0.0

    def set_global_max_speed(self, direct, speed):
        self.lock.acquire()
        self.global_max_speed[direct] = speed
        self.lock.release()

    def set_global_max_seedupload_speed(self, speed):
        self.lock.acquire()
        self.global_max_seedupload_speed = speed
        self.lock.release()

    def calc_and_set_speed_limits(self, dir = UPLOAD):
        if DEBUG:
            print >> sys.stderr, 'RateManager: calc_and_set_speed_limits', dir
        if dir == UPLOAD:
            workingset = self.statusmap[DLSTATUS_DOWNLOADING] + self.statusmap[DLSTATUS_SEEDING]
        else:
            workingset = self.statusmap[DLSTATUS_DOWNLOADING]
        if DEBUG:
            print >> sys.stderr, 'RateManager: calc_and_set_speed_limits: len workingset', len(workingset)
        newws = []
        for ds in workingset:
            if ds.get_num_peers() > 0:
                newws.append(ds)

        workingset = newws
        if DEBUG:
            print >> sys.stderr, 'RateManager: calc_and_set_speed_limits: len active workingset', len(workingset)
        if not workingset:
            return
        globalmaxspeed = self.get_global_max_speed(dir)
        if globalmaxspeed == 0:
            for ds in workingset:
                d = ds.get_download()
                d.set_max_speed(dir, d.get_max_desired_speed(dir))

            return
        if DEBUG:
            print >> sys.stderr, 'RateManager: calc_and_set_speed_limits: globalmaxspeed is', globalmaxspeed, dir
        todoset = []
        for ds in workingset:
            d = ds.get_download()
            maxdesiredspeed = d.get_max_desired_speed(dir)
            if maxdesiredspeed > 0.0:
                d.set_max_speed(dir, maxdesiredspeed)
            else:
                todoset.append(ds)

        if len(todoset) > 0:
            localmaxspeed = globalmaxspeed / float(len(todoset))
            if DEBUG:
                print >> sys.stderr, 'RateManager: calc_and_set_speed_limits: localmaxspeed is', localmaxspeed, dir
            for ds in todoset:
                d = ds.get_download()
                d.set_max_speed(dir, localmaxspeed)

    def get_global_max_speed(self, dir = UPLOAD):
        if dir == UPLOAD and len(self.statusmap[DLSTATUS_DOWNLOADING]) == 0 and len(self.statusmap[DLSTATUS_SEEDING]) > 0:
            return self.global_max_seedupload_speed
        else:
            return self.global_max_speed[dir]


class UserDefinedMaxAlwaysOtherwiseDividedOnDemandRateManager(UserDefinedMaxAlwaysOtherwiseEquallyDividedRateManager):

    def __init__(self):
        UserDefinedMaxAlwaysOtherwiseEquallyDividedRateManager.__init__(self)
        self.ROOM = 5.0

    def calc_and_set_speed_limits(self, dir = UPLOAD):
        if DEBUG:
            print >> sys.stderr, 'RateManager: calc_and_set_speed_limits', dir
        if dir == UPLOAD:
            workingset = self.statusmap[DLSTATUS_DOWNLOADING] + self.statusmap[DLSTATUS_SEEDING]
        else:
            workingset = self.statusmap[DLSTATUS_DOWNLOADING]
        if DEBUG:
            print >> sys.stderr, 'RateManager: calc_and_set_speed_limits: len workingset', len(workingset)
        newws = []
        for ds in workingset:
            if ds.get_num_peers() > 0:
                newws.append(ds)

        workingset = newws
        if DEBUG:
            print >> sys.stderr, 'RateManager: calc_and_set_speed_limits: len new workingset', len(workingset)
            for ds in workingset:
                d = ds.get_download()
                print >> sys.stderr, 'RateManager: calc_and_set_speed_limits: working is', d.get_def().get_name()

        if not workingset:
            return
        globalmaxspeed = self.get_global_max_speed(dir)
        if globalmaxspeed == 0:
            for ds in workingset:
                d = ds.get_download()
                d.set_max_speed(dir, d.get_max_desired_speed(dir))

            return
        if DEBUG:
            print >> sys.stderr, 'RateManager: calc_and_set_speed_limits: globalmaxspeed is', globalmaxspeed, dir
        todoset = []
        for ds in workingset:
            d = ds.get_download()
            maxdesiredspeed = d.get_max_desired_speed(dir)
            if maxdesiredspeed > 0.0:
                d.set_max_speed(dir, maxdesiredspeed)
            else:
                todoset.append(ds)

        if len(todoset) > 0:
            localmaxspeed = globalmaxspeed / float(len(todoset))
            if DEBUG:
                print >> sys.stderr, 'RateManager: calc_and_set_speed_limits: localmaxspeed is', localmaxspeed, dir
            downloadsatmax = False
            downloadsunderutil = False
            for ds in todoset:
                d = ds.get_download()
                currspeed = ds.get_current_speed(dir)
                currmaxspeed = d.get_max_speed(dir)
                newmaxspeed = currspeed + self.ROOM
                if currspeed >= currmaxspeed - 3.0:
                    downloadsatmax = True
                elif newmaxspeed < localmaxspeed:
                    downloadsunderutil = True

            if downloadsatmax and downloadsunderutil:
                totalunused = 0.0
                todoset2 = []
                for ds in todoset:
                    d = ds.get_download()
                    currspeed = ds.get_current_speed(dir)
                    newmaxspeed = currspeed + self.ROOM
                    if newmaxspeed < localmaxspeed:
                        totalunused += localmaxspeed - newmaxspeed
                        print >> sys.stderr, 'RateManager: calc_and_set_speed_limits: Underutil set to', newmaxspeed
                        d.set_max_speed(dir, newmaxspeed)
                    else:
                        todoset2.append(ds)

                if len(todoset2) > 0:
                    pie = float(len(todoset2)) * localmaxspeed + totalunused
                    piece = pie / float(len(todoset2))
                    for ds in todoset:
                        d = ds.get_download()
                        print >> sys.stderr, 'RateManager: calc_and_set_speed_limits: Overutil set to', piece
                        d.set_max_speed(dir, piece)

                else:
                    print >> sys.stderr, 'UserDefinedMaxAlwaysOtherwiseDividedOnDemandRateManager: Internal error: No overutilizers anymore?'
            else:
                for ds in todoset:
                    d = ds.get_download()
                    print >> sys.stderr, 'RateManager: calc_and_set_speed_limits: Normal set to', piece
                    d.set_max_speed(dir, localmaxspeed)


class UserDefinedMaxAlwaysOtherwiseDividedOverActiveSwarmsRateManager(UserDefinedMaxAlwaysOtherwiseEquallyDividedRateManager):

    def __init__(self):
        UserDefinedMaxAlwaysOtherwiseEquallyDividedRateManager.__init__(self)
        self.ROOM = 5.0

    def calc_and_set_speed_limits(self, dir = UPLOAD):
        if DEBUG:
            print >> sys.stderr, 'RateManager: calc_and_set_speed_limits', dir
        if dir == UPLOAD:
            workingset = self.statusmap[DLSTATUS_DOWNLOADING] + self.statusmap[DLSTATUS_SEEDING]
        else:
            workingset = self.statusmap[DLSTATUS_DOWNLOADING]
        if DEBUG:
            print >> sys.stderr, 'RateManager: set_lim: len workingset', len(workingset)
        newws = []
        inactiveset = []
        for ds in workingset:
            if ds.get_num_nonseeds() > 0:
                newws.append(ds)
            else:
                inactiveset.append(ds)

        workingset = newws
        if DEBUG:
            print >> sys.stderr, 'RateManager: set_lim: len new workingset', len(workingset)
            for ds in workingset:
                d = ds.get_download()
                print >> sys.stderr, 'RateManager: set_lim: working is', d.get_def().get_name()

        globalmaxspeed = self.get_global_max_speed(dir)
        if DEBUG:
            print >> sys.stderr, 'RateManager: set_lim: globalmaxspeed is', globalmaxspeed, dir
        if globalmaxspeed == 0:
            for ds in workingset:
                d = ds.get_download()
                d.set_max_speed(dir, d.get_max_desired_speed(dir))

            for ds in inactiveset:
                d = ds.get_download()
                d.set_max_speed(dir, d.get_max_desired_speed(dir))

            return
        if DEBUG:
            print >> sys.stderr, 'RateManager: set_lim: globalmaxspeed is', globalmaxspeed, dir
        todoset = []
        for ds in workingset:
            d = ds.get_download()
            maxdesiredspeed = d.get_max_desired_speed(dir)
            if maxdesiredspeed > 0.0:
                d.set_max_speed(dir, maxdesiredspeed)
            else:
                todoset.append(ds)

        if len(todoset) > 0:
            localmaxspeed = globalmaxspeed / float(len(todoset))
            if DEBUG:
                print >> sys.stderr, 'RateManager: set_lim: localmaxspeed is', localmaxspeed, dir
            for ds in todoset:
                d = ds.get_download()
                if DEBUG:
                    print >> sys.stderr, 'RateManager: set_lim:', d.get_def().get_name(), 'WorkQ', localmaxspeed
                d.set_max_speed(dir, localmaxspeed)

        for ds in inactiveset:
            d = ds.get_download()
            desspeed = d.get_max_desired_speed(dir)
            if desspeed == 0:
                setspeed = globalmaxspeed
            else:
                setspeed = min(desspeed, globalmaxspeed)
            if DEBUG:
                print >> sys.stderr, 'RateManager: set_lim:', d.get_def().get_name(), 'InactQ', setspeed
            d.set_max_speed(dir, setspeed)
