# 构建本地桌面程序：dist\智慧学伴.exe（单文件，内嵌只读快照）
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File .\build_desktop.ps1
#      powershell ... -Console   # 保留控制台，便于排错

[CmdletBinding()]
param(
    [string]$Python = $env:PYTHON,
    [switch]$Console
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Resolve-Python {
    param([string]$Candidate)
    if ($Candidate -and (Test-Path $Candidate)) { return (Resolve-Path $Candidate).Path }
    $bundled = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
    if (Test-Path $bundled) { return $bundled }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw '未找到 Python。请用 -Python 指定，或设置 $env:PYTHON。'
}

$py = Resolve-Python $Python
Write-Host "[build] Python: $py"
$venv = Join-Path $Root '.venv-build'
$venvPy = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Write-Host '[build] 创建构建虚拟环境 .venv-build'
    & $py -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败' }
}
& $venvPy -m pip install --disable-pip-version-check --upgrade pip | Out-Host
if ($LASTEXITCODE -ne 0) { throw '升级 pip 失败' }
& $venvPy -m pip install --disable-pip-version-check pyinstaller pywebview openai | Out-Host
if ($LASTEXITCODE -ne 0) { throw '安装 PyInstaller / pywebview / openai 失败' }

$name = 'SmartCompanion'
$pyArgs = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile')
if (-not $Console) { $pyArgs += '--windowed' }
$pyArgs += @(
    '--name', $name,
    '--collect-all', 'webview',
    '--collect-all', 'openai',
    '--hidden-import', 'webview.platforms.edgechromium',
    '--hidden-import', 'clr_loader',
    '--add-data', 'ui;ui',
    '--add-data', 'out;out',
    '--add-data', 'data/derived;data/derived',
    '--add-data', 'data/raw;data/raw',
    'src/desktop.py'
)

Write-Host '[build] PyInstaller 开始，产物在 dist\'
& $venvPy @pyArgs
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 构建失败' }

$built = Join-Path $Root "dist\$name.exe"
if (-not (Test-Path $built)) { throw "未找到构建产物：$built" }
$target = Join-Path $Root 'dist\智慧学伴.exe'
Copy-Item -Path $built -Destination $target -Force
$size = [math]::Round((Get-Item $target).Length / 1MB, 1)
Write-Host "[build] 完成：$target（$size MB）"
Write-Host '[build] 双击即可运行；首次启动会解压内置快照，约需数秒。'
exit 0
