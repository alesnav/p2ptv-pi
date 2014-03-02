#Embedded file name: ACEStream\Core\NATFirewall\guessip.pyo
import os
import sys
import socket
from traceback import print_exc
DEBUG = False

def get_my_wan_ip():
    try:
        if sys.platform == 'win32':
            return get_my_wan_ip_win32()
        if sys.platform == 'darwin':
            return get_my_wan_ip_darwin()
        return get_my_wan_ip_linux()
    except:
        print_exc()
        return None


def get_my_wan_ip_win32():
    routecmd = 'netstat -nr'
    ifcmd = 'ipconfig /all'
    gwip = None
    for line in os.popen(routecmd).readlines():
        words = line.split()
        if len(words) >= 3:
            if words[0] == 'Default' and words[1] == 'Gateway:':
                gwip = words[-1]
                if DEBUG:
                    print 'netstat found default gateway', gwip
                break

    myip = None
    mywanip = None
    ingw = 0
    for line in os.popen(ifcmd).readlines():
        words = line.split()
        if len(words) >= 3:
            if words[0] == 'IP' and words[1] == 'Address.' or words[1] == 'IP' and words[2] == 'Address.':
                try:
                    socket.getaddrinfo(words[-1], None, socket.AF_INET)
                    myip = words[-1]
                    if DEBUG:
                        print 'ipconfig found IP address', myip
                except socket.gaierror:
                    if DEBUG:
                        print 'ipconfig ignoring IPv6 address', words[-1]

            elif words[0] == 'Default' and words[1] == 'Gateway':
                if words[-1] == ':':
                    if DEBUG:
                        print 'ipconfig ignoring empty default gateway'
                else:
                    ingw = 1
        if ingw >= 1:
            gwip2 = None
            ingw = (ingw + 1) % 3
            try:
                socket.getaddrinfo(words[-1], None, socket.AF_INET)
                gwip2 = words[-1]
                if DEBUG:
                    print 'ipconfig found default gateway', gwip2
            except socket.gaierror:
                if DEBUG:
                    print 'ipconfig ignoring IPv6 default gateway', words[-1]

            if gwip == gwip2:
                mywanip = myip
                break

    return mywanip


def get_my_wan_ip_linux():
    routecmd = '/bin/netstat -nr'
    ifcmd = '/sbin/ifconfig -a'
    gwif = None
    gwip = None
    for line in os.popen(routecmd).readlines():
        words = line.split()
        if len(words) >= 3:
            if words[0] == '0.0.0.0':
                gwif = words[-1]
                gwip = words[1]
                if DEBUG:
                    print 'netstat found default gateway', gwip
                break

    mywanip = None
    for line in os.popen(ifcmd).readlines():
        words = line.split()
        if len(words) >= 2:
            if words[0] == gwif:
                flag = True
            elif words[0] == 'inet':
                words2 = words[1].split(':')
                if len(words2) == 2:
                    mywanip = words2[1]
                    break
                else:
                    flag = False
            else:
                flag = False

    return mywanip


def get_my_wan_ip_darwin():
    routecmd = '/usr/sbin/netstat -nr'
    ifcmd = '/sbin/ifconfig -a'
    gwif = None
    gwip = None
    for line in os.popen(routecmd).readlines():
        words = line.split()
        if len(words) >= 3:
            if words[0] == 'default':
                gwif = words[-1]
                gwip = words[1]
                if DEBUG:
                    print 'netstat found default gateway', gwip
                break

    mywanip = None
    flag = False
    for line in os.popen(ifcmd).readlines():
        words = line.split()
        if len(words) >= 2:
            if words[0] == '%s:' % gwif:
                flag = True
            elif words[0] == 'inet' and flag:
                mywanip = words[1]
                break

    return mywanip


if __name__ == '__main__':
    DEBUG = True
    ip = get_my_wan_ip()
    print 'External IP address is', ip
