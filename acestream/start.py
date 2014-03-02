#!/usr/bin/python2.7
import os
import sys
curdir = os.path.abspath(os.path.dirname(sys.argv[0]))
from ACEStream.Plugin.EngineConsole import start
apptype = 'acestream'
start(apptype, curdir)