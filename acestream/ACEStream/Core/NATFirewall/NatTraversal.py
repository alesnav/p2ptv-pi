#Embedded file name: ACEStream\Core\NATFirewall\NatTraversal.pyo
from time import strftime
from traceback import print_exc
import socket
import sys
DEBUG = False

def coordinateHolePunching(peer1, peer2, holePunchingAddr):
    if DEBUG:
        print >> sys.stderr, 'NatTraversal: coordinateHolePunching at', holePunchingAddr
    try:
        udpsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udpsock.bind(holePunchingAddr)
        udpsock.settimeout(60)
    except socket.error as (errno, strerror):
        if udpsock:
            udpsock.close()
        if DEBUG:
            print >> sys.stderr, 'NatTraversal: Could not open socket: %s' % strerror
        return

    if DEBUG:
        print >> sys.stderr, 'NatTraversal: waiting for connection...'
    peeraddr2 = None
    while True:
        try:
            data, peeraddr1 = udpsock.recvfrom(1024)
            if not data:
                continue
            else:
                if DEBUG:
                    print >> sys.stderr, 'NatTraversal:', strftime('%Y/%m/%d %H:%M:%S'), '...connected from: ', peeraddr1
                if peeraddr2 == None:
                    peeraddr2 = peeraddr1
                elif peeraddr2 != peeraddr1:
                    udpsock.sendto(peeraddr1[0] + ':' + str(peeraddr1[1]), peeraddr2)
                    udpsock.sendto(peeraddr1[0] + ':' + str(peeraddr1[1]), peeraddr2)
                    udpsock.sendto(peeraddr1[0] + ':' + str(peeraddr1[1]), peeraddr2)
                    udpsock.sendto(peeraddr2[0] + ':' + str(peeraddr2[1]), peeraddr1)
                    udpsock.sendto(peeraddr2[0] + ':' + str(peeraddr2[1]), peeraddr1)
                    udpsock.sendto(peeraddr2[0] + ':' + str(peeraddr2[1]), peeraddr1)
                    break
        except socket.timeout as error:
            if DEBUG:
                print >> sys.stderr, 'NatTraversal: timeout with peers', error
            udpsock.close()
            break

    udpsock.close()


def tryConnect(coordinator):
    udpsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udpsock.settimeout(5)
    udpsock.sendto('ping', coordinator)
    udpsock.sendto('ping', coordinator)
    udpsock.sendto('ping', coordinator)
    if DEBUG:
        print >> sys.stderr, 'NatTraversal: sending ping to ', coordinator
    while True:
        data = None
        addr = None
        try:
            data, addr = udpsock.recvfrom(1024)
        except socket.timeout as strerror:
            if DEBUG:
                print >> sys.stderr, 'NatTraversal: timeout with coordinator'
            return 'ERR'

        if addr == coordinator:
            if DEBUG:
                print >> sys.stderr, 'NatTraversal: received', data, 'from coordinator'
            break
        if DEBUG:
            print >> sys.stderr, 'NatTraversal: received', data, 'from', addr

    try:
        host, port = data.split(':')
    except:
        print_exc()
        print >> sys.stderr, 'NatCheckMsgHandler: error in received data:', data
        return 'ERR'

    peer = (host, int(port))
    udpsock.sendto('hello', peer)
    udpsock.sendto('hello', peer)
    udpsock.sendto('hello', peer)
    data = None
    addr = None
    while True:
        try:
            data, addr = udpsock.recvfrom(1024)
        except socket.timeout as strerror:
            if DEBUG:
                print >> sys.stderr, 'NatTraversal: first timeout', strerror
                print >> sys.stderr, 'NatTraversal: resend'
            udpsock.sendto('hello', peer)
            udpsock.sendto('hello', peer)
            udpsock.sendto('hello', peer)
            try:
                data, addr = udpsock.recvfrom(1024)
            except socket.timeout as strerror:
                if DEBUG:
                    print >> sys.stderr, 'NatTraversal: second timeout', strerror
                return 'NO'

        if addr == peer:
            break
        if addr[0] == peer[0]:
            peer = addr
            break

    udpsock.sendto('hello', peer)
    udpsock.sendto('hello', peer)
    udpsock.sendto('hello', peer)
    udpsock.close()
    if DEBUG:
        print >> sys.stderr, 'NatTraversal: message from', addr, 'is', data
    return 'YES'
