"""PostgreSQL/pgvector persistence and cosine retrieval."""
import json
from typing import Any
import psycopg
from .models import Chunk


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        self.database_url = database_url
        self.dimensions = dimensions
        self.vector_type = f"vector({dimensions})"

    def create_schema(self) -> None:
        with psycopg.connect(self.database_url) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(f"""CREATE TABLE IF NOT EXISTS day6_chunks (
                strategy TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                source TEXT NOT NULL,
                page INTEGER NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                embedding {self.vector_type} NOT NULL,
                PRIMARY KEY (strategy, chunk_id)
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS day6_chunks_metadata_idx ON day6_chunks USING GIN (metadata)")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Replace one strategy atomically so re-ingestion cannot leave stale chunks.

        When re-ingesting changed source documents, remove obsolete chunks too.
        """
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have equal lengths")
        rows = []
        for chunk, vector in zip(chunks, vectors):
            if len(vector) != self.dimensions:
                raise ValueError(f"Expected {self.dimensions}-dimensional vectors")
            literal = "[" + ",".join(format(float(x), ".9g") for x in vector) + "]"
            rows.append((strategy, chunk.chunk_id, chunk.document_id, chunk.source, chunk.page,
                         chunk.text, json.dumps(chunk.metadata, ensure_ascii=False), literal))
        with psycopg.connect(self.database_url) as conn:
            conn.execute("DELETE FROM day6_chunks WHERE strategy = %s", (strategy,))
            if rows:
                with conn.cursor() as cur:
                    cur.executemany(
                        """INSERT INTO day6_chunks
                        (strategy, chunk_id, document_id, source, page, content, metadata, embedding)
                        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::vector)""", rows)

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Filter trusted metadata fields and rank by cosine similarity.

        Return chunk ID, text, score and metadata. Parameterize user-supplied values.
        """
        if top_k < 1:
            return []
        literal = "[" + ",".join(format(float(x), ".9g") for x in query_vector) + "]"
        if len(query_vector) != self.dimensions:
            raise ValueError(f"Expected {self.dimensions}-dimensional query vector")
        clauses = ["strategy = %s"]
        params: list[Any] = [literal, strategy]
        if filters:
            allowed = {"section", "chapter", "year", "version", "category", "audience", "language", "document_type"}
            unknown = set(filters) - allowed
            if unknown:
                raise ValueError(f"Unsupported metadata filter(s): {sorted(unknown)}")
            clauses.append("metadata @> %s::jsonb")
            params.append(json.dumps(filters, ensure_ascii=False))
        params.extend([literal, top_k])
        sql = f"""SELECT chunk_id, document_id, source, page, content, metadata,
                         1 - (embedding <=> %s::vector) AS score
                  FROM day6_chunks WHERE {' AND '.join(clauses)}
                  ORDER BY embedding <=> %s::vector LIMIT %s"""
        # Placeholder order follows SELECT vector, WHERE filters, ORDER BY vector, LIMIT.
        with psycopg.connect(self.database_url) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [{"chunk_id": r[0], "document_id": r[1], "source": r[2], "page": r[3],
                 "text": r[4], "metadata": r[5], "score": float(r[6])} for r in rows]
