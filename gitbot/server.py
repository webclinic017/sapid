from __future__ import annotations

import json
import hashlib
import hmac
from typing import (
    Optional,
    Callable,
    Any,
    Union,
    Dict,
    TYPE_CHECKING
)

from aiohttp import web

if TYPE_CHECKING:
    from aiohttp.web import Request


async def json_or_text(request: Request) -> Union[Dict[str, Any], str]:
    text = await request.text()
    try:
        if request.headers['Content-Type'].startswith('application/json'):
            try:
                data = json.loads(text)
            except json.decoder.JSONDecodeError:
                data = json.loads("{}")
            finally:
                return data
    except KeyError:
        # Thanks Cloudflare. Thanks discord.py :(
        pass

    return text

class WebhookServer:
    def __init__(
        self,
        webhook_secret: str,
        endpoint: str = "/gitbot-interaction-receive"
    ):
        self._app = web.Application()
        self._tcp: Optional[web.TCPSite] = None
        self._runner: Optional[web.AppRunner] = None

        self.wh_secret = webhook_secret
        self.wh_endpoint = endpoint

        self._dispatch: Optional[Callable] = None


    def _generate_hash(self, secret: str, payload: bytes) -> str:
        secret = secret.encode("utf-8")
        # payload = json.dumps(payload)
        # payload = payload.encode("utf-8")
        h = hmac.new(secret, payload, hashlib.sha256)
        digest = h.hexdigest()
        return "sha256=" + digest 
      
    async def receive_interaction(self, request: web.Request) -> web.Response:
        headers = request.headers
        data = await json_or_text(request)
        request_content = await request.read() # if the json parse succeeds, this is also likely to succeed.

        # verify headers
        _hash = self._generate_hash(self.wh_secret, request_content)
        signature = headers["x-hub-signature-256"]
        if not hmac.compare_digest(signature, _hash):
            # the signatures did not match.
            return web.Response(status=401)
            
        await self.handle_interaction(headers, data)

        return web.Response(status=200)

    async def handle_interaction(self, headers: dict, data: dict):
        # TODO: Actually handle interactions.
        self._dispatch("raw_interaction_receive", data)
        event = headers["x-github-event"]

    async def _run(self, host: str, port: int, dispatch: Callable):
        endpoint = self.wh_endpoint
        self._app.router.add_post(endpoint, self.receive_interaction)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._tcp = web.TCPSite(self._runner, host=host, port=str(port))
        await self._tcp.start()
        self._dispatch = dispatch
        self._dispatch("gitbot_tcp_ready", host, port)

    async def cleanup(self):
        if self._tcp:
            await self._tcp.stop()
        if self._runner:
            await self._runner.cleanup()