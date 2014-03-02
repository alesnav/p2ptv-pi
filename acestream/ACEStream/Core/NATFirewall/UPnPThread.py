#Embedded file name: ACEStream\Core\NATFirewall\UPnPThread.pyo
import sys
from threading import Event, Thread
from traceback import print_exc
from ACEStream.Core.BitTornado.natpunch import UPnPWrapper, UPnPError
DEBUG = False

class UPnPThread(Thread):

    def __init__(self, upnp_type, ext_ip, listen_port, error_func, got_ext_ip_func):
        Thread.__init__(self)
        self.daemon = True
        self.name = 'UPnP' + self.name
        self.upnp_type = upnp_type
        self.locally_guessed_ext_ip = ext_ip
        self.listen_port = listen_port
        self.error_func = error_func
        self.got_ext_ip_func = got_ext_ip_func
        self.shutdownevent = Event()

    def run(self):
        if self.upnp_type > 0:
            self.upnp_wrap = UPnPWrapper.getInstance()
            self.upnp_wrap.register(self.locally_guessed_ext_ip)
            if self.upnp_wrap.test(self.upnp_type):
                try:
                    shownerror = False
                    if self.upnp_type != 1:
                        ret = self.upnp_wrap.get_ext_ip()
                        if len(ret) == 0:
                            shownerror = True
                            self.error_func(self.upnp_type, self.listen_port, 0)
                        else:
                            for ip in ret:
                                self.got_ext_ip_func(ip)

                    ret = self.upnp_wrap.open(self.listen_port, iproto='TCP')
                    if ret == False and not shownerror:
                        self.error_func(self.upnp_type, self.listen_port, 0)
                    ret = self.upnp_wrap.open(self.listen_port, iproto='UDP')
                    if ret == False and not shownerror:
                        self.error_func(self.upnp_type, self.listen_port, 0, listenproto='UDP')
                except UPnPError as e:
                    self.error_func(self.upnp_type, self.listen_port, 1, e)

            elif self.upnp_type != 3:
                self.error_func(self.upnp_type, self.listen_port, 2)
            elif DEBUG:
                print >> sys.stderr, "upnp: thread: Initialization failed, but didn't report error because UPnP mode 3 is now enabled by default"
        if self.upnp_type > 0:
            if DEBUG:
                print >> sys.stderr, 'upnp: thread: Waiting till shutdown'
            self.shutdownevent.wait()
            if DEBUG:
                try:
                    print >> sys.stderr, 'upnp: thread: Shutting down, closing port on firewall'
                except:
                    pass

            try:
                self.upnp_wrap.close(self.listen_port, iproto='TCP')
                self.upnp_wrap.close(self.listen_port, iproto='UDP')
            except Exception as e:
                try:
                    print >> sys.stderr, 'upnp: thread: close port at shutdown threw', e
                    print_exc()
                except:
                    pass

    def shutdown(self):
        self.shutdownevent.set()
