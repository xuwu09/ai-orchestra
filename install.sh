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

# 一键使用：自动生成个人档案与路由表（旧文件已随整个目录备份，不会覆盖用户数据）
for pair in "capabilities.example.md capabilities.md" "routes.example.yaml routes.yaml"; do
    set -- $pair
    if [ ! -f "$TARGET/references/$2" ]; then
        cp "$TARGET/references/$1" "$TARGET/references/$2"
        echo "generated references/$2 (from $1)"
    else
        echo "kept existing references/$2"
    fi
done

echo ""
echo "installed -> $TARGET"
echo "next steps:"
echo "  1. read TUTORIAL.md  (15 min from zero to first dispatch)"
echo "  2. optional: ChatParty channel -> tools/chatparty/README.md (edit start_chatparty.bat)"
echo "  3. optional: foreign advisor group -> tools/foreign-cli/README.md"
echo "  4. fill references/capabilities.md member roster, then: python references/scan_routes.py"
echo "  5. tell your agent: 调度多个 AI 完成 XX"
