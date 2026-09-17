# -*- coding: utf-8 -*-
"""foreign-cli — 国外顾问组命令行通道（ChatGPT / Grok / Copilot / Perplexity /
Gemini，五站共用同一独立浏览器 profile 的 CDP）。

通道形态：本地代理（端口走环境变量 ORCHESTRA_FOREIGN_PROXY_PORT）+ 独立浏览器
profile（由幂等启动 bat 拉起，路径走环境变量 ORCHESTRA_FOREIGN_LAUNCHER，bat
要点见本目录 README）。登录态绑定该 profile，人工登录一次即持久有效。

Commands:
  status                      CDP/proxy state + page targets
  new    <site>               start a fresh chat (navigate to site home)
  send   <site> <text|@file>  deliver message (three-gate native input)
  extract <site> [--tail N]   read page text tail
  ensure                      best-effort: if CDP dead, run launcher bat and wait

Sites (five-site foreign advisor group, E2E status):
  chatgpt     chatgpt.com             E2E OK (send->reply loop closed)
  grok        grok.com                send OK; reply stream blocked by WS-over-proxy (intermittent)
  copilot     copilot.microsoft.com   E2E OK (send->reply loop closed)
  perplexity  www.perplexity.ai       E2E OK (send->reply loop closed)
  gemini      gemini.google.com/app   E2E OK (send->reply loop closed)

Targets may be page tabs OR iframes (OOPIF "Ask-All" split view) — both
supported; trusted input on an iframe target is fully equivalent to a page.

Send pipeline = three gates (ported from the ChatParty toolchain):
  scan (15-point elementFromPoint hit test; dialog clearing + Escape on fail)
  -> trusted click -> focus gate (activeElement inside editor)
  -> insertText -> value gate (non-empty, trim) -> trusted Enter.

Dependency: pip install websocket-client (the only third-party package).
"""
import argparse
import io
import json
import os
import socket
import subprocess
import sys
import time

import urllib.request

import websocket

CDP_PORT = 9227
CDP_HOST = "127.0.0.1"
PROXY_PORT = int(os.environ.get("ORCHESTRA_FOREIGN_PROXY_PORT", "0"))
LAUNCHER_BAT = os.environ.get(
    "ORCHESTRA_FOREIGN_LAUNCHER", r"<start_foreign_browser.bat 绝对路径>")
SITE_HOME = {
    "chatgpt": "https://chatgpt.com/",
    "grok": "https://grok.com/",
    "copilot": "https://copilot.microsoft.com/",
    "perplexity": "https://www.perplexity.ai/",
    "gemini": "https://gemini.google.com/app",
}
SITE_URL_HINTS = {
    "chatgpt": "chatgpt.com",
    "grok": "grok.com",
    "copilot": "copilot",          # copilot.microsoft.com / copilot.com dual domain
    "perplexity": "perplexity.ai",
    "gemini": "gemini.google.com",
}


def port_open(port, host=CDP_HOST, timeout=2):
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except OSError:
        return False


def _http_json(path, timeout=5):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return json.load(op.open(f"http://{CDP_HOST}:{CDP_PORT}{path}", timeout=timeout))


def ensure_cdp(wait_secs=30):
    """Return (alive, restarted). Best-effort: bat may need a user session."""
    if port_open(CDP_PORT):
        return True, False
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(["cmd", "/c", LAUNCHER_BAT], close_fds=True,
                         creationflags=flags)
    except Exception:
        return False, True
    deadline = time.time() + wait_secs
    while time.time() < deadline:
        time.sleep(1.5)
        if port_open(CDP_PORT):
            return True, True
    return port_open(CDP_PORT), True


def _url_host(url):
    """URL host (lowercase). Host-level match keeps third-party iframes whose
    URL merely CONTAINS a site name (stripe url=...grok.com...) from matching."""
    from urllib.parse import urlparse
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def pick_target(site, tlist=None):
    hint = SITE_URL_HINTS[site]
    if tlist is None:
        try:
            tlist = _http_json("/json/list")
        except Exception:
            return None
    for t in tlist:
        if t.get("type") in ("page", "iframe") and hint in _url_host(t.get("url") or ""):
            return t
    return None


class CDPPage:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=40,
                                              suppress_origin=True)
        self.mid = 0

    def cmd(self, method, params=None):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method,
                                 "params": params or {}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.mid:
                return m.get("result", {})

    def eval_js(self, expression, await_promise=False):
        r = self.cmd("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
            "awaitPromise": await_promise})
        res = r.get("result", {})
        if res.get("subtype") == "error":
            raise RuntimeError(res.get("description", "JS error")[:200])
        return res.get("value")

    def click(self, x, y):
        for t, extra in (("mousePressed", {"buttons": 1}), ("mouseReleased", {})):
            self.cmd("Input.dispatchMouseEvent", {
                "type": t, "x": x, "y": y, "button": "left",
                "clickCount": 1, **extra})

    def key(self, key, code, vk, text=None):
        for tp in ("rawKeyDown", "char", "keyUp"):
            p = {"type": tp, "key": key, "code": code,
                 "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
            if text:
                p["unmodifiedText"] = text
                p["text"] = text
            self.cmd("Input.dispatchKeyEvent", p)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


FIND_MARK_JS = """
(() => {
  document.querySelectorAll('[data-fcli]').forEach(e => e.removeAttribute('data-fcli'));
  const cand = [...document.querySelectorAll('textarea, [contenteditable="true"], [contenteditable=""]')];
  let best = null, bestArea = 0;
  for (const e of cand) {
    const r = e.getBoundingClientRect();
    if (r.width > 60 && r.height > 8 && r.bottom <= innerHeight + 4 && r.top > -4) {
      const a = r.width * r.height;
      if (a > bestArea) { bestArea = a; best = e; }
    }
  }
  if (!best) return null;
  best.setAttribute('data-fcli', '1');
  const r = best.getBoundingClientRect();
  return {x: r.x, y: r.y, w: r.width, h: r.height, tag: best.tagName};
})()
"""

SCAN_JS = """
(() => {
  const best = document.querySelector('[data-fcli]');
  if (!best) return {ok: false, why: 'no-mark'};
  const r = best.getBoundingClientRect();
  const pts = [[.5,.5],[.5,.3],[.5,.7],[.3,.5],[.7,.5],[.5,.2],[.5,.8],[.25,.5],[.75,.5],
               [.5,.12],[.5,.88],[.12,.5],[.88,.5],[.35,.35],[.65,.65]];
  for (const [fx, fy] of pts) {
    const px = Math.round(r.x + r.width*fx), py = Math.round(r.y + r.height*fy);
    if (px < 2 || py < 2 || px > innerWidth-2 || py > innerHeight-2) continue;
    const el = document.elementFromPoint(px, py);
    if (el && (el === best || best.contains(el))) return {ok: true, cx: px, cy: py};
  }
  return {ok: false};
})()
"""

CLOSE_DIALOG_JS = """
(() => {
  const dl = document.querySelector('[role="dialog"][data-state="open"], [role="dialog"].show, [role="alertdialog"]');
  if (!dl) return {found: false};
  const btns = [...dl.querySelectorAll('button')];
  const close = btns.find(b => /close|关闭|dismiss|skip|稍后|以后|知道了|got it/i.test((b.getAttribute('aria-label')||'') + ' ' + b.innerText));
  if (close) { close.click(); return {found: true, how: 'close-btn'}; }
  const x = btns.find(b => { const c=(b.className||'').toString(); return /absolute/.test(c) && b.getBoundingClientRect().width < 40; });
  if (x) { x.click(); return {found: true, how: 'x-btn'}; }
  return {found: true, how: 'no-btn'};
})()
"""

FOCUS_JS = """
(() => {
  const best = document.querySelector('[data-fcli]');
  if (!best) return {ok: false, why: 'no-mark'};
  const ae = document.activeElement;
  return {ok: !!(ae && (ae === best || best.contains(ae)))};
})()
"""

VALUE_JS = """
(() => {
  const best = document.querySelector('[data-fcli]');
  if (!best) return {ok: false, why: 'no-mark'};
  const v = best.value !== undefined ? best.value : (best.innerText || '');
  return {ok: v.trim().length > 0, len: v.trim().length};
})()
"""

AFTER_JS = """
(() => {
  const best = document.querySelector('[data-fcli]');
  const v = best ? (best.value !== undefined ? best.value : (best.innerText || '')) : null;
  return {cleared: v === null ? null : (v.trim().length === 0), href: location.href.slice(0, 90)};
})()
"""


def native_send(page, text, log=None):
    """Three-gate trusted send (scan/focus/value) + dialog clearing + Escape.
    Works on page tabs and OOPIF iframes. Returns a result dict."""
    if log is None:
        log = []
    box = scan = None
    for attempt in range(4):
        box = page.eval_js(FIND_MARK_JS)
        if not box:
            log.append(f"find#{attempt}: none")
            time.sleep(0.8)
            continue
        scan = page.eval_js(SCAN_JS)
        log.append(f"scan#{attempt}: {json.dumps(scan, ensure_ascii=False)}")
        if scan.get("ok"):
            break
        cd = page.eval_js(CLOSE_DIALOG_JS)
        log.append(f"close-dialog: {json.dumps(cd, ensure_ascii=False)}")
        time.sleep(0.6)
        page.key("Escape", "Escape", 27, None)
        time.sleep(0.7)
    if not box or not (scan and scan.get("ok")):
        return {"aborted": "scan-gate", "log": log}
    page.click(scan["cx"], scan["cy"])
    time.sleep(0.6)
    focus = page.eval_js(FOCUS_JS)
    if not focus.get("ok"):
        log.append(f"focus-retry: {json.dumps(focus, ensure_ascii=False)}")
        page.click(scan["cx"], scan["cy"])
        time.sleep(0.6)
        focus = page.eval_js(FOCUS_JS)
    log.append(f"focus: {json.dumps(focus, ensure_ascii=False)}")
    if not focus.get("ok"):
        return {"aborted": "focus-gate", "log": log}
    page.cmd("Input.insertText", {"text": text})
    time.sleep(0.8)
    val = page.eval_js(VALUE_JS)
    if not val.get("ok"):
        log.append(f"value-retry: {json.dumps(val, ensure_ascii=False)}")
        page.cmd("Input.insertText", {"text": text})
        time.sleep(0.8)
        val = page.eval_js(VALUE_JS)
    log.append(f"value: {json.dumps(val, ensure_ascii=False)}")
    if not val.get("ok"):
        return {"aborted": "value-gate", "log": log}
    page.key("Enter", "Enter", 13)
    time.sleep(2.0)
    after = page.eval_js(AFTER_JS)
    log.append(f"after: {json.dumps(after, ensure_ascii=False)}")
    return {"sent": True, "after": after, "log": log}


def cmd_status(_):
    proxy = port_open(PROXY_PORT) if PROXY_PORT > 0 else False
    cdp = port_open(CDP_PORT)
    out = {"proxy": proxy, f"cdp_{CDP_PORT}": cdp,
           "launcher": LAUNCHER_BAT}
    if cdp:
        try:
            targets = _http_json("/json/list")
            pages = [{"site": s, "kind": t.get("type"),
                      "url": (t.get("url") or "")[:60]}
                     for s, hint in SITE_URL_HINTS.items()
                     for t in targets
                     if t.get("type") in ("page", "iframe")
                     and hint in _url_host(t.get("url") or "")]
            out["pages"] = pages
        except Exception as e:
            out["list_error"] = f"{e.__class__.__name__}"
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def cmd_ensure(_):
    alive, restarted = ensure_cdp()
    print(json.dumps({"alive": alive, "restarted": restarted,
                      "proxy": port_open(PROXY_PORT) if PROXY_PORT > 0 else False,
                      "note": "" if alive
                      else "launcher bat not configured or failed; start the foreign browser manually"},
                     ensure_ascii=False))
    return 0 if alive else 1


def cmd_new(args):
    site = args.site
    alive, _ = ensure_cdp()
    if not alive:
        print(json.dumps({"error": f"CDP {CDP_PORT} not alive; run ensure "
                                   "or start the foreign browser manually"},
                         ensure_ascii=False))
        return 1
    tgt = pick_target(site)
    if not tgt:
        # open site home in a new tab via CDP
        try:
            _http_json("/json/new?" + SITE_HOME[site].replace(":", "%3A")
                       .replace("/", "%2F"), timeout=5)
            time.sleep(3)
            tgt = pick_target(site)
        except Exception:
            pass
    if not tgt:
        print(json.dumps({"error": f"no page target for {site}"}, ensure_ascii=False))
        return 1
    page = CDPPage(tgt["webSocketDebuggerUrl"])
    try:
        page.cmd("Page.enable")
        page.cmd("Page.navigate", {"url": SITE_HOME[site]})
        time.sleep(4)
        print(json.dumps({"site": site, "new": "navigated-home"}, ensure_ascii=False))
    finally:
        page.close()
    return 0


def cmd_send(args):
    site = args.site
    text = (io.open(args.text[1:], encoding="utf-8").read()
            if args.text.startswith("@") else args.text)
    alive, _ = ensure_cdp()
    if not alive:
        print(json.dumps({"error": f"CDP {CDP_PORT} not alive; run ensure "
                                   "or start the foreign browser manually"},
                         ensure_ascii=False))
        return 1
    tgt = pick_target(site)
    if not tgt:
        print(json.dumps({"error": f"no page target for {site} — open it (or its "
                                   "split-view pane) in the foreign browser window"},
                         ensure_ascii=False))
        return 1
    page = CDPPage(tgt["webSocketDebuggerUrl"])
    try:
        page.cmd("Runtime.enable")
        r = native_send(page, text)
        if r.get("aborted"):
            print(json.dumps({"site": site, "error": "aborted: " + r["aborted"],
                              "log": r.get("log", [])}, ensure_ascii=False))
            return 1
        print(json.dumps({"site": site, "sent": "gated-enter", "chars": len(text),
                          "after": r.get("after"), "kind": tgt.get("type")},
                         ensure_ascii=False))
    finally:
        page.close()
    return 0


def cmd_extract(args):
    site = args.site
    tgt = pick_target(site)
    if not tgt:
        print(json.dumps({"error": f"no page target for {site}"}, ensure_ascii=False))
        return 1
    page = CDPPage(tgt["webSocketDebuggerUrl"])
    try:
        page.cmd("Runtime.enable")
        text = page.eval_js(f"document.body.innerText.slice(-{args.tail})")
        print(json.dumps({"site": site, "chars": len(text or ""),
                          "content": text or ""}, ensure_ascii=False))
    finally:
        page.close()
    return 0


def main():
    p = argparse.ArgumentParser(prog="foreign-cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("ensure")
    n = sub.add_parser("new")
    n.add_argument("site", choices=list(SITE_HOME))
    s = sub.add_parser("send")
    s.add_argument("site", choices=list(SITE_HOME))
    s.add_argument("text")
    e = sub.add_parser("extract")
    e.add_argument("site", choices=list(SITE_HOME))
    e.add_argument("--tail", type=int, default=2000)
    args = p.parse_args()
    {"status": cmd_status, "ensure": cmd_ensure, "new": cmd_new,
     "send": cmd_send, "extract": cmd_extract}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
