"""Real-site check (YouTube / X.com) of the download button placement + fullscreen hiding.

usage:  python test_button_real_sites.py [WIDTHxHEIGHT]
"""
import os, re, sys, tempfile, time
from playwright.sync_api import sync_playwright

EXT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extension")

INFO = """() => {
  const vids = [...document.querySelectorAll('video')].map(v => {const r=v.getBoundingClientRect();
     return {l:r.left,t:r.top,r:r.right,b:r.bottom,w:r.width,h:r.height};}).filter(r => r.w>=120 && r.h>=70);
  const btns = [...document.querySelectorAll('.ripsync-sniffer-btn')].map(b => {const q=b.getBoundingClientRect();
     return {l:q.left,t:q.top,r:q.right,b:q.bottom,on:b.classList.contains('ripsync-on'),vis:getComputedStyle(b).visibility,parent:b.parentElement.tagName};});
  const mh = document.querySelector('#masthead-container, ytd-masthead');
  return {vids, btns, fs: !!document.fullscreenElement, masthead: mh ? mh.getBoundingClientRect().bottom : null,
          vw: innerWidth, vh: innerHeight};
}"""

FAILS = []
def check(c, m):
    print(("[PASS] " if c else "[FAIL] ") + m)
    if not c: FAILS.append(m)

def overlap(a, b):
    return not (a["r"] <= b["l"] or a["l"] >= b["r"] or a["b"] <= b["t"] or a["t"] >= b["b"])

def wait_btn(page, want=True, timeout=12):
    end = time.time() + timeout
    info = None
    while time.time() < end:
        info = page.evaluate(INFO)
        if any(b["on"] for b in info["btns"]) == want:
            return info
        time.sleep(0.3)
    return info

def report(label, info):
    on = [b for b in info["btns"] if b["on"]]
    print(f"  [{label}] videos={info['vids']} buttons_on={on} masthead_bottom={info['masthead']} viewport={info['vw']}x{info['vh']}")

def verify_outside(label, info):
    on = [b for b in info["btns"] if b["on"]]
    check(len(on) >= 1, f"{label}: button visible")
    if not on or not info["vids"]:
        return
    big = max(info["vids"], key=lambda r: r["w"] * r["h"])
    for b in on:
        check(not overlap(b, big), f"{label}: button is outside the video rect")
        check(b["parent"] in ("BODY", "HTML"), f"{label}: button is body-level")
        # Ensure it is at the TOP RIGHT (above the video or beside top-right), NEVER at the bottom
        is_top_right = (b["b"] <= big["t"] + 5) or (b["l"] >= big["r"] - 5 and b["t"] <= big["t"] + 30)
        check(is_top_right, f"{label}: button is at the TOP-RIGHT outside the video (btn.top={b['t']}, vid.top={big['t']}, btn.left={b['l']}, vid.right={big['r']})")
        check(b["t"] < big["b"], f"{label}: button is NOT below the video")

def leave_fullscreen_like_user(page):
    """Esc key like a user; fall back to the API if the synthetic key did not leave fullscreen."""
    page.keyboard.press("Escape")
    time.sleep(1.2)
    if page.evaluate("!!document.fullscreenElement"):
        print("  (synthetic Esc did not leave fullscreen -> document.exitFullscreen())")
        page.evaluate("document.exitFullscreen()")
        time.sleep(1.2)

def main():
    viewport = None
    if len(sys.argv) > 1:
        w, h = sys.argv[1].lower().split("x")
        viewport = {"width": int(w), "height": int(h)}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            tempfile.mkdtemp(), headless=False, ignore_default_args=["--disable-extensions"],
            args=[f"--disable-extensions-except={EXT_DIR}", f"--load-extension={EXT_DIR}",
                  "--window-size=1300,820", "--window-position=20,20", "--autoplay-policy=no-user-gesture-required"],
            viewport=viewport)
        page = ctx.new_page()

        # ---------------- YouTube watch page ----------------
        print("== YouTube ==", viewport or "default viewport")
        page.goto("https://www.youtube.com/watch?v=jNQXAC9IVRw", wait_until="domcontentloaded")
        time.sleep(4)
        info = wait_btn(page, True, 15)
        report("watch", info)
        verify_outside("YouTube watch", info)

        # theater mode (press t)
        page.keyboard.press("t")
        time.sleep(2)
        info = wait_btn(page, True, 6)
        report("theater", info)
        on = [b for b in info["btns"] if b["on"]]
        if on and info["vids"]:
            big = max(info["vids"], key=lambda r: r["w"] * r["h"])
            check(all(not overlap(b, big) for b in on), "YouTube theater: button (if shown) is outside the video")
        page.keyboard.press("t")
        time.sleep(1.5)

        # real fullscreen via the player's button (genuine click = user gesture)
        try:
            page.hover("#movie_player")
            page.click(".ytp-fullscreen-button", timeout=5000)
            time.sleep(2)
            info = page.evaluate(INFO)
            check(info["fs"], "YouTube: player is in fullscreen")
            check(not any(b["on"] for b in info["btns"]), "YouTube fullscreen: download button hidden")
            leave_fullscreen_like_user(page)
            info = wait_btn(page, True, 8)
            check(not info["fs"], "YouTube: left fullscreen")
            check(any(b["on"] for b in info["btns"]), "YouTube: button back after leaving fullscreen")
        except Exception as e:
            check(False, f"YouTube fullscreen interaction failed: {e}")

        # home page: no button on hover previews
        page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
        time.sleep(4)
        info = page.evaluate(INFO)
        check(not any(b["on"] for b in info["btns"]), "YouTube home: no download button")

        # ---------------- X.com ----------------
        print("== X.com ==")
        page.goto("https://x.com/MrBarneyStynson/status/2109023665203417588", wait_until="domcontentloaded")
        time.sleep(7)
        info = page.evaluate(INFO)
        report("x", info)
        if info["vids"]:
            info = wait_btn(page, True, 8)
            verify_outside("X.com", info)
            # fullscreen of X's player container (a real click gives the user activation)
            try:
                page.mouse.click(5, 300)  # real input event on blank page area -> user activation
                ok = page.evaluate("""() => {
                    const v = document.querySelector('video');
                    const box = v.closest('[data-testid="videoPlayer"], [data-testid="videoComponent"]')
                                || v.parentElement.parentElement;
                    box.requestFullscreen();
                    return true; }""")
                time.sleep(2)
                info = page.evaluate(INFO)
                check(info["fs"], "X.com: player container is in fullscreen")
                check(not any(b["on"] for b in info["btns"]), "X.com fullscreen: download button hidden")
                leave_fullscreen_like_user(page)
                info = wait_btn(page, True, 8)
                check(any(b["on"] for b in info["btns"]), "X.com: button back after leaving fullscreen")
            except Exception as e:
                check(False, f"X.com fullscreen check failed: {str(e)[:200]}")
        else:
            print("  [INFO] X.com did not render a <video> logged-out (login wall) - skipped")

        ctx.close()

    print()
    if FAILS:
        print("FAILED:", FAILS)
        sys.exit(1)
    print(">>> REAL SITE CHECKS PASSED <<<")

if __name__ == "__main__":
    main()
