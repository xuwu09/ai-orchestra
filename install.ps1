# AI Orchestra 一键安装（Windows）
#
# 用法 A —— 一行命令（无需克隆仓库）：
#   irm https://raw.githubusercontent.com/xuwu09/ai-orchestra/main/install.ps1 | iex
#
# 用法 B —— 已克隆仓库后在仓库目录内：
#   .\install.ps1
#
# 可选参数：-Target <目录>（默认安装到 ~\.workbuddy\skills\ai-orchestra；
# Claude Code 用户可用 -Target "$env:USERPROFILE\.claude\skills\ai-orchestra"）
param([string]$Target = (Join-Path $env:USERPROFILE ".workbuddy\skills\ai-orchestra"))
$ErrorActionPreference = "Stop"

# 判断执行形态：仓库内运行 or 管道远程执行（后者需先下载仓库 zip）
if (-not $PSScriptRoot -or -not (Test-Path (Join-Path $PSScriptRoot "SKILL.md"))) {
    $tmp = Join-Path $env:TEMP ("ai-orchestra-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    $zip = "$tmp.zip"
    Write-Host "downloading repo zip ..."
    Invoke-WebRequest "https://github.com/xuwu09/ai-orchestra/archive/refs/heads/main.zip" -OutFile $zip -UseBasicParsing
    Expand-Archive $zip $tmp -Force
    $src = Join-Path $tmp "ai-orchestra-main"
} else {
    $src = $PSScriptRoot
}

if (-not (Test-Path (Join-Path $src "SKILL.md"))) {
    throw "SKILL.md not found in source: $src"
}

New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
if (Test-Path $Target) {
    $bak = "$Target.bak-" + (Get-Date -Format "yyyyMMddHHmmss")
    Move-Item $Target $bak
    Write-Host "existing install backed up -> $bak"
}
Copy-Item $src $Target -Recurse -Force

# 一键使用：自动生成个人档案与路由表（旧文件已随整个目录备份，不会覆盖用户数据）
$refs = Join-Path $Target "references"
foreach ($pair in @(@("capabilities.example.md", "capabilities.md"),
                    @("routes.example.yaml", "routes.yaml"))) {
    $dst = Join-Path $refs $pair[1]
    if (-not (Test-Path $dst)) {
        Copy-Item (Join-Path $refs $pair[0]) $dst
        Write-Host "generated references\$($pair[1]) (from $($pair[0]))"
    } else {
        Write-Host "kept existing references\$($pair[1])"
    }
}

Write-Host ""
Write-Host "installed -> $Target"
Write-Host "next steps:"
Write-Host "  1. read TUTORIAL.md  (15 min from zero to first dispatch)"
Write-Host "  2. optional: ChatParty channel -> tools\chatparty\README.md (edit start_chatparty.bat)"
Write-Host "  3. optional: foreign advisor group -> tools\foreign-cli\README.md"
Write-Host "  4. fill references\capabilities.md member roster, then: python references\scan_routes.py"
Write-Host "  5. tell your agent: 调度多个 AI 完成 XX"
