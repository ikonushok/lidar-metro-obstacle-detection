param(
    [string]$BagPath = '',
    [string]$Image = 'lidar-metro-obstacle-detection:submission',
    [string]$ContainerName = 'lidar-detector',
    [string]$InputTopic = '/sensing/lidar/hesai128/pointcloud',
    [string]$SourceFrame = 'lidar_livox',
    [string]$OutputTopic = '/stage_3/curve_envelope_candidate',
    [ValidateRange(0.05, 4.0)]
    [double]$Rate = 0.2,
    [ValidateRange(1, 1000)]
    [int]$ReadAheadQueueSize = 20,
    [ValidateRange(1, 231)]
    [int]$RosDomainId = 172,
    [switch]$BuildImage,
    [switch]$StopExisting,
    [switch]$Play
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($BagPath)) {
    $BagPath = Join-Path $projectRoot 'dataset\extracted\doubleT_obstacle'
}

$resolvedBag = (Resolve-Path -LiteralPath $BagPath).Path
$metadata = Join-Path $resolvedBag 'metadata.yaml'
if (-not (Test-Path -LiteralPath $metadata)) {
    throw "BagPath must point to an extracted ROS2 bag directory with metadata.yaml: $resolvedBag"
}

$existing = @(& docker ps -a --filter "name=^/$ContainerName$" --format '{{.Names}}')
if ($existing.Count -gt 0) {
    if (-not $StopExisting) {
        throw "Container '$ContainerName' already exists. Re-run with -StopExisting or choose -ContainerName."
    }
    & docker stop $ContainerName 2>$null | Out-Null
    & docker rm $ContainerName 2>$null | Out-Null
}

& docker image inspect $Image --format '{{.Id}}' 2>$null | Out-Null
if ($BuildImage -or $LASTEXITCODE -ne 0) {
    & docker build -t $Image $projectRoot
    if ($LASTEXITCODE -ne 0) { throw "Docker build failed (exit $LASTEXITCODE)." }
}

& docker run --rm -d --name $ContainerName --shm-size=1g `
    -e ROS_DOMAIN_ID=$RosDomainId -e ROS_LOCALHOST_ONLY=1 `
    --mount "type=bind,source=$resolvedBag,target=/data,readonly" `
    $Image `
    ros2 run lidar_mosmetro3d_cpp curve_envelope_node --ros-args `
    -p input_topic:=$InputTopic `
    -p source_frame:=$SourceFrame `
    -p output_topic:=$OutputTopic `
    -p compute_backend:=cpu `
    -p rail_selection_method:=development_candidate `
    -p rail_forward_min_m:=2.0 `
    -p forward_extension_method:=tangent `
    -p noise_filter_mode:=baseline_v3
if ($LASTEXITCODE -ne 0) { throw 'Detector container failed to start.' }

Write-Output "Detector started: $ContainerName"
Write-Output "Runtime: baseline_v3, development_candidate, tangent, source_frame=$SourceFrame, input_topic=$InputTopic"
Write-Output "Inspect bag:"
Write-Output "  docker exec -it $ContainerName /ros_entrypoint.sh ros2 bag info /data"
Write-Output "Read detector JSON:"
Write-Output "  docker exec -it $ContainerName /ros_entrypoint.sh ros2 topic echo $OutputTopic std_msgs/msg/String --field data"
Write-Output "Play bag:"
Write-Output "  docker exec -it $ContainerName /ros_entrypoint.sh ros2 bag play /data --rate $Rate --read-ahead-queue-size $ReadAheadQueueSize"
Write-Output "Stop:"
Write-Output "  docker stop $ContainerName"

if ($Play) {
    & docker exec $ContainerName /ros_entrypoint.sh ros2 bag info /data
    & docker exec $ContainerName /ros_entrypoint.sh ros2 bag play /data --rate $Rate --read-ahead-queue-size $ReadAheadQueueSize
}
