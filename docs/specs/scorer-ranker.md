# Spec: Scorer/Ranker (M6) — Вариант 2

> Гибрид: det. признаки + LLM Judge + Weighted Ranker. Ссылается на
> `03-component.md` (#11–#13), `04-workflow.md` (стадия Score).

## Роль
Ранжирование гипотез: новизна [R-OUT5], реализуемость [R-F7], эффект [R-OUT7],
риски [R-OUT6]. Веса настраиваются [R-A1]; калибровка по labels [R-A3].

## Конвейер

| Шаг | Тип | Выход | Требование |
|------|-----|-------|------------|
| Feature Extractor | deterministic | новизна (граф-дистанция), реализуемость (constraint-match), эффект (KPI-прогноз) | [R-OUT5..7][R-IN2] |
| LLM Judge | `LLM/Agent` | качественная оценка осей | [R-F7] |
| Weighted Ranker | deterministic | взвешенная сумма; веса [R-A1]; калибровка по labels [R-A3] | [R-A1][R-A3] |

## Ранжирование
- Формула: `score = Σ w_i * f_i`; веса из конфига (экспертный режим) [R-A1].
- Калибровка: корректировка весов по Feedback Labels (M8/M10) [R-A3][ASSUM-7].
- Нормализация; стабильность при re-run (Jaccard@10 ≥ 0.9) [R-N1].

## Failure modes
- FE3: LLM Judge недоступен → det.-only скорер (features + weighted ranker).
- FE4: constraint_check отбраковывает (через constraint-match) [R-IN2].

## Метрики
- weight-coverage (R-A1), rank-stability, label-calibration drift.

## Требования
[R-F7][R-OUT5][R-OUT6][R-OUT7][R-IN2][R-K1][R-A1][R-A3][R-N1][ASSUM-7]
