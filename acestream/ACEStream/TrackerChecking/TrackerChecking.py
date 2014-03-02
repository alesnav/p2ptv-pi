#Embedded file name: ACEStream\TrackerChecking\TrackerChecking.pyo
import sys
from ACEStream.Core.BitTornado.bencode import bdecode
from random import shuffle
import urllib
import socket
import ACEStream.Core.Utilities.timeouturlopen as timeouturlopen
from time import time
from traceback import print_exc
HTTP_TIMEOUT = 30
DEBUG = False

def trackerChecking(torrent):
    single_no_thread(torrent)


def single_no_thread(torrent):
    seeder, leecher = (-2, -2)
    if torrent['info'].get('announce-list', '') == '':
        try:
            announce = torrent['info']['announce']
            s, l = singleTrackerStatus(torrent, announce)
            seeder = max(seeder, s)
            leecher = max(leecher, l)
        except:
            pass

    else:
        for announces in torrent['info']['announce-list']:
            a_len = len(announces)
            if a_len == 0:
                continue
            if a_len == 1:
                announce = announces[0]
                s, l = singleTrackerStatus(torrent, announce)
                seeder = max(seeder, s)
                leecher = max(leecher, l)
            else:
                aindex = torrent['info']['announce-list'].index(announces)
                shuffle(announces)
                announces = announces[:16]
                for announce in announces:
                    s, l = singleTrackerStatus(torrent, announce)
                    seeder = max(seeder, s)
                    leecher = max(leecher, l)
                    if seeder > 0:
                        break

                if seeder > 0 or leecher > 0:
                    announces.remove(announce)
                    announces.insert(0, announce)
                    torrent['info']['announce-list'][aindex] = announces
            if seeder > 0:
                break

    if seeder == -3 and leecher == -3:
        pass
    else:
        torrent['seeder'] = seeder
        torrent['leecher'] = leecher
        if torrent['seeder'] > 0 or torrent['leecher'] > 0:
            torrent['status'] = 'good'
        elif torrent['seeder'] == 0 and torrent['leecher'] == 0:
            torrent['status'] = 'unknown'
        elif torrent['seeder'] == -1 and torrent['leecher'] == -1:
            torrent['status'] = 'unknown'
        else:
            torrent['status'] = 'dead'
            torrent['seeder'] = -2
            torrent['leecher'] = -2
    torrent['last_check_time'] = long(time())
    return torrent


def singleTrackerStatus(torrent, announce):
    info_hash = torrent['infohash']
    if DEBUG:
        print >> sys.stderr, 'TrackerChecking: Checking', announce, 'for', `info_hash`
    url = getUrl(announce, info_hash)
    if url == None:
        return (-2, -2)
    try:
        seeder, leecher = getStatus(url, info_hash)
        if DEBUG:
            print >> sys.stderr, 'TrackerChecking: Result', (seeder, leecher)
    except:
        seeder, leecher = (-2, -2)

    return (seeder, leecher)


def getUrl(announce, info_hash):
    if announce == -1:
        return None
    announce_index = announce.rfind('announce')
    last_index = announce.rfind('/')
    url = announce
    if last_index + 1 == announce_index:
        url = url.replace('announce', 'scrape')
    url += '?info_hash=' + urllib.quote(info_hash)
    return url


def getStatus(url, info_hash):
    try:
        resp = timeouturlopen.urlOpenTimeout(url, timeout=HTTP_TIMEOUT)
        response = resp.read()
    except IOError:
        return (-1, -1)
    except AttributeError:
        return (-2, -2)

    try:
        response_dict = bdecode(response)
    except:
        return (-2, -2)

    try:
        status = response_dict['files'][info_hash]
        seeder = status['complete']
        if seeder < 0:
            seeder = 0
        leecher = status['incomplete']
        if leecher < 0:
            leecher = 0
    except KeyError:
        try:
            if response_dict.has_key('flags'):
                if response_dict['flags'].has_key('min_request_interval'):
                    return (-3, -3)
        except:
            pass

        return (-2, -2)

    return (seeder, leecher)
