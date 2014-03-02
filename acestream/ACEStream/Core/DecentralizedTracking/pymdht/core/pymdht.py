#Embedded file name: ACEStream\Core\DecentralizedTracking\pymdht\core\pymdht.pyo
import ptime as time
import controller
import logging, logging_conf

class Pymdht:

    def __init__(self, dht_addr, conf_path, routing_m_mod, lookup_m_mod, private_dht_name, debug_level):
        logging_conf.setup(conf_path, debug_level)
        self.controller = controller.Controller(dht_addr, conf_path, routing_m_mod, lookup_m_mod, private_dht_name)
        self.controller.start()

    def stop(self):
        self.controller.stop()
        time.sleep(0.1)

    def get_peers(self, lookup_id, info_hash, callback_f, bt_port = 0):
        return self.controller.get_peers(lookup_id, info_hash, callback_f, bt_port)

    def remove_torrent(self, info_hash):
        pass

    def print_routing_table_stats(self):
        self.controller.print_routing_table_stats()
