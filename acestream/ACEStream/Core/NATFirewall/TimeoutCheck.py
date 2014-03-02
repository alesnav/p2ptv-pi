#Embedded file name: ACEStream\Core\NATFirewall\TimeoutCheck.pyo
from socket import *
import sys
import thread
import threading
DEBUG = False
to = -1
lck = threading.Lock()
evnt = threading.Event()

def pingback(ping, pingbacksrvr):
    global to
    global lck
    global evnt
    udpsock = socket(AF_INET, SOCK_DGRAM)
    udpsock.connect(pingbacksrvr)
    udpsock.settimeout(ping + 10)
    if DEBUG:
        print >> sys.stderr, 'TIMEOUTCHECK:', '-> ping'
    pingMsg = str('ping:' + str(ping))
    udpsock.send(pingMsg)
    udpsock.send(pingMsg)
    udpsock.send(pingMsg)
    while True:
        rcvaddr = None
        try:
            reply = udpsock.recv(1024)
        except timeout:
            if udpsock:
                udpsock.close()
            if DEBUG:
                print >> sys.stderr, 'TIMEOUTCHECK:', 'UDP connection to the pingback server has timed out for ping', ping
            lck.acquire()
            evnt.set()
            evnt.clear()
            lck.release()
            break

        if DEBUG:
            print >> sys.stderr, pingbacksrvr
        if DEBUG:
            print >> sys.stderr, rcvaddr
        if reply:
            data = reply.split(':')
            if DEBUG:
                print >> sys.stderr, data, 'received from the pingback server'
            if data[0] == 'pong':
                if DEBUG:
                    print >> sys.stderr, 'TIMEOUTCHECK:', '<-', data[0], 'after', data[1], 'seconds'
                to = ping
                if int(data[1]) == 145:
                    lck.acquire()
                    evnt.set()
                    evnt.clear()
                    lck.release()
                return
        return


def GetTimeout(pingbacksrvr):
    pings = [25,
     35,
     55,
     85,
     115,
     145]
    for ping in pings:
        thread.start_new_thread(pingback, (ping, pingbacksrvr))

    evnt.wait()
    if DEBUG:
        print >> sys.stderr, 'TIMEOUTCHECK: timeout is', to
    return to
