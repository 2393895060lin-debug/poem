$pythonExe = "C:\Users\MR\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$serverScript = Join-Path $PSScriptRoot "server.py"
$preferredPort = 8772
$poemDataDir = "D:\poem_data"
$logDir = Join-Path $poemDataDir "logs"
$pycacheDir = Join-Path $poemDataDir "pycache"
$stdoutLog = Join-Path $logDir "server.stdout.log"
$stderrLog = Join-Path $logDir "server.stderr.log"

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = ($listener.LocalEndpoint).Port
    $listener.Stop()
    return $port
}

function Test-HttpOk($url) {
    try {
        $response = Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

$null = New-Item -ItemType Directory -Force -Path $poemDataDir, $logDir, $pycacheDir

$port = $preferredPort
$url = "http://127.0.0.1:$port/"

Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*$serverScript*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$existing = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty OwningProcess
if ($existing) {
    $commandLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $existing").CommandLine
    if ($commandLine -notlike "*$serverScript*") {
        $port = Get-FreePort
        $url = "http://127.0.0.1:$port/"
    }
}

$env:POEM_UI_PORT = "$port"
$env:POEM_DATA_DIR = $poemDataDir
$env:PYTHONPYCACHEPREFIX = $pycacheDir

Start-Process -FilePath $pythonExe `
    -ArgumentList $serverScript `
    -WorkingDirectory $PSScriptRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog | Out-Null

for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 250
    if (Test-HttpOk $url) {
        break
    }
}

Start-Process $url
