# Архитектура JEEX Idea

> **Техническая спецификация:** Детальные технические требования, API, схемы баз данных и конфигурации описаны в [specs.md](specs.md)

## 1) Назначение и границы

- Продукт трансформирует "сырую" идею в профессиональный пакет Markdown документов: Описание идеи → Инженерные спецификации → Архитектура → План реализации.
- Формат работы — диалоговый интерфейс с 4 этапами, на каждом из которых работает команда специализированных агентов под координацией Продукт-менеджера.
- Язык проекта определяется первым сообщением пользователя и сохраняется для всех документов и взаимодействий на протяжении всего жизненного цикла проекта.
- Взаимодействие происходит через единый чат без дополнительных форм: агенты задают структурированные вопросы с вариантами ответов, пользователь отвечает свободным текстом, выбором вариантов (`1.b, 2.c`) или комбинацией подходов.
- Ценностные требования: изоляция знаний между проектами, воспроизводимость (версионирование документов), объяснимость результатов (структурные шаблоны, валидации), скорость ответа (потоковая передача), расширяемость (подключаемые агенты через ADK, рекомендации партнеров).

## 2) Архитектурные принципы

- **Компоненты единственной ответственности**: UI, API, оркестрация агентов, команды агентов, память/поиск, долгосрочное хранение, кэш/квоты, экспорт, наблюдаемость.
- **Мульти-агентная командная модель**: Продукт-менеджер как координатор, управляющий командами специализированных агентов на каждом этапе; агенты взаимодействуют через унифицированные протоколы.
- **Языковая изоляция проекта**: язык определяется при создании проекта из первого сообщения пользователя и применяется ко всем документам, промптам агентов и интерфейсу; переключение языка в рамках проекта не предусмотрено.
- **Четкий контекст проекта**: любой агент и любой поиск работают только в рамках `project_id` и `language`.
- **Принуждение на стороне сервера**: клиент никогда не устанавливает фильтры напрямую для памяти/поиска; фильтр формируется и подписывается на бэкенде.
- **Единый канал взаимодействия**: все коммуникации (вопросы агентов, ответы пользователя, обновления документов) происходят через единый чат; агенты парсят как свободный текст, так и структурированные ответы (`1.b, 2.c`).
- **Потоковая доставка**: все длинные операции доставляют прогресс и промежуточные результаты через SSE.
- **Версионирование как контракт**: каждая значительная генерация/правка является новой версией артефакта, позволяя пользователям "откатывать" изменения в любой момент.
- **Наблюдаемость по умолчанию**: OpenTelemetry для распределенной трассировки с correlation ID и автоматической инструментацией FastAPI.
- **Паттерны устойчивости**: Tenacity для логики повторов и автоматические выключатели при взаимодействии с внешними LLM API для предотвращения каскадных сбоев.
- **Расширяемость через ADK**: поддержка Agent Development Kit (ADK) от Google для будущего выделения агентов в удаленные сервисы с сохранением совместимости протоколов.

## 3) Логическая схема (высокий уровень)

```mermaid
graph TB
    subgraph "Frontend Layer"
        UI[Web Frontend<br/>React/TS<br/>Unified Chat Interface]
    end

    subgraph "API Layer"
        API[API Gateway<br/>FastAPI + Security Middleware<br/>Auth, Rate Limiting & SSE]
        RP[Reverse Proxy<br/>TLS & Compression]
        LANG[Language Detector<br/>LLM-based detection from first message<br/>NO scripts/libraries allowed<br/>Project-level language lock]
    end

    subgraph "Processing Layer"
        ORCH[Agent Orchestrator<br/>Crew + ADK Support<br/>I/O Contracts & Circuit Breakers]
        PM[Product Manager Agent<br/>Coordinator & Document Owner<br/>Multi-language support]
        EMB[Embedding Service<br/>Text Normalization<br/>Vector Computation]
        QA[Quality Assurance<br/>Readability & Grammar<br/>Content Validation]
        PARSER[Response Parser<br/>Free text + Structured format<br/>Context extraction]
    end

    subgraph "Storage Layer"
        QDRANT[Vector Store<br/>Qdrant<br/>Project + Language Scoped Memory]
        PRIMARY[Primary Store<br/>Documents & Versions<br/>Language metadata]
        REDIS[Cache/Queue<br/>Redis<br/>Limits & Progress]
    end

    subgraph "Observability"
        OBS[Observability<br/>OpenTelemetry Stack<br/>Auto-instrumentation & Tracing]
    end

    subgraph "Agent Teams"
        subgraph "Idea Stage Team"
        BA[Business Analyst]
            VC[Venture Expert]
            TRIZ[TRIZ Expert]
            DT[Design Thinker]
            SA_SYS[System Analyst]
        end

        subgraph "Specs Stage Team"
        ES[Engineering Standards]
            QAE[QA Expert]
            SEC[Security Expert]
        end

        subgraph "Architecture Stage Team"
            ARCH[Solution Architect]
            DEVOPS[DevOps Expert]
            PERF[Performance Expert]
        end

        subgraph "Planning Stage Team"
        PP[Project Planner]
            SM[Scrum Master]
            RM[Risk Manager]
        end
    end

    UI --> RP
    RP --> API
    API --> LANG
    LANG --> ORCH
    API --> ORCH
    ORCH --> PM

    PM --> BA
    PM --> VC
    PM --> TRIZ
    PM --> DT
    PM --> SA_SYS
    PM --> ES
    PM --> QAE
    PM --> SEC
    PM --> ARCH
    PM --> DEVOPS
    PM --> PERF
    PM --> PP
    PM --> SM
    PM --> RM

    ORCH --> EMB
    ORCH --> QA
    ORCH --> PARSER
    EMB --> QDRANT
    QA --> PRIMARY
    ORCH --> PRIMARY
    API --> REDIS

    BA -.-> QDRANT
    VC -.-> QDRANT
    TRIZ -.-> QDRANT
    DT -.-> QDRANT
    SA_SYS -.-> QDRANT
    ES -.-> QDRANT
    QAE -.-> QDRANT
    SEC -.-> QDRANT
    ARCH -.-> QDRANT
    DEVOPS -.-> QDRANT
    PERF -.-> QDRANT
    PP -.-> QDRANT
    SM -.-> QDRANT
    RM -.-> QDRANT

    API --> OBS
    ORCH --> OBS
    EMB --> OBS
    QDRANT --> OBS
```

**Компоненты:**

- **Web Frontend** (React/TS): единый чат-интерфейс для всех взаимодействий, 4-этапный прогресс, предварительный просмотр и подсветка различий документов, скачивание архива.
- **API Gateway / Backend** (FastAPI): аутентификация (OAuth2: только Twitter на первом этапе), потоковая передача SSE, лимиты, сбор/агрегация телеметрии, экспорт, рекомендации партнеров.
- **Language Detector**: определение языка из первого сообщения пользователя **через LLM** (запрещено использовать скрипты/библиотеки для детектирования языка), сохранение на уровне проекта, применение ко всем последующим взаимодействиям.
- **Agent Orchestrator** (подход Crew + поддержка ADK + строгие модели I/O контрактов): управление жизненным циклом агентов, маршрутизация запросов, поддержка локальных и удаленных агентов через ADK.
- **Product Manager Agent**: основной координатор, управляет документами проекта, решает какому эксперту передать слово, синтезирует ответы пользователя и обновляет документы, работает на языке проекта.
- **Agent Teams** (команды специализированных агентов на каждом этапе):
  - **Idea Stage**: Business Analyst, Venture Expert, TRIZ Expert, Design Thinker, System Analyst
  - **Specs Stage**: Engineering Standards, QA Expert, Security Expert
  - **Architecture Stage**: Solution Architect, DevOps Expert, Performance Expert
  - **Planning Stage**: Project Planner, Scrum Master, Risk Manager
- **Response Parser**: анализ ответов пользователя в свободном формате или структурированном (`1.b, 2.c, 2.d`), извлечение контекста и намерений.
- **Embedding Service** (абстракция над выбранной моделью): нормализация текста, разбиение на фрагменты, дедупликация, вычисление векторов.
- **Vector Store** (Qdrant): память/контекст проекта, поиск знаний с фильтрацией по проекту и языку.
- **Primary Store** (документы/версии/настройки): долгосрочное хранение артефактов и истории с метаданными языка.
- **Cache/Queue** (Redis): буферы против штормов, очереди эмбеддингов, корзины токенов ограничения скорости, флаги быстрого прогресса.
- **Observability** (стек OTel): трассировки генерации/поиска, дашборды SLO, оповещения.
- **Reverse Proxy**: TLS, сжатие, проброс SSE, базовая защита.

## 4) Ключевые пользовательские потоки

### 4.1 Описание идеи → Мульти-агентное формирование и черновик

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Web UI
    participant API as API Gateway
    participant LANG as Language Detector
    participant PM as Product Manager
    participant BA as Business Analyst
    participant VC as Venture Expert
    participant TRIZ as TRIZ Expert
    participant DT as Design Thinker
    participant SA as System Analyst
    participant PARSER as Response Parser
    participant EMB as Embedding Service
    participant Q as Qdrant
    participant PS as Primary Store

    U->>UI: Enters raw idea (any language)
    UI->>API: POST /projects/{id}/step1
    API->>LANG: Detect language from first message
    LANG->>PS: Save project language
    API->>PM: Start idea refinement (detected language)

    PM->>PS: Save structured idea draft v1
    PM->>U: Greeting (in user's language)

    loop Multi-agent cyclic refinement
        PM->>U: Decide which expert to engage

        alt Business Analyst turn
            PM->>BA: Your turn
            BA->>Q: Search context (project_id, language)
            BA->>U: 1-5 questions with answer options (a,b,c,d,e)
            U->>PARSER: Free text OR structured format OR mixed
            PARSER->>BA: Parsed answers + context
            BA->>BA: Formulate section text
            BA->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Idea Description v2
        end

        alt Venture Expert turn
            PM->>VC: Your turn
            VC->>Q: Search context (project_id, language)
            VC->>U: Investment & scaling questions
            U->>PARSER: Answers
            PARSER->>VC: Parsed answers + context
            VC->>VC: Formulate section text
            VC->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Idea Description v3
        end

        alt TRIZ Expert turn
            PM->>TRIZ: Your turn
            TRIZ->>Q: Search context
            TRIZ->>U: Innovation & contradictions questions
            U->>PARSER: Answers
            PARSER->>TRIZ: Parsed answers + context
            TRIZ->>TRIZ: Formulate section text
            TRIZ->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Idea Description v4
        end

        alt Design Thinker turn
            PM->>DT: Your turn
            DT->>Q: Search context
            DT->>U: UX & empathy questions
            U->>PARSER: Answers
            PARSER->>DT: Parsed answers + context
            DT->>DT: Formulate section text
            DT->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Idea Description v5
        end

        alt System Analyst turn
            PM->>SA: Your turn
            SA->>Q: Search context
            SA->>U: System dependencies questions
            U->>PARSER: Answers
            PARSER->>SA: Parsed answers + context
            SA->>SA: Formulate section text
            SA->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Idea Description v6
        end

        Note over U,PM: User can interrupt: "satisfied" or request specific expert

    end

    PM->>EMB: Extract key facts from final document
    EMB->>Q: Save embeddings (project_id, language)
    API-->>UI: SSE: Progress updates (agent turns, doc updates)
    API->>UI: Idea Description document ready (in user's language)
```

- Пользователь вводит сырую идею на любом языке; система автоматически определяет язык через LLM и сохраняет его на уровне проекта.
- Продукт-менеджер структурирует исходный текст и сохраняет первую версию документа.
- Далее Продукт-менеджер циклично координирует работу команды экспертов (BA, VC, TRIZ, DT, SA), каждый задаёт вопросы с вариантами ответов.
- Пользователь отвечает в едином чате свободным текстом, выбором вариантов (`1.b, 2.c`) или комбинацией подходов.
- Response Parser анализирует ответы и передаёт контекст **обратно эксперту** (не Продукт-менеджеру).
- **Эксперт формирует текст по своей части** и **выводит его в чат** для ознакомления пользователя.
- **Продукт-менеджер берёт текст эксперта** и **интегрирует его** (частично или полностью) в основной документ; версии инкрементируются.
- Пользователь может прервать процесс словами "устраивает" или обратиться к конкретному эксперту напрямую.
- Все взаимодействия и документы на языке проекта.
- Важные фрагменты попадают в память проекта (Qdrant) с фильтрацией по `project_id` и `language`.
- SSE доставляет прогресс (ход агентов, генерируемые тексты, обновления документа).

### 4.2 Спецификация → Командная разработка технических требований

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Web UI
    participant API as API Gateway
    participant PM as Product Manager
    participant ES as Engineering Standards
    participant QAE as QA Expert
    participant SEC as Security Expert
    participant PARSER as Response Parser
    participant Q as Qdrant
    participant PS as Primary Store

    U->>UI: Request specification
    UI->>API: POST /projects/{id}/step2
    API->>PM: Start specs phase (project language)

    PM->>Q: Search Idea context (project_id, language)
    Q->>PM: Full Idea Description
    PM->>PS: Initialize Engineering Specs draft v1

    loop Multi-agent specs refinement
        PM->>U: Decide which expert to engage

        alt Engineering Standards turn
            PM->>ES: Your turn
            ES->>Q: Search context (project_id, language)
            ES->>U: Standards/process suggestions with options
            U->>PARSER: Answers (free or structured)
            PARSER->>ES: Parsed preferences + context
            ES->>ES: Formulate section text
            ES->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Engineering Specs v2
        end

        alt QA Expert turn
            PM->>QAE: Your turn
            QAE->>Q: Search context
            QAE->>U: Testing strategy questions
            U->>PARSER: Answers
            PARSER->>QAE: Parsed answers + context
            QAE->>QAE: Formulate section text
            QAE->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Engineering Specs v3
        end

        alt Security Expert turn
            PM->>SEC: Your turn
            SEC->>Q: Search context
            SEC->>U: Security requirements questions
            U->>PARSER: Answers
            PARSER->>SEC: Parsed answers + context
            SEC->>SEC: Formulate section text
            SEC->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Engineering Specs v4
        end

        Note over U,PM: User can interrupt or request specific expert
    end

    PM->>Q: Save specs embeddings (project_id, language)
    API-->>UI: SSE: Progress updates
    API->>UI: Engineering Specs document ready (in project language)
```

- Продукт-менеджер координирует команду технических экспертов (Engineering Standards, QA Expert, Security Expert).
- Эксперты извлекают контекст из памяти проекта (Описание идеи), предлагают технические требования, стандарты разработки, подходы к тестированию и безопасности.
- Каждый эксперт формирует текст по своей части и выводит его в чат для ознакомления пользователя.
- Продукт-менеджер интегрирует текст эксперта (частично или полностью) в основной документ.
- Процесс циклический с возможностью прерывания пользователем.
- Пользователь может быстро заменить подходы (например, TDD → BDD) — эксперт переформирует свой текст, Продукт-менеджер обновляет документ.
- Все на языке проекта.

### 4.3 Архитектура → Командное проектирование системы

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Web UI
    participant API as API Gateway
    participant PM as Product Manager
    participant ARCH as Solution Architect
    participant DEVOPS as DevOps Expert
    participant PERF as Performance Expert
    participant PARSER as Response Parser
    participant Q as Qdrant
    participant PS as Primary Store

    U->>UI: Request architecture
    UI->>API: POST /projects/{id}/step3
    API->>PM: Start architecture phase (project language)

    PM->>Q: Search full context (Idea + Specs)
    Q->>PM: Complete project context
    PM->>PS: Analyze existing artifacts
    PS->>PM: Idea Description + Engineering Specs
    PM->>PS: Initialize Architecture draft v1

    loop Multi-agent architecture refinement
        PM->>U: Decide which expert to engage

        alt Solution Architect turn
            PM->>ARCH: Your turn
            ARCH->>Q: Search context (project_id, language)
            ARCH->>U: Stack/pattern suggestions with options
            U->>PARSER: Answers
            PARSER->>ARCH: Parsed preferences + context
            ARCH->>ARCH: Formulate section text
            ARCH->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Architecture v2
        end

        alt DevOps Expert turn
            PM->>DEVOPS: Your turn
            DEVOPS->>Q: Search context
            DEVOPS->>U: Infrastructure/deployment questions
            U->>PARSER: Answers
            PARSER->>DEVOPS: Parsed answers + context
            DEVOPS->>DEVOPS: Formulate section text
            DEVOPS->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Architecture v3
        end

        alt Performance Expert turn
            PM->>PERF: Your turn
            PERF->>Q: Search context
            PERF->>U: Scalability/optimization questions
            U->>PARSER: Answers
            PARSER->>PERF: Parsed answers + context
            PERF->>PERF: Formulate section text
            PERF->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Architecture v4
        end

        Note over U,PM: User can interrupt or request specific expert
    end

    PM->>Q: Save architecture embeddings (project_id, language)
    API-->>UI: SSE: Progress updates
    API->>UI: Architecture document ready (in project language)
```

- Продукт-менеджер координирует архитектурную команду (Solution Architect, DevOps Expert, Performance Expert).
- Эксперты извлекают контекст из памяти проекта (Описание идеи + Инженерные спецификации), предлагают технологический стек, паттерны, инфраструктуру, компромиссы.
- Каждый эксперт формирует текст по своей части и выводит его в чат для ознакомления пользователя.
- Продукт-менеджер интегрирует текст эксперта (частично или полностью) в основной документ.
- Процесс циклический с возможностью прерывания пользователем.
- Пользователь может быстро заменить решения (например, Postgres → ClickHouse) — эксперт переформирует свой текст с учётом изменений, Продукт-менеджер обновляет документ.
- Все на языке проекта.

### 4.4 Планирование → Командная разработка плана реализации

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Web UI
    participant API as API Gateway
    participant PM as Product Manager
    participant PP as Project Planner
    participant SM as Scrum Master
    participant RM as Risk Manager
    participant PARSER as Response Parser
    participant Q as Qdrant
    participant PS as Primary Store

    U->>UI: Request plan
    UI->>API: POST /projects/{id}/step4
    API->>PM: Start planning phase (project language)

    PM->>Q: Search full project context
    Q->>PM: Idea + Specs + Architecture
    PM->>PS: Analyze all artifacts
    PS->>PM: Complete document set
    PM->>PS: Initialize Implementation Plan draft v1

    loop Multi-agent planning refinement
        PM->>U: Decide which expert to engage

        alt Project Planner turn
            PM->>PP: Your turn
            PP->>Q: Search context (project_id, language)
            Note over PP: Phase formation<br/>Task decomposition<br/>Timelines
            PP->>U: Plan structure questions with options
            U->>PARSER: Answers
            PARSER->>PP: Parsed preferences + context
            PP->>PP: Formulate section text
            PP->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Implementation Plan v2
        end

        alt Scrum Master turn
            PM->>SM: Your turn
            SM->>Q: Search context
            Note over SM: Sprint planning<br/>Ceremonies<br/>Team velocity
            SM->>U: Agile process questions
            U->>PARSER: Answers
            PARSER->>SM: Parsed answers + context
            SM->>SM: Formulate section text
            SM->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Implementation Plan v3
        end

        alt Risk Manager turn
            PM->>RM: Your turn
            RM->>Q: Search context
            Note over RM: Risk identification<br/>Mitigation strategies<br/>Dependencies
            RM->>U: Risk management questions
            U->>PARSER: Answers
            PARSER->>RM: Parsed answers + context
            RM->>RM: Formulate section text
            RM->>U: Display generated text in chat
            U->>PM: Review generated text
            PM->>PS: Integrate text into Implementation Plan v4
        end

        Note over U,PM: User can interrupt or request specific expert
    end

    PM->>Q: Save plan embeddings (project_id, language)
    PM->>UI: Configure reminder beacons
    API-->>UI: SSE: Progress updates
    API->>UI: Implementation Plan ready (in project language)
```

- Продукт-менеджер координирует команду планирования (Project Planner, Scrum Master, Risk Manager).
- Эксперты извлекают контекст из памяти проекта (все предыдущие документы), составляют высокоуровневый План реализации: фазы, задачи, критерии приемки, риски/зависимости, контрольные события.
- Каждый эксперт формирует текст по своей части и выводит его в чат для ознакомления пользователя.
- Продукт-менеджер интегрирует текст эксперта (частично или полностью) в основной документ.
- Процесс циклический с возможностью прерывания пользователем.
- "Маяки" настраиваются для последующих напоминаний (например, "вернуться к интеграции с партнером X"), отображаются в UI.
- Все на языке проекта.

### 4.5 Финал — Экспорт пакета

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Web UI
    participant API as API Gateway
    participant EXP as Export Service
    participant PS as Primary Store

    U->>UI: Request package export
    UI->>API: POST /projects/{id}/export
    API->>EXP: Prepare archive

    EXP->>PS: Get active versions
    PS->>EXP: Description v1, Engineering Specs v1, Architecture v1, Implementation Plan v1

    loop Package assembly
        Note over EXP: Document integrity check
        Note over EXP: Manifest generation
        Note over EXP: Folder structuring
        Note over EXP: Markdown formatting
    end

    EXP->>EXP: Create ZIP archive
    EXP->>API: Archive ready
    API-->>UI: SSE: Progress updates
    API->>UI: Download link

    U->>UI: Download archive
    UI->>API: GET /exports/{export_id}
    API->>U: ZIP file with documents
```

- API собирает "снимок" активных версий артефактов во время экспорта, формирует архив с чистой Markdown структурой папок.

## 5) Компоненты и их взаимосвязи (детально)

### 5.1 Frontend

- **Единый чат-интерфейс** без дополнительных форм для всех взаимодействий с агентами; поддержка как свободного текста, так и структурированных ответов (`1.b, 2.c`).
- **Одностраничный мастер** с 4 этапами, каждый этап представляет независимый качественный "чек-лист" (завершение ключевого блока).
- **Подсветка различий** между версиями документов; "быстрые кнопки" для принятия/отката.
- **Полоса прогресса** по этапам и общему процессу; состояние устойчиво к перезагрузке вкладки (состояние получается с бэкенда).
- **Автоматическая языковая локализация**: интерфейс адаптируется под язык проекта, определённый из первого сообщения.
- **Изоляция проектов по URL**: `app.tld/{project_id}` (на основе пути).

### 5.2 API / Backend

- **Аутентификация** OAuth2 (только Twitter на первом этапе); авторизация на основе ролей проекта (владелец, редактор, наблюдатель).
- **Определение языка через LLM**: определение языка из первого сообщения пользователя при создании проекта **исключительно через LLM** (использование скриптов/библиотек для детектирования языка запрещено); сохранение в метаданных проекта; применение ко всем последующим взаимодействиям.
- **SSE эндпоинты** для прогресса генерации; контроль обратного давления, тайм-ауты, переподключение; потоковая доставка обновлений от агентов.
- **Response Parser**: сервис парсинга ответов пользователя в свободном формате или структурированном (`1.b, 2.c, 2.d`); извлечение контекста и намерений.
- **Ограничение скорости**: глобальные и на проект; отдельные квоты для LLM токенов/эмбеддингов.
- **Экспорт архива**: сбор "активных" версий артефактов, генерация манифеста состава на языке проекта.

### 5.2.1 Language Detector — LLM-based Language Detection

**КРИТИЧЕСКОЕ АРХИТЕКТУРНОЕ ТРЕБОВАНИЕ:** Определение языка проекта должно выполняться **исключительно через LLM**. Использование скриптов, библиотек или алгоритмов автоматического определения языка (langdetect, langid, fastText, TextBlob и т.п.) **строго запрещено**.

**Обоснование:**

- **Контекстуальное понимание**: LLM понимает не только язык, но и контекст, намерения и культурные особенности первого сообщения, что критически важно для дальнейшей работы всех агентов.
- **Согласованность тона**: Определение языка через ту же LLM, которая будет использоваться агентами, обеспечивает согласованность стиля и тона общения на протяжении всего проекта.
- **Гибкость**: LLM может обрабатывать смешанные языки, сленг, транслитерацию и другие сложные случаи, которые могут сломать простые библиотеки детектирования.
- **Единый стек**: Все взаимодействия с пользователем проходят через LLM, определение языка не исключение.

**Реализация:**

- Первое сообщение пользователя при создании проекта отправляется LLM с промптом для определения языка
- LLM возвращает ISO код языка (например, "en", "ru", "zh", "es")
- Язык сохраняется в метаданных проекта (поле `language` в таблице `projects`)
- Все последующие взаимодействия агентов используют этот язык из метаданных
- Язык проекта **иммутабелен** — не может быть изменён после создания проекта

**Пример промпта для LLM:**

```text
Определи язык следующего сообщения и верни ТОЛЬКО ISO 639-1 код языка (например: en, ru, zh, es, fr, de, ja, ko):

"{user_first_message}"

Верни только код языка, без дополнительных объяснений.
```

#### Эндпоинты (обзор)

```http
POST /auth/login
POST /auth/logout
GET  /auth/me

GET    /projects
POST   /projects
GET    /projects/{id}
PUT    /projects/{id}
DELETE /projects/{id}

POST /projects/{id}/step1
POST /projects/{id}/step2
POST /projects/{id}/step3
POST /projects/{id}/step4

GET  /projects/{id}/progress
GET  /projects/{id}/events

POST /projects/{id}/export
GET  /exports/{export_id}
```

#### Диаграмма API Flow

```mermaid
sequenceDiagram
    participant Client as Web Client
    participant API as FastAPI Gateway
    participant Auth as Twitter OAuth2 Service
    participant Agent as Agent Orchestrator
    participant DB as PostgreSQL
    participant VDB as Qdrant

    Client->>API: POST /auth/login
    API->>Auth: Twitter OAuth2 Flow
    Auth-->>Client: Access Token

    Client->>API: POST /projects {name, language}
    API->>DB: Create Project Record
    DB-->>API: Project ID
    API-->>Client: Project Created

    Client->>API: POST /projects/{id}/step1
    API->>Agent: Invoke Business Analyst
    Agent->>DB: Save About v1
    Agent->>VDB: Store Knowledge Embeddings
    API-->>Client: SSE Progress Updates
    API-->>Client: About Document Ready

    Client->>API: POST /projects/{id}/step2
    API->>Agent: Invoke Engineering Standards
    Agent->>VDB: Query Project Context
    Agent->>DB: Save Specs v1
    API-->>Client: SSE Progress Updates
    API-->>Client: Specs Document Ready

    Client->>API: POST /projects/{id}/step3
    API->>Agent: Invoke Solution Architect
    Agent->>VDB: Query About + Specs Context
    Agent->>DB: Save Architecture v1
    API-->>Client: Architecture Ready

    Client->>API: POST /projects/{id}/step4
    API->>Agent: Invoke Project Planner
    Agent->>VDB: Query Full Context
    Agent->>DB: Save Stories (plan.md + story folders) v1
    API-->>Client: Implementation Plan Ready

    Client->>API: POST /projects/{id}/export
    API->>DB: Gather All Documents
    API-->>Client: Export Ready
    Client->>API: GET /exports/{export_id}
    API-->>Client: ZIP Archive Download
```

### 5.3 Оркестратор агентов

**Архитектура агентов:**

- **Продукт-менеджер (координатор)** — основной агент-координатор:
  - Управляет жизненным циклом документов проекта
  - Решает, какому эксперту передать слово на текущем этапе
  - Синтезирует ответы пользователя и обновляет документы
  - Обеспечивает согласованность всех артефактов
  - Работает на языке проекта, определённом при создании
  - Может вызывать любого эксперта из любой команды по запросу пользователя

**Команды специализированных агентов по этапам:**

#### Этап 1: Idea Stage Team

- **Бизнес-аналитик** — исследует проблемную область, аудиторию, цели, метрики, монетизацию
- **Венчурный эксперт** — оценивает потенциал масштабирования, инвестиционную привлекательность, рыночные возможности
- **ТРИЗ-эксперт** — предлагает инновационные решения, выявляет противоречия, помогает найти нестандартные подходы
- **Дизайн-мыслитель** — фокусируется на пользовательском опыте, эмпатии к проблемам, человекоцентричных решениях
- **Системный аналитик** — анализирует взаимосвязи, выявляет скрытые зависимости и критические точки системы

#### Этап 2: Specs Stage Team

- **Инженерные стандарты** — формирует руководящие принципы кодирования, процессы Code Review, Definition of Done
- **QA-эксперт** — определяет стратегию тестирования, уровни покрытия, типы тестов
- **Security-эксперт** — устанавливает требования безопасности, аудита, защиты данных

#### Этап 3: Architecture Stage Team

- **Архитектор решений** — выбирает технологический стек, паттерны, проектирует компоненты и интеграции
- **DevOps-эксперт** — определяет инфраструктуру, CI/CD, мониторинг, deployment-стратегии
- **Performance-эксперт** — анализирует масштабируемость, оптимизацию, узкие места производительности

#### Этап 4: Planning Stage Team

- **Планировщик проектов** — декомпозирует задачи, оценивает временные рамки, определяет фазы и вехи
- **Scrum-мастер** — планирует спринты, церемонии, оценивает velocity команды
- **Риск-менеджер** — идентифицирует риски, разрабатывает стратегии митигации, выявляет зависимости

**Принципы работы:**

- **Явные I/O контракты** (строгая схема полей через Pydantic AI, чек-листы валидации), единый "контекст выполнения" с correlation ID.
- **Поддержка ADK**: агенты реализованы с возможностью выделения в удаленные сервисы через Agent Development Kit от Google; протоколы взаимодействия совместимы с ADK спецификациями.
- **Языковая изоляция**: каждый агент получает язык проекта в контексте и генерирует весь контент на этом языке.
- **Циклическое взаимодействие с промежуточным выводом**:
  1. Продукт-менеджер передаёт слово эксперту
  2. Эксперт задаёт вопросы с вариантами
  3. Пользователь отвечает
  4. Response Parser передаёт ответы **обратно эксперту**
  5. **Эксперт формирует текст по своей части**
  6. **Эксперт выводит текст в чат для ознакомления**
  7. **Продукт-менеджер интегрирует текст в основной документ** (частично или полностью)
  8. Продукт-менеджер передаёт слово следующему эксперту
- **Структурированные вопросы**: каждый эксперт задаёт 1-5 вопросов с пронумерованными вариантами ответов (a, b, c, d, e).
- **Гибкий формат ответов**: пользователь может отвечать свободным текстом, выбирать варианты (`"1.b, 2.c, 2.d"`) или комбинировать оба подхода.
- **Прерывание процесса**: пользователь может в любой момент прервать циклическое взаимодействие словами "устраивает" или обратиться к конкретному эксперту напрямую.
- **Строгое правило контекста**: агенты читают память только в рамках `project_id` и `language`; межпроектные запросы недоступны.
- **Версионирование документов**: каждая интеграция текста в документ создаёт новую версию для возможности отката.

### 5.4 Сервис эмбеддингов

- Одна модель эмбеддингов на уровне MVP для поддержания однородности поиска.
- Политики разбиения на фрагменты и фильтры (удаление стоп-сигналов, сжатие повторов), дедупликация перед записью в Vector Store.
- Контроль качества индекса: периодическая переиндексация "устаревших" фрагментов после значительных правок.

### 5.5 Vector Store (Qdrant) — Изоляция данных проекта и языка

- **Одна коллекция** с логическим разделением данных через фильтрацию payload.
- **Двойная изоляция:** все запросы выполняются только в контексте `project_id` И `language`.
- **Оптимизированная конфигурация** для сред с фильтрацией.

> Конфигурация HNSW и другие технические спецификации Qdrant приведены в этом разделе архитектурной документации.

#### Детали конфигурации Qdrant

Qdrant настроен для логической изоляции данных проектов через фильтрацию по payload. Подход: единая коллекция с обязательной фильтрацией по `project_id` и `language` на стороне сервера.

- Базовая модель разделения: одна коллекция, строгий серверный фильтр `project_id` + `language`
- Пример структуры payload (метаданные векторов):

```json
{
  "project_id": "string",
  "language": "string",
  "type": "knowledge | memory",
  "visibility": "private | public",
  "version": "string",
  "tags": ["array", "of", "strings"]
}
```

- HNSW для фильтрации по payload:

```json
{
  "hnsw_config": {
    "m": 0,
    "payload_m": 16
  }
}
```

- Индексация и защита:

  - обязательный payload-индекс по `project_id` и `language`
  - строгая фильтрация на сервере; клиенты не могут её обойти
  - составной фильтр: `project_id` AND `language` для всех запросов

- Оптимизация производительности:
  - локальность данных проекта (Qdrant 1.11+)
  - пакетное чтение для снижения I/O
  - адаптивные квоты на точки/запросы по проекту

### 5.6 Основное хранилище (артефакты и версии)

- Документы и их версии являются "истиной" для экспорта и отображения; память (Qdrant) является "индексом и контекстом" для рассуждений агентов.
- Линейное версионирование в MVP с метаданными (кто/когда/почему) для обеспечения объяснимости и быстрого отката.

### 5.7 Кэш/очередь (Redis)

- Очередь вычисления эмбеддингов; буферы против штормов во время пиков генерации; ключи контроля прогресса для SSE.
- Бюджеты токенов на проект; смягчение "шумных соседей" от агентов (ограничение параллелизма).

### 5.8 Наблюдаемость

- Сквозные трассировки: шаг пользователя → вызовы агентов → эмбеддинги → Qdrant/Основное хранилище → экспорт; единый correlation-id.
- Дашборды SLO: задержка генерации P50/P95, коэффициент успешного экспорта, ошибки поиска, процент "пустых" релевантных результатов.

### 5.9 Безопасность и конфиденциальность

- TLS повсюду; секреты только на сервере; принцип минимальных привилегий до уровня проекта.
- RBAC: владелец проекта, редактор, доступ только для просмотра (включая флаг общедоступного чтения для публикаций).
- Политики хранения: временные ограничения для логов с чувствительными фрагментами промптов/контекста; выборочная трассировка без персональных данных.

## 6) Модель памяти по проектам и языкам

**Подход:** единая коллекция Qdrant с логическим разделением через фильтрацию payload по проекту и языку.

**Принципы изоляции:**

- Все запросы строго в рамках контекста `project_id` И `language`.
- Фильтрация на стороне сервера — клиент не может обойти ограничения.
- Язык проекта определяется **через LLM** из первого сообщения пользователя и фиксируется навсегда (использование библиотек детектирования языка запрещено).
- Все агенты получают язык проекта в контексте и генерируют контент только на этом языке.
- Векторный поиск выполняется только по эмбеддингам на языке проекта.
- Оптимизированная конфигурация для производительности с составным индексом.

> Конфигурация HNSW и другие технические спецификации Qdrant документированы в этом файле

## 7) Масштабирование и производительность

- **Поиск**: составной индекс `project_id` + `language` обеспечивает стабильную скорость при росте числа проектов и языковых вариантов; оптимизация размещения векторов в Qdrant 1.11+ сокращает операции ввода-вывода.
- **Горизонтальный рост**: добавление узлов/шардов Qdrant; языковая изоляция не создаёт дополнительных накладных расходов благодаря payload-фильтрации.
- **Оркестрация**: ограничения параллелизма на агента и на проект; очереди эмбеддингов; стратегия отката при "узких местах"; мульти-агентные команды работают параллельно где возможно.
- **Языковая локализация**: определение языка происходит один раз при создании проекта (низкие накладные расходы); все последующие операции используют закешированное значение.
- **Экспорт**: формирование архива из активных версий без блокировки чтения всей истории; документы экспортируются на языке проекта.

## 8) Развертывание и окружения

### 8.1 Архитектура развертывания

**Frontend:** Запускается локально (Node.js/Vite) на порту 5200, не контейнеризирован для удобства разработки

**Backend и инфраструктура:** Контейнеризированы через Docker Compose

**Порты:**

- Frontend (локальный): 5200
- API: 5210
- PostgreSQL: 5220
- Qdrant: 5230
- Redis: 5240
- Nginx: 80, 443
- OpenTelemetry Collector: 4317, 4318, 8888

### 8.2 Компоненты развертывания

- **Окружения:** dev / stage / prod; идентичные артефакты контейнеров; единая модель эмбеддингов для всех в MVP (соответствует мультитенантному подходу)
- **Сетевые границы:** nginx с TLS, frontend через host.docker.internal:5200, приватные сети для Qdrant/Primary/Redis
- **Региональность:** по мере роста — региональные кластеры по запросу клиентов с учетом требований размещения данных

### 8.3 Локальный стек

```yaml
services:
  # Инфраструктура (контейнеризирована)
  - nginx: Reverse proxy и TLS терминация
  - api: FastAPI бэкенд
  - postgres: PostgreSQL 18 с UUID v7 и AIO
  - redis: Кэш и очереди
  - qdrant: Векторная база данных
  - otel-collector: Телеметрия

  # Frontend (локальный)
  - React/Vite на порту 5200 (управление пакетами только через pnpm)
```

### 8.4 Схема портов для локальной разработки

| Сервис     | Внешний порт | Внутренний порт | URL для доступа         |
| ---------- | ------------ | --------------- | ----------------------- |
| Frontend   | 5200         | 5200            | <http://localhost:5200> |
| API        | 5210         | 8000            | <http://localhost:5210> |
| PostgreSQL | 5220         | 5432            | localhost:5220          |
| Qdrant     | 5230         | 6333            | <http://localhost:5230> |
| Redis      | 5240         | 6379            | localhost:5240          |

### 8.5 Диаграмма архитектуры Docker

```mermaid
graph TB
    subgraph "Host Machine (localhost)"
        DEV[Developer]
        BROWSER[Web Browser\n:5200]
        API_CLIENT[API Client\n:5210]
        DB_CLIENT[DB Client\n:5220]
        QDRANT_UI[Qdrant Web UI\n:5230]
        REDIS_CLI[Redis CLI\n:5240]

    end

    subgraph "Docker Network"
        subgraph "Frontend Container"
            FRONTEND[React App\n:3000]
        end

        subgraph "Backend Container"
            API[FastAPI\n:8000]
        end

        subgraph "Infrastructure Containers"
            POSTGRES[PostgreSQL\n:5432]
            QDRANT[Qdrant\n:6333]
            REDIS[Redis\n:6379]

        end

        subgraph "Volumes"
            PG_VOL[(postgres_data)]
            QD_VOL[(qdrant_data)]
            RD_VOL[(redis_data)]

        end
    end

    DEV --> BROWSER
    DEV --> API_CLIENT
    DEV --> DB_CLIENT
    DEV --> QDRANT_UI
    DEV --> REDIS_CLI


    BROWSER -.5200:3000.-> FRONTEND
    API_CLIENT -.5210:8000.-> API
    DB_CLIENT -.5220:5432.-> POSTGRES
    QDRANT_UI -.5230:6333.-> QDRANT
    REDIS_CLI -.5240:6379.-> REDIS


    FRONTEND --> API
    API --> POSTGRES
    API --> QDRANT
    API --> REDIS


    POSTGRES -.-> PG_VOL
    QDRANT -.-> QD_VOL
    REDIS -.-> RD_VOL

```

### 8.6 Пример конфигурации окружения (фрагмент docker-compose)

```yaml
services:
  frontend:
    build: ./frontend
    ports: ["5200:3000"]

  api:
    build: ./backend
    ports: ["5210:8000"]
    environment:
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/jeex_idea
      - QDRANT_URL=http://qdrant:6333
      - REDIS_URL=redis://redis:6379

    depends_on:
      - postgres
      - qdrant
      - redis

  postgres:
    image: postgres:18-alpine
    ports: ["5220:5432"]
    environment:
      - POSTGRES_DB=jeex_idea
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=secure_password
    volumes: ["./postgres_data:/var/lib/postgresql/data"]

  qdrant:
    image: qdrant/qdrant:v1.15.4
    ports: ["5230:6333"]
    volumes: ["./qdrant_data:/qdrant/storage"]

  redis:
    image: redis:8.2-alpine
    ports: ["5240:6379"]
    volumes: ["./redis_data:/data"]
```

## 9) Критерии качества и SLO

- **Время шага**: P95 генерации одного документа ≤ N секунд при базовом лимите объема ввода.
- **Доступность**: API и SSE ≥ 99.9% в месяц.
- **Безопасность**: 100% запросов к памяти проходят с серверным фильтром; 0 инцидентов кросс-проектного доступа.

## 10) Риски и митигация

- **"Шумные соседи"**: квоты на точки/запросы/токены; при превышении — деградация качества (меньше контекста, отложенные эмбеддинги).
- **Галлюцинации/рассинхрон артефактов**: строгие шаблоны и чек-листы валидации, строгие I/O контракты между агентами, явные правила "что считается источником истины".
- **Длинные ответы**: SSE, буферизация, отображение промежуточных блоков, стабильное кэширование промптов.
- **Операционные накладные расходы**: использование одной коллекции минимизирует их на старте.

## 11) Схема базы данных

### 11.1 Диаграмма связей сущностей (ER)

```mermaid
erDiagram
    PROJECTS {
        uuid id PK
        string name
        string status
        int current_step
        string language
        timestamp created_at
        timestamp updated_at
    }

    DOCUMENT_VERSIONS {
        uuid id PK
        uuid project_id FK
        string document_type
        int version
        text content
        jsonb metadata
        uuid created_by
        timestamp created_at
    }

    AGENT_EXECUTIONS {
        uuid id PK
        uuid project_id FK
        string agent_type
        uuid correlation_id
        jsonb input_data
        jsonb output_data
        string status
        timestamp started_at
        timestamp completed_at
    }

    USERS {
        uuid id PK
        string email
        string name
        jsonb profile_data
        timestamp created_at
        timestamp last_login_at
    }

    EXPORTS {
        uuid id PK
        uuid project_id FK
        string status
        string file_path
        jsonb manifest
        timestamp created_at
        timestamp expires_at
    }

    PROJECTS ||--o{ DOCUMENT_VERSIONS : "has versions"
    PROJECTS ||--o{ AGENT_EXECUTIONS : "has executions"
    PROJECTS ||--o{ EXPORTS : "has exports"
    USERS ||--o{ PROJECTS : "owns"
```

### 11.2 SQL основных таблиц (пример)

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    profile_data JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    last_login_at TIMESTAMP
);

CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    current_step INTEGER DEFAULT 1 CHECK (current_step BETWEEN 1 AND 4),
    language VARCHAR(10) DEFAULT 'en' NOT NULL,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    document_type VARCHAR(50) NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE agent_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    agent_type VARCHAR(50) NOT NULL,
    correlation_id UUID NOT NULL,
    input_data JSONB,
    output_data JSONB,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    error_message TEXT,
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE TABLE exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    file_path TEXT,
    manifest JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '24 hours')
);
```

### 11.3 Стратегия индексации (пример)

```sql
CREATE INDEX idx_projects_created ON projects(created_at DESC);

CREATE INDEX idx_documents_project_type ON document_versions(project_id, document_type);
CREATE INDEX idx_documents_project_version ON document_versions(project_id, version DESC);
CREATE INDEX idx_documents_created ON document_versions(created_at DESC);

CREATE INDEX idx_executions_project ON agent_executions(project_id, started_at DESC);
CREATE INDEX idx_executions_correlation ON agent_executions(correlation_id);
CREATE INDEX idx_executions_status ON agent_executions(status, started_at);

CREATE INDEX idx_exports_project ON exports(project_id);
CREATE INDEX idx_exports_expires ON exports(expires_at) WHERE status = 'completed';

CREATE INDEX idx_projects_user_status ON projects(created_by, status, updated_at DESC);
CREATE UNIQUE INDEX idx_documents_unique_version ON document_versions(project_id, document_type, version);
```
