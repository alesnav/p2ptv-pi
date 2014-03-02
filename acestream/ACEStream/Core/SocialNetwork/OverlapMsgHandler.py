#Embedded file name: ACEStream\Core\SocialNetwork\OverlapMsgHandler.pyo
import sys
from time import time
from traceback import print_exc
from ACEStream.Core.BitTornado.bencode import bencode, bdecode
from ACEStream.Core.BitTornado.BT1.MessageID import *
from ACEStream.Core.Utilities.utilities import *
from ACEStream.Core.Utilities.unicode import str2unicode
DEBUG = False
MIN_OVERLAP_WAIT = 43200.0
ICON_MAX_SIZE = 10240

class OverlapMsgHandler:

    def __init__(self):
        self.recentpeers = {}

    def register(self, overlay_bridge, launchmany):
        if DEBUG:
            print >> sys.stderr, 'socnet: bootstrap: overlap'
        self.mypermid = launchmany.session.get_permid()
        self.session = launchmany.session
        self.peer_db = launchmany.peer_db
        self.superpeer_db = launchmany.superpeer_db
        self.overlay_bridge = overlay_bridge

    def recv_overlap(self, permid, message, selversion):
        try:
            oldict = bdecode(message[1:])
        except:
            print_exc()
            if DEBUG:
                print >> sys.stderr, 'socnet: SOCIAL_OVERLAP: error becoding'
            return False

        if not isValidDict(oldict, permid):
            return False
        self.process_overlap(permid, oldict)
        return True

    def process_overlap(self, permid, oldict):
        self.clean_recentpeers()
        if self.peer_db.hasPeer(permid):
            save_ssocnet_peer(self, permid, oldict, False, False, False)
        elif DEBUG:
            print >> sys.stderr, 'socnet: overlap: peer unknown?! Weird, we just established connection'
        if permid not in self.recentpeers.keys():
            self.recentpeers[permid] = time()
            self.reply_to_overlap(permid)

    def clean_recentpeers(self):
        newdict = {}
        for permid2, t in self.recentpeers.iteritems():
            if t + MIN_OVERLAP_WAIT > time():
                newdict[permid2] = t

        self.recentpeers = newdict

    def reply_to_overlap(self, permid):
        oldict = self.create_oldict()
        self.send_overlap(permid, oldict)

    def initiate_overlap(self, permid, locally_initiated):
        self.clean_recentpeers()
        if not (permid in self.recentpeers.keys() or permid in self.superpeer_db.getSuperPeers()):
            if locally_initiated:
                self.recentpeers[permid] = time()
                self.reply_to_overlap(permid)
            elif DEBUG:
                print >> sys.stderr, 'socnet: overlap: active: he should initiate'
        elif DEBUG:
            print >> sys.stderr, 'socnet: overlap: active: peer recently contacted already'

    def create_oldict(self):
        nickname = self.session.get_nickname().encode('UTF-8')
        persinfo = {'name': nickname}
        iconmime, icondata = self.session.get_mugshot()
        if icondata:
            persinfo.update({'icontype': iconmime,
             'icondata': icondata})
        oldict = {}
        oldict['persinfo'] = persinfo
        return oldict

    def send_overlap(self, permid, oldict):
        try:
            body = bencode(oldict)
            self.overlay_bridge.send(permid, SOCIAL_OVERLAP + body, self.send_callback)
        except:
            if DEBUG:
                print_exc(file=sys.stderr)

    def send_callback(self, exc, permid):
        if exc is not None:
            if DEBUG:
                print >> sys.stderr, 'socnet: SOCIAL_OVERLAP: error sending to', show_permid_short(permid), exc


def isValidDict(oldict, source_permid):
    if not isinstance(oldict, dict):
        if DEBUG:
            print >> sys.stderr, 'socnet: SOCIAL_OVERLAP: not a dict'
        return False
    k = oldict.keys()
    if DEBUG:
        print >> sys.stderr, 'socnet: SOCIAL_OVERLAP: keys', k
    if 'persinfo' not in k or not isValidPersinfo(oldict['persinfo'], False):
        if DEBUG:
            print >> sys.stderr, "socnet: SOCIAL_OVERLAP: key 'persinfo' missing or value wrong type in dict"
        return False
    for key in k:
        if key not in ('persinfo',):
            if DEBUG:
                print >> sys.stderr, 'socnet: SOCIAL_OVERLAP: unknown key', key, 'in dict'
            return False

    return True


def isValidPersinfo(persinfo, signed):
    if not isinstance(persinfo, dict):
        if DEBUG:
            print >> sys.stderr, 'socnet: SOCIAL_*: persinfo: not a dict'
        return False
    k = persinfo.keys()
    if 'name' not in k or not isinstance(persinfo['name'], str):
        if DEBUG:
            print >> sys.stderr, "socnet: SOCIAL_*: persinfo: key 'name' missing or value wrong type"
        return False
    if 'icontype' in k and not isValidIconType(persinfo['icontype']):
        if DEBUG:
            print >> sys.stderr, "socnet: SOCIAL_*: persinfo: key 'icontype' value wrong type"
        return False
    if 'icondata' in k and not isValidIconData(persinfo['icondata']):
        if DEBUG:
            print >> sys.stderr, "socnet: SOCIAL_*: persinfo: key 'icondata' value wrong type"
        return False
    if 'icontype' in k and 'icondata' not in k or 'icondata' in k and 'icontype' not in k:
        if DEBUG:
            print >> sys.stderr, "socnet: SOCIAL_*: persinfo: key 'icontype' without 'icondata' or vice versa"
        return False
    if signed:
        if 'insert_time' not in k or not isinstance(persinfo['insert_time'], int):
            if DEBUG:
                print >> sys.stderr, "socnet: SOCIAL_*: persinfo: key 'insert_time' missing or value wrong type"
            return False
    for key in k:
        if key not in ('name', 'icontype', 'icondata', 'insert_time'):
            if DEBUG:
                print >> sys.stderr, 'socnet: SOCIAL_*: persinfo: unknown key', key, 'in dict'
            return False

    return True


def isValidIconType(type):
    if not isinstance(type, str):
        return False
    idx = type.find('/')
    ridx = type.rfind('/')
    return idx != -1 and idx == ridx


def isValidIconData(data):
    if not isinstance(data, str):
        return False
    return len(data) <= ICON_MAX_SIZE


def save_ssocnet_peer(self, permid, record, persinfo_ignore, hrwidinfo_ignore, ipinfo_ignore):
    if permid == self.mypermid:
        return
    if not persinfo_ignore:
        persinfo = record['persinfo']
        if DEBUG:
            print >> sys.stderr, 'socnet: Got persinfo', persinfo.keys()
            if len(persinfo.keys()) > 1:
                print >> sys.stderr, 'socnet: Got persinfo THUMB THUMB THUMB THUMB'
        name = str2unicode(persinfo['name'])
        if DEBUG:
            print >> sys.stderr, 'socnet: SOCIAL_OVERLAP', show_permid_short(permid), `name`
        if self.peer_db.hasPeer(permid):
            self.peer_db.updatePeer(permid, name=name)
        else:
            self.peer_db.addPeer(permid, {'name': name})
        if 'icontype' in persinfo and 'icondata' in persinfo:
            if DEBUG:
                print >> sys.stderr, 'socnet: saving icon for', show_permid_short(permid), `name`
            self.peer_db.updatePeerIcon(permid, persinfo['icontype'], persinfo['icondata'])
