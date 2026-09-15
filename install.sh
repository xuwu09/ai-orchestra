#!/usr/bin/env bash
# AI Orchestra 一键安装（macOS / Linux）
#
# 用法 A —— 一行命令（无需克隆仓库）：
#   curl -fsSL https://raw.githubusercontent.com/xuwu09/ai-orchestra/main/install.sh | bash
#
# 用法 B —— 已克隆仓库后在仓库目录内：
#   ./install.sh
#
# 可选参数：bash install.sh <目标目录>（默认 ~/.workbuddy/skills/ai-orchestra；
# Claude Code 用户可用 ~/.claude/skills/ai-orchestra）
set -euo pipefail

TARGET="${1:-$HOME/.workbuddy/skills/ai-orchestra}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/SKILL.md" ]; then
    SRC="$SCRIPT_DIR"
else
    TMP="$(mktemp -d)/ai-orchestra-main"
    echo "downloading repo zip ..."
    curl -fsSL "https://github.com/xuwu09/ai-orchestra/archive/refs/heads/main.zip" -o /tmp/ai-orchestra.zip
    unzip -q /tmp/ai-orchestra.zip -d "$(dirname "$TMP")"
    SRC="$TMP"
fi

[ -f "$SRC/SKILL.md" ] || { echo "ERROR: SKILL.md not found in $SRC"; exit 1; }

mkdir -p "$(dirname "$TARGET")"
if [ -d "$TARGET" ]; then
    BAK="$TARGET.bak-$(date +%Y%m%d%H%M%S)"
    mv "$TARGET" "$BAK"
    echo "existing install backed up -> $BAK"
fi
mkdir -p "$TARGET"
cp -R "$SRC/." "$TARGET/"
echo ""
echo "installed -> $TARGET"
echo "next steps:"
echo "  1. references/capabilities.example.md -> copy to capabilities.md, fill your member roster"
echo "  2. references/routes.example.yaml     -> copy to routes.yaml, fill local paths/ports"
echo "  3. ChatParty channel (optional): tools/chatparty/README.md"
echo "  4. tell your agent: 调度多个 AI 完成 XX"
