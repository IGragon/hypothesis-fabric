# System Design — Вариант 2 (Hybrid RAG + agent)

> Позиция: **детерминированный retrieval-first каркас + LLM в слотах**.
> Оркестратор — стейт-машина. Опирается на `analysis.md`; диаграммы — в
> `docs/diagrams/`.

---

## 1. Ключевые архитектурные решения (с rationale)

| ID | Решение | Rationale | Требования | Альтернатива (почему нет) |
|----|---------|-----------|------------|----------------------------|
| AD-1 | Orchestrator = state machine, не свободный агент | Воспроизводимость переходов, контроль токенов; LLM только в слотах. | [R-N1][R-N4] | Свободный агент (V1): выше риск зацикливания/перерасхода. |
| AD-2 | Предbuilt ETL + KG (детерминированно) | Retrieval-first: поиск по готовому индексу быстрее и стабильнее ленивого. | [R-F1..4][R-N4] | Ленивый парсинг (V1): выше latency, ниже воспроизводимость. |
| AD-3 | KG — первый класс (Neo4j) | Сущности/связи поддерживают выявление пробелов и новизну через граф-дистанцию. | [R-F4][R-F5][R-OUT5] | Только векторный поиск: теряет структурную новизну. |
| AD-4 | LLM в фиксированных слотах (реранк, генерация, judge) | Креативность там, где правила слабы; каркас там, где нужна точность. | [R-F5][R-F6][R-F7] | LLM везде (V1) или нигде (V3): теряют баланс. |
| AD-5 | Context budget per slot (Enforcer) | Каждый слот получает truncate/rerank evidence до лимита → предсказуемая стоимость. | [R-N4] | Без лимита: непредсказуемые токены. |
| AD-6 | Canvas / re-run стадии (transition rules) | Пользователь правит промежуточный артефакт и перезапускает стадию [R-F14]. | [R-F14] | Односторонний пайплайн: теряет интерактивность. |
| AD-7 | Citation Bind + constraint_check — детерминированные gates | Точность цитат и реализуемость — критичны; LLM ненадёжна для чисел. | [R-K2][R-IN2][R-N1] | LLM-проверка: галлюцинации источников. |
| AD-8 | Weighted Ranker (формула) с калибровкой по labels | Прозрачная формула с весами [R-A1]; калибровка по фидбэку [R-A3] без fine-tuning. | [R-A1][R-A3][ASSUM-7] | LLM-ранжирование: непрозрачно. |
| AD-9 | On-prem LLM runtime | [R-N5] требует локального развёртывания. | [R-N5][ASSUM-3] | Внешний API: противоречит [R-N5]. |
| AD-10 | Расширение доменов через схему KG | Новые домены (полимеры/композиты) — расширение узлов/рёбер без перестройки ядра. | [R-K4] | Перестройка ядра: нарушает масштабируемость. |

---

## 2. Список модулей и их роли

| # | Модуль | Роль | Тип | Спецификация |
|---|--------|------|-----|--------------|
| M1 | Ingestion & ETL | Парсинг, chunking, эмбеддинги, KG-build (предbuilt). | deterministic | `specs/ingestion-etl.md` |
| M2 | Retriever | Retrieval-first: vector+KG, LLM-реранк. | det.+`LLM/Agent` | `specs/retriever.md` |
| M3 | Knowledge Graph Service | Сущности/связи, provenance, конфликты. | deterministic | `specs/knowledge-graph.md` |
| M4 | Orchestrator (state machine) | Переходы стадий + LLM-слоты, context budget. | deterministic | `specs/orchestrator.md` |
| M5 | Hypothesis Generator | Генерация гипотез + выявление пробелов (слот). | `LLM/Agent` | `specs/hypothesis-generator.md` |
| M6 | Scorer/Ranker | Det. признаки + LLM Judge + Weighted Ranker. | det.+`LLM/Agent` | `specs/scorer-ranker.md` |
| M7 | Justification & Explanation | Обоснование + граф + неопределённость. | `LLM/Agent`+det. | `specs/justification-explanation.md` |
| M8 | Memory & Context | Session store, canvas, context budget, labels. | deterministic | `specs/memory-context.md` |
| M9 | Export & Integration | Отчёты + трекеры + roadmap (опц.). | deterministic | `specs/export-integration.md` |
| M10 | Expert Feedback Loop | Labels → калибровка весов. | deterministic | `specs/feedback-loop.md` |
| M11 | Serving & Config | API, конфиг, секреты, версии моделей. | deterministic | `specs/serving-config.md` |
| M12 | Observability & Evals | Трейсы стадий, метрики, evals. | deterministic | `specs/observability-evals.md` |

> Спецификации покрывают все 12 модулей 1:1.

---

## 3. Основной workflow выполнения задачи

Шаги соответствуют `04-workflow.md`.

1. **Пользователь** → цель [R-IN1] + ограничения [R-IN2] → API Gateway (M11).
2. **KPI/Task Parser** (M4) нормализует цель и ограничения [ASSUM-4]. (det.)
3. **Stage Router** (M4) иницирует run. (det.)
4. **Retrieve** (M2): query plan → vector search + KG traversal → LLM rerank
   [R-F1][R-F4][R-F7]. (det.+LLM)
5. **evidence enough?** — gate; если нет → FE1 (расширить запрос, cap 2). (det.)
6. **Generate slot** (M5): Candidate Synthesizer + Gap Finder → кандидаты
   [R-F5][R-F6][R-OUT4]. (`LLM/Agent`)
7. **candidates valid?** — schema-проверка; если нет → FE2 (re-prompt, cap 3). (det.)
8. **Citation Bind** (M7) — привязка claim→source [R-F9]. (det.)
9. **Score** (M6): features → LLM Judge → Weighted Ranker [R-F7][R-OUT5..7]. (гибрид)
10. **constraint_check** — hard gate [R-IN2]; нарушение → FE4 (вернуться в Generate). (det.)
11. **Explain slot** (M7): обоснование + граф + неопределённость [R-F8][R-F10][R-F11]. (`LLM/Agent`)
12. **Export** (M9): отчёт + задачи [R-F12][R-F13]. (det.)

Re-run любой стадии — через transition rules (canvas) [R-F14].

---

## 4. State / Memory / Context handling

| Ресурс | Область | Политика | Требования |
|--------|---------|----------|------------|
| Session Store | run | состояние стадий + артефакты; персистентно; re-run стадии. | [R-F14] |
| Feedback Labels | долгосрочная | accepted/rejected/adjusted; калибровка весов ранжирования. | [R-A3][ASSUM-7] |
| Context budget | LLM-слот | ≤ 16k токенов; Enforcer truncate/rerank evidence. | [R-N4] |
| Canvas state | UI | редактируемые артефакты стадий, перезапуск. | [R-F14][R-A2] |

**Memory policy**: Feedback Labels не дообучают LLM [ASSUM-7]; калибруют веса
Weighted Ranker (M6) и признаки. Хранение on-prem; redaction в логах [R-N5].

---

## 5. Retrieval-контур

| Параметр | Значение | Требование |
|----------|----------|------------|
| Архитектура | retrieval-first: предbuilt векторный индекс + KG | [AD-2][R-F1][R-F4] |
| Поиск | плотный векторный (RU/EN/CN) + KG traversal (Cypher/SPARQL) | [R-N2][R-F4] |
| Реранк | LLM-реранк evidence под цель (слот) | [R-F7] |
| Query plan | детерминированный из цели/ограничений | [R-IN1][R-IN2] |
| Метаданные | источник/дата/автор/условия с чанком | [R-F3] |
| Context budget | evidence truncate/rerank до 16k токенов | [R-N4] |
| Надёжность | empty → FE1b (low-conf + план до-сбора) | [R-N3][R-F11] |

---

## 6. Tool / API-интеграции

| Tool/API | Контракт | Timeout | Side effects | Защита | Требования |
|----------|----------|---------|--------------|--------|------------|
| vector_search(query, k, lang) | `chunks[]+meta` | 4s | только чтение | deny-list docs | [R-F1] |
| kg_traverse(cypher/keyword) | `entities/relations[]` | 3s | только чтение | параметризованный Cypher | [R-F4] |
| llm_rerank(evidence, goal) | `ranked[]` | 8s | — | schema validation | [R-F7] |
| generate(evidence, constraints) | `candidates[]` | 15s | — | schema validation, cap 3 | [R-F6][R-OUT4] |
| cite_bind(claims, sources) | `claim→source_id[]` | 3s | — | coverage gate ≥85% | [R-F9][R-K2] |
| constraint_check(hyp, constraints) | `{ok, violations[]}` | 2s | — | hard gate | [R-IN2] |
| export(format, payload) | `file/task` | 30s | файл/POST Jira | RBAC, redaction | [R-F12][R-F13] |
| External API (опц.) | статьи/мета | 8s, retry×2 | внешние вызовы | toggle off | [R-K5][R-N5] |

---

## 7. Основные failure modes, fallback и guardrails

| ID | Failure mode | Fallback | Guardrail | Требования |
|----|--------------|----------|-----------|------------|
| FE1 | evidence недостаточно | расширить запрос/ослабить фильтры, cap 2 → low-conf | gate «evidence enough» | [R-N3][R-N4] |
| FE1b | retrieve empty | cached/пусто → low-conf + план до-сбора данных | hit-rate monitor | [R-N3][R-F11] |
| FE2 | candidates invalid | re-prompt слота, cap 3 → отбраковать | schema validator | [R-N1] |
| FE3 | LLM Judge недоступен | det.-only скорер (features + weighted ranker) | healthcheck LLM | [R-F7] |
| FE4 | нарушение ограничений | отбраковать → лог → вернуться в Generate | hard gate | [R-IN2][R-K1] |
| FE5 | stage timeout | partial + статус `incomplete` | per-stage timeout | [R-N4] |
| FE6 | cite_bind low coverage | re-generate с требованием источника, cap 2 | coverage gate 85% | [R-K2][R-F9] |
| FE7 | конфликт источников | KG `contradicts`; explain-слот отмечает, выбирает надёжный | provenance-трейл | [R-N3][R-N1] |
| FE8 | внешний API недоступен | fallback на локальный индекс | toggle off | [R-K5][R-N5] |
| FE9 | ETL-джоба упала | retry + dead-letter; индекс на последнем успешном слепке | idempotent ETL | [R-F1][R-N3] |

**Guardrails (общие)**: per-slot context budget 16k, per-stage timeout, coverage
gate 85%, hard constraint gate, RBAC на экспорт, redaction в логах, внешние API
отключаемы [R-N5].

---

## 8. Конкретные технические и операционные ограничения (числа)

| Параметр | Значение | Единица | Требование |
|----------|----------|---------|------------|
| Latency до первичного набора (p50) | ≤ 2 | мин | [R-N4] |
| Latency до первичного набора (p95) | ≤ 5 | мин | [R-N4] |
| Context budget на LLM-слот | ≤ 16 000 | токенов | [R-N4] |
| Токены/сессия (input) | ≤ 20 000 | токенов | [R-N4] |
| Токены/сессия (output) | ≤ 6 000 | токенов | [R-N4] |
| ETL batch latency | ≤ 2 | ч на 10⁴ док. [ASSUM-1] | [R-F1] |
| Max re-prompt (FE2) | 3 | попытки | [R-N1] |
| Max query expansion (FE1) | 2 | итерации | [R-N3] |
| Coverage цитат (gate) | ≥ 85 | % | [R-K2][R-F9] |
| Hallucination-source rate | ≤ 4 | % | [R-K2] |
| Воспроизводимость (Jaccard@10 re-run) | ≥ 0.9 | — | [R-N1] |
| Доступность API | ≥ 99.5 | % | [R-N4] |
| Timeout vector_search | 4 | с | [R-N4] |
| Timeout kg_traverse | 3 | с | [R-N4] |
| Timeout llm_rerank | 8 | с | [R-N4] |
| Timeout generate | 15 | с | [R-N4] |
| Timeout export | 30 | с | [R-F13] |
| Timeout external API | 8 | с (retry×2) | [R-K5] |
| Локализация данных | 100 | % on-prem | [R-N5] |
| Корпус (оценка) | 10⁴–10⁵ | документов [ASSUM-1] | [R-IN3] |

**Надёжность**: MTBF ≥ 1 рабочий день без деградации; RTO ≤ 10 мин (рестарт
контейнеров + replay run из Session Store). Стоимость: 1 GPU-узел для LLM-слотов
+ CPU-кластер для ETL [ASSUM-2][ASSUM-3]; переменные затраты — токены
(контролируются budget-метриками).

---

## 9. Трассировка требований → модули

| ID | Модуль(и) | ID | Модуль(и) | ID | Модуль(и) |
|----|-----------|----|-----------|----|-----------|
| R-IN1 | M4, M2 | R-F1 | M1, M2 | R-F8 | M7 |
| R-IN2 | M4, M6 (constraint) | R-F2 | M1 | R-F9 | M7 |
| R-IN3 | M1, M3 | R-F3 | M1, M8 | R-F10 | M7, M11 |
| R-OUT1 | M5, M4 | R-F4 | M1, M3, M2 | R-F11 | M7, M6 |
| R-OUT2 | M7 | R-F5 | M5, M3 | R-F12 | M9 |
| R-OUT3 | M7 | R-F6 | M5 | R-F13 | M9 |
| R-OUT4 | M5 | R-F7 | M6, M2 | R-F14 | M4, M8, M10 |
| R-OUT5 | M6 | R-N1 | M4, M7, M12 | R-A1 | M6, M11 |
| R-OUT6 | M6 | R-N2 | M1, M2, M5 | R-A2 | M9, M11 |
| R-OUT7 | M6 | R-N3 | M1, M3, M7, M12 | R-A3 | M8, M10, M6 |
| R-OUT8 | M9 (опц.) | R-N4 | M4, M12 | — | — |
| R-K1 | M6, M4 | R-N5 | M11, M12 | — | — |
| R-K2 | M7, M4 | — | — | — | — |
| R-K3 | M1, M5 | — | — | — | — |
| R-K4 | M3, M1 | — | — | — | — |
| R-K5 | M1, M2, M9 | — | — | — | — |

> Все ID из `analysis.md` адресованы. R-K4 — через расширяемую схему KG (M3/M1).

---

## 10. Assumptions

Все допущения определены в `analysis.md` (раздел 5); здесь зафиксировано, какие
применимы к V2:

| Допущение | Применение в V2 |
|-----------|-----------------|
| `[ASSUM-1]` объём корпуса 10⁴–10⁵ док. — основа предbuilt ETL (AD-2) и оценки ETL latency. |
| `[ASSUM-2]` RU/EN приоритет, CN реже — выбор мультиязычного эмбеддера (M1/M2). |
| `[ASSUM-3]` on-prem LLM — основа AD-9; внешние API отключаемы (FE8). |
| `[ASSUM-4]` KPI/ограничения в NL и/или структурированно — KPI/Task Parser (M4) нормализует. |
| `[ASSUM-5]` roadmap (R-OUT8) — опциональное расширение (M9). |
| `[ASSUM-6]` Jira/YouTrack через REST — M9. |
| `[ASSUM-7]` обучение на фидбэке через пере-взвешивание, не fine-tuning — AD-8, M6/M8/M10. |

Допущения собраны в одном месте (`analysis.md` раздел 5 + эта таблица).
