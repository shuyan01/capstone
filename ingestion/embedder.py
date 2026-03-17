"""
ingestion/embedder.py

Responsible for:
- Taking chunks from chunker.py
- Embedding each chunk using OpenAI text-embedding-3-small
- Storing embeddings + metadata into ChromaDB
- Supporting incremental ingestion (skip already-indexed chunks)

Usage (from other modules):
    from ingestion.embedder import embed_and_store
    embed_and_store(chunks)

Usage (full ingestion — run directly):
    python ingestion/embedder.py
"""

import os
import time
from tqdm import tqdm
from dotenv import load_dotenv

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

load_dotenv()


# ─────────────────────────────────────────
# Config  (reads from .env)
# ─────────────────────────────────────────

OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL",        "text-embedding-3-small")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR",     "./chroma_db")
COLLECTION_NAME    = os.getenv("CHROMA_COLLECTION_NAME", "resumes")

# Number of chunks to send to ChromaDB in one batch
# Larger = faster, but uses more memory
BATCH_SIZE = 100


# ─────────────────────────────────────────
# ChromaDB Client Setup
# ─────────────────────────────────────────

def get_chroma_collection():
    """
    Creates (or loads existing) ChromaDB collection.
    Data is persisted to disk — only need to ingest once.

    Returns:
        A ChromaDB collection object ready for add/query operations
    """
    embedding_fn = OpenAIEmbeddingFunction(
        api_key=OPENAI_API_KEY,
        model_name=EMBEDDING_MODEL,
    )

    # PersistentClient saves data to disk automatically
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    # get_or_create_collection:
    # - If collection exists -> load it (no re-embedding needed)
    # - If not -> create a new empty one
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},  # use cosine similarity for search
    )

    return collection


# ─────────────────────────────────────────
# Embed and Store
# ─────────────────────────────────────────

def embed_and_store(chunks: list[dict], reset: bool = False) -> None:
    """
    Embeds all chunks and stores them in ChromaDB.

    Args:
        chunks: List of chunk dicts from chunker.chunk_all_resumes()
        reset:  If True, clears the entire collection before ingesting.
                Use reset=True only when you want to re-index from scratch.
                Default is False — skips already-indexed chunks (safe to re-run).
    """
    if not chunks:
        print("[Embedder] No chunks to embed.")
        return

    collection = get_chroma_collection()

    # ── Optional: wipe and rebuild collection ──
    if reset:
        print(f"[Embedder] Resetting collection '{COLLECTION_NAME}'...")
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        client.delete_collection(COLLECTION_NAME)
        collection = get_chroma_collection()
        existing_ids = set()
    else:
        # Fetch existing IDs to skip re-embedding (incremental mode)
        existing = collection.get(include=[])
        existing_ids = set(existing["ids"])
        print(f"[Embedder] Already indexed: {len(existing_ids)} chunks — skipping those.")

    # ── Filter out already-indexed chunks ──────
    new_chunks = [c for c in chunks if c["chunk_id"] not in existing_ids]

    if not new_chunks:
        print("[Embedder] All chunks already indexed. Nothing to do.")
        return

    print(f"[Embedder] Embedding {len(new_chunks)} new chunks "
          f"(batch size = {BATCH_SIZE})...\n")

    # ── Batch insert into ChromaDB ──────────────
    total_batches = (len(new_chunks) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in tqdm(range(total_batches), desc="Embedding batches"):
        start = batch_num * BATCH_SIZE
        end   = start + BATCH_SIZE
        batch = new_chunks[start:end]

        # Prepare the four lists ChromaDB expects
        ids       = [c["chunk_id"]  for c in batch]
        documents = [c["text"]      for c in batch]   # text to embed
        metadatas = [                                  # filterable metadata fields
            {
                "resume_id": c["resume_id"],
                "category":  c["category"],
                "source":    c["source"],
                "section":   c["section"],
                "education_tags": ", ".join(c.get("education_tags", [])),
                "location_tags": ", ".join(c.get("location_tags", [])),
                "industry_tags": ", ".join(c.get("industry_tags", [])),
                "job_titles": ", ".join(c.get("job_titles", [])),
                "degree_subjects": ", ".join(c.get("degree_subjects", [])),
                "education_level": c.get("education_level", ""),
                "explicit_years": int(c.get("explicit_years", 0)),
            }
            for c in batch
        ]

        # Embedding happens automatically inside collection.add()
        try:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
        except Exception as e:
            print(f"\n[ERROR] Batch {batch_num + 1} failed: {e}")
            print("Waiting 5 seconds before retrying...")
            time.sleep(5)
            # Retry once
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )

    # ── Final summary ──────────────────────────
    final_count = collection.count()
    print(f"\n[Embedder] Done!")
    print(f"  New chunks embedded: {len(new_chunks)}")
    print(f"  Total in collection: {final_count}")


# ─────────────────────────────────────────
# Helper: check collection stats
# ─────────────────────────────────────────

def get_collection_stats() -> dict:
    """
    Prints and returns basic stats about what is stored in ChromaDB.
    Useful for verifying ingestion progress.
    """
    collection = get_chroma_collection()
    count = collection.count()

    print(f"\n[ChromaDB] Collection:   '{COLLECTION_NAME}'")
    print(f"[ChromaDB] Total chunks:  {count}")
    print(f"[ChromaDB] Persist dir:   {CHROMA_PERSIST_DIR}")

    return {"collection": COLLECTION_NAME, "total_chunks": count}


# ─────────────────────────────────────────
# Full Ingestion Entry Point
#
# Run this file directly to ingest ALL resumes:
#   python ingestion/embedder.py
#
# Steps:
#   1. Parse all resumes from CSV + PDF
#   2. Chunk all resumes into sections
#   3. Embed chunks and store in ChromaDB
#
# Estimated time:  5-10 minutes
# Estimated cost:  $0.50 - $1.00
# ─────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from ingestion.parser  import load_all_resumes
    from ingestion.chunker import chunk_all_resumes

    start_time = time.time()

    print("=" * 60)
    print("Full ingestion started")
    print("=" * 60)

    # ── Step 1: Parse all resumes ───────────────
    print("\n[Step 1/3] Parsing resumes...")
    resumes = load_all_resumes(
        csv_path   = "data/raw/Resume.csv",
        pdf_folder = "data/raw/pdfs",
    )
    print(f"Total resumes loaded: {len(resumes)}")

    # ── Step 2: Chunk all resumes ───────────────
    print("\n[Step 2/3] Chunking resumes...")
    chunks = chunk_all_resumes(resumes)
    print(f"Total chunks created: {len(chunks)}")

    # ── Step 3: Embed and store in ChromaDB ─────
    print("\n[Step 3/3] Embedding and storing in ChromaDB...")
    print("(Calling OpenAI API — please wait)\n")

    # reset=False: skip already-indexed chunks (safe to re-run if interrupted)
    # reset=True:  wipe everything and re-index from scratch
    embed_and_store(chunks, reset=False)

    # ── Completion summary ──────────────────────
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    print("\n" + "=" * 60)
    print(f"Full ingestion complete! Time taken: {minutes}m {seconds}s")
    print("=" * 60)

    get_collection_stats()
