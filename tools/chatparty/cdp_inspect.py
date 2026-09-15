# -*- coding: utf-8 -*-
"""
CDP 巡检三合一（纯标准库，无第三方依赖）：
  python cdp_inspect.py list                列出全部 target（page/webview/iframe）
  python cdp_inspect.py probe <url前缀>     探测该页面的输入框/登录指示器
  python cdp_inspect.py shot <url前缀> <out.png>   截图该页面

用途：把一个新站点接入登录看门狗 / 顾问通道之前，先用本脚本摸清它的
DOM 结构（编辑器选择器、登录态在 cookie 还是 localStorage），再校准
cp_login_guard.py 里的 SITES / CUSTOM_HOST_MAP 指标。

坑位提醒：
- CDP HTTP 请求必须禁代理（ProxyHandler({})），否则回环请求会被系统代理劫持超时
- WebSocket 不带 Origin 头（部分 CDP 端点对带 Origin 的请求返回 403）
- 多站聚合应用的 webview 常以小窗渲染，编辑器可能在视口外（y<0）——属正常现象
"""
import sys, json, os, time, base64, struct, socket, urllib.request

CDP_HTTP = os.environ.get('CDP_HTTP', 'http://127.0.0.1:9222')


def cdp_list():
    """列 target（禁代理）"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    raw = opener.open(CDP_HTTP + '/json/list', timeout=15).read().decode('utf-8')
    return json.loads(raw)


class WS:
    """极简 WebSocket 客户端（纯标准库，仅本机 CDP 用，无 Origin 头）"""
    def __init__(self, url):
        assert url.startswith('ws://127.0.0.1:')
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


def find_target(prefix):
    for t in cdp_list():
        if t.get('type') in ('page', 'webview') and prefix in t.get('url', ''):
            return t
    return None


def eval_js(ws, expr):
    r = ws.cmd('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
    res = r.get('result', {}).get('result', {})
    return res.get('value')


PROBE_JS = '''(() => {
  const vis = el => { const r = el.getBoundingClientRect();
    return r.width > 80 && r.height > 12; };
  const ces = [...document.querySelectorAll('[contenteditable="true"], .editor[type="text/plain"]')];
  const tas = [...document.querySelectorAll('textarea')];
  const inps = [...document.querySelectorAll('input[type="text"], input:not([type])')];
  const fmt = el => { const r = el.getBoundingClientRect();
    return {tag: el.tagName, cls: String(el.className || '').slice(0, 70),
            rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
            ph: el.getAttribute('placeholder') || el.getAttribute('data-placeholder') || ''}; };
  return {
    ready: document.readyState,
    url: location.href.slice(0, 100),
    editors: [...ces.filter(vis), ...tas.filter(vis)].slice(0, 5).map(fmt),
    hidden_editors: [...ces, ...tas].filter(e => !vis(e)).slice(0, 3).map(fmt),
    text_inputs: inps.filter(vis).slice(0, 5).map(fmt),
    body_text_len: document.body ? document.body.innerText.length : -1,
    cookies: document.cookie.split('; ').map(c => c.split('=')[0]).filter(Boolean).slice(0, 40),
    ls_keys: Object.keys(localStorage).slice(0, 60)
  };
})()'''


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    mode = sys.argv[1]
    if mode == 'list':
        data = cdp_list()
        for t in data:
            if t.get('type') in ('page', 'webview', 'iframe'):
                print('[%s] %s | %s' % (t.get('type'), (t.get('title') or '')[:45], t.get('url', '')[:95]))
        print('total: %d' % len(data))
        return
    if len(sys.argv) < 3:
        print('need <url-prefix>')
        return
    prefix = sys.argv[2]
    tgt = find_target(prefix)
    if not tgt:
        print('no target matching %r' % prefix)
        return
    print('target: %s | %s' % ((tgt.get('title') or '')[:45], tgt.get('url', '')[:95]))
    ws = WS(tgt['webSocketDebuggerUrl'])
    try:
        if mode == 'probe':
            info = eval_js(ws, PROBE_JS)
            print(json.dumps(info, ensure_ascii=False, indent=1))
        elif mode == 'shot':
            out = sys.argv[3] if len(sys.argv) > 3 else 'shot.png'
            r = ws.cmd('Page.captureScreenshot', {'format': 'png'})
            with open(out, 'wb') as f:
                f.write(base64.b64decode(r['result']['data']))
            print('saved: %s' % out)
        else:
            print('unknown mode: %s' % mode)
    finally:
        ws.close()


if __name__ == '__main__':
    main()
