# 電腦空間與效能掃描工具（只列出、不刪除）v1.0
# 適用：Windows 10 / PowerShell 5.1
$ErrorActionPreference = 'SilentlyContinue'
$desk = [Environment]::GetFolderPath('Desktop')
$out  = Join-Path $desk 'Claude克勞得'
if (-not (Test-Path $out)) { New-Item -ItemType Directory -Path $out | Out-Null }
$stamp  = Get-Date -Format 'yyyyMMdd_HHmm'
$report = Join-Path $out "電腦掃描報告_$stamp.txt"
$lines  = New-Object System.Collections.Generic.List[string]
function W($t) { $lines.Add($t); Write-Host $t }
function SizeMB($p) {
  if (-not (Test-Path $p)) { return 0 }
  $s = (Get-ChildItem $p -Recurse -Force -File | Measure-Object Length -Sum).Sum
  if ($s) { [math]::Round($s / 1MB, 1) } else { 0 }
}

W "===== 電腦掃描報告（只列出，未刪除任何檔案）====="
W "掃描時間：$(Get-Date -Format 'yyyy/MM/dd HH:mm')"
W ""

W "【一、磁碟空間】"
Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
  $free = [math]::Round($_.FreeSpace / 1GB, 1); $all = [math]::Round($_.Size / 1GB, 1)
  $pct  = if ($_.Size) { [math]::Round($_.FreeSpace / $_.Size * 100) } else { 0 }
  $flag = if ($pct -lt 15) { '  <-- 高：剩餘不足15%' } else { '' }
  W "  $($_.DeviceID) 剩餘 $free GB / 共 $all GB（$pct%）$flag"
}
W ""

W "【二、可安全清理的暫存區（單位 MB）】"
$la = $env:LOCALAPPDATA
$items = [ordered]@{
  '使用者暫存 %TEMP%'           = $env:TEMP
  '系統暫存 Windows\Temp'        = "$env:windir\Temp"
  'Windows 更新下載暫存'         = "$env:windir\SoftwareDistribution\Download"
  'Chrome 快取'                  = "$la\Google\Chrome\User Data\Default\Cache"
  'Edge 快取'                    = "$la\Microsoft\Edge\User Data\Default\Cache"
  '縮圖快取'                     = "$la\Microsoft\Windows\Explorer"
  '錯誤報告 WER'                 = "$env:ProgramData\Microsoft\Windows\WER"
}
$total = 0
foreach ($k in $items.Keys) { $m = SizeMB $items[$k]; $total += $m; W ("  {0,-28} {1,10}" -f $k, $m) }
$rb = 0
try { $sh = New-Object -ComObject Shell.Application; $sh.Namespace(10).Items() | ForEach-Object { $rb += $_.Size } } catch {}
$rbm = [math]::Round($rb / 1MB, 1); $total += $rbm
W ("  {0,-28} {1,10}" -f '資源回收筒', $rbm)
W "  ---- 合計約 $([math]::Round($total/1024,2)) GB"
W ""

W "【三、下載資料夾：超過90天的安裝檔／壓縮檔（需您自行判斷）】"
$dl = Join-Path $env:USERPROFILE 'Downloads'
Get-ChildItem $dl -File -Force | Where-Object { $_.Extension -match '^\.(exe|msi|zip|rar|7z|iso)$' -and $_.LastWriteTime -lt (Get-Date).AddDays(-90) } |
  Sort-Object Length -Descending | Select-Object -First 30 | ForEach-Object {
  W ("  {0,8} MB  {1:yyyy/MM/dd}  {2}" -f [math]::Round($_.Length/1MB,1), $_.LastWriteTime, $_.Name) }
W ""

W "【四、使用者資料夾中最大的 20 個檔案（僅供參考，勿直接刪）】"
Get-ChildItem $env:USERPROFILE -Recurse -File -Force | Where-Object { $_.FullName -notmatch '\\AppData\\' } |
  Sort-Object Length -Descending | Select-Object -First 20 | ForEach-Object {
  W ("  {0,8} MB  {1}" -f [math]::Round($_.Length/1MB,1), $_.FullName) }
W ""

W "【五、開機自動啟動程式（電腦變慢常見原因）】"
Get-CimInstance Win32_StartupCommand | ForEach-Object { W "  - $($_.Name)  [$($_.Location)]" }
W ""

W "【六、已安裝程式（依大小，前 25 名）】"
$keys = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
Get-ItemProperty $keys | Where-Object { $_.DisplayName -and $_.EstimatedSize } | Sort-Object EstimatedSize -Descending |
  Select-Object -First 25 | ForEach-Object {
  W ("  {0,8} MB  {1}" -f [math]::Round($_.EstimatedSize/1024,0), $_.DisplayName) }
W ""

W "【七、硬體概況（判斷變慢原因）】"
$os = Get-CimInstance Win32_OperatingSystem
W "  記憶體：共 $([math]::Round($os.TotalVisibleMemorySize/1MB,1)) GB，目前可用 $([math]::Round($os.FreePhysicalMemory/1MB,1)) GB"
Get-PhysicalDisk | ForEach-Object { W "  硬碟：$($_.FriendlyName)  類型 $($_.MediaType)  健康狀態 $($_.HealthStatus)" }
W ""
W "===== 掃描完成。本工具未刪除任何檔案。 ====="

$lines | Out-File -FilePath $report -Encoding UTF8
Write-Host ""
Write-Host "報告已存到：$report" -ForegroundColor Green
Start-Process notepad.exe $report
