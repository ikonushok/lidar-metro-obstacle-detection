# Code-only audit — lidar_MosMetro3D, gate этапа 3

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Датированный аудит до редакции D0–D3; findings и рекомендации описывают тот срез. Текущие исправления документации указаны в отчёте D0–D3; runtime findings этим не закрыты.
> [Актуальный запуск](../../../../README.md) · [Текущий план](../../../README_work_plan.md) · [Результат D0–D3](../../../stages/stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->


## Summary

- Verdict: `HOLD` для завершённого stage-3 baseline; `PASS_WITH_RISKS` для guarded implementation.
- Readiness stage: technical prototype.
- Validation level / evidence level: L1.
- Validation basis: текущий source tree был выполнен в Humble image 2026-09-18; 12/13 тестов прошли, 1 упал. Код и executable configuration просмотрены статически.
- Audit mode: `code-only`.
- Target project: `lidar_MosMetro3D`.
- Scope: `src/`, `scripts/`, `tests/`, `config/`, Dockerfile, manifests. Документация не является доказательством в этом отчёте.

Код устойчиво разбирает PointCloud2 с учётом offsets, endian, row padding и нечисловых/нулевых XYZ. Есть контейнерная проверка input/replay и stage-2 рендер, который защищён от превращения справочного overlay в safety-решение. Но код не содержит ROS2 узла detector, publisher результата/diagnostics, launch-файла, ROI, envelope-intersection, clustering или оценки ближайшей дистанции.

## Что реализовано

| Область | Evidence | Статус |
|---|---|---|
| Input quality gate | `src/cloud_input.py` | implemented |
| Offline bag audit | `scripts/audit_bag.py` | implemented; явно возвращает `UNKNOWN` |
| ROS2/DDS replay smoke | `scripts/replay_smoke.py` | implemented для входа, не для detector output |
| Контейнер Humble | `Dockerfile` | implemented; образ локально существует |
| Визуальный просмотр stage 2 | `src/stage_2_driver_video.py`, `scripts/render_stage_2_driver_video.py` | implemented, visual-only |
| Геометрический detector | отсутствует | not implemented |
| ROS2 result/diagnostic interfaces и launch | отсутствуют | not implemented |
| Кластеризация/ближайший кандидат | отсутствуют | not implemented |

## Риски и пробелы

| Priority | Area | Evidence | Impact |
|---|---|---|---|
| P0 | Geometry evidence | `config/geometry_contract.yaml`: `ASSUMED_HACKATHON` для `lidar_livox`, `CLEAR`/safety-decision запрещены | Разрешён только маркированный demo-candidate; production baseline не может быть признан готовым |
| P0 | End-to-end output | Нет `create_publisher`, result message, detector node или launch в source tree | ТЗ-цепочка обработки и вывода результата не реализована |
| P1 | Unit-suite | `docker run --rm lidar-mosmetro3d:stage_2 python3 -m unittest discover -s tests -v` завершилась `FAILED` | Текущий regression gate не зелёный |
| P1 | Change control | `git status --short` показывает крупный незакоммиченный рабочий набор, включая Dockerfile, stage 1/2 и docs | Нельзя однозначно связать старые журналы проверки с фиксированной ревизией |

## Mandatory Bug Discovery

- Status: concrete candidate found.
- Candidate count: 1.
- Reproduction status: `REPRODUCED` существующей командой; проект не изменялся.

| # | Candidate | Evidence strength | Trigger | Location | Confidence | Reproduction status |
|---|---|---|---|---|---|---|
| 1 | Тест сравнивает float-координаты ворот строго через `assertEqual` | reproduced | `-1.4 / 10.0` даёт IEEE-значение `-0.139999...`, а ожидается литерал `-0.14` | `tests/test_stage_2_driver_video.py:25` | High | `REPRODUCED` |

## Evidence log

- Files inspected: Dockerfile; `src/cloud_input.py`; `src/stage_2_driver_video.py`; `scripts/audit_bag.py`; `scripts/replay_smoke.py`; `scripts/render_stage_2_driver_video.py`; `tests/test_cloud_input.py`; `tests/test_stage_2_driver_video.py`; `config/geometry_contract.yaml`.
- Commands run:
  - `git -c safe.directory='C:/Users/Ilya/PycharmProjects/lidar_MosMetro3D' status --short`
  - `docker image inspect lidar-mosmetro3d:stage_2 --format '{{.Id}}'`
  - `docker run --rm lidar-mosmetro3d:stage_2 python3 -m unittest discover -s tests -v`
- Outcomes: Docker image id `sha256:070a2540adf49143aebfa83ab53958905e8432a6aa85847dfe223b56057099a2`; test suite failed with one float-equality assertion.
- Residual risk: full bag, detector and ROS result path were not executed because they do not exist in the inspected code.
- Smallest next validation: fix the test assertion under a separate approved change, then rerun the same container suite.
