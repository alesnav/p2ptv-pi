#Embedded file name: ACEStream\Core\CacheDB\SqliteVideoPlaybackStatsCacheDB.pyo
import sys
import os
import thread
from base64 import b64encode
from time import time
from ACEStream.__init__ import LIBRARYNAME
from ACEStream.Core.CacheDB.sqlitecachedb import SQLiteCacheDBBase
from ACEStream.Core.CacheDB.SqliteCacheDBHandler import BasicDBHandler
CREATE_VIDEOPLAYBACK_STATS_SQL_FILE = None
CREATE_VIDEOPLAYBACK_STATS_SQL_FILE_POSTFIX = os.path.join(LIBRARYNAME, 'Core', 'Statistics', 'tribler_videoplayback_stats.sql')
DB_FILE_NAME = 'tribler_videoplayback_stats.sdb'
DB_DIR_NAME = 'sqlite'
CURRENT_DB_VERSION = 2
ENABLE_LOGGER = False
DEBUG = False

def init_videoplayback_stats(config, db_exception_handler = None):
    global CREATE_VIDEOPLAYBACK_STATS_SQL_FILE
    config_dir = config['state_dir']
    install_dir = config['install_dir']
    CREATE_VIDEOPLAYBACK_STATS_SQL_FILE = os.path.join(install_dir, CREATE_VIDEOPLAYBACK_STATS_SQL_FILE_POSTFIX)
    sqlitedb = SQLiteVideoPlaybackStatsCacheDB.get_instance(db_exception_handler)
    sqlite_db_path = os.path.join(config_dir, DB_DIR_NAME, DB_FILE_NAME)
    sqlitedb.initDB(sqlite_db_path, CREATE_VIDEOPLAYBACK_STATS_SQL_FILE, current_db_version=CURRENT_DB_VERSION)
    return sqlitedb


class SQLiteVideoPlaybackStatsCacheDBV2(SQLiteCacheDBBase):

    def updateDB(self, fromver, tover):
        if fromver < 2:
            sql = '\n-- Simplify the database. All info is now an event.\n\nDROP TABLE IF EXISTS playback_info;\nDROP INDEX IF EXISTS playback_info_idx;\n\n-- Simplify the database. Events are simplified to key/value\n-- pairs. Because sqlite is unable to remove a column, we are forced\n-- to DROP and re-CREATE the event table.\n--\n-- Note that this will erase previous statistics... \n\nDROP TABLE IF EXISTS playback_event;\nDROP INDEX IF EXISTS playback_event_idx;\n\nCREATE TABLE playback_event (\n  key                   text NOT NULL,\n  timestamp             real NOT NULL,\n  event                 text NOT NULL\n);  \n\nCREATE INDEX playback_event_idx \n  ON playback_event (key, timestamp);\n'
            self.execute_write(sql, commit=False)
        self.writeDBVersion(CURRENT_DB_VERSION, commit=False)
        self.commit()


class SQLiteVideoPlaybackStatsCacheDB(SQLiteVideoPlaybackStatsCacheDBV2):
    __single = None
    lock = thread.allocate_lock()

    @classmethod
    def get_instance(cls, *args, **kw):
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
            raise RuntimeError, 'SQLiteVideoPlaybackStatsCacheDB is singleton'
        SQLiteCacheDBBase.__init__(self, *args, **kw)


class VideoPlaybackDBHandler(BasicDBHandler):
    __single = None
    lock = thread.allocate_lock()

    @classmethod
    def get_instance(cls, *args, **kw):
        if cls.__single is None:
            cls.lock.acquire()
            try:
                if cls.__single is None:
                    cls.__single = cls(*args, **kw)
            finally:
                cls.lock.release()

        return cls.__single

    def __init__(self):
        if VideoPlaybackDBHandler.__single is not None:
            raise RuntimeError, 'VideoPlaybackDBHandler is singleton'
        BasicDBHandler.__init__(self, SQLiteVideoPlaybackStatsCacheDB.get_instance(), 'playback_event')

    def add_event(self, key, event):
        if ENABLE_LOGGER:
            key = b64encode(key)
            if DEBUG:
                print >> sys.stderr, 'VideoPlaybackDBHandler add_event', key, event
            self._db.execute_write("INSERT INTO %s (key, timestamp, event) VALUES ('%s', %s, '%s')" % (self.table_name,
             key,
             time(),
             event))

    def flush(self):
        pass
