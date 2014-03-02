#Embedded file name: ACEStream\Core\TS\Service.pyo
import sys
import time
import hashlib
import random
from base64 import b64encode, b64decode
import urllib
import os
import binascii
from urllib2 import HTTPError, URLError
from traceback import print_exc
from xml.dom.minidom import parseString, Document
from xml.dom import expatbuilder
from cStringIO import StringIO
from ACEStream.version import VERSION
from ACEStream.Core.simpledefs import *
from ACEStream.Core.TorrentDef import *
from ACEStream.Core.Utilities.timeouturlopen import urlOpenTimeout
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.TS.domutils import domutils
SERVER_TYPE_PROXY = 1
SERVER_TYPE_SERVICE = 2
SERVER_TYPE_AD = 3
SERVER_TYPE_TRACKER = 4
SERVER_TYPE_PREMIUM_SERVICE = 5
SERVER_TYPE_PREMIUM_STATISTICS = 6
SERVER_TYPE_AUTH = 7
DEBUG = False

class BadResponseException(Exception):
    pass


class TSService():
    REQUEST_SECRET = 'q\\\'X!;UL0J_<R*z#GBTL(9mCeRJbm/;L.oi9.`\\"iETli9GD]`t&xlT(]MhJ{NVN,Q.)r~(6+9Bt(G,O%2c/g@sPi]<c[i\\\\ga]fkbHgwH:->ok4w8><y]^:Lw465+W4a(:'
    RESPONSE_SECRET = 'hXD.VAgz=QegM4Hq>P~b7t9LA:eB|}t3z~Rt`FV/-P<va|g,i/M~5/>A-.G70H-p!k|s{wL!Tn\\"=%/L\\\\&@C-Bkz`(w\\\'(KF4fU3(KPKC@.L3.zL4-y%gI8/?RVRx?d+a)'
    SERVICE_SERVERS = ['http://s1.torrentstream.net',
     'http://s1.torrentstream.org',
     'http://s1.torrentstream.info',
     'http://s2.torrentstream.net',
     'http://s2.torrentstream.org',
     'http://s2.torrentstream.info',
     'http://s3.torrentstream.net',
     'http://s3.torrentstream.org',
     'http://s3.torrentstream.info']
    PREMIUM_SERVICE_SERVERS = ['https://p1.acestream.net',
     'https://p2.acestream.net',
     'https://p1.acestream.org',
     'https://p2.acestream.org']
    PREMIUM_STATISTICS_SERVERS = ['http://ps1.acestream.net',
     'http://ps2.acestream.net',
     'http://ps1.acestream.org',
     'http://ps2.acestream.org']
    AUTH_SERVERS = ['https://auth1.acestream.net',
     'https://auth2.acestream.net',
     'https://auth1.acestream.org',
     'https://auth2.acestream.org']

    def __init__(self, baseapp):
        self.baseapp = baseapp

    def get_user_level(self, login, password, action, device_id, hardware_key):
        if hardware_key is None:
            hardware_key = ''
        device_key = hashlib.sha1(device_id + hardware_key).hexdigest()
        params = {'l': login,
         'p': hashlib.sha1(password).hexdigest(),
         'h': b64encode(hardware_key),
         action: device_key}
        response = self.send_request('getuserlevel', params, use_random=True, server_type=SERVER_TYPE_AUTH)
        if response is None:
            if DEBUG:
                log('tsservice::get_user_level: request failed')
            return
        user_level = domutils.get_tag_value(response, 'level')
        if user_level is None:
            return
        try:
            user_level = int(user_level)
        except:
            if DEBUG:
                log('tsservice::get_user_level: bad user_level:', user_level)
            return

        return user_level

    def check_premium_status(self, provider_key, content_id, infohash):
        params = {'p': provider_key,
         'c': content_id,
         'i': binascii.hexlify(infohash)}
        response = self.send_request('checkpremiumstatus', params, use_random=True, server_type=SERVER_TYPE_PREMIUM_SERVICE)
        if response is None:
            if DEBUG:
                log('tsservice::check_premium_status: request failed')
            return
        status = domutils.get_tag_value(response, 'status')
        if status is None:
            return
        try:
            status = int(status)
        except:
            if DEBUG:
                log('tsservice::check_premium_status: bad status:', status)
            return

        return status

    def report_premium_download(self, watch_id, provider_key, content_id, user_login):
        if content_id is None:
            content_id = ''
        params = {'w': watch_id,
         'p': provider_key,
         'c': content_id,
         'u': b64encode(user_login)}
        self.send_request('watch', params, use_random=True, use_timestamp=True, server_type=SERVER_TYPE_PREMIUM_STATISTICS, parse_response=False)

    def get_infohash_from_url(self, url):
        params = {'url': b64encode(url)}
        response = self.send_request('getu2t', params, use_random=True)
        if response is None:
            if DEBUG:
                log('tsservice::get_infohash_from_url: request failed: url', url)
            return
        infohash = domutils.get_tag_value(response, 'infohash')
        if infohash is None:
            return
        infohash = b64decode(infohash)
        if DEBUG:
            log('tsservice::get_infohash_from_url: got data: infohash', binascii.hexlify(infohash))
        return infohash

    def save_url2infohash(self, url, infohash):
        params = {'url': b64encode(url),
         'infohash': b64encode(infohash)}
        self.send_request('putu2t', params)

    def get_infohash_from_adid(self, adid):
        params = {'id': str(adid)}
        response = self.send_request('geta2i', params, use_random=True)
        if response is None:
            if DEBUG:
                log('tsservice::get_infohash_from_adid: request failed: adid', adid)
            return
        infohash = domutils.get_tag_value(response, 'infohash')
        if infohash is None:
            return
        infohash = b64decode(infohash)
        if DEBUG:
            log('tsservice::get_infohash_from_adid: got data: infohash', binascii.hexlify(infohash))
        return infohash

    def send_torrent(self, torrent_data, developer_id = None, affiliate_id = None, zone_id = None, protected = False, infohash = None):
        params = {}
        if developer_id is not None:
            params['d'] = str(developer_id)
        if affiliate_id is not None:
            params['a'] = str(affiliate_id)
        if zone_id is not None:
            params['z'] = str(zone_id)
        if protected:
            params['protected'] = '1'
        if infohash is not None:
            params['infohash'] = binascii.hexlify(infohash)
        response = self.send_request('puttorrent', params, data=torrent_data, content_type='application/octet-stream', use_random=True)
        if response is None:
            if DEBUG:
                log('tsservice::send_torrent: request failed')
            return
        try:
            player_id = domutils.get_tag_value(response, 'id')
        except Exception as e:
            if DEBUG:
                log('tsservice::send_torrent: failed to parse response: ' + str(e))
            return

        return player_id

    def get_torrent(self, infohash = None, player_id = None):
        if infohash is None and player_id is None:
            raise ValueError, 'Infohash or player id must be specified'
        params = {}
        if player_id is not None:
            params['pid'] = player_id
        elif infohash is not None:
            params['infohash'] = b64encode(infohash)
        response = self.send_request('gettorrent', params, use_random=True)
        if response is None:
            return
        torrent_data = domutils.get_tag_value(response, 'torrent')
        if torrent_data is None:
            return
        torrent_checksum = domutils.get_tag_value(response, 'checksum')
        if torrent_checksum is None:
            return
        torrent_data = b64decode(torrent_data)
        buf = StringIO(torrent_data)
        tdef = TorrentDef._read(buf)
        player_data = {'tdef': tdef,
         'checksum': binascii.unhexlify(torrent_checksum)}
        if player_id is not None:
            try:
                developer_id = int(domutils.get_tag_value(response, 'developer_id'))
                affiliate_id = int(domutils.get_tag_value(response, 'affiliate_id'))
                zone_id = int(domutils.get_tag_value(response, 'zone_id'))
                player_data['developer_id'] = developer_id
                player_data['affiliate_id'] = affiliate_id
                player_data['zone_id'] = zone_id
            except:
                if DEBUG:
                    print_exc()

        return player_data

    def check_torrent(self, torrent_checksum = None, infohash = None, player_id = None, developer_id = 0, affiliate_id = 0, zone_id = 0):
        if infohash is None and player_id is None:
            raise ValueError, 'Infohash or player id must be specified'
        params = {}
        if player_id is not None:
            params['pid'] = player_id
        elif infohash is not None:
            if torrent_checksum is not None:
                params['checksum'] = binascii.hexlify(torrent_checksum)
            params['infohash'] = b64encode(infohash)
            params['d'] = str(developer_id)
            params['a'] = str(affiliate_id)
            params['z'] = str(zone_id)
        response = self.send_request('checktorrent', params, use_random=True)
        if response is None:
            return
        player_id = domutils.get_tag_value(response, 'id')
        metadata = None
        http_seeds = None
        if player_id is not None:
            root = response.documentElement
            e_http_seeds = domutils.get_single_element(root, 'httpseeds', False)
            if e_http_seeds is not None:
                http_seeds = []
                e_urls = domutils.get_children_by_tag_name(e_http_seeds, 'url')
                for e_url in e_urls:
                    url = domutils.get_node_text(e_url)
                    http_seeds.append(url)

            e_metadata = domutils.get_single_element(root, 'metadata', False)
            if e_metadata is not None:
                metadata = {}
                e_duration = domutils.get_single_element(e_metadata, 'duration', False)
                e_prebuf_pieces = domutils.get_single_element(e_metadata, 'prebuf_pieces', False)
                e_rpmp4mt = domutils.get_single_element(e_metadata, 'rpmp4mt', False)
                if e_duration is not None:
                    metadata['duration'] = {}
                    files = domutils.get_children_by_tag_name(e_duration, 'file')
                    for f in files:
                        idx = f.getAttribute('id')
                        try:
                            idx = int(idx)
                        except:
                            continue

                        value = domutils.get_node_text(f)
                        metadata['duration']['f' + str(idx)] = value

                if e_prebuf_pieces is not None:
                    metadata['prebuf_pieces'] = {}
                    files = domutils.get_children_by_tag_name(e_prebuf_pieces, 'file')
                    for f in files:
                        idx = f.getAttribute('id')
                        try:
                            idx = int(idx)
                        except:
                            continue

                        value = domutils.get_node_text(f)
                        metadata['prebuf_pieces']['f' + str(idx)] = value

                if e_rpmp4mt is not None:
                    metadata['rpmp4mt'] = {}
                    files = domutils.get_children_by_tag_name(e_rpmp4mt, 'file')
                    for f in files:
                        idx = f.getAttribute('id')
                        try:
                            idx = int(idx)
                        except:
                            continue

                        value = domutils.get_node_text(f)
                        metadata['rpmp4mt']['f' + str(idx)] = value

                if DEBUG:
                    log('tsservice::check_torrent: got metadata: metadata', metadata)
        return (player_id, metadata, http_seeds)

    def send_metadata(self, infohash, metadata):
        params = {'infohash': b64encode(infohash)}
        doc = Document()
        e_metadata = doc.createElement('metadata')
        doc.appendChild(e_metadata)
        if metadata.has_key('duration'):
            e_duration = doc.createElement('duration')
            for idx, duration in metadata['duration'].iteritems():
                idx = idx.replace('f', '')
                e_file = doc.createElement('file')
                e_file.setAttribute('id', idx)
                e_file.appendChild(doc.createTextNode(str(duration)))
                e_duration.appendChild(e_file)

            e_metadata.appendChild(e_duration)
        if metadata.has_key('prebuf_pieces'):
            e_prebuf_pieces = doc.createElement('prebuf_pieces')
            for idx, prebuf_pieces in metadata['prebuf_pieces'].iteritems():
                idx = idx.replace('f', '')
                e_file = doc.createElement('file')
                e_file.setAttribute('id', idx)
                e_file.appendChild(doc.createTextNode(prebuf_pieces))
                e_prebuf_pieces.appendChild(e_file)

            e_metadata.appendChild(e_prebuf_pieces)
        if metadata.has_key('rpmp4mt'):
            e_rpmp4mt = doc.createElement('rpmp4mt')
            for idx, rpmp4mt in metadata['rpmp4mt'].iteritems():
                idx = idx.replace('f', '')
                e_file = doc.createElement('file')
                e_file.setAttribute('id', idx)
                e_file.appendChild(doc.createTextNode(rpmp4mt))
                e_rpmp4mt.appendChild(e_file)

            e_metadata.appendChild(e_rpmp4mt)
        xmldata = doc.toxml()
        if DEBUG:
            log('tsservice::send_metadata: infohash', binascii.hexlify(infohash), 'xmldata', xmldata)
        self.send_request('putmeta', params, data=xmldata, content_type='text/xml', timeout=10)

    def send_request(self, method, params = {}, data = None, content_type = None, use_random = False, use_timestamp = False, timeout = 5, server_type = SERVER_TYPE_SERVICE, parse_response = True):
        if data is not None and content_type is None:
            raise ValueError, 'Data passed without content type'
        if params.has_key('r'):
            raise ValueError, "Cannot use reserved parameter 'r'"
        if params.has_key('t'):
            raise ValueError, "Cannot use reserved parameter 't'"
        if params.has_key('v'):
            raise ValueError, "Cannot use reserved parameter 'v'"
        params['v'] = VERSION
        if use_random:
            request_random = random.randint(1, sys.maxint)
            params['r'] = str(request_random)
        else:
            request_random = None
        if use_timestamp:
            params['t'] = str(long(time.time()))
        get_params = []
        payload = []
        if len(params):
            for k in sorted(params.keys()):
                v = params[k]
                get_params.append(k + '=' + urllib.quote_plus(v))
                payload.append(k + '=' + v)

            if DEBUG:
                log('tsservice::send_request: got params: get_params', get_params, 'payload', payload)
        if data is not None:
            payload.append(data)
            if DEBUG:
                log('tsservice::send_request: got data')
        if len(payload):
            payload = '#'.join(payload)
            payload += self.REQUEST_SECRET
            signature = hashlib.sha1(payload).hexdigest()
            get_params.append('s=' + signature)
            if DEBUG:
                log('tsservice::send_request: sign data: signature', signature)
        query = '/' + method
        if len(get_params):
            query += '?' + '&'.join(get_params)
        if DEBUG:
            log('tsservice::send_request: query', query)
        servers = self.get_servers(server_type)
        random.shuffle(servers)
        response = None
        for serv in servers:
            try:
                url = serv + query
                if DEBUG:
                    log('tsservice::send_request: url', url)
                stream = urlOpenTimeout(url, timeout, content_type, None, data)
                response = stream.read()
                stream.close()
                if DEBUG:
                    log('tsservice::send_request: got response: url', url, 'response', response)
                if parse_response:
                    response = self.check_response(response, request_random)
                break
            except BadResponseException as e:
                response = None
                if DEBUG:
                    log('tsservice::send_request: bad response: ' + str(e))
            except (URLError, HTTPError) as e:
                response = None
                if DEBUG:
                    log('tsservice::send_request: http error: ' + str(e))
            except:
                response = None
                if DEBUG:
                    print_exc()

        return response

    def get_servers(self, server_type):
        if server_type == SERVER_TYPE_SERVICE:
            return self.SERVICE_SERVERS
        if server_type == SERVER_TYPE_PREMIUM_SERVICE:
            return self.PREMIUM_SERVICE_SERVERS
        if server_type == SERVER_TYPE_PREMIUM_STATISTICS:
            return self.PREMIUM_STATISTICS_SERVERS
        if server_type == SERVER_TYPE_AUTH:
            return self.AUTH_SERVERS
        raise ValueError, 'Unknown server type ' + str(server_type)

    def check_response(self, response, request_random = None):
        if len(response) == 0:
            raise BadResponseException, 'Empty response'
        doc = parseString(response)
        root = doc.documentElement
        if root.tagName != 'response':
            raise BadResponseException, 'Bad response tagname: ' + doc.tagName
        if not root.hasAttribute('sig'):
            raise BadResponseException, 'Missing signature'
        if request_random is not None:
            if not root.hasAttribute('r'):
                raise BadResponseException, 'Missing random'
            try:
                response_random = int(root.getAttribute('r'))
            except ValueError:
                raise BadResponseException, 'Cannot parse random'

            if response_random != request_random:
                if DEBUG:
                    log('tsservice::check_response: bad random: response_random', response_random, 'request_random', request_random)
                raise BadResponseException, 'Bad random'
        response_sig = root.getAttribute('sig')
        payload = response.replace(' sig="' + response_sig + '"', '', 1)
        if DEBUG:
            log('tsservice::check_response: response', response)
            log('tsservice::check_response: response_sig', response_sig)
            log('tsservice::check_response: payload', payload)
        check_sig = hashlib.sha1(payload + self.RESPONSE_SECRET).hexdigest()
        if check_sig != response_sig:
            if DEBUG:
                log('tsservice::check_response: bad sig: response_sig', response_sig, 'check_sig', check_sig)
            raise BadResponseException, 'Bad signature'
        return doc


if __name__ == '__main__':
    service = TSService(None)
    url = 'http://test.com'
    infohash = service.get_infohash_from_url(url)
    print infohash
