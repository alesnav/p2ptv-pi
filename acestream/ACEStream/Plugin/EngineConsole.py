#Embedded file name: ACEStream/Plugin/EngineConsole.py
import time
from ACEStream.GlobalConfig import globalConfig
from ACEStream.version import VERSION
from ACEStream.Plugin.BackgroundProcess import run_bgapp, stop_bgapp
from ACEStream.Core.Utilities.logger import log, log_exc

class AppWrapper:

    def __init__(self):
        self.bgapp = None

    def set_bgapp(self, bgapp):
        self.bgapp = bgapp

    def MainLoop(self):
        try:
            while True:
                time.sleep(10)

        except:
            log('appwrapper::MainLoop: exit')
            self.OnExit()

    def OnExit(self):
        if self.bgapp is not None:
            self.bgapp.OnExit()

    def set_icon_tooltip(self, txt):
        pass


def start(apptype, exec_dir):
    if apptype == 'torrentstream':
        appname = 'Torrent Stream'
    elif apptype == 'acestream':
        appname = 'ACE Stream HD'
    else:
        raise Exception, 'Bad app type'
    globalConfig.set_value('apptype', apptype)
    globalConfig.set_mode('client_console')
    wrapper = AppWrapper()
    bgapp = run_bgapp(wrapper, appname, VERSION)
    wrapper.set_bgapp(bgapp)
    wrapper.MainLoop()
    stop_bgapp(bgapp)