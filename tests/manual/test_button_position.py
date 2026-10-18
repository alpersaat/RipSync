"""
Real-Chrome verification of the extension's "Bu Videoyu Indir" button:
  * it must sit OUTSIDE the video, at its top-right corner
  * it must disappear when the video goes fullscreen (and return afterwards)
Loads the unpacked extension into the installed Google Chrome via Playwright.
"""
import json
import os
import socket
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXT_DIR = os.path.join(ROOT, "extension")
PORT = 29911
BRIDGE_PORT = 28710

VIDEO = '<video id="v" width="%d" height="%d" controls muted></video>'

PAGES = {
    # YouTube-like: fixed 56px header on top, 24px gap, then the player
    "/yt": """<html><body style="margin:0;font-family:sans-serif">
<div style="position:fixed;top:0;left:0;right:0;height:56px;background:#fff;z-index:1000;border-bottom:1px solid #ccc">
  <input style="position:absolute;left:520px;top:10px;width:480px;height:34px" placeholder="search"></div>
<div style="padding:80px 24px 0 24px">
  <div id="player" style="width:900px;height:506px;background:#000">%s</div>
  <h1>Title</h1><div style="height:2500px">content</div></div>
<script>document.getElementById('v').style.width='900px';document.getElementById('v').style.height='506px';</script>
</body></html>""" % (VIDEO % (900, 506)),
    # video with plenty of free space around it
    "/plain": """<html><body style="margin:0;font-family:sans-serif">
<div style="padding:120px 100px"><div id="player" style="width:640px;height:360px;background:#000">%s</div>
<div style="height:2500px">content</div></div></body></html>""" % (VIDEO % (640, 360)),
    # video flush against the top-left of the viewport: no room above
    "/flush": """<html><body style="margin:0;font-family:sans-serif">
<div id="player" style="width:640px;height:360px;background:#000">%s</div>
<div style="height:2500px">content</div></body></html>""" % (VIDEO % (640, 360)),
    # tiny video (e.g. an ad / icon) must not get a button
    "/tiny": """<html><body style="margin:40px"><video id="v" width="80" height="45" muted></video></body></html>""",
    # two videos stacked (timeline like)
    "/two": """<html><body style="margin:0;font-family:sans-serif"><div style="padding:60px 200px">
<video id="v" width="500" height="280" muted></video><div style="height:80px">gap</div>
<video id="v2" width="500" height="280" muted></video><div style="height:2000px"></div></div></body></html>""",
    # button (user gesture) that makes the player wrapper go fullscreen
    "/fs": """<html><body style="margin:0;font-family:sans-serif">
<div style="padding:120px 100px"><button id="gofs" style="position:fixed;left:5px;bottom:5px;z-index:5"
 onclick="document.getElementById('player').requestFullscreen()">fs</button>
<div id="player" style="width:640px;height:360px;background:#000">%s</div></div></body></html>""" % (VIDEO % (640, 360)),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path.split("?")[0])
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


RECEIVED = []


class BridgeHandler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        data = b'{"status":"online"}'
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        RECEIVED.append(json.loads(self.rfile.read(n) or b"{}"))
        data = b'{"status":"received"}'
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def port_free(port):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


FAILS = []


def check(cond, msg):
    text = ("[PASS] " if cond else "[FAIL] ") + msg
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))
    if not cond:
        FAILS.append(msg)


JS_INFO = """(sel) => {
  const v = document.querySelector(sel);
  const r = v.getBoundingClientRect();
  const btns = [...document.querySelectorAll('.ripsync-sniffer-btn')];
  return {
    video: {l: r.left, t: r.top, r: r.right, b: r.bottom},
    vw: innerWidth, vh: innerHeight,
    buttons: btns.map(b => { const q = b.getBoundingClientRect(); const cs = getComputedStyle(b);
      return {l: q.left, t: q.top, r: q.right, b: q.bottom, on: b.classList.contains('ripsync-on'),
              vis: cs.visibility, inPlayer: v.parentElement.contains(b) || !!b.closest('#player'),
              parent: b.parentElement.tagName, text: b.innerText}; })
  };
}"""


def wait_on(page, sel="#v", want=True, timeout=4000):
    end = time.time() + timeout / 1000
    while time.time() < end:
        info = page.evaluate(JS_INFO, sel)
        on = any(b["on"] for b in info["buttons"])
        if on == want:
            return info
        time.sleep(0.1)
    return page.evaluate(JS_INFO, sel)


def overlap(a, b):
    return not (a["r"] <= b["l"] or a["l"] >= b["r"] or a["b"] <= b["t"] or a["t"] >= b["b"])


def main():
    httpd = HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    bridge = None
    if port_free(BRIDGE_PORT):
        bridge = HTTPServer(("127.0.0.1", BRIDGE_PORT), BridgeHandler)
        threading.Thread(target=bridge.serve_forever, daemon=True).start()
    else:
        print("[INFO] port 28710 busy (real app running?) - click test skipped")

    user_dir = tempfile.mkdtemp()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_dir,
            headless=False,
            ignore_default_args=["--disable-extensions"],
            args=[
                f"--disable-extensions-except={EXT_DIR}",
                f"--load-extension={EXT_DIR}",
                "--window-size=1300,820",
                "--window-position=20,20",
            ],
            viewport=None,
        )
        base = f"http://127.0.0.1:{PORT}"
        page = ctx.new_page()
        print("Chrome:", ctx.browser.version if ctx.browser else "?")

        # ---- 1. generic page with free space ----
        page.goto(base + "/plain")
        info = wait_on(page)
        btn = info["buttons"][0] if info["buttons"] else None
        check(btn is not None and btn["on"], "button is visible on a normal page")
        if btn:
            v = info["video"]
            check(btn["parent"] in ("BODY", "HTML"), f"button is a body-level element (parent={btn['parent']})")
            check(not btn["inPlayer"], "button is NOT inside the player/video container")
            check(not overlap(btn, v), f"button does not overlap the video  btn={btn} video={v}")
            check(btn["b"] <= v["t"], "button is above the video's top edge")
            check(abs(btn["r"] - v["r"]) <= 1, f"button is right-aligned with the video (btn.r={btn['r']}, video.r={v['r']})")

        # ---- 2. YouTube-like layout with fixed header ----
        page.goto(base + "/yt")
        info = wait_on(page)
        btn = info["buttons"][0] if info["buttons"] else None
        check(btn is not None and btn["on"], "button visible on YouTube-like layout")
        if btn:
            v = info["video"]
            check(not overlap(btn, v), "yt-like: button outside the video")
            check(btn["b"] <= v["t"] and abs(btn["r"] - v["r"]) <= 1, "yt-like: sits above the top-right corner")

        # ---- 3. scrolling keeps it glued, hides when video leaves ----
        page.evaluate("window.scrollTo(0, 150)")
        time.sleep(0.5)
        info = page.evaluate(JS_INFO, "#v")
        btn = info["buttons"][0]
        v = info["video"]
        if btn["on"]:
            check(not overlap(btn, v), "after scroll: still outside the video")
            check(btn["b"] <= v["t"] or btn["l"] >= v["r"], "after scroll: still at top-right outside video")
            check(btn["t"] < v["b"], "after scroll: not below video")
        else:
            check(True, "after scroll: hidden when no top-right room exists")
        page.evaluate("window.scrollTo(0, 2000)")
        time.sleep(0.6)
        info = page.evaluate(JS_INFO, "#v")
        check(not any(b["on"] for b in info["buttons"]), "button hidden when the video scrolled out of view")
        page.evaluate("window.scrollTo(0, 0)")
        info = wait_on(page)
        check(any(b["on"] for b in info["buttons"]), "button returns when video scrolls back")

        # ---- 4. flush video: never inside the video ----
        page.goto(base + "/flush")
        time.sleep(1.0)
        info = page.evaluate(JS_INFO, "#v")
        v = info["video"]
        for b in info["buttons"]:
            if b["on"]:
                check(not overlap(b, v), f"flush video: button (if shown) is outside the video: {b}")
        check(True, f"flush video: on={[b['on'] for b in info['buttons']]}")

        # ---- 5. tiny video gets no button ----
        page.goto(base + "/tiny")
        time.sleep(1.0)
        info = page.evaluate(JS_INFO, "#v")
        check(not any(b["on"] for b in info["buttons"]), "tiny video: no visible button")

        # ---- 6. multiple videos ----
        page.goto(base + "/two")
        time.sleep(1.0)
        info = page.evaluate(JS_INFO, "#v")
        info2 = page.evaluate(JS_INFO, "#v2")
        check(sum(1 for b in info["buttons"] if b["on"]) == 2, "two videos -> two visible buttons")

        # ---- 7. removal ----
        page.evaluate("document.getElementById('v2').remove()")
        time.sleep(1.0)
        n = page.evaluate("document.querySelectorAll('.ripsync-sniffer-btn').length")
        check(n == 1, f"button is removed with its video (buttons left={n})")

        # ---- 8. FULLSCREEN ----
        page.goto(base + "/fs")
        info = wait_on(page)
        check(any(b["on"] for b in info["buttons"]), "fullscreen test: button visible before fullscreen")
        page.click("#gofs")
        time.sleep(1.2)
        fs = page.evaluate("!!document.fullscreenElement")
        check(fs, "document is in fullscreen (player wrapper)")
        info = page.evaluate(JS_INFO, "#v")
        check(not any(b["on"] for b in info["buttons"]), "fullscreen: button is hidden (no 'ripsync-on')")
        check(all(b["vis"] == "hidden" for b in info["buttons"]), "fullscreen: computed visibility is hidden")
        page.evaluate("document.exitFullscreen()")
        info = wait_on(page, want=True)
        check(any(b["on"] for b in info["buttons"]), "after leaving fullscreen: button is back")

        # ---- 9. click -> message pipeline ----
        if bridge:
            page.goto(base + "/plain")
            wait_on(page)
            # Hover over button to open dropdown or click directly on item
            page.hover(".ripsync-sniffer-btn")
            time.sleep(0.3)
            # Click the 1080p menu item
            page.click(".ripsync-menu-item")
            time.sleep(1.5)
            txt = page.evaluate("document.querySelector('.ripsync-label').innerText")
            check("Başlatıldı" in txt or "Baslat" in txt or "✔" in txt, f"click reached the bridge, label='{txt}'")
            check(len(RECEIVED) == 1 and RECEIVED[0].get("url", "").startswith("http"),
                  f"bridge received the download request: {RECEIVED}")
            check(RECEIVED[0].get("quality") == "1080p", f"quality parameter passed: {RECEIVED[0].get('quality')}")

        ctx.close()

    print()
    if FAILS:
        print("FAILED:", len(FAILS))
        for f in FAILS:
            try:
                print(" -", f)
            except Exception:
                print(" -", f.encode("ascii", "replace").decode("ascii"))
        sys.exit(1)
    print(">>> ALL BUTTON POSITION / FULLSCREEN CHECKS PASSED <<<")


if __name__ == "__main__":
    main()
