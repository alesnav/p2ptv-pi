#Embedded file name: ACEStream\Core\Utilities\timeouturlopen.pyo
import sys
import httplib
import socket
import urllib2
import urllib
import urlparse
from gzip import GzipFile
from StringIO import StringIO
from ACEStream.version import VERSION
USER_AGENT = 'ACEStream/' + VERSION
DEBUG = False

def urlOpenTimeout(url, timeout = 30, content_type = None, cookiejar = None, *data):

    class TimeoutHTTPConnection(httplib.HTTPConnection):

        def connect(self):
            msg = 'getaddrinfo returns an empty list'
            for res in socket.getaddrinfo(self.host, self.port, 0, socket.SOCK_STREAM):
                af, socktype, proto, canonname, sa = res
                try:
                    self.sock = socket.socket(af, socktype, proto)
                    self.sock.settimeout(timeout)
                    if self.debuglevel > 0:
                        print 'connect: (%s, %s)' % (self.host, self.port)
                    self.sock.connect(sa)
                except socket.error as msg:
                    if self.debuglevel > 0:
                        print 'connect fail:', (self.host, self.port)
                    if self.sock:
                        self.sock.close()
                    self.sock = None
                    continue

                break

            if not self.sock:
                raise socket.error, msg

    class TimeoutHTTPHandler(urllib2.HTTPHandler):

        def http_open(self, req):
            return self.do_open(TimeoutHTTPConnection, req)

    class GZipProcessor(urllib2.BaseHandler):

        def http_request(self, req):
            req.add_header('Accept-Encoding', 'gzip')
            return req

        https_request = http_request

        def http_response(self, req, resp):
            if resp.headers.get('content-encoding') == 'gzip':
                gzip = GzipFile(fileobj=StringIO(resp.read()), mode='r')
                prev_resp = resp
                resp = urllib2.addinfourl(gzip, prev_resp.headers, prev_resp.url)
                resp.code = prev_resp.code
                resp.msg = prev_resp.msg
            return resp

        https_response = http_response

    handlers = [GZipProcessor,
     TimeoutHTTPHandler,
     urllib2.HTTPDefaultErrorHandler,
     urllib2.HTTPRedirectHandler]
    if cookiejar is not None:
        handlers.append(urllib2.HTTPCookieProcessor(cookiejar))
    opener = urllib2.build_opener(*handlers)
    request = urllib2.Request(url)
    request.add_header('User-Agent', USER_AGENT)
    if content_type is not None:
        request.add_header('Content-Type', content_type)
    return opener.open(request, *data)


def find_proxy(url):
    scheme, netloc, path, pars, query, fragment = urlparse.urlparse(url)
    proxies = urllib.getproxies()
    proxyhost = None
    if scheme in proxies:
        if '@' in netloc:
            sidx = netloc.find('@') + 1
        else:
            sidx = 0
        eidx = netloc.find(':')
        if eidx == -1:
            eidx = len(netloc)
        host = netloc[sidx:eidx]
        if not (host == '127.0.0.1' or urllib.proxy_bypass(host)):
            proxyurl = proxies[scheme]
            proxyelems = urlparse.urlparse(proxyurl)
            proxyhost = proxyelems[1]
    if DEBUG:
        print >> sys.stderr, 'find_proxy: Got proxies', proxies, 'selected', proxyhost, 'URL was', url
    return proxyhost
