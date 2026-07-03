# Spec: Observability & Evals (M12) — Вариант 2

> Трейсы стадий, метрики, evals. Ссылается на `02-container.md` (Container 11),
> `05-dataflow.md` (узел 14).

## Роль
Интерпретируемость [R-N1], контроль производительности [R-N4], оценка качества.
Сбор трейсов стадий, метрик, логов, evals.

## Метрики

| Категория | Метрика | Цель | Требование |
|-----------|---------|------|------------|
| Latency | p50/p95 до набора | ≤2/≤5 мин | [R-N4] |
| Cost | токены/сессия (in/out) | ≤20k/≤6k | [R-N4] |
| Качество | coverage цитат | ≥85% | [R-K2][R-F9] |
| Качество | hallucination-source rate | ≤4% | [R-K2] |
| Воспроизводимость | Jaccard@10 re-run | ≥0.9 | [R-N1] |
| Надёжность | доступность API | ≥99.5% | [R-N4] |
| ETL | batch latency | ≤2 ч/10⁴ док. | [R-F1] |

## Логи / трейсы
- OTel-спаны на каждую стадию и LLM-слот (token usage per slot).
- Redaction: source IDs и метрики, не сырые тексты [R-N5].
- Audit: constraint violations, отбраковки (FE4), label-конфликты [R-IN2][R-A3].

## Evals
- Набор: golden hypotheses + golden citations + golden rankings.
- Чек: schema-validity, citation-existence, constraint-pass, novelty-разнообразие,
  rank-stability.
- Регрессия при смене модели/весов (M11/M6) [R-N1].

## Требования
[R-N1][R-N4][R-N5][R-K2][R-F9][R-F1][R-IN2][R-A3]
