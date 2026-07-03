# C4 Component — Вариант 2 (Hybrid RAG + agent)

```mermaid
flowchart TB
    subgraph ORC["Orchestrator state machine (Container 3)"]
        S1[1: Stage Router]
        S2[2: Context Budget Enforcer]
        S3[3: Transition Rules]
        S4[4: Slot Invoker]
    end
    subgraph RET["Retriever (Container 5)"]
        R1[5: Query Planner det.]
        R2[6: Vector Search]
        R3[7: KG Traversal]
        R4[8: LLM Reranker slot]
    end
    subgraph GEN["Hypothesis Generator (Container 7)"]
        G1[9: Candidate Synthesizer LLM]
        G2[10: Novelty Gap Finder LLM]
    end
    subgraph SCR["Scorer/Ranker (Container 8)"]
        SC1[11: Feature Extractor det.]
        SC2[12: LLM Judge slot]
        SC3[13: Weighted Ranker det.]
    end
    subgraph MEM["Memory (Container 9)"]
        M1[14: Session Store]
        M2[15: Feedback Labels Store]
    end
    S1 --> S4
    S4 -->|"retrieve slot"| R1
    R1 --> R2 & R3
    R2 & R3 --> R4
    R4 -->|"ranked evidence"| S4
    S4 -->|"generate slot"| G1 & G2
    G1 & G2 -->|"candidates"| S4
    S4 -->|"score slot"| SC1
    SC1 --> SC2
    SC2 --> SC3
    SC3 -->|"ranked hypotheses"| S4
    S3 -->|"next stage / re-run"| S1
    S2 -.->|"truncate to budget"| S4
    S1 -.->|"read/write session"| M1
    SC3 -.->|"labels"| M2
    M2 -.->|"calibrate weights"| SC3
    style R4 fill:#fdd,stroke:#c00
    style G1 fill:#fdd,stroke:#c00
    style G2 fill:#fdd,stroke:#c00
    style SC2 fill:#fdd,stroke:#c00
```

## Legend
- Красные узлы (`#fdd`) — LLM-слоты (семантические решения внутри детерминированной
  стадии). Прочие — детерминированные. Пунктир — доступ к памяти/калибровка.

## Компоненты и связи

| # | Компонент | Тип | Роль | Требования |
|---|-----------|-----|------|------------|
| 1 | Stage Router | deterministic | Выбор текущей стадии по стейт-машине. | [R-F6] |
| 2 | Context Budget Enforcer | deterministic | Токен-бюджет на слот; truncate/rerank evidence. | [R-N4] |
| 3 | Transition Rules | deterministic | Правила перехода стадий + re-run (canvas). | [R-F14] |
| 4 | Slot Invoker | deterministic | Вызов LLM-слотов с подготовленным контекстом. | [R-F6] |
| 5 | Query Planner | deterministic | Детерминированный план запросов из цели/ограничений. | [R-IN1][R-IN2] |
| 6 | Vector Search | deterministic | Плотный поиск чанков (RU/EN/CN). | [R-F1][R-N2] |
| 7 | KG Traversal | deterministic | Cypher/SPARQL обход графа сущностей/связей. | [R-F4] |
| 8 | LLM Reranker | `LLM/Agent` | Переранжирование evidence под цель. | [R-F7] |
| 9 | Candidate Synthesizer | `LLM/Agent` | Гипотезы из retrieved context (аналогии/контрфактуалы). | [R-F6][R-OUT4] |
| 10 | Novelty Gap Finder | `LLM/Agent` | Выявление пробелов в знаниях → гипотезы. | [R-F5] |
| 11 | Feature Extractor | deterministic | Новизна (граф. дистанция), реализуемость (constraint-match), эффект (KPI-прогноз). | [R-OUT5..7][R-IN2] |
| 12 | LLM Judge | `LLM/Agent` | Качественная оценка осей. | [R-F7] |
| 13 | Weighted Ranker | deterministic | Взвешенная сумма; веса [R-A1]; калибровка по labels. | [R-A1][R-A3] |
| 14 | Session Store | deterministic | Состояние run, артефакты стадий. | [R-F14] |
| 15 | Feedback Labels Store | deterministic | Метки фидбэка для калибровки. | [R-A3] |

**Распределение LLM vs deterministic**:
- `LLM/Agent` (слоты): #8 Reranker, #9 Synthesizer, #10 Gap Finder, #12 Judge.
- deterministic (каркас): #1,#2,#3,#4 (оркестрация), #5,#6,#7 (retrieval),
  #11,#13 (скоринг-каркас), #14,#15 (память).

> Обоснование позиции: детерминированный каркас даёт воспроизводимость и
> контроль контекста [R-N1][R-N4]; LLM-слоты — креативность там, где правила
  слабы (генерация, реранк, качественная оценка) [R-F5][R-F6]. Re-run стадии
  (canvas) поддержан transition rules #3 [R-F14].
