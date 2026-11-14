"""Run the controlled A/B/C ingestion and retrieval experiment."""
import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_pdf
from .store import PgVectorStore

ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    """Run only against an explicit manifest and prevalidated benchmark."""
    load_dotenv(ROOT / ".env")
    manifest_path = ROOT / "data" / "manifest.json"
    questions_path = ROOT / "benchmark" / "questions.json"
    if not manifest_path.exists() or not questions_path.exists():
        raise FileNotFoundError(
            "Prepare data/manifest.json and benchmark/questions.json first; "
            "the benchmark must contain verified evidence and a fixed dev/test split."
        )
    manifest = _read_json(manifest_path)
    questions = _read_json(questions_path)
    if not isinstance(questions, list) or len(questions) < 20:
        raise ValueError("Benchmark must be a list containing at least 20 questions")
    if sum(q.get("split") == "dev" for q in questions) < 15 or sum(q.get("split") == "test" for q in questions) < 5:
        raise ValueError("Benchmark needs at least 15 dev and 5 test questions")
    if sum(bool(q.get("filter")) for q in questions) < 3 or not any(q.get("split") == "test" and q.get("filter") for q in questions):
        raise ValueError("Benchmark needs at least 3 metadata-filter questions, including one test question")
    required = {"id", "split", "question", "expected_answer", "gold_source_id", "gold_page", "evidence_quote"}
    for q in questions:
        missing = required - q.keys()
        if missing:
            raise ValueError(f"Question {q.get('id', '<unknown>')} missing fields: {sorted(missing)}")

    pages = []
    for document in manifest.get("documents", []):
        pdf_path = (ROOT / document["source_path"]).resolve()
        if not pdf_path.is_file() or ROOT.resolve() not in pdf_path.parents:
            raise ValueError(f"PDF path must exist inside starter/: {document.get('source_path')}")
        document_pages = load_pdf(pdf_path, document["source_id"], document["source_id"])
        for page in document_pages:
            for page_range in document.get("page_metadata_ranges", []):
                if page_range["first_page"] <= page.page <= page_range["last_page"]:
                    page.metadata.update({key: value for key, value in page_range.items()
                                          if key not in {"first_page", "last_page"}})
        pages.extend(document_pages)
    included = {(p.document_id, p.page) for p in pages if p.text and any(
        p.document_id == d["source_id"] and p.page in d.get("content_pages", [])
        for d in manifest["documents"])}
    if len(included) < 30:
        raise ValueError(f"Manifest counts only {len(included)} extracted content pages; at least 30 are required")
    selected_pages = [p for p in pages if (p.document_id, p.page) in included]
    embedder = MyEmbedder(os.environ.get("EMBEDDING_MODEL", ""))
    store = PgVectorStore(os.environ["DATABASE_URL"], embedder.dimensions)
    store.create_schema()

    configs = {
        "A": lambda page: fixed_size(page, size=500, overlap=50),
        "B": lambda page: by_paragraph(page, max_size=900),
        "C": lambda page: by_paragraph(page, max_size=900),
    }
    all_traces = []
    query_vectors = [embedder.embed_query(question["question"]) for question in questions]
    run_info = {"provider": "OpenAI", "model": embedder.model_name, "dimensions": embedder.dimensions,
                "metric": "cosine", "physical_pages": len(pages), "content_pages": len(included), "strategies": {}}
    paragraph_chunks = None
    paragraph_vectors = None
    for strategy, make_chunks in configs.items():
        started = time.perf_counter()
        if strategy == "C":
            chunks, vectors = paragraph_chunks, paragraph_vectors
        else:
            chunks = [chunk for page in selected_pages for chunk in make_chunks(page)]
            vectors = embedder.embed_documents([chunk.text for chunk in chunks])
            if strategy == "B":
                paragraph_chunks, paragraph_vectors = chunks, vectors
        store.upsert(strategy, chunks, vectors)
        query_rows = []
        for question, query_vector in zip(questions, query_vectors):
            active_filter = question.get("filter", {}) if strategy == "C" else {}
            hits = store.search(strategy, query_vector, top_k=3, filters=active_filter)
            trace = evaluate_query(question, hits)
            trace["strategy"] = strategy
            query_rows.append(trace)
        elapsed = time.perf_counter() - started
        all_traces.extend(query_rows)
        run_info["strategies"][strategy] = {"chunk_count": len(chunks), "elapsed_seconds": round(elapsed, 3)}

    output = ROOT / "results"
    _write_json(output / "retrieval_traces.json", all_traces)
    _write_json(output / "retrieval_summary.json", {"run": run_info, "metrics": summarize(all_traces)})
    print(f"Saved {len(all_traces)} retrieval traces to {output}")
    print(json.dumps(summarize(all_traces), indent=2))


if __name__ == "__main__":
    main()
