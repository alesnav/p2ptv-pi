#Embedded file name: ACEStream\Plugin\BackgroundProcess.pyo
import ACEStream.Debug.console
import os
import sys
import time
import random
import binascii
import hashlib
import tempfile
import urllib
import re
import copy
import encodings
import subprocess
import socket
from math import ceil
from cStringIO import StringIO
from base64 import b64decode, b64encode, encodestring, decodestring
from traceback import print_stack, print_exc
from threading import Thread, currentThread, Lock, RLock
try:
    import json
except:
    import simplejson as json

from ACEStream.__init__ import DEFAULT_I2I_LISTENPORT, DEFAULT_SESSION_LISTENPORT, DEFAULT_HTTP_LISTENPORT
from ACEStream.version import VERSION
from ACEStream.Core.API import *
from ACEStream.Core.osutils import *
from ACEStream.Core.Utilities.utilities import get_collected_torrent_filename
from ACEStream.Utilities.LinuxSingleInstanceChecker import *
from ACEStream.Utilities.Instance2Instance import InstanceConnectionHandler, InstanceConnection
from ACEStream.Utilities.TimedTaskQueue import TimedTaskQueue
from ACEStream.Player.BaseApp import BaseApp
from ACEStream.Player.common import get_status_msgs
from ACEStream.Plugin.defs import *
from ACEStream.Plugin.Search import *
from ACEStream.Plugin.AtomFeedParser import *
from ACEStream.Video.defs import *
from ACEStream.Video.utils import videoextdefaults
from ACEStream.Video.VideoServer import VideoHTTPServer
from ACEStream.Video.Ogg import is_ogg, OggMagicLiveStream
from ACEStream.Core.debug import *
from ACEStream.WebUI.WebUI import WebIFPathMapper
from ACEStream.Core.ClosedSwarm.ClosedSwarm import InvalidPOAException
from ACEStream.Core.Utilities.logger import log, log_exc
#from ACEStream.Core.Ads.Manager import AdManager
from ACEStream.GlobalConfig import globalConfig
from ACEStream.Core.CacheDB.SqliteCacheDBHandler import UserProfile
DEBUG = True
DEBUG2 = False
DEBUG_EVENTS = False
DEBUG_TIME = False
DEBUG_IC_STATUS = False
ALLOW_MULTIPLE = True
SEND_LIVEPOS = True
SEND_LIVEPOS_JSON = True
CONTENT_ID_TORRENT_URL = 0
CONTENT_ID_DIRECT_URL = 1
CONTENT_ID_INFOHASH = 2
CONTENT_ID_PLAYER = 3
CONTENT_ID_RAW = 4
CONTENT_ID_ENCRYPTED_FILE = 5
MSG_DOWNLOAD_CANNOT_START = 1
MSG_STARTED_ADS = 2
MSG_STARTED_MAIN_CONTENT = 3


def get_default_api_version(apptype, exec_dir):
    if apptype == 'acestream':
        default_api_version = 2
    elif sys.platform != 'win32':
        default_api_version = 2
    else:
        plugin_path = os.path.join(exec_dir, '..', 'player', 'npts_plugin.dll')
        if os.path.isfile(plugin_path):
            default_api_version = 2
        else:
            default_api_version = 1
    log('get_default_api_version:', default_api_version)
    return default_api_version


def send_startup_event():
    if sys.platform == 'win32':
        try:
            import win32event
            import win32api
        except:
            return

        try:
            if DEBUG:
                log('bg::send_startup_event')
            startupEvent = win32event.CreateEvent(None, 0, 0, 'startupEvent')
            win32event.SetEvent(startupEvent)
            win32api.CloseHandle(startupEvent)
            if DEBUG:
                log('bg::send_startup_event: done')
        except:
            log_exc()


class BackgroundApp(BaseApp):

    def __init__(self, wrapper, redirectstderrout, appname, appversion, params, installdir):
        self.dusers = {}
        self.counter = 0
        self.interval = 120
        self.iseedeadpeople = False
        self.sharing_by_infohash = {}
        self.sharing_by_checksum = {}
        i2i_port = DEFAULT_I2I_LISTENPORT
        session_port = DEFAULT_SESSION_LISTENPORT
        http_port = DEFAULT_HTTP_LISTENPORT
        allow_non_local_client_connection = True
        for param in params:
            if param.startswith('--api-port='):
                try:
                    _, port = param.split('=')
                    i2i_port = int(port)
                except:
                    raise Exception, 'Bad api port value'

            elif param.startswith('--http-port='):
                try:
                    _, port = param.split('=')
                    http_port = int(port)
                except:
                    raise Exception, 'Bad http port value'

            elif param.startswith('--port='):
                try:
                    _, port = param.split('=')
                    session_port = int(port)
                except:
                    raise Exception, 'Bad port value'

            elif param == '--allow-non-local-client-connection':
                allow_non_local_client_connection = True

        apptype = globalConfig.get_value('apptype')
        self.default_api_version = get_default_api_version(apptype, installdir)
        if self.default_api_version == 1:
            i2i_port = 62062
            log('bg::init: fallback to fixed i2i_port:', i2i_port)
        if sys.platform != 'win32':
            i2i_port = 62062
        self.httpport = http_port
        globalConfig.set_value('allow-non-local-client-connection', allow_non_local_client_connection)
        self.videoHTTPServer = VideoHTTPServer(self.httpport)
        if DEBUG_TIME:
            print >> sys.stderr, '>>>time:bg:init: VideoHTTPServer created', time.clock()
        self.videoHTTPServer.register(self.videoservthread_error_callback, self.videoservthread_set_status_callback, self.videoservthread_load_torr)
        if DEBUG_TIME:
            print >> sys.stderr, '>>>time:bg:init: VideoHTTPServer registered', time.clock()
        BaseApp.__init__(self, wrapper, redirectstderrout, appname, appversion, params, installdir, i2i_port, session_port)
        if DEBUG_TIME:
            print >> sys.stderr, '>>>time:bg:init: BaseApp created', time.clock()
        if DEBUG2:
            log('bg::__init__: default_destdir', self.get_default_destdir())
        self.id2hits = Query2HitsMap()
        if DEBUG_TIME:
            print >> sys.stderr, '>>>time:bg:init: Query2HitsMap created', time.clock()
        self.searchmapper = SearchPathMapper(self.s, self.id2hits, self.tqueue)
        if DEBUG_TIME:
            print >> sys.stderr, '>>>time:bg:init: SearchPathMapper created', time.clock()
        self.hits2anypathmapper = Hits2AnyPathMapper(self.s, self.id2hits)
        if DEBUG_TIME:
            print >> sys.stderr, '>>>time:bg:init: Hits2AnyPathMapper created', time.clock()
        self.videoHTTPServer.add_path_mapper(self.searchmapper)
        self.videoHTTPServer.add_path_mapper(self.hits2anypathmapper)
        if DEBUG_TIME:
            print >> sys.stderr, '>>>time:bg:init: path mappers added', time.clock()
        self.webIFmapper = WebIFPathMapper(self, self.s)
        if DEBUG_TIME:
            print >> sys.stderr, '>>>time:bg:init: WebIFPathMapper created', time.clock()
        self.videoHTTPServer.add_path_mapper(self.webIFmapper)
        if DEBUG_TIME:
            print >> sys.stderr, '>>>time:bg:init: path mappers added', time.clock()
        self.videoHTTPServer.background_serve()
        if DEBUG_TIME:
            print >> sys.stderr, '>>>time:bg:init: background_serve() called', time.clock()
        if self.default_api_version < 2:
            send_startup_event()
        if DEBUG_TIME:
            print >> sys.stderr, '>>>time:bg:init: startup event sent', time.clock()

    def OnInit(self):
        try:
            BaseApp.OnInitBase(self)
            log('bg::OnInit: Awaiting commands')
            return True
        except Exception as e:
            log_exc()
            self.show_error(str(e))
            self.OnExit()
            return False

    def external_connection_made(self, s):
        ic = BGInstanceConnection(s, self, self.readlinecallback, self.videoHTTPServer)
        self.singsock2ic[s] = ic
        if DEBUG:
            log('bg:external_connection_made: ip', s.get_ip(), 'port', s.get_port(), 'myip', s.get_myip(), 'myport', s.get_myport(), 'connections', len(self.singsock2ic))

    def connection_lost(self, s):
        if DEBUG2:
            log('bg::connection_lost:')
        try:
            ic = self.singsock2ic[s]
            InstanceConnectionHandler.connection_lost(self, s)
        except:
            if DEBUG:
                print_exc()
            return

        gui_connection_lost_lambda = lambda : self.gui_connection_lost(ic)
        if DEBUG2:
            log('bg::connection_lost: schedule gui_connection_lost')
        self.run_delayed(gui_connection_lost_lambda)

    def gui_connection_lost(self, ic, switchp2ptarget = False):
        d2remove = None
        for d, duser in self.dusers.iteritems():
            if duser['uic'] == ic:
                duser['uic'] = None
                d2remove = d
                break

        if DEBUG2:
            log('bg::gui_connection_lost: switchp2ptarget', switchp2ptarget, 'd2remove', d2remove)
        if not switchp2ptarget:
            ic.info('')
        try:
            if switchp2ptarget:
                ic.cleanup_playback()
            else:
                ic.shutdown()
        except:
            log_exc()

        if d2remove is not None:
            d_delayed_remove_if_lambda = lambda : self.i2ithread_delayed_remove_if_not_complete(d2remove)
            if switchp2ptarget:
                delay = 1.0
            else:
                delay = 10.0
            if DEBUG2:
                log('bg::gui_connection_lost: schedule i2ithread_delayed_remove_if_not_complete, delay', delay)
            self.i2i_listen_server.add_task(d_delayed_remove_if_lambda, delay)

    def i2ithread_delayed_remove_if_not_complete(self, d2remove):
        if DEBUG2:
            log('bg: i2ithread_delayed_remove_if_not_complete')
        d2remove.set_state_callback(self.sesscb_remove_playing_callback)

    def can_remove_playing_download(self, d2remove):
        try:
            dlhash = binascii.hexlify(d2remove.get_hash())
        except:
            dlhash = 'cannot_get_hash'

        if d2remove not in self.dusers:
            if DEBUG2:
                log('bg::can_remove_playing_download: cannot remove, not in dusers: dlhash', dlhash)
            return False
        if self.dusers[d2remove]['uic'] is not None:
            if DEBUG2:
                log('bg::can_remove_playing_download: cannot remove, used by uic: dlhash', dlhash, 'uic', self.dusers[d2remove]['uic'])
            return False
        if DEBUG2:
            log('bg::can_remove_playing_download: can remove: dlhash', dlhash)
        return True

    def remove_playing_download(self, d2remove, removecontent = True, stop = False):
        if DEBUG:
            log('bg::remove_playing_download: hash', binascii.hexlify(d2remove.get_hash()))
        if self.can_remove_playing_download(d2remove):
            duser = self.dusers[d2remove]
            if DEBUG:
                log('bg::remove_playing_download: yes, no interest: removecontent', removecontent, 'stop', stop)
            if stop:
                BaseApp.stop_playing_download(self, d2remove)
            else:
                BaseApp.remove_playing_download(self, d2remove, removecontent)
            if 'streaminfo' in duser:
                stream = duser['streaminfo']['stream']
                stream.close()
            del self.dusers[d2remove]
        elif DEBUG:
            log('bg::remove_playing_download: skip remove')

    def i2ithread_readlinecallback(self, ic, cmd):
        gui_readlinecallback_lambda = lambda : self.gui_readlinecallback(ic, cmd)
        if cmd.startswith('LOAD'):
            self.tqueue.add_task(gui_readlinecallback_lambda, pos=0)
        else:
            self.tqueue.add_task(gui_readlinecallback_lambda)

    def split_params(self, url):
        params = {}
        idx = url.find('?')
        if idx > -1:
            _params = url[idx + 1:].split('&')
            url = url[:idx]
            for param in _params:
                if param.find('=') == -1:
                    continue
                name, value = param.split('=', 1)
                params[name] = value

        return (url, params)

    def gui_readlinecallback(self, ic, cmd):
        if DEBUG:
            log('bg::cmd: got command:', cmd)
        try:
            if cmd.startswith('HELLOBG'):
                cmd_name, sep, params_string = cmd.partition(' ')
                if len(params_string) != 0:
                    params = self.parse_cmd_params(params_string)
                    if 'version' in params:
                        try:
                            api_version = int(params['version'])
                            if DEBUG:
                                log('bg::cmd: detected api version:', api_version)
                            ic.api_version = api_version
                        except:
                            pass

                ic.hello()
            elif cmd.startswith('READY'):
                ic.ready = True
                ic.auth(self.s.get_authlevel())
            elif cmd.startswith('LOAD'):
                cmd_data = cmd.split(' ')
                if cmd.startswith('LOADASYNC'):
                    params_offset = 2
                    base_params_count = 3
                    async_load = True
                else:
                    params_offset = 1
                    base_params_count = 2
                    async_load = False
                if len(cmd_data) < base_params_count:
                    log('bg::cmd: len(cmd_data) < ' + str(base_params_count) + ':', len(cmd_data))
                    raise ValueError('Unformatted LOAD command')
                if async_load:
                    try:
                        request_id = int(cmd_data[1])
                    except:
                        log('bg::cmd: cannot parse request id')
                        raise ValueError('Unformatted LOAD command')

                if cmd_data[params_offset] == 'TORRENT':
                    content_id_type = CONTENT_ID_TORRENT_URL
                elif cmd_data[params_offset] == 'INFOHASH':
                    content_id_type = CONTENT_ID_INFOHASH
                elif cmd_data[params_offset] == 'PID':
                    content_id_type = CONTENT_ID_PLAYER
                elif cmd_data[params_offset] == 'RAW':
                    content_id_type = CONTENT_ID_RAW
                else:
                    log('bg::cmd: unknown type:', content_id_type)
                    raise ValueError('Unformatted LOAD command')
                if content_id_type == CONTENT_ID_PLAYER:
                    if len(cmd_data) != base_params_count + 1:
                        log('bg::cmd: len(cmd_data) != ' + str(base_params_count + 1) + ':', len(cmd_data))
                        raise ValueError('Unformatted LOAD command')
                elif len(cmd_data) != base_params_count + 4:
                    log('bg::cmd: len(cmd_data) != ' + str(base_params_count + 4) + ':', len(cmd_data))
                    raise ValueError('Unformatted LOAD command')
                content_id = cmd_data[params_offset + 1]
                developer_id = 0
                affiliate_id = 0
                zone_id = 0
                if content_id_type != CONTENT_ID_PLAYER:
                    try:
                        developer_id = int(cmd_data[params_offset + 2])
                    except ValueError:
                        pass

                    try:
                        affiliate_id = int(cmd_data[params_offset + 3])
                    except ValueError:
                        pass

                    try:
                        zone_id = int(cmd_data[params_offset + 4])
                    except ValueError:
                        pass

                if async_load:
                    status = {'status': 'loading'}
                    ic.status(status)
                try:
                    ret = self.load_torrent(ic, content_id_type, content_id, developer_id, affiliate_id, zone_id)
                    files = []
                    for x in ret['files']:
                        try:
                            urlencoded_name = urllib.quote(x[0].encode('utf-8'))
                        except:
                            print_exc()
                            urlencoded_name = ''

                        index = x[1]
                        files.append([urlencoded_name, index])

                    jsondata = {'status': ret['status'],
                     'files': files,
                     'infohash': ret['infohash'],
                     'checksum': ret['checksum']}
                    if ret.has_key('qualities'):
                        jsondata['qualities'] = ret['qualities']
                except Exception as e:
                    if async_load:
                        jsondata = {'status': 100,
                         'message': str(e)}
                    else:
                        raise e

                dump = json.dumps(jsondata)
                if DEBUG2:
                    log('bg::cmd: send json response:', dump)
                if async_load:
                    ic.send_load_response(request_id, dump)
                    status = {'status': 'idle'}
                    ic.status(status)
                else:
                    ic.send_response(dump)
            elif cmd.startswith('START'):
                cmd_data = cmd.split(' ')
                if len(cmd_data) < 3:
                    if DEBUG:
                        log('bg::cmd: expected at least 2 params: cmd', cmd, 'cmd_data', cmd_data)
                    raise ValueError, 'Unformatted START command'
                if cmd_data[1] == 'TORRENT':
                    content_id_type = CONTENT_ID_TORRENT_URL
                elif cmd_data[1] == 'URL':
                    content_id_type = CONTENT_ID_DIRECT_URL
                elif cmd_data[1] == 'INFOHASH':
                    content_id_type = CONTENT_ID_INFOHASH
                elif cmd_data[1] == 'PID':
                    content_id_type = CONTENT_ID_PLAYER
                elif cmd_data[1] == 'RAW':
                    content_id_type = CONTENT_ID_RAW
                elif cmd_data[1] == 'EFILE':
                    content_id_type = CONTENT_ID_ENCRYPTED_FILE
                else:
                    if DEBUG:
                        log('bg::cmd: unknown content id type:', cmd_data[1])
                    raise ValueError, 'Unformatted START command'
                content_id = cmd_data[2]
                if content_id_type == CONTENT_ID_PLAYER:
                    if len(cmd_data) < 4:
                        if DEBUG:
                            log('bg::cmd: expected 3 params: cmd', cmd)
                        raise ValueError, 'Unformatted START command'
                elif content_id_type == CONTENT_ID_DIRECT_URL:
                    if len(cmd_data) < 6:
                        if DEBUG:
                            log('bg::cmd: expected at least 5 params: cmd', cmd)
                        raise ValueError, 'Unformatted START command'
                elif content_id_type == CONTENT_ID_ENCRYPTED_FILE:
                    if len(cmd_data) != 3:
                        if DEBUG:
                            log('bg::cmd: expected 2 params: cmd', cmd)
                        raise ValueError, 'Unformatted START command'
                elif len(cmd_data) < 7:
                    if DEBUG:
                        log('bg::cmd: expected at least 6 params: cmd', cmd)
                    raise ValueError, 'Unformatted START command'
                if content_id_type == CONTENT_ID_DIRECT_URL:
                    params_offset = 3
                elif content_id_type == CONTENT_ID_ENCRYPTED_FILE:
                    pass
                else:
                    params_offset = 4
                    fileindex = 0
                    extra_file_indexes = []
                    try:
                        indexes = cmd_data[3].split(',')
                        for i in xrange(len(indexes)):
                            if i == 0:
                                fileindex = int(indexes[0])
                            else:
                                extra_file_indexes.append(int(indexes[i]))

                    except ValueError:
                        pass

                developer_id = 0
                affiliate_id = 0
                zone_id = 0
                position = 0
                quality_id = 0
                if content_id_type != CONTENT_ID_PLAYER and content_id_type != CONTENT_ID_ENCRYPTED_FILE:
                    try:
                        developer_id = int(cmd_data[params_offset])
                    except ValueError:
                        pass

                    try:
                        affiliate_id = int(cmd_data[params_offset + 1])
                    except ValueError:
                        pass

                    try:
                        zone_id = int(cmd_data[params_offset + 2])
                    except ValueError:
                        pass

                    try:
                        quality_id = int(cmd_data[params_offset + 3])
                    except (ValueError, IndexError):
                        pass

                if content_id_type == CONTENT_ID_DIRECT_URL and len(cmd_data) == 7:
                    try:
                        position = int(cmd_data[6])
                    except:
                        pass

                for d, duser in self.dusers.iteritems():
                    if duser['uic'] == ic:
                        ic.info('')
                        self.gui_connection_lost(ic, switchp2ptarget=True)
                        if DEBUG2:
                            log('bg: calling gui_connection_lost on prev ic')
                        break

                if ic.api_version >= 3 and not self.check_user_profile():
                    log('bg::cmd: request user data')
                    ic.event('getuserdata')
                    return
                if content_id_type == CONTENT_ID_DIRECT_URL:
                    a = content_id.split('@@')
                    if len(a) == 1:
                        main_url = content_id
                        download_url = None
                    elif len(a) == 2:
                        main_url = a[0]
                        download_url = a[1]
                    else:
                        if DEBUG:
                            log('bg::cmd: url contains more than two parts: content_id', content_id)
                        raise ValueError, 'Unformatted START command'
                    ic.state(BGP_STATE_PREBUFFERING)
                    self.start_direct_download(ic, main_url, download_url, developer_id, affiliate_id, zone_id, position)
                elif content_id_type == CONTENT_ID_ENCRYPTED_FILE:
                    ic.state(BGP_STATE_PREBUFFERING)
                    self.play_encrypted_file(ic, content_id)
                else:
                    player_data = self.get_torrent(content_id_type, content_id, quality_id)
                    if player_data is None:
                        raise ValueError, 'Cannot retrieve torrent'
                    if player_data.has_key('developer_id'):
                        developer_id = player_data['developer_id']
                    if player_data.has_key('affiliate_id'):
                        affiliate_id = player_data['affiliate_id']
                    if player_data.has_key('zone_id'):
                        zone_id = player_data['zone_id']
                    ic.state(BGP_STATE_PREBUFFERING)
                    status = {'status': 'starting'}
                    ic.status(status)
                    self.get_torrent_start_download(ic, player_data['tdef'], fileindex, extra_file_indexes, developer_id, affiliate_id, zone_id, position)
            elif cmd.startswith('GETPID'):
                cmd_data = cmd.split(' ')
                if len(cmd_data) != 5:
                    raise ValueError('Unformatted GETPID command')
                try:
                    infohash = cmd_data[1]
                    infohash = binascii.unhexlify(infohash)
                    developer_id = int(cmd_data[2])
                    affiliate_id = int(cmd_data[3])
                    zone_id = int(cmd_data[4])
                except:
                    raise ValueError('Unformatted GETPID command')

                sharing = self.sharing_by_infohash.get(infohash, 1)
                if sharing == 0:
                    player_id = ''
                else:
                    player_id = BaseApp.get_player_id_from_db(self, None, infohash, developer_id, affiliate_id, zone_id)
                    if player_id is None:
                        player_id = ''
                ic.send_response(player_id)
            elif cmd.startswith('GETCID'):
                try:
                    cmd_name, sep, params_string = cmd.partition(' ')
                    if len(sep) == 0:
                        raise Exception, 'malformed GETCID command'
                    params = self.parse_cmd_params(params_string)
                    if not ('checksum' in params or 'infohash' in params):
                        raise Exception, 'missing checksum and infohash'
                    checksum = params.get('checksum', None)
                    infohash = params.get('infohash', None)
                    if checksum is not None:
                        if len(checksum) != 40:
                            raise Exception, 'bad checksum length'
                        checksum = binascii.unhexlify(checksum)
                    if infohash is not None:
                        if len(infohash) != 40:
                            raise Exception, 'bad infohash length'
                        infohash = binascii.unhexlify(infohash)
                    try:
                        developer_id = int(params.get('developer', 0))
                    except:
                        developer_id = 0

                    try:
                        affiliate_id = int(params.get('affiliate', 0))
                    except:
                        affiliate_id = 0

                    try:
                        zone_id = int(params.get('zone', 0))
                    except:
                        zone_id = 0

                    if infohash is not None:
                        sharing = self.sharing_by_infohash.get(infohash, 1)
                    elif checksum is not None:
                        sharing = self.sharing_by_checksum.get(checksum, 1)
                    if sharing == 0:
                        player_id = ''
                    else:
                        player_id = BaseApp.get_player_id_from_db(self, checksum, infohash, developer_id, affiliate_id, zone_id)
                        if player_id is None:
                            player_id = ''
                    ic.send_response(player_id)
                except:
                    print_exc()

            elif cmd.startswith('GETADURL'):
                try:
                    cmd_name, sep, params_string = cmd.partition(' ')
                    if len(sep) == 0:
                        raise Exception, 'malformed GETADURL command'
                    params = self.parse_cmd_params(params_string)
                    if 'width' not in params:
                        raise Exception, 'missing width'
                    if 'height' not in params:
                        raise Exception, 'missing height'
                    if DEBUG2:
                        log('bg:cmd:getadurl: params', params)
                    action = params.get('action', 'load')
                    ad_width = int(params['width'])
                    ad_height = int(params['height'])
                    url = None
                    if url is not None and ic.api_version >= 3:
                        params = {'type': 'ad',
                         'url': url,
                         'width': str(ad_width),
                         'height': str(ad_height)}
                        ic.event('showurl', params)
                except:
                    print_exc()

            elif cmd.startswith('USERDATA'):
                try:
                    cmd_name, sep, params_string = cmd.partition(' ')
                    if len(sep) == 0:
                        raise Exception, 'malformed USERDATA command'
                    data = json.loads(params_string)
                    log('bg::cmd:user_data: data', data)
                    age_id = None
                    gender_id = None
                    for field in data:
                        if 'gender' in field:
                            gender_id = int(field['gender'])
                        elif 'age' in field:
                            age_id = int(field['age'])

                    if gender_id is None:
                        raise Exception, 'missing gender'
                    if age_id is None:
                        raise Exception, 'missing age'
                    profile = UserProfile.create()
                    profile.set_active(1)
                    profile.set_gender(gender_id)
                    profile.set_age(age_id)
                    profile.save()
                except:
                    print_exc()

            elif cmd.startswith('SHUTDOWN'):
                ic.state(BGP_STATE_IDLE)
                ic.shutdown()
            elif cmd.startswith('STOP'):
                ic.state(BGP_STATE_IDLE)
                ic.status({'status': 'idle'})
                for d, duser in self.dusers.iteritems():
                    if duser['uic'] == ic:
                        if DEBUG2:
                            log('bg::on_stop: call gui_connection_lost')
                        ic.info('')
                        self.gui_connection_lost(ic, switchp2ptarget=True)
                        break

            elif cmd.startswith('SUPPORTS'):
                ic.set_supported_vod_events([VODEVENT_START])
            elif cmd.startswith('SAVE'):
                if DEBUG:
                    log('bg: got save', cmd)
                try:
                    cmd_name, sep, params_string = cmd.partition(' ')
                    if len(sep) == 0:
                        raise Exception, 'malformed SAVE command'
                    params = self.parse_cmd_params(params_string)
                    if 'infohash' not in params:
                        raise Exception, 'missing infohash'
                    if 'index' not in params:
                        raise Exception, 'missing index'
                    if 'path' not in params:
                        raise Exception, 'missing path'
                    if DEBUG:
                        log('bg:cmd:save: params', params)
                    infohash = binascii.unhexlify(params['infohash'])
                    for d in self.s.get_downloads(DLTYPE_TORRENT):
                        if d.get_def().get_infohash() == infohash:
                            try:
                                index = int(params['index'])
                                path = params['path']
                                func = lambda : d.save_content(path, index)
                                self.run_delayed(func)
                            except:
                                print_exc()

                            break

                except:
                    print_exc()

            elif cmd.startswith('LIVESEEK'):
                try:
                    if SEND_LIVEPOS:
                        _, pos = cmd.split(' ')
                        pos = int(pos)
                        for d, duser in self.dusers.iteritems():
                            if duser['uic'] == ic:
                                if duser['playing_download'] is not None:
                                    duser['playing_download'].live_seek(pos)
                                    ic.restart_playback(is_live=True)
                                elif DEBUG:
                                    log('bg::cmd:live_seek: no playing download')

                except:
                    print_exc()
                    raise Exception, 'Error while seeking'

            elif cmd.startswith('DUR'):
                if DEBUG2:
                    log('bg: got duration', cmd)
                try:
                    _, url, duration = cmd.split(' ')
                    if url != ic.get_video_url():
                        raise Exception('ic.url does not match')
                    duration = int(duration) / 1000
                    for d, duser in self.dusers.iteritems():
                        if duser['uic'] == ic:
                            if duser['playing_download'] is not None:
                                duser['playing_download'].got_duration(duration)

                            def notify_content_type(duser = duser):
                                try:
                                    if duser['playing_ad']:
                                        duser['uic'].info('Advertising video', MSG_STARTED_ADS, force=True)
                                    else:
                                        duser['uic'].info('Main content', MSG_STARTED_MAIN_CONTENT, force=True)
                                except:
                                    pass

                            def clear_notify_content_type(duser = duser):
                                try:
                                    duser['uic'].info('')
                                except:
                                    pass

                            self.i2i_listen_server.add_task(notify_content_type, 2)
                            self.i2i_listen_server.add_task(clear_notify_content_type, 8)
                            break

                except:
                    log_exc()

            elif cmd.startswith('EVENT'):
                try:
                    cmd_name, sep, tail = cmd.partition(' ')
                    if len(tail) != 0:
                        event_name, sep, params_string = tail.partition(' ')
                        if len(params_string) != 0:
                            params = self.parse_cmd_params(params_string)
                        else:
                            params = None
                        if DEBUG2:
                            log('bg::cmd: got event: name', event_name, 'params', params)
                        dl = None
                        is_ad = False
                        for d, duser in self.dusers.iteritems():
                            if duser['uic'] == ic:
                                is_ad = duser['playing_ad']
                                dl = d
                                break

                        if dl is not None and not is_ad:
                            if event_name == 'play':
                                self.tns_send_event(dl, 'PLAY')
                            elif event_name == 'pause':
                                self.tns_send_event(dl, 'PAUSE')
                            elif event_name == 'stop':
                                self.tns_send_event(dl, 'STOP')
                            elif event_name == 'seek':
                                if params.has_key('position') and int(params['position']) != 0:
                                    self.tns_send_event(dl, 'SEEK', {'position': params['position']})
                except:
                    if DEBUG:
                        print_exc()

            elif cmd.startswith('PLAYBACK'):
                if DEBUG2:
                    log('bg: got playback', cmd)
                cmd = self.parse_playback_cmd(cmd)
                if cmd is None:
                    return
                dlhash, event = cmd
                for d, duser in self.dusers.iteritems():
                    if duser['uic'] == ic:
                        if duser['playing_download'] is None:
                            if DEBUG:
                                log('bg::cmd: no playing download')
                            return
                        playing_hash = binascii.hexlify(duser['playing_download'].get_hash())
                        if playing_hash != dlhash:
                            if DEBUG:
                                log('bg::cmd: playing infohash does not match event: playing_hash', playing_hash, 'event_hash', dlhash)
                            return
                        if event != 100 and duser['playing_ad']:
                            main_download, is_ad, ad_downloads = self.get_ad_downloads(d)
                            if not ad_downloads.has_key(duser['playing_download']):
                                if DEBUG2:
                                    log('bg::cmd: playing ad download is not in ad downloads')
                                return
                            adinfo = ad_downloads[duser['playing_download']]
                            if DEBUG2:
                                log('bg::cmd: send event on playing ad: dlhash', dlhash, 'info', adinfo, 'event', event)
                            if event == 0:
                                event_names = ['impression', 'creativeView', 'start']
                            elif event == 25:
                                event_names = ['firstQuartile']
                            elif event == 50:
                                event_names = ['midpoint']
                            elif event == 75:
                                event_names = ['thirdQuartile']
                            else:
                                if DEBUG:
                                    log('bg::cmd: unknown event: event', event)
                                event_names = None
                            if event_names is not None:
                                tracking_list = []
                                for event_name in event_names:
                                    if adinfo['ad']['tracking'].has_key(event_name):
                                        tracking_list.extend(adinfo['ad']['tracking'][event_name])

                                if len(tracking_list):
                                    if adinfo['ad']['adsystem'] == self.ad_manager.TS_ADSYSTEM:
                                        add_sign = True
                                    else:
                                        add_sign = False
                                    lambda_send_event = lambda : self.ad_manager.send_event(tracking_list, add_sign)
                                    self.run_delayed(lambda_send_event)
                                elif DEBUG:
                                    log('bg::cmd: no handlers for event: event_names', event_names)
                        if event == 100:
                            self.finished_playback(d, duser)

            else:
                log('bg::cmd: unknown command:', cmd)
        except Exception as e:
            log_exc()
            ic.stop()
            ic.state(BGP_STATE_IDLE)
            try:
                errmsg = str(e)
            except:
                errmsg = 'unknown error'

            ic.status({'status': 'err',
             'error_id': 0,
             'error_message': errmsg})
            ic.cleanup_playback()

    def stop_download(self, d2stop, show_url = None, msg = None):
        for d, duser in self.dusers.iteritems():
            if d == d2stop:
                if duser['uic'] is None:
                    if DEBUG2:
                        log('bg::stop_download: call remove_playing_download')
                    self.remove_playing_download(d2stop, removecontent=True, stop=False)
                else:
                    duser['uic'].stop()
                    duser['uic'].state(BGP_STATE_IDLE)
                    duser['uic'].status({'status': 'idle'})
                    if show_url is not None and duser['uic'].api_version >= 3:
                        params = {'type': 'notification',
                         'url': show_url}
                        duser['uic'].event('showurl', params)
                    if msg is not None:
                        duser['uic'].info(msg)
                    if DEBUG2:
                        log('bg::stop_download: call gui_connection_lost')
                    self.gui_connection_lost(duser['uic'], switchp2ptarget=True)
                break

    def parse_cmd_params(self, params_string):
        params = {}
        plist = params_string.split(' ')
        for s in plist:
            if len(s) == 0:
                continue
            name, sep, value = s.partition('=')
            if len(sep) == 0:
                if DEBUG:
                    log('bg::parse_cmd_params: missing param value separator:', s)
                continue
            if DEBUG2:
                log('bg::parse_cmd_params: found param: name', name, 'value', value)
            try:
                value = urllib.unquote(value)
                value = value.decode('utf-8')
            except:
                print_exc()
                continue

            params[name] = value

        return params

    def make_cmd_params(self, params):
        plist = []
        for name, value in params.iteritems():
            try:
                value = urllib.quote(value.encode('utf-8'))
                plist.append(name + '=' + value)
            except:
                if DEBUG2:
                    print_exc()

        return ' '.join(plist)

    def parse_playback_cmd(self, cmd):
        try:
            parts = cmd.split(' ')
            if len(parts) != 3:
                if DEBUG:
                    log('bg::parse_playback_cmd: bad parts count: cmd', cmd, 'parts', parts)
                return
            if parts[0] != 'PLAYBACK':
                if DEBUG:
                    log('bg::parse_playback_cmd: bad cmd: cmd', cmd, 'parts', parts)
                return
            event = int(parts[2])
            if event not in (0, 25, 50, 75, 100):
                if DEBUG:
                    log('bg::parse_playback_cmd: bad event: cmd', cmd, 'parts', parts)
                return
            url = parts[1]
            m = re.search('/content/([0-9a-f]+)/', url)
            if m is None:
                if DEBUG:
                    log('bg::parse_playback_cmd: no match in url: cmd', cmd, 'url', url)
                return
            infohash = m.group(1)
            return (infohash, event)
        except:
            if DEBUG:
                print_exc()
            return

    def get_torrent(self, content_id_type, content_id, quality_id = None):
        player_data = None
        if content_id_type == CONTENT_ID_TORRENT_URL and content_id.startswith('http://torrentstream.info/get/'):
            content_id_type = CONTENT_ID_PLAYER
            content_id = content_id.replace('http://torrentstream.info/get/', '')
            if DEBUG2:
                log('bg::get_torrent: update old-style id: content_id_type', content_id_type, 'content_id', content_id)
        if content_id_type == CONTENT_ID_TORRENT_URL:
            try:
                tdef = TorrentDef.load_from_url(content_id)
            except:
                if DEBUG2:
                    print_exc()
                raise Exception, 'Cannot load torrent file'

            qualities = None
            if isinstance(tdef, MultiTorrent):
                if quality_id is None:
                    quality_id = 0
                try:
                    qualities = tdef.get_qualities()
                    tdef = tdef.get_tdef(quality_id)
                except:
                    if DEBUG2:
                        print_exc()
                    raise Exception, 'Cannot load torrent file'

            torrent_data = tdef.save()
            checksum = hashlib.sha1(torrent_data).digest()
            player_data = {'tdef': tdef,
             'checksum': checksum,
             'need_update': True}
            if qualities is not None:
                player_data['qualities'] = qualities
            self.s.save_torrent_local(tdef, checksum)
        elif content_id_type == CONTENT_ID_INFOHASH:
            player_data = self.get_torrent_by_infohash(content_id)
        elif content_id_type == CONTENT_ID_PLAYER:
            player_data = self.get_player_data(content_id)
        elif content_id_type == CONTENT_ID_RAW:
            torrent_data = b64decode(content_id)
            buf = StringIO(torrent_data)
            tdef = TorrentDef._read(buf)
            torrent_data = tdef.save()
            checksum = hashlib.sha1(torrent_data).digest()
            player_data = {'tdef': tdef,
             'checksum': checksum,
             'need_update': True}
            self.s.save_torrent_local(tdef, checksum)
        if player_data and 'tdef' in player_data:
            tdef = player_data['tdef']
            checksum = player_data.get('checksum', None)
            infohash = tdef.get_infohash()
            sharing = tdef.get_sharing()
            self.sharing_by_infohash[infohash] = sharing
            if checksum is not None:
                self.sharing_by_checksum[checksum] = sharing
        return player_data

    def load_torrent(self, ic, content_id_type, content_id, developer_id, affiliate_id, zone_id):
        player_data = self.get_torrent(content_id_type, content_id)
        if player_data is None:
            raise ValueError('Cannot load torrent data')
        tdef = player_data['tdef']
        if player_data.has_key('need_update') and player_data['need_update']:
            BaseApp.update_torrent(self, player_data['tdef'], developer_id, affiliate_id, zone_id)
        if tdef.get_live():
            videofiles = tdef.get_files_as_unicode_with_indexes()
        else:
            videofiles = tdef.get_files_as_unicode_with_indexes(exts=videoextdefaults)
            if DEBUG2:
                try:
                    log('bg::load_torrent: videofiles', videofiles)
                except:
                    print_exc()

        ret = {'infohash': binascii.hexlify(tdef.get_infohash()),
         'checksum': binascii.hexlify(player_data['checksum']),
         'files': videofiles}
        if player_data.has_key('qualities'):
            ret['qualities'] = player_data['qualities']
        if len(videofiles) == 1:
            ret['status'] = 1
        elif len(videofiles) == 0:
            ret['status'] = 0
        elif len(videofiles) > 1:
            ret['status'] = 2
        return ret

    def get_torrent_start_download(self, ic, tdef, fileindex, extra_file_indexes, developer_id, affiliate_id, zone_id, position):
        if tdef.get_live():
            videofiles = tdef.get_files_with_indexes()
        else:
            videofiles = tdef.get_files_with_indexes(exts=videoextdefaults)
        if len(videofiles) == 1:
            dlfile, idx = videofiles[0]
        elif len(videofiles) == 0:
            raise ValueError('bg::get_torrent_start_download: No video files found! Giving up')
        elif len(videofiles) > 1:
            if self.s.get_authlevel() == 0:
                raise ValueError('Playing multiple files is not supported')
            if DEBUG2:
                log('bg::get_torrent_start_download: Found several files:', videofiles)
            dlfile = None
            for name, idx in videofiles:
                if idx == fileindex:
                    dlfile = name
                    break

            if dlfile is None:
                log('bg::get_torrent_start_download: bad fileindex', fileindex, 'videofiles', videofiles)
                raise ValueError('Bad file index')
            if DEBUG2:
                log('bg::get_torrent_start_download: selected file:', dlfile)
        if DEBUG:
            if self.ext_version:
                log('bg::get_torrent_start_download: dlfile:', dlfile, ' fileindex:', fileindex)
            else:
                log('bg::get_torrent_start_download: dlfile:', dlfile, ' fileindexes:', fileindex)
        infohash = tdef.get_infohash()
        oldd = None
        for d in self.s.get_downloads(DLTYPE_TORRENT):
            if d.get_def().get_infohash() == infohash:
                oldd = d
                break

        if oldd is None or oldd not in self.downloads_in_vodmode:
            for d, duser in self.dusers.iteritems():
                if duser['uic'] == ic:
                    if DEBUG2:
                        log('bg: get_torrent_start_download: stop old download for the current ic')
                    ic.cleanup_playback()
                    ic.close()
                    BaseApp.remove_playing_download(self, d, False)
                    del self.dusers[d]

            if DEBUG:
                if oldd is None:
                    log('bg: get_torrent_start_download: Starting new Download')
                else:
                    log('bg: get_torrent_start_download: Restarting old Download in VOD mode')
        else:
            try:
                duser = self.dusers[oldd]
                olduic = duser['uic']
                del self.dusers[oldd]
            except:
                log_exc()

        if not self.ext_version:
            return
        d = BaseApp.start_download(self, tdef, dlfile, extra_file_indexes, developer_id, affiliate_id, zone_id)
        duser = {'uic': ic,
         'mediastate': MEDIASTATE_STOPPED}
        self.dusers[d] = duser
        duser['time_started'] = None
        duser['playing_download'] = None
        duser['playing_ad'] = False
        duser['start_position'] = position
        self.shutteddown = False

    def start_direct_download(self, ic, main_url, download_url, developer_id, affiliate_id, zone_id, position):
        if DEBUG:
            log('bg::start_direct_download: main_url', main_url, 'download_url', download_url, 'd', developer_id, 'a', affiliate_id, 'z', zone_id, 'p', position)
        tdef = BaseApp.get_torrent_from_url(self, main_url)
        if tdef is not None:
            if DEBUG:
                log('bg::start_direct_download: found torrent from url: main_url', main_url, 'infohash', binascii.hexlify(tdef.get_infohash()))
            if download_url is not None:
                urllist = tdef.get_urllist()
                if urllist is None:
                    urllist = []
                if download_url not in urllist:
                    urllist.append(download_url)
                    if DEBUG:
                        log('bg::start_direct_download: update url-list:', urllist)
                    tdef.set_urllist(urllist, invalidate=False)
            return self.get_torrent_start_download(ic, tdef, 0, [], developer_id, affiliate_id, zone_id, position)
        urlhash = hashlib.sha1(main_url).digest()
        oldd = self.s.get_download(DLTYPE_DIRECT, urlhash)
        if oldd is None or oldd not in self.downloads_in_vodmode:
            for d, duser in self.dusers.iteritems():
                if duser['uic'] == ic:
                    if DEBUG2:
                        log('bg::start_direct_download: stop old download for the current ic')
                    ic.cleanup_playback()
                    ic.close()
                    BaseApp.remove_playing_download(self, d, False)
                    del self.dusers[d]

            if DEBUG:
                if oldd is None:
                    log('bg::start_direct_download: start new download')
                else:
                    log('bg::start_direct_download: restart old download in vod mode')
        else:
            try:
                del self.dusers[oldd]
            except:
                log_exc()

        d = BaseApp.start_direct_download(self, main_url, download_url, developer_id, affiliate_id, zone_id)
        duser = {'uic': ic,
         'mediastate': MEDIASTATE_STOPPED}
        self.dusers[d] = duser
        duser['time_started'] = None
        duser['playing_download'] = None
        duser['playing_ad'] = False
        duser['start_position'] = position
        self.shutteddown = False

    def play_encrypted_file(self, ic, path, position = 0):
        if DEBUG:
            log('bg::play_encrypted_file: path', path, 'position', position)
        try:
            path = urllib.unquote(path)
            path = path.decode('utf-8')
        except:
            if DEBUG:
                print_exc()

        d = BaseApp.play_encrypted_file(self, path)
        duser = {'uic': ic,
         'mediastate': MEDIASTATE_STOPPED}
        self.dusers[d] = duser
        duser['time_started'] = None
        duser['playing_download'] = None
        duser['playing_ad'] = False
        duser['start_position'] = position
        self.shutteddown = False

    def gui_states_callback(self, dslist, haspeerlist):
        gui_states_callback_lambda = lambda : self._gui_states_callback(dslist, haspeerlist)
        self.tqueue.add_task(gui_states_callback_lambda)

    def _gui_states_callback(self, dslist, haspeerlist):
        all_dslist, playing_dslist, totalhelping, totalspeed = BaseApp.gui_states_callback(self, dslist, haspeerlist)
        for ds in playing_dslist:
            d = ds.get_download()
            if self.dusers.has_key(d):
                duser = self.dusers[d]
                if duser['uic'] is not None:
                    fake_main_status = None
                    ad = None
                    if duser['playing_ad'] and duser['playing_download'] is not None:
                        ad = duser['playing_download']
                    elif d in self.downloads_in_admode:
                        for _ad, info in self.downloads_in_admode[d].iteritems():
                            if info['finished'] is None and not info['failed']:
                                ad = _ad
                                fake_main_status = DLSTATUS_STOPPED
                                break

                    main_status = self.get_uic_status(ds, duser['mediastate'], fake_main_status)
                    ad_status = None
                    if ad is not None:
                        if all_dslist.has_key(ad):
                            adds = all_dslist[ad]
                            ad_status = self.get_uic_status(adds, duser['mediastate'], True)
                    duser['uic'].status(main_status, ad_status)
                    if not duser['playing_ad'] and d.get_type() == DLTYPE_TORRENT and d.get_def().get_live():
                        params = None
                        if SEND_LIVEPOS:
                            vod_stats = ds.get_vod_stats()
                            if vod_stats is not None:
                                vs = vod_stats.get('videostatus', None)
                            else:
                                vs = None
                            if vs is not None and vs.live_streaming and not vs.prebuffering:
                                vs = vod_stats['videostatus']
                                if vs.live_first_piece is not None and vs.live_last_piece is not None:
                                    curpos = vs.playback_pos_real
                                    if not vs.in_range(vs.live_first_piece_with_offset + 1, vs.live_last_piece + 1, curpos):
                                        if DEBUG_EVENTS:
                                            log('bg::gui_states_callback: adjust curpos: curpos', curpos, 'first_with_offset', vs.live_first_piece_with_offset, 'last', vs.live_last_piece)
                                        curpos = vs.normalize(vs.live_first_piece_with_offset + 1)
                                    live_buffer_pieces = int(vs.live_buffer_pieces * 1.5)
                                    dist = vs.dist_range(curpos, vs.playback_pos)
                                    if DEBUG_EVENTS:
                                        log('bg::gui_states_callback: ajust live buffer pieces: playback_pos', vs.playback_pos, 'curpos', curpos, 'dist', dist, 'live_buffer_pieces', live_buffer_pieces)
                                    live_buffer_pieces += dist
                                    params = {'pos': str(curpos),
                                     'is_live': '1' if vs.playback_pos_is_live else '0',
                                     'buffer_pieces': str(live_buffer_pieces),
                                     'last': str(vs.last_piece),
                                     'live_first': str(vs.live_first_piece_with_offset),
                                     'live_last': str(vs.live_last_piece),
                                     'first_ts': str(vs.live_first_ts),
                                     'last_ts': str(vs.live_last_ts)}
                        else:
                            preprogress = ds.get_vod_prebuffering_progress()
                            live_first = 1
                            live_last = 668
                            if preprogress != 1.0:
                                live_pos = live_first + 1
                            else:
                                live_pos = live_last
                            now = long(time.time())
                            params = {'pos': str(live_pos),
                             'last': '5343',
                             'live_first': str(live_first),
                             'live_last': str(live_last),
                             'first_ts': str(now - 5),
                             'last_ts': str(now)}
                        if params is not None:
                            duser['uic'].event('livepos', params)
                    if d.get_type() == DLTYPE_TORRENT and ds.get_status() in [DLSTATUS_DOWNLOADING, DLSTATUS_SEEDING]:
                        completed_files = ds.get_files_completed()
                        if completed_files is not None:
                            for i in xrange(len(completed_files)):
                                if completed_files[i]:
                                    params = {'infohash': binascii.hexlify(d.get_hash()),
                                     'index': str(i)}
                                    k = 'cansave-' + params['infohash'] + '-' + params['index']
                                    save_type = d.can_save_content()
                                    if k not in duser['uic'].reported_events and save_type != 0:
                                        duser['uic'].reported_events[k] = 1
                                        if save_type == 1:
                                            params['format'] = 'plain'
                                        elif save_type == 2:
                                            params['format'] = 'encrypted'
                                        duser['uic'].event('cansave', params)

                    if duser.has_key('time_started'):
                        if DEBUG_IC_STATUS:
                            log('bg::gui_states_callback: time_started', duser['time_started'])
                        if duser['time_started'] is None:
                            if main_status['status'] == 'prebuf':
                                duser['time_started'] = time.time()
                        elif time.time() - duser['time_started'] > 60:
                            if DEBUG_IC_STATUS:
                                log('bg::gui_states_callback: check main status: status', main_status['status'], 'downloaded', main_status['downloaded'])
                            if main_status['status'] == 'prebuf' and main_status['downloaded'] == 0:
                                duser['uic'].info('Cannot find active peers', MSG_DOWNLOAD_CANNOT_START)
                            else:
                                del duser['time_started']
                                duser['uic'].info('')

    def get_uic_status(self, ds, mediastate, fake_status = None):
        if fake_status is None:
            status = ds.get_status()
        else:
            status = fake_status
        if status == DLSTATUS_STOPPED_ON_ERROR:
            status = {'status': 'err',
             'error_id': 0,
             'error_message': str(ds.get_error())}
        elif status in [DLSTATUS_ALLOCATING_DISKSPACE, DLSTATUS_WAITING4HASHCHECK, DLSTATUS_HASHCHECKING]:
            status = {'status': 'check',
             'progress': int(ds.get_progress() * 100)}
        elif status == DLSTATUS_STOPPED:
            status = {'status': 'idle'}
        elif ds.get_progress() == 1.0:
            status = {'status': 'dl'}
        elif ds.get_vod_playable():
            if mediastate == MEDIASTATE_STOPPED:
                status = {'status': 'idle'}
            elif mediastate == MEDIASTATE_PAUSED:
                status = {'status': 'buf',
                 'progress': int(ds.get_vod_prebuffering_progress() * 100),
                 'time': int(ds.get_vod_playable_after())}
            else:
                status = {'status': 'dl'}
        else:
            preprogress = ds.get_vod_prebuffering_progress()
            if preprogress != 1.0:
                status = {'status': 'prebuf',
                 'progress': int(preprogress * 100),
                 'time': int(ds.get_vod_playable_after())}
            else:
                t = int(ds.get_vod_playable_after())
                if t > 3600:
                    t = 3600
                elif t > 1800:
                    t = 2700
                elif t > 900:
                    t = 1800
                elif t > 300:
                    t = int(t / 60) * 60
                elif t > 60:
                    t = int(t / 10) * 10
                status = {'status': 'wait',
                 'time': t}
        if status['status'] not in ('idle', 'err', 'check'):
            immediate_progress = 0
            if status['status'] in ('prebuf', 'buf', 'dl'):
                total_progress = int(ds.get_progress() * 100)
            else:
                total_progress = 0
            status['total_progress'] = total_progress
            status['immediate_progress'] = immediate_progress
            status['speed_down'] = int(ds.get_current_speed(DOWNLOAD))
            status['http_speed_down'] = int(ds.get_http_speed())
            status['speed_up'] = int(ds.get_current_speed(UPLOAD))
            status['peers'] = ds.get_num_peers()
            status['http_peers'] = ds.get_http_peers()
            status['downloaded'] = ds.get_total_transferred(DOWNLOAD)
            status['http_downloaded'] = ds.get_http_transferred()
            status['uploaded'] = ds.get_total_transferred(UPLOAD)
            d = ds.get_download()
            if SEND_LIVEPOS_JSON and d.get_type() == DLTYPE_TORRENT and d.get_def().get_live():
                vod_stats = ds.get_vod_stats()
                if vod_stats is not None and vod_stats['videostatus'] is not None and vod_stats['videostatus'].live_streaming:
                    vs = vod_stats['videostatus']
                    have_ranges = []
                    have = vs.have[:]
                    if len(have):
                        p = None
                        f = None
                        t = None
                        for i in sorted(have):
                            if p is None:
                                f = i
                            elif i != p + 1:
                                t = p
                                have_ranges.append((f, t))
                                f = i
                            p = i

                        have_ranges.append((f, i))
                    status['live_data'] = {'first': vs.first_piece,
                     'last': vs.last_piece,
                     'live_first': vs.live_first_piece,
                     'live_last': vs.live_last_piece,
                     'live_first_ts': vs.live_first_ts,
                     'live_last_ts': vs.live_last_ts,
                     'pos': vs.playback_pos_real,
                     'is_live': vs.playback_pos_is_live,
                     'have': have_ranges}
        return status

    def get_ad_downloads(self, d, main = None):
        main_download = None
        ad_downloads = None
        is_ad = False
        if d in self.downloads_in_admode:
            main_download = d
            ad_downloads = self.downloads_in_admode[d]
        elif d in self.downloads_in_vodmode:
            main_download = d
        else:
            if main is None:
                return (None, False, None)
            for main_d, ads in self.downloads_in_admode.iteritems():
                if d in ads.keys() and main_d == main:
                    main_download = main_d
                    ad_downloads = ads
                    is_ad = True
                    break

            if main_download is None:
                return (None, False, None)
        if DEBUG2:
            log('bg::get_ad_downloads: main', binascii.hexlify(main_download.get_hash()), 'this', binascii.hexlify(d.get_hash()), 'is_ad', is_ad)
            if ad_downloads is not None:
                for ad, info in ad_downloads.iteritems():
                    log('bg::get_ad_downloads: ad', binascii.hexlify(ad.get_hash()), 'info', info)

        return (main_download, is_ad, ad_downloads)

    def download_failed_callback(self, failed_download, error):
        self.dlinfo_lock.acquire()
        try:
            try:
                failed_reason = str(error)
            except:
                failed_reason = 'unknown'

            if DEBUG2:
                log('bg::download_failed_callback: hash', binascii.hexlify(failed_download.get_hash()), 'failed_reason', failed_reason)
            downloads = {}
            if failed_download in self.downloads_in_vodmode or failed_download in self.downloads_in_admode:
                if DEBUG2:
                    log('bg::download_failed_callback: failed download is main', binascii.hexlify(failed_download.get_hash()))
                downloads[failed_download] = None
                playing_ad = False
            else:
                playing_ad = True
                for main_d, ads in self.downloads_in_admode.iteritems():
                    if failed_download in ads.keys():
                        if DEBUG2:
                            log('bg::download_failed_callback: found main download: main', binascii.hexlify(main_d.get_hash()), 'ad', binascii.hexlify(failed_download.get_hash()))
                        downloads[main_d] = None

            for d, duser in self.dusers.iteritems():
                if d in downloads:
                    if DEBUG2:
                        log('bg::download_failed_callback: found duser for download', binascii.hexlify(d.get_hash()))
                    downloads[d] = duser

            for d, duser in downloads.iteritems():
                if duser is not None:
                    self._finished_playback(d, duser, failed=True, failed_reason=failed_reason, current_download=failed_download, playing_ad=playing_ad)
                elif DEBUG2:
                    log('bg::download_failed_callback: no duser for download', binascii.hexlify(d.get_hash()))

        finally:
            self.dlinfo_lock.release()

    def finished_playback(self, main_download, duser):
        self.dlinfo_lock.acquire()
        try:
            self._finished_playback(main_download, duser)
        finally:
            self.dlinfo_lock.release()

    def _finished_playback(self, main_download, duser, failed = False, failed_reason = '', current_download = None, playing_ad = None):
        if current_download is not None:
            d = current_download
        else:
            d = duser['playing_download']
        if playing_ad is None:
            playing_ad = duser['playing_ad']
        duser['playing_download'] = None
        duser['playing_ad'] = False
        if d is None:
            if DEBUG:
                log('bg::finished_playback: error: no playing download')
            return
        main_download, is_ad, ad_downloads = self.get_ad_downloads(main_download)
        if DEBUG2:
            log('bg::_finished_playback: this', binascii.hexlify(d.get_hash()) if d is not None else 'None', 'main', binascii.hexlify(main_download.get_hash()), 'is_ad', is_ad, 'failed', failed)
            if ad_downloads is not None:
                for ad, info in ad_downloads.iteritems():
                    log('bg::finished_playback: ad', binascii.hexlify(ad.get_hash()), 'info', info)

        if d != main_download and not playing_ad:
            if DEBUG2:
                log('bg::finished_playback: error: main download is not the playing one, but playing_ad is not set')
            return
        if playing_ad:
            if ad_downloads is None:
                if DEBUG2:
                    log('bg::finished_playback: error: finished ad, but ad download is empty')
                return
            if d not in ad_downloads:
                if DEBUG2:
                    log('bg::finished_playback: error: finished ad, but current download is not in ad downloads')
                return
        else:
            self.tns_send_event(main_download, 'COMPLETE')
        if ad_downloads is None:
            return
        if not playing_ad:
            if DEBUG2:
                log('bg::finished_playback: content finished playback, do nothing')
            return
        if failed:
            if DEBUG2:
                log('bg::finished_playback: ad download failed: failed_reason', failed_reason)
            adinfo = ad_downloads[d]
            adinfo['failed'] = True
            try:
                if adinfo['ad']['tracking'].has_key('error'):
                    lambda_send_error = lambda : self.ad_manager.send_error(adinfo['ad']['tracking']['error'], 400, failed_reason)
                    self.run_delayed(lambda_send_error)
            except:
                if DEBUG:
                    print_exc()

        else:
            adinfo = ad_downloads[d]
            if adinfo['started'] is None:
                if DEBUG2:
                    log('bg::finished_playback: error: ad download finished but not started')
                return
            if adinfo['finished'] is not None:
                if DEBUG2:
                    log('bg::finished_playback: error: ad download already finished: time', ad_downloads[d]['finished'])
                return
            finished = time.time()
            if not adinfo['ad']['interruptable']:
                ad_playback_time = int(ceil(finished - adinfo['started']))
                if ad_playback_time < adinfo['ad']['duration'] - 1:
                    if DEBUG2:
                        log('bg::finished_playback: error: ad playback time is wrong: ad_playback_time', ad_playback_time, 'duration', adinfo['ad']['duration'])
                    return
                try:
                    size = d.get_content_length()
                    if size is not None:
                        read_bytes = duser['uic'].cstreaminfo['stream'].read_bytes
                        if DEBUG2:
                            log('bg::finished_playback: got read bytes: read_bytes', read_bytes, 'size', size)
                        if read_bytes < size:
                            if DEBUG2:
                                log('bg::finished_playback: error: player read wrong amount of ad data: read_bytes', read_bytes, 'size', size)
                            return
                except:
                    if DEBUG2:
                        log('bg::finished_playback: error: failed to get read_bytes')
                    print_exc()

            adinfo['finished'] = finished
            tracking_list = adinfo['ad']['tracking']['complete']
            if len(tracking_list):
                if adinfo['ad']['adsystem'] == self.ad_manager.TS_ADSYSTEM:
                    add_sign = True
                else:
                    add_sign = False
                lambda_send_event = lambda : self.ad_manager.send_event(tracking_list, add_sign)
                self.run_delayed(lambda_send_event)
        first_unfinished_ad = None
        for ad, info in ad_downloads.iteritems():
            if info['finished'] is None and not info['failed']:
                if DEBUG2:
                    log('bg::finished_playback: found unfinished ad:', binascii.hexlify(ad.get_hash()))
                first_unfinished_ad = ad
                break

        if first_unfinished_ad is not None:
            if ad_downloads[first_unfinished_ad]['ad']['interruptable']:
                if 'start_params' in duser and duser['start_params'] is not None:
                    if DEBUG2:
                        log('bg::finished_playback: main content has finished prebuffering, skip interruptable ad: hash', binascii.hexlify(first_unfinished_ad.get_hash()))
                    first_unfinished_ad = None
        if first_unfinished_ad is None:
            if 'start_params' in duser and duser['start_params'] is not None:
                params = duser['start_params']
                if DEBUG2:
                    log('bg::finished_playback: no unfinished ads, start main content: main', binascii.hexlify(main_download.get_hash()), 'params', params)
                self.start_playback(main_download, main_download, params, False)
            else:
                if DEBUG2:
                    log('bg::finished_playback: main content has not finished prebuffering yet: main', binascii.hexlify(main_download.get_hash()))
                duser['uic'].state(BGP_STATE_PREBUFFERING)
        else:
            if ad_downloads[first_unfinished_ad]['started'] is not None:
                if DEBUG2:
                    log('bg::finished_playback: error: first unfinished ad is already started')
                return
            if ad_downloads[first_unfinished_ad]['start_params'] is not None:
                params = ad_downloads[first_unfinished_ad]['start_params']
                ad_downloads[first_unfinished_ad]['started'] = time.time()
                if params['complete']:
                    ad_downloads[first_unfinished_ad]['completed'] = True
                self.start_playback(first_unfinished_ad, main_download, params, is_ad=True, is_interruptable_ad=ad_downloads[first_unfinished_ad]['ad']['interruptable'], click_url=ad_downloads[first_unfinished_ad]['ad']['click_through'])
            else:
                if DEBUG2:
                    log('bg::finished_playback: first unfinished ad has not finished prebuffering yet')
                duser['uic'].state(BGP_STATE_PREBUFFERING)

    def start_playback(self, d, main_download, params, is_ad, is_interruptable_ad = False, click_url = None):
        if DEBUG2:
            log('bg::start_playback: d', binascii.hexlify(d.get_hash()), 'main', binascii.hexlify(main_download.get_hash()), 'params', params)
        if params['filename']:
            stream = open(params['filename'], 'rb')
        else:
            stream = params['stream']
        blocksize = params.get('blocksize', None)
        if d.get_type() == DLTYPE_TORRENT:
            if blocksize is None:
                blocksize = d.get_def().get_piece_length()
            is_live = d.get_def().get_live()
        else:
            if blocksize is None:
                blocksize = 524288
            is_live = False
        mimetype = params.get('mimetype', 'application/octet-stream')
        streaminfo = {'mimetype': mimetype,
         'stream': stream,
         'length': params['length'],
         'blocksize': blocksize,
         'svc': d.get_mode() == DLMODE_SVC,
         'bitrate': params['bitrate']}
        use_libavi = globalConfig.get_value('use_libavi', False)
        if not use_libavi and (mimetype == 'video/avi' or mimetype == 'video/x-msvideo') and params['length'] > 2147483648L:
            use_libavi = True
        if use_libavi:
            extension = 'avi'
        else:
            extension = None
        duser = self.dusers[main_download]
        duser['streaminfo'] = streaminfo
        if duser['uic'] is not None:
            duser['uic'].set_streaminfo(duser['streaminfo'], is_ad)
            if is_ad:
                position = 0
            else:
                position = duser['start_position']
                self.tns_send_event(d, 'PLAY')
            duser['uic'].start_playback(d.get_hash(), is_ad, is_interruptable_ad, position, is_live, extension, click_url)
            duser['uic'].state(BGP_STATE_DOWNLOADING)
            duser['mediastate'] = MEDIASTATE_PLAYING
            duser['playing_download'] = d
            duser['playing_ad'] = is_ad
        else:
            duser['mediastate'] = MEDIASTATE_STOPPED

    def sesscb_vod_event_callback(self, d, event, params, main_download = None):
        gui_vod_event_callback_lambda = lambda : self.gui_vod_event_callback(d, event, params, main_download)
        self.run_delayed(gui_vod_event_callback_lambda)

    def gui_vod_event_callback(self, d, event, params, main_download):
        if DEBUG2:
            if main_download is None:
                main = None
            else:
                main = binascii.hexlify(main_download.get_hash())
            log('bg::gui_vod_event_callback: infohash', binascii.hexlify(d.get_hash()), 'event', event, 'params', params, 'main_download', main)
        if event != VODEVENT_METADATA:
            main_download, is_ad, ad_downloads = self.get_ad_downloads(d, main_download)
            if main_download is None:
                if DEBUG:
                    log('bg::gui_vod_event_callback: cannot find main download')
                return
            if not self.dusers.has_key(main_download):
                if DEBUG:
                    log('bg::gui_vod_event_callback: main download is not in duser: infohash', binascii.hexlify(main_download.get_hash()))
                return
        if event == VODEVENT_START:
            is_interruptable_ad = False
            click_url = None
            if ad_downloads is not None:
                first_unfinished_ad = None
                for ad, info in ad_downloads.iteritems():
                    if info['finished'] is None and not info['failed']:
                        if DEBUG2:
                            log('bg::gui_vod_event_callback: found unfinished ad:', binascii.hexlify(ad.get_hash()))
                        first_unfinished_ad = ad
                        break

                if first_unfinished_ad is None:
                    if is_ad:
                        if DEBUG2:
                            log('bg::gui_vod_event_callback: error: got start for ad but there is no unfinished ads')
                        return
                    if DEBUG2:
                        log('bg::gui_vod_event_callback: no unfinished ads, start main content')
                elif is_ad and d == first_unfinished_ad:
                    if DEBUG2:
                        log('bg::gui_vod_event_callback: current ad is the first unfinished, start it')
                    ad_downloads[d]['started'] = time.time()
                    if params['complete']:
                        ad_downloads[d]['completed'] = True
                    is_interruptable_ad = ad_downloads[d]['ad']['interruptable']
                    click_url = ad_downloads[d]['ad']['click_through']
                else:
                    if DEBUG2:
                        log('bg::gui_vod_event_callback: skip start, wait for unfinished ad')
                    if is_ad:
                        ad_downloads[d]['start_params'] = params
                        if DEBUG2:
                            log('bg::gui_vod_event_callback: mark ad as ready: ad', binascii.hexlify(d.get_hash()), 'params', params)
                    else:
                        duser = self.dusers[main_download]
                        duser['start_params'] = params
                        if DEBUG2:
                            log('bg::gui_vod_event_callback: save start params for main download: main', binascii.hexlify(main_download.get_hash()), 'params', params)
                    return
            self.start_playback(d, main_download, params, is_ad, is_interruptable_ad, click_url)
        elif event == VODEVENT_PAUSE:
            duser = self.dusers[main_download]
            if duser['uic'] is not None:
                duser['uic'].pause()
                duser['uic'].state(BGP_STATE_BUFFERING)
            duser['mediastate'] = MEDIASTATE_PAUSED
            self.tns_send_event(main_download, 'BUFFER')
        elif event == VODEVENT_RESUME:
            duser = self.dusers[main_download]
            if duser['uic'] is not None:
                duser['uic'].resume()
                duser['uic'].state(BGP_STATE_DOWNLOADING)
            duser['mediastate'] = MEDIASTATE_PLAYING
            self.tns_send_event(main_download, 'BUFFERFULL')
        elif event == VODEVENT_METADATA:
            if d.get_type() == DLTYPE_TORRENT:
                metadata = {}
                if params.has_key('prebuf_pieces') and params['prebuf_pieces']:
                    metadata['index'] = params['index']
                    metadata['prebuf_pieces'] = params['prebuf_pieces']
                if params.has_key('duration') and params['duration']:
                    metadata['index'] = params['index']
                    metadata['duration'] = params['duration']
                BaseApp.got_ts_metadata(self, d.get_def(), metadata)

    def get_supported_vod_events(self):
        return [VODEVENT_START, VODEVENT_PAUSE, VODEVENT_RESUME]

    def videoservthread_error_callback(self, e, url):
        videoserver_error_guicallback_lambda = lambda : self.videoserver_error_guicallback(e, url)
        self.run_delayed(videoserver_error_guicallback_lambda)

    def videoserver_error_guicallback(self, e, url):
        log('bg: Video server reported error', str(e))

    def videoservthread_set_status_callback(self, status):
        videoserver_set_status_guicallback_lambda = lambda : self.videoserver_set_status_guicallback(status)
        self.run_delayed(videoserver_set_status_guicallback_lambda)
 
       
    def videoservthread_load_torr(self, t_type, t_str):
        if DEBUG:
	  log('bg::loading %s %s' % (t_type, t_str))
        ic = BGInstanceConnection2(self, self.videoHTTPServer)
        content_id = t_str
        if t_type == 'TORRENT':
           content_id_type = CONTENT_ID_TORRENT_URL
        elif t_type == 'INFOHASH':
           content_id_type = CONTENT_ID_INFOHASH
        elif t_type == 'PID':
             content_id_type = CONTENT_ID_PLAYER
        elif t_type == 'RAW':
                  content_id_type = CONTENT_ID_RAW
        else:
            log('bg::cmd: unknown type:', content_id_type)
            raise ValueError('Unformatted LOAD command')
        developer_id = 0
        affiliate_id = 0
        zone_id = 0
        position = 0
        quality_id = 0
        fileindex = 0
        extra_file_indexes = 0
        try:
           ret = self.load_torrent(ic, content_id_type, content_id, developer_id, affiliate_id, zone_id)
           files = []
           for x in ret['files']:
               try:
                   urlencoded_name = urllib.quote(x[0].encode('utf-8'))
               except:
                   print_exc()
                   urlencoded_name = ''
               index = x[1]
               files.append([urlencoded_name, index])
        except Exception as e:
           log("bg: error ", e)
    
        player_data = self.get_torrent(content_id_type, content_id, quality_id)
        if player_data is None:
          raise ValueError, 'Cannot retrieve torrent'
        if player_data.has_key('developer_id'):
          developer_id = player_data['developer_id']
        if player_data.has_key('affiliate_id'):
          affiliate_id = player_data['affiliate_id']
        if player_data.has_key('zone_id'):
          zone_id = player_data['zone_id']

        self.get_torrent_start_download(ic, player_data['tdef'], fileindex, extra_file_indexes, developer_id, affiliate_id, zone_id, position)

    
    def videoserver_set_status_guicallback(self, status):
        pass

    def gui_webui_remove_download(self, d2remove):
        if DEBUG:
            log('bg: gui_webui_remove_download')
        self.gui_webui_halt_download(d2remove, stop=False)

    def gui_webui_stop_download(self, d2stop):
        if DEBUG:
            log('bg: gui_webui_stop_download')
        self.gui_webui_halt_download(d2stop, stop=True)

    def gui_webui_restart_download(self, d2restart):
        duser = {'uic': None}
        self.dusers[d2restart] = duser
        d2restart.restart()

    def gui_webui_save_download(self, d2save, path):
        try:
            if sys.platform == 'win32':
                from win32com.shell import shell
                pidl = shell.SHGetSpecialFolderLocation(0, 5)
                defaultpath = shell.SHGetPathFromIDList(pidl)
            else:
                defaultpath = os.path.expandvars('$HOME')
        except:
            defaultpath = ''

        filename = 'test.mkv'
        if globalConfig.get_mode() == 'client_wx':
            import wx
            dlg = wx.FileDialog(None, message='Save file', defaultDir=defaultpath, defaultFile=filename, wildcard='All files (*.*)|*.*', style=wx.SAVE)
            dlg.Raise()
            result = dlg.ShowModal()
            dlg.Destroy()
            if result == wx.ID_OK:
                path = dlg.GetPath()
                d2save.save_content(path)

    def gui_webui_create_stream(self, config):
        if sys.platform == 'win32':
            if globalConfig.get_value('apptype') == 'torrentstream':
                exename = 'tsengine_stream.exe'
            else:
                exename = 'ace_stream.exe'
            stream_engine_path = os.path.join(self.installdir, exename)
        else:
            stream_engine_path = os.path.join(self.installdir, 'tsengine-stream')
        if not os.path.exists(stream_engine_path):
            raise Exception, 'Cannot find stream engine: ' + stream_engine_path
        for param in ['name', 'source']:
            if param not in config:
                raise Exception, 'Missing param: ' + param
            if not config[param]:
                raise Exception, 'Empty param: ' + param

        args = [stream_engine_path,
         '--name',
         config['name'],
         '--source',
         config['source'],
         '--debug',
         str(self.debug_level)]
        if 'destdir' in config:
            args.extend(['--destdir', config['destdir']])
        if 'bitrate' in config:
            try:
                bitrate = int(config['bitrate'])
                args.extend(['--bitrate', str(bitrate)])
            except:
                if DEBUG:
                    log('bg::gui_webui_create_stream: bad bitrate format:', config['bitrate'])

        if 'trackers' in config:
            try:
                trackers = []
                tmp = config['trackers'].split('\n')
                for t in tmp:
                    t = t.strip()
                    if len(t):
                        t = t.replace(' ', '%20')
                        trackers.append(t)

                if len(trackers):
                    args.extend(['--trackers', ','.join(trackers)])
            except:
                if DEBUG:
                    print_exc()

        if config.get('host', None):
            args.extend(['--host', config['host']])
        if config.get('port', None):
            args.extend(['--port', config['port']])
        if config.get('piecelen', None):
            args.extend(['--piecesize', config['piecelen']])
        if config.get('duration', None):
            args.extend(['--duration', config['duration']])
        args_utf8 = []
        for x in args:
            if isinstance(x, unicode):
                x = x.encode('utf-8')
            args_utf8.append(x)

        if DEBUG:
            log('bg::gui_webui_create_stream: args', args)
        subprocess.Popen(args_utf8, close_fds=True)
        retries = 10
        interval = 1.0
        while retries > 0:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect(('127.0.0.1', 6879))
                s.shutdown(socket.SHUT_RDWR)
                s.close()
                break
            except Exception as e:
                log('bg::gui_webui_create_stream: check stream process:' + str(e))

            time.sleep(interval)
            retries -= 1

    def gui_webui_halt_download(self, d2halt, stop = False):
        if d2halt in self.dusers:
            try:
                duser = self.dusers[d2halt]
                olduic = duser['uic']
                if olduic is not None:
                    log('bg: gui_webui_halt_download: Oops, someone interested, removing anyway')
                    olduic.shutdown()
                if 'streaminfo' in duser:
                    stream = duser['streaminfo']['stream']
                    stream.close()
            finally:
                del self.dusers[d2halt]

        if stop:
            BaseApp.stop_playing_download(self, d2halt)
        else:
            BaseApp.remove_playing_download(self, d2halt, removecontent=True)

    def gui_webui_remove_all_downloads(self, ds2remove):
        if DEBUG:
            log('bg: gui_webui_remove_all_downloads')
        for d2remove in ds2remove:
            self.gui_webui_halt_download(d2remove, stop=False)

    def gui_webui_stop_all_downloads(self, ds2stop):
        if DEBUG:
            log('bg: gui_webui_stop_all_downloads')
        for d2stop in ds2stop:
            self.gui_webui_halt_download(d2stop, stop=True)

    def gui_webui_restart_all_downloads(self, ds2restart):
        if DEBUG:
            log('bg: gui_webui_restart_all_downloads')
        for d2restart in ds2restart:
            self.gui_webui_restart_download(d2restart)

class BGInstanceConnection(InstanceConnection):

    def __init__(self, singsock, connhandler, readlinecallback, videoHTTPServer):
        InstanceConnection.__init__(self, singsock, connhandler, readlinecallback)
        self.bgapp = connhandler
        self.videoHTTPServer = videoHTTPServer
        self.urlpath = None
        self.cstreaminfo = {}
        self.shutteddown = False
        self.supportedvodevents = [VODEVENT_START, VODEVENT_PAUSE, VODEVENT_RESUME]
        self.ready = False
        self.api_version = self.bgapp.default_api_version
        self.last_message_id = 0
        self.last_message_text = ''
        self.reported_events = {}

    def set_streaminfo(self, streaminfo, count_read_bytes = False):
        self.cstreaminfo.update(streaminfo)
        stream = streaminfo['stream']
        self.cstreaminfo['stream'] = ControlledStream(stream, count_read_bytes)

    def restart_playback(self, position = 0, is_live = False):
        url = self.get_video_url()
        if not url:
            return False
        if self.api_version < 2:
            cmd = 'PLAY ' + url
            if position != 0:
                cmd += ' pos=' + str(position)
        elif self.api_version < 4:
            cmd = 'START ' + url
            if is_live:
                cmd += ' stream=1'
            if position != 0:
                cmd += ' pos=' + str(position)
        else:
            params = {'url': self.get_video_url()}
            if is_live:
                params['stream'] = '1'
            if position != 0:
                params['pos'] = str(position)
            params_string = self.bgapp.make_cmd_params(params)
            cmd = 'START ' + params_string
        if DEBUG:
            log('bg::restart_playback: send cmd:', cmd)
        cmd += '\r\n'
        self.write(cmd)
        return True

    def start_playback(self, infohash, is_ad, is_interruptable_ad = False, position = 0, is_live = False, extension = None, click_url = None):
        self.urlpath = URLPATH_CONTENT_PREFIX + '/' + infohash2urlpath(infohash) + '/' + str(random.random())
        if extension is not None:
            self.urlpath += '.' + extension
        streaminfo = copy.copy(self.cstreaminfo)
        self.videoHTTPServer.set_inputstream(streaminfo, self.urlpath)
        if DEBUG:
            log('bg::start_playback: telling plugin to start playback: is_ad', is_ad, 'is_interruptable_ad', is_interruptable_ad, 'is_live', is_live, 'url', self.get_video_url())
        if self.api_version < 2:
            if is_ad:
                cmd = 'PLAYADI' if is_interruptable_ad else 'PLAYAD'
            else:
                cmd = 'PLAY'
            cmd += ' ' + self.get_video_url()
            if position != 0:
                cmd += ' pos=' + str(position)
        elif self.api_version < 4:
            cmd = 'START ' + self.get_video_url()
            if is_ad:
                cmd += ' ad=1'
                if is_interruptable_ad:
                    cmd += ' interruptable=1'
            elif is_live:
                cmd += ' stream=1'
            if position != 0:
                cmd += ' pos=' + str(position)
        else:
            params = {'url': self.get_video_url()}
            if is_ad:
                params['ad'] = '1'
                if is_interruptable_ad:
                    params['interruptable'] = '1'
            if is_live:
                params['stream'] = '1'
            if position != 0:
                params['pos'] = str(position)
            if click_url:
                params['clickurl'] = click_url
            params_string = self.bgapp.make_cmd_params(params)
            cmd = 'START ' + params_string
        if DEBUG:
            log('bg::start_playback: send cmd:', cmd)
        cmd += '\r\n'
        self.write(cmd)

    def cleanup_playback(self):
        if DEBUG:
            log('bg::cleanup_playback')
        if len(self.cstreaminfo) != 0:
            if DEBUG2:
                log('bg::cleanup_playback: close stream, cstreaminfo', self.cstreaminfo)
            self.cstreaminfo['stream'].close()
            try:
                urlpath_copy = self.urlpath
                http_del_inputstream_lambda = lambda : self.videoHTTPServer.del_inputstream(urlpath_copy)
                if DEBUG2:
                    log('bg::cleanup_playback: schedule input stream deletion: url', urlpath_copy)
                self.bgapp.tqueue.add_task(http_del_inputstream_lambda)
            except:
                log_exc()

    def get_video_url(self):
        if self.urlpath is None:
            log('bg::get_video_url: urlpath is None')
            return ''
        ip = self.singsock.get_myip()
        return 'http://' + str(ip) + ':' + str(self.videoHTTPServer.get_port()) + self.urlpath

    def pause(self):
        self.write('PAUSE\r\n')

    def resume(self):
        self.write('RESUME\r\n')

    def info(self, message_text, message_id = 0, force = False):
        if DEBUG2:
            log('bg:ic:info: message_id', message_id, 'message_text', message_text)
        if force or message_id != self.last_message_id or message_text != self.last_message_text:
            self.last_message_id = message_id
            self.last_message_text = message_text
            self.write('INFO ' + str(message_id) + ';' + message_text + '\r\n')

    def status(self, main_status, ad_status = None):

        def get_status_message(status):
            status_string = ''
            if status['status'] == 'idle':
                status_string += ''
            elif status['status'] == 'err':
                status_string += 'Error: ' + status['error_message']
            elif status['status'] == 'check':
                status_string += 'Checking already downloaded parts ' + str(status['progress']) + '%'
            elif status['status'] == 'prebuf':
                if status['peers'] == 1:
                    status_string += 'Prebuffering ' + str(status['progress']) + '% (connected to 1 stream)'
                else:
                    status_string += 'Prebuffering ' + str(status['progress']) + '% (connected to ' + str(status['peers']) + ' streams)'
            elif status['status'] == 'buf':
                status_string += 'Buffering ' + str(status['progress']) + '%'
            elif status['status'] == 'wait':
                status_string += 'Waiting sufficient download speed'
            elif status['status'] == 'dl':
                status_string += ''
            return status_string

        def get_status_string(status):
            status_string = ''
            if status['status'] == 'idle':
                status_string += 'idle'
            elif status['status'] == 'err':
                status_string += 'err;' + str(status['error_id']) + ';' + status['error_message']
            elif status['status'] == 'check':
                status_string += 'check;' + str(status['progress'])
            elif status['status'] == 'prebuf':
                status_string += 'prebuf;' + str(status['progress']) + ';' + str(status['time'])
            elif status['status'] == 'buf':
                status_string += 'buf;' + str(status['progress']) + ';' + str(status['time'])
            elif status['status'] == 'wait':
                status_string += 'wait;' + str(status['time'])
            elif status['status'] == 'dl':
                status_string += 'dl'
            elif status['status'] == 'loading':
                status_string += 'loading'
            elif status['status'] == 'starting':
                status_string += 'starting'
            else:
                raise ValueError, 'Unknown status: ' + status['status']
            if status['status'] not in ('idle', 'err', 'check', 'loading', 'starting'):
                for param in ['total_progress',
                 'immediate_progress',
                 'speed_down',
                 'http_speed_down',
                 'speed_up',
                 'peers',
                 'http_peers',
                 'downloaded',
                 'http_downloaded',
                 'uploaded']:
                    status_string += ';' + str(status[param])

                if 'live_data' in status:
                    status_string += ';' + json.dumps(status['live_data'])
            return status_string

        status_string = 'main:' + get_status_string(main_status)
        if ad_status is not None:
            status_string += '|ad:' + get_status_string(ad_status)
        if DEBUG_IC_STATUS:
            log('bg::ic:status: main_status', main_status, 'ad_status', ad_status, 'status_string', status_string)
        self.write('STATUS ' + status_string + '\r\n')

    def error(self, errstr):
        raise Exception, 'error() deprecated'

    def auth(self, authlevel):
        if not self.ready:
            if DEBUG:
                log('bg::auth: not ready')
            return
        if DEBUG:
            log('send AUTH', authlevel)
        self.write('AUTH ' + str(authlevel) + '\r\n')

    def hello(self):
        if DEBUG:
            log('send HELLO')
        self.write('HELLOTS version=' + VERSION + '\r\n')

    def state(self, state):
        if DEBUG:
            log('send STATE', state)
        self.write('STATE ' + str(state) + '\r\n')

    def event(self, name, params = {}):
        if DEBUG_EVENTS:
            log('ic:event: name', name, 'params', params)
        params_string = self.bgapp.make_cmd_params(params)
        cmd = 'EVENT ' + name
        if len(params_string):
            cmd += ' ' + params_string
        self.write(cmd + '\r\n')

    def send_response(self, response, mark_as_retval = True):
        if mark_as_retval:
            response = '##' + response
        if DEBUG:
            log('BGInstanceConnection::send_response: ', response)
        self.write(response + '\r\n')

    def send_load_response(self, request_id, response):
        if DEBUG:
            log('ic::send_load_response: request_id', request_id, 'response', response)
        self.write('LOADRESP ' + str(request_id) + ' ' + response + '\r\n')

    def searchurl(self, searchurl):
        log('SENDING SEARCHURL 2 PLUGIN')
        self.write('SEARCHURL ' + searchurl + '\r\n')

    def close(self):
        InstanceConnection.close(self)

    def stop(self):
        self.write('STOP\r\n')

    def shutdown(self, shutdownplugin = True):
        if DEBUG:
            log('bg: Shutting down: shutdownplugin', shutdownplugin)
        if not self.shutteddown:
            self.shutteddown = True
            self.cleanup_playback()
            if shutdownplugin:
                try:
                    self.write('SHUTDOWN\r\n')
                    self.close()
                except:
                    log_exc()

class BGInstanceConnection2:
    def __init__(self, connhandler, videoHTTPServer):
        self.bgapp = connhandler
        self.videoHTTPServer = videoHTTPServer
        self.urlpath = None
        self.cstreaminfo = {}
        self.shutteddown = False
        self.supportedvodevents = [VODEVENT_START, VODEVENT_PAUSE, VODEVENT_RESUME]
        self.ready = False
        self.last_message_id = 0
        self.last_message_text = ''
        self.reported_events = {}
        self.videoHTTPServer.url_is_set = 0
        self.videoHTTPServer.ic = self


    def set_streaminfo(self, streaminfo, count_read_bytes = False):
        self.cstreaminfo.update(streaminfo)
        stream = streaminfo['stream']
        self.cstreaminfo['stream'] = ControlledStream(stream, count_read_bytes)

    def start_playback(self, infohash, is_ad, is_interruptable_ad = False, position = 0, is_live = False, extension = None, click_url = None):
        self.urlpath = URLPATH_CONTENT_PREFIX + '/' + infohash2urlpath(infohash) + '/' + str(random.random())
        if extension is not None:
            self.urlpath += '.' + extension
        streaminfo = copy.copy(self.cstreaminfo)
        self.videoHTTPServer.set_inputstream(streaminfo, self.urlpath)

    def cleanup_playback(self):
        if DEBUG:
            log('bg::cleanup_playback')
        if len(self.cstreaminfo) != 0:
            if DEBUG2:
                log('bg::cleanup_playback: close stream, cstreaminfo', self.cstreaminfo)
            self.cstreaminfo['stream'].close()
            try:
                urlpath_copy = self.urlpath
                http_del_inputstream_lambda = lambda : self.videoHTTPServer.del_inputstream(urlpath_copy)
                if DEBUG2:
                    log('bg::cleanup_playback: schedule input stream deletion: url', urlpath_copy)
                self.bgapp.tqueue.add_task(http_del_inputstream_lambda)
            except:
                log_exc()

    def pause(self):
      return

    def resume(self):
      return

    def info(self, message_text, message_id = 0, force = False):
        if DEBUG2:
            log('bg:ic:info: message_id', message_id, 'message_text', message_text)
        if force or message_id != self.last_message_id or message_text != self.last_message_text:
            self.last_message_id = message_id
            self.last_message_text = message_text

    def status(self, main_status, ad_status = None):
        return

    def error(self, errstr):
        raise Exception, 'error() deprecated'

    def auth(self, authlevel):
      return


    def hello(self):
      return

    def state(self, state):
        if DEBUG:
            log('STATE', state)

    def event(self, name, params = {}):
        if DEBUG_EVENTS:
            log('ic:event: name', name, 'params', params)

    def send_response(self, response, mark_as_retval = True):
        if mark_as_retval:
            response = '##' + response
        if DEBUG:
            log('BGInstanceConnection::send_response: ', response)

    def send_load_response(self, request_id, response):
        if DEBUG:
            log('ic::send_load_response: request_id', request_id, 'response', response)

    def searchurl(self, searchurl):
        log('SENDING SEARCHURL 2 PLUGIN')

    def close(self):
        self = None
        
    def stop(self):
      if DEBUG:
	log("ic::got command stop")
      self.bgapp.gui_connection_lost(self, switchp2ptarget=True)

    def shutdown(self, shutdownplugin = True):
        if DEBUG:
            log('bg: Shutting down: shutdownplugin', shutdownplugin)
        if not self.shutteddown:
            self.shutteddown = True
            self.cleanup_playback()
            if shutdownplugin:
                try:
                    self.close()
                except:
                    log_exc()


class ControlledStream():

    def __init__(self, stream, count_read_bytes = False):
        self.stream = stream
        self.done = False
        self.count_read_bytes = count_read_bytes
        self.read_bytes = 0

    def read(self, nbytes = None):
        if not self.done:
            if self.count_read_bytes:
                data = self.stream.read(nbytes)
                if data:
                    self.read_bytes += len(data)
                return data
            data = self.stream.read(nbytes)
            return data
        else:
            return ''

    def seek(self, pos, whence = os.SEEK_SET):
        self.stream.seek(pos, whence)

    def close(self, close_underlying_stream = True):
        self.done = True
        if DEBUG2:
            log('ControlledStream::close: close_underlying_stream', close_underlying_stream)
        if close_underlying_stream:
            try:
                self.stream.close()
            except:
                if DEBUG:
                    print_exc()


class AtBitrateStream():
    SAFE_MARGIN_TIME = 10.0
    BITRATE_SPEED_INCREMENT = 1.05
    STREAM_STATE_TRANSITION = 0
    STREAM_STATE_PREBUFFER = 1
    STREAM_STATE_PLAYING = 2

    def __init__(self, stream, bitrate):
        self.stream = stream
        self.done = False
        self.bitrate = bitrate
        self.safe_bytes = self.SAFE_MARGIN_TIME * bitrate
        self.stream_state = self.STREAM_STATE_TRANSITION
        self.last_time = 0.0
        self.playback = 0.0
        self.given_bytes_till = 0

    def has_to_sleep(self, nbytes):
        curr_time = time.time()
        if self.stream_state is self.STREAM_STATE_TRANSITION:
            self.last_time = curr_time
            elapsed_time = 0.0
            self.stream_state = self.STREAM_STATE_PREBUFFER
        else:
            elapsed_time = curr_time - self.last_time
            self.last_time = curr_time
        self.playback += elapsed_time * self.BITRATE_SPEED_INCREMENT
        if self.stream_state is self.STREAM_STATE_PREBUFFER:
            played_bytes = self.playback * self.bitrate
            if played_bytes + self.safe_bytes <= self.given_bytes_till:
                self.stream_state = self.STREAM_STATE_PLAYING
            self.given_bytes_till += nbytes
            return 0.0
        else:
            delta_time = self.given_bytes_till / float(self.bitrate) - (self.playback + self.SAFE_MARGIN_TIME)
            if delta_time <= 0.0:
                self.stream_state = self.STREAM_STATE_PREBUFFER
            self.given_bytes_till += nbytes
            return max(0.0, delta_time)

    def read(self, nbytes = None):
        if not self.done:
            to_give = self.stream.read(nbytes)
            sleep_time = self.has_to_sleep(nbytes)
            if sleep_time > 0.0:
                time.sleep(sleep_time)
            return to_give
        else:
            return ''

    def seek(self, pos, whence = os.SEEK_SET):
        self.stream.seek(pos, whence)
        self.stream_state = self.STREAM_STATE_TRANSITION
        self.given_bytes_till = pos
        self.playback = pos / float(self.bitrate)

    def close(self):
        self.done = True


def run_bgapp(wrapper, appname, appversion, params = None):
    encoding_list = ['cp1251',
     'utf-8',
     'koi8-r',
     'koi8-u',
     'idna']
    for enc in encoding_list:
        encodings.search_function(enc)

    if params is None:
        params = ['']
    if len(sys.argv) > 1:
        params = sys.argv[1:]
    installdir = os.path.abspath(os.path.dirname(sys.argv[0]))
    app = BackgroundApp(wrapper, 0, appname, appversion, params, installdir)
    s = app.s
    if DEBUG_TIME:
        print >> sys.stderr, '>>>time: BackgroundApp created', time.clock()
    return app


def stop_bgapp(app):
    log('Sleeping seconds to let other threads finish')
    time.sleep(2)
    os._exit(0)
