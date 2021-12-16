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
import logging

import aiohttp.web

from .errors import IPCException

_log = logging.getLogger(__name__)

__all__ = ("IPCServerResponse", "Server", "route")


def route(name=None):
    def decorator(func):
        if not name:
            Server.ROUTES[func.__name__] = func
        else:
            Server.ROUTES[name] = func

        return func

    return decorator


class IPCServerResponse:
    """Responds to endpoint requests

    .. versionadded:: 2.0
    """

    def __init__(self, data):
        self._json = data
        self.length = len(data)

        self.endpoint = data["endpoint"]

        for key, value in data["data"].items():
            setattr(self, key, value)

    def __repr__(self):
        return "<IPCServerResponse length={0.length}>".format(self)

    def __str__(self):
        return self.__repr__()


class Server:
    """The IPC Server.
   
    .. versionadded:: 2.0

    Parameters
    ----------
    Route
        Registers a coroutine as an endpoint when you have an instance of :class:`Server`
    update_endpoints
        Called internally to update the endpoints for :class:`Cog` routes.
    handle_request
        Handles WebSocket requests from :class:`Session`
    handle_multicast
        Handles multicasting websocket requests from :class:`Session`
    start
        Starts The IPC Process.
    
    Raises
    ------
    IPCException
        Exceptions For IPC
    """

    ROUTES = {}

    def __init__(
        self,
        bot,
        adress="localhost",
        port=7385,
        bot_key=None,
        toggle_multicast=True,
        multicast_port=20000,
    ):
        self.bot = bot
        self.loop = bot.loop

        self.adress = adress
        self.port = port
        self.bot_key = bot_key
        self.toggle_multicast = toggle_multicast
        self.multicast_port = multicast_port

        self._server = None
        self._multicast_server = None

        self.endpoints = {}

    def route(self, name=None):
        """Registers a coroutine as an endpoint when
        you have access to an instance of :class:`Server`

        .. versionadded:: 2.0
        """

        def decorator(func):
            if not name:
                self.endpoints[func.__name__] = func
            else:
                self.endpoints[name] = func

            return func

        return decorator

    def update_endpoints(self):
        """Called internally to update the endpoints for :class:`Cog` routes.

        .. versionadded:: 2.0
        """
        self.endpoints = {**self.endpoints, **self.ROUTES}

        self.ROUTES = {}

    async def handle_request(self, request):
        """Handles WebSocket requests from :class:`Session`

        .. versionadded:: 2.0

        Parameters
        ----------
        request: :class:`~aiohttp.web.Request`
            The request made by the client, parsed by aiohttp.
        """
        self.update_endpoints()

        _log.info("IPC: Initiating Server...")

        websocket = aiohttp.web.WebSocketResponse()
        await websocket.prepare(request)

        async for message in websocket:
            request = message.json()

            _log.debug(f"IPC: Server {request}")

            endpoint = request.get("endpoint")

            headers = request.get("headers")

            if not headers or headers.get("Authorization") != self.bot_key:
                _log.info("IPC: Unauthorized request recived!")
                response = {
                    "error": "IPC-Server: Invalid or no token provided.",
                    "code": 403,
                }
            else:
                if not endpoint or endpoint not in self.endpoints:
                    _log.info("IPC: Recieved invalid or no endpoint")
                    response = {
                        "error": "IPC-Server: Invalid or no endpoint given.",
                        "code": 400,
                    }

                else:
                    server_response = IPCServerResponse
                    try:
                        attempted_cls = self.bot.cogs.get(
                            self.endpoints[endpoint].__qualname__.split(".")[0]
                        )

                        if attempted_cls:
                            arguments = (attempted_cls, server_response)
                        else:
                            arguments = (server_response,)

                    except AttributeError:
                        arguments = (server_response,)

                    try:
                        ret = await self.endpoints[endpoint](*arguments)
                        response = ret
                    except Exception as error:
                        _log.error(
                            f"Received error while executing {endpoint} with {request}"
                        )
                        self.bot.dispatch("ipc_error", endpoint, error)

                        response = {
                            "error": "IPC route raised error of type {}".format(
                                type(error).__name__
                            ),
                            "code": 500,
                        }

            try:
                await websocket.send_json(response)
                _log.debug(f"IPC: Server {response}")

            except TypeError as error:
                if str(error).startswith("Object of type") and str(error).endswith(
                    "is not JSON serialable"
                ):
                    error_response = (
                        "IPC route returned values which are not able to be sent over sockets."
                        " If you are trying to send a pycord object,"
                        " please only send the data you need."
                    )
                    _log.error(error_response)

                    response = {"error": error_response, "code": 500}

                    await websocket.send_json(response)
                    _log.debug(f"IPC: Server {response}")

                    raise IPCException(error_response)

    async def handle_multicast(self, request):
        """Handles multicasting websocket requests from :class:`Session`

        .. versionadded:: 2.0

        Parameters
        ----------
        request: :class:`~aiohttp.web.Request`
            The request made by the client, parsed by aiohttp.
        """
        _log.info("IPC: Initializing Multicast Server")
        websocket = aiohttp.web.WebSocketResponse()
        await websocket.prepare(request)

        async for message in websocket:
            request = message.json()
            _log.debug(f"Multicast Server {request}")

            headers = request.get("headers")

            if not headers or headers.get("Authorization") != self.bot_key:
                response = {"error": "IPC-Server: Invalid or no token provided.", "code": 403}
            else:
                response = {
                    "message": "Connection Success!",
                    "port": self.port,
                    "code": 200,
                }

            _log.debug(f"Multicast Server {response}")

            await websocket.send_bytes(response)

    async def __start(self, application, port):
        runner = aiohttp.web.AppRunner(application)
        await runner.setup()

        site = aiohttp.web.TCPSite(runner, self.adress, port)
        await site.start()

    # There is no real reason for this to be async for now but maybe in use later
    async def start(self):
        """Starts The IPC Process.

        .. versionadded:: 2.0
        """
        self.bot.dispatch("ipc_ready")

        self._server = aiohttp.web.Application()
        self._server.router.add_route("GET", "/", self.handle_request)

        if self.toggle_multicast:
            self._multicast_server = aiohttp.web.Application()
            self._multicast_server.add_route("GET", "/", self.handle_multicast)

            self.loop.run_until_complete(
                self.__start(self._multicast_server, self.multicast_port)
            )

        self.loop.run_until_complete(self.__start(self._server, self.port))
