# -*- coding: utf-8 -*-
"""
patch_main_customsend47.py — ChatParty 主进程「群发漏站补扫」补丁（v4.7）
v4.7 = v4.6 基础上新加：广播补扫（RESCUE），与站点无关，一次覆盖 kimi / nano 等任何漏站。

> 合规声明：本工具只用于对你**自己合法安装的 ChatParty 副本**做个人本地修改，
> 不分发 ChatParty 程序本体或其修改版。改动仅供个人使用，请勿分发补丁后的程序包。

【病根（2026-09-18 日志定案）】
  「发送到所有AI」时渲染进程 for 循环逐站 invoke "send-message-to-webview"，
  11-12 条 IPC 在 ~50ms 内打完。但枚举快照存在竞态：16:08/16:25 轮漏 nano、
  17:46 轮漏 kimi、20:13 轮漏 kimi+nano——被漏的站主进程收不到 IPC，
  trusted 补丁（ENTRY/三重门）从未被触发，卡片静默停在欢迎页。
  修复不在渲染侧（bundle 难改且随版本漂移），而在主进程做**补扫**：

【RESCUE 补扫逻辑】
  - 每条 send-message-to-webview IPC 顺手记账（pid+msg+时间，60s 滑窗）
  - 窗内 >=3 条且各站消息完全一致（群发语义）→ 静默 3.5s 后补扫
    （群发 50ms 打完，3.5s 静默期无「循环中途误补」风险；单发/对比 2 站不触发）
  - 补扫：主窗口 DOM 枚举 webview[id]（与 orchestra_bridge status 同法，已验证可靠），
    对「DOM 有卡但 60s 内没收到 IPC」的站，由主进程直接调
    handleSendMessageToWebView 补发（完整复用 custom script + trusted 三重门）
  - 防重：同消息 90s 时间桶内只补一轮；补发站逐站打日志 RESCUE send ->
  - 日志：cp_trusted.log（与 trusted 段同款，路径按你本地保持一致）

⚠️ 锚点说明：锚点取自本地演进链（官方 1.2.0 → 重构建 → v3 → … → v4.6）的
dist-electron/main.js。外部副本直接跑大概率 anchor mismatch 安全退出（不写盘）——
设计行为。基线必须已是 v4.6（脚本会检查 __cpIsNano 标记）。
日志路径硬编码与本地 trusted 段一致，外部副本请自行调整。

配置（环境变量，或改下面默认值）：
  ORCHESTRA_CHATPARTY_ASAR  ChatParty resources\\app.asar 绝对路径
  ORCHESTRA_NODE            node 可执行文件（用于 --check 语法校验）
产物：app.asar.v47new（不直接覆盖原文件，用 replace_v4.py 完成替换）。
"""
import json
import os
import struct
import subprocess
import sys

import hashlib

BASE = os.environ.get("ORCHESTRA_TOOLS_DIR", os.path.dirname(os.path.abspath(__file__)))
ASAR = os.environ.get("ORCHESTRA_CHATPARTY_ASAR", r"<ChatParty resources>\app.asar")
NODE = os.environ.get("ORCHESTRA_NODE", "node")
BLOCK = 4194304

# ---------- 锚点（v4.6 main.js 中唯一） ----------
B1_OLD = '''    electron.ipcMain.handle("send-message-to-webview", (event, data) => this.handleSendMessageToWebView(data));'''

B1_NEW = '''    /* CP-PATCH-BROADCAST-RESCUE v4.7: main-process rescue for webviews missed by renderer group-send */
    const __cpBcRescue = function (data, self) {
      try {
        const __cpFs = require("fs");
        const __cpTlog = function () {
          try {
            const __cpParts = ["[" + new Date().toISOString() + "]"];
            for (let __i = 0; __i < arguments.length; __i++) __cpParts.push(typeof arguments[__i] === "string" ? arguments[__i] : JSON.stringify(arguments[__i]));
            __cpFs.appendFileSync("D:\\\\tools\\\\cli-anything-dsh\\\\chatparty-cli\\\\cp_trusted.log", __cpParts.join(" ") + "\\n");
          } catch (e) {}
        };
        const g = globalThis;
        if (!g.__cpBc) g.__cpBc = { hits: [], pending: null, done: {} };
        const st = g.__cpBc;
        const now = Date.now();
        const normPid = function (s) {
          let x = String(s || "");
          x = x.replace(/^summary-/, "");
          x = x.replace(/^webview-/, "");
          x = x.replace(/^webview-/, "");
          x = x.replace(/-element$/, "");
          return x.trim().toLowerCase();
        };
        const rawId = String((data && data.webviewId) || "");
        const pid = normPid(rawId);
        const msg = String((data && data.message) || "");
        if (!pid || pid.indexOf("summary") >= 0 || !msg) return;
        st.hits = st.hits.filter(function (h) { return now - h.t < 60000; });
        st.hits.push({ pid: pid, msg: msg, t: now });
        if (st.hits.length < 3) return;
        if (st.pending) clearTimeout(st.pending);
        st.pending = setTimeout(function () {
          try {
            const st2 = g.__cpBc;
            const now2 = Date.now();
            st2.hits = st2.hits.filter(function (h) { return now2 - h.t < 60000; });
            if (st2.hits.length < 3) return;
            const msgByPid = {};
            st2.hits.forEach(function (h) { msgByPid[h.pid] = h.msg; });
            const pids = Object.keys(msgByPid);
            if (pids.length < 3) return;
            const uniq = {};
            pids.forEach(function (p) { uniq[msgByPid[p]] = 1; });
            const msgKeys = Object.keys(uniq);
            if (msgKeys.length !== 1) { __cpTlog("RESCUE skip msgs-not-uniform", String(msgKeys.length)); return; }
            const bcMsg = msgKeys[0];
            const bucket = Math.floor(now2 / 90000);
            const bcKey = "bc" + bucket + ":" + bcMsg.slice(0, 100);
            if (st2.done[bcKey]) { __cpTlog("RESCUE skip already-done"); return; }
            st2.done[bcKey] = 1;
            st2.hits = [];
            const mw = self.windowManager && self.windowManager.getMainWindow ? self.windowManager.getMainWindow() : null;
            if (!mw || mw.isDestroyed()) { __cpTlog("RESCUE skip no-mainwin"); return; }
            mw.webContents.executeJavaScript('(function(){var out=[];var els=document.querySelectorAll("webview[id]");for(var i=0;i<els.length;i++){var id=els[i].id||"";var m=/^webview-(.+)-element$/.exec(id);if(!m)continue;var u="";try{u=els[i].getURL?els[i].getURL():(els[i].src||"")}catch(e){u=els[i].src||""}if(u&&u.indexOf("http")===0&&u.indexOf("about:blank")<0){out.push(m[1]+"\\t"+u)}}return JSON.stringify(out)})()').then(function (raw) {
              let domList = [];
              try { domList = JSON.parse(raw) || []; } catch (e) {}
              const domPids = [];
              const seen = {};
              domList.forEach(function (row) {
                const srow = String(row);
                const tab = srow.indexOf("\\t");
                const idPart = tab >= 0 ? srow.slice(0, tab) : srow;
                const u = tab >= 0 ? srow.slice(tab + 1) : "";
                const p = normPid(idPart);
                if (!p || seen[p]) return;
                if (p.indexOf("summary") >= 0) return;
                seen[p] = 1;
                domPids.push({ pid: p, url: u });
              });
              const missing = domPids.filter(function (it) { return pids.indexOf(it.pid) < 0; });
              __cpTlog("RESCUE scan done=", JSON.stringify(pids), "dom=", JSON.stringify(domPids.map(function (x) { return x.pid; })), "missing=", JSON.stringify(missing.map(function (x) { return x.pid; })));
              missing.forEach(function (it) {
                __cpTlog("RESCUE send ->", it.pid, "url=", it.url);
                try { self.handleSendMessageToWebView({ webviewId: it.pid, message: bcMsg }); } catch (e) { __cpTlog("RESCUE send-err", it.pid, String(e)); }
              });
            }).catch(function (e) { __cpTlog("RESCUE dom-enum-err", String(e)); });
          } catch (e) {
            try { require("fs").appendFileSync("D:\\\\tools\\\\cli-anything-dsh\\\\chatparty-cli\\\\cp_trusted.log", "[" + new Date().toISOString() + "] RESCUE ERR " + String(e) + "\\\\n"); } catch (e2) {}
          }
        }, 3500);
      } catch (e) {}
    };
    /* CP-PATCH-BROADCAST-RESCUE-END */
    electron.ipcMain.handle("send-message-to-webview", (event, data) => { try { __cpBcRescue(data, this); } catch (__cpBcE) {} return this.handleSendMessageToWebView(data); });'''


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

    if "__cpBcRescue" in src:
        print("already v4.7")
        return 0
    if "__cpIsNano" not in src:
        raise SystemExit("baseline is NOT v4.6 (__cpIsNano missing) - apply v4.6 first, abort")

    c = src.count(B1_OLD)
    if c != 1:
        raise SystemExit("anchor B1 count=%d want=1 - abort" % c)
    print("anchor B1 OK")

    patched = src.replace(B1_OLD, B1_NEW)
    out_js = os.path.join(BASE, "main_v47_sendpatch.js")
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
    out_asar = ASAR + ".v47new"
    with open(out_asar, "wb") as f:
        f.write(header)
        for b in blobs:
            f.write(b)
    print("packed:", out_asar, os.path.getsize(out_asar))

    # 自校验：重读产物，逐文件 integrity + marker
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
            if b"__cpBcRescue" not in c2 or b"CP-PATCH-BROADCAST-RESCUE" not in c2 or b"__cpIsNano" not in c2 or b"CP-PATCH-TRUSTED" not in c2:
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
