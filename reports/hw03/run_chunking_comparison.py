"""
HW3 Part 2 — Chunking Comparison Pipeline
Domain 2: Municipal Transit Incidents | SID4 = 1346

Compares three LlamaIndex chunking strategies (Token, Semantic, Sentence-Window)
against the 5 questions in questions.yaml, retrieving from the corpus in corpus/.

Usage:
    python3 run_chunking_comparison.py

Outputs:
    raw/token_results.json
    raw/semantic_results.json
    raw/sentence_window_results.json
    RUN_LOG.txt

Requires (install once):
    pip install llama-index llama-index-embeddings-huggingface sentence-transformers faiss-cpu numpy pandas pyyaml
"""

import json
import os
import sys
import time
import yaml
import numpy as np
import faiss

from llama_index.core import Document, VectorStoreIndex, StorageContext, Settings
from llama_index.core.node_parser import (
    SentenceSplitter,
    SemanticSplitterNodeParser,
    SentenceWindowNodeParser,
)
from llama_index.core.vector_stores import SimpleVectorStore
from llama_index.vector_stores.faiss import FaissVectorStore

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "corpus")
QUESTIONS_PATH = os.path.join(os.path.dirname(__file__), "questions.yaml")
OUT_DIR = os.path.join(os.path.dirname(__file__), "raw")
RUN_LOG_PATH = os.path.join(os.path.dirname(__file__), "RUN_LOG.txt")

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"  # small, fast, good quality on CPU
EMBED_DIM = 384  # bge-small-en-v1.5 output dimension
TOP_K = 3

log_lines = []


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    log_lines.append(line)


def load_corpus():
    """Load every .txt file in corpus/ as a LlamaIndex Document."""
    docs = []
    for fname in sorted(os.listdir(CORPUS_DIR)):
        if not fname.endswith(".txt"):
            continue
        path = os.path.join(CORPUS_DIR, fname)
        with open(path, "r", errors="replace") as f:
            text = f.read()
        docs.append(Document(text=text, metadata={"filename": fname}))
    log(f"Loaded {len(docs)} corpus documents from {CORPUS_DIR}")
    return docs


def load_questions():
    with open(QUESTIONS_PATH, "r") as f:
        data = yaml.safe_load(f)
    qs = data["questions"]
    log(f"Loaded {len(qs)} questions from {QUESTIONS_PATH}")
    return qs


def build_faiss_index(nodes, embed_model):
    """Embed nodes and build a FAISS-backed VectorStoreIndex."""
    faiss_index = faiss.IndexFlatL2(EMBED_DIM)
    vector_store = FaissVectorStore(faiss_index=faiss_index)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex(
        nodes, storage_context=storage_context, embed_model=embed_model
    )
    return index


def run_pipeline(name, node_parser, docs, questions, embed_model):
    log(f"--- Running pipeline: {name} ---")
    t0 = time.time()
    nodes = node_parser.get_nodes_from_documents(docs)
    log(f"[{name}] Produced {len(nodes)} chunks")

    index = build_faiss_index(nodes, embed_model)
    retriever = index.as_retriever(similarity_top_k=TOP_K)

    results = []
    for q in questions:
        qtext = q["question"].strip()
        retrieved = retriever.retrieve(qtext)
        retrieved_chunks = [
            {
                "rank": i + 1,
                "score": float(r.score) if r.score is not None else None,
                "source_file": r.node.metadata.get("filename", "unknown"),
                "text": r.node.get_content(),
            }
            for i, r in enumerate(retrieved)
        ]
        # simple automatic check: does any retrieved chunk come from an
        # expected source file for this question?
        expected_sources = set(q.get("source_files", []))
        retrieved_sources = set(c["source_file"] for c in retrieved_chunks)
        hit_expected_source = bool(expected_sources & retrieved_sources)

        results.append(
            {
                "question_id": q["id"],
                "question_type": q.get("question_type"),
                "question": qtext,
                "expected_answer": q.get("expected_answer", "").strip(),
                "expected_source_files": list(expected_sources),
                "retrieved_chunks": retrieved_chunks,
                "hit_expected_source_file": hit_expected_source,
            }
        )
        log(
            f"[{name}] {q['id']}: retrieved {len(retrieved_chunks)} chunks, "
            f"hit_expected_source={hit_expected_source}"
        )

    elapsed = time.time() - t0
    log(f"[{name}] Done in {elapsed:.1f}s, {len(nodes)} chunks total")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{name}_results.json")
    with open(out_path, "w") as f:
        json.dump(
            {
                "pipeline": name,
                "num_chunks": len(nodes),
                "elapsed_seconds": round(elapsed, 2),
                "top_k": TOP_K,
                "results": results,
            },
            f,
            indent=2,
        )
    log(f"[{name}] Saved results to {out_path}")
    return results


def main():
    log("=== HW3 Part 2 Chunking Comparison — starting run ===")
    log(f"Embedding model: {EMBED_MODEL_NAME}")

    docs = load_corpus()
    questions = load_questions()

    # Set up the embedding model globally (used by all three pipelines
    # for both chunking (semantic) and retrieval).
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL_NAME)
    Settings.embed_model = embed_model

    # --- Pipeline 1: Token-based chunking ---
    token_parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)
    run_pipeline("token", token_parser, docs, questions, embed_model)

    # --- Pipeline 2: Semantic chunking ---
    semantic_parser = SemanticSplitterNodeParser(
        buffer_size=1,
        breakpoint_percentile_threshold=95,
        embed_model=embed_model,
    )
    run_pipeline("semantic", semantic_parser, docs, questions, embed_model)

    # --- Pipeline 3: Sentence-window chunking ---
    sentence_window_parser = SentenceWindowNodeParser.from_defaults(
        window_size=3,
        window_metadata_key="window",
        original_text_metadata_key="original_text",
    )
    run_pipeline("sentence_window", sentence_window_parser, docs, questions, embed_model)

    log("=== All three pipelines complete ===")

    with open(RUN_LOG_PATH, "w") as f:
        f.write("\n".join(log_lines) + "\n")
    log(f"Run log written to {RUN_LOG_PATH}")


if __name__ == "__main__":
    main()