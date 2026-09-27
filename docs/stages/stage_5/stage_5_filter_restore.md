# Восстановление фильтра — 2026-09-22

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Исторический legacy noise/temporal режим. Его JS-настройки не определяют итог backend model_v1 в текущем плеере.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

- Режим: patch, восстановление ранее выбранной конфигурации, без новой калибровки.
- Цель: вернуть состояние из сессии «Определи препятствие или шум» до ужесточения 1.20 → 0.70 м и последующего low-side правила/отката.
- Evidence: журнал сессии 01a0c811-e9fd-79f1-ad8c-74575be4dd29, сохранённый git diff команды call_SiUHMIPB0w5tnsxm9Ny1elgr, исходные UI/test файлы в выводах команд; текущая ветка backup-before-reset, HEAD 62c3fee.
- Параметры: 22 точки, связность 0.25 м, длина по оси ≤1.0 м, среднее расстояние от оси ≤1.20 м; существующее viewer-подтверждение 2 из 3.
- Разрешённые файлы: curve_envelope_core, CUDA adapters, stream CLI, ROS node, соответствующие существовавшие тесты и stage_4_cpu viewer. Посторонние изменения не затрагивать.
- Non-goals: новые методы, изменение габарита, осей, TF, ROS messages, зависимостей, разбиения данных.
- Защищённые контракты: raw CORE и UNKNOWN сохраняются; noise split не является доказательством свободного пути; направление преобразования не меняется.
- Проверка: применимость исторического diff; node viewer tests; Docker C++ core regression/CLI build; по возможности кадры doubleT_obstacle 13–27, 40, 48–64. Цель L1, реальный replay отдельно.
- Основная роль: текущий агент; отдельные последовательные проходы safety_geometry_reviewer и validation_reviewer, без заявления о независимости.
- Ограничения: docs/work_plan.md и docs/methodology.md отсутствуют в текущем checkout. Восстановление не подтверждает оптимальность на независимой выборке. Низкие/вытянутые объекты могут подавляться историческим фильтром.
- Stop condition: неполный исторический diff, несовместимый контракт или неясное происхождение восстанавливаемого кода.

## Результат

- Восстановлен полный исторический diff от 2026-09-22 07:55:37 UTC (до ужесточения), а не подобраны новые значения. Дополнительно восстановлены HTML, axis labels и ранее существовавшие viewer-тесты из полных выводов той же сессии. Обработчики controls согласованы с восстановленными ID.
- `git ... apply --check artefacts/stage_5/filter_restore/historical.patch` — PASS до применения. Исходный patch сохранён как evidence.
- `node --test tests/test_cpu_viewer_distance_and_noise.cjs tests/test_cpu_viewer_envelope_geometry.cjs` — 13/13 PASS.
- `node --check web/stage_4_cpu_player_controls.js` — PASS.
- Docker: `g++ -std=c++17 -Wall -Wextra -Werror -I src/cpp tests/test_curve_envelope_core.cpp src/cpp/curve_envelope_core.cpp -o /tmp/test_filter && /tmp/test_filter` — PASS, исходники смонтированы readonly.
- `docker build -t lidar-mosmetro3d:stage-4-cpu-viewer -f Dockerfile .` — PASS, colcon: 1 package finished. Образ e8432ea9738a79b7d8c11b72282352abbfa5f8db064988971c43e66729c92455.
- `./scripts/run_stage_2_cpu_player.ps1 -Port 8100 -RailForwardMinM 2 -NoBrowser` — запущен; GET `/` и API кадра 22 — HTTP 200. Первый API-запрос пересёкся с воспроизведением пользователя и получил 409 Stale frame; далее проверка перенесена в отдельный Docker-процесс.
- Отдельный `DirectDetailedCpuRuntime(rail_forward_min_m=2.0)` на десяти реальных кадрах 13,14,22,23,40,41,48,49,63,64 — везде reportable >0, в JSON подтверждены параметры 22/0.25/1.0/1.2. Сохранены JSON и XYZF в `artefacts/stage_5/filter_restore/`.
- Существующие production viewer-функции проверены через helper из `tests/test_cpu_viewer_distance_and_noise.cjs` с реальными соседними кадрами и фактическим current index. Кадры 13/22/40/48/64 дают banner на 57.0/47.3/56.4/49.3/55.3 м. Краткий результат: `artefacts/stage_5/filter_restore/validation.json`.
- `git diff --check` — PASS после удаления лишних пустых строк из восстановленных выводов.

## Safety-review и validation (последовательные проходы текущего агента)

- Raw CORE membership, source indices и `system_status=UNKNOWN` сохранены; safety_decision_permitted остаётся false. Ни карта, ни TF, ни геометрия не изменены.
- Исторический viewer подавляет near-zone кандидатов при включённом «Поезд движется» (6 м), а compactness может подавлять реальные низкие/вытянутые объекты. Это известные ограничения восстановленного режима, не одобрение безопасного применения. Для safety acceptance — HOLD; вне этой задачи требуется отдельная проверка близкого/низкого препятствия.
- Validation verdict: PASS для восстановления исторической конфигурации и узких проверок, L1. Нет red-to-green доказательства устранения отдельного алгоритмического дефекта; это восстановление версии. Идентичность кандидата физическому человеку не доказана отдельным object matching.
- Не проверены: полный replay, независимые FP/FN, CUDA runtime и ROS pub/sub smoke (сборка выполнена), скриншоты других тоннелей. Параметры не называются оптимальными для всех данных.
- Следующий минимальный тест: визуально сверить человека в плеере на кадрах 13–27, 40, 48–64; отдельно проверить близкий/низкий объект, прежде чем менять safety-claims.
