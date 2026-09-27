# baseline_v3 runtime pipeline

Этот документ описывает только актуальный сдачный runtime. Старые таблицы
подбора моделей и offline-experiment сводки намеренно не публикуются в
проверочном пакете: для жюри важны воспроизводимый запуск, текущие метрики и
честные ограничения.

## Логика

`baseline_v3` работает как составная decision policy:

1. Проверить входной `PointCloud2` и построить наблюдаемую ось рельсов.
2. Протянуть tangent-граф габарита поезда по этой оси.
3. Сгруппировать точки внутри CORE-зоны.
4. Сильные геометрические intrusion-компоненты поднять как obstacle.
5. Внешние/верхние компоненты оставить как boundary/warning, не obstacle.
6. Слабые или маленькие случаи проверить temporal model-assist.
7. Неподтверждённые случаи оставить `UNKNOWN`, не `CLEAR`.

Внутри assist-ветки используется `candidate_baseline_v2` score, но финальной
моделью решения является весь `baseline_v3 runtime pipeline`.

## Runtime evidence

Актуальная сдачная сводка находится в
[`README_noise_classifier.md`](README_noise_classifier.md):

| Проверка | Результат |
|---|---:|
| Real sources runtime | `TP=51`, `FN=1`, `FP alarm=50`, `frames=13759`, `UNKNOWN=13658` |
| `cloud_with_fake_obj` event windows | `6/6` positive events hit, `0` false-positive boundary events |
| Direct player timing | processing p95 `52.25` ms; HTTP wall p95 `133.16` ms; HTTP wall p99 `1932.03` ms |
| ROS2 parity/timing | `PASS`, `201` cases, wall `137.557` s |

## Границы claims

- `80 м` - предел tangent-продолжения габарита, а не подтверждённая дальность
  обнаружения.
- Расстояние считается от начала координат исходного облака, не от носа поезда.
- `UNKNOWN` и отсутствие reportable-кандидата не означают свободный путь.
- ROS2 parity подтверждает интеграцию, но не полный real-time throughput.
- Нужны независимые положительные реальные проезды для строгой оценки recall.
