# Stage 4 — полный C++ catalog `new_data` и диагностические previews

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Каталог/контракт matching JSON переиспользуется, но прежний ROS transport и timings не описывают direct-плеер.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Режим: patch → safety-review → validation. Этап 4, шаг 4 плана.

## Задача

- Goal: воспроизводимо прогнать все 11 271 исходных кадра `new_data` через существующий C++ CPU default `development_candidate`, сохранить покадровый каталог matching JSON и подготовить компактные видео-главы/индекс для диагностики.
- Наблюдаемая проблема: lazy viewer вычисляет результат на запрос, но не оставляет полного fixed catalog; длинный непрерывный ролик не даёт исходных границ частей bag и плохо подходит для выбора аномалий.
- Non-goals: изменение `CurveRailAxis`, AutoRails параметров, профиля/margins, frame/time контрактов, C++ membership, дескью, карты, tracking, классификации, TP/FP/FN или safety decision.
- Source of truth: `docs/README_work_plan.md`, `docs/README_dataset_audit.md`, `config/geometry_new_data_experiment.yaml`, `scripts/serve_stage_2_catalog.py`, `scripts/cpu_catalog_runtime.py` и JSON `curve_envelope_node`.
- Этап: 4 — сигнализация на видео. `new_data` содержит 221 SQLite-часть и 11 271 `PointCloud2` кадр; ранее был проверен только непрерывный фрагмент 1050–1150.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая проверка — Docker image проекта с C++ CPU node.
- Вход/frames: исходный TAR `dataset/for_hackathon/new_data`; `hesai_lidar <- hesai_lidar`; XYΖ без transform, deskew и накопления. Ось/units остаются `ASSUMED`.
- Временная база: `bag_timestamp_ns` и `header_timestamp_ns` сохраняются раздельно; compute/wall время измеряется `time.monotonic()` процесса. Они не вычитаются друг из друга.
- Allowed files: exporter/renderer каталога, узкие тесты, этот отчёт и новые `artefacts/stage_4/cpp_full_catalog_development_candidate/`.
- Files to avoid: C++ geometry/thresholds, YAML profile, ROS2 schemas/QoS, raw archive и существующие artifacts.
- Защищённые контракты: C++ JSON — единственный источник axis/pairs/bounds/core/margin/`UNKNOWN`; `UNKNOWN != CLEAR`; все core returns остаются candidates; каталог проверяет raw hash и header/frame identity до записи/визуализации.
- Deliverables: JSONL.GZ на source-part с header/bag identity, raw XYZ SHA-256, осью, support, reason, indices и times; part videos; contact sheets; window index; completion report.
- Основной агент: текущий агент по `agents/lidar_obstacle_pipeline.md`.
- Safety-review: требуется после реализации, так как отображаются габарит и candidate; отдельный последовательный проход текущего агента.
- Validation-review: после safety-review; не называет визуализацию подтверждением калибровки, coverage или качества detection.
- Validation target: L3 для полного local Docker → ROS2 C++ → catalog → selected matching visualization пути. Не заявлять quality/real-time/replay bag callback behaviour.
- Acceptance criteria: 11 271 сохранённых записей разделены по исходным source-part; у каждой совпадает raw hash и identity с result; previews используют только matching catalog JSON; окна показывают доли support/UNKNOWN и число core returns; нет единого ролика без part boundary.
- Stop conditions: необходимость изменить защищённую геометрию/пороги/контракт, hash/identity mismatch, C++ `UNKNOWN` подменяется отсутствием warning или отсутствует matching JSON.

## Отчёт о завершении

Заполняется по фактически выполненным командам после полного прогона.
