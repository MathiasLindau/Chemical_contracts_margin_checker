import os
import psycopg
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from openai import OpenAI

load_dotenv()

# Initialize clients & local embedding model
openai_client = OpenAI()
model = SentenceTransformer("all-MiniLM-L6-v2")
DB_CONN = "postgresql://postgres:password@localhost:5432/contracts_db"

def vec_to_str(vector):
    """Converts the NumPy array into the PostgreSQL vector format."""
    return "[" + ",".join(str(x) for x in vector) + "]"

def search_contracts(query, num_results=5):
    """Performs a vector search in PostgreSQL."""
    query_vector = model.encode(query)
    query_str = vec_to_str(query_vector)

    with psycopg.connect(DB_CONN) as conn:
        with conn.cursor() as cur:
            rows = cur.execute(
                """
                SELECT contract_id, chunk_text, 1 - (embedding <=> %s::vector) AS similarity
                FROM contract_chunks
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_str, query_str, num_results)
            ).fetchall()

    return [
        {"contract_id": r[0], "chunk_text": r[1], "similarity": r[2]}
        for r in rows
    ]

def build_prompt(query, search_results):
    """Builds the prompt from the question and retrieved contract chunks."""
    context_lines = []
    for r in search_results:
        context_lines.append(f"--- Contract: {r['contract_id']} (Similarity: {r['similarity']:.4f}) ---")
        context_lines.append(r["chunk_text"])
        context_lines.append("")
    
    context = "\n".join(context_lines)

    prompt = f"""You are a legal assistant. Answer the user's question using ONLY the provided contract context. 
If the exact information is not explicitly mentioned, summarize what IS related in the context or state clearly what details are missing instead of just saying "I don't know".

QUESTION: {query}

CONTEXT:
{context}
"""
    return prompt




def ask_margin_checker(query):
    """Executes the search, LLM call, and token tracking."""
    print(f"\n Searching for: '{query}'\n" + "-"*50)
    
    # 1. Retrieval (Search)
    search_results = search_contracts(query, num_results=3)
    
    print("Found Chunks:")
    for r in search_results:
        print(f"-> Contract {r['contract_id']} (Score: {r['similarity']:.4f})")
    print("-" * 50)
    
    # 2. Build prompt
    prompt = build_prompt(query, search_results)
    
    # 3. LLM query with token tracking
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You answer questions regarding contracts."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0
    )
    
    answer = response.choices[0].message.content
    usage = response.usage
    
    input_cost = (usage.prompt_tokens / 1_000_000) * 0.15
    output_cost = (usage.completion_tokens / 1_000_000) * 0.60
    total_cost = input_cost + output_cost

    print("MODEL ANSWER:")
    print(answer)
    print("\n" + "-"*50)
    print(f"📊 Token & Cost Statistics:")
    print(f"   - Input Tokens:  {usage.prompt_tokens}")
    print(f"   - Output Tokens: {usage.completion_tokens}")
    print(f"   - Total Cost:    ${total_cost:.6f}")

if __name__ == "__main__":
    # Test query
    test_query = "What are the regulations regarding termination notice and payment terms?"
    ask_margin_checker(test_query)