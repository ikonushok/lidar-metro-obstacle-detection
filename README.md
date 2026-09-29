<p align="center">
  <img src="./assets/readme/hero.png" width="100%" alt="Обнаружение препятствий по данным 3D-лидара в тоннеле метро">
</p>

# lidar-metro-obstacle-detection

Обнаружение препятствий в тоннеле метро по облакам 3D-лидара: кандидат препятствия, расстояние и статус обработки. Алгоритм `baseline_v3` работает в C++ плеере и через ROS 2.

Видео обнаружения препятствий и работы плеера доступны [в папке на Google Drive](https://drive.google.com/drive/folders/1faIDjvqWk145uFcsPRrAioY53D9uxXmo?usp=sharing).

![baseline_v3: геометрическая обработка и ансамбль из 17 деревьев решений](docs/presentation/picts/baseline_v3_geometry_forest_infographic.png)

## Плеер с архивами организаторов

Нужны Docker с Compose (на Windows — Docker Desktop в режиме Linux containers), интернет для первой сборки и свободный порт `8100`. Ubuntu 22.04 и ROS 2 Humble входят в образ. Все команды выполняйте из корня проекта.

1. Положите архивы организаторов `for_hackathon`, `new_data`, `cloud_with_fake_obj` в `dataset/raw/`. Допустимы расширения `.tar`, `.zst`, `.tar.zst`. Данные предоставляются отдельно.
2. Соберите и запустите плеер:

```bash
docker compose up --build
```

3. Откройте [localhost:8100](http://localhost:8100/), выберите запись `cloud_with_fake_obj` и запустите воспроизведение. Проверьте, что облако отображается, кадры меняются, а при обнаружении появляются предупреждение и расстояние.

Остановка из второго терминала:

```bash
docker compose down
```

Плеер использует direct C++ обработку. Подробная проверка API и подготовка данных — в [инструкции запуска](docs/REVIEWER_QUICKSTART.md).

## Проверка через ROS 2 на своей записи

Для Windows / PowerShell укажите папку bag с `metadata.yaml` и `.db3`, PointCloud2-топик и фактический `header.frame_id`:

```powershell
.\scripts\run_submission_ros2_demo.ps1 `
  -RecordingPath 'D:\data\lidar_run_01' `
  -InputTopic '/your/pointcloud' `
  -SourceFrame 'your_lidar_frame' `
  -BuildImage -StopExisting
```

Замените значения примера своими. `SourceFrame` проверяет frame, а не преобразует координаты. Скрипт запускает детектор и печатает команды просмотра JSON и воспроизведения bag: выполните их в отдельных терминалах.

В топике `/stage_3/curve_envelope_candidate` должны появляться JSON с `intrusion_candidate_present`, расстоянием, `status` и `reason`. После проверки:

```bash
docker stop lidar-detector
```

[Команды для Ubuntu и описание ROS2-входа](SOLUTION.md#74-запустить-headless-ros2-replay) · [Проверка полноты обработки, быстродействия и дальности](docs/REVIEWER_QUICKSTART.md#9-измерение-быстродействия-и-дальности).

`UNKNOWN` и отсутствие кандидата не означают свободный путь. Это хакатонный прототип; качество на независимых проездах и физический габарит требуют проверки. [Ограничения](docs/TRAIN_ENVELOPE_AND_LIMITATIONS.md).

## Документация

<details>
<summary>Инструкции, метод и результаты проверок</summary>

**Запуск и решение**

- [Схема архитектуры](docs/diagrams/runtime-architecture.html) — интерактивная схема компонентов.

- [SOLUTION.md](SOLUTION.md) — устройство решения, алгоритм, запуск и ограничения.
- [REVIEWER_QUICKSTART.md](docs/REVIEWER_QUICKSTART.md) — подготовка архивов, плеер, проверка API и ROS2-демо.
- [PLAYER_SETUP.md](docs/PLAYER_SETUP.md) — ручная подготовка файлов плеера для PowerShell launcher.

**Метод, данные и оценка**

- [METHODOLOGY.md](docs/METHODOLOGY.md) — действующий метод, контракты и границы будущих расширений.
- [DATASETS_AND_ASSUMPTIONS.md](docs/DATASETS_AND_ASSUMPTIONS.md) — состав данных, проверенные наблюдения и допущения.
- [TRAIN_ENVELOPE_AND_LIMITATIONS.md](docs/TRAIN_ENVELOPE_AND_LIMITATIONS.md) — габарит поезда и необходимые калибровки.
- [LIDAR_SPEC.md](docs/LIDAR_SPEC.md) — характеристики лидара и ограничения входных данных.
- [EVALUATION_METRICS.md](docs/EVALUATION_METRICS.md) — расчёт метрик `baseline_v3` и границы оценки.
- [GENERALIZATION_ASSESSMENT.md](docs/GENERALIZATION_ASSESSMENT.md) — оценка переносимости на новый датасет, признаки переобучения и прогноз для скрытого теста.

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

</details>

Лицензия: [MIT](LICENSE).
