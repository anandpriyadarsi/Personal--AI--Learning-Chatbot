"""Inherited Python subprocess outbound-network guard for synthetic validation."""
import ipaddress
import os
import socket

if os.environ.get('ANVAYA_OFFLINE_GUARD')=='1':
    _connect=socket.socket.connect
    _connect_ex=socket.socket.connect_ex
    _getaddrinfo=socket.getaddrinfo
    _sendto=socket.socket.sendto
    def allowed(host):
        if isinstance(host,bytes):host=host.decode('ascii',errors='replace')
        if host=='localhost':return True
        try:return ipaddress.ip_address(str(host).split('%')[0]).is_loopback
        except ValueError:return False
    def guard(address):
        if isinstance(address,tuple) and not allowed(address[0]):
            raise PermissionError('Offline validation denies non-loopback network')
    def connect(self,address):
        guard(address);return _connect(self,address)
    def connect_ex(self,address):
        guard(address);return _connect_ex(self,address)
    def getaddrinfo(host,*args,**kwargs):
        if host is not None and not allowed(host):
            raise PermissionError('Offline validation denies non-loopback DNS')
        return _getaddrinfo(host,*args,**kwargs)
    def sendto(self,data,*args):
        if args:guard(args[-1])
        return _sendto(self,data,*args)
    socket.socket.sendto=sendto
    socket.socket.connect=connect
    socket.socket.connect_ex=connect_ex
    socket.getaddrinfo=getaddrinfo
