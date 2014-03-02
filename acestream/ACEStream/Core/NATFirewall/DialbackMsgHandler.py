#Embedded file name: ACEStream\Core\NATFirewall\DialbackMsgHandler.pyo
import sys
from time import time
from random import shuffle
from traceback import print_exc, print_stack
from threading import currentThread
from ACEStream.Core.BitTornado.BT1.MessageID import *
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
from ACEStream.Core.NATFirewall.ReturnConnHandler import ReturnConnHandler
from ACEStream.Core.Overlay.SecureOverlay import OLPROTO_VER_THIRD
from ACEStream.Core.Utilities.utilities import *
from ACEStream.Core.simpledefs import *
DEBUG = False
REPLY_WAIT = 60
REPLY_VALIDITY = 2 * 24 * 3600.0
REPLY_HARD_LIMIT = 500
PEERS_TO_AGREE = 4
YOURIP_PEERS_TO_AGREE = 16
PEERS_TO_ASK = 7
MAX_TRIES = 35

class DialbackMsgHandler():
    __single = None

    def __init__(self):
        if DialbackMsgHandler.__single:
            raise RuntimeError, 'DialbackMsgHandler is singleton'
        DialbackMsgHandler.__single = self
        self.peers_asked = {}
        self.myips = []
        self.consensusip = None
        self.fromsuperpeer = False
        self.dbreach = False
        self.btenginereach = False
        self.ntries = 0
        self.active = False
        self.rawserver = None
        self.launchmany = None
        self.peer_db = None
        self.superpeer_db = None
        self.trust_superpeers = None
        self.old_ext_ip = None
        self.myips_according_to_yourip = []
        self.returnconnhand = ReturnConnHandler.getInstance()

    def getInstance(*args, **kw):
        if DialbackMsgHandler.__single is None:
            DialbackMsgHandler(*args, **kw)
        return DialbackMsgHandler.__single

    getInstance = staticmethod(getInstance)

    def register(self, overlay_bridge, launchmany, rawserver, config):
        self.overlay_bridge = overlay_bridge
        self.rawserver = rawserver
        self.launchmany = launchmany
        self.peer_db = launchmany.peer_db
        self.superpeer_db = launchmany.superpeer_db
        self.active = (config['dialback_active'],)
        self.trust_superpeers = config['dialback_trust_superpeers']
        self.returnconnhand.register(self.rawserver, launchmany.multihandler, launchmany.listen_port, config['overlay_max_message_length'])
        self.returnconnhand.register_conns_callback(self.network_handleReturnConnConnection)
        self.returnconnhand.register_recv_callback(self.network_handleReturnConnMessage)
        self.returnconnhand.start_listening()
        self.old_ext_ip = launchmany.get_ext_ip()

    def register_yourip(self, launchmany):
        self.launchmany = launchmany

    def olthread_handleSecOverlayConnection(self, exc, permid, selversion, locally_initiated):
        if DEBUG:
            print >> sys.stderr, 'dialback: handleConnection', exc, 'v', selversion, 'local', locally_initiated
        if selversion < OLPROTO_VER_THIRD:
            return True
        if exc is not None:
            try:
                del self.peers_asked[permid]
            except:
                if DEBUG:
                    print >> sys.stderr, "dialback: handleConnection: Got error on connection that we didn't ask for dialback"

            return
        if self.consensusip is None:
            self.ntries += 1
            if self.ntries >= MAX_TRIES:
                if DEBUG:
                    print >> sys.stderr, 'dialback: tried too many times, giving up'
                return True
            if self.dbreach or self.btenginereach:
                self.launchmany.set_activity(NTFY_ACT_GET_EXT_IP_FROM_PEERS)
            else:
                self.launchmany.set_activity(NTFY_ACT_REACHABLE)
            if self.active:
                self.olthread_attempt_request_dialback(permid)
        return True

    def olthread_attempt_request_dialback(self, permid):
        if DEBUG:
            print >> sys.stderr, 'dialback: attempt dialback request', show_permid_short(permid)
        dns = self.olthread_get_dns_from_peerdb(permid)
        ipinuse = False
        threshold = time() - REPLY_WAIT
        newdict = {}
        for permid2, peerrec in self.peers_asked.iteritems():
            if peerrec['reqtime'] >= threshold:
                newdict[permid2] = peerrec
            if peerrec['dns'][0] == dns[0]:
                ipinuse = True

        self.peers_asked = newdict
        if permid in self.peers_asked or ipinuse or len(self.peers_asked) >= PEERS_TO_ASK:
            if DEBUG:
                pipa = permid in self.peers_asked
                lpa = len(self.peers_asked)
                print >> sys.stderr, 'dialback: No request made to', show_permid_short(permid), 'already asked', pipa, 'IP in use', ipinuse, 'nasked', lpa
            return
        dns = self.olthread_get_dns_from_peerdb(permid)
        peerrec = {'dns': dns,
         'reqtime': time()}
        self.peers_asked[permid] = peerrec
        self.overlay_bridge.connect(permid, self.olthread_request_connect_callback)

    def olthread_request_connect_callback(self, exc, dns, permid, selversion):
        if exc is None:
            if selversion >= OLPROTO_VER_THIRD:
                self.overlay_bridge.send(permid, DIALBACK_REQUEST + '', self.olthread_request_send_callback)
            elif DEBUG:
                print >> sys.stderr, 'dialback: DIALBACK_REQUEST: peer speaks old protocol, weird', show_permid_short(permid)
        elif DEBUG:
            print >> sys.stderr, 'dialback: DIALBACK_REQUEST: error connecting to', show_permid_short(permid), exc

    def olthread_request_send_callback(self, exc, permid):
        if exc is not None:
            if DEBUG:
                print >> sys.stderr, 'dialback: DIALBACK_REQUEST error sending to', show_permid_short(permid), exc

    def olthread_handleSecOverlayMessage(self, permid, selversion, message):
        t = message[0]
        if t == DIALBACK_REQUEST:
            if DEBUG:
                print >> sys.stderr, 'dialback: Got DIALBACK_REQUEST', len(message), show_permid_short(permid)
            return self.olthread_process_dialback_request(permid, message, selversion)
        else:
            if DEBUG:
                print >> sys.stderr, 'dialback: UNKNOWN OVERLAY MESSAGE', ord(t)
            return False

    def olthread_process_dialback_request(self, permid, message, selversion):
        if len(message) != 1:
            if DEBUG:
                print >> sys.stderr, 'dialback: DIALBACK_REQUEST: message too big'
            return False
        dns = self.olthread_get_dns_from_peerdb(permid)
        self.returnconnhand.connect_dns(dns, self.network_returnconn_reply_connect_callback)
        return True

    def network_returnconn_reply_connect_callback(self, exc, dns):
        if not currentThread().getName().startswith('NetworkThread'):
            print >> sys.stderr, 'dialback: network_returnconn_reply_connect_callback: called by', currentThread().getName(), ' not NetworkThread'
            print_stack()
        if exc is None:
            hisip = str(dns[0])
            try:
                reply = bencode(hisip)
                if DEBUG:
                    print >> sys.stderr, 'dialback: DIALBACK_REPLY: sending to', dns
                self.returnconnhand.send(dns, DIALBACK_REPLY + reply, self.network_returnconn_reply_send_callback)
            except:
                print_exc()
                return False

        elif DEBUG:
            print >> sys.stderr, 'dialback: DIALBACK_REPLY: error connecting to', dns, exc

    def network_returnconn_reply_send_callback(self, exc, dns):
        if DEBUG:
            print >> sys.stderr, 'dialback: DIALBACK_REPLY: send callback:', dns, exc
        if exc is not None:
            if DEBUG:
                print >> sys.stderr, 'dialback: DIALBACK_REPLY: error sending to', dns, exc

    def network_handleReturnConnConnection(self, exc, dns, locally_initiated):
        if DEBUG:
            print >> sys.stderr, 'dialback: DIALBACK_REPLY: Got connection from', dns, exc

    def network_handleReturnConnMessage(self, dns, message):
        t = message[0]
        if t == DIALBACK_REPLY:
            if DEBUG:
                print >> sys.stderr, 'dialback: Got DIALBACK_REPLY', len(message), dns
            olthread_process_dialback_reply_lambda = lambda : self.olthread_process_dialback_reply(dns, message)
            self.overlay_bridge.add_task(olthread_process_dialback_reply_lambda, 0)
            self.returnconnhand.close(dns)
            return True
        else:
            if DEBUG:
                print >> sys.stderr, 'dialback: UNKNOWN RETURNCONN MESSAGE', ord(t)
            return False

    def olthread_process_dialback_reply(self, dns, message):
        self.dbreach = True
        permid = self.olthread_permid_of_asked_peer(dns)
        if permid is None:
            if DEBUG:
                print >> sys.stderr, "dialback: DIALBACK_REPLY: Got reply from peer I didn't ask", dns
            return False
        del self.peers_asked[permid]
        try:
            myip = bdecode(message[1:])
        except:
            print_exc()
            if DEBUG:
                print >> sys.stderr, 'dialback: DIALBACK_REPLY: error becoding'
            return False

        if not isValidIP(myip):
            if DEBUG:
                print >> sys.stderr, 'dialback: DIALBACK_REPLY: invalid IP'
            return False
        if self.trust_superpeers:
            superpeers = self.superpeer_db.getSuperPeers()
            if permid in superpeers:
                if DEBUG:
                    print >> sys.stderr, 'dialback: DIALBACK_REPLY: superpeer said my IP address is', myip, 'setting it to that'
                self.consensusip = myip
                self.fromsuperpeer = True
        else:
            self.myips, consensusip = tally_opinion(myip, self.myips, PEERS_TO_AGREE)
            if self.consensusip is None:
                self.consensusip = consensusip
        if self.consensusip is not None:
            self.launchmany.dialback_got_ext_ip_callback(self.consensusip)
            if DEBUG:
                print >> sys.stderr, 'dialback: DIALBACK_REPLY: I think my IP address is', self.old_ext_ip, 'others say', self.consensusip, ', setting it to latter'
        self.launchmany.dialback_reachable_callback()
        return True

    def network_btengine_reachable_callback(self):
        if self.launchmany is not None:
            self.launchmany.dialback_reachable_callback()
        self.btenginereach = True

    def isConnectable(self):
        return self.dbreach or self.btenginereach

    def network_btengine_extend_yourip(self, myip):
        self.myips_according_to_yourip, yourip_consensusip = tally_opinion(myip, self.myips_according_to_yourip, YOURIP_PEERS_TO_AGREE)
        if DEBUG:
            print >> sys.stderr, 'dialback: yourip: someone said my IP is', myip
        if yourip_consensusip is not None:
            self.launchmany.yourip_got_ext_ip_callback(yourip_consensusip)
            if DEBUG:
                print >> sys.stderr, 'dialback: yourip: I think my IP address is', self.old_ext_ip, 'others via EXTEND hs say', yourip_consensusip, 'recording latter as option'

    def olthread_get_dns_from_peerdb(self, permid):
        dns = None
        peer = self.peer_db.getPeer(permid)
        if peer:
            ip = self.to_real_ip(peer['ip'])
            dns = (ip, int(peer['port']))
        return dns

    def to_real_ip(self, hostname_or_ip):
        ip = None
        try:
            socket.inet_aton(hostname_or_ip)
            ip = hostname_or_ip
        except:
            try:
                ip = socket.gethostbyname(hostname_or_ip)
            except:
                print_exc()

        return ip

    def olthread_permid_of_asked_peer(self, dns):
        for permid, peerrec in self.peers_asked.iteritems():
            if peerrec['dns'] == dns:
                return permid


def tally_opinion(myip, oplist, requiredquorum):
    consensusip = None
    oplist.append([myip, time()])
    if len(oplist) > REPLY_HARD_LIMIT:
        del oplist[0]
    if DEBUG:
        print >> sys.stderr, 'dialback: DIALBACK_REPLY: peer said I have IP address', myip
    newlist = []
    threshold = time() - REPLY_VALIDITY
    for pair in oplist:
        if pair[1] >= threshold:
            newlist.append(pair)

    oplist = newlist
    opinions = {}
    for pair in oplist:
        ip = pair[0]
        if ip not in opinions:
            opinions[ip] = 1
        else:
            opinions[ip] += 1

    for o in opinions:
        if opinions[o] >= requiredquorum:
            if consensusip is None:
                consensusip = o
                if DEBUG:
                    print >> sys.stderr, 'dialback: DIALBACK_REPLY: Got consensus on my IP address being', consensusip

    return (oplist, consensusip)
