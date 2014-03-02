#Embedded file name: ACEStream\Core\DecentralizedTracking\MagnetLink\MagnetLink.pyo
import sys
from binascii import unhexlify
from urlparse import urlsplit
from traceback import print_exc
from threading import Lock
try:
    from urlparse import parse_qsl
except ImportError:
    from urllib import unquote_plus

    def parse_qsl(query):
        query = unquote_plus(query)
        for part in query.split('&'):
            if '=' in part:
                yield part.split('=', 1)


from ACEStream.Core.DecentralizedTracking.pymdht.core.identifier import Id, IdError
from ACEStream.Core.DecentralizedTracking.MagnetLink.MiniBitTorrent import MiniSwarm, MiniTracker
import ACEStream.Core.DecentralizedTracking.mainlineDHT as mainlineDHT
DEBUG = False

class Singleton:
    _singleton_lock = Lock()

    @classmethod
    def get_instance(cls, *args, **kargs):
        if hasattr(cls, '_singleton_instance'):
            return getattr(cls, '_singleton_instance')
        cls._singleton_lock.acquire()
        try:
            if not hasattr(cls, '_singleton_instance'):
                setattr(cls, '_singleton_instance', cls(*args, **kargs))
            return getattr(cls, '_singleton_instance')
        finally:
            cls._singleton_lock.release()


class MagnetHandler(Singleton):

    def __init__(self, raw_server):
        self._raw_server = raw_server
        self._magnets = []

    def get_raw_server(self):
        return self._raw_server

    def add_magnet(self, magnet_link, timeout):
        self._magnets.append(magnet_link)
        self._raw_server.add_task(magnet_link.close, timeout)

    def remove_magnet(self, magnet_link):
        if magnet_link in self._magnets:
            self._magnets.remove(magnet_link)

    def get_magnets(self):
        return self._magnets


class MagnetLink:

    def __init__(self, url, callback, timeout):
        self._callback = callback
        dn, xt, tr = self._parse_url(url)
        self._name = dn
        self._info_hash = xt
        self._tracker = tr
        magnet_handler = MagnetHandler.get_instance()
        magnet_handler.add_magnet(self, timeout)
        self._swarm = MiniSwarm(self._info_hash, magnet_handler.get_raw_server(), self.metainfo_retrieved)

    def get_infohash(self):
        return self._info_hash

    def get_name(self):
        return self._name

    def retrieve(self):
        if self._info_hash:
            dht = mainlineDHT.dht
            dht.get_peers(self._info_hash, Id(self._info_hash), self.potential_peers_from_dht, 0)
            try:
                if self._tracker:
                    MiniTracker(self._swarm, self._tracker)
            except:
                print_exc()

            return True
        else:
            print >> sys.stderr, 'No Infohash'
            return False

    def potential_peers_from_dht(self, lookup_id, peers):
        if peers:
            self._swarm.add_potential_peers(peers)

    def metainfo_retrieved(self, metainfo, peers = []):
        metadata = {'info': metainfo}
        if self._tracker:
            metadata['announce'] = self._tracker
        else:
            metadata['nodes'] = []
        if peers:
            metadata['initial peers'] = peers
        self._callback(metadata)
        self.close()

    def close(self):
        magnet_handler = MagnetHandler.get_instance()
        magnet_handler.remove_magnet(self)
        if DEBUG:
            print >> sys.stderr, 'Magnet.close()'
        self._swarm.close()

    @staticmethod
    def _parse_url(url):
        dn = None
        xt = None
        tr = None
        if DEBUG:
            print >> sys.stderr, 'Magnet._parse_url()', url
        schema, netloc, path, query, fragment = urlsplit(url)
        if schema == 'magnet':
            if '?' in path:
                pre, post = path.split('?', 1)
                if query:
                    query = '&'.join((post, query))
                else:
                    query = post
            for key, value in parse_qsl(query):
                if key == 'dn':
                    dn = value.decode()
                elif key == 'xt' and value.startswith('urn:btih:'):
                    xt = unhexlify(value[9:49])
                elif key == 'tr':
                    tr = value

            if DEBUG:
                print >> sys.stderr, 'Magnet._parse_url() NAME:', dn
            if DEBUG:
                print >> sys.stderr, 'Magnet._parse_url() HASH:', xt
            if DEBUG:
                print >> sys.stderr, 'Magnet._parse_url() TRAC:', tr
        return (dn, xt, tr)
