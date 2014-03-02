#Embedded file name: ACEStream\Core\CacheDB\sqlitecachedb.pyo
import sys
import os
from time import sleep, time
from base64 import encodestring, decodestring
import threading
from traceback import print_exc, print_stack
from ACEStream.Core.simpledefs import INFOHASH_LENGTH, CHECKSUM_LENGTH, NTFY_DISPERSY, NTFY_STARTED
from ACEStream.Core.Utilities.unicode import dunno2unicode
try:
    import apsw
except:
    print >> sys.stderr, 'not using apsw'

CURRENT_MAIN_DB_VERSION = 5
TEST_SQLITECACHEDB_UPGRADE = False
CREATE_SQL_FILE = None
CREATE_SQL_FILE_POSTFIX = os.path.join('data', 'schema_sdb_v' + str(CURRENT_MAIN_DB_VERSION) + '.sql')
DB_FILE_NAME = 'torrentstream.sdb'
DB_DIR_NAME = 'sqlite'
DEFAULT_BUSY_TIMEOUT = 10000
MAX_SQL_BATCHED_TO_TRANSACTION = 1000
NULL = None
icon_dir = None
SHOW_ALL_EXECUTE = False
costs = []
cost_reads = []
torrent_dir = None
config_dir = None
TEST_OVERRIDE = False
DEBUG = False

class Warning(Exception):
    pass


def init(config, db_exception_handler = None):
    global CREATE_SQL_FILE
    global icon_dir
    global config_dir
    global torrent_dir
    torrent_dir = os.path.abspath(config['torrent_collecting_dir'])
    config_dir = config['state_dir']
    install_dir = config['install_dir']
    CREATE_SQL_FILE = os.path.join(install_dir, CREATE_SQL_FILE_POSTFIX)
    sqlitedb = SQLiteCacheDB.getInstance(db_exception_handler)
    if config['superpeer']:
        sqlite_db_path = ':memory:'
    else:
        sqlite_db_path = os.path.join(config_dir, DB_DIR_NAME, DB_FILE_NAME)
    if DEBUG:
        print >> sys.stderr, 'cachedb: init: SQL FILE', sqlite_db_path
    icon_dir = os.path.abspath(config['peer_icon_path'])
    sqlitedb.initDB(sqlite_db_path, CREATE_SQL_FILE)
    return sqlitedb


def done(config_dir):
    SQLiteCacheDB.getInstance().close()


def make_filename(config_dir, filename):
    if config_dir is None:
        return filename
    else:
        return os.path.join(config_dir, filename)


def bin2str(bin):
    return encodestring(bin).replace('\n', '')


def str2bin(str):
    return decodestring(str)


def print_exc_plus():
    tb = sys.exc_info()[2]
    stack = []
    while tb:
        stack.append(tb.tb_frame)
        tb = tb.tb_next

    print_exc()
    print >> sys.stderr, 'Locals by frame, innermost last'
    for frame in stack:
        print >> sys.stderr
        print >> sys.stderr, 'Frame %s in %s at line %s' % (frame.f_code.co_name, frame.f_code.co_filename, frame.f_lineno)
        for key, value in frame.f_locals.items():
            print >> sys.stderr, '\t%20s = ' % key,
            try:
                print >> sys.stderr, value
            except:
                print >> sys.stderr, '<ERROR WHILE PRINTING VALUE>'


class safe_dict(dict):

    def __init__(self, *args, **kw):
        self.lock = threading.RLock()
        dict.__init__(self, *args, **kw)

    def __getitem__(self, key):
        self.lock.acquire()
        try:
            return dict.__getitem__(self, key)
        finally:
            self.lock.release()

    def __setitem__(self, key, value):
        self.lock.acquire()
        try:
            dict.__setitem__(self, key, value)
        finally:
            self.lock.release()

    def __delitem__(self, key):
        self.lock.acquire()
        try:
            dict.__delitem__(self, key)
        finally:
            self.lock.release()

    def __contains__(self, key):
        self.lock.acquire()
        try:
            return dict.__contains__(self, key)
        finally:
            self.lock.release()

    def values(self):
        self.lock.acquire()
        try:
            return dict.values(self)
        finally:
            self.lock.release()


class SQLiteCacheDBBase():
    lock = threading.RLock()

    def __init__(self, db_exception_handler = None):
        self.exception_handler = db_exception_handler
        self.cursor_table = safe_dict()
        self.cache_transaction_table = safe_dict()
        self.class_variables = safe_dict({'db_path': None,
         'busytimeout': None})
        self.permid_id = safe_dict()
        self.infohash_id = safe_dict()
        self.checksum_id = safe_dict()
        self.show_execute = False
        self.status_table = None
        self.category_table = None
        self.src_table = None
        self.applied_pragma_sync_norm = False

    def __del__(self):
        self.close()

    def close(self, clean = False):
        thread_name = threading.currentThread().getName()
        cur = self.getCursor(create=False)
        if cur:
            con = cur.getconnection()
            cur.close()
            con.close()
            con = None
            del self.cursor_table[thread_name]
            try:
                if thread_name in self.cache_transaction_table.keys():
                    del self.cache_transaction_table[thread_name]
            except:
                print_exc()

        if clean:
            self.permid_id = safe_dict()
            self.infohash_id = safe_dict()
            self.exception_handler = None
            self.class_variables = safe_dict({'db_path': None,
             'busytimeout': None})
            self.cursor_table = safe_dict()
            self.cache_transaction_table = safe_dict()

    def getCursor(self, create = True):
        thread_name = threading.currentThread().getName()
        curs = self.cursor_table
        cur = curs.get(thread_name, None)
        if cur is None and create:
            self.openDB(self.class_variables['db_path'], self.class_variables['busytimeout'])
            cur = curs.get(thread_name)
        return cur

    def openDB(self, dbfile_path = None, busytimeout = DEFAULT_BUSY_TIMEOUT):
        thread_name = threading.currentThread().getName()
        if thread_name in self.cursor_table:
            return self.cursor_table[thread_name]
        if dbfile_path.lower() != ':memory:':
            db_dir, db_filename = os.path.split(dbfile_path)
            if db_dir and not os.path.isdir(db_dir):
                os.makedirs(db_dir)
        con = apsw.Connection(dbfile_path)
        con.setbusytimeout(busytimeout)
        cur = con.cursor()
        self.cursor_table[thread_name] = cur
        if not self.applied_pragma_sync_norm:
            self.applied_pragma_sync_norm = True
            cur.execute('PRAGMA synchronous = NORMAL;')
        return cur

    def createDBTable(self, sql_create_table, dbfile_path, busytimeout = DEFAULT_BUSY_TIMEOUT):
        cur = self.openDB(dbfile_path, busytimeout)
        print dbfile_path
        cur.execute(sql_create_table)

    def initDB(self, sqlite_filepath, create_sql_filename = None, busytimeout = DEFAULT_BUSY_TIMEOUT, check_version = True, current_db_version = CURRENT_MAIN_DB_VERSION):
        if create_sql_filename is None:
            create_sql_filename = CREATE_SQL_FILE
        try:
            self.lock.acquire()
            class_db_path = self.class_variables['db_path']
            if sqlite_filepath is None:
                if class_db_path is not None:
                    return self.openDB(class_db_path, self.class_variables['busytimeout'])
                raise Exception, 'You must specify the path of database file when open it at the first time'
            else:
                if class_db_path is None:
                    self.safelyOpenACEStreamDB(sqlite_filepath, create_sql_filename, busytimeout, check_version=check_version, current_db_version=current_db_version)
                    self.class_variables = {'db_path': sqlite_filepath,
                     'busytimeout': int(busytimeout)}
                    return self.openDB()
                if sqlite_filepath != class_db_path:
                    raise Exception, 'Only one database file can be opened. You have opened %s and are trying to open %s.' % (class_db_path, sqlite_filepath)
        finally:
            self.lock.release()

    def safelyOpenACEStreamDB(self, dbfile_path, sql_create, busytimeout = DEFAULT_BUSY_TIMEOUT, check_version = False, current_db_version = None):
        try:
            if not os.path.isfile(dbfile_path):
                raise Warning('No existing database found. Attempting to creating a new database %s' % repr(dbfile_path))
            cur = self.openDB(dbfile_path, busytimeout)
            if check_version:
                sqlite_db_version = self.readDBVersion()
                if sqlite_db_version == NULL or int(sqlite_db_version) < 1:
                    raise NotImplementedError
        except Exception as exception:
            if isinstance(exception, Warning):
                print >> sys.stderr, exception
            else:
                print_exc()
            if os.path.isfile(dbfile_path):
                self.close(clean=True)
                os.remove(dbfile_path)
            if os.path.isfile(sql_create):
                f = open(sql_create)
                sql_create_tables = f.read()
                f.close()
            else:
                raise Exception, 'Cannot open sql script at %s' % os.path.realpath(sql_create)
            self.createDBTable(sql_create_tables, dbfile_path, busytimeout)
            if check_version:
                sqlite_db_version = self.readDBVersion()

        if check_version:
            self.checkDB(sqlite_db_version, current_db_version)

    def checkDB(self, db_ver, curr_ver):
        if not db_ver or not curr_ver:
            self.updateDB(db_ver, curr_ver)
            return
        db_ver = int(db_ver)
        curr_ver = int(curr_ver)
        if db_ver != curr_ver or config_dir is not None and os.path.exists(os.path.join(config_dir, 'upgradingdb.txt')):
            self.updateDB(db_ver, curr_ver)

    def updateDB(self, db_ver, curr_ver):
        pass

    def readDBVersion(self):
        cur = self.getCursor()
        sql = u"select value from MyInfo where entry='version'"
        res = self.fetchone(sql)
        if res:
            find = list(res)
            return find[0]
        else:
            return None

    def writeDBVersion(self, version, commit = True):
        sql = u"UPDATE MyInfo SET value=? WHERE entry='version'"
        self.execute_write(sql, [version], commit=commit)

    def show_sql(self, switch):
        self.show_execute = switch

    def commit(self):
        self.transaction()

    def lastrowid(self):
        cur = self.getCursor()
        con = cur.getconnection()
        return con.last_insert_rowid()

    def _execute(self, sql, args = None):
        cur = self.getCursor()
        if SHOW_ALL_EXECUTE or self.show_execute:
            thread_name = threading.currentThread().getName()
            print >> sys.stderr, '===', thread_name, '===\n', sql, '\n-----\n', args, '\n======\n'
        try:
            if args is None:
                return cur.execute(sql)
            return cur.execute(sql, args)
        except Exception as msg:
            if True:
                print_exc()
                print_stack()
                print >> sys.stderr, 'cachedb: execute error:', Exception, msg
                thread_name = threading.currentThread().getName()
                print >> sys.stderr, '===', thread_name, '===\nSQL Type:', type(sql), '\n-----\n', sql, '\n-----\n', args, '\n======\n'
            raise msg

    def execute_read(self, sql, args = None):
        return self._execute(sql, args)

    def execute_write(self, sql, args = None, commit = True):
        self.cache_transaction(sql, args)
        if commit:
            self.commit()

    def executemany(self, sql, args, commit = True):
        thread_name = threading.currentThread().getName()
        if thread_name not in self.cache_transaction_table:
            self.cache_transaction_table[thread_name] = []
        all = [ (sql, arg) for arg in args ]
        self.cache_transaction_table[thread_name].extend(all)
        if commit:
            self.commit()

    def cache_transaction(self, sql, args = None):
        thread_name = threading.currentThread().getName()
        if thread_name not in self.cache_transaction_table:
            self.cache_transaction_table[thread_name] = []
        self.cache_transaction_table[thread_name].append((sql, args))

    def transaction(self, sql = None, args = None):
        if sql:
            self.cache_transaction(sql, args)
        thread_name = threading.currentThread().getName()
        n = 0
        sql_full = ''
        arg_list = []
        sql_queue = self.cache_transaction_table.get(thread_name, None)
        if sql_queue:
            while True:
                try:
                    _sql, _args = sql_queue.pop(0)
                except IndexError:
                    break

                _sql = _sql.strip()
                if not _sql:
                    continue
                if not _sql.endswith(';'):
                    _sql += ';'
                sql_full += _sql + '\n'
                if _args != None:
                    arg_list += list(_args)
                n += 1
                if n % MAX_SQL_BATCHED_TO_TRANSACTION == 0:
                    self._transaction(sql_full, arg_list)
                    sql_full = ''
                    arg_list = []

            self._transaction(sql_full, arg_list)

    def _transaction(self, sql, args = None):
        if sql:
            sql = 'BEGIN TRANSACTION; \n' + sql + 'COMMIT TRANSACTION;'
            try:
                self._execute(sql, args)
            except Exception as e:
                self.commit_retry_if_busy_or_rollback(e, 0, sql=sql)

    def commit_retry_if_busy_or_rollback(self, e, tries, sql = None):
        print >> sys.stderr, 'sqlcachedb: commit_retry: after', str(e), repr(sql)
        if str(e).startswith('BusyError'):
            try:
                self._execute('COMMIT')
            except Exception as e2:
                if tries < 5:
                    sleep(pow(2.0, tries + 2) / 100.0)
                    self.commit_retry_if_busy_or_rollback(e2, tries + 1)
                else:
                    self.rollback(tries)
                    raise Exception, e2

        else:
            self.rollback(tries)
            m = 'cachedb: TRANSACTION ERROR ' + threading.currentThread().getName() + ' ' + str(e)
            raise Exception, m

    def rollback(self, tries):
        print_exc()
        try:
            self._execute('ROLLBACK')
        except Exception as e:
            m = 'cachedb: ROLLBACK ERROR ' + threading.currentThread().getName() + ' ' + str(e)
            raise Exception, m

    def insert_or_replace(self, table_name, commit = True, **argv):
        if len(argv) == 1:
            sql = 'INSERT OR REPLACE INTO %s (%s) VALUES (?);' % (table_name, argv.keys()[0])
        else:
            questions = '?,' * len(argv)
            sql = 'INSERT OR REPLACE INTO %s %s VALUES (%s);' % (table_name, tuple(argv.keys()), questions[:-1])
        self.execute_write(sql, argv.values(), commit)

    def insert(self, table_name, commit = True, **argv):
        if len(argv) == 1:
            sql = 'INSERT INTO %s (%s) VALUES (?);' % (table_name, argv.keys()[0])
        else:
            questions = '?,' * len(argv)
            sql = 'INSERT INTO %s %s VALUES (%s);' % (table_name, tuple(argv.keys()), questions[:-1])
        self.execute_write(sql, argv.values(), commit)

    def insertMany(self, table_name, values, keys = None, commit = True):
        questions = u'?,' * len(values[0])
        if keys is None:
            sql = u'INSERT INTO %s VALUES (%s);' % (table_name, questions[:-1])
        else:
            sql = u'INSERT INTO %s %s VALUES (%s);' % (table_name, tuple(keys), questions[:-1])
        self.executemany(sql, values, commit=commit)

    def update(self, table_name, where = None, commit = True, **argv):
        if len(argv) > 0:
            sql = u'UPDATE %s SET ' % table_name
            arg = []
            for k, v in argv.iteritems():
                if type(v) is tuple:
                    sql += u'%s %s ?,' % (k, v[0])
                    arg.append(v[1])
                else:
                    sql += u'%s=?,' % k
                    arg.append(v)

            sql = sql[:-1]
            if where != None:
                sql += u' where %s' % where
            self.execute_write(sql, arg, commit)

    def delete(self, table_name, commit = True, **argv):
        sql = u'DELETE FROM %s WHERE ' % table_name
        arg = []
        for k, v in argv.iteritems():
            if type(v) is tuple:
                sql += u'%s %s ? AND ' % (k, v[0])
                arg.append(v[1])
            else:
                sql += u'%s=? AND ' % k
                arg.append(v)

        sql = sql[:-5]
        self.execute_write(sql, argv.values(), commit)

    def size(self, table_name):
        num_rec_sql = u'SELECT count(*) FROM %s;' % table_name
        result = self.fetchone(num_rec_sql)
        return result

    def fetchone(self, sql, args = None):
        find = self.execute_read(sql, args)
        if not find:
            return NULL
        find = list(find)
        if len(find) > 0:
            find = find[0]
        else:
            return NULL
        if len(find) > 1:
            return find
        else:
            return find[0]

    def fetchall(self, sql, args = None, retry = 0):
        res = self.execute_read(sql, args)
        if res != None:
            find = list(res)
            return find
        else:
            return []

    def getOne(self, table_name, value_name, where = None, conj = 'and', **kw):
        if isinstance(value_name, tuple):
            value_names = u','.join(value_name)
        elif isinstance(value_name, list):
            value_names = u','.join(value_name)
        else:
            value_names = value_name
        if isinstance(table_name, tuple):
            table_names = u','.join(table_name)
        elif isinstance(table_name, list):
            table_names = u','.join(table_name)
        else:
            table_names = table_name
        sql = u'select %s from %s' % (value_names, table_names)
        if where or kw:
            sql += u' where '
        if where:
            sql += where
            if kw:
                sql += u' %s ' % conj
        if kw:
            arg = []
            for k, v in kw.iteritems():
                if type(v) is tuple:
                    operator = v[0]
                    arg.append(v[1])
                else:
                    operator = '='
                    arg.append(v)
                sql += u' %s %s ? ' % (k, operator)
                sql += conj

            sql = sql[:-len(conj)]
        else:
            arg = None
        return self.fetchone(sql, arg)

    def getAll(self, table_name, value_name, where = None, group_by = None, having = None, order_by = None, limit = None, offset = None, conj = 'and', **kw):
        if isinstance(value_name, tuple):
            value_names = u','.join(value_name)
        elif isinstance(value_name, list):
            value_names = u','.join(value_name)
        else:
            value_names = value_name
        if isinstance(table_name, tuple):
            table_names = u','.join(table_name)
        elif isinstance(table_name, list):
            table_names = u','.join(table_name)
        else:
            table_names = table_name
        sql = u'select %s from %s' % (value_names, table_names)
        if where or kw:
            sql += u' where '
        if where:
            sql += where
            if kw:
                sql += u' %s ' % conj
        if kw:
            arg = []
            for k, v in kw.iteritems():
                if type(v) is tuple:
                    operator = v[0]
                    arg.append(v[1])
                else:
                    operator = '='
                    arg.append(v)
                sql += u' %s %s ?' % (k, operator)
                sql += conj

            sql = sql[:-len(conj)]
        else:
            arg = None
        if group_by != None:
            sql += u' group by ' + group_by
        if having != None:
            sql += u' having ' + having
        if order_by != None:
            sql += u' order by ' + order_by
        if limit != None:
            sql += u' limit %d' % limit
        if offset != None:
            sql += u' offset %d' % offset
        try:
            return self.fetchall(sql, arg) or []
        except Exception as msg:
            print >> sys.stderr, 'sqldb: Wrong getAll sql statement:', sql
            raise Exception, msg

    def insertInfohash(self, infohash, check_dup = False, commit = True):
        if infohash in self.infohash_id:
            if check_dup:
                print >> sys.stderr, 'sqldb: infohash to insert already exists', `infohash`
            return
        infohash_str = bin2str(infohash)
        sql_insert_torrent = 'INSERT INTO Torrent (infohash) VALUES (?)'
        self.execute_write(sql_insert_torrent, (infohash_str,), commit)

    def deleteInfohash(self, infohash = None, torrent_id = None, commit = True):
        if torrent_id is None:
            torrent_id = self.getTorrentID(infohash)
        if torrent_id != None:
            self.delete('Torrent', torrent_id=torrent_id, commit=commit)
            if infohash in self.infohash_id:
                self.infohash_id.pop(infohash)

    def getTorrentID(self, infohash):
        if infohash in self.infohash_id:
            return self.infohash_id[infohash]
        sql_get_torrent_id = 'SELECT torrent_id FROM Torrent WHERE infohash==?'
        tid = self.fetchone(sql_get_torrent_id, (bin2str(infohash),))
        if tid != None:
            self.infohash_id[infohash] = tid
        return tid

    def getTorrentIDByChecksum(self, checksum):
        if checksum in self.checksum_id:
            return self.checksum_id[checksum]
        sql_get_torrent_id = 'SELECT torrent_id FROM Torrent WHERE checksum==?'
        tid = self.fetchone(sql_get_torrent_id, (bin2str(checksum),))
        if tid != None:
            self.checksum_id[checksum] = tid
        return tid

    def getTorrentIDS(self, infohashes):
        to_select = []
        for infohash in infohashes:
            if infohash not in self.infohash_id:
                to_select.append(bin2str(infohash))

        while len(to_select) > 0:
            nrToQuery = min(len(to_select), 50)
            parameters = '?,' * nrToQuery
            sql_get_torrent_ids = 'SELECT torrent_id, infohash FROM Torrent WHERE infohash IN (' + parameters[:-1] + ')'
            torrents = self.fetchall(sql_get_torrent_ids, to_select[:nrToQuery])
            for torrent_id, infohash in torrents:
                self.infohash_id[str2bin(infohash)] = torrent_id

            to_select = to_select[nrToQuery:]

        to_return = []
        for infohash in infohashes:
            if infohash in self.infohash_id:
                to_return.append(self.infohash_id[infohash])
            else:
                to_return.append(None)

        return to_return

    def getInfohash(self, torrent_id):
        sql_get_infohash = 'SELECT infohash FROM Torrent WHERE torrent_id==?'
        arg = (torrent_id,)
        ret = self.fetchone(sql_get_infohash, arg)
        ret = str2bin(ret)
        return ret

    def getTorrentStatusTable(self):
        if self.status_table is None:
            st = self.getAll('TorrentStatus', ('lower(name)', 'status_id'))
            self.status_table = dict(st)
        return self.status_table

    def getTorrentCategoryTable(self):
        if self.category_table is None:
            ct = self.getAll('Category', ('lower(name)', 'category_id'))
            self.category_table = dict(ct)
        return self.category_table

    def getTorrentSourceTable(self):
        if self.src_table is None:
            st = self.getAll('TorrentSource', ('name', 'source_id'))
            self.src_table = dict(st)
        return self.src_table

    def test(self):
        res1 = self.getAll('Category', '*')
        res2 = len(self.getAll('Peer', 'name', 'name is not NULL'))
        return (res1, res2)


class SQLiteCacheDBV2(SQLiteCacheDBBase):

    def updateDB(self, fromver, tover):
        if fromver < 2:
            sql = '\n            ALTER TABLE adid2infohash ADD COLUMN last_seen INTEGER NOT NULL DEFAULT 0;\n            \n            CREATE TABLE IF NOT EXISTS ts_players (\n                player_id TEXT PRIMARY KEY NOT NULL,\n                infohash TEXT NOT NULL,\n                developer_id INTEGER,\n                affiliate_id INTEGER,\n                zone_id INTEGER\n            );\n            CREATE INDEX IF NOT EXISTS ts_players_infohash_idx ON ts_players (infohash);\n            \n            CREATE TABLE IF NOT EXISTS ts_metadata (\n                infohash TEXT PRIMARY KEY NOT NULL,\n                idx INTEGER NOT NULL,\n                duration INTEGER NOT NULL,\n                prebuf_pieces TEXT,\n                replace_mp4_metatags TEXT\n            );\n            \n            CREATE UNIQUE INDEX IF NOT EXISTS ts_metadata_idx ON ts_metadata (infohash, idx);\n            CREATE INDEX IF NOT EXISTS ts_metadata_infohash_idx ON ts_metadata (infohash);\n            '
            self.execute_write(sql, commit=False)
        if fromver < 3:
            sql = "\n            DELETE FROM ts_players;\n            ALTER TABLE ts_players ADD COLUMN `checksum` TEXT NOT NULL DEFAULT '';\n            CREATE INDEX IF NOT EXISTS ts_players_checksum_idx ON ts_players (`checksum`);\n            \n            DELETE FROM Torrent;\n            DELETE FROM TorrentTracker;\n            ALTER TABLE Torrent ADD COLUMN `checksum` TEXT NOT NULL DEFAULT '';\n            CREATE INDEX IF NOT EXISTS torrent_checksum_idx ON Torrent (`checksum`);\n            "
            self.execute_write(sql, commit=False)
        if fromver < 4:
            sql = "\n            CREATE TABLE user_profiles (\n                `id`        INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,\n                `created`   INTEGER NOT NULL,\n                `modified`  INTEGER NOT NULL,\n                `active`    INTEGER NOT NULL\n            );\n            \n            CREATE TABLE user_profile_data (\n                `profile_id`    INTEGER NOT NULL,\n                `name`          TEXT NOT NULL,\n                `value`         TEXT\n            );\n            \n            CREATE UNIQUE INDEX user_profile_data_idx_profile_param ON user_profile_data (`profile_id`, `name`);\n            CREATE INDEX user_profile_data_idx_profile ON user_profile_data (`profile_id`);\n            \n            CREATE TABLE `gender` (\n                `id`   INTEGER PRIMARY KEY NOT NULL,\n                `name` TEXT NOT NULL\n            );\n            \n            CREATE TABLE `age` (\n                `id`   INTEGER PRIMARY KEY NOT NULL,\n                `name` TEXT NOT NULL\n            );\n\n            INSERT INTO `gender` VALUES (1, 'gender_male');\n            INSERT INTO `gender` VALUES (2, 'gender_female');\n            \n            INSERT INTO `age` VALUES (1, 'age_less_than_13');\n            INSERT INTO `age` VALUES (2, 'age_13_17');\n            INSERT INTO `age` VALUES (3, 'age_18_24');\n            INSERT INTO `age` VALUES (4, 'age_25_34');\n            INSERT INTO `age` VALUES (5, 'age_35_44');\n            INSERT INTO `age` VALUES (6, 'age_45_54');\n            INSERT INTO `age` VALUES (7, 'age_55_64');\n            INSERT INTO `age` VALUES (8, 'age_more_than_64');\n            "
            self.execute_write(sql, commit=False)
        if fromver < 5:
            sql = "\n            UPDATE `age` SET `name` = 'age_18_21' WHERE `id` = 3;\n            INSERT INTO `age` VALUES (9,  'age_22_25');\n            UPDATE `age` SET `name` = 'age_26_30' WHERE `id` = 4;\n            INSERT INTO `age` VALUES (10, 'age_31_36');\n            UPDATE `age` SET `name` = 'age_37_44' WHERE `id` = 5;\n            "
            self.execute_write(sql, commit=False)
        self.writeDBVersion(CURRENT_MAIN_DB_VERSION, commit=False)
        self.commit()


class SQLiteCacheDB(SQLiteCacheDBV2):
    __single = None

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

    def __init__(self, *args, **kargs):
        if self.__single != None:
            raise RuntimeError, 'SQLiteCacheDB is singleton'
        SQLiteCacheDBBase.__init__(self, *args, **kargs)


if __name__ == '__main__':
    configure_dir = sys.argv[1]
    config = {}
    config['state_dir'] = configure_dir
    config['install_dir'] = u'.'
    config['peer_icon_path'] = u'.'
    sqlite_test = init(config)
    sqlite_test.test()
