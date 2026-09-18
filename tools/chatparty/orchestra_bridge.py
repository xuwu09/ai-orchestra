# -*- coding: utf-8 -*-
"""
orchestra_bridge.py — ai-orchestra <-> ChatParty 桥（纯标准库，无 venv 依赖）

ChatParty 以 --remote-debugging-port=9222 启动（start_chatparty.bat 模板见本目录），
本桥经 CDP 控制各站 webview。程序路径走环境变量 ORCHESTRA_CHATPARTY_EXE。

用法：
  python orchestra_bridge.py status                 # 各站 target/标题/登录线索（组长选站用）
  python orchestra_bridge.py send <key> <message>   # 向指定站发消息（key 见 SITES，或直接给 URL 片段）
  python orchestra_bridge.py broadcast <msg>        # 全员发布+对账清单（only=k1,k2 / skip=k 过滤；站间 2-4s 节流）
  python orchestra_bridge.py read <key> [seconds]   # 读该站回复（页面文本尾部；seconds>0 时轮询等待文本稳定）
  python orchestra_bridge.py ensure                 # 幂等拉起 ChatParty（已跑则直接返回）

设计要点：
- WS 类抄自 cp_login_guard.py（无 Origin 头、纯标准库）——不依赖 websocket-client/venv
- 发送脚本与实测选择器同源：textarea 用 native setter + input 事件，
  contenteditable 用 execCommand，发送先按钮后 Enter（React 受控组件不认直赋值）
- read 返回 body.innerText 尾部，由 ai-orchestra 组长（LLM）自行解析回复内容

> 合规声明：本工具只通过 CDP 驱动你自己安装并登录的 ChatParty 副本；
> 不分发 ChatParty 程序本体或其修改版。
"""
import base64
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.request

CDP = 'http://127.0.0.1:9222'
EXE = os.environ.get('ORCHESTRA_CHATPARTY_EXE', r'<ChatParty.exe 绝对路径>')
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'orchestra_bridge.log')

# key: (url 片段, 显示名, 发送按钮候选选择器)
# 输入框通用探测：可见 textarea 优先，其次 contenteditable
SITES = {
    'deepseek':  ('chat.deepseek.com', 'DeepSeek', ''),
    'doubao':    ('doubao.com', '豆包', ''),
    'qwen':      ('qianwen.com', '通义千问', ''),
    'kimi':      ('kimi.com', 'Kimi', ''),
    'glm':       ('chatglm.cn', 'GLM', ''),
    'yuanbao':   ('yuanbao.tencent.com', '元宝', ''),
    'mimo':      ('xiaomimimo.com', 'MiMo', ''),
    'metaso':    ('metaso.cn', '秘塔', 'button.send-arrow-button, button[class*="send"]'),
    'nano':      ('n.cn', '纳米', 'button.send-btn, button[class*="send"]'),
    'wenxin':    ('baidu.com', '文心', 'button[id*="send"], button[class*="send"]'),
    'hunyuan':   ('aistudio.tencent.com', '混元/AIStudio', 'div.hy-chat-input-send-btn, button[class*="send"]'),
    'zhida':     ('zhihu.com', '知乎直答', 'button[class*="send"], button[type="submit"]'),
}


def log(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%m-%d %H:%M:%S ') + str(msg) + '\n')
    except Exception:
        pass


# ---------- 纯标准库 CDP（抄 cp_login_guard.py） ----------

def http_json(path, timeout=6):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return json.load(opener.open(CDP + path, timeout=timeout))


def cdp_list():
    for _ in range(3):
        try:
            return http_json('/json/list')
        except Exception:
            time.sleep(2)
    return []


class WS:
    """极简 WebSocket 客户端（纯标准库，仅本机 CDP 用，无 Origin 头）"""

    def __init__(self, url):
        assert url.startswith('ws://127.0.0.1:')
        rest = url[len('ws://127.0.0.1:'):]
        port, path = rest.split('/', 1)
        self.s = socket.create_connection(('127.0.0.1', int(port)), timeout=25)
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


def eval_js(ws, expr, await_promise=False):
    try:
        r = ws.cmd('Runtime.evaluate', {'expression': expr, 'returnByValue': True,
                                        'awaitPromise': await_promise})
    except Exception as e:
        return {'__err__': str(e)[:200]}
    res = r.get('result', {}).get('result', {})
    if 'exceptionDetails' in r.get('result', {}) or res.get('subtype') == 'error':
        desc = (r.get('result', {}).get('exceptionDetails', {}).get('exception', {})
                .get('description', '') or res.get('description', ''))
        return {'__err__': str(desc)[:300]}
    return res.get('value')


# ---------- 站点匹配 ----------

NOISE_URL_RE = re.compile(r'(\.js($|\?)|\.css($|\?)|sharedworker|serviceworker|/workers?/)', re.I)


def _is_noise(url):
    """worker/静态资源 target 不是可对话页面（如 qwen rmb.worker.js、doubao sharedworker）。"""
    return bool(NOISE_URL_RE.search(url))


def find_target(key):
    """按 key 找 CDP target：先 SITES 表 url 片段，再当作用户自填 url 片段。

    多候选时过滤僵尸 target（2026-09-18 deepseek 双 target 课）：
    title 含站点显示名 > 不含 > 空标题；同组内 title 更长（加载更完整）优先。
    返回值附 _candidates（全部候选 WS URL）供 _send_one 首选失败时自动换下一个。
    """
    frag, name = SITES.get(key, (key, key, ''))[:2]
    cands = []
    for t in cdp_list():
        url = t.get('url') or ''
        if 'index.html' in url or url.startswith('file://'):
            continue  # 主窗口不是站点
        if _is_noise(url):
            continue  # worker/静态资源不参与匹配
        if frag in url:
            cands.append(t)
    if not cands:
        return None
    if len(cands) > 1:
        def _rank(t):
            title = (t.get('title') or '').strip()
            if not title:
                return (2, 0)
            return (0, -len(title)) if name.lower() in title.lower() else (1, -len(title))
        cands.sort(key=_rank)
    if len(cands) == 1:
        return cands[0]
    t = dict(cands[0])  # 浅拷贝附元信息，不动原始 target
    t['_ambiguous'] = len(cands)
    t['_others'] = [((c.get('title') or '')[:30] + '|' + (c.get('url') or '')[:70])
                    for c in cands[1:]]
    t['_candidates'] = [c.get('webSocketDebuggerUrl') for c in cands]
    return t


# ---------- 注入 JS ----------

SEND_JS_TEMPLATE = r"""
(async function() {
  const MSG = __MSG_JSON__;
  const BTN_SEL = __BTN_SEL_JSON__;
  const HREF0 = location.href;

  function visible(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  // 1) 找输入框：可见 textarea 优先，其次 contenteditable
  let input = [...document.querySelectorAll('textarea')].find(visible);
  if (!input) input = [...document.querySelectorAll('[contenteditable="true"]')].find(visible);
  if (!input) return {ok: false, stage: 'input', err: 'no visible input'};
  input.focus();

  // 2) 设值（React 受控组件必须 native setter / execCommand）
  if (input.tagName === 'TEXTAREA' || input.tagName === 'INPUT') {
    const proto = input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(input, MSG);
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
  } else {
    input.focus();
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);
    document.execCommand('insertText', false, MSG);
    input.dispatchEvent(new InputEvent('input', {bubbles: true, data: MSG}));
  }

  await new Promise(r => setTimeout(r, 600));

  // 3) 发送：先点候选按钮（可见且非 disabled），失败再 Enter keydown
  function clickBtn() {
    if (!BTN_SEL) return false;
    for (const sel of BTN_SEL.split(',')) {
      const btn = [...document.querySelectorAll(sel.trim())].find(visible);
      if (btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
        btn.click();
        return true;
      }
    }
    return false;
  }
  const sentByBtn = clickBtn();
  if (!sentByBtn) {
    const ev = {bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13};
    input.dispatchEvent(new KeyboardEvent('keydown', ev));
    await new Promise(r => setTimeout(r, 120));
    input.dispatchEvent(new KeyboardEvent('keyup', ev));
  }

  // 4) 验证：发送成功≠站点接受。等 1.8s 看 URL 是否跳会话页 + 输入框是否清空。
  // 残留字先不清——留给 python 侧 trusted Enter 重试，仍失败才由 CLEAR_INPUT_JS 清。
  await new Promise(r => setTimeout(r, 1800));
  const urlChanged = location.href !== HREF0;
  const leftover = input.tagName === 'TEXTAREA' || input.tagName === 'INPUT'
    ? (input.value || '').length
    : (input.innerText || '').length;
  return {ok: true, by: sentByBtn ? 'button' : 'enter', input: input.tagName,
          url_changed: urlChanged, href: location.href.slice(0, 120), leftover: leftover};
})()
"""

READ_JS = r"""
(() => {
  const t = (document.body && document.body.innerText) || '';
  return {title: document.title.slice(0, 60), url: location.href.slice(0, 120),
          tail: t.replace(/\n{3,}/g, '\n\n').slice(-2600)};
})()
"""

FOCUS_INPUT_JS = r"""
(function(){var i=document.querySelector('textarea');
if(!i) i=document.querySelector('[contenteditable="true"]');
if(i) i.focus(); return !!i;})()
"""

BOX_JS = r"""
(function(){var i=document.querySelector('textarea');
if(!i || !i.offsetParent) i=document.querySelector('[contenteditable="true"]');
if(!i) return 'no-input';
i.scrollIntoView({block:'center'});
var r=i.getBoundingClientRect();
return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2});})()
"""

CLEAR_INPUT_JS = r"""
(function(){var i=document.querySelector('textarea');
if(!i) i=document.querySelector('[contenteditable="true"]');
if(!i) return 'no-input';
i.focus();
if(i.tagName==='TEXTAREA'||i.tagName==='INPUT'){
  var p=i.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(p,'value').set.call(i,'');
  i.dispatchEvent(new Event('input',{bubbles:true}));
}else{
  document.execCommand('selectAll',false,null);
  document.execCommand('delete',false,null);
}
return 'cleared';})()
"""


# ---------- 子命令 ----------

def cmd_status():
    targets = cdp_list()
    if not targets:
        print(json.dumps({'chatparty_alive': False,
                          'hint': '运行 start_chatparty.bat 拉起（CDP 9222）'}, ensure_ascii=False))
        return 0
    open_sites = []
    main_t = None
    for t in targets:
        url = t.get('url') or ''
        if 'index.html' in url or url.startswith('file://'):
            main_t = t
            continue
        if _is_noise(url):
            continue  # worker/静态资源不进 open_sites
        matched = None
        for key, (frag, name, _btn) in SITES.items():
            if frag in url:
                matched = {'key': key, 'name': name}
                break
        open_sites.append({'key': (matched or {}).get('key'), 'name': (matched or {}).get('name', '?'),
                           'title': (t.get('title') or '')[:24], 'url': url[:80]})
    # 主窗口探针：webview 元素（卡片开了但 target 慢的情况）
    wv_count = None
    if main_t:
        try:
            ws = WS(main_t['webSocketDebuggerUrl'])
            v = eval_js(ws, "[...document.querySelectorAll('webview')].length")
            wv_count = v if not isinstance(v, dict) else None
            ws.close()
        except Exception:
            pass
    out = {'chatparty_alive': True, 'webviews_in_dom': wv_count, 'open_sites': open_sites,
           'known_keys': sorted(SITES.keys())}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def _key_or_frag(key):
    if key in SITES:
        return key
    # 允许直接传 url 片段（如自定义站）
    for k, (frag, _n, _b) in SITES.items():
        if frag in key or key in frag:
            return k
    return key  # 当作自定义 url 片段


def _send_via(ws_url, key, message):
    """对给定 CDP target WS 发送（发送主体）。返回 out dict。"""
    js = SEND_JS_TEMPLATE.replace('__MSG_JSON__', json.dumps(message, ensure_ascii=False)) \
                         .replace('__BTN_SEL_JSON__', json.dumps(SITES.get(key, ('', '', ''))[2]))
    try:
        ws = WS(ws_url)
        r = eval_js(ws, js, await_promise=True)
        # 5) 假成功重试：富文本编辑器（Lexical/tiptap 类）拒收合成事件，且 execCommand
        #    填的字不在编辑器 state 里——Enter 也没用。走全 trusted 管线（trial_send.py
        #    在 Kimi 验证的路线）：清残留 → trusted click 编辑器中心 → Input.insertText
        #    重填 → trusted Enter。残留 >8 字才触发（挡掉豆包会话页 URL 不变的误报）。
        if isinstance(r, dict) and r.get('ok') and r.get('url_changed') is False \
                and (r.get('leftover') or 0) > 8:
            try:
                eval_js(ws, CLEAR_INPUT_JS)
                time.sleep(0.3)
                box = eval_js(ws, BOX_JS)
                if isinstance(box, str):
                    b = json.loads(box)
                    for tp in ('mousePressed', 'mouseReleased'):
                        ws.cmd('Input.dispatchMouseEvent',
                               {'type': tp, 'x': int(b['x']), 'y': int(b['y']),
                                'button': 'left', 'clickCount': 1})
                    time.sleep(0.4)
                    ws.cmd('Input.insertText', {'text': message})
                    time.sleep(0.5)
                    for tp in ('rawKeyDown', 'keyDown'):
                        ws.cmd('Input.dispatchKeyEvent',
                               {'type': tp, 'windowsVirtualKeyCode': 13,
                                'code': 'Enter', 'key': 'Enter', 'text': '\r'})
                    ws.cmd('Input.dispatchKeyEvent',
                           {'type': 'keyUp', 'windowsVirtualKeyCode': 13,
                            'code': 'Enter', 'key': 'Enter'})
                    time.sleep(1.8)
                    after = eval_js(ws, 'location.href')
                    r['trusted_retry'] = isinstance(after, str) and after != r.get('href')
                    if r['trusted_retry']:
                        r['url_changed'] = True
                        r['href'] = str(after)[:120]
            except Exception as e2:
                r['trusted_retry_error'] = str(e2)[:100]
            if not r.get('url_changed'):
                eval_js(ws, CLEAR_INPUT_JS)  # 仍失败：清残留，避免污染下一轮
        # 6) 成功也清残留（2026-09-18 metaso 课：url_changed=true 但框留 240 字，污染下一轮）
        if isinstance(r, dict) and r.get('ok') and r.get('url_changed') \
                and (r.get('leftover') or 0) > 0:
            try:
                if eval_js(ws, CLEAR_INPUT_JS) == 'cleared':
                    r['cleaned'] = True
            except Exception:
                pass
        ws.close()
    except Exception as e:
        r = {'ok': False, 'error': str(e)[:200]}
    out = {'ok': bool(r and not isinstance(r, dict) or (isinstance(r, dict) and r.get('ok'))),
           'site': key, 'detail': r}
    # 发送成功≠站点接受：url_changed=False 时输入框字已清，需重发或换站（2026-09-18 千问假成功课）
    if isinstance(r, dict) and r.get('ok') and r.get('url_changed') is False:
        out['url_changed'] = False
        out['note'] = 'front-end submit only; editor rejected synthetic Enter/button — verify via read, likely resend'
    elif isinstance(r, dict) and r.get('url_changed'):
        out['url_changed'] = True
    return out


def _send_one(key, message):
    """向单站发送（cmd_send / cmd_broadcast 共用核心）。返回 out dict，不打印。

    多候选 target（deepseek 双 webview）时首选失败自动换下一个候选重试——
    不猜谁是僵尸，能发的那个总会成功；成功所用候选序号回填 used_candidate。
    """
    key = _key_or_frag(key)
    tgt = find_target(key)
    if not tgt:
        return {'ok': False, 'site': key,
                'error': f'no cdp target for {key}（卡片未开或站名不对，先 status 看 open_sites）'}
    cands = tgt.get('_candidates') or [tgt.get('webSocketDebuggerUrl')]
    out, ci = {}, 0
    for ci, cu in enumerate(cands):
        out = _send_via(cu, key, message)
        if out.get('ok') or ci == len(cands) - 1:
            break
    if len(cands) > 1:
        out['ambiguous_targets'] = len(cands)  # 僵尸过滤已生效，附候选数备查
        if out.get('ok') and ci > 0:
            out['used_candidate'] = ci  # 首选 target 发送失败、第 N 候选成功的实锤
    return out


def cmd_send(key, message):
    out = _send_one(key, message)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    log(f"send {key}: {json.dumps(out, ensure_ascii=False)[:200]}")
    return 0 if out['ok'] else 1


def cmd_read(key, wait_seconds=0):
    key = _key_or_frag(key)
    tgt = find_target(key)
    if not tgt:
        print(json.dumps({'ok': False, 'error': f'no cdp target for {key}'}, ensure_ascii=False))
        return 1
    best = None
    deadline = time.time() + max(0, int(wait_seconds))
    stable, last = 0, None
    try:
        ws = WS(tgt['webSocketDebuggerUrl'])
        while True:
            r = eval_js(ws, READ_JS)
            if isinstance(r, dict) and r.get('tail') is not None:
                if r['tail'] == last:
                    stable += 1
                else:
                    stable, last = 0, r['tail']
                best = r
            if time.time() >= deadline or (wait_seconds and stable >= 3 and time.time() > deadline - wait_seconds + 8):
                break
            if not wait_seconds:
                break
            time.sleep(2)
        ws.close()
    except Exception as e:
        print(json.dumps({'ok': False, 'error': str(e)[:200]}, ensure_ascii=False))
        return 1
    if best is None:
        print(json.dumps({'ok': False, 'error': 'read failed'}, ensure_ascii=False))
        return 1
    print(json.dumps({'ok': True, 'site': key, **best}, ensure_ascii=False, indent=1))
    return 0


def cmd_broadcast(message, only=None, skip=None, gap=(2.0, 4.0)):
    """全员发布+对账（2026-09-18 改进项落地）：逐站发送，站间 2-4s 随机节流
    （防风控，同 foreign_cli v1.3.0 参数），末尾输出四态对账清单——
    - sent       已送达（URL 跳转确认，或 trusted fallback 重试成功）
    - verify     已提交但 URL 未变且残留少——可能已在会话页（豆包），read 验证
    - suspicious 疑似假成功（URL 未变且残留多，fallback 未救回）——read 验证后重发或换站
    - missing    无 CDP target（卡片未开）或发送异常
    """
    import random
    keys = [k for k in SITES
            if (not only or k in only) and (not skip or k not in skip)]
    sent, verify, suspicious, missing = [], [], [], []
    for i, k in enumerate(keys):
        if i:
            time.sleep(random.uniform(*gap))
        out = _send_one(k, message)
        d = out.get('detail') if isinstance(out.get('detail'), dict) else {}
        if not out.get('ok'):
            missing.append({'key': k,
                            'reason': (out.get('error') or d.get('error') or 'send failed')[:80]})
        elif out.get('url_changed') is True:
            sent.append(k)
        elif (d.get('leftover') or 0) > 8:
            suspicious.append({'key': k, 'leftover': d.get('leftover'),
                               'trusted_retry': bool(d.get('trusted_retry'))})
        else:
            verify.append(k)
    out = {'total': len(keys), 'sent': sent, 'verify': verify,
           'suspicious': suspicious, 'missing': missing,
           'hint': ('missing=未送达（开卡/补发）；suspicious=疑似假成功（read 验证后重发或换站）；'
                    'verify=URL 未变但残留少（可能已在会话页，read 确认）')}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    log(f"broadcast: sent={sent} verify={verify} "
        f"susp={[s['key'] for s in suspicious]} miss={[m['key'] for m in missing]}")
    return 0 if not missing and not suspicious else 1


def _chatparty_process_running():
    """tasklist 探测 ChatParty.exe 是否在跑（mbcs 解码，纯标准库）。"""
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ChatParty.exe'],
                             capture_output=True).stdout.decode('mbcs', errors='replace')
        return 'ChatParty.exe' in out
    except Exception:
        return False


def cmd_ensure():
    """幂等拉起：CDP 9222 在线即返回；否则 bat 拉起并轮询。
    注意：若本脚本运行在沙箱/受限 job 中，拉起的进程可能随会话回收——
    常驻方案 = 开机自启（任务计划/VBS 静默拉启动器 bat）或手动双击启动器。"""
    try:
        http_json('/json/version', timeout=3)
        print(json.dumps({'alive': True, 'note': 'CDP 9222 already up'}, ensure_ascii=False))
        return 0
    except Exception:
        pass
    bat = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'start_chatparty.bat')
    try:
        subprocess.Popen(['cmd', '/c', bat], creationflags=0x00000008 | 0x00000200)
    except Exception as e:
        print(json.dumps({'alive': False, 'error': str(e)[:120],
                          'note': '请手动运行 start_chatparty.bat'}, ensure_ascii=False))
        return 1
    for _ in range(15):
        time.sleep(2)
        try:
            http_json('/json/version', timeout=3)
            print(json.dumps({'alive': True, 'via': 'bat',
                              'note': '若由沙箱会话拉起，会话结束后可能被回收；建议开机自启常驻'},
                             ensure_ascii=False))
            return 0
        except Exception:
            continue
    running = _chatparty_process_running()
    if running:
        note = ('ChatParty 在跑但无 CDP 9222（可能直接双击 exe 启动，官方 exe 不内置 CDP）——'
                '请关闭 ChatParty 后用启动器 bat 重开以获得遥控通道')
    else:
        note = '拉起超时。常驻方案：手动运行启动器 bat 或配置开机自启'
    print(json.dumps({'alive': False, 'process_running': running, 'note': note},
                     ensure_ascii=False))
    return 1


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 0
    cmd = args[0]
    if cmd == 'status':
        return cmd_status()
    if cmd == 'send' and len(args) >= 3:
        return cmd_send(args[1], ' '.join(args[2:]))
    if cmd == 'broadcast' and len(args) >= 2:
        only = skip = None
        for a in args[2:]:
            if a.startswith('only='):
                only = {x for x in a[5:].split(',') if x}
            elif a.startswith('skip='):
                skip = {x for x in a[5:].split(',') if x}
        return cmd_broadcast(args[1], only=only, skip=skip)
    if cmd == 'read' and len(args) >= 2:
        return cmd_read(args[1], int(args[2]) if len(args) > 2 else 0)
    if cmd == 'ensure':
        return cmd_ensure()
    print(__doc__)
    return 1


if __name__ == '__main__':
    sys.exit(main())
