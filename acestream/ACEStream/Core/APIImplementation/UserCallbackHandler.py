#Embedded file name: ACEStream\Core\APIImplementation\UserCallbackHandler.pyo
import sys
import os
import shutil
import binascii
from threading import currentThread
from traceback import print_exc
from ACEStream.Core.simpledefs import *
from ACEStream.Core.APIImplementation.ThreadPool import ThreadPool
from ACEStream.Core.CacheDB.Notifier import Notifier
from ACEStream.GlobalConfig import globalConfig
DEBUG = False

class UserCallbackHandler:

    def __init__(self, session):
        self.session = session
        self.sesslock = session.sesslock
        self.sessconfig = session.sessconfig
        mode = globalConfig.get_mode()
        if mode == 'stream' or mode == 'node' or mode == 'tracker':
            count_threads = 1
        else:
            count_threads = 10
        self.threadpool = ThreadPool(count_threads)
        self.notifier = Notifier.getInstance(self.threadpool)

    def shutdown(self):
        if DEBUG:
            print >> sys.stderr, 'uch: shutdown'
        self.threadpool.joinAll()

    def perform_vod_usercallback(self, d, usercallback, event, params):
        if DEBUG:
            print >> sys.stderr, 'Session: perform_vod_usercallback()', `(d.get_def().get_name_as_unicode())`

        def session_vod_usercallback_target():
            try:
                usercallback(d, event, params)
            except:
                print_exc()

        self.perform_usercallback(session_vod_usercallback_target)

    def perform_getstate_usercallback(self, usercallback, data, returncallback):
        if DEBUG:
            print >> sys.stderr, 'Session: perform_getstate_usercallback()'

        def session_getstate_usercallback_target():
            try:
                when, getpeerlist = usercallback(data)
                returncallback(usercallback, when, getpeerlist)
            except:
                print_exc()

        self.perform_usercallback(session_getstate_usercallback_target)

    def perform_removestate_callback(self, dltype, dlhash, contentdest, removecontent):
        if DEBUG:
            print >> sys.stderr, 'Session: perform_removestate_callback()'

        def session_removestate_callback_target():
            if DEBUG:
                print >> sys.stderr, 'Session: session_removestate_callback_target called', currentThread().getName()
            try:
                self.sesscb_removestate(dltype, dlhash, contentdest, removecontent)
            except:
                print_exc()

        self.perform_usercallback(session_removestate_callback_target)

    def perform_usercallback(self, target):
        self.sesslock.acquire()
        try:
            self.threadpool.queueTask(target)
        finally:
            self.sesslock.release()

    def sesscb_removestate(self, dltype, dlhash, contentdest, removecontent):
        contentdest = contentdest.encode('utf-8')
        if DEBUG:
            print >> sys.stderr, 'Session: sesscb_removestate called', `dlhash`, `contentdest`, removecontent
        self.sesslock.acquire()
        try:
            if self.session.lm.download_exists(dltype, dlhash):
                print >> sys.stderr, 'Session: sesscb_removestate: Download is back, restarted? Canceling removal!', `dlhash`
                return
            if dltype == DLTYPE_TORRENT:
                dlpstatedir = os.path.join(self.sessconfig['state_dir'], STATEDIR_DLPSTATE_DIR)
            elif dltype == DLTYPE_DIRECT:
                dlpstatedir = os.path.join(self.sessconfig['state_dir'], STATEDIR_DLDIRECT_PSTATE_DIR)
        finally:
            self.sesslock.release()

        if dltype == DLTYPE_TORRENT:
            try:
                self.session.remove_from_internal_tracker_by_infohash(dlhash)
            except:
                print_exc()

        hexdlhash = binascii.hexlify(dlhash)
        try:
            temp_dir = os.path.join(self.sessconfig['buffer_dir'], hexdlhash)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, True)
        except:
            print_exc()

        try:
            basename = hexdlhash + '.pickle'
            filename = os.path.join(dlpstatedir, basename)
            if DEBUG:
                print >> sys.stderr, 'Session: sesscb_removestate: removing dlcheckpoint entry', filename
            if os.access(filename, os.F_OK):
                os.remove(filename)
        except:
            print_exc()

        if removecontent and contentdest is not None:
            if DEBUG:
                print >> sys.stderr, 'Session: sesscb_removestate: removing saved content', contentdest
            if not os.path.isdir(contentdest):
                if os.path.exists(contentdest):
                    os.remove(contentdest)
            else:
                shutil.rmtree(contentdest, True)

    def notify(self, subject, changeType, obj_id, *args):
        if DEBUG:
            print >> sys.stderr, 'ucb: notify called:', subject, changeType, `obj_id`, args
        self.notifier.notify(subject, changeType, obj_id, *args)
