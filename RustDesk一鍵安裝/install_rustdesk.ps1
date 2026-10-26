# RustDesk 一鍵安裝程式
# 用法：對同資料夾的「一鍵安裝RustDesk.bat」按兩下即可（會自動要求系統管理員權限）
# 流程：下載官方最新版 -> 驗證檔案 -> 靜默安裝 -> 設定固定密碼 -> 權限設定 -> 電源設定 -> 產生安裝紀錄

$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'RustDesk 一鍵安裝'

function Step($n, $msg) { Write-Host ""; Write-Host "[$n/6] $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  !!  $msg" -ForegroundColor Yellow }
function Fail($msg) {
    Write-Host ""; Write-Host "  XX  $msg" -ForegroundColor Red
    Read-Host "`n按 Enter 關閉視窗"; exit 1
}
function AskYes($msg) { (Read-Host "$msg (Y/N)") -match '^[Yy]' }

# ---- 0. 取得系統管理員權限 ----
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host '需要系統管理員權限，請在跳出的視窗按「是」...'
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

$exe = Join-Path $env:ProgramFiles 'RustDesk\rustdesk.exe'
$version = ''

# ---- 1. 下載官方最新版 ----
Step 1 '從 RustDesk 官方 GitHub 取得最新版本'
if (Test-Path $exe) {
    Ok "這台電腦已經安裝過 RustDesk，跳過下載與安裝"
} else {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $ProgressPreference = 'SilentlyContinue'   # 關閉進度條，下載速度會快很多
    try {
        $rel = Invoke-RestMethod 'https://api.github.com/repos/rustdesk/rustdesk/releases/latest' -Headers @{ 'User-Agent' = 'rustdesk-installer' }
    } catch { Fail "無法連上 GitHub，請確認網路正常後再執行一次。($($_.Exception.Message))" }
    $version = $rel.tag_name
    $asset = $rel.assets | Where-Object { $_.name -eq "rustdesk-$version-x86_64.exe" } | Select-Object -First 1
    if (-not $asset) { Fail "找不到 Windows 安裝檔 (版本 $version)，請改用手動下載：https://github.com/rustdesk/rustdesk/releases" }

    $setup = Join-Path $env:TEMP $asset.name
    Write-Host "  下載中：$($asset.name)（約 20~30 MB，請稍候）"
    try { Invoke-WebRequest $asset.browser_download_url -OutFile $setup -UseBasicParsing }
    catch { Fail "下載失敗：$($_.Exception.Message)" }
    Ok "下載完成，版本 $version"

    # ---- 2. 驗證檔案（防止下載到被竄改的檔案）----
    Step 2 '驗證安裝檔'
    $hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
    if ($asset.digest -match '^sha256:([0-9a-f]{64})$') {
        if ($hash -ne $Matches[1]) { Remove-Item $setup -Force; Fail '檔案驗證不符，已刪除檔案，請勿安裝並通知 IT。' }
        Ok 'SHA256 與 GitHub 官方紀錄相符'
    } else {
        Warn 'GitHub 未提供驗證碼，僅檢查數位簽章'
    }
    $sig = Get-AuthenticodeSignature $setup
    if ($sig.Status -eq 'Valid') { Ok "數位簽章有效：$($sig.SignerCertificate.Subject)" }
    else { Warn "數位簽章狀態：$($sig.Status)（檔案來源為官方 GitHub，仍繼續安裝）" }

    # ---- 3. 靜默安裝 ----
    Step 3 '安裝 RustDesk（會建立桌面捷徑與開機自動啟動服務）'
    $proc = Start-Process $setup -ArgumentList '--silent-install' -PassThru
    $null = $proc.WaitForExit(180000)
    for ($i = 0; $i -lt 60 -and -not (Test-Path $exe); $i++) { Start-Sleep 2 }
    if (-not (Test-Path $exe)) { Fail '安裝逾時，請改用手動安裝（對下載的檔案按兩下 -> 安裝）。' }
    Remove-Item $setup -Force -ErrorAction SilentlyContinue
    Ok "已安裝到 $exe"
}
if (-not $version) { $version = (Get-Item $exe).VersionInfo.ProductVersion }

# 等待背景服務啟動（之後的設定都要靠它）
$svc = Get-Service -Name RustDesk -ErrorAction SilentlyContinue
if ($svc) {
    Set-Service RustDesk -StartupType Automatic
    if ($svc.Status -ne 'Running') { Start-Service RustDesk -ErrorAction SilentlyContinue }
}
Start-Sleep 5

function RD { param([string[]]$a) ((& $exe @a | Out-String).Trim()) }

# ---- 4. 設定固定密碼 ----
Step 4 '設定固定密碼（建議 12 碼以上，含大小寫英文、數字、符號）'
Write-Host '  直接按 Enter 可跳過，之後再到 RustDesk 設定。'
$pwSet = $false
while ($true) {
    $p1 = Read-Host '  請輸入密碼' -AsSecureString
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($p1))
    if (-not $plain) { Warn '已跳過密碼設定'; break }
    if ($plain.Length -lt 8) { Warn '密碼至少 8 碼，請重新輸入'; continue }
    if ($plain -match '[\s"]') { Warn '密碼不可包含空白或雙引號 "，請重新輸入'; continue }
    $p2 = Read-Host '  請再輸入一次' -AsSecureString
    $plain2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($p2))
    if ($plain -cne $plain2) { Warn '兩次輸入不一致，請重新輸入'; continue }
    $r = RD '--password', $plain
    $plain = $null; $plain2 = $null
    if ($r -match 'Done') { Ok '固定密碼設定完成（請登記在公司密碼清冊）'; $pwSet = $true }
    else { Warn "密碼設定失敗：$r（請之後到 RustDesk -> 設定 -> 安全 手動設定）" }
    break
}

# ---- 5. 依電腦用途設定權限 ----
Step 5 '這台電腦的用途'
Write-Host '  1 = 一般文書電腦（全部功能開啟）'
Write-Host '  2 = 試驗設備電腦（關閉檔案傳輸、剪貼簿，保護原始數據）'
$role = Read-Host '  請輸入 1 或 2'
if ($role -eq '2') {
    RD '--option', 'enable-file-transfer', 'N' | Out-Null
    RD '--option', 'enable-clipboard', 'N' | Out-Null
    Ok '已關閉檔案傳輸與剪貼簿'
    if (AskYes '  是否要求「現場人員按接受」才能連線？（現場沒人時就無法連線）') {
        RD '--option', 'approve-mode', 'click' | Out-Null
        Ok '已設定為需要現場人員按接受'
    }
    $roleName = '試驗設備電腦'
} else {
    $roleName = '一般文書電腦'
    Ok '維持預設（全部功能開啟）'
}

# ---- 6. 電源設定 ----
Step 6 '電源設定'
if (AskYes '  插電時是否設定為「永不睡眠」？被連線的電腦建議選 Y') {
    powercfg /change standby-timeout-ac 0
    Ok '已設定插電時永不睡眠（螢幕仍會照常關閉）'
}

# ---- 完成：顯示 ID 並產生安裝紀錄 ----
$id = ''
for ($i = 0; $i -lt 10 -and -not ($id -match '^\d+$'); $i++) { $id = RD '--get-id'; if (-not ($id -match '^\d+$')) { Start-Sleep 2 } }
if (-not ($id -match '^\d+$')) { $id = '（請打開 RustDesk 查看左上角 ID）' }

$log = Join-Path $PSScriptRoot ("RustDesk安裝紀錄_{0}_{1}.txt" -f $env:COMPUTERNAME, (Get-Date -Format 'yyyyMMdd'))
@"
RustDesk 安裝紀錄
================================
安裝日期：$(Get-Date -Format 'yyyy/MM/dd HH:mm')
電腦名稱：$env:COMPUTERNAME
執行帳號：$env:USERNAME
RustDesk 版本：$version
RustDesk ID：$id
電腦用途：$roleName
固定密碼：$(if ($pwSet) { '已設定（密碼不記錄於此檔，請登記於公司密碼清冊）' } else { '未設定' })
安裝人員簽名：______________   覆核：______________
"@ | Out-File $log -Encoding UTF8

Write-Host ""
Write-Host '================================================' -ForegroundColor Green
Write-Host '  安裝完成！' -ForegroundColor Green
Write-Host "  這台電腦的 RustDesk ID：$id" -ForegroundColor Green
Write-Host "  安裝紀錄已存到：$log" -ForegroundColor Green
Write-Host '================================================' -ForegroundColor Green
Read-Host "`n按 Enter 關閉視窗"
