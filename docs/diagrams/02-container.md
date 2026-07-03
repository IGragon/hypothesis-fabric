# C4 Container — Вариант 2 (Hybrid RAG + agent)

```mermaid
C4Container
    title C4 Container: Фабрика гипотез — Hybrid RAG + agent
    Boundary(perim, "On-prem периметр [R-N5]") {
        Container(1, "Web App (frontend)", "TypeScript/React", "Canvas гипотез, графы, конструктор roadmap [R-F10][R-A2][R-F14]")
        Container(2, "API Gateway", "FastAPI", "REST: приём цели/ограничений, оркестрация стадий")
        Container(3, "Orchestrator (state machine)", "Python", "Детерминированные переходы стадий + LLM-слоты [R-F6][R-F7]")
        Container(4, "Ingestion & ETL", "Airflow/Prefect + GROBID/SciSpacy", "Парсинг, chunking, эмбеддинги, KG-build [R-F1..4]")
        Container(5, "Retriever", "Service", "Retrieval-first: векторный + KG-запрос, реранк (LLM) [R-F1][R-F7]")
        Container(6, "KG Service", "Neo4j", "Сущности/связи, первый класс [R-F4][R-F5]")
        Container(7, "Hypothesis Generator (slot)", "LLM", "Генерация гипотез из retrieved context [R-F6][R-OUT4]")
        Container(8, "Scorer/Ranker", "hybrid", "Дет. признаки + LLM-суждение [R-F7][R-OUT5..7]")
        Container(9, "Storage", "Postgres + VectorDB + ObjectStore + Neo4j", "Сессии, артефакты, чанки, граф, labels [R-F3][R-A3]")
        Container(10, "LLM Runtime", "on-prem / private endpoint", "Inference LLM [ASSUM-3]")
        Container(11, "Observability", "OTel + logs + evals store", "Трейсы стадий, метрики, evals [R-N1]")
    }
    System_Ext(12, "База знаний / API", "Документы, внешние API [R-IN3][R-K5]")
    System_Ext(13, "Jira/YouTrack", "Экспорт задач [R-F13]")

    Rel(1, 2, "HTTP: цель, ограничения, фидбек")
    Rel(2, 3, "запуск run (stage transitions)")
    Rel(3, 5, "stage: retrieve (det. query plan)")
    Rel(5, 6, "kg_query")
    Rel(5, 9, "чанки/эмбеддинги")
    Rel(3, 7, "stage: generate (LLM slot)")
    Rel(7, 10, "LLM call")
    Rel(3, 8, "stage: score (hybrid)")
    Rel(4, 12, "ETL: парсинг/импорт")
    Rel(4, 9, "чанки/эмбеддинги/граф")
    Rel(4, 6, "построение KG")
    Rel(3, 13, "stage: export")
    Rel(2, 11, "spans/логи стадий")
    Rel(3, 9, "stateful session artifacts [R-A3]")
```

## Legend
- `Container` — runnable-единица. `System_Ext` — вне периметра.
- `Rel` — связь; подчёркнутое свойство — главная ответственность.
- Теги `[R-*]` — трассировка к требованиям.

## Компоненты и связи

| # | Контейнер | Технология | Роль | Требования |
|---|-----------|------------|------|------------|
| 1 | Web App | TypeScript/React | Canvas: графы, карточки, конструктор roadmap, фидбек. | [R-F10][R-A2][R-F14] |
| 2 | API Gateway | FastAPI | REST-шлюз; приём [R-IN1..3]; запуск run. | [R-N4][R-N5] |
| 3 | Orchestrator (state machine) | Python | Детерминированные переходы стадий; LLM-слоты в рамках стадии. | [R-F6][R-F7] |
| 4 | Ingestion & ETL | Airflow/Prefect + GROBID/SciSpacy | Парсинг, chunking, эмбеддинги, построение KG. | [R-F1..4][R-F3] |
| 5 | Retriever | Service | Retrieval-first: векторный + KG-запрос; LLM-реранк. | [R-F1][R-F7] |
| 6 | KG Service | Neo4j | Сущности/связи — первый класс; provenance. | [R-F4][R-F5] |
| 7 | Hypothesis Generator | LLM | Генерация гипотез из retrieved context (слот). | [R-F6][R-OUT4] |
| 8 | Scorer/Ranker | hybrid | Дет. признаки + LLM-суждение; веса [R-A1]. | [R-F7][R-OUT5..7] |
| 9 | Storage | Postgres + VectorDB + ObjectStore + Neo4j | Сессии, артефакты, чанки, граф, labels. | [R-F3][R-A3] |
| 10 | LLM Runtime | on-prem | Inference; изолирован. | [R-N5][ASSUM-3] |
| 11 | Observability | OTel + logs + evals | Трейсы стадий, метрики, evals. | [R-N1][R-N4] |
| 12 | База знаний / API | — | Внешние документы/API; опциональны. | [R-IN3][R-K5] |
| 13 | Jira/YouTrack | — | Приёмник задач. | [R-F13] |

**Ключевая особенность V2**: Orchestrator (3) — **стейт-машина**, не свободный
агент. Стадии фиксированы (retrieve → generate → score → explain → export); LLM
работает внутри слотов (7, 8, реранк в 5). Ingestion/ETL (4) и KG (6) —
**предbuilt** детерминированно, а не лениво. Это даёт воспроизводимость и контроль
контекста, уступая V1 в гибкости планирования.
