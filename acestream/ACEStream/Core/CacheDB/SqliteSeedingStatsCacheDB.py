#Embedded file name: ACEStream\Core\CacheDB\SqliteSeedingStatsCacheDB.pyo
import os
from time import time
import threading
from traceback import print_exc
from ACEStream.__init__ import LIBRARYNAME
from ACEStream.Core.CacheDB.sqlitecachedb import *
from ACEStream.Core.CacheDB.SqliteCacheDBHandler import BasicDBHandler
from ACEStream.Core.simpledefs import *
CREATE_SEEDINGSTATS_SQL_FILE = None
CREATE_SEEDINGSTATS_SQL_FILE_POSTFIX = os.path.join(LIBRARYNAME, 'Core', 'Statistics', 'tribler_seedingstats_sdb.sql')
DB_FILE_NAME = 'tribler_seedingstats.sdb'
DB_DIR_NAME = 'sqlite'
CURRENT_DB_VERSION = 1
DEFAULT_BUSY_TIMEOUT = 10000
MAX_SQL_BATCHED_TO_TRANSACTION = 1000
SHOW_ALL_EXECUTE = False
costs = []
cost_reads = []
DEBUG = False

def init_seeding_stats(config, db_exception_handler = None):
    global CREATE_SEEDINGSTATS_SQL_FILE
    config_dir = config['state_dir']
    install_dir = config['install_dir']
    CREATE_SEEDINGSTATS_SQL_FILE = os.path.join(install_dir, CREATE_SEEDINGSTATS_SQL_FILE_POSTFIX)
    sqlitedb = SQLiteSeedingStatsCacheDB.getInstance(db_exception_handler)
    sqlite_db_path = os.path.join(config_dir, DB_DIR_NAME, DB_FILE_NAME)
    sqlitedb.initDB(sqlite_db_path, CREATE_SEEDINGSTATS_SQL_FILE)
    return sqlitedb


class SQLiteSeedingStatsCacheDB(SQLiteCacheDBBase):
    __single = None
    lock = threading.RLock()

    @classmethod
    def getInstance(cls, *args, **kw):
        if cls.__single is None:
            cls.lock.acquire()
            try:
                if cls.__single is None:
                    cls.__single = cls(*args, **kw)
            finally:
                cls.lock.release()

        return cls.__single

    def __init__(self, *args, **kw):
        if self.__single != None:
            raise RuntimeError, 'SQLiteSeedingStatsCacheDB is singleton'
        SQLiteCacheDBBase.__init__(self, *args, **kw)


class SeedingStatsDBHandler(BasicDBHandler):
    __single = None
    lock = threading.Lock()

    def getInstance(*args, **kw):
        if SeedingStatsDBHandler.__single is None:
            SeedingStatsDBHandler.lock.acquire()
            try:
                if SeedingStatsDBHandler.__single is None:
                    SeedingStatsDBHandler(*args, **kw)
            finally:
                SeedingStatsDBHandler.lock.release()

        return SeedingStatsDBHandler.__single

    getInstance = staticmethod(getInstance)

    def __init__(self):
        if SeedingStatsDBHandler.__single is not None:
            raise RuntimeError, 'SeedingStatDBHandler is singleton'
        SeedingStatsDBHandler.__single = self
        db = SQLiteSeedingStatsCacheDB.getInstance()
        BasicDBHandler.__init__(self, db, 'SeedingStats')

    def updateSeedingStats(self, permID, reputation, dslist, interval):
        permID = bin2str(permID)
        seedings = []
        for item in dslist:
            if item.get_status() == DLSTATUS_SEEDING:
                seedings.append(item)

        commit = False
        for i in range(0, len(seedings)):
            ds = seedings[i]
            infohash = bin2str(ds.get_download().get_def().get_infohash())
            stats = ds.stats['stats']
            ul = stats.upTotal
            if i == len(seedings) - 1:
                commit = True
            res = self.existedInfoHash(infohash)
            if res is not None:
                self.updateSeedingStat(infohash, ul, res[0][0], interval, commit)
            else:
                self.insertSeedingStat(infohash, permID, ul, interval, commit)

    def existedInfoHash(self, infohash):
        sql = "SELECT seeding_time FROM SeedingStats WHERE info_hash='%s' and crawled=0" % infohash
        try:
            cursor = self._db.execute_read(sql)
            if cursor:
                res = list(cursor)
                if len(res) > 0:
                    return res
                else:
                    return None
            else:
                return None
        except:
            return None

    def updateSeedingStat(self, infohash, reputation, seedingtime, interval, commit):
        try:
            sql_update = "UPDATE SeedingStats SET seeding_time=%s, reputation=%s WHERE info_hash='%s' AND crawled=0" % (seedingtime + interval, reputation, infohash)
            self._db.execute_write(sql_update, None, commit)
        except:
            print_exc()

    def insertSeedingStat(self, infohash, permID, reputation, interval, commit):
        try:
            sql_insert = "INSERT INTO SeedingStats VALUES(%s, '%s', '%s', %s, %s, %s)" % (time(),
             permID,
             infohash,
             interval,
             reputation,
             0)
            self._db.execute_write(sql_insert, None, commit)
        except:
            print_exc()


class SeedingStatsSettingsDBHandler(BasicDBHandler):
    __single = None
    lock = threading.Lock()

    def getInstance(*args, **kw):
        if SeedingStatsSettingsDBHandler.__single is None:
            SeedingStatsSettingsDBHandler.lock.acquire()
            try:
                if SeedingStatsSettingsDBHandler.__single is None:
                    SeedingStatsSettingsDBHandler(*args, **kw)
            finally:
                SeedingStatsSettingsDBHandler.lock.release()

        return SeedingStatsSettingsDBHandler.__single

    getInstance = staticmethod(getInstance)

    def __init__(self):
        if SeedingStatsSettingsDBHandler.__single is not None:
            raise RuntimeError, 'SeedingStatDBHandler is singleton'
        SeedingStatsSettingsDBHandler.__single = self
        db = SQLiteSeedingStatsCacheDB.getInstance()
        BasicDBHandler.__init__(self, db, 'CrawlingSettings')

    def loadCrawlingSettings(self):
        try:
            sql_query = 'SELECT * FROM SeedingStatsSettings'
            cursor = self._db.execute_read(sql_query)
            if cursor:
                return list(cursor)
            return None
        except:
            print_exc()

    def updateCrawlingSettings(self, args):
        try:
            sql_update = 'UPDATE SeedingStatsSettings SET crawling_interval=%s, crawling_enabled=%s WHERE version=1' % (args[0], args[1])
            cursor = self._db.execute_write(sql_update)
        except:
            print_exc()
