# Headless ROS2 Smoke Report

Дата: 2026-09-27.

## Цель

Проверить понятный запуск без браузера:

```text
ros2 bag play -> PointCloud2 -> curve_envelope_node -> std_msgs/String JSON
```

## Evidence

- Docker image: `lidar-metro-obstacle-detection:submission`.
- Image id: `sha256:9686850054da221452d9fe0ee65ed4932ad78581274fc947865d8bfa9e7e0ec1`.
- Bag: `dataset/extracted/doubleT_obstacle`.
- Bag info: `201` сообщений `sensor_msgs/msg/PointCloud2` на `/sensing/lidar/hesai128/pointcloud`, длительность `20.392030296s`.

## Выполненные команды

```powershell
.\scripts\run_submission_ros2_demo.ps1 -StopExisting
docker exec lidar-detector /ros_entrypoint.sh ros2 bag info /data
docker exec lidar-detector /ros_entrypoint.sh ros2 topic list -t
```

Smoke публикации JSON:

```powershell
$echoJob = Start-Job -ScriptBlock {
  docker exec lidar-detector /ros_entrypoint.sh `
    ros2 topic echo /stage_3/curve_envelope_candidate std_msgs/msg/String --field data --once
}
Start-Sleep -Seconds 2
docker exec -d lidar-detector /ros_entrypoint.sh `
  ros2 bag play /data --rate 0.2 --read-ahead-queue-size 20
Wait-Job $echoJob -Timeout 90
Receive-Job $echoJob
docker exec lidar-detector /bin/bash -lc "pkill -f 'ros2 bag play /data' || true"
docker stop lidar-detector
```

## Результат

PASS. `ros2 topic echo --once` получил JSON результата детектора.

Ключевые поля полученного сообщения:

| Поле | Значение |
|---|---|
| `format` | `lidar-curve-envelope-v1` |
| `runtime_transport` | `ros2` |
| `noise_filter_mode` | `baseline_v3` |
| `rail_selection_method` | `development_candidate` |
| `forward_extension_method` | `tangent` |
| `source_frame` | `lidar_livox` |
| `safety_decision_permitted` | `false` |
| `system_status` | `UNKNOWN` |

## Наблюдение по real-time

Отдельная проба `ros2 bag play --rate 1.0 --read-ahead-queue-size 2` на этом
Windows/Docker bind mount дала повторяющиеся предупреждения
`Message queue starved`. Поэтому для демо по умолчанию используется
`--rate 0.2 --read-ahead-queue-size 20`, а full real-time throughput остаётся
отдельной проверкой с counts, drops, latency и ресурсами.

## Уровень валидации

L1/L2 для запуска и ROS2-интеграционного smoke на development bag. Это не
независимая оценка качества и не production real-time proof.
