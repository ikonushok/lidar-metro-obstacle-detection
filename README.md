<p align="center">
  <img src="./assets/readme/hero.png" width="100%" alt="Обнаружение препятствий по данным 3D-лидара в тоннеле метро">
</p>

# lidar-metro-obstacle-detection

Экспериментальный модуль обнаружения препятствий в габарите движения поезда метро по облакам 3D-лидара. Текущий алгоритм — `baseline_v3`: C++ ядро с браузерным плеером для записей и отдельным ROS2-входом для `PointCloud2`.

[**Открыть схему архитектуры →**](assets/diagrams/solution_architecture.svg) Схема показывает путь от облака точек до результата; [два способа запуска](assets/diagrams/readme_launch_paths.svg) используют одно ядро.

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

## Плеер с архивами организаторов

Для просмотра известных записей в браузере нужен работающий Docker с Compose. Положите три архива в `dataset/raw/`: `for_hackathon`, `new_data`, `cloud_with_fake_obj`. Данные не входят в Git и не скачиваются автоматически; допустимые расширения описаны в [инструкции подготовки](docs/REVIEWER_QUICKSTART.md).

```bash
docker compose up --build
```

Команда собирает образ Ubuntu 22.04 / ROS 2 Humble, при необходимости подготавливает архивы и запускает direct C++ плеер с `baseline_v3`. Откройте [http://localhost:8100/](http://localhost:8100/). Для остановки выполните `docker compose down`. Плеер перечисляет известные источники; **для новой записи используйте ROS2-вход выше**.

## Результат и границы

- Выход: кандидат препятствия, ближайшее расстояние от начала координат исходного облака, статус и diagnostics.
- `UNKNOWN` и отсутствие кандидата **не означают свободный путь**. Решение не выдаёт разрешение движения.
- Монтаж лидара, физический габарит и качество на независимых положительных проездах не подтверждены. `80 м` — граница поиска, а не измеренная дальность обнаружения.
- Это хакатонный прототип, не сертифицированная система управления поездом. [Текущие проверки и пробелы](docs/reports/submission/SUBMISSION_READINESS_REPORT.md) приведены отдельно.

## Документация

- [SOLUTION.md](SOLUTION.md) — архитектура, алгоритм, результат и ограничения.
- [REVIEWER_QUICKSTART.md](docs/REVIEWER_QUICKSTART.md) — подготовка данных, ручной запуск, API и ROS2 demo.
- [METHODOLOGY.md](docs/METHODOLOGY.md) — метод и контракты `baseline_v3`.
- [SUBMISSION_CHECKLIST.md](docs/SUBMISSION_CHECKLIST.md) — состав и проверки перед сдачей.

Лицензия: [MIT](LICENSE).
