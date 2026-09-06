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
                         BM25 + Vector     CSV IDs first,
                               |           then text only
                              RRF          on those IDs
                               |                 |
                        Cross-Encoder            |
                               |                 |
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
| Hybrid | CSV / Pandas + Contract Markdown | Structured CSV first, then the same text pipeline **restricted to those contract IDs** |

**Important terminology:**

- **Hybrid Search** = BM25 + Vector Search + RRF
- **Hybrid Route** = Structured data + contract text

---

## Contract Data

The project currently contains:

- **100 synthetic contracts** (CON-2023-0001 … 0100)
- **784 contract chunks**
- **6 markdown templates** (Texas master, German Rahmenvertrag, English supply, SIAC, call-off PO, REACH long form)

CON-2023-0001 … 0050 keep the same CSV values as the evaluation set. 0051 … 0100 add new products, customers, currencies (USD/EUR/GBP/CHF) and force-majeure wording. Markdown is no longer one cloned Texas shell.

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

On the **hybrid** route, structured retrieval runs first. Text search then uses **only chunks from those contract IDs**. A cheapest-price question that lands on `CON-2023-0007` will show payment-term and adder clauses from that deal as secondary sources, not random other agreements. If structured retrieval returns two IDs (a comparison), both contracts stay in the text pool.

If structured retrieval is an **aggregation or unfiltered lookup** with no contract IDs, text search is **skipped**. The model gets the CSV aggregate only, plus a note that other agreements were not searched. If the question names a product or customer, text search is limited to those rows. Filter/lookup hits are capped at 8 rows so the full catalog is never dumped into the prompt. Unstructured search is unchanged.

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

- Hit@3 — at least one valid contract ID is in the top 3
- Full Hit@3 — every valid ID is in the top 3
- MRR@3 — how high the first correct ID sits

Published results (`python evaluation/evaluate_retrieval.py`, 50 questions):

| Method | Hit@3 | Full Hit@3 | MRR@3 |
|---|---:|---:|---:|
| Vector | 64.0% | 58.0% | 0.6167 |
| BM25 | 72.0% | 66.0% | 0.7067 |
| Hybrid (RRF@3) | 72.0% | 66.0% | 0.6600 |

BM25 is the strongest of these three on this set. Many questions use the same wording as the contracts, so lexical match wins. Hybrid RRF matches BM25 on Hit@3 but loses on MRR@3: the weaker vector list sometimes pushes the right contract down. **There is no strong need to tune RRF first.** It is already doing its job as a *candidate pool* (top 10) for the Cross-Encoder, not as the final ranking.

### Measuring the reranker

The table above does **not** include the Cross-Encoder. The live app does: RRF top 10 → Cross-Encoder top 3.

The same script now reports a fourth row, **RERANK (RRF@10 + Cross-Encoder@3)**, with the same Hit@3 / Full Hit@3 / MRR@3 on `valid_contract_ids`. That is the right way to measure the reranker: keep the gold IDs, change only the ranking stage, compare to RRF@3.

Run it after ingest (loads `cross-encoder/ms-marco-MiniLM-L6-v2` on the first question):

```bash
python evaluation/evaluate_retrieval.py
```

If rerank Beat@3 / MRR@3 is close to BM25, the Cross-Encoder is recovering the RRF drop. If it is worse, the next lever is chunking or the hybrid ID filter, not RRF weights.

---

## Answer Evaluation

Answer quality is evaluated separately by route.

### Structured

Structured questions use deterministic contract data and are classified as:

- CORRECT
- PARTLY_CORRECT
- INCORRECT

Current result (stored dataset answers):

**20 / 20 correct — 100%**

### Unstructured

Unstructured answers are evaluated against contractual evidence:

- RELEVANT
- PARTLY_RELEVANT
- NOT_RELEVANT

Current result (stored dataset answers):

**14 / 14 relevant — 100%**

### Hybrid

Hybrid answers are evaluated against both structured values and contractual evidence.

Current result (stored dataset answers):

- **16 / 16 relevant — 100%**
- **0 / 16 partly relevant**
- **0 / 16 not relevant**

These numbers come from `python evaluation/evaluate_answer.py` (no `--live`). That judges the answers already stored in `evaluation/evaluation_dataset.json`. It is a check of the eval set, not of the running app. Use `--live` or the Streamlit UI for the pipeline.

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

After the app writes an answer, it can call the LLM again and ask whether that answer is relevant. That second call is the judge. It costs extra time and extra tokens.

`RAG_LLM_JUDGE=1` is the default in `.env.example`. Every Streamlit answer then gets a relevance label (`RELEVANT` / `PARTLY_RELEVANT` / `NON_RELEVANT`) stored in `query_logs`. Set `RAG_LLM_JUDGE=0` to skip it. `python evaluation/evaluate_answer.py --live` always runs the judge.

---

## Query Generation

`generate/generate_test_questions.py` and `generate/generate_test_answer.py` are the generators behind the evaluation files. They are **ok to keep**; they are not a live test of the app.

- The **published** set is `evaluation/evaluation_dataset.json` (50 items). Do not overwrite it unless you also re-check hybrid adder math.
- Questions: random mix of structured / unstructured / hybrid, with styles (informal, typos, comparison, and so on). Structured items ask for **one CSV field** and store deterministic ground truth. Hybrid items require **both** selected contracts plus CSV **and** Markdown.
- Answers: structured values come from the CSV (no LLM). Unstructured and hybrid answers are extracted from the supplied contracts only (`temperature=0`).
- Question generation uses `temperature=0.9` for phrasing variety. A “comparison” style on a structured item is still one field of one contract.
- Unstructured questions can still mention volume or adders when those lines appear in the Markdown. That is expected.
- 50 items is a small set; route mix is random, so counts are not balanced on every run.

Hybrid adder calculations in the checked-in dataset were checked against the CSV. Totals are `base_price * (1 + energy_adder_percentage/100 + raw_material_adder_percentage/100)`.

---

## Streamlit Application

The current frontend is built with **Streamlit**.

The application provides:

- natural-language contract questions
- automatic route classification
- answer generation
- source display
- retrieval scores
- response time
- token usage
- estimated API cost
- answer-quality feedback
- query history (last 10, with delete / clear)
- timestamps in `Europe/Berlin` (set `DISPLAY_TZ` to change)

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

Docker Compose starts Grafana with a **checked-in dashboard**, so a clone gets the same boards without exporting from a laptop:

- datasource: PostgreSQL (`query_logs` on `app_postgres`)
- dashboard JSON: `grafana/dashboards/query-monitoring.json`
- provisioning: `grafana/provisioning/`

Open http://localhost:3000 (user `admin`, password `admin` unless `GRAFANA_ADMIN_PASSWORD` is set). The home dashboard is **Query Monitoring**:

- total queries, average response time, total cost, average tokens
- queries by route
- answer quality (LLM judge)
- user feedback
- queries, response time, cost and tokens over time
- recent query table

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
- Sentence Transformers
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
│       └── CON-2023-0100.md
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
├── grafana/
│   ├── dashboards/
│   │   └── query-monitoring.json
│   └── provisioning/
│       ├── dashboards/
│       └── datasources/
│
├── src/
│   └── margin_checker/
│       ├── __init__.py
│       ├── db.py
│       ├── ingest.py
│       ├── rag.py
│       ├── rerank.py
│       ├── retrieval.py
│       ├── router.py
│       ├── structured.py
│       └── sources.py
│
├── tests/
│   ├── test_history_and_eval.py
│   ├── test_hybrid_restrict.py
│   ├── test_hybrid_scope.py
│   ├── test_rerank.py
│   └── test_sources.py
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

The first start waits for Postgres, creates the monitoring table, and ingests contract chunks (this downloads the embedding model and can take a few minutes). Later starts reuse `pgdata`, but ingest runs again if fewer than 100 distinct contract IDs are stored (so the new 100-contract set is picked up).

The Streamlit application is exposed on:

```text
http://localhost:8502
```

Grafana is exposed on:

```text
http://localhost:3000
```

Log in with `admin` / `admin`. The Query Monitoring dashboard is provisioned from the repo. If Grafana was already running with an old `grafana_data` volume, run `docker compose up -d grafana` after pulling so it reloads provisioning.

### 3. How to test this version

**Manual UI checks** (use the demo questions below):

1. Open http://localhost:8502
2. Ask a **structured** question: `Which contract has the lowest price?`
3. Ask an **unstructured** question: `What happens if the supplier fails to deliver the agreed quantity?`
4. Ask a **hybrid** question: `Which contract has the lowest price and what are its payment terms?`
5. Ask a **hybrid aggregation**: `What is the average base price and typical payment terms?` — structured numbers only; no random other agreements in secondary sources.

For each answer, confirm:

- the **Route** metric matches the intended route
- **Primary sources** list the contract IDs used in the answer
- on hybrid, **Secondary sources** are clauses from those same contract IDs (not unrelated agreements)
- the LLM judge label is stored (and shown) unless `RAG_LLM_JUDGE=0`
- response time, tokens, and cost are shown
- thumbs-up/down feedback can be saved
- the question appears in **Query History** (last 10) after refresh
- history times match local Berlin time (or `DISPLAY_TZ`)
- Delete removes one row; Clear history removes all logs

Then open http://localhost:3000 and confirm the Query Monitoring dashboard loads against Postgres.

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

Hybrid questions combine deterministic structured information with retrieved contractual evidence. After CSV retrieval, text search is limited to those contract IDs. Catalog-wide averages/sums/counts do not search every markdown file; they stay on the structured result unless the question names a product or customer.

### Separate evaluation stages

Routing, retrieval and answer generation are evaluated independently. This makes it easier to identify where errors originate.

---

## Limitations

The evaluation dataset is small (50 questions), so a few items move the percentages a lot.

**Retrieval.** BM25 already beats Hybrid RRF on MRR@3. RRF is still useful as a top-10 pool for the Cross-Encoder; retuning fusion weights is not the first fix. The published retrieval table is Vector / BM25 / RRF only until you run the new rerank row. Hybrid ID-filtering is in the live app but not in that retrieval script (the script still searches the full corpus so methods stay comparable).

**Reranker.** Six clause templates now vary the legal language. Identical Cross-Encoder scores should be less common than with the old single Texas shell, but similar logistics wording can still cluster.

**Speed.** The first question after a restart loads the bi-encoder and Cross-Encoder. Later questions reuse them, BM25, and cached chunks. `RAG_LLM_JUDGE=1` adds a second OpenAI call on every answer.

**Robustness.** Lookup no longer dumps the CSV. Hybrid aggregations with no contract ID no longer search the whole corpus. Remaining limits: Docker/Postgres is still required for vectors; there is no login; `rag.py` is still the long orchestration file; the 50-question eval set still covers only CON-2023-0001 … 0050.

After pulling this version, **re-ingest** so Postgres has the new 100 contracts (`docker compose up --build` or `uv run python -m src.margin_checker.ingest`). Ingest drops and rebuilds `contract_chunks` only; query history stays.

The contracts are synthetic. They are realistic for a prototype, not legal or commercial advice.

The future market-data integration is not part of the current pipeline.

---

## Future Development

Potential next steps include:

1. Connect market-data APIs.
2. Calculate dynamic contract margins from daily market inputs.
3. Improve structured query handling and calculations.
4. Experiment with retrieval parameters and chunking strategies.
5. Expand the evaluation dataset.
6. Add more difficult multi-hop questions.
7. Improve monitoring and alerting.
8. Add supply-chain risk and opportunity scoring.
9. Develop a production-ready user interface.

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

The system finds the matching CSV row(s), then searches only those contracts’ clauses for payment terms and related text.

A catalog-wide average does **not** search every markdown file. Name a product if you also need that deal’s clauses.

### 4. Evaluation

Inspect:

- route
- sources
- retrieval scores
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
    -> text search restricted to those contract IDs
    -> same BM25 + Vector + RRF + Cross-Encoder pipeline
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
