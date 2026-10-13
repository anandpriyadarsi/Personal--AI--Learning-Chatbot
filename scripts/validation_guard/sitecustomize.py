"""Validator child processes allow only loopback sockets, never paid providers."""
import ipaddress
import socket


_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex


def _local(address):
    if not isinstance(address, tuple):
        return False
    host = address[0]
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _local(address):
        raise RuntimeError('External network forbidden in synthetic validation')
    return _connect(self, address)


def connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _local(address):
        raise RuntimeError('External network forbidden in synthetic validation')
    return _connect_ex(self, address)


socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
