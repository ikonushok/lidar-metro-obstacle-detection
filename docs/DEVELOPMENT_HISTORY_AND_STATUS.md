# История работ и текущий статус

Статус: публичная сводка для сдачного среза, 2026-09-27.

Этот документ показывает, какую работу мы прошли до текущего решения, но не
заменяет проверку кода. Для запуска используйте [README](../README.md) и
[quickstart](REVIEWER_QUICKSTART.md), для метода — [METHODOLOGY.md](METHODOLOGY.md),
для состава данных — [DATASETS_AND_ASSUMPTIONS.md](DATASETS_AND_ASSUMPTIONS.md).

Текущий исполняемый runtime-путь:

```text
PointCloud2 / XYZ
  -> observed rail pairs
  -> tangent train envelope
  -> raw CORE components
  -> baseline_v3 geometry-first / boundary / temporal assist
  -> JSON diagnostics
```

Слабая score-ветка перенесена внутрь `baseline_v3`; финальным сдачным решением
является весь `baseline_v3 runtime pipeline`.
`UNKNOWN` и неподтверждённый слабый случай не превращаются в `CLEAR`.

## Что сделано

| Направление | Текущий статус | Граница доказательства |
|---|---|---|
| Docker/ROS2 среда | Реализована сборка на `ros:humble-ros-base-jammy` | Проверяет воспроизводимость контейнера, но не production real-time |
| PointCloud2 input | Реализовано чтение фактической схемы сообщений | Новые bag требуют проверки topic/frame и схемы |
| Direct player | Реализован HTTP-плеер через постоянный C++ процесс | Средство просмотра и демонстрации, не обязательный интерфейс автопроверки |
| Headless ROS2 path | Реализован `curve_envelope_node` для `ros2 bag play` | Основной сдачный путь без браузера |
| Рельсы и габарит | Реализована локальная цепочка наблюдаемых пар + tangent extension | Геометрия имеет статус engineering assumption без внешней калибровки |
| `baseline_v3` | Интегрирован в direct player и ROS2 node | Development-качество не равно независимой сертификации |
| Synthetic/fake-object dataset | Поддержан в подготовке данных и плеере | Демонстрационная проверка, не замена скрытого теста жюри |
| Repo gate | `scripts/check_submission_package.py` проверяет публичный состав | Gate не доказывает качество детекции |

## Подтверждённые проверки сдачного среза

| Проверка | Результат / смысл |
|---|---|
| Docker build | Образ `lidar-metro-obstacle-detection:submission` собирается |
| Public scripts surface | В Docker context входят только сдачные scripts, `scripts/research/` исключён |
| Public src surface | В сдачной поверхности оставлены C++ ядро, ROS2 node и reader/player helpers |
| Direct player | Локальный запуск читает подготовленные источники и возвращает JSON |
| ROS2 wrapper smoke | Headless wrapper запускает detector container и получает JSON через ROS2 topic |
| Package gate | Проверяет README, SOLUTION, docs, scripts, src, `.gitignore` и отсутствие данных в Git |

Детали проверок: [SUBMISSION_READINESS_REPORT.md](reports/submission/SUBMISSION_READINESS_REPORT.md)
и [ROS2_HEADLESS_DEMO_VERIFICATION.md](reports/submission/ROS2_HEADLESS_DEMO_VERIFICATION.md).

## Что остаётся ограничением

- Независимый положительный test set отсутствует: основной реальный positive
  interval связан с `doubleT_obstacle`.
- `cloud_with_fake_obj` полезен для демонстрации и проверки сценариев, но не
  является заменой скрытого набора организатора.
- Нет внешней калибровки монтажа, `/tf`, IMU, одометрии, карты и физически
  подтверждённого профиля поезда.
- 80 м в tangent-конфигурации — параметр построения рабочей геометрии, не
  измеренная дальность обнаружения.
- Расстояние в JSON считается от начала координат исходного облака, не от носа
  поезда.
- Full real-time throughput, drops, p95/p99 latency и ресурсы на стенде
  организатора требуют отдельного замера.
- CUDA, deskew, tracking, TTC и управление поездом не входят в сдачный MVP.

## Что должен уметь сделать проверяющий

1. Собрать Docker image.
2. Подготовить локальные архивы через `scripts/prepare_hackathon_datasets.py`.
3. Запустить direct player и посмотреть подготовленные источники.
4. Запустить headless ROS2 demo через `scripts/run_submission_ros2_demo.ps1`.
5. Подставить свой распакованный ROS2 bag, topic и `source_frame`.
6. Запустить `scripts/check_submission_package.py`, чтобы проверить состав
   сдачного репозитория.

Эти действия описаны в [README](../README.md), [SOLUTION](../SOLUTION.md),
[REVIEWER_QUICKSTART](REVIEWER_QUICKSTART.md) и [SUBMISSION_CHECKLIST](SUBMISSION_CHECKLIST.md).

## Защищённые контракты

- `UNKNOWN/DEGRADED` не трактуется как `CLEAR`.
- Имя topic не заменяет `header.frame_id` и калибровку.
- Source distance не называется расстоянием от носа поезда.
- Synthetic tangent не объявляется наблюдаемой рельсовой опорой.
- Runtime-параметры `development_candidate`, `rail_forward_min_m=2`,
  `tangent`, `baseline_v3` должны совпадать в direct и ROS2 маршрутах.
- Документы описывают хакатонный prototype/MVP, не production-certified систему.
