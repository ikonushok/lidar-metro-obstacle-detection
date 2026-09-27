# Описание решения

Статус: сдачный срез на 2026-09-27. Это хакатонный прототип для
обнаружения кандидатов препятствий в габарите движения поезда метро по данным
3D-лидара. Решение не является сертифицированной системой безопасности и не
выдаёт разрешение на движение поезда.

## 1. Кратко

Решение принимает облако точек `sensor_msgs/msg/PointCloud2`, строит локальную
ось рельсов, протягивает вдоль неё габарит поезда и ищет связные компоненты
точек внутри контролируемой зоны. Для подавления инфраструктурного шума
используется лёгкая C++-встроенная модель `candidate_baseline_v2`.

Основной выход:

- `intrusion_candidate_present` — найден ли reportable-кандидат препятствия;
- `nearest_reportable_intrusion_distance_from_source_origin_m` — расстояние до
  ближайшей reportable-точки от начала координат исходного облака;
- `status`, `system_status`, diagnostics — почему кандидат найден, подавлен
  или состояние осталось неопределённым;
- `safety_decision_permitted=false` — модуль не разрешает движение.

Важно: `UNKNOWN` и отсутствие reportable-кандидата не означают подтверждённый
`CLEAR`.

## 2. Что получает проверяющий

Репозиторий содержит:

- Docker-сборку на базе `ros:humble-ros-base-jammy`;
- C++ ядро обработки облака;
- ROS2 node `curve_envelope_node` для сценария `ros2 bag play`;
- direct HTTP-плеер для просмотра подготовленных датасетов;
- скрипты подготовки локальных датасетов из `dataset/raw`;
- документацию и gate-проверку состава сдачного репозитория.

Данные не входят в Git и Docker image. Проверяющий кладёт архивы локально в
`dataset/raw`, затем запускает подготовительный скрипт.

## 3. Входные данные

Ожидаемый runtime-вход — ROS2 bag с сообщениями
`sensor_msgs/msg/PointCloud2`.

Поддерживаемые практические варианты:

- direct player/catalog: архивы в `dataset/for_hackathon`;
- headless ROS2: распакованный bag-каталог в `dataset/extracted/<source>`.

Для сдачного player-сценария используются три локальных архива без расширения:

```text
dataset/raw/for_hackathon
dataset/raw/new_data
dataset/raw/cloud_with_fake_obj
```

После подготовки они появляются как ignored-файлы/каталоги в
`dataset/for_hackathon` или `dataset/extracted`. Эти пути намеренно не
отслеживаются Git.

## 4. Архитектура

Оба режима запуска используют одно C++ ядро.

```text
PointCloud2 / XYZ
  -> quality gate входа
  -> поиск локальной оси рельсов
  -> построение габарита поезда с tangent-продолжением
  -> raw CORE-точки внутри габарита
  -> связные компоненты
  -> candidate_baseline_v2: reportable candidate / ignored noise
  -> JSON diagnostics
```

Direct player:

```text
архив bag -> XYZ -> C++ stdin/stdout -> HTTP JSON -> web player
```

ROS2 path:

```text
ros2 bag play -> PointCloud2 -> curve_envelope_node -> std_msgs/String JSON
```

Входной топик и `source_frame` задаются параметрами. Имя топика не считается
доказательством системы координат: `source_frame` должен соответствовать
реальному `header.frame_id` сообщения.

## 5. Алгоритм

1. Декодируется фактическая схема `PointCloud2`: поля, offsets, datatype,
   endian, `point_step`, `row_step`.
2. Невалидные и нулевые XYZ-точки не используются как препятствия.
3. Из текущего облака выбираются наблюдаемые пары рельсов.
4. По ним строится локальная ось пути.
5. Вдоль оси протягивается контролируемый габарит.
6. Точки внутри CORE-зоны группируются в компоненты.
7. Модель `candidate_baseline_v2` подавляет компоненты, похожие на шум или
   инфраструктуру.
8. Для reportable-компонент вычисляется ближайшая дистанция и диагностический
   статус.

Текущий сдачный режим:

```text
rail_selection_method = development_candidate
rail_forward_min_m    = 2.0
forward_extension     = tangent
noise_filter_mode     = candidate_baseline_v2
```

Параметр 80 м в конфигурации tangent-графа — это предел продолжения рабочей
геометрии, а не подтверждённая дальность обнаружения.

## 6. Визуальный пример

Кадры ниже взяты из локального player-сценария.

![Облако тоннеля](docs/presentation/picts/reference_01_tunnel.png)

![Ось рельсов и дальность](docs/presentation/picts/reference_02_rails_axis.png)

![Габарит поезда](docs/presentation/picts/reference_03_train_envelope.png)

![Кандидат препятствия](docs/presentation/picts/reference_05_obstacle.png)

## 7. Как запустить

### 7.1. Подготовить данные

Положить исходные архивы в `dataset/raw`, затем из корня репозитория:

```powershell
python .\scripts\prepare_hackathon_datasets.py
```

Скрипт не добавляет данные в Git. Он готовит локальные ignored-пути для
плеера и, при необходимости, распаковки для ROS2 replay.

### 7.2. Собрать Docker image

```powershell
docker build -t lidar-metro-obstacle-detection:submission .
```

### 7.3. Запустить плеер

```powershell
.\scripts\run_stage_2_cpu_player.ps1 `
  -Port 8100 `
  -RailSelectionMethod development_candidate `
  -RailForwardMinM 2 `
  -ForwardExtensionMethod tangent `
  -NoiseFilterMode candidate_baseline_v2 `
  -Image lidar-metro-obstacle-detection:submission `
  -NoBrowser
```

Открыть:

```text
http://localhost:8100/
```

В плеере доступны подготовленные источники, включая обычные сцены, длинный
проезд `new_data`, synthetic fake-object dataset и development-сцену
`doubleT_obstacle`.

### 7.4. Запустить headless ROS2 replay

Пример для распакованного `dataset/extracted/doubleT_obstacle`:

```powershell
$bagPath = (Resolve-Path 'dataset/extracted/doubleT_obstacle').Path

docker run --rm -d --name lidar-detector --shm-size=1g `
  -e ROS_DOMAIN_ID=172 -e ROS_LOCALHOST_ONLY=1 `
  --mount "type=bind,source=$bagPath,target=/data,readonly" `
  lidar-metro-obstacle-detection:submission `
  ros2 run lidar_mosmetro3d_cpp curve_envelope_node --ros-args `
  -p input_topic:=/sensing/lidar/hesai128/pointcloud `
  -p source_frame:=lidar_livox `
  -p output_topic:=/stage_3/curve_envelope_candidate `
  -p compute_backend:=cpu `
  -p rail_selection_method:=development_candidate `
  -p rail_forward_min_m:=2.0 `
  -p forward_extension_method:=tangent `
  -p noise_filter_mode:=candidate_baseline_v2
```

В отдельном окне:

```powershell
docker exec -it lidar-detector /ros_entrypoint.sh `
  ros2 topic echo /stage_3/curve_envelope_candidate std_msgs/msg/String --field data
```

В третьем окне:

```powershell
docker exec -it lidar-detector /ros_entrypoint.sh ros2 bag info /data
docker exec -it lidar-detector /ros_entrypoint.sh ros2 bag play /data --rate 0.2 --read-ahead-queue-size 2
```

Остановить:

```powershell
docker stop lidar-detector
```

Для нового bag нужно заменить `input_topic` по выводу `ros2 bag info`, а
`source_frame` — по фактическому `header.frame_id` PointCloud2.

## 8. Подтверждённые проверки текущего среза

| Проверка | Результат |
|---|---|
| Repo gate `scripts/check_submission_package.py --require-clean` | PASS |
| Docker build `lidar-metro-obstacle-detection:submission` | PASS |
| Direct player на локальных подготовленных архивах | PASS |
| `/datasets.json` в плеере | 8 source ID |
| `cloud_with_fake_obj` manifest | `frame_count=1510`, `runtime_transport=direct_cpp` |
| `doubleT_obstacle` frame 13 | найден candidate, дистанция около `55.568` м |
| Headless ROS2 full slowed replay `doubleT_obstacle` | 201 JSON outputs на 201 PointCloud2 inputs |
| ROS2 alarms on slowed replay | 51 alarm frame |

Docker image, зафиксированный в проверке:

```text
sha256:c4cf115060bd918c1ae7f6347b6afce37abfb4cb73d8cb9c408c54391f63dff1
```

Во время ROS2 replay на Windows/Docker bind mount наблюдались предупреждения
`Message queue starved`. Поэтому этот прогон подтверждает интерфейс и
завершение обработки, но не доказывает real-time throughput.

Эти проверки подтверждают воспроизводимость интерфейсов сдачного среза, но не
заменяют скрытую проверку жюри на новых данных.

## 9. Ограничения

- Геометрия габарита имеет статус engineering assumption: нет внешней
  калибровки монтажа, `/tf`, карты, IMU и одометрии.
- `source_frame` и направление движения должны быть проверены для нового bag.
- Расстояние считается от начала координат исходного облака, не от носа поезда.
- `candidate_baseline_v2` — фильтр кандидатов, а не safety-доказательство
  свободного пути.
- `UNKNOWN` не превращается в `CLEAR`.
- Full real-time, p95/p99 latency, drops и ресурсы на целевом стенде не
  заявлены.
- CUDA, deskew, tracking, TTC и управление поездом не входят в сдачный MVP.
- Synthetic/fake-object dataset нужен для демонстрационной проверки, но не
  заменяет скрытую проверку жюри на реальных данных.

## 10. Структура важных файлов

```text
Dockerfile
README.md
SOLUTION.md
scripts/prepare_hackathon_datasets.py
scripts/run_stage_2_cpu_player.ps1
scripts/check_submission_package.py
src/cpp/
models/noise_classifier_candidate_baseline_v2.json
web/
docs/README_REVIEWER_PLAYER_QUICKSTART.md
docs/README_SUBMISSION_CHECKLIST.md
```

## 11. Вывод

Сдачный прототип решает задачу как candidate-only pipeline: по облаку точек он
строит локальный габарит движения поезда, выделяет компоненты внутри него и
публикует диагностический сигнал о потенциальном препятствии. Решение
воспроизводимо через Docker, direct player и headless ROS2 replay, но честно
сохраняет ограничения MVP: отсутствие production-safety claim, отсутствие
подтверждённого `CLEAR` и отсутствие доказанного real-time throughput.
