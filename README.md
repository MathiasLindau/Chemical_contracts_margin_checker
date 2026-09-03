Chemical Contracts Margin Checker

A RAG-based contract analysis application for procurement and supply-chain use cases. The system helps users analyze chemical supply contracts, including pricing, volume commitments, surcharges, penalties, delivery terms, and contractual clauses.

Problem

Procurement teams often need to combine information from structured contract data with details buried in contract documents. Simple database queries are sufficient for some questions, while contractual clauses require semantic document retrieval. More complex questions require both.

This project therefore separates queries into three routes:

Structured — questions answerable from tabular contract data.
Unstructured — questions requiring information from contract text.
Hybrid — questions requiring both structured data and contract text.

Examples include:

Question	Route	Operation
Which contract has the highest breach penalty?	Structured	Ranking
Which contracts have an energy surcharge above 5%?	Structured	Filtering
What is the total potential penalty exposure?	Structured	Aggregation / Calculation
What happens if the supplier fails to deliver the agreed quantity?	Unstructured	Semantic Retrieval
What are the consequences of failing to meet the minimum volume commitment?	Unstructured	Semantic Retrieval
How do two contracts compare regarding price and breach penalties?	Hybrid	Comparison
Which contract offers the best price while having favorable payment terms?	Hybrid	Multi-hop / Comparison
Architecture

The pipeline follows:

User Question
      │
      ▼
   Router
      │
 ┌────┼─────────────┐
 ▼    ▼             ▼
Structured       Unstructured
   │                  │
   ▼                  ▼
 CSV / SQL       Contract Retrieval
   │                  │
   └────────┬─────────┘
            ▼
       Hybrid Path
            │
            ▼
      LLM Answer
            │
            ▼
        Response

Structured data is stored in PostgreSQL/CSV-based contract records, while contract documents are chunked and stored with embeddings for retrieval.

The retrieval layer evaluates three approaches:

Vector search using all-MiniLM-L6-v2
BM25 using minsearch
Hybrid retrieval combining vector and BM25 rankings using Reciprocal Rank Fusion
Evaluation

Evaluation is performed at separate stages rather than treating the RAG system as a single black box:

Route Evaluation

Measures whether the query is correctly classified as:

structured
unstructured
hybrid

Current evaluation:

Route Accuracy: 94.0%
47 / 50 correct
Retrieval Evaluation

Retrieval is evaluated independently using Hit@3, Full Hit@3 and MRR@3.

Current results:

VECTOR:
  Hit@3:      68.0%
  Full Hit@3: 60.0%
  MRR@3:      0.6300

BM25:
  Hit@3:      72.0%
  Full Hit@3: 66.0%
  MRR@3:      0.7200

HYBRID:
  Hit@3:      74.0%
  Full Hit@3: 66.0%
  MRR@3:      0.6733
Answer Evaluation

Answer quality is evaluated separately for each route.

For structured questions, deterministic CSV ground truth is used:

CORRECT
PARTLY_CORRECT
INCORRECT

For unstructured and hybrid questions, generated answers are evaluated against the relevant evidence:

RELEVANT
PARTLY_RELEVANT
NOT_RELEVANT

This separation makes it possible to distinguish routing, retrieval, and generation errors.

Query Generation

An evaluation dataset is generated with realistic variations in user phrasing, including informal questions, vague requests, comparisons, multi-step questions, cost-focused questions, volume questions, adder questions, and penalty-related questions.

Structured questions are tied to a specific CSV field and use deterministic ground truth rather than asking the LLM to calculate the expected answer.

Technology Stack
Python
OpenAI API
PostgreSQL
pgvector
Sentence Transformers
BM25 / minsearch
Pandas
JSON / CSV
Markdown contract documents
Project Structure
chemical-contracts-margin-checker/
│
├── data/
│   ├── chemical_contracts.csv
│   └── contracts/
│
├── evaluation_questions.json
├── evaluation_dataset.json
│
├── generate_questions.py
├── answer_test_questions.py
├── route_evaluation.py
├── retrieval_evaluation.py
├── evaluate_answer.py
│
└── README.md
Running the Project

Install the dependencies and configure the required environment variables, including the OpenAI API key and PostgreSQL connection.

The evaluation scripts can then be run independently:

python generate_questions.py
python answer_test_questions.py
python route_evaluation.py
python retrieval_evaluation.py
python evaluate_answer.py
Limitations

The retrieval results show that retrieval is still the main area for improvement. BM25 currently performs better than vector search on this evaluation dataset, while the hybrid approach achieves the highest Hit@3.

The evaluation dataset is also relatively small, so individual questions can have a noticeable impact on the reported metrics. Further improvements should therefore be validated against a larger and more diverse test set.

Future Work
Improve structured query handling and calculations.
Experiment with retrieval parameters and chunking strategies.
Improve hybrid ranking.
Expand the evaluation dataset.
Add more difficult multi-hop questions.
Build the final user interface for interactive contract analysis.



Retrieval Architecture

The query router determines which data source and retrieval method are needed:

Route	Retrieval	Example
Structured	CSV + Python/Pandas	Which contract has the lowest price?
Unstructured	BM25 + Vector Search + RRF → contract text	What happens if the supplier fails to deliver?
Hybrid	CSV/Pandas + BM25 + Vector Search + RRF	Which contract has the lowest price and what are its payment terms?
In short
Structured
→ CSV / Pandas

Unstructured
→ Contract Text / BM25 + Vector / RRF

Hybrid
→ CSV / Pandas + Contract Text / BM25 + Vector / RRF

Hybrid Search refers to BM25 + Vector Search.
Hybrid Route refers to structured data + contract text.