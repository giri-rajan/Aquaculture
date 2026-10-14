"""Drive the real AquaSentinel app through the demo storyboard and record it.

Three recordings: A (scenes 1-6, English voice clip on the mic), B (scenes 7-9, Tamil clip), C (phone, scene 10).
Every event is written to marks.json as seconds from the start of its recording.
"""
import asyncio
import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

HERE = Path(__file__).parent
APP = "http://localhost:5173"
API = "http://localhost:8080/api"
W, H = 1600, 900
MARKS: dict = {}

# Visible cursor and click ring (a recording aid drawn over the page; the app itself is unchanged).
# The browser speech recogniser is hidden so the app uses its Gemini transcription path, which accepts
# the synthesized voice clip on the virtual microphone.
INIT = """
delete window.SpeechRecognition; delete window.webkitSpeechRecognition;
window.addEventListener('DOMContentLoaded', () => {
  const c = document.createElement('div');
  c.style.cssText = 'position:fixed;left:0;top:0;width:22px;height:22px;z-index:2147483647;pointer-events:none;transform:translate(-3px,-2px);transition:left .06s linear,top .06s linear';
  c.innerHTML = '<svg width="22" height="22" viewBox="0 0 22 22"><path d="M3 2l14 8-6.2 1.6L7.6 18z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  document.body.appendChild(c);
  document.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  document.addEventListener('mousedown', e => {
    const r = document.createElement('div');
    r.style.cssText = `position:fixed;left:${e.clientX-18}px;top:${e.clientY-18}px;width:36px;height:36px;border-radius:50%;border:3px solid rgba(15,118,110,.85);z-index:2147483646;pointer-events:none;transition:transform .45s ease-out,opacity .45s ease-out`;
    document.body.appendChild(r);
    requestAnimationFrame(() => { r.style.transform = 'scale(1.8)'; r.style.opacity = '0'; });
    setTimeout(() => r.remove(), 600);
  }, true);
});
"""


def api(path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


class Rec:
    def __init__(self, name):
        self.name, self.t0 = name, None
        MARKS[name] = {}

    def start(self):
        self.t0 = time.monotonic()

    def mark(self, key):
        t = round(time.monotonic() - self.t0, 2)
        MARKS[self.name][key] = t
        print(f"[{self.name} {t:7.2f}s] {key}", flush=True)
        (HERE / "marks.json").write_text(json.dumps(MARKS, indent=1))


async def glide(page, loc_or_xy, steps=28, pause=0.25):
    """Move the cursor smoothly to an element (centre) or an (x, y) point."""
    if isinstance(loc_or_xy, tuple):
        x, y = loc_or_xy
    else:
        await loc_or_xy.scroll_into_view_if_needed()
        b = await loc_or_xy.bounding_box()
        x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    await page.mouse.move(x, y, steps=steps)
    await asyncio.sleep(pause)
    return x, y


async def click(page, loc, pause=0.4):
    await glide(page, loc)
    await loc.click()
    await asyncio.sleep(pause)


async def smooth_scroll(page, dy, steps=12):
    for _ in range(steps):
        await page.mouse.wheel(0, dy / steps)
        await asyncio.sleep(0.04)


async def wait_text(page, text, timeout=180):
    await page.get_by_text(text, exact=False).first.wait_for(timeout=timeout * 1000)


async def new_ctx(p, wav, name, mobile=False):
    browser = await p.chromium.launch(channel="chrome", headless=True, args=[
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
        f"--use-file-for-fake-audio-capture={wav}", "--autoplay-policy=no-user-gesture-required", "--hide-scrollbars"])
    if mobile:
        ctx = await browser.new_context(viewport={"width": 430, "height": 932}, device_scale_factor=3, is_mobile=True,
                                        has_touch=True, permissions=["microphone"],
                                        record_video_dir=str(HERE / name), record_video_size={"width": 430, "height": 932})
    else:
        ctx = await browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=2, permissions=["microphone"],
                                        record_video_dir=str(HERE / name), record_video_size={"width": W, "height": H})
    await ctx.add_init_script(INIT)
    page = await ctx.new_page()
    return browser, ctx, page


async def run_a(p):
    rec = Rec("A")
    browser, ctx, page = await new_ctx(p, HERE / "cmd.wav", "A")
    rec.start()
    await page.goto(f"{APP}/?lang=en&theme=light#live")
    await wait_text(page, "Mission planner", 60)
    await asyncio.sleep(4)
    await page.mouse.move(W / 2, H / 2)
    rec.mark("s1_start")
    # Scene 1: across the KPI tiles, then to the map
    for x in (120, 380, 640, 900, 1160, 1420):
        await page.mouse.move(x, 160, steps=14)
        await asyncio.sleep(0.35)
    await glide(page, (560, 560), steps=30, pause=2.5)
    rec.mark("s1_end")

    # Scene 2: voice mission
    mission = page.get_by_label("Mission request")
    await mission.scroll_into_view_if_needed()
    await asyncio.sleep(0.6)
    rec.mark("s2_start")
    mic = page.locator("form").filter(has=mission).get_by_role("button", name="Speak")
    await click(page, mic)
    rec.mark("s2_mic_on")
    await asyncio.sleep(6.6)
    await page.locator("form").filter(has=mission).locator("button[aria-pressed='true']").click()
    rec.mark("s2_mic_off")
    await page.wait_for_function("() => document.querySelector('[aria-label=\"Mission request\"]').value.length > 10", timeout=90000)
    rec.mark("s2_transcribed")
    await asyncio.sleep(1.2)
    await click(page, page.get_by_role("button", name="Plan mission"))
    rec.mark("s2_sent")
    await wait_text(page, "planned by Gemini", 180)
    rec.mark("s2_planned")
    await asyncio.sleep(2.5)
    await glide(page, (600, 520), steps=30, pause=3)
    rec.mark("s2_route_shown")

    # Scene 3: plant the hidden discharge
    began = page.locator("label").filter(has_text="Discharge began").locator("select")
    await began.scroll_into_view_if_needed()
    await began.select_option("12")
    await asyncio.sleep(0.8)
    rec.mark("s3_start")
    await click(page, page.get_by_role("button", name="Industrial discharge"), pause=2)
    rec.mark("s3_clicked")
    await asyncio.sleep(2)

    # Scene 4: detection, re-plan, trace (no clicks)
    await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    await asyncio.sleep(1)
    await page.mouse.move(560, 520, steps=20)
    rec.mark("s4_start")
    try:
        await wait_text(page, "Anomaly #1", 240); rec.mark("s4_anomaly")
        await wait_text(page, "Tracing plume", 120); rec.mark("s4_tracing")
        await wait_text(page, "Source:", 240); rec.mark("s4_source")
    except PWTimeout:
        rec.mark("s4_TIMEOUT")
    try:
        await wait_text(page, "Likely cause", 240); rec.mark("s5_diagnosis_ready")
    except PWTimeout:
        rec.mark("s5_TIMEOUT")
    await asyncio.sleep(1.5)

    # Scene 5: walk through the diagnosis, camera, true source
    card = page.locator("section").filter(has_text="Gemini diagnosis").first
    await card.scroll_into_view_if_needed()
    await page.evaluate("(el) => window.scrollBy({top: el.getBoundingClientRect().top - 70, behavior: 'smooth'})", await card.element_handle())
    await asyncio.sleep(1.2)
    rec.mark("s5_start")
    for label in ("Likely cause", "Evidence", "CPCB:", "Recommended actions", "Lab tests to confirm"):
        loc = card.get_by_text(label, exact=False).first
        if await loc.count():
            await glide(page, loc, steps=22, pause=1.6)
            rec.mark(f"s5_{label.split()[0].lower().strip(':')}")
    cam = page.locator("section").filter(has_text="Boat camera").first
    await page.evaluate("(el) => window.scrollBy({top: el.getBoundingClientRect().top - 70, behavior: 'smooth'})", await cam.element_handle())
    await asyncio.sleep(1.2)
    await glide(page, cam.locator("img"), steps=22, pause=2)
    rec.mark("s5_camera")
    await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    await asyncio.sleep(1.2)
    await click(page, page.get_by_label("show true source"), pause=0.6)
    rec.mark("s5_truth")
    await glide(page, (300, 640), steps=25, pause=2.5)
    rec.mark("s5_end")

    # Scene 6: zone health
    await click(page, page.get_by_role("link", name="Zone health"), pause=1.5)
    rec.mark("s6_start")
    await click(page, page.locator("button").filter(has_text="South-west · SW"), pause=2.5)
    rec.mark("s6_sw")
    why = page.get_by_text("why the model says", exact=False).first
    await page.evaluate("(el) => window.scrollBy({top: el.getBoundingClientRect().top - 80, behavior: 'smooth'})", await why.element_handle())
    await asyncio.sleep(1.2)
    await glide(page, (300, 260), steps=20, pause=1.5)
    await glide(page, (1100, 200), steps=24, pause=2.5)
    rec.mark("s6_end")
    await asyncio.sleep(1)
    await ctx.close(); await browser.close()


async def run_b(p):
    rec = Rec("B")
    browser, ctx, page = await new_ctx(p, HERE / "ta.wav", "B")
    rec.start()
    await page.goto(f"{APP}/?lang=en&theme=light#live")
    await wait_text(page, "Mission planner", 60)
    await asyncio.sleep(3)
    await page.mouse.move(1200, 60, steps=10)
    rec.mark("s7_start")
    lang = page.locator("header select")
    await glide(page, lang)
    await lang.select_option("ta")
    rec.mark("s7_tamil")
    await asyncio.sleep(2.2)
    await click(page, page.get_by_role("link", name="ஏரியிடம் கேள்"), pause=1.5)
    rec.mark("s7_ask")
    q = page.get_by_label("கேள்வி")
    await click(page, page.locator("form").filter(has=q).get_by_role("button", name="பேசுங்கள்"))
    rec.mark("s7_mic_on")
    await asyncio.sleep(7.0)
    await page.locator("form").filter(has=q).locator("button[aria-pressed='true']").click()
    rec.mark("s7_mic_off")
    await page.wait_for_function("() => document.querySelector('[aria-label=\"கேள்வி\"]').value.length > 5", timeout=90000)
    rec.mark("s7_transcribed")
    await asyncio.sleep(1.2)
    await click(page, page.get_by_role("button", name="அனுப்பு"))
    rec.mark("s7_sent")
    await page.locator(".prose-sm").first.wait_for(timeout=180000)
    rec.mark("s7_answer")
    await asyncio.sleep(2)
    tools_btn = page.get_by_role("button", name="கருவி அழைப்புகள்").first
    if await tools_btn.count():
        await click(page, tools_btn, pause=2.5)
    rec.mark("s7_tools")
    await asyncio.sleep(1.5)

    # Scene 8: alerts and report
    await click(page, page.get_by_role("link", name="அறிக்கைகள் & எச்சரிக்கைகள்"), pause=1.5)
    rec.mark("s8_start")
    sel = page.get_by_label("முரண்பாடு")
    await sel.wait_for(timeout=20000)
    await glide(page, sel)
    opts = await sel.locator("option").all()
    await sel.select_option(index=1 if len(opts) > 1 else 0)
    await asyncio.sleep(0.6)
    await click(page, page.get_by_role("button", name="எச்சரிக்கைகளை எழுது"))
    rec.mark("s8_alert_clicked")
    try:
        await wait_text(page, "தமிழ் · Tamil", 180); rec.mark("s8_alerts")
    except PWTimeout:
        rec.mark("s8_alerts_TIMEOUT")
    await asyncio.sleep(1)
    cards = page.get_by_text("हिन्दी · Hindi", exact=False).first
    if await cards.count():
        await page.evaluate("(el) => window.scrollBy({top: el.getBoundingClientRect().top - 420, behavior: 'smooth'})", await cards.element_handle())
    await asyncio.sleep(2.5)
    rec.mark("s8_alerts_shown")
    await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    await asyncio.sleep(1)
    await click(page, page.get_by_role("button", name="அறிக்கை உருவாக்கு"))
    rec.mark("s8_report_clicked")
    try:
        await page.get_by_role("link", name="PDF").first.wait_for(timeout=300000); rec.mark("s8_report_ready")
    except PWTimeout:
        rec.mark("s8_report_TIMEOUT")
    await asyncio.sleep(1)
    await glide(page, page.get_by_role("link", name="PDF").first, pause=2)
    rec.mark("s8_end")

    # Scene 9: benchmarks in English
    await glide(page, lang)
    await lang.select_option("en")
    await asyncio.sleep(1.5)
    await click(page, page.get_by_role("link", name="Benchmarks"), pause=2.5)
    rec.mark("s9_start")
    for row in ("These are simulator results", "Source localisation", "Anomaly detection", "End-to-end latency"):
        loc = page.get_by_text(row, exact=False).first
        if await loc.count():
            await glide(page, loc, steps=22, pause=2)
    rec.mark("s9_end")
    await asyncio.sleep(1)
    await ctx.close(); await browser.close()


async def run_c(p):
    rec = Rec("C")
    browser, ctx, page = await new_ctx(p, HERE / "cmd.wav", "C", mobile=True)
    rec.start()
    await page.goto(f"{APP}/?lang=hi&theme=dark#live")
    await wait_text(page, "मिशन योजनाकार", 60)
    await asyncio.sleep(3)
    rec.mark("s10_start")
    for _ in range(3):
        await page.mouse.wheel(0, 260)
        await asyncio.sleep(0.9)
    await asyncio.sleep(1)
    await page.tap("nav.tabbar a[href='#zones']")
    rec.mark("s10_zones")
    await asyncio.sleep(3.5)
    await page.tap("nav.tabbar a[href='#live']")
    rec.mark("s10_live")
    await asyncio.sleep(4)
    rec.mark("s10_end")
    await ctx.close(); await browser.close()


async def main(which):
    async with async_playwright() as p:
        if "A" in which:
            await run_a(p)
        if "B" in which:
            await run_b(p)
        if "C" in which:
            await run_c(p)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ABC"))
