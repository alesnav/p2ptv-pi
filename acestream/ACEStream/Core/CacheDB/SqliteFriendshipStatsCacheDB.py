#Embedded file name: ACEStream\Core\CacheDB\SqliteFriendshipStatsCacheDB.pyo
import sys
import os
import threading
from ACEStream.__init__ import LIBRARYNAME
from ACEStream.Core.CacheDB.sqlitecachedb import *
from ACEStream.Core.CacheDB.SqliteCacheDBHandler import BasicDBHandler
CREATE_FRIENDSHIP_STATS_SQL_FILE = None
CREATE_FRIENDSHIP_STATS_SQL_FILE_POSTFIX = os.path.join(LIBRARYNAME, 'Core', 'Statistics', 'tribler_friendship_stats_sdb.sql')
DB_FILE_NAME = 'tribler_friendship_stats.sdb'
DB_DIR_NAME = 'sqlite'
CURRENT_DB_VERSION = 2
DEBUG = False

def init_friendship_stats(config, db_exception_handler = None):
    global CREATE_FRIENDSHIP_STATS_SQL_FILE
    config_dir = config['state_dir']
    install_dir = config['install_dir']
    CREATE_FRIENDSHIP_STATS_SQL_FILE = os.path.join(install_dir, CREATE_FRIENDSHIP_STATS_SQL_FILE_POSTFIX)
    sqlitedb = SQLiteFriendshipStatsCacheDB.getInstance(db_exception_handler)
    sqlite_db_path = os.path.join(config_dir, DB_DIR_NAME, DB_FILE_NAME)
    sqlitedb.initDB(sqlite_db_path, CREATE_FRIENDSHIP_STATS_SQL_FILE, current_db_version=CURRENT_DB_VERSION)
    return sqlitedb


class FSCacheDBBaseV2(SQLiteCacheDBBase):

    def updateDB(self, fromver, tover):
        if DEBUG:
            print >> sys.stderr, 'fscachedb2: Upgrading', fromver, tover
        if fromver == 1 and tover == 2:
            sql = 'ALTER TABLE FriendshipStatistics ADD COLUMN crawled_permid TEXT DEFAULT client NOT NULL;'
            self.execute_write(sql, commit=False)
            self.writeDBVersion(2, commit=False)
            self.commit()


class SQLiteFriendshipStatsCacheDB(FSCacheDBBaseV2):
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
            raise RuntimeError, 'SQLiteFriendshipStatsCacheDB is singleton'
        FSCacheDBBaseV2.__init__(self, *args, **kw)


class FriendshipStatisticsDBHandler(BasicDBHandler):
    __single = None
    lock = threading.Lock()

    def getInstance(*args, **kw):
        if FriendshipStatisticsDBHandler.__single is None:
            FriendshipStatisticsDBHandler.lock.acquire()
            try:
                if FriendshipStatisticsDBHandler.__single is None:
                    FriendshipStatisticsDBHandler(*args, **kw)
            finally:
                FriendshipStatisticsDBHandler.lock.release()

        return FriendshipStatisticsDBHandler.__single

    getInstance = staticmethod(getInstance)

    def __init__(self):
        if FriendshipStatisticsDBHandler.__single is not None:
            raise RuntimeError, 'FriendshipStatisticsDBHandler is singleton'
        FriendshipStatisticsDBHandler.__single = self
        db = SQLiteFriendshipStatsCacheDB.getInstance()
        BasicDBHandler.__init__(self, db, 'FriendshipStatistics')

    def getAllFriendshipStatistics(self, permid, last_update_time = None, range = None, sort = None, reverse = False):
        value_name = ('source_permid', 'target_permid', 'isForwarder', 'request_time', 'response_time', 'no_of_attempts', 'no_of_helpers', 'modified_on')
        where = 'request_time > ' + str(last_update_time)
        if range:
            offset = range[0]
            limit = range[1] - range[0]
        else:
            limit = offset = None
        if sort:
            desc = not reverse and 'desc' or ''
            if sort in 'name':
                order_by = ' lower(%s) %s' % (sort, desc)
            else:
                order_by = ' %s %s' % (sort, desc)
        else:
            order_by = None
        permidstr = bin2str(permid)
        res_list = self.getAll(value_name, where=where, offset=offset, limit=limit, order_by=order_by, source_permid=permidstr)
        if DEBUG:
            print >> sys.stderr, 'FriendshipStatisticsDBHandler: getAll: result is', res_list
        return res_list

    def saveFriendshipStatisticData(self, data):
        self._db.insertMany('FriendshipStatistics', data)

    def insertFriendshipStatistics(self, my_permid, target_permid, current_time, isForwarder = 0, no_of_attempts = 0, no_of_helpers = 0, commit = True):
        sql_insert_friendstatistics = "INSERT INTO FriendshipStatistics (source_permid, target_permid, isForwarder, request_time, response_time, no_of_attempts, no_of_helpers, modified_on) VALUES ('" + my_permid + "','" + target_permid + "'," + str(isForwarder) + ',' + str(current_time) + ', 0 , ' + str(no_of_attempts) + ',' + str(no_of_helpers) + ',' + str(current_time) + ')'
        self._db.execute_write(sql_insert_friendstatistics, commit=commit)

    def updateFriendshipStatistics(self, my_permid, target_permid, current_time, isForwarder = 0, no_of_attempts = 0, no_of_helpers = 0, commit = True):
        sql_insert_friendstatistics = 'UPDATE FriendshipStatistics SET request_time = ' + str(current_time) + ', no_of_attempts = ' + str(no_of_attempts) + ', no_of_helpers = ' + str(no_of_helpers) + ', modified_on = ' + str(current_time) + " where source_permid = '" + my_permid + "' and target_permid = '" + target_permid + "'"
        self._db.execute_write(sql_insert_friendstatistics, commit=commit)

    def updateFriendshipResponseTime(self, my_permid, target_permid, current_time, commit = True):
        sql_insert_friendstatistics = 'UPDATE FriendshipStatistics SET response_time = ' + str(current_time) + ', modified_on = ' + str(current_time) + " where source_permid = '" + my_permid + "' and target_permid = '" + target_permid + "'"
        if DEBUG:
            print >> sys.stderr, sql_insert_friendstatistics
        self._db.execute_write(sql_insert_friendstatistics, commit=commit)

    def insertOrUpdateFriendshipStatistics(self, my_permid, target_permid, current_time, isForwarder = 0, no_of_attempts = 0, no_of_helpers = 0, commit = True):
        if DEBUG:
            print >> sys.stderr, 'Friendship record being inserted of permid'
            print >> sys.stderr, target_permid
        res = self._db.getOne('FriendshipStatistics', 'target_permid', target_permid=target_permid)
        if not res:
            sql_insert_friendstatistics = "INSERT INTO FriendshipStatistics (source_permid, target_permid, isForwarder, request_time, response_time, no_of_attempts, no_of_helpers, modified_on) VALUES ('" + my_permid + "','" + target_permid + "'," + str(isForwarder) + ',' + str(current_time) + ', 0 , ' + str(no_of_attempts) + ',' + str(no_of_helpers) + ',' + str(current_time) + ')'
        else:
            sql_insert_friendstatistics = 'UPDATE FriendshipStatistics SET no_of_attempts = ' + str(no_of_attempts) + ', no_of_helpers = ' + str(no_of_helpers) + ', modified_on = ' + str(current_time) + " where source_permid = '" + my_permid + "' and target_permid = '" + target_permid + "'"
        if DEBUG:
            print >> sys.stderr, 'result is ', res
            print >> sys.stderr, sql_insert_friendstatistics
        try:
            self._db.execute_write(sql_insert_friendstatistics, commit=commit)
        except:
            print >> sys.stderr

    def getLastUpdateTimeOfThePeer(self, permid):
        res = self._db.getAll('FriendshipStatistics', 'source_permid', order_by='modified_on desc', limit=1)
        if not res:
            return 0
        else:
            return 0
