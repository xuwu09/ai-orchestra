# -*- coding: utf-8 -*-
"""
replace_v4.py — 等待 ChatParty 退出后：备份当前 app.asar → 用补丁产物替换 → 读回校验。

> 合规声明：仅用于对你自己合法安装的 ChatParty 副本做个人本地修改，
> 不分发程序本体或修改版。

用法：python replace_v4.py [--wait 秒数] [--new <新 asar 路径>]
默认等待 90 秒，进程不退出则放弃（绝不替换运行中的程序）。
校验：①补丁 marker（CP-PATCH-TRUSTED）在包内 ②main.js 存在且尺寸正常。
校验失败给出回滚命令。
"""
import hashlib
import json
import os
import struct
import subprocess
import sys
import time

ASAR = os.environ.get("ORCHESTRA_CHATPARTY_ASAR",
                      r"<ChatParty resources>\app.asar")
NEW = os.environ.get("ORCHESTRA_CHATPARTY_ASAR_NEW", ASAR + ".new")
MARKER = b"CP-PATCH-TRUSTED"


def chatparty_running():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ChatParty.exe"],
                             capture_output=True).stdout.decode("mbcs", errors="replace")
        return "ChatParty.exe" in out
    except Exception:
        return True  # 检测失败按在跑处理，避免误替换


def verify_asar(path):
    raw = open(path, "rb").read()
    json_len = struct.unpack("<4I", raw[:16])[3]
    tree = json.loads(raw[16:16 + json_len].decode("utf-8"))
    flat = []

    def walk(node, prefix=""):
        for name, ch in node.items():
            p = prefix + "/" + name
            if "files" in ch:
                walk(ch["files"], p)
            else:
                flat.append((p, ch))
    walk(tree["files"])
    main = dict(flat).get("/dist-electron/main.js")
    return MARKER in raw, main is not None and main["size"] > 240000


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4194304), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    wait = 90
    new_path = NEW
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--wait" and i + 1 < len(args):
            wait = int(args[i + 1]); i += 2
        elif args[i] == "--new" and i + 1 < len(args):
            new_path = args[i + 1]; i += 2
        else:
            i += 1
    if not os.path.exists(new_path):
        print("new asar missing:", new_path)
        return 1
    deadline = time.time() + wait
    while chatparty_running():
        if time.time() >= deadline:
            print("ChatParty 仍在运行，未替换。请彻底退出 ChatParty（含托盘）后重试。")
            return 1
        time.sleep(2)
    print("ChatParty 已退出")
    bak = ASAR + ".pre-patch-backup"
    if not os.path.exists(bak):
        os.replace(ASAR, bak)
        print("backup:", bak, os.path.getsize(bak), "bytes")
    else:
        print("backup exists (kept):", bak)
    os.replace(new_path, ASAR)
    print("REPLACED ->", ASAR, os.path.getsize(ASAR), "bytes")
    ok_marker, ok_size = verify_asar(ASAR)
    print("verify: patch-marker=%s mainjs-size-ok=%s" % (ok_marker, ok_size))
    if ok_marker and ok_size:
        print("ALL GOOD - 可以启动 ChatParty 测试群发了")
        print("new asar sha256:", sha256(ASAR))
        return 0
    print("VERIFY FAILED - 回滚: copy /y \"%s\" \"%s\"" % (bak, ASAR))
    return 1


if __name__ == "__main__":
    sys.exit(main())
