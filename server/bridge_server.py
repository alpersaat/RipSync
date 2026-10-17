import asyncio
import hmac
import json
import os
import socket
import threading
from typing import Callable, Optional, Dict, Any
from aiohttp import web
from core.logger import get_logger

logger = get_logger("bridge_server")

ALLOWED_ORIGIN_PREFIXES = ("chrome-extension://", "moz-extension://")


def is_port_available(host: str = "127.0.0.1", port: int = 28710) -> bool:
    """
    Checks whether a TCP port is currently available to bind on the host.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.bind((host, port))
            return True
    except OSError:
        return False


def find_available_port(host: str = "127.0.0.1", start_port: int = 28710, max_attempts: int = 20) -> int:
    """
    Finds the first available port starting from start_port up to start_port + max_attempts.
    """
    for p in range(start_port, start_port + max_attempts):
        if is_port_available(host, p):
            return p
    return start_port


def write_extension_config(token: str, port: int = 28710) -> Optional[str]:
    """
    Writes a config.json file inside the unpacked extension directory
    containing the bridge port and authorization token for zero-touch pairing.

    Test ortamında (PYTEST_CURRENT_TEST) gerçek eklenti dizinini bozmamak için
    yazma atlanır; testler kendi tmp dizinini geçer.
    """
    try:
        from core.paths import get_extension_dir
        ext_dir = get_extension_dir()
        if os.path.isdir(ext_dir):
            cfg_path = os.path.join(ext_dir, "config.json")
            data = {
                "bridge_port": port,
                "bridge_token": token
            }
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return cfg_path
    except Exception as e:
        logger.error(f"Uzantı konfigürasyonu yazılamadı: {e}")
    return None


class BridgeServer:
    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 28710,
                 auth_token: Optional[str] = None,
                 on_download_request: Optional[Callable[[Dict[str, Any]], None]] = None,
                 on_media_detected: Optional[Callable[[Dict[str, Any]], None]] = None,
                 auto_fallback: bool = True,
                 on_status_change: Optional[Callable[[str, int, Optional[str]], None]] = None):
        self.host = host
        self.port = int(port)
        self.actual_port = int(port)
        self.auth_token = auth_token
        self.on_download_request = on_download_request
        self.on_media_detected = on_media_detected
        self.auto_fallback = auto_fallback
        self.on_status_change = on_status_change

        self.conflict_detected = False
        self.error_message: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self.is_running = False
        self._ready_event = threading.Event()

    def _is_origin_allowed(self, request: web.Request) -> bool:
        """
        Validates the Origin header.
        - None/Empty: Local/native processes (tests, curl, desktop loopback) allowed.
        - chrome-extension:// or moz-extension://: Browser extension contexts allowed.
        - All external web origins (http://, https://): REJECTED.
        """
        origin = request.headers.get("Origin")
        if not origin:
            return True
        origin_lower = origin.lower()
        return any(origin_lower.startswith(prefix) for prefix in ALLOWED_ORIGIN_PREFIXES)

    def _cors_headers(self, request: web.Request) -> Dict[str, str]:
        """
        Returns CORS headers restricting access strictly to the extension origin.
        Never emits Access-Control-Allow-Origin: *
        """
        origin = request.headers.get("Origin")
        if origin and self._is_origin_allowed(request):
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, X-RipSync-Token",
                "Access-Control-Max-Age": "86400",
            }
        return {}

    def _verify_token(self, request: web.Request) -> bool:
        """
        Verifies that the request carries a valid authorization token.
        Checked in:
        1. X-RipSync-Token header
        2. Authorization: Bearer <token>
        3. ?token=<token> query parameter
        """
        if not self.auth_token:
            return True

        token = request.headers.get("X-RipSync-Token")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()
        if not token:
            token = request.query.get("token")

        if not token:
            return False

        try:
            return hmac.compare_digest(str(token).strip(), str(self.auth_token).strip())
        except Exception:
            return False

    async def _handle_options(self, request: web.Request):
        if not self._is_origin_allowed(request):
            return web.Response(status=403, text="Forbidden origin: web pages cannot access RipSync bridge.")
        return web.Response(headers=self._cors_headers(request))

    async def _handle_status(self, request: web.Request):
        cors = self._cors_headers(request)
        if not self._is_origin_allowed(request):
            return web.json_response({"error": "Forbidden origin"}, status=403, headers=cors)

        if not self._verify_token(request):
            return web.json_response({
                "error": "Unauthorized",
                "message": "Geçerli bir RipSync köprü anahtarı (token) gereklidir."
            }, status=401, headers=cors)

        from core.power_manager import get_global_power_manager
        mgr = get_global_power_manager()
        power_alert = mgr.get_status_dict() if mgr and (mgr.is_active() or mgr.is_suspended) else None

        return web.json_response({
            "status": "online",
            "app": "RipSync",
            "version": "1.0.0",
            "authenticated": True,
            "power_alert": power_alert
        }, headers=cors)

    async def _handle_power_status(self, request: web.Request):
        cors = self._cors_headers(request)
        if not self._is_origin_allowed(request):
            return web.json_response({"error": "Forbidden origin"}, status=403, headers=cors)

        if not self._verify_token(request):
            return web.json_response({"error": "Unauthorized"}, status=401, headers=cors)

        from core.power_manager import get_global_power_manager
        mgr = get_global_power_manager()
        info = mgr.get_status_dict() if mgr else {"is_active": False, "action": "none"}
        return web.json_response(info, headers=cors)

    async def _handle_power_control(self, request: web.Request):
        cors = self._cors_headers(request)
        if not self._is_origin_allowed(request):
            return web.json_response({"error": "Forbidden origin"}, status=403, headers=cors)

        if not self._verify_token(request):
            return web.json_response({"error": "Unauthorized"}, status=401, headers=cors)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400, headers=cors)

        cmd = data.get("command", "").lower()
        seconds = int(data.get("seconds", 300))

        from core.power_manager import get_global_power_manager
        mgr = get_global_power_manager()
        if not mgr:
            return web.json_response({"error": "Power manager not initialized"}, status=503, headers=cors)

        if cmd == "cancel":
            mgr.cancel()
        elif cmd == "suspend":
            mgr.suspend(reason=data.get("reason", "Tarayıcı bildirimi üzerinden askıya alındı"))
        elif cmd == "resume":
            mgr.resume()
        elif cmd == "postpone":
            mgr.postpone(seconds)
        else:
            return web.json_response({"error": f"Unknown power command: {cmd}"}, status=400, headers=cors)

        return web.json_response({
            "status": "ok",
            "command": cmd,
            "power_state": mgr.get_status_dict()
        }, headers=cors)

    async def _handle_download(self, request: web.Request):
        cors = self._cors_headers(request)
        if not self._is_origin_allowed(request):
            return web.json_response({"error": "Forbidden origin: web pages cannot trigger downloads."}, status=403, headers=cors)

        if not self._verify_token(request):
            return web.json_response({"error": "Unauthorized: Invalid or missing bridge token."}, status=401, headers=cors)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400, headers=cors)

        url = data.get("url")
        if not url:
            return web.json_response({"error": "Missing URL"}, status=400, headers=cors)

        if self.on_download_request:
            self.on_download_request(data)

        return web.json_response({"status": "received", "url": url}, headers=cors)

    async def _handle_sniff(self, request: web.Request):
        cors = self._cors_headers(request)
        if not self._is_origin_allowed(request):
            return web.json_response({"error": "Forbidden origin"}, status=403, headers=cors)

        if not self._verify_token(request):
            return web.json_response({"error": "Unauthorized: Invalid or missing bridge token."}, status=401, headers=cors)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400, headers=cors)

        if self.on_media_detected:
            self.on_media_detected(data)

        return web.json_response({"status": "media_registered"}, headers=cors)

    async def _handle_power_alert_page(self, request: web.Request):
        token = request.query.get("token", "")
        # Render a rich, reactive in-browser notification alert
        html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>RipSync - Bilgisayar Kapatma Uyarısı</title>
  <style>
    body {{
      background-color: #1a1b26;
      color: #c0caf5;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      padding: 20px;
      box-sizing: border-box;
    }}
    .card {{
      background-color: #24283b;
      border: 2px solid #f7768e;
      border-radius: 14px;
      padding: 32px;
      max-width: 520px;
      width: 100%;
      text-align: center;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
    }}
    .icon {{ font-size: 54px; margin-bottom: 12px; }}
    h1 {{ color: #f7768e; font-size: 24px; margin: 0 0 12px; }}
    p {{ font-size: 15px; color: #a9b1d6; line-height: 1.5; margin: 0 0 20px; }}
    .counter {{
      font-size: 48px;
      font-weight: 800;
      color: #ff9e64;
      margin: 15px 0;
      font-variant-numeric: tabular-nums;
    }}
    .status-badge {{
      display: inline-block;
      padding: 6px 14px;
      border-radius: 20px;
      background: rgba(247, 118, 142, 0.15);
      color: #f7768e;
      font-weight: 600;
      font-size: 13px;
      margin-bottom: 20px;
    }}
    .btn-group {{
      display: flex;
      gap: 12px;
      justify-content: center;
      margin-top: 20px;
    }}
    button {{
      cursor: pointer;
      font-size: 15px;
      font-weight: bold;
      padding: 12px 24px;
      border-radius: 8px;
      border: none;
      transition: all 0.2s;
    }}
    .btn-cancel {{
      background-color: #f7768e;
      color: #ffffff;
    }}
    .btn-cancel:hover {{ background-color: #ff899d; }}
    .btn-suspend {{
      background-color: #7aa2f7;
      color: #1a1b26;
    }}
    .btn-suspend:hover {{ background-color: #89b4fa; }}
  </style>
</head>
<body>
  <div class="card" id="alertCard">
    <div class="icon" id="statusIcon">🛑</div>
    <h1 id="alertTitle">Bilgisayar Kapatılıyor!</h1>
    <div class="status-badge" id="badge">Kuyruk Tamamlandı</div>
    <p id="alertDesc">RipSync indirme kuyruğundaki tüm görevler tamamlandı. Açık işlerinizi kaybetmemek için işlemi iptal edebilir veya askıya alabilirsiniz.</p>
    <div class="counter" id="countdownSec">--</div>
    <div class="btn-group">
      <button class="btn-cancel" onclick="sendCmd('cancel')">🛑 Kapatmayı İptal Et</button>
      <button class="btn-suspend" onclick="sendCmd('suspend')">⏸️ İşlemi Askıya Al</button>
    </div>
  </div>

  <script>
    const token = "{token}";
    async function sendCmd(command) {{
      try {{
        const resp = await fetch("/api/power_control", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json", "X-RipSync-Token": token }},
          body: JSON.stringify({{ command, reason: "Tarayıcı sayfasından durduruldu" }})
        }});
        if (resp.ok) {{
          updateUI();
        }}
      }} catch (e) {{
        console.error(e);
      }}
    }}

    async function updateUI() {{
      try {{
        const resp = await fetch("/api/power_status?token=" + encodeURIComponent(token));
        if (!resp.ok) return;
        const data = await resp.json();
        const cnt = document.getElementById("countdownSec");
        const title = document.getElementById("alertTitle");
        const desc = document.getElementById("alertDesc");
        const badge = document.getElementById("badge");
        const icon = document.getElementById("statusIcon");

        if (data.is_suspended) {{
          badge.textContent = "İşlem Askıya Alındı";
          badge.style.background = "rgba(122, 162, 247, 0.2)";
          badge.style.color = "#7aa2f7";
          title.textContent = "Kapatma Askıya Alındı";
          title.style.color = "#7aa2f7";
          desc.textContent = data.suspend_reason || "İşlem askıya alındı. Bilgisayarınız kapatılmayacak.";
          cnt.textContent = "⏸️ Askıda";
          cnt.style.color = "#7aa2f7";
        }} else if (!data.is_active) {{
          badge.textContent = "İptal Edildi";
          title.textContent = "Eylem İptal Edildi";
          title.style.color = "#9ece6a";
          desc.textContent = "Bilgisayar kapatma / uyku işlemi iptal edildi. Rahatça çalışmaya devam edebilirsiniz.";
          cnt.textContent = "✅ Güvende";
          cnt.style.color = "#9ece6a";
          icon.textContent = "🛡️";
        }} else {{
          cnt.textContent = data.remaining_seconds + " saniye";
          const actName = data.action === "shutdown" ? "Kapatılıyor" : "Uyku Moduna Geçiliyor";
          title.textContent = "Bilgisayar " + actName + "!";
        }}
      }} catch (e) {{
        console.error(e);
      }}
    }}

    setInterval(updateUI, 1000);
    updateUI();
  </script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def _start_server(self, target_port: int):
        app = web.Application()
        # Routes
        app.router.add_options("/{tail:.*}", self._handle_options)
        app.router.add_get("/api/status", self._handle_status)
        app.router.add_get("/api/power_status", self._handle_power_status)
        app.router.add_post("/api/power_control", self._handle_power_control)
        app.router.add_get("/power_alert", self._handle_power_alert_page)
        app.router.add_post("/api/download", self._handle_download)
        app.router.add_post("/api/sniff_media", self._handle_sniff)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, target_port)
        await self._site.start()
        self.actual_port = target_port
        self.is_running = True

    def start(self, wait_for_ready: bool = True, timeout: float = 3.0) -> bool:
        if self.is_running:
            return True

        target_port = self.port
        self.conflict_detected = False
        self.error_message = None
        self._ready_event.clear()

        # Check port availability before starting
        if not is_port_available(self.host, target_port):
            if self.auto_fallback:
                alt_port = find_available_port(self.host, start_port=target_port, max_attempts=25)
                if alt_port != target_port:
                    print(f"[BridgeServer] Port {target_port} kullanımda. Otomatik olarak {alt_port} portuna geçiliyor.")
                    self.conflict_detected = True
                    target_port = alt_port
                else:
                    self.conflict_detected = True
                    self.error_message = f"Port {target_port} kullanımda ve boş alternatif port bulunamadı."
                    print(f"[BridgeServer] {self.error_message}")
                    if self.on_status_change:
                        self.on_status_change("conflict", target_port, self.error_message)
                    return False
            else:
                self.conflict_detected = True
                self.error_message = f"Port {target_port} kullanımda (Port çakışması)."
                print(f"[BridgeServer] {self.error_message}")
                if self.on_status_change:
                    self.on_status_change("conflict", target_port, self.error_message)
                return False

        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._start_server(target_port))

                # Update unpacked extension config so the browser extension pairs seamlessly
                if self.auth_token:
                    write_extension_config(token=self.auth_token, port=self.actual_port)

                self._ready_event.set()

                if self.conflict_detected:
                    msg = f"Port {self.port} kullanımda olduğu için köprü {self.actual_port} portunda başlatıldı."
                    if self.on_status_change:
                        self.on_status_change("running_fallback", self.actual_port, msg)
                else:
                    msg = f"Köprü sunucusu aktif (Port: {self.actual_port})"
                    if self.on_status_change:
                        self.on_status_change("running", self.actual_port, msg)

                self._loop.run_forever()
            except Exception as e:
                logger.error(f"Köprü sunucusu port {target_port} üzerinde başlatılamadı: {e}", exc_info=True)
                self.is_running = False
                self.error_message = str(e)
                self._ready_event.set()
                if self.on_status_change:
                    status_type = "conflict" if isinstance(e, OSError) else "error"
                    self.on_status_change(status_type, target_port, f"Sunucu başlatılamadı: {e}")
            finally:
                try:
                    self._loop.close()
                except Exception as e:
                    logger.debug(f"Event loop kapatma uyarısı: {e}")

        self._thread = threading.Thread(target=run, daemon=True, name="BridgeServerThread")
        self._thread.start()

        if wait_for_ready:
            self._ready_event.wait(timeout=timeout)

        return self.is_running

    def stop(self, timeout: float = 2.0):
        if self._loop and self.is_running:
            try:
                fut = asyncio.run_coroutine_threadsafe(self._cleanup(), self._loop)
                try:
                    fut.result(timeout=timeout)
                except Exception:
                    if self._loop.is_running():
                        self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception as e:
                logger.debug(f"Köprü sunucusu durdurma uyarısı: {e}")
        self.is_running = False
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            self._thread.join(timeout=timeout)
        if self.on_status_change:
            try:
                self.on_status_change("stopped", self.actual_port, "Köprü sunucusu durduruldu.")
            except Exception:
                pass

    async def _cleanup(self):
        try:
            if self._site:
                await self._site.stop()
            if self._runner:
                await self._runner.cleanup()
        except Exception as e:
            logger.warning(f"Köprü sunucusu temizleme uyarısı: {e}")
        finally:
            self.is_running = False
            if self._loop and self._loop.is_running():
                self._loop.stop()

    def restart(self, new_port: Optional[int] = None, wait_for_ready: bool = True) -> bool:
        """
        Safely stops the bridge server and restarts it, optionally on a new port.
        """
        self.stop()
        if new_port is not None:
            self.port = int(new_port)
            self.actual_port = int(new_port)
        self.conflict_detected = False
        self.error_message = None
        return self.start(wait_for_ready=wait_for_ready)
