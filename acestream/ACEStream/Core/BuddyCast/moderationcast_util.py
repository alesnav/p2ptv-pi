#Embedded file name: ACEStream\Core\BuddyCast\moderationcast_util.pyo
import sys
from ACEStream.Core.CacheDB.sqlitecachedb import bin2str, str2bin
from types import StringType, ListType, DictType
from time import time
from ACEStream.Core.BitTornado.bencode import bencode
from ACEStream.Core.Overlay.permid import verify_data
from os.path import exists, isfile
from ACEStream.Core.Subtitles.RichMetadataInterceptor import validMetadataEntry
DEBUG = False
TIMESTAMP_IN_FUTURE = 300

def validInfohash(infohash):
    r = isinstance(infohash, str) and len(infohash) == 20
    if not r:
        if DEBUG:
            print >> sys.stderr, 'Invalid infohash: type(infohash) ==', str(type(infohash)) + ', infohash ==', `infohash`
    return r


def validPermid(permid):
    r = type(permid) == str and len(permid) <= 125
    if not r:
        if DEBUG:
            print >> sys.stderr, 'Invalid permid: type(permid) ==', str(type(permid)) + ', permid ==', `permid`
    return r


def now():
    return int(time())


def validTimestamp(timestamp):
    r = timestamp is not None and type(timestamp) == int and timestamp > 0 and timestamp <= now() + TIMESTAMP_IN_FUTURE
    if not r:
        if DEBUG:
            print >> sys.stderr, 'Invalid timestamp'
    return r


def validVoteCastMsg(data):
    if data is None:
        print >> sys.stderr, 'data is None'
        return False
    if not type(data) == DictType:
        print >> sys.stderr, 'data is not Dictionary'
        return False
    for key, value in data.items():
        if not validPermid(key):
            if DEBUG:
                print >> sys.stderr, 'not valid permid: ', repr(key)
            return False
        if not ('vote' in value and 'time_stamp' in value):
            if DEBUG:
                print >> sys.stderr, 'validVoteCastMsg: key missing, got', value.keys()
            return False
        if not type(value['vote']) == int:
            if DEBUG:
                print >> sys.stderr, 'Vote is not int: ', repr(value['vote'])
            return False
        if not (value['vote'] == 2 or value['vote'] == -1):
            if DEBUG:
                print >> sys.stderr, 'Vote is not -1 or 2: ', repr(value['vote'])
            return False
        if not type(value['time_stamp']) == int:
            if DEBUG:
                print >> sys.stderr, 'time_stamp is not int: ', repr(value['time_stamp'])
            return False

    return True


def validChannelCastMsg(channelcast_data):
    if not isinstance(channelcast_data, dict):
        return False
    for signature, ch in channelcast_data.items():
        if not isinstance(ch, dict):
            if DEBUG:
                print >> sys.stderr, 'validChannelCastMsg: value not dict'
            return False
        length = len(ch)
        if not 6 <= length <= 7:
            if DEBUG:
                print >> sys.stderr, 'validChannelCastMsg: #keys!=7'
            return False
        if not ('publisher_id' in ch and 'publisher_name' in ch and 'infohash' in ch and 'torrenthash' in ch and 'torrentname' in ch and 'time_stamp' in ch):
            if DEBUG:
                print >> sys.stderr, 'validChannelCastMsg: key missing'
            return False
        if length == 7:
            if 'rich_metadata' not in ch:
                if DEBUG:
                    print >> sys.stderr, 'validChannelCastMsg: key missing'
                return False
            if not validMetadataEntry(ch['rich_metadata']):
                print >> sys.stderr, 'validChannelCastMsg: invalid rich metadata'
                return False
        if not (validPermid(ch['publisher_id']) and isinstance(ch['publisher_name'], str) and validInfohash(ch['infohash']) and validInfohash(ch['torrenthash']) and isinstance(ch['torrentname'], str) and validTimestamp(ch['time_stamp'])):
            if DEBUG:
                print >> sys.stderr, 'validChannelCastMsg: something not valid'
            return False
        l = (ch['publisher_id'],
         ch['infohash'],
         ch['torrenthash'],
         ch['time_stamp'])
        if not verify_data(bencode(l), ch['publisher_id'], signature):
            if DEBUG:
                print >> sys.stderr, 'validChannelCastMsg: verification failed!'
            return False

    return True


def voteCastMsgToString(data):
    return repr(data)
