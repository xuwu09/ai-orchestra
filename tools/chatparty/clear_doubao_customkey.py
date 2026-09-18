# -*- coding: utf-8 -*-
"""
clear_doubao_customkey.py — 清豆包 custom script 的 sendMessage（消「1+11+1」竞态）

背景（2026-09-18 v4.8）：
  主进程 v4.8 已把豆包并入 trusted 三重门分支，但 custom script 仍在并行执行——
  custom 先 execCommand 填字，trusted 1500ms 后 cleared 清空重填，竞态时输入框
  短暂出现「1+11+1」（发送仍成功，纯观感问题）。
  custom script 存在主窗口 localStorage：chatallai_custom_scripts → doubao →
  scripts.sendMessage。删掉该字段即消除竞态；**getLLMLastMessage 保留**（读回复用）。
  nano/qwen/hunyuan 的 sendMessage 不动（trusted 分支 fall-through 并行模式，无副作用，
  且站点再改版时 custom 仍是后备）。

用法（ChatParty 在跑时执行）：
  python clear_doubao_customkey.py          # 探查+清 doubao.sendMessage
  python clear_doubao_customkey.py --list   # 只列出各站 custom script 概览，不动手

⚠️ 生效条件：localStorage 改动需 ChatParty 重启才进 store——
   重启会丢全部 webview 会话，请择时手动重启（关闭后双击启动器 bat）。

复用 orchestra_bridge 的 CDP 基础设施（同目录 import，纯标准库）。
"""
import json
import sys

from orchestra_bridge import cdp_list, WS, eval_js, log

STORE_KEY = 'chatallai_custom_scripts'


def find_main_window():
    for t in cdp_list():
        url = t.get('url') or ''
        if 'index.html' in url or url.startswith('file://'):
            return t
    return None


def main():
    list_only = '--list' in sys.argv
    t = find_main_window()
    if not t:
        print(json.dumps({'ok': False, 'error': 'CDP 9222 找不到主窗口（index.html）——'
                          'ChatParty 是否经启动器 bat 拉起？'}, ensure_ascii=False))
        return 1
    ws = WS(t['webSocketDebuggerUrl'])
    try:
        raw = eval_js(ws, f"localStorage.getItem({json.dumps(STORE_KEY)})")
        if not isinstance(raw, str):
            print(json.dumps({'ok': False, 'error': f'{STORE_KEY} 不存在或读取失败'},
                             ensure_ascii=False))
            return 1
        data = json.loads(raw)
        overview = {name: sorted((v.get('scripts') or {}).keys())
                    for name, v in data.items() if isinstance(v, dict)}
        out = {'ok': True, 'mode': 'list' if list_only else 'clean',
               'entries': overview}
        if list_only:
            print(json.dumps(out, ensure_ascii=False, indent=1))
            return 0
        entry = data.get('doubao')
        scripts = (entry or {}).get('scripts') or {}
        if 'sendMessage' not in scripts:
            out['removed'] = None
            out['note'] = 'doubao.scripts.sendMessage 本就不存在，无需清理'
            print(json.dumps(out, ensure_ascii=False, indent=1))
            return 0
        del scripts['sendMessage']  # getLLMLastMessage 保留（读回复依赖）
        new_raw = json.dumps(data, ensure_ascii=False)
        expr = (f"localStorage.setItem({json.dumps(STORE_KEY)}, "
                f"{json.dumps(new_raw)}); 'written'")
        w = eval_js(ws, expr)
        back = eval_js(ws, f"localStorage.getItem({json.dumps(STORE_KEY)})")
        gone = ('sendMessage' not in str(json.loads(back).get('doubao', {}).get('scripts', {}))
                if isinstance(back, str) else False)
        out['removed'] = 'doubao.scripts.sendMessage'
        out['write_result'] = w
        out['verify_gone'] = gone
        out['note'] = ('已清 doubao.sendMessage（getLLMLastMessage 保留）。生效需重启 ChatParty'
                       '（会丢全部 webview 会话，择时手动重启：关闭后双击启动器 bat）')
        log(f"clear_doubao_customkey: removed doubao.scripts.sendMessage, gone={gone}")
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0 if gone else 1
    finally:
        ws.close()


if __name__ == '__main__':
    sys.exit(main())
