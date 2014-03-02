#Embedded file name: ACEStream\Plugin\EngineWx.pyo
import os
import sys
from traceback import print_exc
try:
    import wxversion
    wxversion.select('2.8')
except:
    pass

try:
    import wx
except:
    print 'wx is not installed'
    os._exit(1)

import ACEStream
from ACEStream.GlobalConfig import globalConfig
from ACEStream.Plugin.BackgroundProcess import run_bgapp, stop_bgapp, send_startup_event, get_default_api_version
from ACEStream.Player.systray import PlayerTaskBarIcon
from ACEStream.version import VERSION
ALLOW_MULTIPLE = False

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
        iconpath = bgapp.iconpath
        self.systray = PlayerTaskBarIcon(self, self.bgapp, iconpath)

    def set_icon_tooltip(self, txt):
        if self.systray is not None:
            self.systray.set_icon_tooltip(txt)

    def on_error(self, errmsg, exit = False):
        if self.bgapp is None:
            title = 'Error'
        else:
            title = self.bgapp.appname + ' Error'
        dlg = wx.MessageDialog(None, errmsg, title, wx.OK | wx.ICON_ERROR | wx.STAY_ON_TOP)
        result = dlg.ShowModal()
        dlg.Destroy()
        if exit:
            self.ExitMainLoop()


def start(apptype, exec_dir):
    if apptype == 'torrentstream':
        appname = 'Torrent Stream'
    elif apptype == 'acestream':
        appname = 'ACE Stream HD'
    else:
        raise Exception, 'Bad app type'
    single_instance_checker = wx.SingleInstanceChecker(appname + '-' + wx.GetUserId())
    if single_instance_checker.IsAnotherRunning():
        print >> sys.stderr, 'appwrapper: already running, exit'
        if get_default_api_version(apptype, exec_dir) < 2:
            send_startup_event()
        os._exit(0)
    globalConfig.set_value('apptype', apptype)
    globalConfig.set_mode('client_wx')
    wrapper = AppWrapper()
    try:
        bgapp = run_bgapp(wrapper, appname, VERSION)
    except Exception as e:
        print >> sys.stderr, 'Fatal error while starting:', str(e)
        print_exc()
        os._exit(0)

    wrapper.set_bgapp(bgapp)
    bgapp.debug_systray = bgapp.debug_level & 1024 != 0
    ACEStream.Player.systray.DEBUG = bgapp.debug_systray
    ACEStream.Player.systray.SHOW_DEBUG_LEVEL = bgapp.debug_systray
    ACEStream.Player.systray.DEBUG_PIECES = bgapp.debug_level & 128 != 0
    ACEStream.Player.systray.DEBUG_VIDEOSTATUS = bgapp.debug_level & 2048 != 0
    ACEStream.Player.systray.DEBUG_PROXY_BUF = bgapp.debug_level & 4096 != 0
    wrapper.MainLoop()
    if not ALLOW_MULTIPLE:
        del single_instance_checker
    stop_bgapp(bgapp)
