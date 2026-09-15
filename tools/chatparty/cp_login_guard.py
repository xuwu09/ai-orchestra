# -*- coding: utf-8 -*-
"""
ChatParty 登录看门狗 v3
- 每 45 秒巡检：内置站用校准过的指标（CDP cookie 名单 + localStorage），自定义站用内置 host 指标
- 已登录时持续备份 cookie + localStorage 到 guard-backups/（只在登录态备份）
- 掉登录自动恢复：注入 cookie + LS -> 刷新该 webview -> 复核（每站每小时最多 3 次）
- 自定义站配置丢失：强制回写（含 custom-providers 为 "[]" 的情况）-> 刷新主窗口（10 分钟冷却）
- 单实例锁：guard.lock，重复启动自动退出
- 日志: guard.log
"""
import urllib.request, json, os, time, traceback, ctypes
import socket, base64, struct

BASE = os.path.dirname(os.path.abspath(__file__))  # 日志/备份/锁都在脚本同目录生成
BKDIR = os.path.join(BASE, 'guard-backups')
LOG = os.path.join(BASE, 'guard.log')
LOCK = os.path.join(BASE, 'guard.lock')
CDP = 'http://127.0.0.1:9222'
CFG_FALLBACK = os.path.join(BASE, 'custom-providers-backup.json')  # 可选：主窗口配置兜底源（无则忽略）
os.makedirs(BKDIR, exist_ok=True)


def pid_alive(pid):
    try:
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            k.CloseHandle(h)
            return True
        return False
    except Exception:
        return False


def acquire_lock():
    """心跳锁：2 分钟内有更新才算被持有；返回 True=拿到锁"""
    if os.path.isfile(LOCK):
        try:
            if time.time() - os.path.getmtime(LOCK) < 120:
                return False
        except Exception:
            pass
    _touch_lock()
    return True


def _touch_lock():
    try:
        with open(LOCK, 'w') as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def release_lock():
    try:
        if os.path.isfile(LOCK):
            os.remove(LOCK)
    except Exception:
        pass


# key, url_frag, auth cookie names (checked via CDP, HttpOnly visible), js indicator (optional)
SITES = [
    ('deepseek', 'deepseek.com', [],
     '!!localStorage.getItem("userToken") && !location.pathname.startsWith("/sign_in")'),
    ('kimi', 'kimi.com', [],
     '!!localStorage.getItem("access_token") || !!localStorage.getItem("msh_user_id")'),
    ('qianwen', 'qianwen.com', ['tongyi_sso_ticket'], None),
    ('doubao', 'doubao.com', ['oauth_token_v2', 'multi_sids', 'sid_tt', 'sessionid'], None),
    ('glm', 'chatglm.cn', ['chatglm_token'], None),
    ('yuanbao', 'yuanbao.tencent.com', ['hy_token'], None),
    ('mimo', 'xiaomimimo.com', ['xiaomichatbot_serviceToken'], None),
]
CUSTOM_HOST_MAP = [
    ('metaso.cn', ['uid', 'sid'], None),
    ('n.cn', ['Auth-Token'], None),
    ('wenxin.baidu.com', ['H_WISE_SIDS'], None),
    ('tiangong.cn', ['(use-js)',], 'false'),
]

def log(msg):
    line = '%s %s' % (time.strftime('%m-%d %H:%M:%S'), msg)
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass
    print(line, flush=True)

def cdp_list():
    for _ in range(3):
        try:
            return json.load(urllib.request.urlopen(CDP + '/json/list', timeout=6))
        except Exception:
            time.sleep(3)
    return []

class WS:
    """极简 WebSocket 客户端（纯标准库，仅本机 CDP 用，无 Origin 头）"""
    def __init__(self, url):
        assert url.startswith('ws://127.0.0.1:')
        rest = url[len('ws://127.0.0.1:'):]
        port, path = rest.split('/', 1)
        self.s = socket.create_connection(('127.0.0.1', int(port)), timeout=12)
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

def get_cookies(ws, url):
    try:
        r = ws.cmd('Network.getCookies', {'urls': [url]})
        return r.get('result', {}).get('cookies', [])
    except Exception:
        return []

def backup_ls(ws):
    return eval_js(ws, '''(() => { const o = {};
      for (let i=0;i<localStorage.length;i++){const k=localStorage.key(i);o[k]=localStorage.getItem(k);}
      return JSON.stringify(o); })()''') or {}

def backup_site(key, url, ws):
    ls = backup_ls(ws)
    if isinstance(ls, str):
        try:
            ls = json.loads(ls)
        except Exception:
            ls = {}
    data = {'site': key, 'url': url, 'time': time.strftime('%m-%d %H:%M:%S'),
            'cookies': get_cookies(ws, url), 'ls': ls}
    if not data['cookies'] and not data['ls']:
        return False
    with open(os.path.join(BKDIR, 'site-%s.json' % key), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    return True

def load_backup(key):
    p = os.path.join(BKDIR, 'site-%s.json' % key)
    if os.path.isfile(p):
        try:
            return json.load(open(p, encoding='utf-8'))
        except Exception:
            pass
    return None

def inject_cookies(ws, url, cookies):
    ok = 0
    for c in cookies:
        params = {'url': url, 'name': c['name'], 'value': c['value']}
        for k in ('domain', 'path', 'secure', 'httpOnly'):
            if c.get(k) is not None:
                params[k] = c[k]
        if c.get('expires') and c['expires'] not in (-1, 0):
            params['expires'] = c['expires']
        try:
            r = ws.cmd('Network.setCookie', params)
            if r.get('result', {}).get('success'):
                ok += 1
        except Exception:
            pass
    return ok

def inject_ls(ws, ls):
    if not ls:
        return 0
    if isinstance(ls, str):
        try:
            ls = json.loads(ls)
        except Exception:
            return 0
    if not isinstance(ls, dict):
        return 0
    n = eval_js(ws, '''(() => { const o = %s; let n = 0;
        for (const k of Object.keys(o)) { if (typeof o[k] === "string") { try { localStorage.setItem(k, o[k]); n++; } catch(e) {} } }
        return n; })()''' % json.dumps(ls, ensure_ascii=False))
    return n or 0

def backup_main_state(main_ws):
    val = eval_js(main_ws, '''(() => { const o = {};
        for (let i=0;i<localStorage.length;i++){const k=localStorage.key(i);o[k]=localStorage.getItem(k);}
        return JSON.stringify(o); })()''')
    if val:
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                return False
        with open(os.path.join(BKDIR, 'main-localstorage.json'), 'w', encoding='utf-8') as f:
            json.dump(val, f, ensure_ascii=False)
        return True
    return False

def _load_cfg_fallback():
    """旧手动备份里取 custom-providers / selected-providers，兜底用"""
    try:
        d = json.load(open(CFG_FALLBACK, encoding='utf-8'))
        out = {}
        for k in ('custom-providers', 'selected-providers'):
            if k in d:
                v = d[k]
                out[k] = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        # 过滤掉已删除的天工
        cp = out.get('custom-providers')
        if cp:
            try:
                lst = json.loads(cp)
                lst = [c for c in lst if 'tiangong' not in (c.get('url') or '')]
                out['custom-providers'] = json.dumps(lst, ensure_ascii=False)
            except Exception:
                pass
        return out
    except Exception:
        return {}


def restore_main_state(main_ws):
    p = os.path.join(BKDIR, 'main-localstorage.json')
    if not os.path.isfile(p):
        return False
    try:
        saved = json.load(open(p, encoding='utf-8'))
    except Exception:
        return False
    if isinstance(saved, str):
        try:
            saved = json.loads(saved)
        except Exception:
            return False
    if not isinstance(saved, dict):
        return False
    # v3: 若备份里没有 custom-providers（曾被空态覆盖），从兜底配置合并
    if not saved.get('custom-providers'):
        fb = _load_cfg_fallback()
        if fb:
            saved.update(fb)
    n = eval_js(main_ws, '''(() => { const o = %s; let n = 0;
        for (const k of Object.keys(o)) {
          if (typeof o[k] !== "string") continue;
          if (localStorage.getItem(k) !== o[k]) { localStorage.setItem(k, o[k]); n++; }
        }
        return n; })()''' % json.dumps(saved, ensure_ascii=False))
    return bool(n)

def site_indicators(url, customs):
    """return (key, cookie_names, js_expr)"""
    for key, frag, cnames, js in SITES:
        if frag in url:
            return key, cnames, js
    for frag, cnames, js in CUSTOM_HOST_MAP:
        if frag in url:
            return 'custom-' + frag.split('.')[0], cnames, js
    for c in customs or []:
        cu = c.get('url') or ''
        if cu and url.startswith(cu):
            return 'custom-' + (c.get('id') or cu)[:20], [], None
    return None, None, None

restore_counts = {}
last_full_backup = 0.0
last_main_reload = 0.0

def can_restore(key):
    hour = int(time.time() // 3600)
    h, c = restore_counts.get(key, (hour, 0))
    if h != hour:
        h, c = hour, 0
    if c >= 3:
        restore_counts[key] = (h, c)
        return False
    restore_counts[key] = (h, c + 1)
    return True

def main():
    global last_full_backup, last_main_reload
    log('=== login guard v3 started (pid %s) ===' % os.getpid())
    if not acquire_lock():
        log('another guard instance is running (lock held) -> exit')
        return
    try:
        _loop()
    finally:
        release_lock()

def _loop():
    global last_full_backup, last_main_reload
    while True:
        main_ws = None
        try:
            targets = cdp_list()
            mains = [t for t in targets if t.get('type') == 'page']
            if mains:
                main_ws = WS(mains[0]['webSocketDebuggerUrl'])
            customs = []
            if main_ws:
                raw = eval_js(main_ws, 'localStorage.getItem("custom-providers")')
                try:
                    customs = json.loads(raw) if raw else []
                except Exception:
                    customs = []
                if not customs and os.path.isfile(os.path.join(BKDIR, 'main-localstorage.json')):
                    # v3: 空态时绝不做 backup_main_state（防好备份被空配置覆盖）
                    if time.time() - last_main_reload < 600:
                        log('WARN custom-providers empty (reload cooling down)')
                    else:
                        log('WARN custom-providers empty -> force restore work progress + reload main')
                        if restore_main_state(main_ws):
                            last_main_reload = time.time()
                            main_ws.cmd('Page.reload')
                            log('main reloaded after config restore')
                            time.sleep(15)
                            targets = cdp_list()
                            mains = [t for t in targets if t.get('type') == 'page']
                            main_ws = WS(mains[0]['webSocketDebuggerUrl']) if mains else None
                        else:
                            log('WARN config restore wrote nothing (no source?)')
                elif customs and time.time() - last_full_backup > 600:
                    if backup_main_state(main_ws):
                        last_full_backup = time.time()
                        log('work progress backed up (%d custom sites)' % len(customs))

            for t in targets:
                if t.get('type') != 'webview':
                    continue
                url = t.get('url') or ''
                if not url.startswith('http'):
                    continue
                key, cnames, js = site_indicators(url, customs)
                if key is None or (not cnames and not js):
                    continue
                try:
                    ws = WS(t['webSocketDebuggerUrl'])
                except Exception:
                    continue
                try:
                    logged_in = False
                    if cnames:
                        names = set(c['name'] for c in get_cookies(ws, url))
                        logged_in = any(n in names for n in cnames)
                    if not logged_in and js:
                        v = eval_js(ws, '(() => { try { return %s } catch(e) { return false } })()' % js)
                        logged_in = bool(v)
                    if logged_in:
                        backup_site(key, url, ws)
                    else:
                        bak = load_backup(key)
                        if bak and (bak.get('cookies') or bak.get('ls')):
                            if not can_restore(key):
                                log('WARN %s logged out, restore limit reached' % key)
                                continue
                            log('DETECT %s logged out -> restore (cookies=%d ls=%d)'
                                % (key, len(bak.get('cookies', [])), len(bak.get('ls', {}))))
                            n1 = inject_cookies(ws, url, bak.get('cookies', []))
                            n2 = inject_ls(ws, bak.get('ls', {}))
                            try:
                                ws.cmd('Page.reload')
                            except Exception:
                                pass
                            log('restored %s: %d cookies + %d ls keys, reload -> recheck next cycle'
                                % (key, n1, n2))
                        else:
                            if can_restore(key):
                                log('INFO %s logged out, no backup yet (needs manual login once)' % key)
                finally:
                    ws.close()
        except Exception:
            log('loop error: ' + traceback.format_exc(limit=2).replace('\n', ' | ')[:200])
        finally:
            if main_ws:
                main_ws.close()
        _touch_lock()
        time.sleep(45)

if __name__ == '__main__':
    main()
