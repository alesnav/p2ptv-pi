#Embedded file name: ACEStream\Core\NATFirewall\upnp.pyo
import sys
import socket
from cStringIO import StringIO
import urllib
import urllib2
from urlparse import urlparse
import xml.sax as sax
from xml.sax.handler import ContentHandler
from traceback import print_exc
from ACEStream.Core.BitTornado.subnetparse import IP_List
from ACEStream.Core.Utilities.logger import log, log_exc
UPNP_WANTED_SERVICETYPES = ['urn:schemas-upnp-org:service:WANIPConnection:1', 'urn:schemas-upnp-org:service:WANPPPConnection:1']
DEBUG = False

class UPnPPlatformIndependent:

    def __init__(self):
        self.services = {}
        self.lastdiscovertime = 0
        self.local_ip_list = IP_List()
        self.local_ip_list.set_intranet_addresses()

    def discover(self):
        maxwait = 4
        req = 'M-SEARCH * HTTP/1.1\r\n'
        req += 'HOST: 239.255.255.250:1900\r\n'
        req += 'MAN: "ssdp:discover"\r\n'
        req += 'MX: ' + str(maxwait) + '\r\n'
        req += 'ST: ssdp:all\r\n'
        req += '\r\n\r\n'
        try:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.s.settimeout(maxwait + 2.0)
            self.s.sendto(req, ('239.255.255.250', 1900))
            while True:
                if DEBUG:
                    print >> sys.stderr, 'upnp: discover: Wait 4 reply'
                rep, sender = self.s.recvfrom(1024)
                if DEBUG:
                    print >> sys.stderr, 'upnp: discover: Got reply from', sender
                repio = StringIO(rep)
                while True:
                    line = repio.readline()
                    if line == '':
                        break
                    if line[-2:] == '\r\n':
                        line = line[:-2]
                    idx = line.find(':')
                    if idx == -1:
                        continue
                    key = line[:idx]
                    key = key.lower()
                    if key.startswith('location'):
                        location = line[idx + 1:].strip()
                        desc = self.get_description(location)
                        if desc is not None:
                            self.services[location] = self.parse_services(desc)

        except:
            if DEBUG:
                print_exc()

    def found_wanted_services(self):
        for location, services in self.services.iteritems():
            for service in services:
                if service['type'] in UPNP_WANTED_SERVICETYPES:
                    return True

        return False

    def add_port_map(self, internalip, port, iproto = 'TCP'):
        success = False
        ret = self.do_soap_request('AddPortMapping', port, iproto=iproto, internalip=internalip)
        for srch in ret:
            se = srch.get_error()
            if se is None:
                success = True
            elif DEBUG:
                log('upnp::add_port_map: error:', str(se))

        if not success:
            raise Exception, 'Failed to map port'

    def del_port_map(self, port, iproto = 'TCP'):
        success = False
        ret = self.do_soap_request('DeletePortMapping', port, iproto=iproto)
        for srch in ret:
            se = srch.get_error()
            if se is None:
                success = True
            elif DEBUG:
                log('upnp::del_port_map: error:', str(se))

        if not success:
            raise Exception, 'Failed to delete port mapping'

    def get_ext_ip(self):
        ext_ip_list = []
        ret = self.do_soap_request('GetExternalIPAddress')
        for srch in ret:
            se = srch.get_error()
            if se is None:
                ip = srch.get_ext_ip()
                if self.is_valid_ext_ip(ip):
                    if DEBUG:
                        log('upnp::get_ext_ip: add ip to the list:', ip)
                    ext_ip_list.append(ip)
                elif DEBUG:
                    log('upnp::get_ext_ip: not a valid ip, ignore:', ip)
            elif DEBUG:
                log('upnp::get_ext_ip: error:', str(se))

        return ext_ip_list

    def is_valid_ext_ip(self, ip):
        if ip is None:
            return False
        elif not isinstance(ip, (str, unicode)):
            return False
        elif len(ip) == 0:
            return False
        elif ip == '0.0.0.0':
            return False
        elif self.local_ip_list.includes(ip):
            return False
        else:
            return True

    def do_soap_request(self, methodname, port = -1, iproto = 'TCP', internalip = None):
        for location, services in self.services.iteritems():
            for service in services:
                if service['type'] in UPNP_WANTED_SERVICETYPES:
                    o = urlparse(location)
                    endpoint = o[0] + '://' + o[1] + service['url']
                    if DEBUG:
                        log('upnp::do_soap_request: methodname', methodname, 'endpoint', endpoint, 'port', port, 'iproto', iproto, 'internalip', internalip)
                    headers, body = self.create_soap_request(methodname, port, iproto=iproto, internalip=internalip)
                    if DEBUG:
                        log('upnp::do_soap_request: headers', headers)
                        log('upnp::do_soap_request: body', body)
                    try:
                        req = urllib2.Request(url=endpoint, data=body, headers=headers)
                        f = urllib2.urlopen(req)
                        resp = f.read()
                    except urllib2.HTTPError as e:
                        resp = e.fp.read()
                        if DEBUG:
                            print_exc()

                    srch = SOAPResponseContentHandler(methodname)
                    if DEBUG:
                        log('upnp::do_soap_request: method', methodname, 'response', resp)
                    try:
                        srch.parse(resp)
                    except sax.SAXParseException as e:
                        se = srch.get_error()
                        if se is None:
                            srch.set_error(str(e))
                    except Exception as e:
                        srch.set_error(str(e))

                    yield srch

    def get_description(self, url):
        if DEBUG:
            log('upnp::get_description: url', url)
        try:
            f = urllib2.urlopen(url, timeout=5.0)
            data = f.read()
            return data
        except:
            if DEBUG:
                print_exc()
            return None

    def parse_services(self, desc):
        dch = DescriptionContentHandler()
        dch.parse(desc)
        return dch.services

    def create_soap_request(self, methodname, port = -1, iproto = 'TCP', internalip = None):
        headers = {}
        headers['Content-type'] = 'text/xml; charset="utf-8"'
        headers['SOAPAction'] = '"urn:schemas-upnp-org:service:WANIPConnection:1#' + methodname + '"'
        headers['User-Agent'] = 'Mozilla/4.0 (compatible; UPnP/1.0; Windows 9x)'
        body = ''
        body += '<?xml version="1.0"?>'
        body += '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"'
        body += ' SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        body += '<SOAP-ENV:Body><m:' + methodname + ' xmlns:m="urn:schemas-upnp-org:service:WANIPConnection:1">'
        if methodname == 'AddPortMapping':
            externalport = port
            internalport = port
            internalclient = internalip
            description = 'TSEngine ' + iproto + ' at ' + internalip + ':' + str(internalport)
            body += '<NewRemoteHost xmlns:dt="urn:schemas-microsoft-com:datatypes" dt:dt="string"></NewRemoteHost>'
            body += '<NewExternalPort xmlns:dt="urn:schemas-microsoft-com:datatypes" dt:dt="ui2">' + str(externalport) + '</NewExternalPort>'
            body += '<NewProtocol xmlns:dt="urn:schemas-microsoft-com:datatypes" dt:dt="string">' + iproto + '</NewProtocol>'
            body += '<NewInternalPort xmlns:dt="urn:schemas-microsoft-com:datatypes" dt:dt="ui2">' + str(internalport) + '</NewInternalPort>'
            body += '<NewInternalClient xmlns:dt="urn:schemas-microsoft-com:datatypes" dt:dt="string">' + internalclient + '</NewInternalClient>'
            body += '<NewEnabled xmlns:dt="urn:schemas-microsoft-com:datatypes" dt:dt="boolean">1</NewEnabled>'
            body += '<NewPortMappingDescription xmlns:dt="urn:schemas-microsoft-com:datatypes" dt:dt="string">' + description + '</NewPortMappingDescription>'
            body += '<NewLeaseDuration xmlns:dt="urn:schemas-microsoft-com:datatypes" dt:dt="ui4">0</NewLeaseDuration>'
        elif methodname == 'DeletePortMapping':
            externalport = port
            body += '<NewRemoteHost xmlns:dt="urn:schemas-microsoft-com:datatypes" dt:dt="string"></NewRemoteHost>'
            body += '<NewExternalPort xmlns:dt="urn:schemas-microsoft-com:datatypes" dt:dt="ui2">' + str(externalport) + '</NewExternalPort>'
            body += '<NewProtocol xmlns:dt="urn:schemas-microsoft-com:datatypes" dt:dt="string">' + iproto + '</NewProtocol>'
        body += '</m:' + methodname + '></SOAP-ENV:Body>'
        body += '</SOAP-ENV:Envelope>'
        return (headers, body)


class UPnPError(Exception):

    def __init__(self, errorcode, errordesc):
        Exception.__init__(self)
        self.errorcode = errorcode
        self.errordesc = errordesc

    def __str__(self):
        return 'UPnP Error %d: %s' % (self.errorcode, self.errordesc)


class DescriptionContentHandler(ContentHandler):

    def __init__(self):
        ContentHandler.__init__(self)
        self.currrent_service = {}
        self.services = []

    def parse(self, desc):
        sax.parseString(desc, self)

    def endDocument(self):
        if DEBUG:
            print >> sys.stderr, 'upnp: discover: Services found', self.services

    def startElement(self, name, attributes):
        n = name.lower()
        if n == 'service':
            self.current_service = {}

    def endElement(self, name):
        n = name.lower()
        if n == 'servicetype':
            if self.current_service is None:
                if DEBUG:
                    log('upnp::DescriptionContentHandler::endElement: not in <service>: name', name)
                return
            self.current_service['type'] = self.content
        elif n == 'controlurl':
            if self.current_service is None:
                if DEBUG:
                    log('upnp::DescriptionContentHandler::endElement: not in <service>: name', name)
                return
            self.current_service['url'] = self.content
        elif n == 'service':
            s = {'type': self.current_service['type'],
             'url': self.current_service['url']}
            self.services.append(s)
            self.current_service = None

    def characters(self, content):
        self.content = content


class SOAPResponseContentHandler(ContentHandler):

    def __init__(self, methodname):
        ContentHandler.__init__(self)
        self.methodname = methodname
        self.ip = None
        self.errorset = False
        self.errorcode = 0
        self.errordesc = 'No error'
        self.content = None

    def parse(self, resp):
        sax.parseString(resp, self)

    def get_ext_ip(self):
        return self.ip

    def get_error(self):
        if self.errorset:
            return UPnPError(self.errorcode, self.methodname + ': ' + self.errordesc)
        else:
            return None

    def set_error(self, errmsg):
        self.errorset = True
        self.errorcode = 0
        self.errordesc = errmsg

    def endElement(self, name):
        n = name.lower()
        if self.methodname == 'GetExternalIPAddress' and n.endswith('newexternalipaddress'):
            self.ip = self.content
        elif n == 'errorcode':
            self.errorset = True
            self.errorcode = int(self.content)
        elif n == 'errordescription':
            self.errorset = True
            self.errordesc = self.content

    def characters(self, content):
        self.content = content


if __name__ == '__main__':
    u = UPnPPlatformIndependent()
    u.discover()
    print >> sys.stderr, 'IGD say my external IP address is', u.get_ext_ip()
