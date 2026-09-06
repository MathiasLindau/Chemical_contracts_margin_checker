import os
import glob
from dotenv import load_dotenv

load_dotenv()

import psycopg
from sentence_transformers import SentenceTransformer
from tqdm.auto import tqdm

model = SentenceTransformer("all-MiniLM-L6-v2")

from src.margin_checker.db import DB_CONN

def init_db():
    """Initialisiert die Datenbank mit pgvector (384 Dimensionen für MiniLM)."""
    with psycopg.connect(DB_CONN) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("""
                DROP TABLE IF EXISTS contract_chunks;
                CREATE TABLE contract_chunks (
                    id SERIAL PRIMARY KEY,
                    contract_id TEXT,
                    chunk_text TEXT,
                    embedding VECTOR(384)
                );
            """)
            conn.commit()
    print("Datenbanktabellen erfolgreich mit 384-dim Vektoren initialisiert.")

def vec_to_str(vector):
    """Konvertiert ein NumPy-Array in das von pgvector benötigte String-Format."""
    return "[" + ",".join(str(x) for x in vector) + "]"

def chunk_markdown(file_path):
    """Parst die Markdown-Datei und teilt sie anhand der Überschriften (##) auf."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    contract_id = os.path.basename(file_path).replace(".md", "")
    sections = content.split("## ")
    chunks = []
    
    for section in sections:
        if not section.strip():
            continue
        chunk_text = "## " + section.strip()
        chunks.append({
            "contract_id": contract_id,
            "chunk_text": chunk_text
        })
        
    return chunks

def main():
    init_db()
    
    markdown_files = glob.glob("data/contracts/*.md")
    if not markdown_files:
        print("Keine Markdown-Verträge gefunden!")
        return

    all_chunks = []
    for file_path in markdown_files:
        chunks = chunk_markdown(file_path)
        all_chunks.extend(chunks)

    print(f"Insgesamt {len(all_chunks)} Chunks geladen. Erzeuge lokale Embeddings...")
    
    # Texte extrahieren für Batch-Embedding
    texts = [c["chunk_text"] for c in all_chunks]
    vectors = model.encode(texts, show_progress_bar=True)

    # In PostgreSQL speichern
    with psycopg.connect(DB_CONN) as conn:
        with conn.cursor() as cur:
            for chunk, vec in tqdm(zip(all_chunks, vectors), total=len(all_chunks)):
                cur.execute(
                    """
                    INSERT INTO contract_chunks (contract_id, chunk_text, embedding)
                    VALUES (%s, %s, %s::vector);
                    """,
                    (chunk["contract_id"], chunk["chunk_text"], vec_to_str(vec))
                )
            conn.commit()
            
    print(f"Ingestion abgeschlossen! {len(all_chunks)} lokale Vektoren in PostgreSQL gespeichert.")

if __name__ == "__main__":
    main()