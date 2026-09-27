# Модельная assist-ветка и метрики

Короткий статус для сдачи: финальное решение - не отдельная ML-модель, а
`baseline_v3 runtime pipeline`. Модельная часть используется только как
assist-ветка для слабых или неоднозначных CORE-компонент. Если temporal
confirmation не подтверждает такую ветку, результат остаётся `UNKNOWN`, а не
`CLEAR`.

Исполняемый pipeline подробно описан в
[README_noise_classifier_v3.md](README_noise_classifier_v3.md).

## Что сдаётся

```text
baseline_v3 =
  geometry-first gate по габариту поезда
  + boundary/warning для объектов вне или выше габарита
  + temporal model-assist для слабых/маленьких случаев
```

Внутри текущей assist-ветки используется переносимый C++ score
`candidate_baseline_v2 / random_forest_lite`:

- 17 shallow decision trees;
- threshold `0.8064516129`;
- runtime-артефакт: `models/noise_classifier_candidate_baseline_v2.json`;
- C++ export без внешней ML-библиотеки.

`candidate_baseline_v2` не является финальной моделью сдачи. Это внутренний
score и legacy/comparison режим для assist-части `baseline_v3`.

## Главные метрики текущего решения

Единая offline-сводка `baseline_v3` по 8 источникам:

| Проверка | TP | FN | FP | TN | UNKNOWN |
|---|---:|---:|---:|---:|---:|
| `baseline_v3`, 8-source development/offline | 58 | 0 | 149 | 13519 | 41 |

Смысл строки:

- `doubleT_obstacle`: известная помеха сохранена, `52` TP-кадра, `0` FN;
- `cloud_with_fake_obj`: `6` оцениваемых positive events, `0` FN, `0` FP на
  внешних/верхних boundary-событиях #7/#8;
- старые отрицательные источники: суммарно `149` FP и `41` UNKNOWN;
- `UNKNOWN` не считается `CLEAR` и не смешивается с FP.

Эта строка является development/offline evidence. Она не заменяет полный
runtime replay на целевой среде Ubuntu 22.04 + ROS 2 Humble + Docker.

## Сравнение проверенных assist-моделей

Сравнение ниже относится только к assist/legacy-модели на сохранённом
seven-source development-прогоне, а не ко всему `baseline_v3`.

| Модель | Threshold | TP | TN | FP | FN | Комментарий |
|---|---:|---:|---:|---:|---:|---|
| `candidate_baseline_v2 / random_forest_lite` | 0.806452 | 52 | 13514 | 193 | 0 | выбран для C++ assist-ветки |
| `random_forest` | 0.709677 | 52 | 13514 | 193 | 0 | не выбран: тяжелее переносить |
| `lightgbm` | 0.967742 | 52 | 13514 | 193 | 0 | не выбран: тяжелее переносить |
| `ensemble_v1` | 0.870968 | 52 | 13514 | 193 | 0 | не выбран: сложнее runtime |
| `gradient_boosting` | 0.967742 | 52 | 13353 | 354 | 0 | хуже по FP |

Причина выбора `candidate_baseline_v2`: сохраняет `FN=0` на известном
положительном проезде, входит в группу лучших по temporal FP и уже встроен в
проверяемый C++ runtime без тяжёлых ML-зависимостей.

## Собственный synthetic/evaluation набор

Собственный synthetic-набор используется как development/screening evidence, а
не как независимая контрольная выборка.

| Кандидат | TP | FN | FP всего | TN | UNKNOWN/FP в UNKNOWN | Статус |
|---|---:|---:|---:|---:|---:|---|
| `baseline_v3` | 52 | 0 | 93 | 7614 | 23 | прогнан; training/screening |
| `candidate_baseline_v2` | 51 | 1 | 23 | 7684 | 23 | сравнение assist-score |

Вывод: synthetic-набор помог проверить и отобрать решение, но не является
доказательством качества на скрытых реальных данных жюри.

## Производительность

Исторический lean C++ benchmark assist-ветки на первых 5 минутах `new_data`
давал p95 около `51.4` мс/кадр для stream compute. Этот замер не включает
ROS2 delivery, HTTP/UI, чтение архива, очередь и drops.

Для финального утверждения о real-time нужны full-path replay, latency,
throughput, drops и ресурсы на целевом стенде.

## Что не заявляем

- Не заявляем production/safety ready.
- Не заявляем подтверждённый `CLEAR`.
- Не заявляем независимый recall: положительных реальных проездов мало, часть
  evidence участвовала в разработке.
- Не заменяем скрытую проверку организаторов локальными synthetic-данными.

