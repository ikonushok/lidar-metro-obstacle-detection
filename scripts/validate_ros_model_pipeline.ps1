param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8100,
    [string]$Image = 'lidar-mosmetro3d:stage-4-cpu-viewer',
    [switch]$SkipViewerCheck
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$outputDir = Join-Path $projectRoot 'artefacts/stage_5/direct_player'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
# Separate DDS domain from the viewer. The image profile uses SHM for large clouds.
$testDomainId = (($Port % 232) + 2) % 232
& docker run --rm --shm-size=512m -e ROS_DOMAIN_ID=$testDomainId `
    --mount "type=bind,source=$projectRoot,target=/workspace,readonly" `
    --mount "type=bind,source=$outputDir,target=/output" `
    $Image python3 /app/scripts/check_ros_model_pipeline.py --root /workspace --output /output/parity.json
if ($LASTEXITCODE -ne 0) { throw 'ROS2 model integration check failed.' }

if (-not $SkipViewerCheck) {
    $baseUrl = "http://localhost:$Port"
    $manifest = Invoke-RestMethod "$baseUrl/api/cpu_sources/doubleT_obstacle/manifest.json" -TimeoutSec 60
    if ($manifest.runtime_transport -ne 'direct_cpp' -or $manifest.noise_filter_mode -ne 'candidate_baseline_v2' -or
        $manifest.forward_extension_config.method -ne 'tangent' -or
        $manifest.rail_search_config.forward_min_m -ne 2.0) {
        throw 'Viewer must use direct_cpp + candidate_baseline_v2 + tangent + RailForwardMinM=2. Restart with the documented command.'
    }
    $checks = foreach ($index in @(13, 145)) {
        $response = Invoke-RestMethod "$baseUrl/api/cpu_sources/doubleT_obstacle/$index.json" -TimeoutSec 60
        $result = $response.result
        if ($result.runtime_transport -ne 'direct_cpp' -or $result.noise_filter_mode -ne 'candidate_baseline_v2' -or
            $result.forward_extension_method -ne 'tangent' -or $result.safety_decision_permitted -ne $false -or
            $result.source_frame -ne $response.frame.source_frame -or
            $result.header_timestamp_ns -ne [string]$response.frame.header_timestamp_ns -or
            $result.intrusion_candidate_present -ne ($index -eq 13)) {
            throw "Viewer result mismatch at frame $index."
        }
        [PSCustomObject]@{
            frame = $index
            candidate = $result.intrusion_candidate_present
            reportable_core_count = $result.reportable_core_count
            runtime_transport = $result.runtime_transport
            noise_filter_mode = $result.noise_filter_mode
        }
    }
    $checks | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputDir 'viewer_http.json') -Encoding UTF8
    $checks | Format-Table
    Write-Output "PASS: direct C++ -> candidate_baseline_v2 -> viewer API at $baseUrl; separate ROS2 parity passed."
}
Write-Output "PASS: integration evidence in $outputDir (development data; not independent quality validation)."
