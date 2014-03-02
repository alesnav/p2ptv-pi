#Embedded file name: ACEStream\Core\TorrentDef.pyo
import sys
import os
import copy
import math
import time
import urllib2
from traceback import print_stack
from types import StringType, ListType, IntType, LongType
from base64 import b64encode
import ACEStream
from ACEStream.Core.simpledefs import *
from ACEStream.Core.defaults import *
from ACEStream.Core.exceptions import *
from ACEStream.Core.Base import *
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
import ACEStream.Core.APIImplementation.maketorrent as maketorrent
import ACEStream.Core.APIImplementation.makeurl as makeurl
from ACEStream.Core.APIImplementation.miscutils import *
from ACEStream.Core.Utilities.utilities import validTorrentFile, isValidURL
from ACEStream.Core.Utilities.unicode import dunno2unicode
from ACEStream.Core.Utilities.timeouturlopen import urlOpenTimeout
from ACEStream.Core.osutils import *
from ACEStream.Core.Utilities.TSCrypto import sha, m2_AES_encrypt, m2_AES_decrypt
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.ClosedSwarm import ClosedSwarm
from ACEStream.Core.DecentralizedTracking.MagnetLink.MagnetLink import MagnetLink
DEBUG = False
DEBUG_PREMIUM = False
TORRENT_CACHE_EXPIRE = 86400

class TorrentDef(Serializable, Copyable):
    torrent_cache = {}

    def __init__(self, input = None, metainfo = None, infohash = None):
        self.readonly = False
        if input is not None:
            self.input = input
            self.metainfo = metainfo
            self.infohash = infohash
            return
        self.input = {}
        self.input.update(tdefdefaults)
        try:
            self.input['encoding'] = sys.getfilesystemencoding()
        except:
            self.input['encoding'] = sys.getdefaultencoding()

        self.input['files'] = []
        self.metainfo_valid = False
        self.ts_metainfo_valid = False
        self.metainfo = None
        self.infohash = None
        self.protected = False

    @staticmethod
    def load(filename):
        f = open(filename, 'rb')
        return TorrentDef._read(f)

    @staticmethod
    def _read(stream):
        bdata = stream.read()
        stream.close()
        protected = False
        if bdata[:8] == chr(1) + chr(2) + chr(3) + chr(4) + chr(17) + chr(2) + chr(101) + chr(46):
            bdata = bdata[8:]
            bdata = m2_AES_decrypt(bdata, '%E0(tK8r]8KKU=crz!Vuex0b#I)H+!0n}%f0]L_x0ch++?-<#YHwXkvM6UL')
            protected = True
        elif bdata[:4] == chr(1) + chr(2) + chr(3) + chr(4):
            bdata = bdata[4:]
            bdata = m2_AES_decrypt(bdata, 'tslive_key')
            protected = True
        elif bdata[:4] == chr(17) + chr(2) + chr(101) + chr(46):
            bdata = bdata[4:]
            bdata = m2_AES_decrypt(bdata, '=Atl6GD#Vb+#QwW9zJy34lBOcM-7R7G)')
            protected = True
        data = bdecode(bdata, params={'use_ordered_dict': True})
        if not data.has_key('info') and data.has_key('qualities'):
            return MultiTorrent._create(data, protected)
        else:
            return TorrentDef._create(data, protected)

    @staticmethod
    def _create(metainfo, protected = False):
        metainfo = validTorrentFile(metainfo)
        t = TorrentDef()
        t.protected = protected
        t.metainfo = metainfo
        t.ts_metainfo_valid = True
        t.metainfo_valid = True
        maketorrent.copy_metainfo_to_input(t.metainfo, t.input)
        if t.get_url_compat():
            t.infohash = makeurl.metainfo2swarmid(t.metainfo)
        else:
            t.infohash = sha(bencode(metainfo['info'], params={'skip_dict_sorting': True})).digest()
        if DEBUG:
            print >> sys.stderr, 'TorrentDef::_create: infohash:', `(t.infohash)`
        return t

    @staticmethod
    def retrieve_from_magnet(url, callback, timeout = 30.0):

        def metainfo_retrieved(metadata):
            tdef = TorrentDef.load_from_dict(metadata)
            callback(tdef)

        try:
            magnet_link = MagnetLink(url, metainfo_retrieved, timeout)
            return magnet_link.retrieve()
        except Exception as e:
            print >> sys.stderr, 'Exception within magnet link'
            print >> sys.stderr, e
            return False

    @staticmethod
    def load_from_url(url, use_cache = True):
        if url.startswith(P2PURL_SCHEME):
            metainfo, swarmid = makeurl.p2purl2metainfo(url)
            metainfo['info']['url-compat'] = 1
            t = TorrentDef._create(metainfo)
            return t
        else:
            b64_url = b64encode(url)
            if use_cache:
                if b64_url in TorrentDef.torrent_cache:
                    tdef_from_cache = TorrentDef.torrent_cache[b64_url]
                    if DEBUG:
                        log('TorrentDef::load_from_url: found in cache: url', url, 'timestamp', tdef_from_cache['timestamp'])
                    if tdef_from_cache['timestamp'] < time.time() - TORRENT_CACHE_EXPIRE:
                        if DEBUG:
                            log('TorrentDef::load_from_url: expired, delete from cache')
                        del TorrentDef.torrent_cache[b64_url]
                    else:
                        return tdef_from_cache['tdef']
            if url.startswith('file:///'):
                try:
                    url = dunno2unicode(urllib2.unquote(url))
                except:
                    log_exc()

            f = urlOpenTimeout(url)
            tdef = TorrentDef._read(f)
            if DEBUG:
                log('TorrentDef::load_from_url: add to cache, url', url)
            TorrentDef.torrent_cache[b64_url] = {'tdef': tdef.copy(),
             'timestamp': time.time()}
            return tdef

    @staticmethod
    def load_from_dict(metainfo):
        return TorrentDef._create(metainfo)

    def add_content(self, inpath, outpath = None, playtime = None):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        s = os.stat(inpath)
        d = {'inpath': inpath,
         'outpath': outpath,
         'playtime': playtime,
         'length': s.st_size}
        self.input['files'].append(d)
        self.metainfo_valid = False

    def remove_content(self, inpath):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        for d in self.input['files']:
            if d['inpath'] == inpath:
                self.input['files'].remove(d)
                break

    def create_live(self, name, bitrate, playtime = '1:00:00', authconfig = None, protected = False, provider_key = None, content_id = None, premium = False, license = None, tns_enabled = False):
        self.set_ts_bitrate(0, bitrate)
        self.input['bps'] = bitrate
        self.input['playtime'] = playtime
        self.protected = protected
        if provider_key is not None:
            self.input['provider'] = provider_key
        if content_id is not None:
            self.input['content_id'] = content_id
        if premium:
            self.input['premium'] = 1
        if license is not None:
            self.input['license'] = license
        if tns_enabled:
            self.input['tns'] = 1
        authparams = {}
        if authconfig is None:
            authparams['authmethod'] = LIVE_AUTHMETHOD_NONE
        else:
            authparams['authmethod'] = authconfig.get_method()
            authparams['pubkey'] = authconfig.get_pubkey()
        self.input['live'] = authparams
        d = {'inpath': name,
         'outpath': None,
         'playtime': None,
         'length': None}
        self.input['files'].append(d)

    def set_sharing(self, value):
        self.input['sharing'] = int(value)
        self.metainfo_valid = False

    def get_sharing(self):
        return self.input.get('sharing', 1)

    def set_private_flag(self, value):
        self.input['private'] = 1 if value else 0
        self.metainfo_valid = False

    def get_private_flag(self):
        value = self.input.get('private', 0)
        if value == 1:
            return True
        return False

    def set_encoding(self, enc):
        self.input['encoding'] = enc
        self.metainfo_valid = False

    def get_encoding(self):
        return self.input['encoding']

    def set_thumbnail(self, thumbfilename):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        f = open(thumbfilename, 'rb')
        data = f.read()
        f.close()
        self.input['thumb'] = data
        self.metainfo_valid = False

    def get_thumbnail(self):
        if 'thumb' not in self.input or self.input['thumb'] is None:
            return (None, None)
        else:
            thumb = self.input['thumb']
            return ('image/jpeg', thumb)

    def set_tracker(self, url):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        if not isValidURL(url):
            raise ValueError('Invalid URL')
        if url.endswith('/'):
            url = url[:-1]
        self.input['announce'] = url
        self.metainfo_valid = False

    def get_tracker(self):
        return self.input['announce']

    def set_tracker_hierarchy(self, hier):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        newhier = []
        if type(hier) != ListType:
            raise ValueError('hierarchy is not a list')
        for tier in hier:
            if type(tier) != ListType:
                raise ValueError('tier is not a list')
            newtier = []
            for url in tier:
                if not isValidURL(url):
                    raise ValueError('Invalid URL: ' + `url`)
                if url.endswith('/'):
                    url = url[:-1]
                newtier.append(url)

            newhier.append(newtier)

        self.input['announce-list'] = newhier
        self.metainfo_valid = False

    def get_tracker_hierarchy(self):
        return self.input['announce-list']

    def set_dht_nodes(self, nodes):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        if type(nodes) != ListType:
            raise ValueError('nodes not a list')
        else:
            for node in nodes:
                if type(node) != ListType and len(node) != 2:
                    raise ValueError('node in nodes not a 2-item list: ' + `node`)
                if type(node[0]) != StringType:
                    raise ValueError('host in node is not string:' + `node`)
                if type(node[1]) != IntType:
                    raise ValueError('port in node is not int:' + `node`)

        self.input['nodes'] = nodes
        self.metainfo_valid = False

    def get_dht_nodes(self):
        return self.input['nodes']

    def set_comment(self, value):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        self.input['comment'] = value
        self.metainfo_valid = False

    def get_comment(self):
        return self.input['comment']

    def get_comment_as_unicode(self):
        return dunno2unicode(self.input['comment'])

    def set_created_by(self, value):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        self.input['created by'] = value
        self.metainfo_valid = False

    def get_created_by(self):
        return self.input['created by']

    def set_urllist(self, value, invalidate = True):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        for url in value:
            if not isValidURL(url):
                raise ValueError('Invalid URL: ' + `url`)

        self.input['url-list'] = value
        if invalidate:
            self.metainfo_valid = False
        elif self.metainfo_valid:
            self.metainfo['url-list'] = value

    def get_urllist(self):
        return self.input['url-list']

    def set_httpseeds(self, value):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        for url in value:
            if not isValidURL(url):
                raise ValueError('Invalid URL: ' + `url`)

        self.input['httpseeds'] = value
        self.metainfo_valid = False

    def get_httpseeds(self):
        return self.input['httpseeds']

    def set_piece_length(self, value):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        if not (type(value) == IntType or type(value) == LongType):
            raise ValueError('Piece length not an int/long')
        self.input['piece length'] = value
        self.metainfo_valid = False

    def get_piece_length(self):
        return self.input['piece length']

    def set_cs_keys(self, keys):
        self.input['cs_keys'] = ','.join(keys)

    def get_cs_keys_as_ders(self):
        if 'cs_keys' in self.input and len(self.input['cs_keys']) > 0:
            return self.input['cs_keys'].split(',')
        return []

    def get_cs_keys(self):
        if 'cs_keys' in self.input:
            keys = self.input['cs_keys'].split(',')
            cs_keys = []
            for key in keys:
                k = ClosedSwarm.pubkey_from_der(key)
                cs_keys.append(k)

            return cs_keys
        return []

    def set_add_md5hash(self, value):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        self.input['makehash_md5'] = value
        self.metainfo_valid = False

    def get_add_md5hash(self):
        return self.input['makehash_md5']

    def set_add_crc32(self, value):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        self.input['makehash_crc32'] = value
        self.metainfo_valid = False

    def get_add_crc32(self):
        return self.input['makehash_crc32']

    def set_add_sha1hash(self, value):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        self.input['makehash_sha1'] = value
        self.metainfo_valid = False

    def get_add_sha1hash(self):
        return self.input['makehash_sha1']

    def set_create_merkle_torrent(self, value):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        self.input['createmerkletorrent'] = value
        self.metainfo_valid = False

    def get_create_merkle_torrent(self):
        return self.input['createmerkletorrent']

    def set_signature_keypair_filename(self, value):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        self.input['torrentsigkeypairfilename'] = value
        self.metainfo_valid = False

    def get_signature_keypair_filename(self):
        return self.input['torrentsigkeypairfilename']

    def get_live(self):
        return bool('live' in self.input and self.input['live'])

    def get_live_authmethod(self):
        return 'live' in self.input and self.input['live']['authmethod']

    def get_live_pubkey(self):
        if 'live' in self.input and 'pubkey' in self.input['live']:
            return self.input['live']['pubkey']
        else:
            return None

    def get_provider(self):
        if DEBUG_PREMIUM:
            pid = '47bce5c74f589f4867dbd57e9ca9f808'
            log('tdef::get_premium: return fake provider:', pid)
            return pid
        elif 'provider' in self.input:
            return self.input['provider']
        else:
            return None

    def get_content_id(self):
        if DEBUG_PREMIUM:
            cid = b64encode(self.input['name'])
            log('tdef::get_premium: return fake content id:', cid)
            return cid
        elif 'content_id' in self.input:
            return self.input['content_id']
        else:
            return None

    def get_premium(self):
        if DEBUG_PREMIUM:
            log('tdef::get_premium: return fake premium status')
            return 1
        elif 'premium' in self.input:
            return self.input['premium']
        else:
            return 0

    def get_license(self):
        return self.input.get('license', None)

    def get_tns_enabled(self):
        return self.input.get('tns', 0)

    def get_access(self):
        if 'access' in self.input:
            return self.input['access']
        else:
            return None

    def can_save(self):
        default_value = 1
        access = self.get_access()
        if access is None:
            if DEBUG:
                log('tdef::can_save: no access rules, allow saving')
            return default_value
        if 'allow_save' not in access:
            if DEBUG:
                log('tdef::can_save: no allow_save in access rules, allow saving')
            return default_value
        try:
            allow_save = int(access['allow_save'])
        except ValueError:
            if DEBUG:
                log('tdef::can_save: non-numeric allow_save in access rules, allow saving')
            return default_value

        if DEBUG:
            log('tdef::can_save: got allow_save from access rules:', allow_save)
        return allow_save

    def set_url_compat(self, value):
        self.input['url-compat'] = value

    def get_url_compat(self):
        return 'url-compat' in self.input and self.input['url-compat']

    def set_live_ogg_headers(self, value):
        if self.get_url_compat():
            raise ValueError('Cannot use P2PURLs for Ogg streams')
        self.input['ogg-headers'] = value

    def get_live_ogg_headers(self):
        if 'ogg-headers' in self.input:
            return self.input['ogg-headers']
        else:
            return None

    def set_metadata(self, value):
        self.input['ns-metadata'] = value

    def get_metadata(self):
        if 'ns-metadata' in self.input:
            return self.input['ns-metadata']
        else:
            return None

    def set_initial_peers(self, value):
        self.input['initial peers'] = value

    def get_initial_peers(self):
        if 'initial peers' in self.input:
            return self.input['initial peers']
        else:
            return []

    def set_authorized_peers(self, value):
        self.input['authorized-peers'] = value

    def get_authorized_peers(self):
        if 'authorized_peers' in self.input:
            return self.input['authorized-peers']
        else:
            return []

    def finalize(self, userabortflag = None, userprogresscallback = None):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        if self.metainfo_valid:
            if not self.ts_metainfo_valid:
                if self.input.has_key('x-ts-properties'):
                    self.metainfo['x-ts-properties'] = self.input['x-ts-properties']
                elif self.metainfo.has_key('x-ts-properties'):
                    del self.metainfo['x-ts-properties']
                self.ts_metainfo_valid = True
            return
        if 'live' in self.input:
            try:
                secs = parse_playtime_to_secs(self.input['playtime'])
            except:
                secs = 3600

            pl = float(self.get_piece_length())
            length = float(self.input['bps'] * secs)
            length *= 8
            if DEBUG:
                print >> sys.stderr, 'TorrentDef: finalize: length', length, 'piecelen', pl
            diff = length % pl
            add = (pl - diff) % pl
            newlen = int(length + add)
            d = self.input['files'][0]
            d['length'] = newlen
        infohash, metainfo = maketorrent.make_torrent_file(self.input, userabortflag=userabortflag, userprogresscallback=userprogresscallback)
        if infohash is not None:
            if self.get_url_compat():
                url = makeurl.metainfo2p2purl(metainfo)
                swarmid = makeurl.metainfo2swarmid(metainfo)
                self.infohash = swarmid
            else:
                self.infohash = infohash
            self.metainfo = metainfo
            self.input['name'] = metainfo['info']['name']
            self.input['piece length'] = metainfo['info']['piece length']
            self.metainfo_valid = True

    def is_finalized(self):
        return self.metainfo_valid

    def get_infohash(self):
        if self.metainfo_valid:
            return self.infohash
        raise TorrentDefNotFinalizedException()

    def get_metainfo(self):
        if self.metainfo_valid:
            return self.metainfo
        raise TorrentDefNotFinalizedException()

    def get_name(self):
        if self.metainfo_valid:
            return self.input['name']
        raise TorrentDefNotFinalizedException()

    def set_name(self, name):
        if self.readonly:
            raise OperationNotPossibleAtRuntimeException()
        self.input['name'] = name
        self.metainfo_valid = False

    def get_ts_metadata(self):
        if 'x-ts-properties' in self.input:
            return copy.copy(self.input['x-ts-properties'])
        else:
            return None

    def set_ts_metadata(self, metadata):
        self.input['x-ts-properties'] = metadata
        self.ts_metainfo_valid = False

    def get_ts_affiliate(self):
        affiliate_id = None
        meta = self.get_ts_metadata()
        if meta and 'affiliate_id' in meta:
            affiliate_id = meta['affiliate_id']
        return affiliate_id

    def set_ts_affiliate(self, affiliate_id):
        if DEBUG:
            log('TorrentDef::set_ts_affiliate: affiliate_id', affiliate_id)
        if 'x-ts-properties' not in self.input:
            self.input['x-ts-properties'] = {}
        meta = self.input['x-ts-properties']
        meta['affiliate_id'] = affiliate_id
        self.ts_metainfo_valid = False

    def get_ts_prebuf_pieces(self, idx = 0):
        prebuf_pieces = None
        meta = self.get_ts_metadata()
        if meta and 'prebuf_pieces' in meta:
            k = 'f' + str(idx)
            if k in meta['prebuf_pieces']:
                prebuf_pieces = meta['prebuf_pieces'][k]
        return prebuf_pieces

    def set_ts_prebuf_pieces(self, index, pieces):
        if DEBUG:
            log('TorrentDef::set_ts_prebuf_pieces: index', index, 'pieces', pieces)
        if 'x-ts-properties' not in self.input:
            self.input['x-ts-properties'] = {}
        meta = self.input['x-ts-properties']
        if 'prebuf_pieces' not in meta:
            meta['prebuf_pieces'] = {}
        if index == -1:
            index = 0
        key = 'f' + str(index)
        meta['prebuf_pieces'][key] = pieces
        self.ts_metainfo_valid = False

    def get_ts_duration(self, idx = 0):
        duration = None
        meta = self.get_ts_metadata()
        if meta and 'duration' in meta:
            k = 'f' + str(idx)
            if k in meta['duration']:
                duration = meta['duration'][k]
        if duration is None:
            return
        try:
            duration = int(duration)
        except:
            if DEBUG:
                log('TorrentDef::get_ts_duration: non-numeric duration: duration', duration)
            duration = None

        return duration

    def set_ts_duration(self, index, duration):
        if DEBUG:
            log('TorrentDef::set_ts_duration: index', index, 'duration', duration)
        if 'x-ts-properties' not in self.input:
            self.input['x-ts-properties'] = {}
        meta = self.input['x-ts-properties']
        if 'duration' not in meta:
            meta['duration'] = {}
        if index == -1:
            index = 0
        key = 'f' + str(index)
        meta['duration'][key] = duration
        self.ts_metainfo_valid = False

    def set_ts_bitrate(self, index, bitrate):
        if DEBUG:
            log('TorrentDef::set_ts_bitrate: index', index, 'bitrate', bitrate)
        if 'x-ts-properties' not in self.input:
            self.input['x-ts-properties'] = {}
        meta = self.input['x-ts-properties']
        if 'bitrate' not in meta:
            meta['bitrate'] = {}
        if index == -1:
            index = 0
        key = 'f' + str(index)
        meta['bitrate'][key] = bitrate
        self.ts_metainfo_valid = False

    def get_ts_replace_mp4_metatags(self, idx = 0):
        replace = None
        meta = self.get_ts_metadata()
        if meta and 'rpmp4mt' in meta:
            k = 'f' + str(idx)
            if k in meta['rpmp4mt']:
                replace = meta['rpmp4mt'][k]
        return replace

    def set_ts_replace_mp4_metatags(self, index, value):
        if DEBUG:
            log('TorrentDef::set_ts_replace_mp4_metatags: value', value)
        if 'x-ts-properties' not in self.input:
            self.input['x-ts-properties'] = {}
        meta = self.input['x-ts-properties']
        if 'rpmp4mt' not in meta:
            meta['rpmp4mt'] = {}
        if index == -1:
            index = 0
        key = 'f' + str(index)
        meta['rpmp4mt'][key] = value
        self.ts_metainfo_valid = False

    def get_ts_bitrate(self, idx = 0):
        bitrate = self.get_ts_bitrate_from_metainfo(idx)
        if bitrate is None:
            bitrate = self.get_ts_bitrate_from_duration(idx)
        return bitrate

    def get_ts_bitrate_from_metainfo(self, idx = 0):
        bitrate = None
        meta = self.get_ts_metadata()
        if meta and 'bitrate' in meta:
            k = 'f' + str(idx)
            if k in meta['bitrate']:
                bitrate = meta['bitrate'][k]
        if bitrate is None:
            return
        try:
            bitrate = int(bitrate)
        except:
            if DEBUG:
                log('TorrentDef::get_ts_bitrate: non-numeric bitrate: bitrate', bitrate)
            bitrate = None

        return bitrate

    def get_ts_bitrate_from_duration(self, idx = 0):
        bitrate = None
        try:
            duration = self.get_ts_duration(idx)
            if duration is None:
                return
            if 'files' in self.metainfo['info']:
                length = self.metainfo['info']['files'][idx]['length']
            else:
                length = self.metainfo['info']['length']
            bitrate = int(length) / int(duration)
        except:
            log_exc()

        return bitrate

    def get_name_as_unicode(self):
        if not self.metainfo_valid:
            raise TorrentDefNotFinalizedException()
        if 'name.utf-8' in self.metainfo['info']:
            try:
                return unicode(self.metainfo['info']['name.utf-8'], 'UTF-8')
            except UnicodeError:
                pass

        if 'name' in self.metainfo['info']:
            if 'encoding' in self.metainfo:
                try:
                    return unicode(self.metainfo['info']['name'], self.metainfo['encoding'])
                except UnicodeError:
                    pass
                except LookupError:
                    pass

            try:
                return unicode(self.metainfo['info']['name'])
            except UnicodeError:
                pass

            try:
                return unicode(self.metainfo['info']['name'], 'UTF-8')
            except UnicodeError:
                pass

            try:

                def filter_characters(name):

                    def filter_character(char):
                        if 0 < ord(char) < 128:
                            return char
                        else:
                            if DEBUG:
                                print >> sys.stderr, 'Bad character filter', ord(char), 'isalnum?', char.isalnum()
                            return u'?'

                    return u''.join([ filter_character(char) for char in name ])

                return unicode(filter_characters(self.metainfo['info']['name']))
            except UnicodeError:
                pass

        return u''

    def verify_torrent_signature(self):
        if self.metainfo_valid:
            return ACEStream.Core.Overlay.permid.verify_torrent_signature(self.metainfo)
        raise TorrentDefNotFinalizedException()

    def save(self, filename = None):
        if not self.readonly:
            self.finalize()
        if 'initial peers' in self.metainfo:
            del self.metainfo['initial peers']
        bdata = bencode(self.metainfo)
        if self.protected:
            bdata = m2_AES_encrypt(bdata, 'tslive_key')
            bdata = chr(1) + chr(2) + chr(3) + chr(4) + bdata
        if filename is not None:
            f = open(filename, 'wb')
            f.write(bdata)
            f.close()
        return bdata

    def get_protected(self):
        return self.protected

    def get_bitrate(self, file = None):
        if not self.metainfo_valid:
            raise NotYetImplementedException()
        return maketorrent.get_bitrate_from_metainfo(file, self.metainfo)

    def get_files_with_length(self, exts = None):
        return maketorrent.get_files(self.metainfo, exts)

    def get_files(self, exts = None):
        return [ filename for filename, length, fileindex in maketorrent.get_files(self.metainfo, exts) ]

    def get_files_with_indexes(self, exts = None):
        return [ (filename, fileindex) for filename, length, fileindex in maketorrent.get_files(self.metainfo, exts) ]

    def _get_all_files_as_unicode_with_length(self):
        if 'files' in self.metainfo['info']:
            join = os.path.join
            files = self.metainfo['info']['files']
            fileindex = -1
            for file_dict in files:
                fileindex += 1
                if 'path.utf-8' in file_dict:
                    try:
                        yield (join(*[ unicode(element, 'UTF-8') for element in file_dict['path.utf-8'] ]), file_dict['length'], fileindex)
                        continue
                    except UnicodeError:
                        pass

                if 'path' in file_dict:
                    if 'encoding' in self.metainfo:
                        encoding = self.metainfo['encoding']
                        try:
                            yield (join(*[ unicode(element, encoding) for element in file_dict['path'] ]), file_dict['length'], fileindex)
                            continue
                        except UnicodeError:
                            pass
                        except LookupError:
                            pass

                    try:
                        yield (join(*[ unicode(element) for element in file_dict['path'] ]), file_dict['length'], fileindex)
                        continue
                    except UnicodeError:
                        pass

                    try:
                        yield (join(*[ unicode(element, 'UTF-8') for element in file_dict['path'] ]), file_dict['length'], fileindex)
                        continue
                    except UnicodeError:
                        pass

                    try:

                        def filter_characters(name):

                            def filter_character(char):
                                if 0 < ord(char) < 128:
                                    return char
                                else:
                                    if DEBUG:
                                        print >> sys.stderr, 'Bad character filter', ord(char), 'isalnum?', char.isalnum()
                                    return u'?'

                            return u''.join([ filter_character(char) for char in name ])

                        yield (join(*[ unicode(filter_characters(element)) for element in file_dict['path'] ]), file_dict['length'], fileindex)
                        continue
                    except UnicodeError:
                        pass

        else:
            yield (self.get_name_as_unicode(), self.metainfo['info']['length'], 0)

    def get_files_as_unicode_with_length(self, exts = None):
        if not self.metainfo_valid:
            raise NotYetImplementedException()
        videofiles = []
        for filename, length, fileindex in self._get_all_files_as_unicode_with_length():
            prefix, ext = os.path.splitext(filename)
            if ext != '' and ext[0] == '.':
                ext = ext[1:]
            if exts is None or ext.lower() in exts:
                videofiles.append((filename, length))

        return videofiles

    def get_files_as_unicode_with_indexes(self, exts = None):
        if not self.metainfo_valid:
            raise NotYetImplementedException()
        videofiles = []
        for filename, length, fileindex in self._get_all_files_as_unicode_with_length():
            prefix, ext = os.path.splitext(filename)
            if ext != '' and ext[0] == '.':
                ext = ext[1:]
            if exts is None or ext.lower() in exts:
                videofiles.append((filename, fileindex))

        return videofiles

    def get_files_as_unicode(self, exts = None):
        return [ filename for filename, _ in self.get_files_as_unicode_with_length(exts) ]

    def get_length(self, selectedfiles = None):
        if not self.metainfo_valid:
            raise NotYetImplementedException()
        length, filepieceranges = maketorrent.get_length_filepieceranges_from_metainfo(self.metainfo, selectedfiles)
        return length

    def get_creation_date(self, default = 0):
        if not self.metainfo_valid:
            raise NotYetImplementedException()
        return self.metainfo.get('creation date', default)

    def is_multifile_torrent(self):
        if not self.metainfo_valid:
            raise NotYetImplementedException()
        return 'files' in self.metainfo['info']

    def is_merkle_torrent(self):
        if self.metainfo_valid:
            return 'root hash' in self.metainfo['info']
        raise TorrentDefNotFinalizedException()

    def get_url(self):
        if self.metainfo_valid:
            return makeurl.metainfo2p2purl(self.metainfo)
        raise TorrentDefNotFinalizedException()

    def get_index_of_file_in_files(self, file):
        if not self.metainfo_valid:
            raise NotYetImplementedException()
        info = self.metainfo['info']
        if file is not None and 'files' in info:
            for i in range(len(info['files'])):
                x = info['files'][i]
                intorrentpath = maketorrent.pathlist2filename(x['path'])
                if intorrentpath == file:
                    return i

            return ValueError('File not found in torrent')
        raise ValueError('File not found in single-file torrent')

    def copy(self):
        input = copy.copy(self.input)
        metainfo = copy.copy(self.metainfo)
        infohash = self.infohash
        t = TorrentDef(input, metainfo, infohash)
        t.metainfo_valid = self.metainfo_valid
        t.ts_metainfo_valid = self.ts_metainfo_valid
        t.protected = self.protected
        t.set_cs_keys(self.get_cs_keys_as_ders())
        return t


class MultiTorrent(Serializable, Copyable):

    @staticmethod
    def _create(data, protected):
        m = MultiTorrent(protected)
        for t in data['qualities']:
            tdef = TorrentDef._create(t['data'], protected)
            if DEBUG:
                log('multitorrent::_create: name', t['name'], 'infohash', binascii.hexlify(tdef.get_infohash()))
            m.add(tdef, t['name'])

        return m

    def __init__(self, protected = True):
        self.torrents = []
        self.protected = protected

    def add(self, tdef, name):
        self.torrents.append({'name': name,
         'tdef': tdef})

    def get(self, index):
        return self.torrents[index]

    def get_tdef(self, index):
        return self.torrents[index]['tdef']

    def get_qualities(self):
        qualities = []
        for t in self.torrents:
            bitrate = t['tdef'].get_ts_bitrate()
            if bitrate is None:
                bitrate = 0
            else:
                bitrate = int(bitrate * 8 / 1000)
            qualities.append({'name': t['name'],
             'bitrate': bitrate})

        return qualities

    def save(self, filename = None):
        torrent_list = []
        for t in self.torrents:
            torrent_list.append({'name': t['name'],
             'data': t['tdef'].get_metainfo()})

        bdata = bencode({'qualities': torrent_list})
        if self.protected:
            bdata = m2_AES_encrypt(bdata, '=Atl6GD#Vb+#QwW9zJy34lBOcM-7R7G)')
            bdata = chr(17) + chr(2) + chr(101) + chr(46) + bdata
        if filename is not None:
            f = open(filename, 'wb')
            f.write(bdata)
            f.close()
        return bdata

    def copy(self):
        m = MultiTorrent(self.protected)
        m.torrents = copy.copy(self.torrents)
        return m
