# CPU result viewer — результат

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Каталог/контракт matching JSON переиспользуется, но прежний ROS transport и timings не описывают direct-плеер.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Этап 4. Цель и границы: [task spec](stage_4_cpu_result_viewer.md).

## Что изменено

- Добавлен `scripts/export_cpu_viewer_replay.py`: он запускает только `compute_backend:=cpu`, по одному посылает saved XYZ в ROS2 node, проверяет frame/timestamp результата и записывает неизменённые XYZ вместе с JSON в статический набор.
- Добавлен `web/stage_4_cpu_viewer.html`. Browser только читает `manifest.json`, `results.json` и XYZ, окрашивает индексы из `core_source_indices`, рисует полученные pairs/bounds и показывает status/nearest distance. В нём нет AutoRails, CurveRailAxis membership или другого детектора.
- Набор replay создан в `artefacts/stage_4/cpu_viewer/`: 1050, 1100, 1150 из development-window `new_data`.

## Evidence и команды

- `docker build -t lidar-mosmetro3d:stage-4-cpu-viewer -f Dockerfile .` — **PASS**, C++ package собран в Humble CPU image.
- `docker run ... python3 /app/scripts/export_cpu_viewer_replay.py /data --output /output --first-index 1050 --last-index 1150` — **PASS**: три кадра, backend `cpu`, статусы всех трёх — `OBSERVED_CORE_INTRUSION_CANDIDATE`.
- HTML JavaScript проверен `node --check`; exporter прошёл `python3 -m py_compile` внутри CPU image.
- Временный `python3 -m http.server` отдал viewer и оба JSON. HTTP-проверка: `frame_count=3`, `result_count=3`, `backend=cpu`, в первом result 585 core indices.
- Отдельная проверка manifest/results: frame identity совпадает во всех трёх парах; `core_source_indices` равны `core_count` (585, 909, 396) и ни один индекс не выходит за границы исходного XYZ. В HTML нет `AutoRails`, `live-envelope`, `classifyLocal` или `createEnvelope`.
- Полный C++ catalog launcher и непрерывный benchmark описаны в отдельном [отчёте](stage_4_cpu_catalog_player_run.md). Этот документ относится только к статическому smoke/demo на трёх сохранённых кадрах.

## Запуск launcher

Команды выполняются из корня проекта в PyCharm Terminal / PowerShell.

```powershell
# Показать статический smoke/demo на трёх подготовленных CPU results.
.\scripts\run_stage_4_cpu_viewer.ps1 -NoBrowser
Start-Process 'http://localhost:8094/'
```

```powershell
Можно не передавать `-NoBrowser`: launcher сам откроет браузер. Параметр `-Port 8095` задаёт другой свободный порт. Полный C++ catalog запускается через `.\scripts\run_stage_2_cpu_player.ps1`, а старый `.\scripts\run_stage_2_player.ps1` относится к прежнему JS-плееру.

## Safety-review

Последовательный safety-review текущим агентом, не независимый: **PASS_WITH_RISKS**.

- Browser не классифицирует точки и не меняет geometry contract: красный цвет определяется только source indices CPU output. Axis/bounds используются для отрисовки полученного результата.
- Identity source frame/header проверяется exporter и viewer перед показом; результат без подходящего кадра не отображается.
- Footer и статус явно сохраняют candidate-only ограничение: `UNKNOWN` не объявляет путь свободным.
- Риск: bounds/frame/units остаются `ASSUMED`; показанные core returns могут включать штатную инфраструктуру. Это демонстрация результата, не safety decision.

## Validation-review

Последовательный validation-review текущим агентом, не независимый: **PASS_WITH_RISKS, L1** для CPU ROS2 → static files → HTTP data chain на трёх saved development frames.

Не проверены вручную WebGL rendering и playback, настоящая запись видео, полный rosbag, прямой/поворот/низкий положительный объект с разметкой, потеря опоры в статическом viewer, длительная нагрузка, queue/drops и p95 end-to-end. Browser automation на данной машине не запустилась из-за ошибки kernel assets; это не результат viewer.

## Следующий минимальный шаг

Открыть `artefacts/stage_4/cpu_viewer/` через локальный HTTP server и вручную подтвердить кадры 1050/1100/1150. Затем добавить в тот же export один `UNKNOWN` frame потери опоры и записать короткое видео playback без изменения алгоритма.
