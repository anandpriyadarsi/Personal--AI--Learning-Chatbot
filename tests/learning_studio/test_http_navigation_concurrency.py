"""Browser fixtures must tolerate a speculative/partial HTTP connection."""
import socket
from urllib.parse import urlsplit
from urllib.request import urlopen
from .test_browser import live


def test_speculative_connection_does_not_block_a_reader_navigation(live):
    url,_=live
    address=urlsplit(url)
    idle=socket.create_connection((address.hostname,address.port),timeout=2)
    try:
        # A browser may open a connection before sending the remaining headers.
        idle.sendall(b'GET / HTTP/1.1\r\n')
        with urlopen(url+'/learning',timeout=2) as response:
            assert response.status==200
    finally:
        idle.close()
