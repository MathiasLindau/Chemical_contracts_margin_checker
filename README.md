# Chemical Contracts Margin Checker

A RAG-based contract analysis application for procurement and supply-chain use cases.

The system analyzes chemical supply contracts across **structured contract data** and **unstructured contract text**. It combines deterministic data analysis with document retrieval and LLM-based answer generation.

The longer-term concept is:

> **Contract + Market API = Dynamic Margin**

The goal is to connect contractual conditions with daily market inputs such as raw-material prices, oil prices, energy prices, container prices, and logistics costs to support better supply-chain opportunity and risk assessment.

---

## Problem

Procurement teams often need to combine information from structured contract data with details buried in contract documents.

Some questions can be answered deterministically from tabular data. Other questions require semantic retrieval from contractual clauses. More complex questions require both.

The system therefore separates queries into three routes:

- **Structured** — questions answerable from tabular contract data.
- **Unstructured** — questions requiring information from contract text.
- **Hybrid** — questions requiring both structured data and contract text.

### Example questions

| Question | Route | Operation |
|---|---|---|
| Which contract has the lowest price? | Structured | Ranking |
| Which contracts have an energy surcharge above 5%? | Structured | Filtering |
| What is the total potential penalty exposure? | Structured | Aggregation / Calculation |
| What happens if the supplier fails to deliver the agreed quantity? | Unstructured | Semantic Retrieval |
| What are the consequences of failing to meet the minimum volume commitment? | Unstructured | Semantic Retrieval |
| How do two contracts compare regarding price and breach penalties? | Hybrid | Comparison |
| Which contract has the lowest price and what are its payment terms? | Hybrid | Multi-source analysis |

---

## Architecture

```text
                         User Question
                               |
                               v
                         +-----------+
                         |   Router  |
                         +-----------+
                               |
              +----------------+----------------+
              |                |                |
              v                v                v
        Structured       Unstructured        Hybrid
              |                |                |
              v                v                v
        CSV / Pandas      Contract Text    CSV / Pandas
                               |                +
                               v          Contract Text
                         BM25 + Vector           |
                               |                 |
                              RRF                |
                               |                 |
                        Top 10 candidates        |
                               |                 |
                         Cross-Encoder           |
                               |                 |
                            Top 3                |
              |                |                 |
              +----------------+-----------------+
                               |
                               v
                         LLM Answer
                               |
                               v
                    Primary / Secondary sources
                               |
                               v
                       Evaluation / Logging
```

### Route architecture

| Route | Data source | Retrieval / analysis |
|---|---|---|
| Structured | CSV / Pandas | Deterministic filtering, ranking and calculations |
| Unstructured | Contract Markdown | BM25 + Vector + RRF (top 10) → Cross-Encoder (top 3) |
| Hybrid | CSV / Pandas + Contract Markdown | Structured analysis + the same text pipeline |

**Important terminology:**

- **Hybrid Search** = BM25 + Vector Search + RRF
- **Hybrid Route** = Structured data + contract text

---

## Contract Data

The project currently contains:

- **50 synthetic but realistically designed contracts**
- **300 contract chunks**
- **300 embeddings**
- **0 empty chunks**

Contracts contain fields such as:

- product
- base price
- volume commitments
- energy adders
- raw-material adders
- payment terms
- transport duration
- shelf life
- demurrage / free-container days
- breach penalties
- contractual clauses

The contracts are synthetic, but designed to represent realistic procurement and chemical supply-chain scenarios.

---

## Retrieval

The unstructured retrieval layer evaluates three approaches.

### Vector Search

Semantic retrieval using:

`all-MiniLM-L6-v2`

### BM25

Lexical retrieval using:

`minsearch`

### Hybrid Retrieval

BM25 and vector rankings are combined using **Reciprocal Rank Fusion (RRF)**.

This allows the system to benefit from both:

- semantic similarity
- exact contractual terminology and keyword matches

### Cross-Encoder reranking

RRF returns the top 10 text candidates. A Cross-Encoder then scores each `(question, chunk)` pair and keeps the top 3 for the LLM:

`cross-encoder/ms-marco-MiniLM-L-6-v2`

Structured retrieval is not reranked. The UI shows both the original RRF score and `reranker_score` on text sources.

The published retrieval table below does **not** include this Cross-Encoder. `evaluate_retrieval.py` still measures Vector, BM25 and RRF only.

Identical reranker scores (for example `-11.2868` on several contracts) are common here. Most contracts share the same clause template; only product, price and penalty values change. For a cost question, those text chunks are all weakly related, so the Cross-Encoder assigns almost the same strongly negative score. The useful contract then comes from the CSV and is shown as a **primary / structured** source. That is expected with the current chunking, not a display bug.

---

## Evaluation

Evaluation is performed at separate stages rather than treating the RAG system as a single black box.

### Ground Truth and Evidence

Ground truth is defined by the underlying contract data and supporting evidence.

For structured questions, expected values are controlled using the contract dataset.

For unstructured questions, the relevant contractual evidence defines what the answer should be based on.

For hybrid questions, both structured values and contractual evidence are used.

> The LLM-as-Judge does **not** create the ground truth. It evaluates whether the generated answer is consistent with the predefined ground truth and evidence.

---

## Route Evaluation

Route evaluation measures whether the query is correctly classified as:

- structured
- unstructured
- hybrid

Current evaluation:

**Route Accuracy: 94.0%**

**47 / 50 correct**

---

## Retrieval Evaluation

Retrieval is evaluated independently using:

- Hit@3
- Full Hit@3
- MRR@3

Current evaluation results:

| Method | Hit@3 | Full Hit@3 | MRR@3 |
|---|---:|---:|---:|
| Vector | 64.0% | 58.0% | 0.6167 |
| BM25 | 72.0% | 66.0% | 0.7067 |
| Hybrid | 72.0% | 66.0% | 0.6600 |

On the current evaluation dataset, BM25 performs strongly because many contract questions depend on exact contractual terminology. Hybrid RRF matches BM25 on Hit@3 but has a lower MRR@3, which means vector hits sometimes push the correct contract down the ranked list.

---

## Answer Evaluation

Answer quality is evaluated separately by route.

### Structured

Structured questions use deterministic contract data and are classified as:

- CORRECT
- PARTLY_CORRECT
- INCORRECT

Current result:

**20 / 20 correct — 100%**

### Unstructured

Unstructured answers are evaluated against contractual evidence:

- RELEVANT
- PARTLY_RELEVANT
- NOT_RELEVANT

Current result:

**14 / 14 relevant — 100%**

### Hybrid

Hybrid answers are evaluated against both structured values and contractual evidence.

Current result:

- **14 / 16 relevant — 87.5%**
- **2 / 16 partly relevant — 12.5%**
- **0 / 16 not relevant**

The evaluation separates routing, retrieval and generation errors so that each stage can be analyzed independently.

---

## LLM-as-Judge

The project uses an LLM-based judge as an additional evaluation layer.

The judge evaluates the generated answer against the predefined evidence and expected answer criteria.

This is intentionally separated from ground-truth creation:

```text
Contract Data + Evidence
          |
          v
     Ground Truth
          |
          +------------------+
          |                  |
          v                  v
     Generated Answer    LLM-as-Judge
          |                  |
          +--------->--------+
                    |
                    v
              Quality Result
```

The judge therefore provides an evaluation signal; it does not define what is correct.

In the Streamlit UI the judge is **off by default** so answers stay faster. Set `RAG_LLM_JUDGE=1` in `.env` to enable it on every request. `python evaluation/evaluate_answer.py --live` always runs the judge.

---

## Query Generation

The evaluation dataset contains realistic variations in user phrasing, including:

- informal questions
- vague requests
- comparisons
- multi-step questions
- cost-focused questions
- volume questions
- adder questions
- penalty-related questions

Structured questions are tied to specific CSV fields and use deterministic ground truth rather than asking the LLM to calculate the expected answer.

The project also includes evaluation questions with supporting evidence.

Hybrid adder calculations in the evaluation dataset were checked against the CSV. Totals are `base_price * (1 + energy_adder_percentage/100 + raw_material_adder_percentage/100)`.

---

## Streamlit Application

The current frontend is built with **Streamlit**.

The application provides:

- natural-language contract questions
- automatic route classification
- answer generation
- **Primary sources** (contract IDs cited in the answer)
- **Secondary sources** (other retrieved hits, with RRF and reranker scores on text chunks)
- response time, token usage and estimated API cost
- thumbs-up / thumbs-down feedback
- query history

The first question after a restart can take longer while the Cross-Encoder loads. Later questions reuse the loaded model, the BM25 index and the cached chunks.

Example application flow:

```text
Question
   |
   v
Router
   |
   +--> Structured
   |
   +--> Unstructured
   |
   +--> Hybrid
            |
            v
        Retrieval /
        Data Analysis
            |
            v
        LLM Answer
            |
            v
       Logging + Feedback
```

---

## Monitoring

Query-level information is stored in PostgreSQL.

The monitoring layer records information such as:

- question
- answer
- route
- response time
- prompt tokens
- completion tokens
- total tokens
- estimated cost
- LLM-as-Judge relevance
- relevance explanation
- user feedback

Grafana can be connected to PostgreSQL for monitoring dashboards such as:

- total queries
- queries by route
- answer quality
- queries per day
- response time over time

---

## Future Business Concept

The current system focuses on contract understanding.

The intended next step is to connect contracts with external market data.

For example, a contract may contain:

```text
Product: Polyethylene
Base Price: 1200 USD / metric ton

Energy Adder: 5%
Raw Material Adder: 10%

Minimum Monthly Volume: 50 tons
Maximum Monthly Volume: 100 tons
```

A future API could provide daily values for:

- raw-material prices
- oil prices
- energy prices
- container prices
- logistics costs
- other relevant market indicators

The system could then combine:

```text
Contract Terms
      +
Daily Market Inputs
      =
Updated Margin
```

This enables a future workflow in which procurement and supply-chain teams can assess:

- margin development
- contract profitability
- cost exposure
- supply-chain risks
- commercial opportunities
- contracts requiring attention

The long-term objective is to move from static contract analysis toward **dynamic, data-driven margin and risk monitoring** on a daily or weekly basis.

---

## Technology Stack

- Python
- OpenAI API
- Streamlit
- PostgreSQL
- pgvector
- Sentence Transformers (bi-encoder + Cross-Encoder reranker)
- BM25 / minsearch
- Pandas
- JSON / CSV
- Markdown contract documents
- Docker / Docker Compose
- Grafana

---

## Project Structure

```text
chemical-contracts-margin-checker/
│
├── app.py
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── run.sh
│
├── data/
│   ├── chemical_contracts.csv
│   └── contracts/
│       ├── CON-2023-0001.md
│       ├── ...
│       └── CON-2023-0050.md
│
├── evaluation/
│   ├── evaluate_answer.py
│   ├── evaluate_retrieval.py
│   ├── evaluate_route.py
│   ├── evaluation_dataset.json
│   └── evaluation_questions.json
│
├── generate/
│   ├── generate_contracts.py
│   ├── generate_test_answer.py
│   └── generate_test_questions.py
│
├── src/
│   └── margin_checker/
│       ├── __init__.py
│       ├── db.py
│       ├── ingest.py
│       ├── rag.py
│       ├── rerank.py
│       ├── retrieval.py
│       └── router.py
│
├── tests/
│   └── test_rerank.py
│
├── pyproject.toml
├── uv.lock
├── .env.example
└── README.md
```

---

## Running the Project

### 1. Configure environment variables

Copy the example file and add your OpenAI key:

```bash
cp .env.example .env
```

The example values match `docker-compose.yml` (`password` for Postgres). Do not commit `.env` to GitHub.

`.env` can use `localhost` for local scripts. Docker Compose overrides `DB_CONN` inside the app container so it still reaches the `app_postgres` service.

### 2. Start the application

```bash
docker compose up --build
```

The first start waits for Postgres, creates the monitoring table, and ingests contract chunks (this downloads the embedding model and can take a few minutes). Later starts reuse the existing `pgdata` volume.

The Streamlit application is exposed on:

```text
http://localhost:8502
```

Grafana is exposed on:

```text
http://localhost:3000
```

### 3. How to test this version

**Manual UI checks** (use the demo questions below):

1. Open http://localhost:8502
2. Ask a **structured** question: `Which contract has the lowest price?`
3. Ask an **unstructured** question: `What happens if the supplier fails to deliver the agreed quantity?`
4. Ask a **hybrid** question: `Which contract has the lowest price and what are its payment terms?`

For each answer, confirm:

- the **Route** metric matches the intended route
- **Primary sources** list the contract IDs used in the answer
- **Secondary sources** list other retrieved text hits (RRF and Reranker scores)
- response time, tokens, and cost are shown
- thumbs-up/down feedback can be saved
- the question appears in **Query History** after refresh

Local Streamlit (`streamlit run app.py`) is at http://localhost:8501. Docker Compose publishes the app at http://localhost:8502.

**Automated evaluations** (need `.env` with `OPENAI_API_KEY` and `DB_CONN` pointing at reachable Postgres):

```bash
# Route classification using the production router
python evaluation/evaluate_route.py

# Retrieval quality (Postgres must already contain ingested chunks)
python evaluation/evaluate_retrieval.py

# Judge stored dataset answers (does not call the live RAG pipeline)
python evaluation/evaluate_answer.py

# Judge live RAG answers against the dataset evidence
python evaluation/evaluate_answer.py --live
```

Without `--live`, answer evaluation scores the answers already stored in `evaluation/evaluation_dataset.json`. That is useful for dataset quality, but it is **not** a test of the running app. Use `--live` or the Streamlit UI to test this version of the pipeline.

### 4. Local run without Docker (optional)

```bash
uv sync
uv run python -m src.margin_checker.ingest
uv run streamlit run app.py
```

Postgres with pgvector must already be running, and `DB_CONN` must use `localhost`.

---

## Design Decisions

### Separate routing from retrieval

The router first determines which information sources are required. This prevents every query from unnecessarily executing all retrieval paths.

### Deterministic structured analysis

Structured questions are answered from contract data rather than relying on semantic retrieval for numerical filtering, ranking and aggregation.

### Evidence-based unstructured analysis

Contractual questions use retrieved document chunks as evidence for the generated answer.

### Hybrid route

Hybrid questions combine deterministic structured information with retrieved contractual evidence.

After the answer is generated, **primary sources** are the retrieved rows whose contract IDs appear in the answer. **Secondary sources** are the other hits. This is display/attribution, not a second retrieval stage.

### Separate evaluation stages

Routing, retrieval and answer generation are evaluated independently. This makes it easier to identify where errors originate.

---

## Limitations

The current evaluation dataset is relatively small, so individual questions can have a noticeable impact on the reported metrics.

Retrieval is still an important area for improvement. BM25 currently performs strongly on the evaluation dataset. Hybrid RRF does not beat BM25 on MRR@3. The Cross-Encoder is not yet part of `evaluate_retrieval.py`.

Hybrid answers often cite a **structured** CSV row while secondary text chunks look unrelated. Restricting text search to the structured contract IDs would reduce that noise.

Identical Cross-Encoder scores on secondary chunks usually mean those templates are equally weakly related to the question, not that ranking is broken.

The contracts are synthetic rather than real-world commercial contracts. They are designed to be realistic for prototyping and evaluation, but they should not be interpreted as legal or commercial advice.

Grafana is started by Docker Compose but dashboards are not pre-provisioned.

The future market-data integration is a planned extension and is not yet part of the current margin calculation pipeline.

---

## Future Development

Potential next steps include:

1. Connect market-data APIs.
2. Calculate dynamic contract margins from daily market inputs.
3. Improve structured query handling and calculations.
4. Experiment with retrieval parameters and chunking strategies.
5. Restrict hybrid text retrieval to structured contract IDs.
6. Include the Cross-Encoder in retrieval evaluation.
7. Expand the evaluation dataset.
7. Add more difficult multi-hop questions.
8. Improve monitoring and alerting.
9. Add supply-chain risk and opportunity scoring.
10. Develop a production-ready user interface.

---

## Demo Flow

A typical demonstration can follow this sequence:

### 1. Structured question

Ask for a numerical or ranking result from contract data.

Example:

> Which contract has the lowest price?

The system uses the structured route.

### 2. Unstructured question

Ask about a contractual clause.

Example:

> What happens if the supplier fails to deliver the agreed quantity?

The system retrieves relevant contract text using BM25 + vector search + RRF, then reranks with the Cross-Encoder.

### 3. Hybrid question

Combine numerical contract information with contractual terms.

Example:

> Which contract has the lowest price and what are its payment terms?

The system combines structured analysis with reranked contract-text retrieval. Primary sources should match the contract IDs in the answer.

### 4. Evaluation

Inspect:

- route
- primary vs secondary sources
- retrieval / reranker scores
- response time
- token usage
- cost
- answer relevance
- user feedback

---

## Summary

This project demonstrates a modular RAG architecture for chemical contract analysis.

The core architecture separates:

```text
Structured
    -> CSV / Pandas

Unstructured
    -> Contract Text
    -> BM25 + Vector + RRF (top 10)
    -> Cross-Encoder (top 3)

Hybrid
    -> CSV / Pandas
    -> Contract Text (same text pipeline)
    -> Primary sources = IDs cited in the answer
```

The current prototype focuses on contract understanding and evidence-based answers.

The intended evolution is:

```text
Contract
   +
Market API
   =
Dynamic Margin
   +
Supply-Chain Risk / Opportunity
```

This creates a path from static contract analysis toward continuously updated procurement and supply-chain decision support.
