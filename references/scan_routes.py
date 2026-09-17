"""扫描本地 AI 客户端 → 生成 routes.yaml（ai-orchestra 派发路由表）。

安装 skill 时或成员变化后运行一次。产物放在本目录 routes.yaml。

全部本机路径 / 端口集中在顶部 CONFIG 区——按你的实际安装位置改这里，
脚本其余部分不用动。也可用环境变量覆盖（见 CONFIG 注释）。

判据（优先级 = 派发优先级）：
  1 official-cli  客户端自带 CLI/无头模式
  2 cdp-client    Chromium 系客户端挂 --remote-debugging-port
  3 opencli-web   无客户端但有网页版 + OpenCLI Browser Bridge
  4 clipboard     剪贴板人肉中转（兜底，永远可用）

用法：
  python scan_routes.py            # 扫描并写 routes.yaml
  python scan_routes.py --print    # 只打印不落盘
"""

import json
import os
import socket
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "routes.yaml")

# ═════════════════════════ CONFIG（按本机实际修改） ═════════════════════════

# 干活组 CLI agent：cli 路径 + 日志路径（用于探活）
AGENT_CLI = os.environ.get("ORCHESTRA_AGENT_CLI", r"<干活组 CLI 绝对路径>")
AGENT_LOG = os.environ.get("ORCHESTRA_AGENT_LOG", r"<agent 日志绝对路径>")

# CDP 客户端成员：exe 探测候选、CDP 端口、幂等启动 bat、CLI 包装脚本
# 格式：key -> dict；不需要的成员整段删掉即可
CDP_CLIENTS = {
    "doubao": {
        "exe_candidates": [r"<豆包安装目录>\Doubao.exe"],
        "cdp_port": 9225,
        "launcher": r"<start_doubao_cdp.bat 绝对路径>",
        "cli": None,  # 有 CLI 包装就填路径
        "note": "cdp_alive=false 是待拉起不是不可用：ensure/幂等 bat 拉起后再判；网页备选（ProseMirror 需粘贴法）",
    },
    "qianwen": {
        "exe_candidates": [r"<千问安装目录>\qianwen.exe"],
        "cdp_port": 9226,
        "launcher": r"<start_qianwen_cdp.bat 绝对路径>",
        "cli": r"<qianwen_cli.py 绝对路径>",
        "note": "编辑器不认 JS 合成 Enter，必须走 CDP 原生 Input 管线（dispatchKeyEvent）；先 ensure/幂等 bat 再判，别直接降级",
    },
}

# 网页站聚合（ChatParty 类多站应用；不需要就置 None）
CHATPARTY = {
    "exe": os.environ.get("ORCHESTRA_CHATPARTY_EXE", r"<ChatParty.exe 绝对路径>"),
    "launcher": os.environ.get("ORCHESTRA_CHATPARTY_BAT", r"<启动器 bat 绝对路径>"),
    "cdp_port": 9222,
}

# 外网成员（web-proxy 通道）：本地代理端口 + 浏览器 CDP 端口 + 拉起 bat
# 代理端口按你自己的本地代理填写（或设环境变量 ORCHESTRA_FOREIGN_PROXY_PORT）
FOREIGN_PROXY_PORT = int(os.environ.get("ORCHESTRA_FOREIGN_PROXY_PORT", "0"))
FOREIGN_CDP_PORT = 9227
FOREIGN_LAUNCHER = r"<start_foreign_browser.bat 绝对路径>"
FOREIGN_MEMBERS = ["chatgpt", "grok"]

# OpenCLI daemon 端口
OPENCLI_PORT = 19825

# ═══════════════════════════════════════════════════════════════════════════

# ensure_available 语义：
#   cdp_alive/proxy_alive=false 只代表扫描那一刻没在线；ensure_available=true
#   表示该成员有自愈/拉起手段（幂等 bat / ensure 命令 / 启动器），派发时先拉起再判，
#   不要直接降级。真正「真不可用」= installed=false 或 ensure_available 缺失/为 false。


def port_open(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=2)
        s.close()
        return True
    except OSError:
        return False


def _opencli_ready():
    return port_open(OPENCLI_PORT)


def scan_agent():
    if not os.path.exists(AGENT_CLI) or "<" in AGENT_CLI:
        return {"installed": False, "route": None}
    route = "official-cli" if os.path.exists(AGENT_LOG) else None
    alive = False
    if route:
        try:
            with open(AGENT_LOG, "rb") as f:
                tail = f.read()[-4000:].decode("utf-8", "replace")
            alive = "127.0.0.1:" in tail
        except OSError:
            pass
    return {"installed": True, "route": route, "alive": alive, "cli": AGENT_CLI,
            "note": "<cli> --profile headless '<task>' --cwd <dir>（按你的 CLI 语法改）"}


def scan_cdp_client(key, cfg):
    exe = next((p for p in cfg["exe_candidates"] if os.path.exists(p)), None)
    if not exe:
        return {"installed": False, "route": None}
    cdp = port_open(cfg["cdp_port"])
    route = "cdp-client" if cdp else ("opencli-web" if _opencli_ready() else "clipboard")
    info = {"installed": True, "route": route, "cdp_alive": cdp, "ensure_available": True,
            "exe": exe, "launcher": cfg["launcher"], "note": cfg["note"]}
    if cfg.get("cli"):
        info["cli"] = cfg["cli"]
    return info


def scan_chatparty():
    if not CHATPARTY:
        return {"installed": False, "route": None}
    if not os.path.exists(CHATPARTY["exe"]):
        return {"installed": False, "route": None}
    cdp = port_open(CHATPARTY["cdp_port"])
    return {"installed": True, "route": "cdp-client" if cdp else "clipboard",
            "cdp_alive": cdp, "ensure_available": True,
            "exe": CHATPARTY["exe"], "launcher": CHATPARTY["launcher"],
            "note": "多站网页顾问聚合（登录态由 tools/chatparty/cp_login_guard.py 看门狗保活）；"
                    "cdp_alive=false 用启动器 bat 拉起后即恢复；各站按 CDP target URL 匹配"}


def scan_foreign(name):
    notes = [FOREIGN_BASE_NOTE]
    if name in FOREIGN_NOTES:
        notes.append(FOREIGN_NOTES[name])
    if FOREIGN_PROXY_PORT <= 0:
        return {"installed": True, "route": None, "proxy_alive": False,
                "note": "代理端口未配置（ORCHESTRA_FOREIGN_PROXY_PORT 或脚本顶部 FOREIGN_PROXY_PORT）"}
    proxy_ok = port_open(FOREIGN_PROXY_PORT)
    if not proxy_ok:
        return {"installed": True, "route": None, "proxy_alive": False,
                "note": "需要本地代理在线（代理口 %d 未监听）" % FOREIGN_PROXY_PORT}
    cdp_ok = port_open(FOREIGN_CDP_PORT)
    route = "web-proxy" if cdp_ok else None
    info = {"installed": True, "route": route, "proxy_alive": True, "cdp_alive": cdp_ok,
            "ensure_available": True, "launcher": FOREIGN_LAUNCHER,
            "note": "；".join(notes)}
    if FOREIGN_CLI and "<" not in FOREIGN_CLI:
        info["cli"] = FOREIGN_CLI
    return info


def scan_opencli():
    ready = _opencli_ready()
    return {"installed": ready, "route": "opencli-web" if ready else None,
            "note": "Bridge 扩展须已连接（browser <会话> doctor 验证）"}


def main():
    as_print = "--print" in sys.argv
    routes = {"agent": scan_agent()}
    for key, cfg in CDP_CLIENTS.items():
        routes[key] = scan_cdp_client(key, cfg)
    if CHATPARTY:
        routes["chatparty"] = scan_chatparty()
    for name in FOREIGN_MEMBERS:
        routes[name] = scan_foreign(name)
    routes["opencli"] = scan_opencli()

    lines = ["# routes.yaml — 由 scan_routes.py 生成，勿手改顺序",
             "# 派发优先级：official-cli > cdp-client > opencli-web > clipboard",
             "# 语义：alive=false + ensure_available=true = 待拉起（先跑 ensure/launcher 再判，不直接降级）；",
             "#       真不可用 = installed=false 或 ensure_available 为 false/缺失", ""]
    for name, info in routes.items():
        lines.append(f"{name}:")
        for k, v in info.items():
            lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
    content = "\n".join(lines) + "\n"
    if as_print:
        print(content)
    else:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"written: {OUT}")


if __name__ == "__main__":
    main()
