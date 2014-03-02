#Embedded file name: ACEStream\Core\BitTornado\HTTPHandler.pyo
import sys
import time
from cStringIO import StringIO
from clock import clock
from gzip import GzipFile
from traceback import print_exc
from ACEStream.Core.Utilities.logger import log, log_exc
try:
    True
except:
    True = 1
    False = 0

DEBUG = False
DEBUG2 = False
weekdays = ['Mon',
 'Tue',
 'Wed',
 'Thu',
 'Fri',
 'Sat',
 'Sun']
months = [None,
 'Jan',
 'Feb',
 'Mar',
 'Apr',
 'May',
 'Jun',
 'Jul',
 'Aug',
 'Sep',
 'Oct',
 'Nov',
 'Dec']

class HTTPConnection:

    def __init__(self, handler, connection):
        self.handler = handler
        self.connection = connection
        self.buf = ''
        self.closed = False
        self.done = False
        self.donereading = False
        self.next_func = self.read_type
        if DEBUG:
            log('HTTPConnection::__init__: handler', handler, 'connection', connection)

    def get_ip(self):
        return self.connection.get_ip()

    def data_came_in(self, data):
        if DEBUG2:
            log('HTTPConnection::data_came_in: data_len', len(data), 'data', data)
        if self.donereading or self.next_func is None:
            if DEBUG2:
                log('HTTPConnection::data_came_in: skip and return True: donereading', self.donereading, 'or next_func', self.next_func)
            return True
        self.buf += data
        if DEBUG2:
            log('HTTPConnection::data_came_in: buf_len', len(self.buf))
        while 1:
            try:
                i = self.buf.index('\n')
            except ValueError:
                return True

            val = self.buf[:i]
            self.buf = self.buf[i + 1:]
            self.next_func = self.next_func(val)
            if self.donereading:
                if DEBUG2:
                    log('HTTPConnection::data_came_in: donereading, return True')
                return True
            if self.next_func is None or self.closed:
                if DEBUG2:
                    log('HTTPConnection::data_came_in: break and return False: next_func', self.next_func, 'or closed', self.closed)
                return False

    def read_type(self, data):
        self.header = data.strip()
        words = data.split()
        if DEBUG2:
            log('HTTPConnection::read_type: data', data, 'words', words)
        if len(words) == 3:
            self.command, self.path, garbage = words
            self.pre1 = False
        elif len(words) == 2:
            self.command, self.path = words
            self.pre1 = True
            if self.command != 'GET':
                if DEBUG2:
                    log('HTTPConnection::read_type: return none')
                return None
        else:
            if DEBUG2:
                log('HTTPConnection::read_type: return none')
            return None
        if self.command not in ('HEAD', 'GET'):
            if DEBUG2:
                log('HTTPConnection::read_type: return none')
            return None
        self.headers = {}
        if DEBUG2:
            log('HTTPConnection::read_type: command', self.command, 'path', self.path, 'next read_header()')
        return self.read_header

    def read_header(self, data):
        data = data.strip()
        if data == '':
            self.donereading = True
            if self.headers.get('accept-encoding', '').find('gzip') > -1:
                self.encoding = 'gzip'
            else:
                self.encoding = 'identity'
            if DEBUG2:
                log('HTTPConnection::read_header: done reading, call getfunc: path', self.path, 'headers', self.headers)
            r = self.handler.getfunc(self, self.path, self.headers)
            if r is not None:
                self.answer(r)
            elif DEBUG2:
                log('HTTPConnection::read_header: getfunc returned None')
            return
        try:
            i = data.index(':')
        except ValueError:
            return

        header_name = data[:i].strip().lower()
        header_value = data[i + 1:].strip()
        self.headers[header_name] = header_value
        if DEBUG2:
            log('HTTPConnection::read_header: add header: header_name', header_name, 'header_value', header_value)
        return self.read_header

    def answer(self, (responsecode, responsestring, headers, data)):
        if self.closed:
            if DEBUG2:
                log('HTTPConnection::answer: closed, skip answer')
            return
        if DEBUG2:
            log('HTTPConnection::answer: len', len(data), 'code', responsecode, responsestring, 'headers', headers)
        if self.encoding == 'gzip':
            compressed = StringIO()
            gz = GzipFile(fileobj=compressed, mode='wb', compresslevel=9)
            gz.write(data)
            gz.close()
            cdata = compressed.getvalue()
            if len(cdata) >= len(data):
                self.encoding = 'identity'
            else:
                if DEBUG2:
                    log('HTTPConnection::answer: gzip response: compressed=%i uncompressed=%i\n' % (len(cdata), len(data)))
                data = cdata
                headers['Content-Encoding'] = 'gzip'
        if self.encoding == 'identity':
            ident = '-'
        else:
            ident = self.encoding
        self.handler.log(self.connection.get_ip(), ident, '-', self.header, responsecode, len(data), self.headers.get('referer', '-'), self.headers.get('user-agent', '-'))
        self.done = True
        r = StringIO()
        r.write('HTTP/1.0 ' + str(responsecode) + ' ' + responsestring + '\r\n')
        if not self.pre1:
            headers['Content-Length'] = len(data)
            for key, value in headers.items():
                r.write(key + ': ' + str(value) + '\r\n')

            r.write('\r\n')
        if self.command != 'HEAD':
            r.write(data)
        self.connection.write(r.getvalue())
        if self.connection.is_flushed():
            if DEBUG2:
                log('HTTPConnection::answer: connection is flushed, call connection.shutdown')
            self.connection.shutdown(1)
        elif DEBUG2:
            log('HTTPConnection::answer: connection is not flushed')


class HTTPHandler:

    def __init__(self, getfunc, minflush):
        self.connections = {}
        self.getfunc = getfunc
        self.minflush = minflush
        self.lastflush = clock()
        if DEBUG:
            log('HTTPHandler::__init__: ---')

    def external_connection_made(self, connection):
        connection.set_handler(self)
        self.connections[connection] = HTTPConnection(self, connection)
        if DEBUG2:
            log('HTTPHandler::external_connection_made: count_connections', len(self.connections), 'connection', connection)

    def connection_flushed(self, connection):
        if self.connections[connection].done:
            if DEBUG2:
                log('HTTPHandler::connection_flushed: connection is done, call connection.shutdown')
            connection.shutdown(1)
        elif DEBUG2:
            log('HTTPHandler::connection_flushed: connection is not done')

    def connection_lost(self, connection):
        try:
            ec = self.connections[connection]
            ec.closed = True
            del ec.connection
            del ec.next_func
            del self.connections[connection]
            if DEBUG2:
                log('HTTPHandler::connection_lost: count_connections', len(self.connections), 'connection', connection)
        except:
            if DEBUG2:
                log('HTTPHandler::connection_lost: error: connection', connection)
            print_exc()
            raise

    def data_came_in(self, connection, data):
        c = self.connections[connection]
        if DEBUG2:
            log('HTTPHandler::data_came_in: data_len', len(data), 'connection', connection)
        if not c.data_came_in(data) and not c.closed:
            if DEBUG2:
                log('HTTPHandler::data_came_in: shutdown connection')
            c.connection.shutdown(1)

    def log(self, ip, ident, username, header, responsecode, length, referrer, useragent):
        year, month, day, hour, minute, second, a, b, c = time.localtime(time.time())
        if DEBUG:
            print >> sys.stderr, 'HTTPHandler: %s %s %s [%02d/%3s/%04d:%02d:%02d:%02d] "%s" %i %i "%s" "%s"' % (ip,
             ident,
             username,
             day,
             months[month],
             year,
             hour,
             minute,
             second,
             header,
             responsecode,
             length,
             referrer,
             useragent)
        t = clock()
        if t - self.lastflush > self.minflush:
            self.lastflush = t
            sys.stdout.flush()


class DummyHTTPHandler:

    def __init__(self):
        pass

    def external_connection_made(self, connection):
        if DEBUG:
            print >> sys.stderr, 'DummyHTTPHandler: ext_conn_made'
        reply = 'HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n\r\nACEStream Internal Tracker not activated.\r\n'
        connection.write(reply)
        connection.close()

    def connection_flushed(self, connection):
        pass

    def connection_lost(self, connection):
        pass

    def data_came_in(self, connection, data):
        if DEBUG:
            print >> sys.stderr, 'DummyHTTPHandler: data_came_in', len(data)

    def log(self, ip, ident, username, header, responsecode, length, referrer, useragent):
        pass
