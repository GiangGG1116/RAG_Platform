# RAG Microservice Platform

Production-grade Retrieval-Augmented Generation (RAG) platform built with microservice architecture.

## Architecture

```mermaid
flowchart TB
    %% Actors
    User(("User / Client App"))
    
    %% Edge Layer
    subgraph Edge ["Edge Layer"]
        Gateway{"API Gateway"}
        RedisAuth[("Redis\n(Rate Limiting & Auth)")]
        Gateway -. "Check Limits" .-> RedisAuth
    end
    
    %% Microservices Layer
    subgraph Services ["Core Microservices"]
        Ingestion["Ingestion Service\nLangGraph: Chunking"]
        Retrieval["Retrieval Service\nLangGraph: RAG Logic"]
        LLM["LLM Service\n\nOrchestrator"]
        Worker["Embedding Worker\n(Background Async)"]
    end
    
    %% Data Layer
    subgraph Data ["Data & Infrastructure"]
        Postgres[("PostgreSQL\n(pgvector)")]
        RabbitMQ[("RabbitMQ\n(Message Broker)")]
        RedisMem[("Redis\n(Chat Memory)")]
    end
    
    %% External
    subgraph External ["External Providers"]
        OpenAI("OpenAI API\nLocal LLMs")
    end
    
    %% Connections
    User == "REST / HTTP" ==> Gateway
    
    %% Gateway to Services
    Gateway == "POST /documents" ==> Ingestion
    Gateway == "POST /query" ==> Retrieval
    
    %% Ingestion Flow
    Ingestion -- "1. Publish Document" --> RabbitMQ
    RabbitMQ -. "2. Async Consume" .-> Worker
    Worker -- "3. Request Embeddings" --> LLM
    Worker -- "4. Store Vectors" --> Postgres
    
    %% Retrieval Flow
    Retrieval -- "1. Load Chat History" --> RedisMem
    Retrieval -- "2. Embed Query" --> LLM
    Retrieval -- "3. Vector Search (Top-K)" --> Postgres
    Retrieval -- "4. Generate Final Answer" --> LLM
    
    %% LLM Outbound
    LLM -. "API Calls" .-> OpenAI
    
    %% Styles
    classDef user fill:#e1f5fe,stroke:#0288d1,stroke-width:2px,color:#01579b
    classDef gateway fill:#ffe0b2,stroke:#f57c00,stroke-width:2px,color:#e65100
    classDef svc fill:#e8f5e9,stroke:#388e3c,stroke-width:2px,color:#1b5e20
    classDef worker fill:#fce4ec,stroke:#c2185b,stroke-width:2px,color:#880e4f
    classDef db fill:#ede7f6,stroke:#5e35b1,stroke-width:2px,color:#311b92
    classDef ext fill:#eceff1,stroke:#607d8b,stroke-width:2px,color:#263238,stroke-dasharray: 5 5
    
    class User user;
    class Gateway gateway;
    class Ingestion,Retrieval,LLM svc;
    class Worker worker;
    class Postgres,RabbitMQ,RedisAuth,RedisMem db;
    class OpenAI ext;
```

| Service               | Port | Description                                        |
| --------------------- | ---- | -------------------------------------------------- |
| **API Gateway** | 8000 | Central entry point, auth, rate limiting           |
| **Ingestion**   | 8001 | Document upload, chunking (LangGraph pipeline)     |
| **Retrieval**   | 8002 | Hybrid search, RAG generation (LangGraph pipeline) |
| **LLM Service** | 8003 | LLM orchestration (OpenAI / Local)                 |
| **Worker**      | —   | Async embedding generation via RabbitMQ            |


## Quick Start

### Prerequisites

- Docker & Docker Compose
- (Optional) `kubectl` for K8s deployment

### 1. Clone & Configure

```bash
cd rag_micro
cp .env.example .env
# Edit .env with your OPENAI_API_KEY (or use LLM_PROVIDER=local)
```

### 2. Start All Services

```bash
# Core services only
make up

# With observability stack (Prometheus, Grafana, Loki)
make up-full
```

### 3. Verify

```bash
# Check all services
make ps

# Health check
curl http://localhost:8000/health

# Readiness check (all dependencies)
curl http://localhost:8000/ready
```

### 4. Try It Out

```bash
# Ingest a document
curl -X POST http://localhost:8000/api/v1/documents \
  -H "Content-Type: application/json" \
  -H "X-API-Key: default-api-key-change-me" \
  -d '{
    "title": "RAG Overview",
    "content": "RAG combines retrieval with generation for accurate answers...",
    "doc_type": "text"
  }'

# Query with RAG
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: default-api-key-change-me" \
  -d '{
    "question": "What is RAG?",
    "top_k": 5
  }'
```

## Observability

| Tool                | URL                    | Credentials                    |
| ------------------- | ---------------------- | ------------------------------ |
| Grafana             | http://localhost:3001  | admin / admin                  |
| Prometheus          | http://localhost:9090  | —                             |
| RabbitMQ Management | http://localhost:15672 | rag_user / rag_secret_password |

## Key Features

### LangGraph Pipelines

- **Ingestion Pipeline**: `validate → extract → chunk → publish → update_status`
- **RAG Pipeline**: `analyze_query → retrieve → rerank → generate → cite`

## Kubernetes Deployment

```bash
# Apply all manifests
make k8s-apply

# Delete all resources
make k8s-delete
```

## Testing

```bash
make test          # All tests
make test-unit     # Unit tests only
make lint          # Ruff linter
make format        # Ruff formatter
```

