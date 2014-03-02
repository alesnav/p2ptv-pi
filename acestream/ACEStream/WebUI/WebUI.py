#Embedded file name: ACEStream\WebUI\WebUI.pyo
import sys, os
import time
import random
import urllib
import urlparse
import cgi
import binascii
import copy
from cStringIO import StringIO
from traceback import print_exc, print_stack
from threading import RLock, Condition
from base64 import encodestring
try:
    import simplejson as json
except ImportError:
    import json

from ACEStream.Core.API import *
from ACEStream.Core.BitTornado.bencode import *
from ACEStream.Video.VideoServer import AbstractPathMapper
from ACEStream.Core.Utilities.logger import log, log_exc
from ACEStream.Plugin.defs import *
DEBUG = False

def streaminfo404():
    return {'statuscode': 404,
     'statusmsg': '404 Not Found'}


class WebIFPathMapper(AbstractPathMapper):
    binaryExtensions = ['.gif',
     '.png',
     '.jpg',
     '.js',
     '.css']
    contentTypes = {'.css': 'text/css',
     '.gif': 'image/gif',
     '.jpg': 'image/jpg',
     '.png': 'image/png',
     '.js': 'text/javascript',
     '.html': 'text/html'}

    def __init__(self, bgApp, session):
        self.bgApp = bgApp
        self.session = session
        self.downspeed = 0
        self.upspeed = 0
        self.lastreqtime = time.time()
        if sys.platform == 'win32':
            self.webUIPath = os.path.join(self.bgApp.installdir, 'webui')
        else:
            self.webUIPath = os.path.join(self.bgApp.installdir, 'data', 'webui')
        if DEBUG:
            log('webui: path', self.webUIPath)
        self.session.set_download_states_callback(self.speed_callback)

    def get(self, urlpath):
        try:
            return self.doget(urlpath)
        except:
            print_exc()
            return None

    def doget(self, urlpath):
        if not urlpath.startswith(URLPATH_WEBIF_PREFIX):
            return streaminfo404()
        else:
            self.lastreqtime = time.time()
            try:
                fakeurl = 'http://127.0.0.1' + urlpath[len(URLPATH_WEBIF_PREFIX):]
                if DEBUG:
                    log('webui::doget: fakeurl', fakeurl)
                request_url = urlparse.urlparse(fakeurl)
            except:
                print_exc()
                return

            path = request_url[2]
            query_string = request_url[4]
            query_params = urlparse.parse_qs(query_string)
            if DEBUG:
                log('webui::doget: urlpath', urlpath, 'request_url', request_url, 'path', path, 'query_params', query_params)
            if len(path) == 0:
                if DEBUG:
                    log('webui::doget: show status page')
                page = self.statusPage()
                pageStream = StringIO(page)
                return {'statuscode': 200,
                 'mimetype': 'text/html',
                 'stream': pageStream,
                 'length': len(page)}
            if path == 'permid.js':
                try:
                    permid = encodestring(self.bgApp.s.get_permid()).replace('\n', '')
                    txt = "var permid = '%s';" % permid
                    dataStream = StringIO(txt)
                except:
                    print_exc()
                    return {'statuscode': 500,
                     'statusmsg': 'Bad permid'}

                return {'statuscode': 200,
                 'mimetype': 'text/javascript',
                 'stream': dataStream,
                 'length': len(txt)}
            if path == '/createstream':
                if DEBUG:
                    log('webui::doget: show create stream page')
                page = self.createStreamPage()
                pageStream = StringIO(page)
                return {'statuscode': 200,
                 'mimetype': 'text/html',
                 'stream': pageStream,
                 'length': len(page)}
            if path == '/dispatch':
                if 'url' not in query_params:
                    if DEBUG:
                        log('webui::doget:dispatch: missing url')
                    return streaminfo404()
                url = query_params['url'][0]
                redirect_url = 'http://127.0.0.1:6878/webui/' + url
                params = []
                for name, val in query_params.iteritems():
                    if name != 'url':
                        params.append(urllib.quote_plus(name) + '=' + urllib.quote_plus(val[0]))

                if len(params):
                    redirect_url += '?' + '&'.join(params)
                if DEBUG:
                    log('webui::doget:dispatch: redirect_url', redirect_url)
                page = '<!DOCTYPE html><html><head><script type="text/javascript">'
                page += 'parent.location.href = "' + redirect_url + '";'
                page += '</script></head><body></body></html>'
                pageStream = StringIO(page)
                return {'statuscode': 200,
                 'mimetype': 'text/html',
                 'stream': pageStream,
                 'length': len(page)}
            if path.startswith('/player/') and query_params.has_key('a') and query_params['a'][0] == 'check':
                player_id = path.split('/')[2]
                redirect_url = 'http://127.0.0.1:6878/webui/player/' + player_id
                params = []
                for name, val in query_params.iteritems():
                    if name != 'a':
                        params.append(urllib.quote_plus(name) + '=' + urllib.quote_plus(val[0]))

                if len(params):
                    redirect_url += '?' + '&'.join(params)
                if DEBUG:
                    log('webui::doget:dispatch: redirect_url', redirect_url)
                page = '<!DOCTYPE html><html><head><script type="text/javascript">'
                page += 'parent.location.href = "' + redirect_url + '";'
                page += '</script></head><body></body></html>'
                pageStream = StringIO(page)
                return {'statuscode': 200,
                 'mimetype': 'text/html',
                 'stream': pageStream,
                 'length': len(page)}
            if path.startswith('/player/'):
                player_id = path.split('/')[2]
                if DEBUG:
                    log('webui::doget: show player page: id', player_id)
                params = {}
                for name, val in query_params.iteritems():
                    params[name] = val[0]

                page = self.playerPage(player_id, params)
                pageStream = StringIO(page)
                return {'statuscode': 200,
                 'mimetype': 'text/html',
                 'stream': pageStream,
                 'length': len(page)}
            static_path = None
            json_query = None
            if path.startswith('/json/'):
                json_query = request_url[4]
            else:
                static_path = os.path.join(self.webUIPath, path[1:])
            if DEBUG:
                log('webui::doget: request parsed: static_path', static_path, 'json_query', json_query)
            if static_path is not None:
                if not os.path.isfile(static_path):
                    if DEBUG:
                        log('webui::doget: file not found:', static_path)
                    return streaminfo404()
                extension = os.path.splitext(static_path)[1]
                if extension in self.binaryExtensions:
                    mode = 'rb'
                else:
                    mode = 'r'
                fp = open(static_path, mode)
                data = fp.read()
                fp.close()
                dataStream = StringIO(data)
                return {'statuscode': 200,
                 'mimetype': self.getContentType(extension),
                 'stream': dataStream,
                 'length': len(data)}
            if json_query is not None:
                params = {}
                for s in json_query.split('&'):
                    name, value = s.split('=')
                    params[name] = value

                if DEBUG:
                    log('webui:doget: got json request:', json_query, 'params', params)
                if 'q' not in params:
                    return
                try:
                    req = urllib.unquote(params['q'])
                    if DEBUG:
                        log('webui::doget: parse json: req', req)
                    jreq = json.loads(req)
                    if DEBUG:
                        log('webui::doget: parse json done: jreq', jreq)
                except:
                    print_exc()
                    return

                try:
                    method = jreq['method']
                except:
                    return {'statuscode': 504,
                     'statusmsg': 'Json request in wrong format! At least a method has to be specified!'}

                try:
                    args = jreq['arguments']
                    if DEBUG:
                        print >> sys.stderr, 'webUI: Got JSON request: ', jreq, '; method: ', method, '; arguments: ', args
                except:
                    args = None
                    if DEBUG:
                        print >> sys.stderr, 'webUI: Got JSON request: ', jreq, '; method: ', method

                if args is None:
                    data = self.process_json_request(method)
                    if DEBUG:
                        print >> sys.stderr, 'WebUI: response to JSON ', method, ' request: ', data
                else:
                    data = self.process_json_request(method, args)
                    if DEBUG:
                        print >> sys.stderr, 'WebUI: response to JSON ', method, ' request: ', data, ' arguments: ', args
                if data == 'Args missing':
                    return {'statuscode': 504,
                     'statusmsg': 'Json request in wrong format! Arguments have to be specified!'}
                dataStream = StringIO(data)
                return {'statuscode': 200,
                 'mimetype': 'application/json',
                 'stream': dataStream,
                 'length': len(data)}
            if DEBUG:
                log('webui::doget: unknow request format: request_url', request_url)
            return streaminfo404()

    def process_json_request(self, method, args = None):
        try:
            return self.doprocess_json_request(method, args=args)
        except:
            print_exc()
            return json.JSONEncoder().encode({'success': 'false'})

    def doprocess_json_request(self, method, args = None):
        if args is not None and args.has_key('id'):
            infohash = urllib.unquote(str(args['id']))
        else:
            infohash = None
        if DEBUG:
            print >> sys.stderr, 'WebUI: received JSON request for method: ', method
        if method == 'get_all_downloads':
            condition = Condition()
            dlist = []
            states_func = lambda dslist: self.states_callback(dslist, condition, dlist)
            self.session.set_download_states_callback(states_func)
            condition.acquire()
            condition.wait(5.0)
            condition.release()
            return json.JSONEncoder().encode({'downloads': dlist})
        if method == 'pause_all':
            try:
                func = lambda : self.bgApp.gui_webui_stop_all_downloads(self.session.get_downloads())
                self.bgApp.run_delayed(func)
                return json.JSONEncoder().encode({'success': 'true'})
            except:
                return json.JSONEncoder().encode({'success': 'false'})

        elif method == 'resume_all':
            try:
                func = lambda : self.bgApp.gui_webui_restart_all_downloads(self.session.get_downloads())
                self.bgApp.run_delayed(func)
                return json.JSONEncoder().encode({'success': 'true'})
            except:
                return json.JSONEncoder().encode({'success': 'false'})

        elif method == 'remove_all':
            try:
                func = lambda : self.bgApp.gui_webui_remove_all_downloads(self.session.get_downloads())
                self.bgApp.run_delayed(func)
                return json.JSONEncoder().encode({'success': 'true'})
            except:
                return json.JSONEncoder().encode({'success': 'false'})

        else:
            if method == 'get_speed_info':
                return json.JSONEncoder().encode({'success': 'true',
                 'downspeed': self.downspeed,
                 'upspeed': self.upspeed})
            if args is None:
                return 'Args missing'
            if method == 'pause_dl':
                try:
                    downloads = self.session.get_downloads()
                    for dl in downloads:
                        if dl.get_def().get_infohash() == infohash:
                            func = lambda : self.bgApp.gui_webui_stop_download(dl)
                            self.bgApp.run_delayed(func)

                    return json.JSONEncoder().encode({'success': 'true'})
                except:
                    return json.JSONEncoder().encode({'success': 'false'})

            elif method == 'resume_dl':
                try:
                    downloads = self.session.get_downloads()
                    for dl in downloads:
                        if dl.get_def().get_infohash() == infohash:
                            func = lambda : self.bgApp.gui_webui_restart_download(dl)
                            self.bgApp.run_delayed(func)

                    return json.JSONEncoder().encode({'success': 'true'})
                except:
                    return json.JSONEncoder().encode({'success': 'false'})

            elif method == 'remove_dl':
                try:
                    downloads = self.session.get_downloads()
                    for dl in downloads:
                        if dl.get_def().get_infohash() == infohash:
                            func = lambda : self.bgApp.gui_webui_remove_download(dl)
                            self.bgApp.run_delayed(func)

                    return json.JSONEncoder().encode({'success': 'true'})
                except:
                    return json.JSONEncoder().encode({'success': 'false'})

            elif method == 'save_dl':
                try:
                    if args is not None:
                        path = urllib.unquote(str(args['path']))
                    else:
                        raise Exception, 'Missing path in request'
                    downloads = self.session.get_downloads()
                    for dl in downloads:
                        if dl.get_type() == DLTYPE_TORRENT and dl.get_def().get_infohash() == infohash:
                            func = lambda : self.bgApp.gui_webui_save_download(dl, path)
                            self.bgApp.run_delayed(func)

                    return json.JSONEncoder().encode({'success': 'true'})
                except:
                    return json.JSONEncoder().encode({'success': 'false'})

            elif method == 'create_stream':
                if DEBUG:
                    log('webui: createstream: args', args)
                try:
                    self.bgApp.gui_webui_create_stream(args)
                    return json.JSONEncoder().encode({'success': 'true'})
                except Exception as e:
                    if DEBUG:
                        print_exc()
                    return json.JSONEncoder().encode({'success': 'false',
                     'error': str(e)})

            else:
                raise Exception, 'Unknown method ' + method

    def states_callback(self, dslist, condition, dlist):
        for ds in dslist:
            d = ds.get_download()
            infohash = urllib.quote(d.get_hash())
            dl = {'id': infohash,
             'name': d.get_def().get_name(),
             'status': dlstatus_strings[ds.get_status()],
             'progress': ds.get_progress(),
             'upload': ds.get_current_speed(UPLOAD),
             'download': ds.get_current_speed(DOWNLOAD)}
            dlist.append(dl)

        condition.acquire()
        condition.notify()
        condition.release()
        return (0.0, False)

    def speed_callback(self, dslist):
        upspeed = 0
        downspeed = 0
        for ds in dslist:
            d = ds.get_download()
            upspeed += ds.get_current_speed(UPLOAD)
            downspeed += ds.get_current_speed(DOWNLOAD)

        self.downspeed = downspeed
        self.upspeed = upspeed
        return (1.0, False)

    def statusPage(self):
        page = '<!DOCTYPE html>'
        page += '<html>\n'
        header = os.path.join(self.webUIPath, 'html', 'head.html')
        if DEBUG:
            log('webui::statusPage: header', header)
        if os.path.isfile(header):
            f = open(header)
            head = f.read()
            f.close
            page += head
        body = os.path.join(self.webUIPath, 'html', 'body.html')
        if DEBUG:
            log('webui::statusPage: body', body)
        if os.path.isfile(body):
            f = open(body)
            tmp = f.read()
            f.close
            page += tmp
        page += '</html>'
        return page

    def createStreamPage(self):
        path = os.path.join(self.webUIPath, 'html', 'create_stream.html')
        if not os.path.isfile(path):
            return ''
        f = open(path)
        html = f.read()
        f.close()
        destdir = self.bgApp.get_default_destdir()
        if isinstance(destdir, unicode):
            destdir = destdir.encode('utf-8')
        html = html.replace('{dest_dir}', destdir)
        return html

    def playerPage(self, player_id, params):
        path = os.path.join(self.webUIPath, 'html', 'player.html')
        if not os.path.isfile(path):
            return ''
        f = open(path)
        html = f.read()
        f.close()
        if 'autoplay' in params and params['autoplay'] == 'true':
            autoplay = 'true'
        else:
            autoplay = 'false'
        html = html.replace('{player_id}', player_id)
        html = html.replace('{autoplay}', autoplay)
        return html

    def getContentType(self, ext):
        content_type = 'text/plain'
        if ext in self.contentTypes:
            content_type = self.contentTypes[ext]
        return content_type
