"""
discord.ext.ipc
~~~~~~~~~~~~~~~
Extension module to facilitate the creation of IPC Sessions.

:copyright: 2021-present Pycord Development
:license: MIT, see LICENSE for more details.
"""

from .core import Session
from .errors import IPCException
from .server import Server, IPCServerResponse, make
