param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8094,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$viewerRoot = Join-Path $projectRoot 'artefacts\stage_4\cpu_viewer'
$image = 'lidar-mosmetro3d:stage-4-cpu-viewer'

foreach ($required in @('index.html', 'manifest.json', 'results.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $viewerRoot $required))) {
        throw "Viewer dataset is missing ${required}: $viewerRoot. Run the CPU viewer export first."
    }
}

$url = "http://localhost:$Port/"
if (Test-NetConnection -ComputerName localhost -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue) {
    if (-not $NoBrowser) { Start-Process $url }
    Write-Output "Viewer port $Port is already active. Open $url"
    return
}

$serverJob = Start-Job -ScriptBlock {
    param($ServerPort, $ServerRoot, $ServerImage)
    & docker run --rm --publish "${ServerPort}:8000" `
        --mount "type=bind,source=$ServerRoot,target=/output,readonly" `
        $ServerImage python3 -m http.server 8000 --directory /output
} -ArgumentList $Port, $viewerRoot, $image

try {
    $deadline = (Get-Date).AddSeconds(15)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        if (Test-NetConnection -ComputerName localhost -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue) {
            $ready = $true
            break
        }
        if ($serverJob.State -in @('Completed', 'Failed', 'Stopped')) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $ready) {
        $serverOutput = Receive-Job -Job $serverJob -Keep 2>&1 | Out-String
        throw "CPU viewer did not become available at $url. Docker output: $serverOutput"
    }
    if (-not $NoBrowser) { Start-Process $url }
    Write-Output "CPU viewer is available at $url. Press Ctrl+C to stop it."
    Wait-Job -Job $serverJob | Out-Null
    Receive-Job -Job $serverJob -ErrorAction Continue
} finally {
    if ($serverJob.State -eq 'Running') { Stop-Job -Job $serverJob }
    Remove-Job -Job $serverJob -Force -ErrorAction SilentlyContinue
}
