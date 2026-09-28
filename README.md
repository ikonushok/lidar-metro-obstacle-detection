<p align="center">
  <img src="./assets/readme/hero.png" width="100%" alt="Обнаружение препятствий по данным 3D-лидара в тоннеле метро">
</p>

# lidar-metro-obstacle-detection

Демонстрационный прототип обнаружения препятствий в тоннеле метро по облакам 3D-лидара.

[![Architecture: interactive diagram](https://img.shields.io/badge/architecture-interactive%20diagram-0891b2)](https://ikonushok.github.io/lidar-metro-obstacle-detection/diagrams/runtime-architecture.html)

[**Открыть интерактивную схему архитектуры →**](https://ikonushok.github.io/lidar-metro-obstacle-detection/diagrams/runtime-architecture.html) Масштабирование, темы и просмотр связей между компонентами. Схема показывает оба способа запуска и общую C++ реализацию.

Текущий алгоритм — `baseline_v3`: C++ ядро с браузерным плеером для записей и отдельным ROS2-входом для `PointCloud2`.

Конвейер обработки:

```text
облако точек → проверка входа → поиск рельсов → габарит движения
             → geometry-first / boundary / temporal model-assist
             → кандидат препятствия, расстояние и diagnostics
```

## Проверка на данных проверяющего

Основной путь для новых данных: `ros2 bag play → PointCloud2 → curve_envelope_node → JSON`. Проверяющий предоставляет **папку с записью лидара**: внутри должны быть `metadata.yaml` и файлы `.db3`. В ROS2 такая запись называется bag. Узнайте PointCloud2-топик через `ros2 bag info`, а `source_frame` — из `header.frame_id` сообщения. Имя топика не определяет frame.

На Windows с Docker Desktop запустите детектор из корня проекта, указав путь к папке с записью и параметры облака точек:

```powershell
.\scripts\run_submission_ros2_demo.ps1 `
  -RecordingPath 'D:\data\lidar_run_01' `
  -InputTopic '/your/pointcloud' `
  -SourceFrame 'your_lidar_frame' `
  -BuildImage -StopExisting
```

Скрипт печатает команды для просмотра JSON и воспроизведения записи. Выходной топик — `/stage_3/curve_envelope_candidate`; в JSON проверяйте `intrusion_candidate_present`, ближайшее расстояние, `status` и `reason`. Подробный сценарий с командами ROS2 и вариант для Ubuntu: [SOLUTION.md](SOLUTION.md#74-запустить-headless-ros2-replay).

Для проверки быстродействия без плеера запустите detector container в компактном
production/perf режиме и затем выполните измеритель:

```powershell
.\scripts\run_submission_ros2_demo.ps1 `
  -StopExisting -Rate 1.0 -ReadAheadQueueSize 20 -DiagnosticsDetail summary

python .\scripts\measure_headless_ros2_cpp_performance.py `
  --rate 1.0 --read-ahead-queue-size 20 --expected-messages 201 `
  --collector-timeout-seconds 210 `
  --output-stem headless_ros2_cpp_performance_rate_1p0_summary_diagnostics
```

Скрипт запускает `ros2 bag play`, собирает выходные JSON, `processing_ms`,
`docker stats` и сохраняет артефакты в `artefacts/current_model_validation/`.

Для проверки дальности первого public detection на доступных positive-окнах
используйте тот же Docker/Humble runtime:

```powershell
docker run --rm --mount "type=bind,source=$PWD,target=/workspace" `
  lidar-metro-obstacle-detection:submission `
  bash -lc "source /opt/ros/humble/setup.bash && source /app/install/setup.bash && python3 /workspace/scripts/measure_detection_distances.py --root /workspace --progress"
```

## Плеер с архивами организаторов

Для просмотра известных записей в браузере нужен работающий Docker с Compose. Положите три архива в `dataset/raw/`: `for_hackathon`, `new_data`, `cloud_with_fake_obj`. Данные не входят в Git и не скачиваются автоматически; допустимые расширения описаны в [инструкции подготовки](docs/REVIEWER_QUICKSTART.md).

```bash
docker compose up --build
```

Команда собирает образ Ubuntu 22.04 / ROS 2 Humble, при необходимости подготавливает архивы и запускает direct C++ плеер с `baseline_v3`. Откройте [http://localhost:8100/](http://localhost:8100/). Для остановки выполните `docker compose down`. Плеер перечисляет известные источники; **для новой записи используйте ROS2-вход выше**.

**Цвета предупреждений в плеере:**

- **«Препятствие/Возможное препятствие на XX м»** — public C++ detection. В режиме `baseline_v3` трёхкадровый ранний кандидат теперь поднимается в `intrusion_candidate_present=true`, поэтому headless JSON, evaluator и плеер используют один и тот же ранний результат.
- Максимальная задетектированная дальность в доступных пользовательских positive-окнах `cloud_with_fake_obj` — `68.069 м` от начала координат исходного LiDAR-frame (`obj01_2x2_center`, кадр `137`). На кадре `142`, показанном в плеере, расстояние равно `65.708 м`.
- Это решение алгоритма, а не гарантия реального препятствия. На `new_data`, где по сообщению пользователя препятствий нет, 47 красных кадров считаются ложноположительными; плеер помечает их как «Ложная тревога».

Под ползунком кадров жёлтые полосы показывают предоставленные пользователем интервалы видимости объектов. Оранжевые и красные метки появляются только после просмотра соответствующих кадров в плеере. Кнопки `01`–`10` служат для перехода к объектам; отсутствие оранжевой или красной метки на непросмотренном кадре ничего не говорит о результате детектора.

## Результат и границы

- Выход: кандидат препятствия, ближайшее расстояние от начала координат исходного облака, статус и diagnostics.
- `UNKNOWN` и отсутствие кандидата **не означают свободный путь**. Решение не выдаёт разрешение движения.
- Headless ROS2/C++ замер без плеера на `doubleT_obstacle` в `diagnostics_detail=summary`: `processing_ms` p95 `71.78` ms, max `74.96` ms. Это укладывается в вычислительный бюджет порядка `100` ms для `10 Hz`, но локальный Windows/Docker replay всё ещё дал `187/201` JSON и `Message queue starved`; полный end-to-end real-time на целевом Ubuntu-стенде не заявлен.
- Монтаж лидара, физический габарит и качество на независимых положительных проездах не подтверждены. `80 м` — граница поиска, а не измеренная дальность обнаружения.
- Это хакатонный прототип, не сертифицированная система управления поездом. [Текущие проверки и пробелы](docs/reports/submission/SUBMISSION_READINESS_REPORT.md) приведены отдельно.

## Документация

**Запуск и решение**

- [SOLUTION.md](SOLUTION.md) — устройство решения, алгоритм, запуск и ограничения.
- [REVIEWER_QUICKSTART.md](docs/REVIEWER_QUICKSTART.md) — подготовка архивов, плеер, проверка API и ROS2-демо.
- [PLAYER_SETUP.md](docs/PLAYER_SETUP.md) — ручная подготовка файлов плеера для PowerShell launcher.

**Метод, данные и оценка**

- [METHODOLOGY.md](docs/METHODOLOGY.md) — действующий метод, контракты и границы будущих расширений.
- [DATASETS_AND_ASSUMPTIONS.md](docs/DATASETS_AND_ASSUMPTIONS.md) — состав данных, проверенные наблюдения и допущения.
- [TRAIN_ENVELOPE_AND_LIMITATIONS.md](docs/TRAIN_ENVELOPE_AND_LIMITATIONS.md) — габарит поезда и необходимые калибровки.
- [LIDAR_SPEC.md](docs/LIDAR_SPEC.md) — характеристики лидара и ограничения входных данных.
- [EVALUATION_METRICS.md](docs/EVALUATION_METRICS.md) — расчёт метрик `baseline_v3` и границы оценки.

**Сдача и результаты проверок**

- [SUBMISSION_CHECKLIST.md](docs/SUBMISSION_CHECKLIST.md) — состав передачи и проверки перед сдачей.
- [DEVELOPMENT_HISTORY_AND_STATUS.md](docs/DEVELOPMENT_HISTORY_AND_STATUS.md) — выполненные этапы, текущий статус и оставшиеся задачи.
- [SUBMISSION_READINESS_REPORT.md](docs/reports/submission/SUBMISSION_READINESS_REPORT.md) — подтверждённые результаты и пробелы к критериям сдачи.
- [ROS2_HEADLESS_DEMO_VERIFICATION.md](docs/reports/submission/ROS2_HEADLESS_DEMO_VERIFICATION.md) — журнал проверки ROS2-демо без браузера.
- [HEADLESS_ROS2_CPP_PERFORMANCE.md](docs/reports/submission/HEADLESS_ROS2_CPP_PERFORMANCE.md) — замер быстродействия ROS2 → C++ detector без плеера.
- [DETECTION_DISTANCE_REPORT.md](docs/reports/submission/DETECTION_DISTANCE_REPORT.md) — замер first public detection distance на доступных positive-окнах.
- [Техническое задание](docs/hackathon_documentations/5.%20ДепТранспорта.pdf) — требования заказчика к решению и среде запуска.
- [Инструкция по сдаче](docs/hackathon_documentations/instruction.md) — правила передачи материалов и стоп-кода.

[Иллюстрации для презентации](docs/presentation/picts/) хранятся отдельно от инструкций и отчётов.

Лицензия: [MIT](LICENSE).

## Аппаратные рекомендации для следующей итерации

Текущий MVP работает с одним `PointCloud2`-потоком и не доказывает оптимальность
монтажа лидара. Для повышения плотности наблюдений в зоне габарита стоит
отдельно проверить две аппаратные гипотезы:

- два 3D-лидара, размещённые слева и справа от оси состава, а не один датчик по
  центру;
- лидар или режим лидара с более плотным облаком точек, особенно для дальних и
  низких препятствий.

Обе гипотезы требуют отдельной калибровки `base_link <- lidar`, синхронизации
времени, проверки перекрытия safety envelope и повторного измерения recall,
FP/мин, дальности устойчивой детекции и задержки. Без этих проверок замена или
добавление датчиков считается направлением развития, а не подтверждённым
улучшением качества.
