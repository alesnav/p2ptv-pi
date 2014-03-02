#Embedded file name: ACEStream\Core\DecentralizedTracking\pymdht\core\utils.pyo
import socket

class AddrError(Exception):
    pass


class IP6Addr(AddrError):
    pass


def compact_port(port):
    return ''.join([ chr(port_byte_int) for port_byte_int in divmod(port, 256) ])


def compact_addr(addr):
    return socket.inet_aton(addr[0]) + compact_port(addr[1])


compact_peer = compact_addr
