<#
.SYNOPSIS
  "智慧学伴" 流水线：质检 -> 内容地图 -> 契约校验 -> 自检。
.DESCRIPTION
  第一天只需要这一条命令：./run.ps1
  子任务：qc（质检+基线）/ content（内容地图）/ validate（契约校验）/ clean（清空 out 再重建）。
.NOTES
  解释器优先级：$env:PYTHON -> DSH 自带 python -> PATH 上的 python。
#>
[CmdletBinding()]
param(
    [ValidateSet('all', 'qc', 'content', 'validate', 'clean')]
    [string]$Task = 'all'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$NL = [char]10
Push-Location $root
try {
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'

    function Resolve-Python {
        if ($env:PYTHON -and (Test-Path $env:PYTHON)) { return $env:PYTHON }
        $bundled = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
        if (Test-Path $bundled) { return $bundled }
        $found = Get-Command python -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
        throw '找不到 Python 解释器：请设置 $env:PYTHON 或安装 python'
    }

    $python = Resolve-Python
    Write-Host "解释器 $python"
    Write-Host "工作目录 $root"

    function Invoke-Py {
        param([string]$Script, [string[]]$PyArgs = @())
        & $python (Join-Path $root $Script) @PyArgs
        if ($LASTEXITCODE -ne 0) { throw "$Script 退出码 $LASTEXITCODE" }
    }

    function Invoke-Step {
        param([string]$Label, [string]$Name, [scriptblock]$Body)
        $t0 = Get-Date
        & $Body
        $ms = [int]((Get-Date) - $t0).TotalMilliseconds
        Write-Host ("[{0}] {1,-9} ok ({2} ms)" -f $Label, $Name, $ms)
    }

    function Test-FileHashes {
        $manifest = Join-Path $root 'data\raw\SHA256SUMS.txt'
        if (-not (Test-Path $manifest)) { throw "缺少 $manifest" }
        $bad = @()
        $lines = Get-Content -LiteralPath $manifest -Encoding utf8 | Where-Object { $_.Trim() }
        foreach ($line in $lines) {
            $parts = $line.Trim() -split '\s+', 2
            $expected = $parts[0]
            $name = $parts[1].TrimStart('*')
            $path = Join-Path $root (Join-Path 'data\raw' $name)
            if (-not (Test-Path -LiteralPath $path)) { $bad += "缺文件 $name"; continue }
            $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()
            if ($actual -ne $expected.ToLower()) { $bad += "$name 哈希不符" }
        }
        if ($bad.Count) { throw ("SHA256 校验失败：" + ($bad -join '；')) }
        Write-Host ("   SHA256SUMS 校验通过（{0} 个文件）" -f $lines.Count)
    }

    function Test-NoHardcodedIds {
        # 源码里不允许出现具体学生/题目/指标/节点编号，否则换一份评测数据就跑不动
        $pattern = '(\bD0\d\b|\bQ0\d\d\b|\bT0[1-3]\b|\bN0\d\b|\bDR\d{4}\b)'
        $hits = Select-String -Path (Join-Path $root 'src\*.py') -Pattern $pattern -AllMatches
        if ($hits) {
            $detail = ($hits | ForEach-Object { "  $($_.Filename):$($_.LineNumber) $($_.Line.Trim())" }) -join $NL
            throw ("src/ 里发现硬编码编号：" + $NL + $detail)
        }
        Write-Host '   源码无硬编码编号'
    }

    function Test-Deterministic {
        $targets = @('out\qc_report.json', 'out\baseline.json')
        $before = @{}
        foreach ($t in $targets) { $before[$t] = (Get-FileHash -LiteralPath (Join-Path $root $t) -Algorithm SHA256).Hash }
        Invoke-Py 'src\qc.py' @('--baseline')
        foreach ($t in $targets) {
            $after = (Get-FileHash -LiteralPath (Join-Path $root $t) -Algorithm SHA256).Hash
            if ($after -ne $before[$t]) { throw "$t 两次运行字节不一致，输出里可能混入了时间戳" }
        }
        Write-Host '   两次运行字节一致'
    }

    function Clear-Out {
        foreach ($p in @('out\*.json', 'out\tables\*.csv')) {
            Get-ChildItem -Path (Join-Path $root $p) -ErrorAction SilentlyContinue | Remove-Item -Force
        }
        Write-Host 'out/ 已清空'
    }

    switch ($Task) {
        'clean' { Clear-Out }
        'qc' { Invoke-Step '1/1' 'qc' { Invoke-Py 'src\qc.py' @('--baseline') } }
        'content' { Invoke-Step '1/1' 'content' { Invoke-Py 'src\content_map.py' } }
        'validate' { Invoke-Step '1/1' 'validate' { Invoke-Py 'src\validate.py' } }
        'all' {
            Invoke-Step '1/4' 'qc' { Invoke-Py 'src\qc.py' @('--baseline') }
            Invoke-Step '2/4' 'content' { Invoke-Py 'src\content_map.py' }
            Invoke-Step '3/4' 'validate' { Invoke-Py 'src\validate.py' }
            Invoke-Step '4/4' 'selfcheck' {
                Test-FileHashes
                Test-NoHardcodedIds
                Test-Deterministic
            }
            Write-Host '全部通过'
        }
    }
}
catch {
    Write-Host "失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}
