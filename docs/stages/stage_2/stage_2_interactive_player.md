# Task spec — интерактивный 3D-плеер Stage 2

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача

- Goal: дать машинисту браузерный инструмент ручного покадрового просмотра полного облака `doubleT_obstacle` из направления рабочей визуальной гипотезы, без детектора или safety-вывода.
- Наблюдаемая проблема или исходный claim: прошлый MP4 не является достоверным средством просмотра: ранее продольной осью ошибочно считали X, а его подготовка прореживала облако. Нужен управляемый просмотр исходных возвратов без такого прореживания.
- Non-goals: классификация типа объекта, `CLEAR`, safety envelope, TF/extrinsics, deskew, накопление/совмещение кадров, карта, tracking, TTC, калибровка или метрики качества. Экспериментальные кластеры — ручная визуальная помощь, не детектор препятствий.
- Source of truth: `docs/hackathon_documentations/5. ДепТранспорта.pdf`; фактический `doubleT_obstacle`; `docs/dataset_audit.md`; `config/geometry_contract.yaml`; `docs/train_clearance.md`.
- Пункт/раздел ТЗ и обязательный результат: ТЗ задаёт целевую среду Ubuntu 22.04 + ROS 2 Humble + Docker; плеер — вспомогательное средство этапа 2, не замена обязательного baseline этапа 3.
- Этап `docs/work_plan.md`: 2 — геометрия и правила проверки.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая среда проверки: только статические проверки Windows workspace, Docker-сборка и полный export намеренно не запускались в этой задаче.
- Входные данные и единицы: `PointCloud2` с XYZ; рабочая визуальная гипотеза единиц — метры, но она `UNCONFIRMED`.
- Конкретный bag/версия/интервал, топик и объём выборки: `dataset/extracted/doubleT_obstacle`, `/sensing/lidar/hesai128/pointcloud`, 201 кадров по проверке этапа 1.
- Факты из `docs/dataset_audit.md`, подтверждения на текущем входе и непроверенные предположения: XYZ float32, 921600 записей в сообщении, из них в исследованном входе много `(0,0,0)` no-return; TF/IMU/одометрии/разметки нет. `forward=-Y`, `lateral=X`, `vertical=Z`, метрические единицы и положение начала габарита не подтверждены.
- Рабочие frames и направление transforms: frame `lidar_livox` только наблюдается; transform отсутствует и не требуется плееру. Визуальная гипотеза не создаёт `T_target <- source`.
- Режим baseline/расширений; необходимые TF/движение/карта/габарит и поведение при их отсутствии: покадровый visual-only режим. При отсутствии подтверждённой геометрии плеер показывает подпись `UNCONFIRMED / manual review only`; любой геометрический результат остаётся `UNKNOWN`.
- Временная база событий и способ измерения вычислительной задержки: отображаются относительное время bag от первого кадра и raw header timestamp отдельно; часы не сопоставляются, latency не вычисляется.
- Allowed files: `src/stage_2_player.py`, `scripts/prepare_stage_2_player.py`, `scripts/run_stage_2_player.ps1`, `scripts/validate_stage_2.ps1`, `web/stage_2_player.html`, Dockerfile, `tests/test_stage_2_driver_video.py`, `docs/stages/stage_2/`.
- Files to avoid: исходный bag/TAR, ROS2-сообщения, TF-контракт, `config/geometry_contract.yaml`, численные пороги detector и safety policy.
- Защищённые контракты: `UNKNOWN` не становится `CLEAR`; header/bag clocks не смешиваются; `visualization_overlay.safety_decision_permitted=false`; zero/no-return, NaN/Inf учитываются отдельно; нет скрытого sampling/cropping/voxelisation.
- Deliverables и статус каждого: exporter локального формата `.xyzf` — реализован; браузерный плеер — реализован; переключаемый visual-only crop только по X/Z с независимыми отступами слева/справа/сверху/снизу 0–10 м — реализован; экспериментальная voxel-clustering внутри visual band — реализована; однокомандный запуск — реализован; runtime/export полного bag — ожидает повторного запуска с обновлённым manifest.
- Путь отчёта этапа или категории: `docs/stages/stage_2/stage_2_interactive_player_result.md`.
- Основной агент: `agents/lidar_obstacle_pipeline.md`.
- Нужен ли `safety_geometry_reviewer` и почему: да, отдельный проход после реализации, поскольку на экране размещается reference overlay в неподтверждённых осях.
- Нужен ли отдельный этап `validation_reviewer`; порядок и кто выполняет проходы: да, после static tests проверить claims и уровень доказательств текущим агентом; это не независимое review.
- Validation target: L1 для статических/unit-проверок; L3 возможен только после Docker export 201 кадров и ручного просмотра браузера.
- Validation method: unit tests, `py_compile`, статическая проверка HTML и затем команда запуска на полном bag.
- Acceptance criteria: управление запуском/паузой/шагом/перемоткой/скоростью; четыре ракурса; кадр, обе временные метки, число точек и ближайший raw-return; видимый reference overlay; полный набор finite non-zero returns в source order без decimation; переключатель crop, оставляющий только X/Z reference band с отдельными пользовательскими отступами слева/справа/сверху/снизу, без продольного отсечения вперёд по −Y; отдельный experimental переключатель, подсвечивающий voxel-компоненты внутри выбранной band; явная ошибка вместо fallback-sampling.
- Stop conditions: не называть `-Y` подтверждённым направлением движения; не выдавать расстояние до препятствия, результат геометрии или решение безопасности; не запускать тяжёлые Docker build/export в этой задаче.
