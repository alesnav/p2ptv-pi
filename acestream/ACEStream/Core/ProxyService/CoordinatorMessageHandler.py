#Embedded file name: ACEStream\Core\ProxyService\CoordinatorMessageHandler.pyo
import sys
from ACEStream.Core.BitTornado.bencode import bdecode
from ACEStream.Core.BitTornado.BT1.MessageID import *
from ACEStream.Core.Utilities.utilities import show_permid_short
from ACEStream.Core.simpledefs import *
DEBUG = False

class CoordinatorMessageHandler:

    def __init__(self, launchmany):
        self.launchmany = launchmany

    def handleMessage(self, permid, selversion, message):
        type = message[0]
        if DEBUG:
            print >> sys.stderr, 'coordinator message handler: received the message', getMessageName(type), 'from', show_permid_short(permid)
        if type == JOIN_HELPERS:
            return self.got_join_helpers(permid, message, selversion)
        if type == RESIGN_AS_HELPER:
            return self.got_resign_as_helper(permid, message, selversion)
        if type == DROPPED_PIECE:
            return self.got_dropped_piece(permid, message, selversion)
        if type == PROXY_HAVE:
            return self.got_proxy_have(permid, message, selversion)

    def got_join_helpers(self, permid, message, selversion):
        if DEBUG:
            print >> sys.stderr, 'coordinator: network_got_join_helpers: got_join_helpers'
        try:
            infohash = message[1:21]
        except:
            print >> sys.stderr, 'coordinator: network_got_join_helpers: warning - bad data in JOIN_HELPERS'
            return False

        network_got_join_helpers_lambda = lambda : self.network_got_join_helpers(permid, infohash, selversion)
        self.launchmany.rawserver.add_task(network_got_join_helpers_lambda, 0)
        return True

    def network_got_join_helpers(self, permid, infohash, selversion):
        if DEBUG:
            print >> sys.stderr, 'coordinator: network_got_join_helpers: network_got_join_helpers'
        coord_obj = self.launchmany.get_coopdl_role_object(infohash, COOPDL_ROLE_COORDINATOR)
        if coord_obj is None:
            if DEBUG:
                print >> sys.stderr, 'coordinator: network_got_join_helpers: There is no coordinator object associated with this infohash'
            return
        coord_obj.got_join_helpers(permid, selversion)

    def got_resign_as_helper(self, permid, message, selversion):
        if DEBUG:
            print >> sys.stderr, 'coordinator: got_resign_as_helper'
        try:
            infohash = message[1:21]
        except:
            print >> sys.stderr, 'coordinator warning: bad data in RESIGN_AS_HELPER'
            return False

        network_got_resign_as_helper_lambda = lambda : self.network_got_resign_as_helper(permid, infohash, selversion)
        self.launchmany.rawserver.add_task(network_got_resign_as_helper_lambda, 0)
        return True

    def network_got_resign_as_helper(self, permid, infohash, selversion):
        if DEBUG:
            print >> sys.stderr, 'coordinator: network_got_resign_as_helper'
        coord_obj = self.launchmany.get_coopdl_role_object(infohash, COOPDL_ROLE_COORDINATOR)
        if coord_obj is None:
            if DEBUG:
                print >> sys.stderr, 'coordinator: network_got_resign_as_helper: There is no coordinator object associated with this infohash'
            return
        coord_obj.got_resign_as_helper(permid, selversion)

    def got_dropped_piece(self, permid, message, selversion):
        if DEBUG:
            print >> sys.stderr, 'coordinator: got_dropped_piece'
        try:
            infohash = message[1:21]
            piece = bdecode(message[22:])
        except:
            print >> sys.stderr, 'coordinator warning: bad data in DROPPED_PIECE'
            return False

        network_got_dropped_piece_lambda = lambda : self.network_got_dropped_piece(permid, infohash, peice, selversion)
        self.launchmany.rawserver.add_task(network_got_dropped_piece_lambda, 0)
        return True

    def network_got_dropped_piece(self, permid, infohash, piece, selversion):
        if DEBUG:
            print >> sys.stderr, 'coordinator: network_got_dropped_piece'
        coord_obj = self.launchmany.get_coopdl_role_object(infohash, COOPDL_ROLE_COORDINATOR)
        if coord_obj is None:
            if DEBUG:
                print >> sys.stderr, 'coordinator: network_got_dropped_piece: There is no coordinator object associated with this infohash'
            return
        coord_obj.got_dropped_piece_(permid, piece, selversion)

    def got_proxy_have(self, permid, message, selversion):
        if DEBUG:
            print >> sys.stderr, 'coordinator: network_got_proxy_have: got_proxy_have'
        try:
            infohash = message[1:21]
            aggregated_string = bdecode(message[21:])
        except:
            print >> sys.stderr, 'coordinator: network_got_proxy_have: warning - bad data in PROXY_HAVE'
            return False

        network_got_proxy_have_lambda = lambda : self.network_got_proxy_have(permid, infohash, selversion, aggregated_string)
        self.launchmany.rawserver.add_task(network_got_proxy_have_lambda, 0)
        return True

    def network_got_proxy_have(self, permid, infohash, selversion, aggregated_string):
        if DEBUG:
            print >> sys.stderr, 'coordinator: network_got_proxy_have: network_got_proxy_have'
        coord_obj = self.launchmany.get_coopdl_role_object(infohash, COOPDL_ROLE_COORDINATOR)
        if coord_obj is None:
            if DEBUG:
                print >> sys.stderr, 'coordinator: network_got_proxy_have: There is no coordinator object associated with this infohash'
            return
        coord_obj.got_proxy_have(permid, selversion, aggregated_string)
