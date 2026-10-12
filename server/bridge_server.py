import asyncio
import threading
from typing import Callable, Optional, Dict, Any
from aiohttp import web

class BridgeServer:
    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 28710,
                 on_download_request: Optional[Callable[[Dict[str, Any]], None]] = None,
                 on_media_detected: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.host = host
        self.port = port
        self.on_download_request = on_download_request
        self.on_media_detected = on_media_detected

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self.is_running = False

    def _cors_headers(self) -> Dict[str, str]:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }

    async def _handle_options(self, request: web.Request):
        return web.Response(headers=self._cors_headers())

    async def _handle_status(self, request: web.Request):
        return web.json_response({
            "status": "online",
            "app": "RipSync",
            "version": "1.0.0"
        }, headers=self._cors_headers())

    async def _handle_download(self, request: web.Request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400, headers=self._cors_headers())

        url = data.get("url")
        if not url:
            return web.json_response({"error": "Missing URL"}, status=400, headers=self._cors_headers())

        if self.on_download_request:
            self.on_download_request(data)

        return web.json_response({"status": "received", "url": url}, headers=self._cors_headers())

    async def _handle_sniff(self, request: web.Request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400, headers=self._cors_headers())

        if self.on_media_detected:
            self.on_media_detected(data)

        return web.json_response({"status": "media_registered"}, headers=self._cors_headers())

    async def _start_server(self):
        app = web.Application()
        # Routes
        app.router.add_options("/{tail:.*}", self._handle_options)
        app.router.add_get("/api/status", self._handle_status)
        app.router.add_post("/api/download", self._handle_download)
        app.router.add_post("/api/sniff_media", self._handle_sniff)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        self.is_running = True

    def start(self):
        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._start_server())
                self._loop.run_forever()
            except Exception as e:
                print(f"[BridgeServer] Failed to bind/start server: {e}")
            finally:
                try:
                    self._loop.close()
                except Exception:
                    pass

        self._thread = threading.Thread(target=run, daemon=True, name="BridgeServerThread")
        self._thread.start()

    def stop(self):
        if self._loop and self.is_running:
            asyncio.run_coroutine_threadsafe(self._cleanup(), self._loop)

    async def _cleanup(self):
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        self.is_running = False
        if self._loop:
            self._loop.stop()
