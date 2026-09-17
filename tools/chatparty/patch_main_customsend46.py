# -*- coding: utf-8 -*-
"""
patch_main_customsend46.py — ChatParty 主进程「trusted 三重门发送」补丁工具（示例/最新版）
v4.6 = v4.5 三重门基础上 ①纳米(bot.n.cn) Slate 直填路径 ②Kimi value 门 trim 修复

> 合规声明：本工具只用于对你**自己合法安装的 ChatParty 副本**做个人本地修改，
> 不分发 ChatParty 程序本体或其修改版。改动仅供个人使用，请勿分发补丁后的程序包。

三重门（probe → focus → value → Enter）：
  1. probe 门：elementFromPoint 必须命中输入框/子元素（布局未稳时坐标会偏），400ms 重试≤4 次
  2. focus 门：trusted click 后 activeElement 必须在输入框内，补点一次仍失败 ABORT（不 Enter）
  3. value 门：insertText 后必须读到 trim 非空文本，重试一轮仍空 ABORT
  全过才 Enter，Enter 后 2s 记 URL 验证跳转。日志 cp_trusted.log。

⚠️ 锚点说明：脚本里的锚点字符串取自我们本地演进链（官方 1.2.0 → 重构建版 →
v3 → … → v4.5）的 dist-electron/main.js。**外部副本直接跑大概率 anchor mismatch
而安全退出（不会写盘）**——这是设计行为。你的用法二选一：
  a) 把它当「三重门」参考实现，按你副本的 main.js 实际代码调整锚点后自改；
  b) 先走 README「自改教程」前几步（挂 CDP / 删站重构建），从你自己的基线出发。

配置（环境变量，或改下面默认值）：
  ORCHESTRA_CHATPARTY_ASAR  ChatParty resources\\app.asar 绝对路径
  ORCHESTRA_NODE            node 可执行文件（用于 --check 语法校验）
产物：app.asar.v46new（不直接覆盖原文件，用 replace_v4.py 完成替换）。
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

# ---------- 锚点 ----------
A1_OLD = '''        const __cpIsKimi = (__cpSrc || "").includes("kimi.com");'''
A1_NEW = '''        const __cpIsKimi = (__cpSrc || "").includes("kimi.com");
        const __cpIsNano = (__cpSrc || "").includes("bot.n.cn");'''

A2_OLD = '''        __cpTlog("ENTRY src=", __cpSrc, "| metaso=", __cpIsMetaso, "zhida=", __cpIsZhida, "kimi=", __cpIsKimi);'''
A2_NEW = '''        __cpTlog("ENTRY src=", __cpSrc, "| metaso=", __cpIsMetaso, "zhida=", __cpIsZhida, "kimi=", __cpIsKimi, "nano=", __cpIsNano);'''

A3_OLD = '''        if (__cpIsMetaso || __cpIsZhida || __cpIsKimi) {'''
A3_NEW = '''        if (__cpIsMetaso || __cpIsZhida || __cpIsKimi || __cpIsNano) {'''

A4_OLD = '''          const __cpFrag = __cpIsMetaso ? "metaso.cn" : (__cpIsKimi ? "kimi.com" : "zhida.zhihu.com");'''
A4_NEW = '''          const __cpFrag = __cpIsMetaso ? "metaso.cn" : (__cpIsKimi ? "kimi.com" : (__cpIsNano ? "bot.n.cn" : "zhida.zhihu.com"));'''

# 分支头：前面插 nano 分支
A5_OLD = '''                if (__cpIsMetaso || __cpIsKimi) {'''
A5_NEW = '''                if (__cpIsNano) {
                  const __cpNanoSend = async () => {
                    try {
                      const __cpMsg = String(data.message);
                      const __cpJs1 = '(function(){var MSG=' + JSON.stringify(__cpMsg) + ';var c=document.querySelector("[contenteditable=\\\\"true\\\\"]");if(!c)return "no-div";var fk=Object.keys(c).filter(function(k){return k.indexOf("__reactFiber")===0;});if(!fk.length)return "no-fiber";var f=c[fk[0]],hops=0;function isEd(o){return o&&typeof o==="object"&&typeof o.insertText==="function"&&typeof o.insertBreak==="function"&&Array.isArray(o.children)&&typeof o.onChange==="function";}while(f&&hops<40){var ps=[f.memoizedProps,f.memoizedState];for(var i=0;i<ps.length;i++){var p=ps[i];if(!p||typeof p!=="object")continue;if(isEd(p)){window.__cpSlate=p;break;}var ks=Object.keys(p);for(var j=0;j<ks.length&&j<30;j++){var v=p[ks[j]];if(isEd(v)){window.__cpSlate=v;break;}}if(window.__cpSlate)break;}if(window.__cpSlate)break;f=f.return;hops++;}if(!window.__cpSlate)return "no-editor";var e=window.__cpSlate;if(!e.selection){e.selection={anchor:{path:[0,0],offset:0},focus:{path:[0,0],offset:0}};}try{e.insertText(MSG);}catch(se){return "ins-err:"+String(se).slice(0,80);}return "inserted:"+JSON.stringify(e.children).slice(0,80);})()';
                      __cpTlog("BRANCH nano insert-begin");
                      const __cpR1 = await __cpTgt.executeJavaScript(__cpJs1);
                      __cpTlog("BRANCH nano insert", String(__cpR1));
                      if (!String(__cpR1).startsWith("inserted")) { this.log("[IPC-TRUSTED] nano insert failed"); return; }
                      await new Promise((r11) => setTimeout(r11, 800));
                      const __cpJs2 = '(function(){var sb=document.querySelector(".send-btn");if(!sb)return "no-btn";var pk=Object.keys(sb).filter(function(k){return k.indexOf("__reactProps")===0;});if(!pk.length)return "no-btnprops";var mock={preventDefault:function(){},stopPropagation:function(){},persist:function(){},target:sb,currentTarget:sb,type:"click",nativeEvent:new MouseEvent("click")};try{sb[pk[0]].onClick.call(sb,mock);return "send-clicked";}catch(e){return "ERR:"+String(e).slice(0,100);}})()';
                      const __cpR2 = await __cpTgt.executeJavaScript(__cpJs2);
                      __cpTlog("BRANCH nano send", String(__cpR2));
                      this.log("[IPC-TRUSTED] nano slate send:", String(__cpR2));
                      await new Promise((r12) => setTimeout(r12, 2000));
                      const __cpU2 = await __cpTgt.executeJavaScript("location.href");
                      __cpTlog("BRANCH nano after-url", String(__cpU2));
                    } catch (ne) {
                      __cpTlog("BRANCH nano ERR", String(ne));
                      this.log("[IPC-TRUSTED] nano err", String(ne));
                    }
                  };
                  __cpNanoSend();
                } else if (__cpIsMetaso || __cpIsKimi) {'''

# Kimi value 门 trim（v4.5 分支里出现 2 处，一并替换）
A6_OLD = '''                      if (!__cpV || String(__cpV).length === 0) {'''
A6_NEW = '''                      if (!__cpV || String(__cpV).trim().length === 0) {'''


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
    src = raw[data_off + int(main_node["offset"]): data_off + int(main_node["offset"]) + main_node["size"]].decode("utf-8", "replace")
    print("main.js size:", main_node["size"])

    if "__cpIsNano" in src:
        print("already v4.6")
        return 0

    checks = [("A1", A1_OLD, 1), ("A2", A2_OLD, 1), ("A3", A3_OLD, 1), ("A4", A4_OLD, 1), ("A5", A5_OLD, 1), ("A6", A6_OLD, 2)]
    for name, a, want in checks:
        c = src.count(a)
        if c != want:
            raise SystemExit("anchor %s count=%d want=%d - abort" % (name, c, want))
    print("anchors OK")

    patched = src.replace(A1_OLD, A1_NEW).replace(A2_OLD, A2_NEW).replace(A3_OLD, A3_NEW).replace(A4_OLD, A4_NEW).replace(A5_OLD, A5_NEW).replace(A6_OLD, A6_NEW)
    out_js = os.path.join(BASE, "main_v46_sendpatch.js")
    open(out_js, "w", encoding="utf-8", newline="\n").write(patched)
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
    out_asar = ASAR + ".v46new"
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
        c = raw2[data_off2 + int(ch["offset"]): data_off2 + int(ch["offset"]) + ch["size"]]
        if p == "/dist-electron/main.js":
            main_size2 = len(c)
            if b"__cpIsNano" not in c or b"__cpSlate" not in c or b"trim().length" not in c or b"CP-PATCH-SEND" not in c:
                raise SystemExit("marker missing in main.js")
        if hashlib.sha256(c).hexdigest() != ch["integrity"]["hash"]:
            print("INTEGRITY FAIL:", p)
            bad += 1
    if bad:
        raise SystemExit("%d files integrity FAIL" % bad)
    print("self-check OK: %d files, main.js %d bytes" % (n_files, main_size2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
