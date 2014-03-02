#Embedded file name: ACEStream\Core\CacheDB\MetadataDBHandler.pyo
from ACEStream.Core.Subtitles.MetadataDomainObjects.SubtitleInfo import SubtitleInfo
from ACEStream.Core.Subtitles.MetadataDomainObjects.MetadataDTO import MetadataDTO
from ACEStream.Core.CacheDB.SqliteCacheDBHandler import BasicDBHandler
import threading
from ACEStream.Core.CacheDB.sqlitecachedb import SQLiteCacheDB
import sys
from ACEStream.Core.Subtitles.MetadataDomainObjects.MetadataExceptions import SignatureException, MetadataDBException
from ACEStream.Core.Utilities.utilities import bin2str, str2bin
import sqlite3
import time
SUBTITLE_LANGUAGE_CODE = 'lang'
SUBTITLE_PATH = 'path'
METADATA_TABLE = 'Metadata'
MD_ID_KEY = 'metadata_id'
MD_PUBLISHER_KEY = 'publisher_id'
MD_INFOHASH_KEY = 'infohash'
MD_DESCRIPTION_KEY = 'description'
MD_TIMESTAMP_KEY = 'timestamp'
MD_SIGNATURE_KEY = 'signature'
SUBTITLES_TABLE = 'Subtitles'
SUB_MD_FK_KEY = 'metadata_id_fk'
SUB_LANG_KEY = 'subtitle_lang'
SUB_LOCATION_KEY = 'subtitle_location'
SUB_CHECKSUM_KEY = 'checksum'
SUBTITLES_HAVE_TABLE = 'SubtitlesHave'
SH_MD_FK_KEY = 'metadata_id_fk'
SH_PEER_ID_KEY = 'peer_id'
SH_HAVE_MASK_KEY = 'have_mask'
SH_TIMESTAMP = 'received_ts'
SH_RESULTS_LIMIT = 200
DEBUG = False
SELECT_SUBS_JOIN_BASE = 'SELECT sub.' + SUB_MD_FK_KEY + ', sub.' + SUB_LANG_KEY + ', sub.' + SUB_LOCATION_KEY + ', sub.' + SUB_CHECKSUM_KEY + ' FROM ' + METADATA_TABLE + ' AS md ' + 'INNER JOIN ' + SUBTITLES_TABLE + ' AS sub ' + 'ON md.' + MD_ID_KEY + ' = sub.' + SUB_MD_FK_KEY
MD_SH_JOIN_CLAUSE = METADATA_TABLE + ' AS md ' + 'INNER JOIN ' + SUBTITLES_HAVE_TABLE + ' AS sh ' + 'ON md.' + MD_ID_KEY + ' = sh.' + SH_MD_FK_KEY
QUERIES = {'SELECT SUBS JOIN HASH ALL': SELECT_SUBS_JOIN_BASE + ' WHERE md.' + MD_INFOHASH_KEY + ' = ?' + ' AND md.' + MD_PUBLISHER_KEY + ' = ?;',
 'SELECT SUBS JOIN HASH ONE': SELECT_SUBS_JOIN_BASE + ' WHERE md.' + MD_INFOHASH_KEY + ' = ?' + ' AND md.' + MD_PUBLISHER_KEY + ' = ?' + ' AND sub.' + SUB_LANG_KEY + ' = ?;',
 'SELECT SUBS FK ALL': 'SELECT * FROM ' + SUBTITLES_TABLE + ' WHERE ' + SUB_MD_FK_KEY + ' = ?;',
 'SELECT SUBS FK ONE': 'SELECT * FROM ' + SUBTITLES_TABLE + ' WHERE ' + SUB_MD_FK_KEY + ' = ?' + ' AND ' + SUB_LANG_KEY + ' = ?;',
 'SELECT METADATA': 'SELECT * FROM ' + METADATA_TABLE + ' WHERE ' + MD_INFOHASH_KEY + ' = ?' + ' AND ' + MD_PUBLISHER_KEY + ' = ?;',
 'SELECT NRMETADATA': 'SELECT COUNT(*) FROM ' + METADATA_TABLE + ' WHERE ' + MD_PUBLISHER_KEY + ' = ?;',
 'SELECT PUBLISHERS FROM INFOHASH': 'SELECT ' + MD_PUBLISHER_KEY + ' FROM ' + METADATA_TABLE + ' WHERE ' + MD_INFOHASH_KEY + ' = ?;',
 'UPDATE METADATA': 'UPDATE ' + METADATA_TABLE + ' SET ' + MD_DESCRIPTION_KEY + ' = ?, ' + MD_TIMESTAMP_KEY + ' = ?, ' + MD_SIGNATURE_KEY + ' = ?' + ' WHERE ' + MD_INFOHASH_KEY + ' = ?' + ' AND ' + MD_PUBLISHER_KEY + ' = ?;',
 'UPDATE SUBTITLES': 'UPDATE ' + SUBTITLES_TABLE + ' SET ' + SUB_LOCATION_KEY + '= ?, ' + SUB_CHECKSUM_KEY + '= ?' + ' WHERE ' + SUB_MD_FK_KEY + '= ?' + ' AND ' + SUB_LANG_KEY + '= ?;',
 'DELETE ONE SUBTITLES': 'DELETE FROM ' + SUBTITLES_TABLE + ' WHERE ' + SUB_MD_FK_KEY + '= ? ' + ' AND ' + SUB_LANG_KEY + '= ?;',
 'DELETE ONE SUBTITLE JOIN': 'DELETE FROM ' + SUBTITLES_TABLE + ' WHERE ' + SUB_MD_FK_KEY + ' IN ( SELECT ' + MD_ID_KEY + ' FROM ' + METADATA_TABLE + ' WHERE ' + MD_PUBLISHER_KEY + ' = ?' + ' AND ' + MD_INFOHASH_KEY + ' = ? )' + ' AND ' + SUB_LANG_KEY + '= ?;',
 'DELETE ALL SUBTITLES': 'DELETE FROM ' + SUBTITLES_TABLE + ' WHERE ' + SUB_MD_FK_KEY + '= ?;',
 'DELETE METADATA PK': 'DELETE FROM ' + METADATA_TABLE + ' WHERE ' + MD_ID_KEY + ' = ?;',
 'INSERT METADATA': 'INSERT or IGNORE INTO ' + METADATA_TABLE + ' VALUES ' + '(NULL,?,?,?,?,?)',
 'INSERT SUBTITLES': 'INSERT INTO ' + SUBTITLES_TABLE + ' VALUES (?, ?, ?, ?);',
 'SELECT SUBTITLES WITH PATH': 'SELECT sub.' + SUB_MD_FK_KEY + ', sub.' + SUB_LOCATION_KEY + ', sub.' + SUB_LANG_KEY + ', sub.' + SUB_CHECKSUM_KEY + ', m.' + MD_PUBLISHER_KEY + ', m.' + MD_INFOHASH_KEY + ' FROM ' + METADATA_TABLE + ' AS m ' + 'INNER JOIN ' + SUBTITLES_TABLE + ' AS sub ' + 'ON m.' + MD_ID_KEY + ' = ' + ' sub.' + SUB_MD_FK_KEY + ' WHERE ' + SUB_LOCATION_KEY + ' IS NOT NULL;',
 'SELECT SUBTITLES WITH PATH BY CHN INFO': 'SELECT sub.' + SUB_LOCATION_KEY + ', sub.' + SUB_LANG_KEY + ', sub.' + SUB_CHECKSUM_KEY + ' FROM ' + METADATA_TABLE + ' AS m ' + 'INNER JOIN ' + SUBTITLES_TABLE + ' AS sub ' + 'ON m.' + MD_ID_KEY + ' = ' + ' sub.' + SUB_MD_FK_KEY + ' WHERE sub.' + SUB_LOCATION_KEY + ' IS NOT NULL' + ' AND m.' + MD_PUBLISHER_KEY + ' = ?' + ' AND m.' + MD_INFOHASH_KEY + ' = ?;',
 'INSERT HAVE MASK': 'INSERT INTO ' + SUBTITLES_HAVE_TABLE + ' VALUES ' + '(?, ?, ?, ?);',
 'GET ALL HAVE MASK': 'SELECT sh.' + SH_PEER_ID_KEY + ', sh.' + SH_HAVE_MASK_KEY + ', sh.' + SH_TIMESTAMP + ' FROM ' + MD_SH_JOIN_CLAUSE + ' WHERE md.' + MD_PUBLISHER_KEY + ' = ? AND md.' + MD_INFOHASH_KEY + ' = ? ' + 'ORDER BY sh.' + SH_TIMESTAMP + ' DESC' + ' LIMIT ' + str(SH_RESULTS_LIMIT) + ';',
 'GET ONE HAVE MASK': 'SELECT sh.' + SH_HAVE_MASK_KEY + ', sh.' + SH_TIMESTAMP + ' FROM ' + MD_SH_JOIN_CLAUSE + ' WHERE md.' + MD_PUBLISHER_KEY + ' = ? AND md.' + MD_INFOHASH_KEY + ' = ? AND sh.' + SH_PEER_ID_KEY + ' = ?;',
 'UPDATE HAVE MASK': 'UPDATE ' + SUBTITLES_HAVE_TABLE + ' SET ' + SH_HAVE_MASK_KEY + ' = ?, ' + SH_TIMESTAMP + ' = ?' + ' WHERE ' + SH_PEER_ID_KEY + ' = ?' + ' AND ' + SH_MD_FK_KEY + ' IN ' + '( SELECT + ' + MD_ID_KEY + ' FROM ' + METADATA_TABLE + ' WHERE + ' + MD_PUBLISHER_KEY + ' = ?' + ' AND ' + MD_INFOHASH_KEY + ' = ? );',
 'DELETE HAVE': 'DELETE FROM ' + SUBTITLES_HAVE_TABLE + ' WHERE ' + SH_PEER_ID_KEY + ' = ?' + ' AND ' + SH_MD_FK_KEY + ' IN ' + '( SELECT + ' + MD_ID_KEY + ' FROM ' + METADATA_TABLE + ' WHERE + ' + MD_PUBLISHER_KEY + ' = ?' + ' AND ' + MD_INFOHASH_KEY + ' = ? );',
 'CLEANUP OLD HAVE': 'DELETE FROM ' + SUBTITLES_HAVE_TABLE + ' WHERE ' + SH_TIMESTAMP + ' < ? ' + ' AND ' + SH_PEER_ID_KEY + ' NOT IN ' + '( SELECT md.' + MD_PUBLISHER_KEY + ' FROM ' + METADATA_TABLE + ' AS md WHERE md.' + MD_ID_KEY + ' = ' + SH_MD_FK_KEY + ' );'}

class MetadataDBHandler(object, BasicDBHandler):
    __single = None
    _lock = threading.RLock()

    @staticmethod
    def getInstance(*args, **kw):
        if MetadataDBHandler.__single is None:
            MetadataDBHandler._lock.acquire()
            try:
                if MetadataDBHandler.__single is None:
                    MetadataDBHandler(*args, **kw)
            finally:
                MetadataDBHandler._lock.release()

        return MetadataDBHandler.__single

    def __init__(self, db = SQLiteCacheDB.getInstance()):
        try:
            MetadataDBHandler._lock.acquire()
            MetadataDBHandler.__single = self
        finally:
            MetadataDBHandler._lock.release()

        try:
            self._db = db
            print >> sys.stderr, 'Metadata: DB made'
        except:
            print >> sys.stderr, "Metadata: couldn't make the tables"

        print >> sys.stderr, 'Metadata DB Handler initialized'

    def commit(self):
        self._db.commit()

    def getAllSubtitles(self, channel, infohash):
        query = QUERIES['SELECT SUBS JOIN HASH ALL']
        infohash = bin2str(infohash)
        channel = bin2str(channel)
        results = self._db.fetchall(query, (infohash, channel))
        subsDict = {}
        for entry in results:
            subsDict[entry[1]] = SubtitleInfo(entry[1], entry[2], entry[3])

        return subsDict

    def _deleteSubtitleByChannel(self, channel, infohash, lang):
        query = QUERIES['DELETE ONE SUBTITLE JOIN']
        infohash = bin2str(infohash)
        channel = bin2str(channel)
        self._db.execute_write(query, (channel, infohash, lang))

    def _getAllSubtitlesByKey(self, metadataKey):
        query = QUERIES['SELECT SUBS FK ALL']
        results = self._db.fetchall(query, (metadataKey,))
        subsDict = {}
        for entry in results:
            subsDict[entry[1]] = SubtitleInfo(entry[1], entry[2], str2bin(entry[3]))

        return subsDict

    def getSubtitle(self, channel, infohash, lang):
        query = QUERIES['SELECT SUBS JOIN HASH ONE']
        infohash = bin2str(infohash)
        channel = bin2str(channel)
        res = self._db.fetchall(query, (infohash, channel, lang))
        if len(res) == 0:
            return None
        if len(res) == 1:
            checksum = str2bin(res[0][3])
            return SubtitleInfo(res[0][1], res[0][2], checksum)
        raise MetadataDBException('Metadata DB Constraint violeted!')

    def _getSubtitleByKey(self, metadata_fk, lang):
        query = QUERIES['SELECT SUBS FK ONE']
        res = self._db.fetchall(query, (metadata_fk, lang))
        if len(res) == 0:
            return None
        if len(res) == 1:
            checksum = str2bin(res[0][3])
            return SubtitleInfo(res[0][1], res[0][2], checksum)
        raise MetadataDBException('Metadata DB Constraint violeted!')

    def getMetadata(self, channel, infohash):
        query = QUERIES['SELECT METADATA']
        infohash = bin2str(infohash)
        channel = bin2str(channel)
        res = self._db.fetchall(query, (infohash, channel))
        if len(res) == 0:
            return
        if len(res) > 1:
            raise MetadataDBException('Metadata DB Constraint violated')
        metaTuple = res[0]
        subsDictionary = self._getAllSubtitlesByKey(metaTuple[0])
        publisher = str2bin(metaTuple[1])
        infohash = str2bin(metaTuple[2])
        timestamp = int(metaTuple[4])
        description = unicode(metaTuple[3])
        signature = str2bin(metaTuple[5])
        toReturn = MetadataDTO(publisher, infohash, timestamp, description, None, signature)
        for sub in subsDictionary.itervalues():
            toReturn.addSubtitle(sub)

        return toReturn

    def getNrMetadata(self, channel):
        query = QUERIES['SELECT NRMETADATA']
        channel = bin2str(channel)
        return self._db.fetchone(query, (channel,))

    def getAllMetadataForInfohash(self, infohash):
        strinfohash = bin2str(infohash)
        query = QUERIES['SELECT PUBLISHERS FROM INFOHASH']
        channels = self._db.fetchall(query, (strinfohash,))
        return [ self.getMetadata(str2bin(entry[0]), infohash) for entry in channels ]

    def hasMetadata(self, channel, infohash):
        query = QUERIES['SELECT METADATA']
        infohash = bin2str(infohash)
        channel = bin2str(channel)
        res = self._db.fetchall(query, (infohash, channel))
        return len(res) != 0

    def insertMetadata(self, metadata_dto):
        if not metadata_dto.verifySignature():
            raise SignatureException('Metadata to insert is not properlysigned')
        select_query = QUERIES['SELECT METADATA']
        signature = bin2str(metadata_dto.signature)
        infohash = bin2str(metadata_dto.infohash)
        channel = bin2str(metadata_dto.channel)
        res = self._db.fetchall(select_query, (infohash, channel))
        isUpdate = False
        if len(res) != 0:
            if metadata_dto.timestamp > res[0][4]:
                query = QUERIES['UPDATE METADATA']
                self._db.execute_write(query, (metadata_dto.description,
                 metadata_dto.timestamp,
                 signature,
                 infohash,
                 channel), False)
                fk_key = res[0][0]
                isUpdate = True
            else:
                return
        else:
            query = QUERIES['INSERT METADATA']
            self._db.execute_write(query, (channel,
             infohash,
             metadata_dto.description,
             metadata_dto.timestamp,
             signature), True)
            if DEBUG:
                print >> sys.stderr, 'Performing query on db: ' + query
            newRows = self._db.fetchall(select_query, (infohash, channel))
            if len(newRows) == 0:
                raise IOError('No results, while there should be one')
            fk_key = newRows[0][0]
        self._insertOrUpdateSubtitles(fk_key, metadata_dto.getAllSubtitles(), False)
        self._db.commit()
        return isUpdate

    def _insertOrUpdateSubtitles(self, fk_key, subtitles, commitNow = True):
        allSubtitles = self._getAllSubtitlesByKey(fk_key)
        oldSubsSet = frozenset(allSubtitles.keys())
        newSubsSet = frozenset(subtitles.keys())
        commonLangs = oldSubsSet & newSubsSet
        newLangs = newSubsSet - oldSubsSet
        toDelete = oldSubsSet - newSubsSet
        for lang in commonLangs:
            self._updateSubtitle(fk_key, subtitles[lang], False)

        for lang in toDelete:
            self._deleteSubtitle(fk_key, lang, False)

        for lang in newLangs:
            self._insertNewSubtitle(fk_key, subtitles[lang], False)

        if commitNow:
            self._db.commit()

    def _updateSubtitle(self, metadata_fk, subtitle, commitNow = True):
        toUpdate = self._getSubtitleByKey(metadata_fk, subtitle.lang)
        if toUpdate is None:
            return
        query = QUERIES['UPDATE SUBTITLES']
        checksum = bin2str(subtitle.checksum)
        self._db.execute_write(query, (subtitle.path,
         checksum,
         metadata_fk,
         subtitle.lang), commitNow)

    def updateSubtitlePath(self, channel, infohash, lang, newPath, commitNow = True):
        query = QUERIES['SELECT SUBS JOIN HASH ONE']
        channel = bin2str(channel)
        infohash = bin2str(infohash)
        res = self._db.fetchall(query, (infohash, channel, lang))
        if len(res) > 1:
            raise MetadataDBException('Metadata DB constraint violated')
        else:
            if len(res) == 0:
                if DEBUG:
                    print >> sys.stderr, 'Nothing to update for channel %s, infohash %s, lang %s. Doing nothing.' % (channel[-10:], infohash, lang)
                return False
            query = QUERIES['UPDATE SUBTITLES']
            self._db.execute_write(query, (newPath,
             res[0][3],
             res[0][0],
             lang), commitNow)
            return True

    def _deleteSubtitle(self, metadata_fk, lang, commitNow = True):
        query = QUERIES['DELETE ONE SUBTITLES']
        self._db.execute_write(query, (metadata_fk, lang), commitNow)

    def _insertNewSubtitle(self, metadata_fk, subtitle, commitNow = True):
        query = QUERIES['INSERT SUBTITLES']
        checksum = bin2str(subtitle.checksum)
        self._db.execute_write(query, (metadata_fk,
         subtitle.lang,
         subtitle.path,
         checksum), commitNow)

    def deleteMetadata(self, channel, infohash):
        channel = bin2str(channel)
        infohash = bin2str(infohash)
        query = QUERIES['SELECT METADATA']
        if DEBUG:
            print >> sys.stderr, 'Performing query on db: ' + query
        res = self._db.fetchall(query, (infohash, channel))
        if len(res) == 0:
            return
        if len(res) > 1:
            raise IOError('Metadata DB constraint violated')
        metadata_fk = res[0][0]
        self._deleteAllSubtitles(metadata_fk, False)
        query = QUERIES['DELETE METADATA PK']
        self._db.execute_write(query, (metadata_fk,), False)
        self._db.commit()

    def _deleteAllSubtitles(self, metadata_fk, commitNow):
        query = QUERIES['DELETE ALL SUBTITLES']
        self._db.execute_write(query, (metadata_fk,), commitNow)

    def getAllLocalSubtitles(self):
        query = QUERIES['SELECT SUBTITLES WITH PATH']
        res = self._db.fetchall(query)
        result = {}
        for entry in res:
            path = entry[1]
            lang = entry[2]
            checksum = str2bin(entry[3])
            channel = str2bin(entry[4])
            infohash = str2bin(entry[5])
            s = SubtitleInfo(lang, path, checksum)
            if channel not in result:
                result[channel] = {}
            if infohash not in result[channel]:
                result[channel][infohash] = []
            result[channel][infohash].append(s)

        return result

    def getLocalSubtitles(self, channel, infohash):
        query = QUERIES['SELECT SUBTITLES WITH PATH BY CHN INFO']
        channel = bin2str(channel)
        infohash = bin2str(infohash)
        res = self._db.fetchall(query, (channel, infohash))
        result = {}
        for entry in res:
            location = entry[0]
            language = entry[1]
            checksum = str2bin(entry[2])
            subInfo = SubtitleInfo(language, location, checksum)
            result[language] = subInfo

        return result

    def insertHaveMask(self, channel, infohash, peer_id, havemask, timestamp = None):
        query = QUERIES['SELECT METADATA']
        if timestamp is None:
            timestamp = int(time.time())
        channel = bin2str(channel)
        infohash = bin2str(infohash)
        peer_id = bin2str(peer_id)
        res = self._db.fetchall(query, (infohash, channel))
        if len(res) != 1:
            raise MetadataDBException('No entry in the MetadataDB for %s, %s' % (channel[-10:], infohash))
        metadata_fk = res[0][0]
        insertQuery = QUERIES['INSERT HAVE MASK']
        try:
            self._db.execute_write(insertQuery, (metadata_fk,
             peer_id,
             havemask,
             timestamp))
        except sqlite3.IntegrityError as e:
            raise MetadataDBException(str(e))

    def updateHaveMask(self, channel, infohash, peer_id, newMask, timestamp = None):
        channel = bin2str(channel)
        infohash = bin2str(infohash)
        peer_id = bin2str(peer_id)
        updateQuery = QUERIES['UPDATE HAVE MASK']
        if timestamp is None:
            timestamp = int(time.time())
        self._db.execute_write(updateQuery, (newMask,
         timestamp,
         peer_id,
         channel,
         infohash))

    def deleteHaveEntry(self, channel, infohash, peer_id):
        channel = bin2str(channel)
        infohash = bin2str(infohash)
        peer_id = bin2str(peer_id)
        deleteQuery = QUERIES['DELETE HAVE']
        self._db.execute_write(deleteQuery, (peer_id, channel, infohash))

    def getHaveMask(self, channel, infohash, peer_id):
        query = QUERIES['GET ONE HAVE MASK']
        channel = bin2str(channel)
        infohash = bin2str(infohash)
        peer_id = bin2str(peer_id)
        res = self._db.fetchall(query, (channel, infohash, peer_id))
        if len(res) <= 0:
            return None
        if len(res) > 1:
            raise AssertionError('channel,infohash,peer_id should be unique')
        else:
            return res[0][0]

    def getHaveEntries(self, channel, infohash):
        query = QUERIES['GET ALL HAVE MASK']
        channel = bin2str(channel)
        infohash = bin2str(infohash)
        res = self._db.fetchall(query, (channel, infohash))
        returnlist = list()
        for entry in res:
            peer_id = str2bin(entry[0])
            haveMask = entry[1]
            timestamp = entry[2]
            returnlist.append((peer_id, haveMask, timestamp))

        return returnlist

    def cleanupOldHave(self, limit_ts):
        cleanupQuery = QUERIES['CLEANUP OLD HAVE']
        self._db.execute_write(cleanupQuery, (limit_ts,))

    def insertOrUpdateHave(self, channel, infohash, peer_id, havemask, timestamp = None):
        if timestamp is None:
            timestamp = int(time.time())
        if self.getHaveMask(channel, infohash, peer_id) is not None:
            self.updateHaveMask(channel, infohash, peer_id, havemask, timestamp)
        else:
            self.insertHaveMask(channel, infohash, peer_id, havemask, timestamp)
