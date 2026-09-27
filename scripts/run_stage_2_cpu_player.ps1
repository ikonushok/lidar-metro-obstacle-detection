param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8094,
    [switch]$NoBrowser,
    [Alias('RebuildResults')]
    [switch]$RebuildImage,
    [switch]$Measure,
    [ValidateSet('baseline', 'development_candidate')]
    [string]$RailSelectionMethod = 'development_candidate',
    [ValidateRange(0.0, 10.0)]
    [double]$RailForwardMinM = 2.0,
    [ValidateSet('tangent', 'arc_limited')]
    [string]$ForwardExtensionMethod = 'tangent',
    [ValidateRange(0.0, 80.0)]
    [double]$ArcExtensionHorizonM = 0.0,
    [ValidateRange(1.0, 10000.0)]
    [double]$MinArcRadiusM = 60.0,
    [ValidateRange(0.1, 90.0)]
    [double]$MaxArcTurnDeg = 8.0,
    [ValidateRange(3, 50)]
    [int]$ArcFitWindowPairs = 5,
    [ValidateSet('legacy', 'baseline_v3_assist_score', 'baseline_v3')]
    [string]$NoiseFilterMode = 'baseline_v3',
    [string]$Image = 'lidar-mosmetro3d:stage-4-cpu-viewer',
    [string]$Dockerfile = '',
    [ValidateRange(0, 1000000)]
    [int]$FirstIndex = 1050,
    [ValidateRange(0, 1000000)]
    [int]$LastIndex = 1150
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$image = $Image
$dockerfilePath = if ([string]::IsNullOrWhiteSpace($Dockerfile)) {
    Join-Path $projectRoot 'Dockerfile'
} elseif ([IO.Path]::IsPathRooted($Dockerfile)) {
    $Dockerfile
} else {
    Join-Path $projectRoot $Dockerfile
}
$railForwardMinTag = $RailForwardMinM.ToString('0.###', [Globalization.CultureInfo]::InvariantCulture).Replace('.', 'p')
$arcHorizonTag = $ArcExtensionHorizonM.ToString('0.###', [Globalization.CultureInfo]::InvariantCulture).Replace('.', 'p')
$minArcRadiusTag = $MinArcRadiusM.ToString('0.###', [Globalization.CultureInfo]::InvariantCulture).Replace('.', 'p')
$maxArcTurnTag = $MaxArcTurnDeg.ToString('0.###', [Globalization.CultureInfo]::InvariantCulture).Replace('.', 'p')
$runtimeTransport = if ($RailSelectionMethod -eq 'development_candidate') { 'direct_cpp' } else { 'ros2' }
$name = "lidar-cpu-catalog-$Port-$runtimeTransport-$RailSelectionMethod-fmin$railForwardMinTag-$ForwardExtensionMethod-arc$arcHorizonTag-r$minArcRadiusTag-turn$maxArcTurnTag-fit$ArcFitWindowPairs-$NoiseFilterMode"
$rosDomainId = ($Port % 232) + 1
$profile = Join-Path $projectRoot 'artefacts\stage_3\cpp_envelope_core\fastdds_udp_smoke.xml'
$viewerAssets = Join-Path $projectRoot 'artefacts\stage_4\cpu_viewer\vendor\three.min.js'

if ($LastIndex -lt $FirstIndex) { throw 'LastIndex must be greater than or equal to FirstIndex.' }
if (-not (Test-Path -LiteralPath $profile)) { throw "Missing Fast DDS UDP profile: $profile" }
if (-not (Test-Path -LiteralPath $viewerAssets)) { throw "Missing viewer assets. Run the previous CPU viewer export once." }
& docker image inspect $image --format '{{.Id}}' 2>$null | Out-Null
if ($RebuildImage -or $LASTEXITCODE -ne 0) {
    & docker build -t $image -f $dockerfilePath $projectRoot
    if ($LASTEXITCODE -ne 0) { throw "CPU viewer image build failed (exit $LASTEXITCODE)" }
}

if ($Measure) {
    & docker run --rm `
        -e ROS_DOMAIN_ID=$rosDomainId `
        -e FASTRTPS_DEFAULT_PROFILES_FILE=/workspace/artefacts/stage_3/cpp_envelope_core/fastdds_udp_smoke.xml `
        --mount "type=bind,source=$projectRoot,target=/workspace,readonly" `
        --mount "type=bind,source=$projectRoot\artefacts\stage_4,target=/output" `
        $image python3 /app/scripts/measure_cpu_catalog_window.py --root /workspace `
        --first-index $FirstIndex --last-index $LastIndex --rail-selection-method $RailSelectionMethod `
        --rail-forward-min-m $RailForwardMinM --forward-extension-method $ForwardExtensionMethod `
        --arc-extension-horizon-m $ArcExtensionHorizonM --min-arc-radius-m $MinArcRadiusM `
        --max-arc-turn-deg $MaxArcTurnDeg --arc-fit-window-pairs $ArcFitWindowPairs `
        --noise-filter-mode $NoiseFilterMode `
        --output /output/cpu_catalog_metrics.json
    if ($LASTEXITCODE -ne 0) { throw "CPU contiguous-window measurement failed (exit $LASTEXITCODE)" }
}

$running = @(& docker ps --filter "publish=$Port" --format '{{.ID}}')
foreach ($id in $running) {
    $info = (& docker inspect $id | ConvertFrom-Json)[0]
    if ($info.Name -eq "/$name") {
        $url = "http://localhost:$Port/"
        Write-Output "CPU catalog already available: $url"
        if (-not $NoBrowser) { Start-Process $url }
        return
    }
    throw "Port $Port belongs to another server; use another -Port."
}

& docker run --rm -d --name $name --publish "127.0.0.1:${Port}:8000" `
    --mount "type=bind,source=$projectRoot,target=/workspace,readonly" `
    -e PYTHONPATH=/workspace/src:/app/src `
    -e ROS_DOMAIN_ID=$rosDomainId `
    -e FASTRTPS_DEFAULT_PROFILES_FILE=/workspace/artefacts/stage_3/cpp_envelope_core/fastdds_udp_smoke.xml `
    $image python3 /app/scripts/serve_stage_2_cpu_catalog.py --root /workspace `
    --rail-selection-method $RailSelectionMethod --rail-forward-min-m $RailForwardMinM `
    --forward-extension-method $ForwardExtensionMethod --arc-extension-horizon-m $ArcExtensionHorizonM `
    --min-arc-radius-m $MinArcRadiusM --max-arc-turn-deg $MaxArcTurnDeg `
    --arc-fit-window-pairs $ArcFitWindowPairs `
    --noise-filter-mode $NoiseFilterMode
if ($LASTEXITCODE -ne 0) { throw 'CPU catalog server failed to start' }
$url = "http://localhost:$Port/"
Write-Output "CPU catalog (transport=$runtimeTransport; C++ rails -> $ForwardExtensionMethod/envelope -> $NoiseFilterMode -> JSON -> viewer; $RailSelectionMethod, rail_forward_min_m=$RailForwardMinM, arc_extension_horizon_m=$ArcExtensionHorizonM, min_arc_radius_m=$MinArcRadiusM, max_arc_turn_deg=$MaxArcTurnDeg, arc_fit_window_pairs=$ArcFitWindowPairs): $url (stop: docker stop $name)"
if (-not $NoBrowser) { Start-Process $url }
