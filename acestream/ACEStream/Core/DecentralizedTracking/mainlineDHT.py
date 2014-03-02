#Embedded file name: ACEStream\Core\DecentralizedTracking\mainlineDHT.pyo
import sys
import logging
from traceback import print_exc
DEBUG = False
dht_imported = False
if sys.version.split()[0] >= '2.5':
    try:
        import ACEStream.Core.DecentralizedTracking.pymdht.core.pymdht as pymdht
        import ACEStream.Core.DecentralizedTracking.pymdht.plugins.routing_nice_rtt as routing_mod
        import ACEStream.Core.DecentralizedTracking.pymdht.plugins.lookup_a16 as lookup_mod
        dht_imported = True
    except ImportError as e:
        print_exc()

dht = None

def init(addr, conf_path):
    global dht_imported
    global dht
    if DEBUG:
        print >> sys.stderr, 'dht: DHT initialization', dht_imported
        log_level = logging.DEBUG
    else:
        log_level = logging.ERROR
    if dht_imported and dht is None:
        private_dht_name = None
        dht = pymdht.Pymdht(addr, conf_path, routing_mod, lookup_mod, private_dht_name, log_level)
        if DEBUG:
            print >> sys.stderr, 'dht: DHT running'


def control():
    import pdb
    pdb.set_trace()


def deinit():
    if dht is not None:
        try:
            dht.stop()
        except:
            pass
