"""
The MIT License (MIT)

Copyright (c) 2021-present Pycord Development

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""
import asyncio
import logging

import aiohttp

from .errors import IPCException

_log = logging.getLogger(__name__)

__all__ = "Session"


class Session:
    """Handles getting webserver requests to the bot.
    
    .. versionadded:: 2.0

    Parameters
    ----------
    url
        Returns The URL.
    socket_ini
        Tries to connect to the server.
    request
        Sends requests to the IPC Server

    Raises
    ------
    IPCException
        Exceptions For IPC
    """

    def __init__(
        self, adress="localhost", port=None, multicast_port=20000, bot_key=None
    ):
        self.loop = asyncio.get_event_loop()

        self.adress = adress
        self.port = port
        self.mc_port = multicast_port
        self.bot_key = bot_key
        self.session = None
        self.websocket = None
        self.multicast = None

    @property
    def url(self):
        return "ws://{0.adress}:{1}".format(
            self, self.port if self.port else self.multicast_port
        )

    async def socket_ini(self):
        """Tries to connect to the server."""
        _log.info("IPC: Starting to connect the the server WebSocket...")
        self.session = aiohttp.ClientSession()

        if not self.port:
            _log.debug(
                "IPC: Port was Not provided.",
                self.url,
            )

            self.multicast = await self.session.ws_connect(self.url, autoping=False)

            payload = {"connect": True, "headers": {"Authorization", self.bot_key}}

            _log.debug(f"IPC: Multicast Server {payload}")

            await self.multicast.send_json(payload)
            ipcrec = await self.multicast.receive()

            if ipcrec.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                _log.error(
                    "IPC: Oh No, The WebSocket connection has just closed, Multicast Server is unreachable."
                )
                raise IPCException("IPC: Multicast Connection Failed.")

            port_data = ipcrec.json()
            self.port = port_data["port"]

        self.websocket = await self.session.ws_connect(
            self.url, autoping=False, autoclose=False
        )
        _log.info(f"IPC: Session connected to {self.url}")

        return self.websocket

    async def request(self, endpoint, **kwargs):
        """Sends a request to the IPC server."""
        _log.info(f"IPC: Requesting IPC Server for {endpoint} with {kwargs}")

        if not self.session:
            await self.socket_ini()

        payload = {
            "endpoint": endpoint,
            "data": kwargs,
            "headers": {"Authorization": self.bot_key},
        }
        await self.websocket.send_json(payload)

        _log.debug(f"IPC: Session {payload}")

        ipcrec = await self.websocket.receive()

        _log.debug(f"IPC: Session {ipcrec}")

        if ipcrec.type == aiohttp.WSMsgType.PING:
            _log.info("IPC: Received a ping request")
            await self.websocket.ping()

            return await self.request(endpoint, **kwargs)

        if ipcrec.type == aiohttp.WSMsgType.PONG:
            _log.info("IPC: Received A pong request")

            return await self.request(endpoint, **kwargs)

        if ipcrec.type == aiohttp.WSMsgType.CLOSED:
            _log.exception(
                "IPC: Oh No! It seems like the WebSocket connection was closed, Trying to reconnect now."
            )

            await self.session.close()

            await asyncio.sleep(1)

            await self.socket_ini()

            return await self.request(endpoint, **kwargs)

        return ipcrec.json()
