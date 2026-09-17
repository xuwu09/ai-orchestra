# -*- coding: utf-8 -*-
"""
patch_main_customsend48.py — ChatParty 主进程「豆包并入 trusted 分支」补丁（v4.8）
v4.8 = v4.7 基础上把豆包(doubao.com)加入主进程 trusted 三重门分支（与 Kimi 同款 contenteditable 路径）。

> 合规声明：本工具只用于对你**自己合法安装的 ChatParty 副本**做个人本地修改，
> 不分发 ChatParty 程序本体或其修改版。改动仅供个人使用，请勿分发补丁后的程序包。

【病根（2026-09-18 日志定案）】
  豆包前端改版：guidance textarea 形态消失，编辑器变为 tiptap ProseMirror contenteditable；
  发送按钮 class 从 send-msg-btn-bg 换成 tailwind 风格新类 → localStorage 里的
  doubao.sendMessage custom script 填字成功但 findBtn 永远找不到按钮 → 静默放弃，
  文字卡在输入框（输入框有字不发送）。
  实测（CDP）：trusted click 编辑器中心 → activeElement=ProseMirror-focused →
  trusted Enter → URL 跳会话页发送成功。修复=豆包并入 trusted 分支：
  probe → click → focus 门 → cleared → insertText → value 门 → trusted Enter。
  custom script doubao 键保留不动（trusted 分支 1500ms 后 cleared 会清掉 custom
  填的字，两者并行无冲突；若站点再改版 trusted 失效时 custom 仍是后备）。

⚠️ 锚点说明：锚点取自本地演进链（… → v4.6 → v4.7）的 dist-electron/main.js。
基线必须已是 v4.7（脚本会检查 __cpBcRescue 标记）。外部副本不匹配安全退出。
配置（环境变量）：ORCHESTRA_CHATPARTY_ASAR / ORCHESTRA_NODE
产物：app.asar.v48new（用 replace_v4.py 完成替换）。
"""
import hashlib
import json
import os
import struct
import subprocess
import sys

BASE = os.environ.get("ORCHESTRA_TOOLS_DIR", os.path.dirname(os.path.abspath(__file__)))
ASAR = os.environ.get("ORCHESTRA_CHATPARTY_ASAR", r"<ChatParty resources>\app.asar")
NODE = os.environ.get("ORCHESTRA_NODE", "node")
BLOCK = 4194304

# ---------- 锚点（v4.7 main.js 中各唯一） ----------
D1_OLD = '''        const __cpIsNano = (__cpSrc || "").includes("bot.n.cn");'''
D1_NEW = '''        const __cpIsNano = (__cpSrc || "").includes("bot.n.cn");
        const __cpIsDoubao = (__cpSrc || "").includes("doubao.com");'''

D2_OLD = '''        __cpTlog("ENTRY src=", __cpSrc, "| metaso=", __cpIsMetaso, "zhida=", __cpIsZhida, "kimi=", __cpIsKimi, "nano=", __cpIsNano);'''
D2_NEW = '''        __cpTlog("ENTRY src=", __cpSrc, "| metaso=", __cpIsMetaso, "zhida=", __cpIsZhida, "kimi=", __cpIsKimi, "nano=", __cpIsNano, "doubao=", __cpIsDoubao);'''

D3_OLD = '''        if (__cpIsMetaso || __cpIsZhida || __cpIsKimi || __cpIsNano) {'''
D3_NEW = '''        if (__cpIsMetaso || __cpIsZhida || __cpIsKimi || __cpIsNano || __cpIsDoubao) {'''

D4_OLD = '''          const __cpFrag = __cpIsMetaso ? "metaso.cn" : (__cpIsKimi ? "kimi.com" : (__cpIsNano ? "bot.n.cn" : "zhida.zhihu.com"));'''
D4_NEW = '''          const __cpFrag = __cpIsMetaso ? "metaso.cn" : (__cpIsKimi ? "kimi.com" : (__cpIsNano ? "bot.n.cn" : (__cpIsDoubao ? "doubao.com" : "zhida.zhihu.com")));'''

D5_OLD = '''                } else if (__cpIsMetaso || __cpIsKimi) {'''
D5_NEW = '''                } else if (__cpIsMetaso || __cpIsKimi || __cpIsDoubao) {'''


def asar_integrity(content: bytes) -> dict:
    h = hashlib.sha256(content).hexdigest()
    blocks = []
    for i in range(0, len(content), BLOCK):
        blocks.append(hashlib.sha256(content[i:i + BLOCK]).hexdigest())
    return {"algorithm": "SHA256", "hash": h, "blockSize": BLOCK, "blocks": blocks}


def load_asar(path):
    raw = open(path, "rb").read()
    json_len = struct.unpack("<4I", raw[:16])[3]
    data_off = 16 + ((json_len + 3) & ~3)
    tree = json.loads(raw[16:16 + json_len].decode("utf-8"))
    return raw, data_off, tree


def walk_files(node, prefix=""):
    for name, ch in node.items():
        p = prefix + "/" + name
        if "files" in ch:
            yield from walk_files(ch["files"], p)
        else:
            yield p, ch


def main():
    raw, data_off, tree = load_asar(ASAR)
    main_node = None
    for p, ch in walk_files(tree["files"]):
        if p == "/dist-electron/main.js":
            main_node = ch
            break
    if main_node is None:
        raise SystemExit("/dist-electron/main.js not found in asar - abort")
    src = raw[data_off + int(main_node["offset"]): data_off + int(main_node["offset"]) + main_node["size"]].decode("utf-8", "replace")
    print("main.js size:", main_node["size"])

    if "__cpIsDoubao" in src:
        print("already v4.8")
        return 0
    if "__cpBcRescue" not in src:
        raise SystemExit("baseline is NOT v4.7 (__cpBcRescue missing) - apply v4.7 first, abort")

    checks = [("D1", D1_OLD, 1), ("D2", D2_OLD, 1), ("D3", D3_OLD, 1), ("D4", D4_OLD, 1), ("D5", D5_OLD, 1)]
    for name, a, want in checks:
        c = src.count(a)
        if c != want:
            raise SystemExit("anchor %s count=%d want=%d - abort" % (name, c, want))
    print("anchors OK")

    patched = src.replace(D1_OLD, D1_NEW).replace(D2_OLD, D2_NEW).replace(D3_OLD, D3_NEW).replace(D4_OLD, D4_NEW).replace(D5_OLD, D5_NEW)
    out_js = os.path.join(BASE, "main_v48_sendpatch.js")
    with open(out_js, "w", encoding="utf-8", newline="\n") as f:
        f.write(patched)
    print("written:", out_js, len(patched), "chars")

    r = subprocess.run([NODE, "--check", out_js], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("SYNTAX CHECK FAILED:\n" + (r.stderr or "")[:800])
    print("node --check OK")

    blob_cache = {"/dist-electron/main.js": patched.encode("utf-8")}
    blobs = []
    pos = 0
    for p, ch in walk_files(tree["files"]):
        if p in blob_cache:
            content = blob_cache[p]
            ch["size"] = len(content)
            ch["integrity"] = asar_integrity(content)
        else:
            content = raw[data_off + int(ch["offset"]): data_off + int(ch["offset"]) + ch["size"]]
        ch["offset"] = str(pos)
        blobs.append(content)
        pos += len(content)

    header_json = json.dumps(tree, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    padded = (len(header_json) + 3) & ~3
    header = struct.pack("<4I", 4, padded + 8, padded + 4, len(header_json)) + header_json + b"\x00" * (padded - len(header_json))
    out_asar = ASAR + ".v48new"
    with open(out_asar, "wb") as f:
        f.write(header)
        for b in blobs:
            f.write(b)
    print("packed:", out_asar, os.path.getsize(out_asar))

    raw2, data_off2, tree2 = load_asar(out_asar)
    bad = 0
    n_files = 0
    main_size2 = None
    for p, ch in walk_files(tree2["files"]):
        if "integrity" not in ch:
            continue
        n_files += 1
        c2 = raw2[data_off2 + int(ch["offset"]): data_off2 + int(ch["offset"]) + ch["size"]]
        if p == "/dist-electron/main.js":
            main_size2 = len(c2)
            if b"__cpIsDoubao" not in c2 or b"__cpBcRescue" not in c2 or b"CP-PATCH-TRUSTED" not in c2:
                raise SystemExit("marker missing in main.js")
        if hashlib.sha256(c2).hexdigest() != ch["integrity"]["hash"]:
            print("INTEGRITY FAIL:", p)
            bad += 1
    if bad:
        raise SystemExit("%d files integrity FAIL" % bad)
    print("self-check OK: %d files, main.js %d bytes" % (n_files, main_size2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
