# Headless ROS2 C++ Performance Report

Дата: 2026-09-28.

## Цель

Проверить быстродействие основного runtime-пути без browser/HTTP player:

```text
ros2 bag play -> PointCloud2 -> curve_envelope_node -> std_msgs/String JSON
```

Это замер C++ ROS2 detector path, а не direct player и не веб-визуализация.

## Evidence

- Docker image: `lidar-metro-obstacle-detection:submission`
  (`sha256:e292698a910bd605d75f571f89f5c10fedb499e6a3259cedf418fcddb001e4be`).
- Detector container: `curve_envelope_node`, `compute_backend=cpu`,
  `rail_selection_method=development_candidate`, `rail_forward_min_m=2.0`,
  `forward_extension_method=tangent`, `noise_filter_mode=baseline_v3`.
- Production/performance output mode: `diagnostics_detail=summary`.
- Bag: `dataset/extracted/doubleT_obstacle`.
- Bag info: `201` сообщений `sensor_msgs/msg/PointCloud2` на
  `/sensing/lidar/hesai128/pointcloud`, длительность `20.392030296s`, размер
  `4.5 GiB`.
- Выход: `/stage_3/curve_envelope_candidate`, `std_msgs/msg/String` JSON.
- Измеритель: `scripts/measure_headless_ros2_cpp_performance.py`; collector,
  копируемый внутрь container: `scripts/headless_ros2_perf_collector.py`.

## Выполненные команды

```powershell
docker build -t lidar-metro-obstacle-detection:submission .

.\scripts\validate_ros_model_pipeline.ps1 `
  -Image lidar-metro-obstacle-detection:submission `
  -SkipViewerCheck

.\scripts\run_submission_ros2_demo.ps1 `
  -StopExisting `
  -Rate 1.0 `
  -ReadAheadQueueSize 20 `
  -DiagnosticsDetail summary

python .\scripts\measure_headless_ros2_cpp_performance.py `
  --rate 1.0 `
  --read-ahead-queue-size 20 `
  --expected-messages 201 `
  --collector-timeout-seconds 210 `
  --output-stem headless_ros2_cpp_performance_rate_1p0_summary_diagnostics
```

## Результаты

| Сценарий | Выход JSON | `processing_ms` p50/p95/p99/max | replay wall | Docker CPU/RAM | Очередь |
|---|---:|---:|---:|---:|---|
| До оптимизации, full diagnostics | `187/201` | `313.43 / 350.23 / 355.48 / 377.73` ms | `112.25` s | max `136.52%`, max `883.3` MiB | `Message queue starved` |
| После PointCloud compaction, full diagnostics | `187/201` | `223.28 / 230.64 / 235.35 / 237.90` ms | `122.89` s | max `141.55%`, max `905.8` MiB | `Message queue starved` |
| Текущий production/perf mode, `diagnostics_detail=summary` | `187/201` | `67.12 / 71.78 / 73.40 / 74.96` ms | `110.19` s | max `146.06%`, max `929.1` MiB | `Message queue starved` |

Сырые артефакты основного текущего замера:

- `artefacts/current_model_validation/headless_ros2_cpp_performance_rate_1p0_summary_diagnostics_summary.json`
- `artefacts/current_model_validation/headless_ros2_cpp_performance_rate_1p0_summary_diagnostics_messages.jsonl`
- `artefacts/current_model_validation/headless_ros2_cpp_performance_rate_1p0_summary_diagnostics_docker_stats.jsonl`
- `artefacts/current_model_validation/headless_ros2_cpp_performance_rate_1p0_summary_diagnostics_bag_play.log`
- `artefacts/current_model_validation/headless_ros2_cpp_performance_rate_1p0_summary_diagnostics_collector_stderr.log`

Полный диагностический режим сохранён для viewer/debug. В нём публикуются
крупные массивы индексов и wireframe; для проверки вычислительного бюджета
детектора используется `diagnostics_detail=summary`.

## Вывод

Да, код ускорен. На том же headless ROS2/C++ пути без плеера `processing_ms` p95
снизился с `350.23` ms до `71.78` ms. Для лидара около `10 Hz` это укладывается
в инженерный бюджет `100` ms на кадр по вычислительной части detector node.

При этом локальный end-to-end replay через `ros2 bag play` на Windows/Docker
всё ещё не является доказанным real-time прогоном: получено `187/201` JSON,
`rosbag2_player` сообщает `Message queue starved`, а wall time replay намного
дольше длительности bag. Это похоже на ограничение replay/storage/backpressure
в текущем стенде, но требует подтверждения на целевом Ubuntu 22.04 / ROS 2
Humble / Docker host.

Формулировка для сдачи: C++ detector compute в текущем production/perf режиме
имеет запас для потока порядка `10 Hz` на проверенном development bag; полный
end-to-end real-time replay на целевом стенде пока не закрыт.

## Уровень валидации

L1/L3 для одного development bag в Docker/Humble headless ROS2 path. Не является
L4/L5, не проверяет стенд заказчика, независимые проезды, GPU/CUDA, tuning под
целевое железо или production safety.

## Что не проверено

- Целевой стенд заказчика Intel Core i7-9700E / 128 GiB / RTX 4070 Ti SUPER.
- Запуск того же performance script внутри Ubuntu Docker host без Windows bind
  mount overhead.
- Несколько независимых bag и скрытый test set.
- Причина недобора `14` выходных сообщений в локальном replay.

## Следующий минимальный тест

Повторить:

```powershell
.\scripts\run_submission_ros2_demo.ps1 -StopExisting -Rate 1.0 -ReadAheadQueueSize 20 -DiagnosticsDetail summary
python .\scripts\measure_headless_ros2_cpp_performance.py --rate 1.0 --read-ahead-queue-size 20 --expected-messages 201 --collector-timeout-seconds 210 --output-stem headless_ros2_cpp_performance_rate_1p0_summary_diagnostics
```

на целевом Ubuntu/Humble/Docker стенде и зафиксировать counts, drops,
`Message queue starved`, p50/p95/p99/max, CPU/RAM и replay wall time.
