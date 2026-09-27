# model_v1 temporal viewer FP fix

## Цель

Убрать однокадровые FP в CPU viewer для `model_v1`, не ломая длительную детекцию наподобие `doubleT_obstacle` и не превращая `UNKNOWN` в `CLEAR`.

## Воспроизведение

Добавлен regression test: один backend `model_v1` candidate в текущем кадре при `temporal-required-frames=2` не должен показывать `ПРЕДУПРЕЖДЕНИЕ` и баннер расстояния.

До фикса тест падал: `backendModelSplit()` возвращал `reportable_core_source_indices` напрямую, обходя temporal confirmation.

## Изменение

- `web/stage_4_cpu_player.js`: добавлен post-model temporal слой для `model_v1`.
- `tests/test_cpu_viewer_distance_and_noise.cjs`: добавлены проверки suppress/keep для model candidates.

Модельные reportable indices остаются источником кандидатов; legacy JS thresholds не заменяют `model_v1`. Неподтверждённые model candidates переходят в viewer noise/reportable=false, но raw/model diagnostics остаются видимыми.

## Проверка

- `node --test tests\test_cpu_viewer_distance_and_noise.cjs` — PASS, 13 tests.
- `node --test tests\test_cpu_viewer_distance_and_noise.cjs tests\test_cpu_viewer_envelope_geometry.cjs` — PASS, 16 tests.

## Остаточный риск

Это viewer/post-filter fix. На момент этого прохода ROS2 C++ publish layer оставался покадровым; это ограничение закрыто отдельным этапом [stage_5_ros2_temporal_runtime.md](../../stages/stage_5/stage_5_ros2_temporal_runtime.md), где публичный ROS2 `intrusion_candidate_present` переведён на causal temporal confirmation.
