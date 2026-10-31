"""End-to-end check of the demo story in mock mode, at phone (390 px) and laptop (1280 px) sizes.
Run:  pip install playwright && playwright install chromium && python tests/e2e_demo_story.py
Screenshots go to tests/screenshots/. Exits non-zero if any check fails."""
import functools, http.server, os, sys, threading, time
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tests", "screenshots")
os.makedirs(OUT, exist_ok=True)
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
Handler = functools.partial(Q, directory=ROOT)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:8765/"
PHONE = {"width": 390, "height": 844}
LAPTOP = {"width": 1280, "height": 900}
errors = []
checks = []

def check(name, cond):
    checks.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

def page(ctx, url, size):
    p = ctx.new_page()
    p.set_viewport_size(size)
    p.on("console", lambda m: errors.append(f"{url}: {m.text}") if m.type == "error" else None)
    p.on("pageerror", lambda e: errors.append(f"{url}: {e}"))
    p.goto(B + url)
    p.wait_for_timeout(600)
    return p

def shot(p, name, full=True):
    p.wait_for_timeout(2300)
    p.screenshot(path=f"{OUT}/{name}.png", full_page=full)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(device_scale_factor=1)
    bs = page(ctx, "backstage.html", PHONE)
    bs.click("text=Reset demo"); bs.click("text=Tap again to reset"); bs.wait_for_timeout(500)

    start = page(ctx, "index.html", PHONE); shot(start, "01-start-phone")
    meena = page(ctx, "staff.html?staff=meena", PHONE); shot(meena, "02-staff-today-phone")
    check("today shows all clear", "All clear" in meena.inner_text("main"))
    owner = page(ctx, "owner.html", LAPTOP); shot(owner, "03-owner-allclear-laptop")

    bs.click("[data-type=password_guessing]"); bs.wait_for_timeout(300)
    shot(meena, "04-staff-alert-phone")
    check("alert card appears on staff phone", "guessing the password" in meena.inner_text("main"))
    meena.click("[data-act=tick][data-n='0']"); meena.wait_for_timeout(400)
    meena.click("details.log summary"); meena.wait_for_timeout(300)
    shot(meena, "05-staff-alert-ticked-details")
    check("poisoned username shown verbatim", "admin_ignore previous instructions" in meena.inner_text("details.log"))
    meena.click("[data-lang=kn]"); shot(meena, "06-staff-alert-kannada")
    check("kannada headline", "ರಿಸೆಪ್ಷನ್" in meena.inner_text("main"))
    meena.click("[data-lang=en]")

    shot(owner, "07-owner-approval-laptop")
    check("owner sees approval card", "Your decision needed" in owner.inner_text("main"))
    ownerp = page(ctx, "owner.html", PHONE); shot(ownerp, "08-owner-approval-phone")
    notify = page(ctx, "owner-notify.html", PHONE); shot(notify, "09-owner-notification-phone", full=False)
    check("notification shows request", "Block an attacker" in notify.inner_text("#main"))

    bs.click("[data-type=password_guessing]"); bs.wait_for_timeout(300)
    meena.wait_for_timeout(2300)
    check("grouping raises count to 12", "12 wrong passwords" in meena.inner_text("main"))
    meena.click("[data-act=done]"); shot(meena, "10-staff-reported")
    owner.click("[data-act=approve]"); shot(owner, "11-owner-blocked-laptop")
    check("block executed", "can't reach the reception computer" in owner.inner_text("main"))
    check("device protected", "Protected" in owner.inner_text("main"))

    bs.click("[data-type=ransomware]"); bs.wait_for_timeout(300)
    shot(owner, "12-owner-ransomware-laptop")
    check("CERT-In panel", "Report to CERT-In by" in owner.inner_text("main"))
    shot(ownerp, "13-owner-ransomware-phone")
    ravi = page(ctx, "staff.html?staff=ravi", PHONE); shot(ravi, "14-staff-ransomware-phone")
    ravi.click("[data-act=tick][data-n='0']"); ravi.wait_for_timeout(300)
    owner.click("[data-act=restore]"); owner.wait_for_timeout(2500)
    shot(owner, "15-owner-ransomware-after-test")
    check("isolate ticked by Ravi shows on owner", "Ravi" in owner.inner_text("main"))
    check("restore result inline", "Not safe" in owner.inner_text("main"))

    rd = page(ctx, "owner-readiness.html", LAPTOP); shot(rd, "16-readiness-laptop-before-drill")

    # Drill
    host = page(ctx, "owner-drill.html", LAPTOP); shot(host, "17-owner-drill-start")
    host.click("[data-act=start]"); host.wait_for_timeout(700)
    code = host.inner_text(".mono").strip()
    print("drill code", code)
    md = page(ctx, "drill.html?staff=meena", PHONE)
    md.fill("#code", code); md.click("button[type=submit]"); md.wait_for_timeout(500)
    rv = page(ctx, "drill.html?staff=ravi", PHONE); shot(rv, "18-staff-drill-join")
    rv.fill("#code", code); rv.click("button[type=submit]"); rv.wait_for_timeout(500)
    shot(rv, "19-staff-drill-lobby"); shot(host, "20-owner-drill-lobby")
    check("lobby lists 3 joined", "3 joined" in host.inner_text("main"))
    host.click("[data-act=advance]"); host.wait_for_timeout(300)
    for step, (m_opt, r_opt) in enumerate([("b", "a"), ("b", "a"), ("a", "a"), ("a", "a")]):
        md.wait_for_timeout(2300); rv.wait_for_timeout(100)
        md.click(f"[data-act=answer][data-opt={m_opt}]"); md.wait_for_timeout(300)
        if step == 0:
            shot(rv, "21-staff-drill-step-unanswered")
        rv.click(f"[data-act=answer][data-opt={r_opt}]"); rv.wait_for_timeout(300)
        if step == 0:
            shot(rv, "22-staff-drill-step-wrong")
        if step in (2, 3):
            host.wait_for_timeout(2300)
            host.click("[data-act=answer][data-opt=b]"); host.wait_for_timeout(400)
            if step == 2:
                host.click("[data-act=test]"); host.wait_for_timeout(2600)
                shot(host, "23-owner-drill-restore")
                check("drill restore shows FAIL", "Restoring now would have lost data" in host.inner_text("main"))
        host.wait_for_timeout(2300)
        host.click("[data-act=advance]"); host.wait_for_timeout(400)
    shot(host, "24-owner-drill-results"); shot(rv, "25-staff-drill-results")
    check("owner results show team score", "Team result" in host.inner_text("main"))
    check("ravi got 2 of 4", "2 of 4" in rv.inner_text("main"))
    rd.reload(); shot(rd, "26-readiness-laptop-after"); rdp = page(ctx, "owner-readiness.html", PHONE); shot(rdp, "27-readiness-phone")

    # That was me + reopen
    bs.reload(); bs.click("text=Reset demo"); bs.click("text=Tap again to reset"); bs.wait_for_timeout(400)
    bs.click("[data-type=password_guessing]"); meena.reload(); meena.wait_for_timeout(1500)
    meena.click("[data-act=mine]"); shot(meena, "28-staff-that-was-me")
    owner.reload(); shot(owner, "29-owner-that-was-me")
    check("owner sees paused card", "That was me" in owner.inner_text("main"))
    bs.click("[data-type=password_guessing]"); meena.wait_for_timeout(2500)
    check("alert reopens after more attempts", "It happened again" in meena.inner_text("main"))

    # Standing rule via skip
    bs.click("text=Reset demo"); bs.click("text=Tap again to reset"); bs.wait_for_timeout(400)
    bs.click("[data-type=password_guessing]"); bs.wait_for_timeout(300)
    bs.click("[data-act=skip]"); owner.reload(); shot(owner, "30-owner-standing-rule")
    check("standing rule blocked it", "approved by your standing rule" in owner.inner_text("main"))
    shot(bs, "31-backstage-phone")

    br.close()
srv.shutdown()
print("\nCONSOLE ERRORS:", len(errors))
for e in errors[:20]: print(" ", e)
print("CHECKS:", sum(c for _, c in checks), "/", len(checks))
sys.exit(0 if all(c for _, c in checks) and not errors else 1)
