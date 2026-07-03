# Spec: Retriever (M2) — Вариант 2

> Retrieval-first: vector + KG traversal, LLM-реранк. Ссылается на
> `03-component.md` (#5–#8), `05-dataflow.md` (узел 6).

## Роль
По запросу стадии Retrieve вернуть релевантные evidence: чанки + сущности/связи.
Query plan детерминирован; реранк — LLM-слот.

## Источники
- Предbuilt VectorDB (M1) + KG Neo4j (M3) [R-IN3].
- Опционально внешние API [R-K5][R-N5].

## Поиск / reranking

| Шаг | Тип | Выход | Требование |
|------|-----|-------|------------|
| Query Planner | deterministic | план запросов из цели/ограничений | [R-IN1][R-IN2] |
| Vector Search | deterministic | top-k чанков (RU/EN/CN) | [R-F1][R-N2] |
| KG Traversal | deterministic | сущности/связи (Cypher/SPARQL) | [R-F4] |
| LLM Reranker | `LLM/Agent` | ранжированные evidence под цель | [R-F7] |

## Ограничения
- Context budget: evidence truncate/rerank до 16k токенов (Enforcer) [R-N4].
- Timeouts: vector 4s, kg 3s, rerank 8s.
- FE1: evidence недостаточно → расширить запрос/ослабить фильтры, cap 2.
- FE1b: empty → low-conf + план до-сбора данных [R-N3][R-F11].
- deny-list документов [R-N5].

## Метрики
- hit-rate, latency, source-ID coverage, rerank delta.

## Требования
[R-F1][R-F3][R-F4][R-F7][R-IN1][R-IN2][R-N2][R-N3][R-N4][R-K5][R-N5]
