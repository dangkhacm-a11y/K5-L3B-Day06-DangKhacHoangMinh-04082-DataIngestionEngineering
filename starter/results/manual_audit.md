# Retrieval and manual audit notes

## Run details

- Corpus: 61 physical PDF pages, all counted as content pages.
- Embedding: OpenAI `text-embedding-3-small`, 1536 dimensions.
- Vector store: PostgreSQL 16 + pgvector 0.8.7, cosine distance.
- Benchmark: 15 dev and 5 test questions. The questions and exact evidence excerpts are in `benchmark/questions.json`.
- Full top-3 traces: `results/retrieval_traces.json`.
- Automated retrieval summary: `results/retrieval_summary.json`.

## Retrieval metrics

| Strategy | Split | Hit@1 | Evidence Hit@3 | Chunks | Elapsed seconds |
|---|---|---:|---:|---:|---:|
| A fixed 500 chars, overlap 50 | dev | 9/15 | 10/15 | 407 | 8.002 |
| A fixed 500 chars, overlap 50 | test | 3/5 | 3/5 | 407 | 8.002 |
| B paragraphs, maximum 900 chars | dev | 9/15 | 11/15 | 221 | 4.567 |
| B paragraphs, maximum 900 chars | test | 4/5 | 4/5 | 221 | 4.567 |
| C B plus chapter filter | dev | 9/15 | 11/15 | 221 | 1.108 |
| C B plus chapter filter | test | 4/5 | 4/5 | 221 | 1.108 |

The C timing excludes document embedding because C reused B's identical chunks and vectors. It is therefore not a full independent ingest-time comparison. API token usage and dollar cost were not captured in this run.

## Metadata audit

- Test top-3 records with source, physical page, and chapter metadata complete and valid: 15/15.
- All six filtered questions used metadata values present in the corpus.
- C returned records satisfying the requested chapter filter: 18/18 top-3 records across the six filtered questions (including 15/15 test records).
- B and C returned the same top-3 page IDs for each filtered query. The filter enforced scope but did not change these rankings because B's unfiltered results already fell within the requested chapters.
- The chapter field is useful for coarse scoping. It cannot distinguish sections within a chapter.

## Chunk coherence audit

Sample rule: first chunk (ordinal 0) on each of the first ten physical content pages, applied identically to all strategies. Score: 0 = hard to understand because an idea or its subject is cut; 1 = partly understandable or missing context; 2 = self-contained and preserves the idea. C has the same chunk text as B, so its coherence scores match B.

| PDF page | A | B | C | Observation |
|---:|---:|---:|---:|---|
| 1 | 1 | 1 | 1 | A cuts off after the opening discussion; B carries more of the explanation but still stops before the example finishes. |
| 2 | 1 | 2 | 2 | A truncates the Five Whys example; B contains the example and its takeaway. |
| 3 | 1 | 1 | 1 | Both stop during a discussion of degree value. |
| 4 | 1 | 1 | 1 | Both stop before the benefits discussion is complete. |
| 5 | 1 | 1 | 1 | The page begins mid-list; both chunks retain some context. |
| 6 | 1 | 1 | 1 | Both contain the intellectual adjustment and only part of the social adjustment. |
| 7 | 1 | 1 | 1 | Survey questions are readable, but the final item continues beyond the chunk. |
| 8 | 1 | 1 | 1 | Figure prompts are readable; the graphics themselves are not in the extracted text. |
| 9 | 1 | 1 | 1 | Section introduction is understandable, but the chunk stops mid-paragraph. |
| 10 | 1 | 1 | 1 | Table entries are partly split across lines/chunks. |
| **Average / 2** | **1.0** | **1.1** | **1.1** | B improves one sampled page; the sample is small. |

## Grounding quality audit

These ratings review whether the returned top-3 collectively provide enough evidence to answer each test question: 0 = no evidence; 1 = partial evidence or missing context; 2 = enough evidence with traceable source. A multi-chunk answer does not change the automated Evidence Hit@3 definition; those cases are noted separately.

| Test question | A | B | C | Note |
|---|---:|---:|---:|---|
| q16 grit and perseverance | 2 | 2 | 2 | Correct chapter and page; B/C include the surrounding study context. |
| q17 GRIT acronym | 2 | 2 | 2 | The top result contains all four terms. |
| q18 information-choice research | 1 | 2 | 2 | A's relevant sentence is split at the fixed-window boundary; B/C return a coherent paragraph. |
| q19 learning-style recommendation | 1 | 1 | 1 | Related evidence appears across pages 42–43/top-3 chunks, but no single returned chunk contains the complete gold evidence excerpt. |
| q20 time management in college | 2 | 2 | 2 | The top result includes the comparison table and direct answer. |
| **Average / 2** | **1.6** | **1.8** | **1.8** | Five test questions only. |

## Method and limitations

The evidence-quote/page match was checked against extracted PDF text before the run. The manual coherence sample and top-3 grounding labels above were reviewed by the Codex assistant after retrieval; they are not independent human labels and should be checked by the student before submission. The coherence sample was selected after the run, so it is descriptive rather than a preregistered sample. Test size is only five questions, so these comparisons apply to this corpus and benchmark only. The assistant did not inspect the OpenAI billing dashboard; cost is unreported rather than assumed to be zero.
