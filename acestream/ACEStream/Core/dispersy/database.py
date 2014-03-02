#Embedded file name: ACEStream\Core\dispersy\database.pyo
from __future__ import with_statement
import thread
import hashlib
import sqlite3
from singleton import Singleton

class Database(Singleton):

    def __init__(self, file_path):
        self._connection = sqlite3.Connection(file_path, isolation_level=None)
        self._cursor = self._connection.cursor()
        synchronous, = self._cursor.execute(u'PRAGMA synchronous').next()
        if not synchronous == 0:
            self._cursor.execute(u'PRAGMA synchronous = 0')
        temp_store, = self._cursor.execute(u'PRAGMA temp_store').next()
        if not temp_store == 3:
            self._cursor.execute(u'PRAGMA temp_store = 3')
        try:
            count, = self.execute(u"SELECT COUNT(1) FROM sqlite_master WHERE type = 'table' AND name = 'option'").next()
        except StopIteration:
            raise RuntimeError()

        if count:
            try:
                version, = self.execute(u"SELECT value FROM option WHERE key == 'database_version' LIMIT 1").next()
            except StopIteration:
                version = u'0'

        else:
            version = u'0'
        self.check_database(version)

    def __enter__(self):
        self._cursor.execute(u'BEGIN')
        return self.execute

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self._cursor.execute(u'COMMIT')
            return True
        else:
            self._cursor.execute(u'ROLLBACK')
            return False

    @property
    def last_insert_rowid(self):
        return self._cursor.lastrowid

    @property
    def changes(self):
        return self._cursor.rowcount

    def execute(self, statements, bindings = ()):
        try:
            return self._cursor.execute(statements, bindings)
        except sqlite3.Error as exception:
            raise

    def executescript(self, statements):
        try:
            return self._cursor.executescript(statements)
        except sqlite3.Error as exception:
            raise

    def executemany(self, statements, sequenceofbindings):
        try:
            return self._cursor.executemany(statements, sequenceofbindings)
        except sqlite3.Error as exception:
            raise

    def commit(self):
        return self._connection.commit()

    def check_database(self, database_version):
        raise NotImplementedError()
