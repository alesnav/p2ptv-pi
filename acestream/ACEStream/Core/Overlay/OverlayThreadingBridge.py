#Embedded file name: ACEStream\Core\Overlay\OverlayThreadingBridge.pyo
import sys
from threading import currentThread
from traceback import print_exc
from ACEStream.Core.Overlay.SecureOverlay import CloseException
from ACEStream.Core.BitTornado.BT1.MessageID import getMessageName
from ACEStream.Core.Utilities.utilities import show_permid_short
from ACEStream.Utilities.TimedTaskQueue import TimedTaskQueue
import threading
DEBUG = False

class OverlayThreadingBridge:
    __single = None
    lock = threading.Lock()

    def __init__(self):
        if OverlayThreadingBridge.__single:
            raise RuntimeError, 'OverlayThreadingBridge is Singleton'
        OverlayThreadingBridge.__single = self
        self.secover = None
        self.olapps = None
        self.olappsmsghandler = None
        self.olappsconnhandler = None
        self.tqueue = TimedTaskQueue(nameprefix='Overlay')

    def getInstance(*args, **kw):
        if OverlayThreadingBridge.__single is None:
            OverlayThreadingBridge.lock.acquire()
            try:
                if OverlayThreadingBridge.__single is None:
                    OverlayThreadingBridge(*args, **kw)
            finally:
                OverlayThreadingBridge.lock.release()

        return OverlayThreadingBridge.__single

    getInstance = staticmethod(getInstance)

    def resetSingleton(self):
        OverlayThreadingBridge.__single = None

    def register_bridge(self, secover, olapps):
        self.secover = secover
        self.olapps = olapps
        secover.register_recv_callback(self.handleMessage)
        secover.register_conns_callback(self.handleConnection)

    def register(self, launchmanycore, max_len):
        self.secover.register(launchmanycore, max_len)
        self.iplport2oc = self.secover.iplport2oc

    def get_handler(self):
        return self.secover

    def start_listening(self):
        self.secover.start_listening()

    def register_recv_callback(self, callback):
        self.olappsmsghandler = callback

    def register_conns_callback(self, callback):
        self.olappsconnhandler = callback

    def handleConnection(self, exc, permid, selversion, locally_initiated, hisdns):
        if DEBUG:
            print >> sys.stderr, 'olbridge: handleConnection', exc, show_permid_short(permid), selversion, locally_initiated, hisdns, currentThread().getName()

        def olbridge_handle_conn_func():
            if DEBUG:
                print >> sys.stderr, 'olbridge: handle_conn_func', exc, show_permid_short(permid), selversion, locally_initiated, hisdns, currentThread().getName()
            try:
                if hisdns:
                    self.secover.add_peer_to_db(permid, hisdns, selversion)
                if self.olappsconnhandler is not None:
                    self.olappsconnhandler(exc, permid, selversion, locally_initiated)
            except:
                print_exc()

            if isinstance(exc, CloseException):
                self.secover.update_peer_status(permid, exc.was_auth_done())

        self.tqueue.add_task(olbridge_handle_conn_func, 0)

    def handleMessage(self, permid, selversion, message):
        if DEBUG:
            print >> sys.stderr, 'olbridge: handleMessage', show_permid_short(permid), selversion, getMessageName(message[0]), currentThread().getName()

        def olbridge_handle_msg_func():
            if DEBUG:
                print >> sys.stderr, 'olbridge: handle_msg_func', show_permid_short(permid), selversion, getMessageName(message[0]), currentThread().getName()
            try:
                if self.olappsmsghandler is None:
                    ret = True
                else:
                    ret = self.olappsmsghandler(permid, selversion, message)
            except:
                print_exc()
                ret = False

            if ret == False:
                if DEBUG:
                    print >> sys.stderr, 'olbridge: olbridge_handle_msg_func closing!', show_permid_short(permid), selversion, getMessageName(message[0]), currentThread().getName()
                self.close(permid)

        self.tqueue.add_task(olbridge_handle_msg_func, 0)
        return True

    def connect_dns(self, dns, callback):
        if DEBUG:
            print >> sys.stderr, 'olbridge: connect_dns', dns

        def olbridge_connect_dns_callback(cexc, cdns, cpermid, cselver):
            if DEBUG:
                print >> sys.stderr, 'olbridge: connect_dns_callback', cexc, cdns, show_permid_short(cpermid), cselver
            olbridge_connect_dns_callback_lambda = lambda : callback(cexc, cdns, cpermid, cselver)
            self.add_task(olbridge_connect_dns_callback_lambda, 0)

        self.secover.connect_dns(dns, olbridge_connect_dns_callback)

    def connect(self, permid, callback):
        if DEBUG:
            print >> sys.stderr, 'olbridge: connect', show_permid_short(permid), currentThread().getName()

        def olbridge_connect_callback(cexc, cdns, cpermid, cselver):
            if DEBUG:
                print >> sys.stderr, 'olbridge: connect_callback', cexc, cdns, show_permid_short(cpermid), cselver, callback, currentThread().getName()
            olbridge_connect_callback_lambda = lambda : callback(cexc, cdns, cpermid, cselver)
            self.add_task(olbridge_connect_callback_lambda, 0)

        self.secover.connect(permid, olbridge_connect_callback)

    def send(self, permid, msg, callback):
        if DEBUG:
            print >> sys.stderr, 'olbridge: send', show_permid_short(permid), len(msg)

        def olbridge_send_callback(cexc, cpermid):
            if DEBUG:
                print >> sys.stderr, 'olbridge: send_callback', cexc, show_permid_short(cpermid)
            olbridge_send_callback_lambda = lambda : callback(cexc, cpermid)
            self.add_task(olbridge_send_callback_lambda, 0)

        self.secover.send(permid, msg, olbridge_send_callback)

    def close(self, permid):
        self.secover.close(permid)

    def add_task(self, task, t = 0, ident = None):
        self.tqueue.add_task(task, t, ident)
