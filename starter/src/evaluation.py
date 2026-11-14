"""Evidence retrieval metrics; human coherence/grounding are separate audits."""
import re
from typing import Any


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", value.casefold()).split())


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Check gold source/page plus evidence text and preserve the retrieved trace.

    Accept any documented alternative gold evidence. Do not infer human grounding
    or chunk coherence labels from exact string match.
    """
    gold_sources = set(question.get("gold_source_ids", [question["gold_source_id"]]))
    gold_pages = question.get("gold_pages", [question["gold_page"]])
    if not isinstance(gold_pages, list):
        gold_pages = [gold_pages]
    evidence_options = question.get("evidence_quotes", [question["evidence_quote"]])
    if not isinstance(evidence_options, list):
        evidence_options = [evidence_options]
    normalized_evidence = [_normalize(q) for q in evidence_options if q]
    judged = []
    for result in hits:
        source_page_match = (result.get("source") in gold_sources
                             and result.get("page") in gold_pages)
        content = _normalize(result.get("text", ""))
        evidence_match = any(q in content for q in normalized_evidence if q)
        judged.append({**result, "source_page_match": source_page_match,
                       "evidence_match": evidence_match,
                       "evidence_hit": source_page_match and evidence_match})
    return {"id": question["id"], "split": question["split"],
            "question": question["question"], "filter": question.get("filter", {}),
            "hit_at_1": bool(judged and judged[0]["evidence_hit"]),
            "evidence_hit_at_3": any(row["evidence_hit"] for row in judged[:3]),
            "hits": judged[:3]}


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate retrieval counts without claiming answer-generation accuracy."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for trace in traces:
        groups.setdefault((trace["strategy"], trace["split"]), []).append(trace)
    summary = {}
    for (strategy, split), rows in sorted(groups.items()):
        summary[f"{strategy}/{split}"] = {
            "n": len(rows),
            "hit_at_1": sum(bool(row["hit_at_1"]) for row in rows),
            "evidence_hit_at_3": sum(bool(row["evidence_hit_at_3"]) for row in rows),
        }
    return summary
