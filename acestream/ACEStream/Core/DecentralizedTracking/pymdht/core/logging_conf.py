#Embedded file name: ACEStream\Core\DecentralizedTracking\pymdht\core\logging_conf.pyo
import logging
import os
FORMAT = '%(asctime)s %(levelname)s %(filename)s:%(lineno)s - %(funcName)s()\n%(message)s\n'
try:
    devnullstream = open('/dev/null', 'w')
except:
    from ACEStream.Utilities.NullFile import *
    devnullstream = NullFile()

logging.basicConfig(level=logging.CRITICAL, format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%a, %d %b %Y %H:%M:%S', stream=devnullstream)

def testing_setup(module_name):
    logger = logging.getLogger('dht')
    logger.setLevel(logging.DEBUG)
    filename = ''.join((str(module_name), '.log'))
    logger_file = os.path.join('test_logs', filename)
    logger_conf = logging.FileHandler(logger_file, 'w')
    logger_conf.setLevel(logging.DEBUG)
    logger_conf.setFormatter(logging.Formatter(FORMAT))
    logger.addHandler(logger_conf)


def setup(logs_path, logs_level):
    logger = logging.getLogger('dht')
    logger.setLevel(logs_level)
    logger_conf = logging.FileHandler(os.path.join(logs_path, 'dht.log'), 'w')
    logger_conf.setLevel(logs_level)
    logger_conf.setFormatter(logging.Formatter(FORMAT))
    logger.addHandler(logger_conf)
