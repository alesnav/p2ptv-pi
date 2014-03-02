#Embedded file name: ACEStream\Core\CacheDB\SqliteCacheDBHandler.pyo
from ACEStream.Core.CacheDB.sqlitecachedb import SQLiteCacheDB, bin2str, str2bin, NULL
from copy import deepcopy, copy
from traceback import print_exc
from time import time
from ACEStream.Core.TorrentDef import TorrentDef
import sys
import os
import socket
import threading
import base64
from random import randint, sample
import math
import re
import hashlib
from maxflow import Network
from math import atan, pi
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
from Notifier import Notifier
from ACEStream.Core.simpledefs import *
from ACEStream.Core.Utilities.unicode import name2unicode, dunno2unicode
from ACEStream.Core.defaults import DEFAULTPORT
from ACEStream.Core.Utilities.logger import log, log_exc
MAXFLOW_DISTANCE = 2
ALPHA = float(1) / 30000
DEBUG = False
SHOW_ERROR = False

def show_permid_shorter(permid):
    if not permid:
        return 'None'
    s = base64.encodestring(permid).replace('\n', '')
    return s[-5:]


class BasicDBHandler():

    def __init__(self, db, table_name):
        self._db = db
        self.table_name = table_name
        self.notifier = Notifier.getInstance()

    def __del__(self):
        try:
            self.sync()
        except:
            if SHOW_ERROR:
                print_exc()

    def close(self):
        try:
            self._db.close()
        except:
            if SHOW_ERROR:
                print_exc()

    def size(self):
        return self._db.size(self.table_name)

    def sync(self):
        self._db.commit()

    def commit(self):
        self._db.commit()

    def getOne(self, value_name, where = None, conj = 'and', **kw):
        return self._db.getOne(self.table_name, value_name, where=where, conj=conj, **kw)

    def getAll(self, value_name, where = None, group_by = None, having = None, order_by = None, limit = None, offset = None, conj = 'and', **kw):
        return self._db.getAll(self.table_name, value_name, where=where, group_by=group_by, having=having, order_by=order_by, limit=limit, offset=offset, conj=conj, **kw)


class MyDBHandler(BasicDBHandler):
    __single = None
    lock = threading.Lock()

    @staticmethod
    def getInstance(*args, **kw):
        if MyDBHandler.__single is None:
            MyDBHandler.lock.acquire()
            try:
                if MyDBHandler.__single is None:
                    MyDBHandler(*args, **kw)
            finally:
                MyDBHandler.lock.release()

        return MyDBHandler.__single

    def __init__(self):
        if MyDBHandler.__single is not None:
            raise RuntimeError, 'MyDBHandler is singleton'
        MyDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self, db, 'MyInfo')

    def get(self, key, default_value = None):
        value = self.getOne('value', entry=key)
        if value is not NULL:
            return value
        if default_value is not None:
            return default_value
        raise KeyError, key

    def put(self, key, value, commit = True):
        if self.getOne('value', entry=key) is NULL:
            self._db.insert(self.table_name, commit=commit, entry=key, value=value)
        else:
            where = 'entry=' + repr(key)
            self._db.update(self.table_name, where, commit=commit, value=value)


class UserProfile():

    @staticmethod
    def create():
        dbhandler = UserProfileDBHandler.getInstance()
        return UserProfile(dbhandler)

    def __init__(self, dbhandler, profile_id = None):
        self.dbhandler = dbhandler
        self.profile_id = profile_id
        self.active = 0
        self.gender = None
        self.age = None
        self.genders = self.dbhandler.get_genders()
        self.ages = self.dbhandler.get_ages()

    def get_id(self):
        return self.profile_id

    def set_id(self, profile_id):
        self.profile_id = profile_id

    def set_active(self, active):
        self.active = active

    def get_active(self):
        return self.active

    def set_gender(self, gender_id):
        gender_id = int(gender_id)
        if not self.genders.has_key(gender_id):
            if DEBUG:
                print >> sys.stderr, 'UserProfile::set_gender: bad gender id: gender_id', gender_id, type(gender_id), 'self.genders', self.genders
            raise ValueError, 'bad gender id'
        self.gender = gender_id

    def set_age(self, age_id):
        age_id = int(age_id)
        if not self.ages.has_key(age_id):
            raise ValueError, 'bad age id'
        self.age = age_id

    def get_gender_id(self):
        return self.gender

    def get_gender_name(self):
        if self.gender is None:
            return
        return self.genders[self.gender]

    def get_age_id(self):
        return self.age

    def get_age_name(self):
        if self.age is None:
            return
        return self.ages[self.age]

    def save(self):
        self.dbhandler.save_profile(self)
        self.dbhandler.close()

    def delete(self):
        self.dbhandler.delete_profile(self)

    def get_genders(self):
        return copy(self.genders)

    def get_ages(self):
        return copy(self.ages)

    def __str__(self):
        return 'UserProfile: id=%s active=%s gender=%s age=%s' % (self.profile_id,
         self.active,
         self.gender,
         self.age)


class UserProfileDBHandler(BasicDBHandler):
    __single = None
    lock = threading.Lock()

    @staticmethod
    def getInstance(*args, **kw):
        if UserProfileDBHandler.__single is None:
            UserProfileDBHandler.lock.acquire()
            try:
                if UserProfileDBHandler.__single is None:
                    UserProfileDBHandler(*args, **kw)
            finally:
                UserProfileDBHandler.lock.release()

        return UserProfileDBHandler.__single

    def __init__(self):
        if UserProfileDBHandler.__single is not None:
            raise RuntimeError, 'UserProfileDBHandler is singleton'
        UserProfileDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self, db, 'user_profiles')

    def get_active_profile(self):
        profile_id = self._db.getOne('user_profiles', 'id', active=1)
        if profile_id is NULL:
            return None
        return self.get_profile(profile_id)

    def get_profile(self, profile_id):
        fields = ('name', 'value')
        res = self._db.getAll('user_profile_data', fields, profile_id=profile_id)
        if len(res) == 0:
            return None
        profile = UserProfile(self, profile_id)
        profile.set_active(1)
        for row in res:
            if row[0] == 'gender':
                profile.set_gender(row[1])
            elif row[0] == 'age':
                profile.set_age(row[1])

        return profile

    def save_profile(self, profile):
        profile_id = profile.get_id()
        if profile_id is None:
            now = long(time())
            values = {'created': now,
             'modified': now,
             'active': profile.get_active()}
            self._db.insert('user_profiles', commit=True, **values)
            profile_id = self._db.lastrowid()
            if DEBUG:
                print >> sys.stderr, 'UserProfileDBHandler::save_profile: create new profile: profile_id', profile_id
            profile.set_id(profile_id)
            if profile.get_active() == 1:
                self._db.update('user_profiles', where='`id` != ' + str(profile_id), commit=False, active=0)
            values = {'profile_id': profile_id,
             'name': 'gender',
             'value': profile.get_gender_id()}
            self._db.insert('user_profile_data', commit=False, **values)
            values = {'profile_id': profile_id,
             'name': 'age',
             'value': profile.get_age_id()}
            self._db.insert('user_profile_data', commit=False, **values)
        else:
            where = '`id`=' + str(profile_id)
            self._db.update('user_profiles', where=where, commit=False, modified=long(time()))
            where = "`profile_id`=%d and `name`='gender'" % profile_id
            self._db.update('user_profile_data', where=where, commit=False, value=profile.get_gender_id())
            where = "`profile_id`=%d and `name`='age'" % profile_id
            self._db.update('user_profile_data', where=where, commit=False, value=profile.get_age_id())
        self.commit()
        return profile_id

    def delete_profile(self, profile):
        pass

    def get_genders(self):
        data = {}
        fields = ('id', 'name')
        res = self._db.getAll('gender', fields)
        for row in res:
            data[row[0]] = row[1]

        if DEBUG:
            print >> sys.stderr, 'UserProfileDBHandler::get_genders: res', res, 'data', data
        return data

    def get_ages(self):
        data = {}
        fields = ('id', 'name')
        res = self._db.getAll('age', fields)
        for row in res:
            data[row[0]] = row[1]

        if DEBUG:
            print >> sys.stderr, 'UserProfileDBHandler::get_ages: res', res, 'data', data
        return data


class Url2TorrentDBHandler(BasicDBHandler):
    __single = None
    lock = threading.Lock()

    @staticmethod
    def getInstance(*args, **kw):
        if Url2TorrentDBHandler.__single is None:
            Url2TorrentDBHandler.lock.acquire()
            try:
                if Url2TorrentDBHandler.__single is None:
                    Url2TorrentDBHandler(*args, **kw)
            finally:
                Url2TorrentDBHandler.lock.release()

        return Url2TorrentDBHandler.__single

    def __init__(self):
        if Url2TorrentDBHandler.__single is not None:
            raise RuntimeError, 'Url2TorrentDBHandler is singleton'
        Url2TorrentDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self, db, 'url2torrent')

    def get(self, url):
        urlhash = hashlib.sha1(url).hexdigest()
        infohash = self.getOne('infohash', urlhash=urlhash)
        if infohash is None:
            return
        return str2bin(infohash)

    def put(self, url, infohash, commit = True):
        urlhash = hashlib.sha1(url).hexdigest()
        if self.getOne('infohash', urlhash=urlhash) is NULL:
            self._db.insert(self.table_name, commit=commit, urlhash=urlhash, url=url, infohash=bin2str(infohash), updated=long(time()))
        else:
            where = 'urlhash=' + repr(urlhash)
            self._db.update(self.table_name, where, commit=commit, infohash=bin2str(infohash), updated=long(time()))


class AdID2InfohashDBHandler(BasicDBHandler):
    __single = None
    lock = threading.Lock()

    @staticmethod
    def getInstance(*args, **kw):
        if AdID2InfohashDBHandler.__single is None:
            AdID2InfohashDBHandler.lock.acquire()
            try:
                if AdID2InfohashDBHandler.__single is None:
                    AdID2InfohashDBHandler(*args, **kw)
            finally:
                AdID2InfohashDBHandler.lock.release()

        return AdID2InfohashDBHandler.__single

    def __init__(self):
        if AdID2InfohashDBHandler.__single is not None:
            raise RuntimeError, 'AdID2Infohash is singleton'
        AdID2InfohashDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self, db, 'adid2infohash')

    def get(self, adid):
        infohash = self.getOne('infohash', adid=adid)
        if infohash is None:
            return
        return str2bin(infohash)

    def get_last_seen(self, infohash):
        last_seen = self.getOne('last_seen', infohash=bin2str(infohash))
        return last_seen

    def put(self, adid, infohash, commit = True):
        if self.getOne('infohash', adid=adid) is NULL:
            self._db.insert(self.table_name, commit=commit, adid=adid, infohash=bin2str(infohash), last_seen=long(time()))
        else:
            where = 'adid=' + repr(str(adid))
            self._db.update(self.table_name, where, commit=commit, last_seen=long(time()))


class TsPlayersDBHandler(BasicDBHandler):
    __single = None
    lock = threading.Lock()

    @staticmethod
    def getInstance(*args, **kw):
        if TsPlayersDBHandler.__single is None:
            TsPlayersDBHandler.lock.acquire()
            try:
                if TsPlayersDBHandler.__single is None:
                    TsPlayersDBHandler(*args, **kw)
            finally:
                TsPlayersDBHandler.lock.release()

        return TsPlayersDBHandler.__single

    def __init__(self):
        if TsPlayersDBHandler.__single is not None:
            raise RuntimeError, 'TsPlayersDBHandler is singleton'
        TsPlayersDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self, db, 'ts_players')

    def get(self, player_id):
        keys = ['checksum',
         'infohash',
         'developer_id',
         'affiliate_id',
         'zone_id']
        res = self.getOne(keys, player_id=player_id)
        if res is None:
            return
        res = dict(zip(keys, res))
        res['infohash'] = str2bin(res['infohash'])
        res['checksum'] = str2bin(res['checksum'])
        return res

    def getPlayerId(self, checksum, infohash, developer_id, affiliate_id, zone_id):
        if checksum is None:
            player_id = self.getOne('player_id', infohash=bin2str(infohash), developer_id=developer_id, affiliate_id=affiliate_id, zone_id=zone_id)
        else:
            player_id = self.getOne('player_id', checksum=bin2str(checksum), infohash=bin2str(infohash), developer_id=developer_id, affiliate_id=affiliate_id, zone_id=zone_id)
        return player_id

    def put(self, player_id, checksum, infohash, developer_id, affiliate_id, zone_id, commit = True):
        if self.getOne('infohash', player_id=player_id) is NULL:
            self._db.insert(self.table_name, commit=commit, player_id=player_id, checksum=bin2str(checksum), infohash=bin2str(infohash), developer_id=developer_id, affiliate_id=affiliate_id, zone_id=zone_id)


class TsMetadataDBHandler(BasicDBHandler):
    __single = None
    lock = threading.Lock()

    @staticmethod
    def getInstance(*args, **kw):
        if TsMetadataDBHandler.__single is None:
            TsMetadataDBHandler.lock.acquire()
            try:
                if TsMetadataDBHandler.__single is None:
                    TsMetadataDBHandler(*args, **kw)
            finally:
                TsMetadataDBHandler.lock.release()

        return TsMetadataDBHandler.__single

    def __init__(self):
        if TsMetadataDBHandler.__single is not None:
            raise RuntimeError, 'TsMetadataDBHandler is singleton'
        TsMetadataDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self, db, 'ts_metadata')

    def get(self, infohash):
        keys = ['idx',
         'duration',
         'prebuf_pieces',
         'replace_mp4_metatags']
        res = self.getAll(keys, infohash=bin2str(infohash))
        if not res:
            return None
        if DEBUG:
            log('TsMetadataDBHandler::get: infohash', bin2str(infohash), 'res', res)
        metadata = {}
        for row in res:
            row = dict(zip(keys, row))
            k = 'f' + str(row['idx'])
            if row['duration']:
                metadata.setdefault('duration', {})[k] = row['duration']
            if row['prebuf_pieces']:
                metadata.setdefault('prebuf_pieces', {})[k] = row['prebuf_pieces']
            if row['replace_mp4_metatags']:
                metadata.setdefault('rpmp4mt', {})[k] = row['replace_mp4_metatags']

        if DEBUG:
            log('TsMetadataDBHandler::get: metadata', metadata)
        return metadata

    def put(self, infohash, metadata, commit = True):
        if DEBUG:
            log('TsMetadataDBHandler::put: infohash', bin2str(infohash), 'metadata', metadata)
        data = {}
        if metadata.has_key('duration'):
            for idx, duration in metadata['duration'].iteritems():
                data.setdefault(idx, {})['duration'] = duration

        if metadata.has_key('prebuf_pieces'):
            for idx, prebuf_pieces in metadata['prebuf_pieces'].iteritems():
                data.setdefault(idx, {})['prebuf_pieces'] = prebuf_pieces

        if metadata.has_key('rpmp4mt'):
            for idx, replace_mp4_metatags in metadata['rpmp4mt'].iteritems():
                data.setdefault(idx, {})['replace_mp4_metatags'] = replace_mp4_metatags

        if DEBUG:
            log('TsMetadataDBHandler::put: formatted data:', data)
        for idx, meta in data.iteritems():
            idx = int(idx.replace('f', ''))
            self._db.insert_or_replace(self.table_name, commit=commit, infohash=bin2str(infohash), idx=idx, **meta)


class TorrentDBHandler(BasicDBHandler):
    __single = None
    lock = threading.Lock()

    @staticmethod
    def getInstance(*args, **kw):
        if TorrentDBHandler.__single is None:
            TorrentDBHandler.lock.acquire()
            try:
                if TorrentDBHandler.__single is None:
                    TorrentDBHandler(*args, **kw)
            finally:
                TorrentDBHandler.lock.release()

        return TorrentDBHandler.__single

    def __init__(self):
        if TorrentDBHandler.__single is not None:
            raise RuntimeError, 'TorrentDBHandler is singleton'
        TorrentDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self, db, 'Torrent')
        self.status_table = {'good': 1,
         'unknown': 0,
         'dead': 2}
        self.status_table.update(self._db.getTorrentStatusTable())
        self.id2status = dict([ (x, y) for y, x in self.status_table.items() ])
        self.torrent_dir = None
        self.category_table = {'Video': 1,
         'VideoClips': 2,
         'Audio': 3,
         'Compressed': 4,
         'Document': 5,
         'Picture': 6,
         'xxx': 7,
         'other': 8}
        self.category_table.update(self._db.getTorrentCategoryTable())
        self.category_table['unknown'] = 0
        self.id2category = dict([ (x, y) for y, x in self.category_table.items() ])
        self.src_table = self._db.getTorrentSourceTable()
        self.id2src = dict([ (x, y) for y, x in self.src_table.items() ])
        self.keys = ['torrent_id',
         'checksum',
         'name',
         'torrent_file_name',
         'length',
         'creation_date',
         'num_files',
         'thumbnail',
         'insert_time',
         'secret',
         'relevance',
         'source_id',
         'category_id',
         'status_id',
         'num_seeders',
         'num_leechers',
         'comment']
        self.existed_torrents = set()
        self.value_name = ['C.torrent_id',
         'category_id',
         'status_id',
         'name',
         'creation_date',
         'num_files',
         'num_leechers',
         'num_seeders',
         'length',
         'secret',
         'insert_time',
         'source_id',
         'torrent_file_name',
         'relevance',
         'infohash',
         'tracker',
         'last_check']
        self.value_name_for_channel = ['C.torrent_id',
         'infohash',
         'name',
         'torrent_file_name',
         'length',
         'creation_date',
         'num_files',
         'thumbnail',
         'insert_time',
         'secret',
         'relevance',
         'source_id',
         'category_id',
         'status_id',
         'num_seeders',
         'num_leechers',
         'comment']

    def register(self, category, torrent_dir):
        self.category = category
        self.torrent_dir = torrent_dir

    def getTorrentID(self, infohash):
        return self._db.getTorrentID(infohash)

    def getTorrentIDByChecksum(self, checksum):
        return self._db.getTorrentIDByChecksum(checksum)

    def getTorrentIDS(self, infohashes):
        for infohash in infohashes:
            pass

        return self._db.getTorrentIDS(infohashes)

    def getInfohash(self, torrent_id):
        return self._db.getInfohash(torrent_id)

    def hasTorrent(self, infohash, checksum = None):
        if (infohash, checksum) in self.existed_torrents:
            return True
        else:
            kw = {'infohash': bin2str(infohash)}
            if checksum is not None:
                kw['checksum'] = bin2str(checksum)
            existed = self._db.getOne('CollectedTorrent', 'torrent_id', **kw)
            if existed is None:
                return False
            self.existed_torrents.add((infohash, checksum))
            return True

    def addExternalTorrent(self, torrentdef, source = 'TS', extra_info = {}, commit = True):
        if torrentdef.is_finalized():
            infohash = torrentdef.get_infohash()
            checksum = extra_info.get('checksum', None)
            if not self.hasTorrent(infohash, checksum):
                try:
                    self._addTorrentToDB(torrentdef, source, extra_info, commit)
                    self.notifier.notify(NTFY_TORRENTS, NTFY_INSERT, infohash)
                except:
                    print_exc()
                    if checksum is not None:
                        print >> sys.stderr, 'delete from db: checksum', checksum
                        self.deleteTorrentByChecksum(checksum)

    def addInfohash(self, infohash, commit = True):
        if self._db.getTorrentID(infohash) is None:
            self._db.insert('Torrent', commit=commit, infohash=bin2str(infohash))

    def addOrGetTorrentID(self, infohash):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is None:
            self._db.insert('Torrent', commit=True, infohash=bin2str(infohash), status_id=self._getStatusID('good'))
            torrent_id = self._db.getTorrentID(infohash)
        return torrent_id

    def addOrGetTorrentIDS(self, infohashes):
        if len(infohashes) == 1:
            return [self.addOrGetTorrentID(infohashes[0])]
        to_be_inserted = []
        torrent_ids = self._db.getTorrentIDS(infohashes)
        for i in range(len(torrent_ids)):
            torrent_id = torrent_ids[i]
            if torrent_id is None:
                to_be_inserted.append(infohashes[i])

        status_id = self._getStatusID('good')
        sql = 'INSERT OR IGNORE INTO Torrent (infohash, status_id) VALUES (?, ?)'
        self._db.executemany(sql, [ (bin2str(infohash), status_id) for infohash in to_be_inserted ])
        return self._db.getTorrentIDS(infohashes)

    def _getStatusID(self, status):
        return self.status_table.get(status.lower(), 0)

    def _getCategoryID(self, category_list):
        if len(category_list) > 0:
            category = category_list[0].lower()
            cat_int = self.category_table[category]
        else:
            cat_int = 0
        return cat_int

    def _getSourceID(self, src):
        if src in self.src_table:
            src_int = self.src_table[src]
        else:
            src_int = self._insertNewSrc(src)
            self.src_table[src] = src_int
            self.id2src[src_int] = src
        return src_int

    def _get_database_dict(self, torrentdef, source = 'TS', extra_info = {}):
        mime, thumb = torrentdef.get_thumbnail()
        checksum = extra_info.get('checksum', None)
        if checksum is not None:
            checksum = bin2str(checksum)
        return {'infohash': bin2str(torrentdef.get_infohash()),
         'checksum': checksum,
         'name': torrentdef.get_name_as_unicode(),
         'torrent_file_name': extra_info.get('filename', None),
         'length': torrentdef.get_length(),
         'creation_date': torrentdef.get_creation_date(),
         'num_files': len(torrentdef.get_files()),
         'thumbnail': bool(thumb),
         'insert_time': long(time()),
         'secret': 0,
         'relevance': 0.0,
         'source_id': self._getSourceID(source),
         'category_id': self._getCategoryID(self.category.calculateCategory(torrentdef.metainfo, torrentdef.get_name_as_unicode())),
         'status_id': self._getStatusID(extra_info.get('status', 'unknown')),
         'num_seeders': extra_info.get('seeder', -1),
         'num_leechers': extra_info.get('leecher', -1),
         'comment': torrentdef.get_comment_as_unicode()}

    def _addTorrentToDB(self, torrentdef, source, extra_info, commit):
        infohash = torrentdef.get_infohash()
        torrent_name = torrentdef.get_name_as_unicode()
        database_dict = self._get_database_dict(torrentdef, source, extra_info)
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is None:
            self._db.insert('Torrent', commit=True, **database_dict)
            torrent_id = self._db.getTorrentID(infohash)
        else:
            where = 'torrent_id = %d' % torrent_id
            self._db.update('Torrent', where=where, commit=False, **database_dict)
        self._addTorrentTracker(torrent_id, torrentdef, extra_info, commit=False)
        if commit:
            self.commit()
        return torrent_id

    def getInfohashFromTorrentName(self, name):
        sql = "select infohash from Torrent where name='" + str2bin(name) + "'"
        infohash = self._db.fetchone(sql)
        return infohash

    def _insertNewSrc(self, src, commit = True):
        desc = ''
        if src.startswith('http') and src.endswith('xml'):
            desc = 'RSS'
        self._db.insert('TorrentSource', commit=commit, name=src, description=desc)
        src_id = self._db.getOne('TorrentSource', 'source_id', name=src)
        return src_id

    def _addTorrentTracker(self, torrent_id, torrentdef, extra_info = {}, add_all = False, commit = True):
        exist = self._db.getOne('TorrentTracker', 'tracker', torrent_id=torrent_id)
        if exist:
            return
        announce = torrentdef.get_tracker()
        announce_list = torrentdef.get_tracker_hierarchy()
        ignore_number = 0
        retry_number = 0
        last_check_time = 0
        if 'last_check_time' in extra_info:
            last_check_time = int(time() - extra_info['last_check_time'])
        sql_insert_torrent_tracker = '\n        INSERT INTO TorrentTracker\n        (torrent_id, tracker, announce_tier, \n        ignored_times, retried_times, last_check)\n        VALUES (?,?,?, ?,?,?)\n        '
        values = []
        if announce != None:
            values.append((torrent_id,
             announce,
             1,
             ignore_number,
             retry_number,
             last_check_time))
        tier_num = 2
        trackers = {announce: None}
        if add_all:
            for tier in announce_list:
                for tracker in tier:
                    if tracker in trackers:
                        continue
                    value = (torrent_id,
                     tracker,
                     tier_num,
                     0,
                     0,
                     0)
                    values.append(value)
                    trackers[tracker] = None

                tier_num += 1

        if len(values) > 0:
            self._db.executemany(sql_insert_torrent_tracker, values, commit=commit)

    def updateTorrent(self, infohash, commit = True, **kw):
        if 'category' in kw:
            cat_id = self._getCategoryID(kw.pop('category'))
            kw['category_id'] = cat_id
        if 'status' in kw:
            status_id = self._getStatusID(kw.pop('status'))
            kw['status_id'] = status_id
        if 'seeder' in kw:
            kw['num_seeders'] = kw.pop('seeder')
        if 'leecher' in kw:
            kw['num_leechers'] = kw.pop('leecher')
        if 'last_check_time' in kw or 'ignore_number' in kw or 'retry_number' in kw or 'retried_times' in kw or 'ignored_times' in kw:
            self.updateTracker(infohash, kw, commit=False)
        for key in kw.keys():
            if key not in self.keys:
                kw.pop(key)

        if len(kw) > 0:
            infohash_str = bin2str(infohash)
            where = "infohash='%s'" % infohash_str
            self._db.update(self.table_name, where, commit=False, **kw)
        if commit:
            self.commit()
        self.notifier.notify(NTFY_TORRENTS, NTFY_UPDATE, infohash)

    def updateTracker(self, infohash, kw, tier = 1, tracker = None, commit = True):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is None:
            return
        update = {}
        if 'last_check_time' in kw:
            update['last_check'] = kw.pop('last_check_time')
        if 'ignore_number' in kw:
            update['ignored_times'] = kw.pop('ignore_number')
        if 'ignored_times' in kw:
            update['ignored_times'] = kw.pop('ignored_times')
        if 'retry_number' in kw:
            update['retried_times'] = kw.pop('retry_number')
        if 'retried_times' in kw:
            update['retried_times'] = kw.pop('retried_times')
        if tracker is None:
            where = 'torrent_id=%d AND announce_tier=%d' % (torrent_id, tier)
        else:
            where = 'torrent_id=%d AND tracker=%s' % (torrent_id, repr(tracker))
        self._db.update('TorrentTracker', where, commit=commit, **update)

    def deleteTorrent(self, infohash, delete_file = False, commit = True):
        if not self.hasTorrent(infohash):
            return False
        if delete_file:
            deleted = self.eraseTorrentFile(infohash)
        else:
            deleted = True
        if deleted:
            self._deleteTorrent(infohash, commit=commit)
        self.notifier.notify(NTFY_TORRENTS, NTFY_DELETE, infohash)
        return deleted

    def deleteTorrentByChecksum(self, checksum, commit = True):
        torrent_id = self._db.getTorrentIDByChecksum(checksum)
        if torrent_id is not None:
            self._db.delete(self.table_name, commit=commit, torrent_id=torrent_id)
            self._db.delete('TorrentTracker', commit=commit, torrent_id=torrent_id)
            self.existed_torrents = [ (_infohash, _checksum) for _infohash, _checksum in self.existed_torrents if _checksum is None or _checksum != checksum ]

    def _deleteTorrent(self, infohash, keep_infohash = True, commit = True):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is not None:
            if keep_infohash:
                self._db.update(self.table_name, where='torrent_id=%d' % torrent_id, commit=commit, torrent_file_name=None)
            else:
                self._db.delete(self.table_name, commit=commit, torrent_id=torrent_id)
            self.existed_torrents = [ (_infohash, _checksum) for _infohash, _checksum in self.existed_torrents if _infohash != infohash ]
            self._db.delete('TorrentTracker', commit=commit, torrent_id=torrent_id)

    def eraseTorrentFile(self, infohash):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is not None:
            torrent_dir = self.getTorrentDir()
            torrent_name = self.getOne('torrent_file_name', torrent_id=torrent_id)
            src = os.path.join(torrent_dir, torrent_name)
            if not os.path.exists(src):
                return True
            try:
                os.remove(src)
            except Exception as msg:
                print >> sys.stderr, 'cachedbhandler: failed to erase torrent', src, Exception, msg
                return False

        return True

    def getTracker(self, infohash, tier = 0):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is not None:
            sql = 'SELECT tracker, announce_tier FROM TorrentTracker WHERE torrent_id==%d' % torrent_id
            if tier > 0:
                sql += ' AND announce_tier<=%d' % tier
            return self._db.fetchall(sql)

    def getSwarmInfo(self, torrent_id):
        if torrent_id is not None:
            dict = self.getSwarmInfos([torrent_id])
            if torrent_id in dict:
                return dict[torrent_id]

    def getSwarmInfos(self, torrent_id_list):
        torrent_id_list = [ torrent_id for torrent_id in torrent_id_list if torrent_id ]
        results = {}
        sql = 'SELECT t.torrent_id, t.num_seeders, t.num_leechers, max(last_check) FROM Torrent t, TorrentTracker tr WHERE t.torrent_id in ('
        sql += ','.join(map(str, torrent_id_list))
        sql += ') AND t.torrent_id = tr.torrent_id GROUP BY t.torrent_id'
        rows = self._db.fetchall(sql)
        for row in rows:
            torrent_id = row[0]
            num_seeders = row[1]
            num_leechers = row[2]
            last_check = row[3]
            results[torrent_id] = [torrent_id,
             num_seeders,
             num_leechers,
             last_check,
             -1,
             row]

        return results

    def getTorrentDir(self):
        return self.torrent_dir

    def updateTorrentDir(self, torrent_dir):
        sql = 'SELECT torrent_id, torrent_file_name FROM Torrent WHERE torrent_file_name not NULL'
        results = self._db.fetchall(sql)
        updates = []
        for result in results:
            head, tail = os.path.split(result[1])
            new_file_name = os.path.join(torrent_dir, tail)
            updates.append((new_file_name, result[0]))

        sql = 'UPDATE TORRENT SET torrent_file_name = ? WHERE torrent_id = ?'
        self._db.executemany(sql, updates)
        self.torrent_dir = torrent_dir

    def getTorrent(self, checksum = None, infohash = None, keys = None, include_mypref = True):
        if checksum is None and infohash is None:
            return
        if infohash is not None:
            pass
        if keys is None:
            keys = deepcopy(self.value_name)
        else:
            keys = list(keys)
        keys.append('infohash')
        keys.append('checksum')
        where = 'C.torrent_id = T.torrent_id and announce_tier=1 '
        if checksum is not None:
            res = self._db.getOne('CollectedTorrent C, TorrentTracker T', keys, where=where, checksum=bin2str(checksum))
        else:
            res = self._db.getOne('CollectedTorrent C, TorrentTracker T', keys, where=where, infohash=bin2str(infohash))
        if not res:
            return
        if not isinstance(res, (tuple, list)):
            res = (res,)
        torrent = dict(zip(keys, res))
        if 'source_id' in torrent:
            torrent['source'] = self.id2src[torrent['source_id']]
            del torrent['source_id']
        if 'category_id' in torrent:
            torrent['category'] = [self.id2category[torrent['category_id']]]
            del torrent['category_id']
        if 'status_id' in torrent:
            torrent['status'] = self.id2status[torrent['status_id']]
            del torrent['status_id']
        torrent['checksum'] = str2bin(torrent['checksum'])
        torrent['infohash'] = str2bin(torrent['infohash'])
        if 'last_check' in torrent:
            torrent['last_check_time'] = torrent['last_check']
            del torrent['last_check']
        return torrent

    def getNumberTorrents(self, category_name = 'all', library = False):
        table = 'CollectedTorrent'
        value = 'count(torrent_id)'
        where = '1 '
        library = False
        if category_name != 'all':
            where += ' and category_id= %d' % self.category_table.get(category_name.lower(), -1)
        if library:
            where += ' and torrent_id in (select torrent_id from MyPreference where destination_path != "")'
        else:
            where += ' and status_id=%d ' % self.status_table['good']
            where += self.category.get_family_filter_sql(self._getCategoryID)
        number = self._db.getOne(table, value, where)
        if not number:
            number = 0
        return number

    def getTorrents(self, category_name = 'all', range = None, library = False, sort = None, reverse = False):
        library = False
        s = time()
        value_name = deepcopy(self.value_name)
        sql = 'Select ' + ','.join(value_name)
        sql += ' From CollectedTorrent C Left Join TorrentTracker T ON C.torrent_id = T.torrent_id'
        where = ''
        if category_name != 'all':
            where += 'category_id = %d AND' % self.category_table.get(category_name.lower(), -1)
        if library:
            where += 'C.torrent_id in (select torrent_id from MyPreference where destination_path != "")'
        else:
            where += 'status_id=%d ' % self.status_table['good']
            where += self.category.get_family_filter_sql(self._getCategoryID)
        sql += ' Where ' + where
        if range:
            offset = range[0]
            limit = range[1] - range[0]
            sql += ' Limit %d Offset %d' % (limit, offset)
        if sort:
            desc = reverse and 'desc' or ''
            if sort in 'name':
                sql += ' Order By lower(%s) %s' % (sort, desc)
            else:
                sql += ' Order By %s %s' % (sort, desc)
        ranks = self.getRanks()
        res_list = self._db.fetchall(sql)
        torrent_list = self.valuelist2torrentlist(value_name, res_list, ranks, mypref_stats)
        del res_list
        del mypref_stats
        return torrent_list

    def valuelist2torrentlist(self, value_name, res_list, ranks, mypref_stats):
        torrent_list = []
        for item in res_list:
            value_name[0] = 'torrent_id'
            torrent = dict(zip(value_name, item))
            try:
                torrent['source'] = self.id2src[torrent['source_id']]
            except:
                print_exc()
                torrent['source'] = 'http://some/RSS/feed'

            torrent['category'] = [self.id2category[torrent['category_id']]]
            torrent['status'] = self.id2status[torrent['status_id']]
            torrent['simRank'] = ranksfind(ranks, torrent['infohash'])
            torrent['infohash'] = str2bin(torrent['infohash'])
            torrent['last_check_time'] = torrent['last_check']
            del torrent['last_check']
            del torrent['source_id']
            del torrent['category_id']
            del torrent['status_id']
            torrent_id = torrent['torrent_id']
            if mypref_stats is not None and torrent_id in mypref_stats:
                torrent['myDownloadHistory'] = True
                data = mypref_stats[torrent_id]
                torrent['download_started'] = data[0]
                torrent['progress'] = data[1]
                torrent['destdir'] = data[2]
            torrent_list.append(torrent)

        return torrent_list

    def getRanks(self):
        value_name = 'infohash'
        order_by = 'relevance desc'
        rankList_size = 20
        where = 'status_id=%d ' % self.status_table['good']
        res_list = self._db.getAll('Torrent', value_name, where=where, limit=rankList_size, order_by=order_by)
        return [ a[0] for a in res_list ]

    def getNumberCollectedTorrents(self):
        return self._db.getOne('CollectedTorrent', 'count(torrent_id)')

    def getTorrentsStats(self):
        return self._db.getOne('CollectedTorrent', ['count(torrent_id)', 'sum(length)', 'sum(num_files)'])

    def freeSpace(self, torrents2del):
        sql = '\n            select torrent_file_name, torrent_id, infohash, relevance,\n                min(relevance,2500) +  min(500,num_leechers) + 4*min(500,num_seeders) - (max(0,min(500,(%d-creation_date)/86400)) ) as weight\n            from CollectedTorrent\n            where  torrent_id not in (select torrent_id from MyPreference)\n            order by weight  \n            limit %d                                  \n        ' % (int(time()), torrents2del)
        res_list = self._db.fetchall(sql)
        if len(res_list) == 0:
            return False
        sql_del_torrent = 'delete from Torrent where torrent_id=?'
        sql_del_tracker = 'delete from TorrentTracker where torrent_id=?'
        tids = [ (torrent_id,) for torrent_file_name, torrent_id, infohash, relevance, weight in res_list ]
        self._db.executemany(sql_del_torrent, tids, commit=False)
        self._db.executemany(sql_del_tracker, tids, commit=False)
        self._db.commit()
        torrent_dir = self.getTorrentDir()
        deleted = 0
        for torrent_file_name, torrent_id, infohash, relevance, weight in res_list:
            torrent_path = os.path.join(torrent_dir, torrent_file_name)
            try:
                os.remove(torrent_path)
                print >> sys.stderr, 'Erase torrent:', os.path.basename(torrent_path)
                deleted += 1
            except Exception as msg:
                pass

        self.notifier.notify(NTFY_TORRENTS, NTFY_DELETE, str2bin(infohash))
        return deleted

    def hasMetaData(self, infohash):
        return self.hasTorrent(infohash)

    def getTorrentRelevances(self, tids):
        sql = 'SELECT torrent_id, relevance from Torrent WHERE torrent_id in ' + str(tuple(tids))
        return self._db.fetchall(sql)

    def updateTorrentRelevance(self, infohash, relevance):
        self.updateTorrent(infohash, relevance=relevance)

    def updateTorrentRelevances(self, tid_rel_pairs, commit = True):
        if len(tid_rel_pairs) > 0:
            sql_update_sims = 'UPDATE Torrent SET relevance=? WHERE torrent_id=?'
            self._db.executemany(sql_update_sims, tid_rel_pairs, commit=commit)

    def selectTorrentToCheck(self, policy = 'random', infohash = None, return_value = None):
        if infohash is None:
            sql = 'select T.torrent_id, ignored_times, retried_times, torrent_file_name, infohash, status_id, num_seeders, num_leechers, last_check \n                     from CollectedTorrent T, TorrentTracker TT\n                     where TT.torrent_id=T.torrent_id and announce_tier=1 '
            if policy.lower() == 'random':
                ntorrents = self.getNumberCollectedTorrents()
                if ntorrents == 0:
                    rand_pos = 0
                else:
                    rand_pos = randint(0, ntorrents - 1)
                last_check_threshold = int(time()) - 300
                sql += 'and last_check < %d \n                        limit 1 offset %d ' % (last_check_threshold, rand_pos)
            elif policy.lower() == 'oldest':
                last_check_threshold = int(time()) - 300
                sql += ' and last_check < %d and status_id <> 2\n                         order by last_check\n                         limit 1 ' % last_check_threshold
            elif policy.lower() == 'popular':
                last_check_threshold = int(time()) - 14400
                sql += ' and last_check < %d and status_id <> 2 \n                         order by 3*num_seeders+num_leechers desc\n                         limit 1 ' % last_check_threshold
            res = self._db.fetchone(sql)
        else:
            sql = 'select T.torrent_id, ignored_times, retried_times, torrent_file_name, infohash, status_id, num_seeders, num_leechers, last_check \n                     from CollectedTorrent T, TorrentTracker TT\n                     where TT.torrent_id=T.torrent_id and announce_tier=1\n                     and infohash=? \n                  '
            infohash_str = bin2str(infohash)
            res = self._db.fetchone(sql, (infohash_str,))
        if res:
            torrent_file_name = res[3]
            torrent_dir = self.getTorrentDir()
            torrent_path = os.path.join(torrent_dir, torrent_file_name)
            if res is not None:
                res = {'torrent_id': res[0],
                 'ignored_times': res[1],
                 'retried_times': res[2],
                 'torrent_path': torrent_path,
                 'infohash': str2bin(res[4])}
            return_value['torrent'] = res
        return_value['event'].set()

    def getTorrentsFromSource(self, source):
        id = self._getSourceID(source)
        where = 'C.source_id = %d and C.torrent_id = T.torrent_id and announce_tier=1' % id
        where += self.category.get_family_filter_sql(self._getCategoryID)
        value_name = deepcopy(self.value_name)
        res_list = self._db.getAll('Torrent C, TorrentTracker T', value_name, where)
        torrent_list = self.valuelist2torrentlist(value_name, res_list, None, None)
        del res_list
        return torrent_list

    def setSecret(self, infohash, secret):
        kw = {'secret': secret}
        self.updateTorrent(infohash, commit=True, **kw)
