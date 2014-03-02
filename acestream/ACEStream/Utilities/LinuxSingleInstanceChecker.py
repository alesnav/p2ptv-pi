#Embedded file name: ACEStream\Utilities\LinuxSingleInstanceChecker.pyo
import sys
import commands

class LinuxSingleInstanceChecker:

    def __init__(self, basename):
        self.basename = basename

    def IsAnotherRunning(self):
        cmd = 'pgrep -fl "%s\\.py" | grep -v pgrep' % self.basename
        progressInfo = commands.getoutput(cmd)
        print >> sys.stderr, 'LinuxSingleInstanceChecker returned', progressInfo
        numProcesses = len(progressInfo.split('\n'))
        return numProcesses > 1
