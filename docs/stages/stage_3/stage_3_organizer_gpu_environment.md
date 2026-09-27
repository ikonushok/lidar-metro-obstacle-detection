# Уточнение GPU-окружения организаторов

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-22. Этап 3 (необязательный CUDA backend).

## Задача

- Goal: зафиксировать ответ организаторов о GPU/CUDA и определить, какие решения он позволяет принять для текущего CUDA-образа.
- Наблюдаемый claim: `Dockerfile.cuda` использует `nvidia/cuda:12.4.1-devel-ubuntu22.04`; CUDA backend остаётся необязательным, а обычный `Dockerfile` не требует NVIDIA.
- Non-goals: менять CUDA-версию, базовый образ, `compute_backend`, CMake-архитектуру, Docker runtime, ROS2-контракты, геометрию, пороги или выполнять запуск на стенде.
- Source of truth: текстовый ответ организаторов, полученный пользователем; текущие `Dockerfile.cuda`, `Dockerfile` и [результат CUDA](stage_3_cuda_envelope_run.md). NVIDIA-SMI и список пакетов не заменяют фактический Docker GPU smoke-test.
- Пункт/раздел ТЗ и обязательный результат: ТЗ §3, Ubuntu 22.04 + ROS 2 Humble + Docker; GPU RTX 4070 Ti SUPER разрешён к использованию. Обязательность GPU-only запуска в приведённом ответе не подтверждена.
- Этап docs/work_plan.md: этап 3; перед включением CUDA по умолчанию нужен замер полного пути на стенде ТЗ.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая среда проверки организаторов частично раскрыта ниже.
- Входные данные, frames, transforms и временная база: не применимо; задача не запускает конвейер и не меняет его контракт.
- Режим: документирование окружения для опционального CUDA расширения. При недоступной CUDA `auto` использует CPU fallback, а явно запрошенный `cuda` даёт `UNKNOWN`, не `CLEAR`.
- Allowed files: этот task spec, [отчёт](stage_3_organizer_gpu_environment_run.md), `docs/README_work_plan.md`, `docs/README_methodology.md`, `README.md`.
- Files to avoid: Dockerfile, исходный код, конфигурации, датасет и артефакты запуска.
- Защищённые контракты: CPU — default; CUDA — optional; `UNKNOWN` не является `CLEAR`; среда организаторов не считается проверенной без выполненной команды на ней.
- Deliverables: трассируемый отчёт с фактами/выводами/открытыми вопросами; ссылки из плана, методологии и README.
- Основной агент: текущий агент по `agents/lidar_obstacle_pipeline.md`.
- `safety_geometry_reviewer`: не нужен — не меняются frame, envelope, пороги, время или safety-логика.
- `validation_reviewer`: отдельный проход текущего агента по `agents/validation_reviewer.md`, только для границ claim и уровня доказательств.
- Validation target: L0.
- Validation method: статически сверить ответ организаторов с текущими Docker/CUDA-контрактами и проверить ссылки/Markdown diff.
- Acceptance criteria: не выдать версию CUDA из `nvidia-smi` за установленный toolkit; не заявить доступность `--gpus all`, разрешение `nvidia/cuda` или GPU-only требование без ответа организаторов.
- Stop conditions: при необходимости сменить образ, CUDA toolchain или режим по умолчанию — создать отдельную задачу с build/run планом.
