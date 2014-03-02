#Embedded file name: ACEStream\Utilities\Instance2Instance.pyo
import sys
import socket
import os
from traceback import print_exc, print_stack
from threading import Thread, Event
from ACEStream.GlobalConfig import globalConfig
from ACEStream.Core.BitTornado.RawServer import RawServer
from ACEStream.Core.Utilities.logger import log, log_exc
DEBUG = False

class Instance2InstanceServer(Thread):

    def __init__(self, i2iport, connhandler, timeout = 300.0, port_file = None):
        Thread.__init__(self)
        self.setDaemon(True)
        self.setName('Instance2Instance' + self.getName())
        self.i2iport = i2iport
        self.port_file = port_file
        self.connhandler = connhandler
        self.i2idoneflag = Event()
        self.rawserver = RawServer(self.i2idoneflag, timeout / 5.0, timeout, ipv6_enable=False, failfunc=self.rawserver_fatalerrorfunc, errorfunc=self.rawserver_nonfatalerrorfunc)
        self.rawserver.add_task(self.rawserver_keepalive, 1)
        if globalConfig.get_value('allow-non-local-client-connection'):
            interfaces = self.rawserver.bind(self.i2iport, reuse=True)
        else:
            interfaces = self.rawserver.bind(self.i2iport, bind=['127.0.0.1'], reuse=True)
        if DEBUG:
            log('i2is::init: bound on interfaces', interfaces)
        if i2iport == 0 and len(interfaces):
            host, port = interfaces[0]
            self.i2iport = port
            if port_file is not None:
                f = None
                try:
                    f = open(port_file, 'w')
                    f.write(str(port))
                except:
                    if DEBUG:
                        log('i2is::init: cannot save port to file', port_file)
                    raise Exception, 'Cannot save port'
                finally:
                    if f:
                        f.close()

    def rawserver_keepalive(self):
        self.rawserver.add_task(self.rawserver_keepalive, 1)

    def shutdown(self):
        self.connhandler.shutdown()
        self.i2idoneflag.set()
        if self.port_file is not None and os.path.isfile(self.port_file):
            try:
                os.remove(self.port_file)
            except:
                if DEBUG:
                    print_exc()

    def rawserver_fatalerrorfunc(self, e):
        if DEBUG:
            print >> sys.stderr, 'i2is: RawServer fatal error func called', e
        print_exc()

    def rawserver_nonfatalerrorfunc(self, e):
        if DEBUG:
            print >> sys.stderr, 'i2is: RawServer non fatal error func called', e
            print_exc()

    def run(self):
        try:
            if DEBUG:
                log('i2is::run: ready to receive remote commands on', self.i2iport)
            self.rawserver.listen_forever(self)
        except:
            print_exc()
        finally:
            self.rawserver.shutdown()

    def external_connection_made(self, s):
        try:
            self.connhandler.external_connection_made(s)
        except:
            print_exc()
            s.close()

    def connection_flushed(self, s):
        self.connhandler.connection_flushed(s)

    def connection_lost(self, s):
        if DEBUG:
            log('Instance2InstanceServer: connection_lost ------------------------------------------------')
        self.connhandler.connection_lost(s)

    def data_came_in(self, s, data):
        try:
            self.connhandler.data_came_in(s, data)
        except:
            print_exc()
            s.close()

    def add_task(self, func, t):
        self.rawserver.add_task(func, t)


class InstanceConnectionHandler:

    def __init__(self, readlinecallback = None):
        self.readlinecallback = readlinecallback
        self.singsock2ic = {}

    def set_readlinecallback(self, readlinecallback):
        self.readlinecallback = readlinecallback

    def external_connection_made(self, s):
        peername = s.get_ip()
        if DEBUG:
            log('InstanceConnectionHandler: external_connection_made: ip', peername)
        if not globalConfig.get_value('allow-non-local-client-connection') and peername != '127.0.0.1':
            print >> sys.stderr, 'i2is: ich: ext_conn_made: Refusing non-local connection from', peername
            s.close()
        ic = InstanceConnection(s, self, self.readlinecallback)
        self.singsock2ic[s] = ic

    def connection_flushed(self, s):
        pass

    def connection_lost(self, s):
        peername = s.get_ip()
        if DEBUG:
            log('InstanceConnectionHandler:connection_lost: ip', peername)
        if not globalConfig.get_value('allow-non-local-client-connection') and peername != '127.0.0.1':
            print >> sys.stderr, 'i2is: ich: connection_lost: Refusing non-local connection from', peername
            return
        del self.singsock2ic[s]

    def data_came_in(self, s, data):
        if DEBUG:
            log('InstanceConnectionHandler:data_came_in')
        ic = self.singsock2ic[s]
        try:
            ic.data_came_in(data)
        except:
            print_exc()

    def shutdown(self):
        if DEBUG:
            log('InstanceConnectionHandler:shutdown')
        for ic in self.singsock2ic.values():
            ic.shutdown()


class InstanceConnection:

    def __init__(self, singsock, connhandler, readlinecallback):
        self.singsock = singsock
        self.connhandler = connhandler
        self.readlinecallback = readlinecallback
        self.rflag = False
        self.remain = ''
        self.proto = 0

    def data_came_in(self, data):
        if DEBUG:
            if len(data) > 100:
                display_data = data[0:20] + '...' + data[-20:]
            else:
                display_data = data
            if len(self.remain) > 100:
                display_remain = self.remain[0:20] + '...' + self.remain[-20:]
            else:
                display_remain = self.remain
        if DEBUG:
            log('InstanceConnection::data_came_in: data_len', len(data), 'remain_len', len(self.remain), 'data', display_data)
        if len(self.remain):
            data = self.remain + data
            self.remain = ''
            if len(data) > 100:
                display_data = data[0:20] + '...' + data[-20:]
            else:
                display_data = data
            if DEBUG:
                log('InstanceConnection::data_came_in: add remain: remain', display_remain, 'data', display_data)
        lines = data.splitlines(True)
        for line in lines:
            if DEBUG:
                if len(line) > 100:
                    display_line = line[0:20] + '...' + line[-20:]
                else:
                    display_line = line
            if line.endswith('\r\n'):
                if DEBUG:
                    log('InstanceConnection::data_came_in: got command: line', display_line)
                self.remain = ''
                self.readlinecallback(self, line[:-2])
            else:
                if DEBUG:
                    log('InstanceConnection::data_came_in: command not completed: line', display_line, 'remain', display_remain)
                self.remain += line

    def write(self, data):
        if self.singsock is not None:
            self.singsock.write(data)

    def close(self):
        if DEBUG:
            print >> sys.stderr, 'InstanceConnection:close'
        if self.singsock is not None:
            self.singsock.close()
            self.connhandler.connection_lost(self.singsock)
            self.singsock = None


class Instance2InstanceClient:

    def __init__(self, port, cmd, param):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('127.0.0.1', port))
        msg = cmd + ' ' + param + '\r\n'
        s.send(msg)
        s.close()
