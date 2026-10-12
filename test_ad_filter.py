"""
Automated test for RipSync Extension's Ad & Micro-video filtering:
1. Verify that looping muted banner videos without controls do NOT get a download button.
2. Verify that banner/ad container videos do NOT get a download button.
3. Verify that small (< 220x140) videos without controls do NOT get a download button.
4. Verify that real video players DO get a download button.
5. Verify that clicking the dismiss (X) button removes the download button for that video.
6. Verify that domain blacklist (disabledDomains) prevents buttons on that site.
"""
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
EXT_DIR = os.path.join(ROOT, "extension")
PORT = 29915

PAGE_HTML = """<!DOCTYPE html>
<html>
<head><title>Trendyol-like Ad Test</title></head>
<body style="margin:20px; font-family:sans-serif;">
  <h1>Trendyol Test Page</h1>
  <p>Some text and product listings</p>

  <!-- 1. Looping muted banner ad (common in e-commerce carousels) -->
  <div class="banner-wrap">
    <h3>Indirimli Urunler</h3>
    <video id="ad_loop" width="300" height="150" loop muted autoplay src="dummy.mp4"></video>
  </div>

  <!-- 2. Video inside ad container -->
  <div class="ad-sponsored-box">
    <h3>Sponsorlu Reklam</h3>
    <video id="ad_container" width="400" height="220" muted src="dummy.mp4"></video>
  </div>

  <!-- 3. Mini card video without controls -->
  <div class="mini-card">
    <video id="ad_mini" width="180" height="100" muted src="dummy.mp4"></video>
  </div>

  <!-- 4. Real Main Video Player with controls -->
  <div class="player-wrap" style="margin-top: 50px;">
    <h2>Gercek Video / Dizi / Film</h2>
    <video id="real_video" width="640" height="360" controls muted src="dummy.mp4"></video>
  </div>
</body>
</html>
"""

class ServerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE_HTML.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(PAGE_HTML.encode('utf-8'))

    def log_message(self, *args):
        pass

def check(condition, message):
    if condition:
        print(f"[PASS] {message}")
    else:
        print(f"[FAIL] {message}")
        sys.exit(1)

def main():
    server = HTTPServer(("127.0.0.1", PORT), ServerHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            tempfile.mkdtemp(),
            headless=False,
            ignore_default_args=["--disable-extensions"],
            args=[
                f"--disable-extensions-except={EXT_DIR}",
                f"--load-extension={EXT_DIR}",
                "--window-size=1200,800"
            ]
        )
        page = ctx.new_page()
        page.goto(f"http://127.0.0.1:{PORT}/")
        time.sleep(1.0)
        page.evaluate("document.getElementById('real_video').scrollIntoView()")
        time.sleep(2.0)

        # 1. Count active buttons
        buttons_info = page.evaluate("""() => {
            const btns = [...document.querySelectorAll('.ripsync-sniffer-btn')];
            return btns.map(b => ({
                on: b.classList.contains('ripsync-on'),
                text: b.innerText,
                top: b.getBoundingClientRect().top,
                left: b.getBoundingClientRect().left
            }));
        }""")

        visible_btns = [b for b in buttons_info if b['on']]
        check(len(visible_btns) == 1, f"Only 1 button should be visible (for real video), found: {len(visible_btns)}")

        # 2. Verify that dismissing (X) works
        print("Testing dismiss button...")
        page.click(".ripsync-on .ripsync-dismiss-btn")
        time.sleep(1.0)

        visible_after_dismiss = page.evaluate("""() => {
            return [...document.querySelectorAll('.ripsync-sniffer-btn')].filter(b => b.classList.contains('ripsync-on')).length;
        }""")
        check(visible_after_dismiss == 0, "Button should be completely removed after clicking dismiss (X)")

        # 3. Reload page and test disabledDomains blacklist
        print("Testing domain blacklist (disabledDomains)...")
        workers = ctx.service_workers
        if not workers:
            time.sleep(1.0)
            workers = ctx.service_workers
        check(len(workers) > 0, "Extension service worker found")
        workers[0].evaluate("chrome.storage.local.set({ disabledDomains: ['127.0.0.1'] })")
        time.sleep(1.0)
        page.reload()
        time.sleep(2.0)

        visible_on_disabled_site = page.evaluate("""() => {
            return [...document.querySelectorAll('.ripsync-sniffer-btn')].filter(b => b.classList.contains('ripsync-on')).length;
        }""")
        check(visible_on_disabled_site == 0, "No buttons should appear when domain is in disabledDomains")

        print(">>> ALL AD FILTER & PER-SITE TESTS PASSED SUCCESSFULLY! <<<")
        ctx.close()

if __name__ == "__main__":
    main()
