# CUDA backend для CurveRailAxis envelope — результат

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Этап 3. Цель и границы: [task spec](stage_3_cuda_envelope.md).

## Что изменено

- Добавлен необязательный CUDA backend: `src/cpp/cuda_envelope.*`. CPU строит те же rail-pair segments, CUDA размечает независимые точки, CPU считает counters и ближайшие исходные точки.
- Midpoint рельсов перед вычислением сегментов округляется так же, как в CPU reference. Не изменены CurveRailAxis, профиль, margins, пороги, TF, deskew, map, tracking и зоны `CORE`/`MARGIN`/`OUTSIDE_REFERENCE`/`UNKNOWN`.
- ROS2 node получил параметр `compute_backend`: `cpu` (default), `auto`, `cuda`. В `auto` отказ CUDA даёт именованный CPU fallback; при явно запрошенном `cuda` без доступного backend публикуется `UNKNOWN`, без `CLEAR`. До выбора backend отсутствие пары рельсов остаётся `UNKNOWN`.
- `Dockerfile.cuda` собирает Ubuntu 22.04 + ROS 2 Humble образ с `LIDAR_ENABLE_CUDA=ON`. Обычный `Dockerfile` собирает CPU-заглушку без CUDA и не требует NVIDIA.

## Evidence и измерения

1. CUDA synthetic parity test прошёл на локальной GPU.
2. Из read-only архива `dataset/for_hackathon/new_data` повторно извлечены только development frames 1050, 1100, 1150. Проверены: `source_mutations=0`, `hesai_lidar`, float32 XYZ; это не test split и не разметка препятствий.
3. CUDA labels побайтно совпали с C++ CPU labels на всех точках трёх кадров. Совпали counts и source index ближайших `CORE`/`MARGIN` точек.
4. [Benchmark](../../../artefacts/stage_3/cuda_envelope/benchmark.json): CUDA envelope с передачей XYZ/labels и выделениями памяти — 1.91–2.23 мс mean, p95 2.31–2.79 мс. Полный kernel CPU AutoRails + CUDA envelope — 9.25–10.58 мс mean, p95 10.19–12.06 мс.
5. `Dockerfile.cuda` собран как `lidar-mosmetro3d:cuda-curve-envelope`; установленный `curve_envelope_node` связан с `libcudart.so.12` и видит локальную NVIDIA GeForce RTX 5080, driver 576.88.

CUDA ускоряет только проверку точек; AutoRails пока CPU и занимает существенную часть времени. На этих кадрах CUDA не доказала заметного выигрыша полного пути над прежним CPU kernel (9.43–10.40 мс mean на трёх сопоставимых supported кадрах). Поэтому backend остаётся опциональным, а не основанием заявлять ускорение всего конвейера.

## Выполненные команды

- `docker build -t lidar-mosmetro3d:cuda-cpu-fallback -f Dockerfile .` — PASS.
- `docker run --rm --gpus all nvidia/cuda:12.4.1-devel-ubuntu22.04 ... test_cuda_envelope` — PASS.
- `docker run --rm ... experiment_new_data_baseline.py --indices 1050 1100 1150 --export-xyz` — PASS, read-only вход.
- `docker run --rm --gpus all nvidia/cuda:12.4.1-devel-ubuntu22.04 ... cuda_envelope_cli ... && cmp ...` — PASS, exact labels на 3/3 кадрах.
- `docker run --rm --gpus all nvidia/cuda:12.4.1-devel-ubuntu22.04 ... cuda_pipeline_cli ...` — PASS, 30 repetitions/frame.
- `docker build -t lidar-mosmetro3d:cuda-curve-envelope -f Dockerfile.cuda .` — PASS.
- `docker run --rm --gpus all lidar-mosmetro3d:cuda-curve-envelope ... ldd ... && nvidia-smi` — PASS.

## Safety-review

Sequential safety-review текущим агентом после реализации, не независимый. **PASS_WITH_RISKS для candidate-only ASSUMED режима.**

- Паритет labels на real saved frames подтверждает, что CUDA не сдвинула границы зон или nearest point относительно CPU reference.
- Потеря опоры проверяется до CUDA; explicit CUDA unavailable ветка публикует `UNKNOWN` с `CURVE_AXIS_SUPPORTED`, не подменяя исправную геометрию отсутствующей осью. CPU fallback в `auto` указан в output.
- Низкие точки не отбрасываются. Нет output `CLEAR`, semantic obstacle claim или управляющего действия.
- Непроверены реальные габарит/калибровка/frame, physical obstacle, полный поворот, CUDA unavailable branch во время ROS runtime и формирование PointCloud2 в node. GPU не делает геометрию валидированной.

## Validation

**L1**: CUDA core, exact parity на трёх реальных development frames, GPU container build/link/smoke и kernel timing. **L0**: ROS2 node с live PointCloud2/bag, organiser RTX 4070 Ti SUPER, p95 полного pipeline, queue/drops/CPU/GPU utilization, video и TP/FP/FN.

Следующий минимальный тест: один Docker ROS2 replay/collector с корректно подготовленным bag storage, `compute_backend=cpu` и `compute_backend=cuda` на одном интервале; зафиксировать p95 end-to-end, очередь, dropped frames и совпадение output JSON.
