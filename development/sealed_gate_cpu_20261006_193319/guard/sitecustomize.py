"""CPU fixture sockets may connect only to listeners registered in this process.

Installed as sitecustomize.py in immutable CPU stages. Model/service endpoints,
including 8095, are denied before the original socket connect is called.
"""
import socket
import weakref

FT_CPU_FIXTURE_NETWORK_GUARD = True
_listeners = weakref.WeakValueDictionary()
_listen = socket.socket.listen
_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex


def listen(self, *args, **kwargs):
    result = _listen(self, *args, **kwargs)
    address = self.getsockname()
    if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1') and address[1] != 8095:
        _listeners[(address[0], address[1])] = self
    return result


def allowed(address):
    listener = _listeners.get((address[0],address[1])) if isinstance(address,tuple) and len(address)>=2 else None
    if listener is None or listener.fileno()<0 or not listener.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN):
        raise PermissionError('CPU fixture network guard denied an unregistered endpoint')


def connect(self, address):
    allowed(address)
    return _connect(self, address)


def connect_ex(self, address):
    allowed(address)
    return _connect_ex(self, address)


socket.socket.listen = listen
socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
