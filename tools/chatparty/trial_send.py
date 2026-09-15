# -*- coding: utf-8 -*-
"""ChatParty 顾问通道试跑：对指定站点 send+extract，结果落盘 trial_result.txt
用法: python trial_send.py <site_key> <url_prefix> "<text>"
site_key: kimi / metaso / wenxin ...
"""
import sys, os, json, time, socket, base64, struct, urllib.request

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trial_result.txt')
CDP_HTTP = 'http://127.0.0.1:9222/json/list'

FIND_EDITOR_JS = '''(() => {
  const cands = document.querySelectorAll('.editor[type="text/plain"], [contenteditable="true"], textarea');
  let el = null;
  for (const c of cands) {
    const r = c.getBoundingClientRect();
    if (r.width > 100 && r.height > 10) { el = c; break; }
  }
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return JSON.stringify({x: Math.round(r.x + r.width / 2), y: Math.round(r.y + Math.min(r.height / 2, 30)),
                         tag: el.tagName, cls: String(el.className || '').slice(0, 60),
                         inview: r.y > 0 && r.y < innerHeight});
})()'''

FOCUS_JS = '''(() => {
  const el = document.querySelector('.editor[type="text/plain"], [contenteditable="true"], textarea');
  if (!el) return false;
  el.focus();
  return document.activeElement === el;
})()'''

RESIDUAL_JS = '''(() => {
  const el = document.querySelector('.editor[type="text/plain"], [contenteditable="true"], textarea');
  if (!el) return -1;
  return (el.value !== undefined && el.tagName === 'TEXTAREA') ? el.value.length : (el.innerText || '').length;
})()'''


class WS:
    def __init__(self, url):
        rest = url[len('ws://127.0.0.1:'):]
        port, path = rest.split('/', 1)
        self.s = socket.create_connection(('127.0.0.1', int(port)), timeout=15)
        key = base64.b64encode(os.urandom(16)).decode()
        req = ('GET /%s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
               'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n' % (path, int(port), key))
        self.s.sendall(req.encode())
        resp = b''
        while b'\r\n\r\n' not in resp:
            resp += self.s.recv(4096)
        assert b'101' in resp.split(b'\r\n')[0], resp[:120]
        self.buf = resp.split(b'\r\n\r\n', 1)[1]
        self.i = 0

    def _recv(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise ConnectionError('ws closed')
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def _recv_msg(self):
        while True:
            b1, b2 = self._recv(2)
            opcode = b1 & 0x0F
            ln = b2 & 0x7F
            if ln == 126:
                ln = struct.unpack('>H', self._recv(2))[0]
            elif ln == 127:
                ln = struct.unpack('>Q', self._recv(8))[0]
            payload = self._recv(ln)
            if opcode == 1:
                return payload.decode('utf-8', 'replace')

    def _send_msg(self, obj):
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        ln = len(data)
        if ln < 126:
            hdr = struct.pack('!BB', 0x81, 0x80 | ln)
        elif ln < 65536:
            hdr = struct.pack('!BBH', 0x81, 0x80 | 126, ln)
        else:
            hdr = struct.pack('!BBQ', 0x81, 0x80 | 127, ln)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.s.sendall(hdr + mask + masked)

    def cmd(self, method, params=None):
        self.i += 1
        self._send_msg({'id': self.i, 'method': method, 'params': params or {}})
        while True:
            m = json.loads(self._recv_msg())
            if m.get('id') == self.i:
                return m

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def eval_js(ws, expr):
    try:
        r = ws.cmd('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
    except Exception:
        return None
    res = r.get('result', {}).get('result', {})
    if 'exceptionDetails' in r.get('result', {}) or res.get('subtype') == 'error':
        return None
    return res.get('value')


def main():
    site, prefix, text = sys.argv[1], sys.argv[2], sys.argv[3]
    lines = ['--- trial %s (%s) ---' % (site, time.strftime('%H:%M:%S'))]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        data = json.loads(opener.open(CDP_HTTP, timeout=15).read().decode('utf-8'))
    except Exception as e:
        open(OUT, 'w', encoding='utf-8').write('CDP list ERROR: %r\n' % e)
        return
    tgt = next((t for t in data if t.get('type') in ('page', 'webview')
                and t.get('url', '').startswith(prefix)), None)
    if not tgt:
        lines.append('target not found for prefix %s' % prefix)
        lines += ['  saw: ' + t.get('url', '')[:70] for t in data if t.get('type') in ('page', 'webview')]
        open(OUT, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
        return
    lines.append('target: %s | %s' % (tgt.get('title', '')[:40], tgt.get('url', '')[:70]))
    ws = WS(tgt['webSocketDebuggerUrl'])
    eval_js(ws, '''(() => { const el = document.querySelector('.editor[type="text/plain"], [contenteditable="true"], textarea');
      if (!el) return 'no-editor';
      el.scrollIntoView({block: "center", behavior: "instant"});
      return 'ok'; })()''')
    time.sleep(0.8)
    rect = eval_js(ws, FIND_EDITOR_JS)
    if rect:
        rect = json.loads(rect)
        lines.append('editor: <%s> cls=%s at (%d,%d) inview=%s' % (rect['tag'], rect['cls'][:40], rect['x'], rect['y'], rect.get('inview')))
        if rect.get('inview'):
            for tp in ('mousePressed', 'mouseReleased'):
                ws.cmd('Input.dispatchMouseEvent', {'type': tp, 'x': rect['x'], 'y': rect['y'],
                                                    'button': 'left', 'clickCount': 1})
            time.sleep(0.5)
        else:
            focused = eval_js(ws, FOCUS_JS)
            lines.append('js focus -> %s (element off-viewport)' % focused)
            time.sleep(0.4)
        ws.cmd('Input.insertText', {'text': text})
        time.sleep(0.6)
        for tp in ('rawKeyDown', 'keyDown'):
            ws.cmd('Input.dispatchKeyEvent', {'type': tp, 'windowsVirtualKeyCode': 13,
                                              'code': 'Enter', 'key': 'Enter', 'text': '\r'})
        ws.cmd('Input.dispatchKeyEvent', {'type': 'keyUp', 'windowsVirtualKeyCode': 13,
                                          'code': 'Enter', 'key': 'Enter'})
        time.sleep(2)
        resid = eval_js(ws, RESIDUAL_JS)
        lines.append('sent via native CDP; residual=%s' % resid)
    else:
        lines.append('editor not found')
    if rect:
        lines.append('waiting 25s for reply...')
        time.sleep(25)
        tail = eval_js(ws, 'document.body.innerText.slice(-1200)')
        lines.append('--- page text tail ---')
        lines += (tail or '').splitlines()[-25:]
    ws.close()
    open(OUT, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')


try:
    main()
except Exception as e:
    open(OUT, 'a', encoding='utf-8').write('FATAL: %r\n' % e)
