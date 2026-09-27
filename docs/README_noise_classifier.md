# Runtime metrics and model assist

Короткий статус для сдачи: финальное решение - не отдельная ML-модель, а
`baseline_v3 runtime pipeline`. Модельная часть используется только как
assist-ветка для слабых или неоднозначных CORE-компонент. Если temporal
confirmation не подтверждает такую ветку, результат остаётся `UNKNOWN`, а не
`CLEAR`.

## Что сдаётся

```text
baseline_v3 =
  geometry-first gate по габариту поезда
  + boundary/warning для объектов вне или выше габарита
  + temporal model-assist для слабых/маленьких случаев
```

Внутри assist-ветки используется переносимый C++ score
`candidate_baseline_v2 / random_forest_lite`:

- 17 shallow decision trees;
- threshold `0.8064516129`;
- runtime-артефакт: `models/noise_classifier_candidate_baseline_v2.json`;
- C++ export без внешней ML-библиотеки.

`candidate_baseline_v2` не является финальной моделью сдачи и не доказывает
`CLEAR`; это только внутренний score для части `baseline_v3`.

## Актуальные метрики

Главная сдачная строка для проверяющего - runtime recheck от 2026-09-27 на
Docker image `lidar-metro-obstacle-detection:submission`
(`sha256:9686850054da221452d9fe0ee65ed4932ad78581274fc947865d8bfa9e7e0ec1`).
Артефакты локально сохранены в ignored-каталоге
`artefacts/current_model_validation/`.

| Проверка | Результат | Интерпретация |
|---|---:|---|
| Real sources runtime | `TP=51`, `FN=1`, `FP alarm=50`, `frames=13759`, `UNKNOWN=13658` | `UNKNOWN` не считается `CLEAR`; один FN - первый кадр temporal assist перед подтверждением. |
| `cloud_with_fake_obj` event windows | `6/6` positive events hit, `0` false-positive boundary events | Оцениваемые синтетические препятствия ловятся; внешние/верхние #7/#8 не становятся obstacle. |
| Direct player timing, `new_data` 1050..1150 | processing p95 `52.25` ms; HTTP wall p95 `133.16` ms; HTTP wall p99 `1932.03` ms | C++ compute укладывается в ориентир ~10 Hz, но full HTTP path имеет хвосты из-за архива/API/ожиданий. |
| ROS2 parity/timing, `doubleT_obstacle` | `PASS`, `201` cases, wall `137.557` s | ROS2 path в Docker/Humble совпадает с direct path на development sequence; это integration/parity, не full throughput proof. |

## Производительность

Свежий direct-player замер для `baseline_v3` на окне `new_data` `1050..1150`
даёт compute p95 `52.25` мс/кадр, но HTTP wall p95 `133.16` мс и p99
`1932.03` мс.

Поэтому можно говорить о запасе C++ compute-ядра, но нельзя заявлять
production real-time без отдельного стендового replay с очередями, drops,
полученными/обработанными кадрами и ресурсами на целевой среде.

## Что не заявляем

- Не заявляем production/safety ready.
- Не заявляем подтверждённый `CLEAR`.
- Не заявляем независимый real-world recall: положительных реальных проездов
  мало, а `doubleT_obstacle` является development-positive.
- Не заменяем скрытую проверку организаторов локальными synthetic-данными.
