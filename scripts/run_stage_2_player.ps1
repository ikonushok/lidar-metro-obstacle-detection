param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8080,
    [switch]$RebuildData,
    [switch]$NoBrowser,
    [switch]$LegacyLayers,
    [string]$BagName = 'doubleT_obstacle',
    [ValidateRange(0, 1000000)]
    [int]$AuditFirstFrame = 100,
    [ValidatePattern('^(?i:max|[0-9]+)$')]
    [string]$AuditLastFrame = 'max'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if(-not $LegacyLayers -and -not $RebuildData -and (Test-Path -LiteralPath (Join-Path $projectRoot 'dataset/for_hackathon/new_data'))){
    & (Join-Path $PSScriptRoot 'run_stage_2_catalog.ps1') -Port $Port -NoBrowser:$NoBrowser -BagName $BagName
    return
}
$dataRoot = Join-Path $projectRoot "dataset/extracted/$BagName"
$playerRoot = Join-Path $projectRoot "artefacts/stage_2/player_$BagName"
$stage3Root = Join-Path $projectRoot 'artefacts/stage_3'
$stage3Results = Join-Path $stage3Root 'stage_3_results.jsonl'
if (-not (Test-Path -LiteralPath $stage3Results)) {
    $stage3Results = Join-Path $stage3Root 'overlay_replay/stage_3_results.jsonl'
}
$stage3ResultsRelative = $null
if (Test-Path -LiteralPath $stage3Results) {
    $stage3ResultsRelative = $stage3Results.Substring($stage3Root.Length).TrimStart([char]'\', [char]'/' )
    $stage3ResultsRelative = $stage3ResultsRelative.Replace([char]'\', [char]'/' )
}
$manifest = Join-Path $playerRoot 'manifest.json'
$image = 'lidar-mosmetro3d:stage_2-player'

if (-not (Test-Path -LiteralPath $dataRoot)) {
    throw "Bag not found: $dataRoot. Run scripts/extract_stage_1.py first."
}

if ($RebuildData -or -not (Test-Path -LiteralPath $manifest)) {
    & docker build --progress plain -t $image $projectRoot
    if ($LASTEXITCODE -ne 0) { throw "Docker build failed (exit $LASTEXITCODE)" }
    New-Item -ItemType Directory -Force $playerRoot | Out-Null
    $mounts = @(
        '--mount', "type=bind,source=$dataRoot,target=/data,readonly",
        '--mount', "type=bind,source=$playerRoot,target=/output"
    )
    $prepareArgs = @('python3', 'scripts/prepare_stage_2_player.py', '/data', '--output', '/output')
    if ($BagName -eq 'doubleT_obstacle' -and (Test-Path -LiteralPath $stage3Results)) {
        $mounts += @('--mount', "type=bind,source=$stage3Root,target=/stage3,readonly")
        $prepareArgs += @('--stage-3-results', "/stage3/$stage3ResultsRelative")
    }
    & docker run --rm @mounts `
        $image @prepareArgs
    if ($LASTEXITCODE -ne 0) { throw "Player data preparation failed (exit $LASTEXITCODE)" }
}

# Publish the selected UI on every launch without re-exporting immutable XYZ.
$webSource = Join-Path $projectRoot 'web/stage_2_raw_player.html'
if ($LegacyLayers) { $webSource = Join-Path $projectRoot 'web/stage_2_player.html' }
foreach ($asset in @('vendor/three.min.js', 'vendor/OrbitControls.js')) {
    if (-not (Test-Path -LiteralPath (Join-Path $playerRoot $asset))) {
        throw "Missing player asset $asset. Run with -RebuildData."
    }
}
Copy-Item -LiteralPath $webSource -Destination (Join-Path $playerRoot 'index.html') -Force
if (-not $LegacyLayers) {
    Copy-Item -LiteralPath (Join-Path $projectRoot 'web/stage_2_review_layers.js') `
        -Destination (Join-Path $playerRoot 'stage_2_review_layers.js') -Force
    foreach ($asset in @('stage_2_auto_rails.js', 'stage_2_auto_rails_config.json', 'stage_3_live_envelope.js', 'stage_3_live_envelope_config.json', 'stage_3_objects.js', 'stage_3_objects_config.json')) {
        Copy-Item -LiteralPath (Join-Path $projectRoot "web/$asset") -Destination (Join-Path $playerRoot $asset) -Force
    }
}
Write-Output 'Player HTML refreshed. Prepared XYZ frames reused unchanged.'

if ($LegacyLayers -and $BagName -eq 'doubleT_obstacle' -and $null -ne $stage3ResultsRelative) {
    $auditManifest = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    if ($AuditLastFrame -ieq 'max') {
        $auditLastFrameResolved = [int]$auditManifest.frame_count - 1
    } else {
        $auditLastFrameResolved = [int]$AuditLastFrame
    }
    if ($auditLastFrameResolved -lt $AuditFirstFrame) {
        throw 'AuditLastFrame must be greater than or equal to AuditFirstFrame.'
    }
    & docker run --rm `
        --mount "type=bind,source=$playerRoot,target=/output" `
        --mount "type=bind,source=$stage3Root,target=/stage3,readonly" `
        $image python3 scripts/audit_stage_3_candidates.py `
        --results "/stage3/$stage3ResultsRelative" `
        --manifest /output/manifest.json `
        --first-frame $AuditFirstFrame `
        --last-frame $auditLastFrameResolved `
        --full-cloud `
        --output /output/candidate_audit.json
    if ($LASTEXITCODE -ne 0) { throw "Candidate audit failed (exit $LASTEXITCODE)" }
}

$existingListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($null -ne $existingListener) {
    $matchingPlayer = $false
    $portContainers = @(& docker ps --filter "publish=$Port" --format '{{.ID}}')
    foreach ($containerId in $portContainers) {
        $container = (& docker inspect $containerId | ConvertFrom-Json)[0]
        $mount = @($container.Mounts | Where-Object { $_.Destination -eq '/output' })
        if ($mount.Count -ne 1) { continue }
        $servedRoot = [IO.Path]::GetFullPath($mount[0].Source)
        if ($servedRoot -eq [IO.Path]::GetFullPath($playerRoot)) {
            $matchingPlayer = $true
        } elseif ($servedRoot -eq [IO.Path]::GetFullPath((Join-Path $projectRoot 'artefacts/stage_2/player'))) {
            # This project's legacy server points to obsolete assets.
            & docker stop $containerId | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Could not stop the legacy player server.' }
        }
    }
    if (-not $matchingPlayer) {
        $existingListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($null -ne $existingListener) {
            throw "Port $Port is occupied by a server that does not serve $playerRoot. Use -Port with a free port."
        }
    }
    if ($matchingPlayer) {
    $url = "http://localhost:$Port"
    if (-not $LegacyLayers) { $url += '/?v=membership-1' }
    if (-not $NoBrowser) { Start-Process $url }
    Write-Output "Player is already available at $url; existing server is reused. Press Ctrl+C in its original PowerShell window to stop it."
    return
    }
}

& docker image inspect $image --format '{{.Id}}' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    & docker build --progress plain -t $image $projectRoot
    if ($LASTEXITCODE -ne 0) { throw "Docker build failed (exit $LASTEXITCODE)" }
}
$serverJob = Start-Job -ScriptBlock {
    param($ServerPort, $ServerRoot, $ServerImage)
    & docker run --rm --publish "${ServerPort}:8000" `
        --mount "type=bind,source=$ServerRoot,target=/output,readonly" `
        $ServerImage python3 -m http.server 8000 --directory /output
} -ArgumentList $Port, $playerRoot, $image

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
        throw "Local player server did not become available at http://localhost:$Port. Docker output: $serverOutput"
    }
    $url = "http://localhost:$Port"
    if (-not $LegacyLayers) { $url += '/?v=membership-1' }
    if (-not $NoBrowser) { Start-Process $url }
    Write-Output "Player is available at $url. Press Ctrl+C here to stop the local player."
    Wait-Job -Job $serverJob | Out-Null
    Receive-Job -Job $serverJob
} finally {
    if ($serverJob.State -eq 'Running') { Stop-Job -Job $serverJob }
    Remove-Job -Job $serverJob -Force -ErrorAction SilentlyContinue
}
