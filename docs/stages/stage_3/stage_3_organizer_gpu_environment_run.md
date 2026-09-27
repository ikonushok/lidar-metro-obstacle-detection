# GPU/CUDA-окружение организаторов — разбор ответа

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-22. Этап 3. Цель и границы: [task spec](stage_3_organizer_gpu_environment.md).

## Факты из ответа организаторов

- `NVIDIA-SMI 580.173.02`, загруженный NVIDIA driver `580.173.02`; строка `CUDA Version: 13.0`.
- В списке пакетов присутствуют `cuda-nvcc-12-9 12.9.86-1`, `cuda-toolkit-12-9-config-common 12.9.79-1`, `cuda-toolkit-12-config-common 12.9.79-1`, `cuda-toolkit-config-common 12.9.79-1` и `cuda-drivers-575 575.57.08-0ubuntu1`.

`CUDA Version: 13.0` в выводе NVIDIA-SMI — максимальная версия CUDA, поддерживаемая загруженным драйвером, а не доказательство установки CUDA Toolkit 13.0. Для компиляции на хосте прямо показан `nvcc` 12.9. Пакет `cuda-drivers-575` не отменяет факт загруженного драйвера 580.173.02: по одному списку пакетов нельзя установить, почему присутствует более старый metapackage или какие именно пакеты активны.

## Полезность для текущего решения

Ответ снимает главный риск несовместимости текущего `Dockerfile.cuda`: его базовый образ `nvidia/cuda:12.4.1-devel-ubuntu22.04` использует CUDA 12.4, то есть более ранний CUDA 12.x toolchain, чем явно показанный на стенде 12.9. Он не требует менять базовый образ или `CUDA_ARCHITECTURES "89-virtual"` только из-за этого ответа. RTX 4070 Ti SUPER относится к целевому Ada SM 89, который уже задан в CMake.

Это не является успешной проверкой образа на стенде: NVIDIA-SMI и пакеты не доказывают сборку `Dockerfile.cuda`, загрузку PTX, ROS2 replay, p95 полного pipeline или производительность RTX 4070 Ti SUPER. Текущая политика сохраняется: `cpu` — default, CUDA включается явно; в `auto` недоступная CUDA откатывается на CPU, а явный `cuda` возвращает `UNKNOWN`.

## Что ответ не подтвердил

- наличие и настройку NVIDIA Container Toolkit;
- возможность `docker run --gpus all ...` на проверочном стенде;
- разрешение/ограничения на образы `nvidia/cuda` и конкретные теги;
- обязательность работоспособности без GPU либо допустимость GPU-only зависимости.

Следовательно, нельзя обещать GPU-контейнер без ручной настройки стенда и нельзя делать CUDA обязательной зависимостью. Обычный CPU `Dockerfile` остаётся необходимым воспроизводимым путём; CUDA-образ — дополнительный путь до прямого подтверждения организаторов.

## Evidence inspected

- переданный пользователем текст ответа организаторов;
- `Dockerfile.cuda` — `nvidia/cuda:12.4.1-devel-ubuntu22.04`, CUDA build с `LIDAR_ENABLE_CUDA=ON`;
- `Dockerfile` — CPU-сборка без NVIDIA;
- `src/lidar_mosmetro3d_cpp/CMakeLists.txt` — `CUDA_ARCHITECTURES "89-virtual"`;
- [предыдущий CUDA-отчёт](stage_3_cuda_envelope_run.md) — локальный L1, не стенд организаторов.

## Commands run

- `rg` по Docker/CUDA/CMake-документам и коду — найдены текущие CUDA base image, опциональный backend и SM 89 target.
- `Get-Content` перечисленных документов — подтверждены фактические формулировки и ссылки.

На стенде организаторов команды не выполнялись.

## Validation

**L0, PASS_WITH_RISKS.** Статически согласованы документированные факты, текущий образ и границы выводов. Нет runtime evidence NVIDIA Container Toolkit, Docker GPU, ROS2 или производительности на стенде.

## Остаточный риск и следующий минимальный тест

Остаётся риск, что GPU runtime Docker не настроен или политика стенда запрещает/ограничивает `nvidia/cuda`. Следующий минимальный тест на стенде организаторов:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-devel-ubuntu22.04 nvidia-smi
```

После успешного smoke-test отдельно собрать `Dockerfile.cuda` и выполнить один одинаковый ROS2 replay с `compute_backend=cpu` и `compute_backend=cuda`, сохранив p95, очередь, dropped frames, CPU/GPU/RAM и совпадение выходов.
