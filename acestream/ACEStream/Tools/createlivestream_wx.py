#Embedded file name: ACEStream\Tools\createlivestream_wx.pyo
import sys
import os
try:
    import wxversion
    wxversion.select('2.8')
except:
    pass

try:
    import wx
except:
    print >> sys.stderr, 'wx is not installed'
    os._exit(1)

import shutil
import time
import tempfile
import urllib2
import binascii
import subprocess
from traceback import print_exc
from threading import Thread
from base64 import encodestring
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import ACEStream.Debug.console
from ACEStream.GlobalConfig import globalConfig
from ACEStream.Core.API import *
from ACEStream.Video.Ogg import ogg_grab_page, is_ogg
import ACEStream.Core.BitTornado.parseargs as parseargs
from ACEStream.Core.Utilities.timeouturlopen import urlOpenTimeout
from ACEStream.Core.BitTornado.CurrentRateMeasure import Measure
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Core.TS.Service import TSService
from ACEStream.Core.Video import VideoSource
DEBUG = False
argsdef = [('name', '', 'name of the stream'),
 ('source', '-', 'source to stream (url, file or "-" to indicate stdin)'),
 ('destdir', '', 'dir to save torrent (and stream)'),
 ('bitrate', 512, 'bitrate of the stream in kbit/s'),
 ('piecesize', 'auto', 'transport piece size'),
 ('duration', '1:00:00', 'duration of the stream in hh:mm:ss format'),
 ('host', '', 'the hostname or ip address of internal tracker'),
 ('port', 7764, 'the TCP+UDP listen port'),
 ('trackers', '', 'comma separated list of additional trackers'),
 ('provider-key', '', 'provider key'),
 ('maxclients', 7, 'the max number of peers to serve directly'),
 ('mode', '', ''),
 ('debug', 0, '')]

def get_usage(defs):
    return parseargs.formatDefinitions(defs, 80)


class AppWrapper(wx.App):

    def __init__(self, redirectstderrout = False):
        self.bgapp = None
        self.systray = None
        wx.App.__init__(self, redirectstderrout)

    def OnExit(self):
        if self.systray is not None:
            self.systray.RemoveIcon()
            self.systray.Destroy()
        if self.bgapp is not None:
            self.bgapp.OnExit()

    def set_bgapp(self, bgapp):
        self.bgapp = bgapp

    def set_icon(self, iconpath):
        self.systray = StreamTaskBarIcon(self, self.bgapp, iconpath)

    def set_icon_tooltip(self, txt):
        if self.systray is not None:
            self.systray.set_icon_tooltip(txt)


class StreamTaskBarIcon(wx.TaskBarIcon):

    def __init__(self, wxapp, bgapp, iconfilename):
        wx.TaskBarIcon.__init__(self)
        self.bgapp = bgapp
        self.wxapp = wxapp
        self.icons = wx.IconBundle()
        self.icon = wx.Icon(iconfilename, wx.BITMAP_TYPE_ICO)
        self.icons.AddIcon(self.icon)
        if sys.platform != 'darwin':
            self.SetIcon(self.icon, self.bgapp.appname)
        else:
            menuBar = wx.MenuBar()
            filemenu = wx.Menu()
            item = filemenu.Append(-1, 'E&xit', 'Terminate the program')
            self.Bind(wx.EVT_MENU, self.OnExit, item)
            wx.App.SetMacExitMenuItemId(item.GetId())

    def OnExit(self, e):
        self.wxapp.ExitMainLoop()

    def CreatePopupMenu(self):
        menu = wx.Menu()
        mi = menu.Append(wx.ID_ANY, 'Exit')
        self.Bind(wx.EVT_MENU, self.OnExitClient, id=mi.GetId())
        return menu

    def OnExitClient(self, event = None):
        self.wxapp.ExitMainLoop()

    def set_icon_tooltip(self, txt):
        if sys.platform == 'darwin':
            return
        self.SetIcon(self.icon, txt)


class WebUIServer(HTTPServer):

    def __init__(self, port, app):
        self.port = port
        self.app = app
        HTTPServer.__init__(self, ('', self.port), WebUIHandler)

    def background_serve(self):
        name = 'WebUIServerThread'
        t = Thread(target=self.serve_forever, name=name)
        t.setDaemon(True)
        t.start()

    def shutdown(self):
        self.socket.close()


class WebUIHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        try:
            if self.path == '/':
                stream_info = self.server.app.get_stream_info()
                response = '<!DOCTYPE html>'
                response += '<html><head>'
                response += '<meta http-equiv="refresh" content="5">'
                response += '<title>Stream Info</title>'
                response += '</head><body>'
                if stream_info is None:
                    response += 'No stream'
                else:
                    player_id = self.server.app.player_id
                    if player_id is None:
                        player_id = ''
                    response += 'Name: ' + stream_info['name'] + '<br/>'
                    response += 'Tracker: ' + stream_info['tracker_url'] + '<br/>'
                    response += 'Bitrate: ' + str(stream_info['bitrate']) + ' kbit/s<br/>'
                    response += 'Source download speed: %.1f<br/>' % (stream_info['speed_source'] / 1024.0)
                    response += 'Peers: ' + str(stream_info['peers']) + '<br/>'
                    response += 'Upload speed: %.1f<br/>' % stream_info['speed_up']
                    response += 'File: <a href="/get/' + stream_info['infohash'] + '">download</a><br/>'
                    response += 'Content ID: %s<br/>' % player_id
                    if len(player_id):
                        response += '<a href="http://torrentstream.org/stream/test.php?id=' + player_id + '" target=_blank"">Watch online</a><br/>'
                response += '</body></html>'
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(response)
            elif self.path.startswith('/get/'):
                infohash = self.path[5:]
                path = self.server.app.get_torrent_path(infohash)
                log('webui::get: get torrent: infohash', infohash, 'path', path)
                f = open(path, 'rb')
                data = f.read()
                f.close()
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Disposition', 'attachment; filename=' + os.path.basename(path))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404, 'Not found: %s' % self.path)
        except Exception as e:
            self.send_error(503, str(e))


class InfiniteHTTPStream():

    def __init__(self, url, reader = 'builtin'):
        self.url = url
        self.reader = reader
        self.reopen()

    def read(self, nbytes = None):
        got = False
        while not got:
            try:
                ret = self.stream.read(nbytes)
                if len(ret) == 0:
                    raise ValueError('EOF')
                else:
                    got = True
            except:
                if DEBUG:
                    print_exc()
                print >> sys.stderr, 'createlivestream: Reconnecting on EOF input stream'
                self.reopen()

        return ret

    def close(self):
        self.stream.close()

    def reopen(self):
        while True:
            try:
                print >> sys.stderr, 'createlivestream: open stream: url', self.url, 'reader', self.reader
                if self.reader == 'urllib2':
                    self.stream = urllib2.urlopen(self.url)
                else:
                    self.stream = urlOpenTimeout(self.url)
                break
            except KeyboardInterrupt:
                raise
            except:
                if DEBUG:
                    print_exc()
                retry_in = 5
                print >> sys.stderr, 'createlivestream: failed to open url', self.url, 'retrying in', retry_in, 'seconds'
                time.sleep(retry_in)


class HaltOnEOFStream():

    def __init__(self, stream):
        self.stream = stream
        self.ratemeasure = Measure(30)

    def read(self, nbytes = None):
        ret = self.stream.read(nbytes)
        if len(ret) == 0:
            print >> sys.stderr, 'createlivestream: Exiting on EOF input stream'
            os._exit(1)
        self.ratemeasure.update_rate(len(ret))
        return ret

    def close(self):
        self.stream.close()


class FileLoopStream():

    def __init__(self, stream):
        self.stream = stream

    def read(self, nbytes = None):
        data = self.stream.read(nbytes)
        if len(data) == 0:
            self.stream.seek(0)
            data = self.stream.read(nbytes)
        return data

    def close(self):
        self.stream.close()


class StreamApp():

    def __init__(self, appname, installdir):
        self.appname = appname
        self.installdir = installdir
        self.wrapper = None
        self.config = None
        self.s = None
        self.statedir = None
        self.source = None
        self.child_processes = []
        self.stats = {}
        self.download = None
        self.player_id = None
        self.tsservice = TSService(self)

    def set_wrapper(self, wrapper):
        self.wrapper = wrapper

    def state_callback(self, ds):
        d = ds.get_download()
        if DEBUG:
            print >> sys.stderr, `(d.get_def().get_name())`, dlstatus_strings[ds.get_status()], '%3.1f %%' % ds.get_progress(), ds.get_error(), 'up %.1f down %.1f' % (ds.get_current_speed(UPLOAD), ds.get_current_speed(DOWNLOAD))
        self.stats['speed_source'] = self.source.ratemeasure.get_rate_noupdate()
        self.stats['peers'] = ds.get_num_peers()
        self.stats['speed_up'] = ds.get_current_speed(UPLOAD)
        if self.wrapper is not None:
            status_string = 'Source: %.1f\nPeers: %d\nUP: %.1f' % (self.stats['speed_source'] / 1024.0, self.stats['peers'], self.stats['speed_up'])
            self.wrapper.set_icon_tooltip(status_string)
        return (1.0, False)

    def get_piece_size(self, bitrate):
        mid = bitrate / 2
        piece_size = 32768
        while piece_size < mid:
            piece_size *= 2

        return piece_size

    def get_vlc_path(self):
        vlc_path = os.path.join(self.installdir, '..', 'player', 'tsplayer.exe')
        if not os.path.isfile(vlc_path):
            raise Exception, 'Cannot find vlc:', vlc_path
        return vlc_path

    def init_source(self, source_id, tdef, dcfg):
        if source_id == '-':
            source = sys.stdin
        elif source_id.startswith('http:'):
            source = InfiniteHTTPStream(source_id)
        elif source_id.startswith('pipe:'):
            cmd = source_id[len('pipe:'):]
            child_out, source = os.popen2(cmd, 'b')
        elif source_id.startswith('vlcfile:'):
            source_id = source_id[len('vlcfile:'):]
            a = source_id.split('#')
            if len(a) != 2:
                raise ValueError, 'Bad source format'
            path = a[0]
            transcode_options = a[1]
            if DEBUG:
                print >> sys.stderr, 'init_source: vlcfile: path', path, 'transcode_options', transcode_options
            vlc_path = self.get_vlc_path()
            vlc_args = [vlc_path,
             '-I',
             'none',
             '--sout',
             '#transcode{' + transcode_options + '}:http{mux=ts,dst=:9090}',
             '--sout-keep',
             path]
            print >> sys.stderr, 'init_source: start vlc: vlc_args', vlc_args
            vlc_process = subprocess.Popen(vlc_args, close_fds=True)
            self.child_processes.append(vlc_process)
            source = InfiniteHTTPStream('http://localhost:9090')
        elif source_id.startswith('vlcdshow:'):
            source_id = source_id[len('vlcdshow:'):]
            a = source_id.split('#')
            if len(a) != 4:
                raise ValueError, 'Bad source format'
            video_device_name = a[0]
            audio_device_name = a[1]
            video_size = a[2]
            transcode_options = a[3]
            if DEBUG:
                print >> sys.stderr, 'init_source: vlcdshow: video_device_name', video_device_name, 'audio_device_name', audio_device_name, 'video_size', video_size, 'transcode_options', transcode_options
            vlc_path = self.get_vlc_path()
            vlc_args = [vlc_path,
             '-I',
             'none',
             'dshow://',
             'vdev="' + video_device_name + '"',
             'adev="' + audio_device_name + '"',
             'size="' + video_size + '"',
             '--sout',
             '#transcode{' + transcode_options + '}:http{mux=ts,dst=:9090}',
             '--sout-keep']
            print >> sys.stderr, 'init_source: start vlc: vlc_args', vlc_args
            vlc_process = subprocess.Popen(vlc_args, close_fds=True)
            self.child_processes.append(vlc_process)
            source = InfiniteHTTPStream('http://localhost:9090')
        else:
            try:
                stream = open(source_id, 'rb')
            except IOError:
                print >> sys.stderr, 'Cannot open file', source_id
                raise KeyboardInterrupt
            except:
                raise

            source = stream
            dcfg.set_video_ratelimit(tdef.get_bitrate())
        return source

    def send_torrent_to_server(self, tdef, developer_id = 0, affiliate_id = 0, zone_id = 0):
        t = Thread(target=self._send_torrent_to_server, args=[tdef,
         developer_id,
         affiliate_id,
         zone_id])
        t.setDaemon(True)
        t.start()

    def _send_torrent_to_server(self, tdef, developer_id = 0, affiliate_id = 0, zone_id = 0):
        if DEBUG:
            log('stream::send_torrent_to_server: infohash', binascii.hexlify(tdef.get_infohash()), 'd', developer_id, 'a', affiliate_id, 'z', zone_id)
        torrent_data = tdef.save()
        protected = tdef.get_protected()
        if protected:
            infohash = tdef.get_infohash()
        else:
            infohash = None
        self.player_id = self.tsservice.send_torrent(torrent_data, developer_id, affiliate_id, zone_id, protected, infohash)
        if DEBUG:
            log('stream::send_torrent_to_server: torrent saved: infohash', binascii.hexlify(tdef.get_infohash()), 'd', developer_id, 'a', affiliate_id, 'z', zone_id, 'player_id', self.player_id)

    def start_stream(self, config):
        t = Thread(target=self._start_stream, args=[config])
        t.setDaemon(True)
        t.start()

    def _start_stream(self, config):
        if len(config['destdir']) == 0:
            state_dir = Session.get_default_state_dir()
            config['destdir'] = os.path.join(state_dir, 'streams')
        try:
            config['destdir'] = config['destdir'].decode('utf-8')
        except:
            print_exc()

        if not os.path.isdir(config['destdir']):
            try:
                os.makedirs(config['destdir'])
            except:
                print_exc()
                return

        try:
            path = os.path.join(config['destdir'], config['name'])
            if os.path.isfile(path):
                os.remove(path)
        except:
            print_exc()

        globalConfig.set_mode('stream')
        sscfg = SessionStartupConfig()
        statedir = tempfile.mkdtemp()
        sscfg.set_state_dir(statedir)
        sscfg.set_listen_port(config['port'])
        sscfg.set_megacache(False)
        sscfg.set_overlay(False)
        sscfg.set_dialback(True)
        if config['host']:
            url = 'http://' + str(config['host']) + ':' + str(sscfg.get_listen_port()) + '/announce'
            sscfg.set_internal_tracker_url(url)
        s = Session(sscfg)
        authfilename = os.path.join(config['destdir'], config['name'] + '.sauth')
        try:
            authcfg = RSALiveSourceAuthConfig.load(authfilename)
        except:
            authcfg = RSALiveSourceAuthConfig()
            authcfg.save(authfilename)

        config['protected'] = True
        provider_key = config['provider-key'] if len(config['provider-key']) else None
        bitrate = int(config['bitrate'])
        bitrate *= 125
        tdef = TorrentDef()
        tdef.create_live(config['name'], bitrate, config['duration'], authcfg, config['protected'], provider_key)
        tdef.set_tracker(s.get_internal_tracker_url())
        if config['piecesize'] == 'auto':
            piece_size = self.get_piece_size(bitrate)
        else:
            piece_size = int(config['piecesize'])
        tdef.set_piece_length(piece_size)
        print >> sys.stderr, 'bitrate:', config['bitrate']
        print >> sys.stderr, 'piece size:', piece_size
        print >> sys.stderr, 'dest dir:', config['destdir']
        print >> sys.stderr, 'tracker url:', s.get_internal_tracker_url()
        if config['trackers']:
            trackers = [[s.get_internal_tracker_url()]]
            for t in config['trackers'].split(','):
                print >> sys.stderr, 'tracker:', t
                trackers.append([t])

            tdef.set_tracker_hierarchy(trackers)
        tdef.finalize()
        print >> sys.stderr, '-------------------'
        ext = 'acelive'
        torrentbasename = config['name'] + '.' + ext
        torrentfilename = os.path.join(config['destdir'], torrentbasename)
        config['torrentfilename'] = torrentfilename
        tdef.save(torrentfilename)
        self.send_torrent_to_server(tdef)
        dscfg = DownloadStartupConfig()
        dscfg.set_dest_dir(config['destdir'])
        source = self.init_source(config['source'], tdef, dscfg)
        self.source = HaltOnEOFStream(source)
        restartstatefilename = os.path.join(config['destdir'], config['name'] + '.restart')
        dscfg.set_video_source(self.source, authcfg, restartstatefilename=restartstatefilename)
        dscfg.set_max_uploads(config['maxclients'])
        self.s = s
        self.statedir = statedir
        self.config = config
        self.download = s.start_download(tdef, dscfg)
        self.download.set_state_callback(self.state_callback, getpeerlist=False)

    def get_stream_info(self):
        if self.download is None:
            return
        return {'name': self.config['name'],
         'bitrate': self.config['bitrate'],
         'tracker_url': self.s.get_internal_tracker_url(),
         'speed_source': self.stats.get('speed_source', 0),
         'peers': self.stats.get('peers', 0),
         'speed_up': self.stats.get('speed_up', 0),
         'infohash': binascii.hexlify(self.download.get_def().get_infohash())}

    def get_torrent_path(self, infohash):
        return self.config['torrentfilename']

    def OnExit(self):
        print >> sys.stderr, 'stopping...'
        for p in self.child_processes:
            print >> sys.stderr, 'stop child process:', p
            try:
                p.kill()
            except:
                if DEBUG:
                    print_exc()

        if self.s is not None:
            self.s.shutdown()
            time.sleep(3)
        if self.statedir is not None:
            try:
                shutil.rmtree(self.statedir)
            except:
                pass


def start(apptype, current_dir):
    try:
        config, fileargs = parseargs.parseargs(sys.argv, argsdef, presets={})
    except Exception as e:
        print >> sys.stderr, e
        os._exit(1)

    if config['name'] == '':
        print >> sys.stderr, 'Usage:  ', get_usage(argsdef)
        os._exit(0)
    debug_level = config['debug']
    ACEStream.Core.BitTornado.SocketHandler.DEBUG = debug_level & 8 != 0
    ACEStream.Core.BitTornado.BT1.Choker.DEBUG = debug_level & 8 != 0
    ACEStream.Core.BitTornado.BT1.Connecter.DEBUG = debug_level & 8 != 0
    ACEStream.Core.BitTornado.BT1.Downloader.DEBUG = debug_level & 8 != 0
    ACEStream.Core.BitTornado.BT1.Encrypter.DEBUG = debug_level & 8 != 0
    ACEStream.Core.BitTornado.BT1.Encrypter.DEBUG_CLOSE = debug_level & 8 != 0
    ACEStream.Core.BitTornado.BT1.Rerequester.DEBUG = debug_level & 8 != 0
    ACEStream.Core.BitTornado.BT1.Rerequester.DEBUG_DHT = debug_level & 8 != 0
    ACEStream.Core.BitTornado.BT1.Rerequester.DEBUG_CHECK_NETWORK_CONNECTION = debug_level & 8 != 0
    ACEStream.Core.BitTornado.BT1.track.DEBUG = debug_level & 8 != 0
    ACEStream.Core.BitTornado.BT1.StorageWrapper.DEBUG_LIVE = debug_level == -1 or debug_level & 16 != 0
    ACEStream.Core.Video.VideoSource.DEBUG = debug_level == -1 or debug_level & 16 != 0
    ACEStream.Core.NATFirewall.NatCheck.DEBUG = debug_level & 64 != 0
    ACEStream.Core.NATFirewall.UPnPThread.DEBUG = debug_level & 64 != 0
    ACEStream.Core.NATFirewall.UDPPuncture.DEBUG = debug_level & 64 != 0
    ACEStream.Core.NATFirewall.upnp.DEBUG = debug_level & 64 != 0
    ACEStream.Core.NATFirewall.ConnectionCheck.DEBUG = debug_level & 64 != 0
    ACEStream.Core.BitTornado.RawServer.DEBUG = debug_level & 512 != 0
    ACEStream.Core.BitTornado.RawServer.DEBUG2 = debug_level & 512 != 0
    ACEStream.Core.BitTornado.ServerPortHandler.DEBUG = debug_level & 512 != 0
    ACEStream.Core.BitTornado.ServerPortHandler.DEBUG2 = debug_level & 512 != 0
    ACEStream.Core.BitTornado.HTTPHandler.DEBUG = debug_level & 512 != 0
    ACEStream.Core.BitTornado.HTTPHandler.DEBUG2 = debug_level & 512 != 0
    ACEStream.Core.BitTornado.SocketHandler.DEBUG = debug_level & 512 != 0
    ACEStream.Core.BitTornado.SocketHandler.DEBUG2 = debug_level & 512 != 0
    globalConfig.set_value('apptype', apptype)
    if apptype == 'torrentstream':
        appname = 'Torrent Stream'
    else:
        appname = 'ACE Stream HD'
    app = StreamApp(appname, current_dir)
    iconpath = os.path.join(current_dir, 'data', 'images', 'stream.ico')
    wrapper = AppWrapper()
    wrapper.set_bgapp(app)
    wrapper.set_icon(iconpath)
    app.set_wrapper(wrapper)
    webui_server = WebUIServer(6879, app)
    webui_server.background_serve()
    app.start_stream(config)
    wrapper.MainLoop()
    app.OnExit()
    os._exit(0)
