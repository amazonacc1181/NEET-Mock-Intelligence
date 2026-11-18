from __future__ import annotations

import base64
import json
import mimetypes
import re
import time
from pathlib import Path
from typing import Any

import httpx

from core import config

RELATIONSHIP_LABELS = {
    "EXACTLY_SAME": "Exactly same",
    "SUBSTANTIALLY_SAME_DATA_DIFFERENCE": "Substantially same — data/details changed",
    "SAME_PATTERN_OR_SOLUTION_METHOD": "Same question pattern / solution method",
    "CONCEPTUALLY_SAME_DIFFERENT_APPLICATION": "Conceptually same — different application",
    "SAME_NCERT_SOURCE_OR_KNOWLEDGE": "Same NCERT source / knowledge",
    "SAME_DIAGRAM_OR_EXPERIMENTAL_SETUP": "Same diagram / graph / experiment / data representation",
    "SAME_MULTI_CONCEPT_COMBINATION": "Same multi-concept combination / reasoning chain",
}

ANALYSIS_SYSTEM = """You are an exceptionally careful NEET (India) question analyst. Extract facts from the supplied question; do not invent missing text, options, answer keys, chapter names, NCERT line numbers, or diagrams. Distinguish what is explicitly present from your inference. When a solution is not supplied, you may solve independently but must label it AI-generated and unverified. If unsure, say so. Return valid JSON only."""

ANALYSIS_SCHEMA_INSTRUCTIONS = """Return this JSON object for EACH input question, preserving the exact id and question_number:
{
  "id": "exact input id",
  "question_number": 1,
  "subject": "Physics|Chemistry|Biology|Uncertain",
  "chapter": "best-fit NCERT chapter or Uncertain",
  "topic": "topic",
  "subtopic": "subtopic or null",
  "core_concept": "one precise sentence",
  "concept_tags": ["..."],
  "question_type": "Numerical|Conceptual|NCERT fact|Assertion-reason|Match the following|Statement-based|Diagram-based|Reaction-based|Other",
  "difficulty": "Easy|Moderate|Difficult|Uncertain",
  "formulae_or_laws": ["..."],
  "reactions_or_mechanisms": ["..."],
  "ncert_anchor": "specific chapter/paragraph/figure/table if confidently identifiable, otherwise Uncertain",
  "answer": "option/value if confidently solvable, otherwise Uncertain",
  "solution_steps": ["step 1", "step 2"],
  "solution_origin": "Provided in source|AI-derived, unverified|Not solved",
  "solution_confidence": 0,
  "common_traps": ["..."],
  "extraction_warnings": ["..."],
  "short_search_text": "compact semantic description for retrieval"
}
Return a JSON object with shape {"questions": [ ... ]}. Do not omit a question. Never claim that an AI-derived answer is an official answer key."""

MATCH_SYSTEM = """You are a strict cross-paper NEET question relationship examiner. Compare a NEET question against candidate mock questions using the full question, options, diagrams/page evidence when supplied, and their concept analyses. Chapter overlap alone is NOT a meaningful match. Only return matches for which specific evidence exists in the supplied text or images. Do not invent source wording, question numbers, or shared data. Multiple mock questions may match one NEET question. It is acceptable and often correct to return no matches. Return valid JSON only."""

MATCH_SCHEMA_INSTRUCTIONS = f"""Classify each valid relationship into exactly one primary category, choosing the strongest applicable category:
{json.dumps(RELATIONSHIP_LABELS, ensure_ascii=False, indent=2)}

Priority/definitions:
- EXACTLY_SAME: essentially the same question and required reasoning/answer; harmless formatting or option-order differences allowed.
- SUBSTANTIALLY_SAME_DATA_DIFFERENCE: same question structure and solution path; only numbers, names, values, or minor data/details changed.
- SAME_PATTERN_OR_SOLUTION_METHOD: same problem template and reasoning steps, but asks a different quantity or has a meaningful structural variation.
- CONCEPTUALLY_SAME_DIFFERENT_APPLICATION: same underlying concept/principle, but a different application, setup, or context.
- SAME_NCERT_SOURCE_OR_KNOWLEDGE: both test the same specific NCERT statement, fact, reaction, figure, table, example, or passage, even if the question asked differs.
- SAME_DIAGRAM_OR_EXPERIMENTAL_SETUP: same distinctive diagram, graph, apparatus, experiment, table or data representation is reused/adapted.
- SAME_MULTI_CONCEPT_COMBINATION: substantially the same combination and sequence of two or more concepts, with a similar reasoning chain.

Return JSON:
{{
  "neet_question_id": "exact id",
  "matches": [{{
    "mock_question_id": "exact candidate id",
    "relationship": "one category key above",
    "confidence": 0,
    "rationale": "specific comparison; explain why it qualifies",
    "shared_concept": "precise shared concept/source",
    "differences": "specific differences, not generic wording",
    "solution_comparison": "same/different method and why",
    "evidence": ["short quoted or pinpointed evidence from NEET question", "corresponding evidence from mock question"]
  }}],
  "no_match_reason": "why no candidates qualify, if matches is empty"
}}
Confidence is 0-100 and should reflect evidence, not fluency. Return only genuine matches. Include every credible match, but no weak chapter-only overlap. Never refer to a candidate not supplied."""


class LLMError(RuntimeError):
    pass


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: int | None = None):
        if not base_url or not model:
            raise LLMError("LLM is not configured. Set LLM_BASE_URL and LLM_MODEL in .env.")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "local-no-key"
        self.model = model
        self.timeout = timeout or config.LLM_TIMEOUT

    def _endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return self.base_url + "/chat/completions"

    def chat(self, messages: list[dict[str, Any]], max_tokens: int = 7000, json_mode: bool = True) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        last_error = None
        for attempt in range(config.LLM_MAX_RETRIES):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(self._endpoint(), headers=headers, json=payload)
                if response.status_code in (400, 404, 422) and "response_format" in payload:
                    payload.pop("response_format", None)
                    with httpx.Client(timeout=self.timeout) as client:
                        response = client.post(self._endpoint(), headers=headers, json=payload)
                if response.status_code == 429 or response.status_code >= 500:
                    wait = min(60, 2 ** attempt * 2)
                    last_error = f"HTTP {response.status_code}: {response.text[:700]}"
                    time.sleep(wait)
                    continue
                if response.is_error:
                    raise LLMError(f"Provider returned HTTP {response.status_code}: {response.text[:1200]}")
                body = response.json()
                content = body["choices"][0]["message"].get("content", "")
                if isinstance(content, list):
                    content = "\n".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
                if not str(content).strip():
                    raise LLMError("The model returned an empty response.")
                return str(content)
            except LLMError:
                raise
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < config.LLM_MAX_RETRIES - 1:
                    time.sleep(min(60, 2 ** attempt * 2))
        raise LLMError(f"Model request failed after retries: {last_error}")

    def json(self, system: str, prompt: str, max_tokens: int = 7000) -> Any:
        raw = self.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ], max_tokens=max_tokens, json_mode=True)
        return parse_json_response(raw)

    def json_multimodal(self, system: str, text: str, image_paths: list[str | tuple[str, str]], max_tokens: int = 7000) -> Any:
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for item in image_paths:
            label, path = item if isinstance(item, tuple) else ("Source page image", item)
            data_url = image_as_data_url(path)
            if data_url:
                content.append({"type": "text", "text": f"Image evidence: {label}"})
                content.append({"type": "image_url", "image_url": {"url": data_url, "detail": "high"}})
        raw = self.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ], max_tokens=max_tokens, json_mode=True)
        return parse_json_response(raw)


def parse_json_response(raw: str) -> Any:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Find the outermost JSON object/array in case the provider adds a preamble.
        start_candidates = [x for x in (text.find("{"), text.find("[")) if x >= 0]
        if not start_candidates:
            raise LLMError("Model response did not contain parseable JSON.")
        start = min(start_candidates)
        end_obj, end_arr = text.rfind("}"), text.rfind("]")
        end = max(end_obj, end_arr)
        if end < start:
            raise LLMError("Model response contained incomplete JSON.")
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"Could not parse model JSON: {exc}") from exc


def get_primary_client() -> OpenAICompatibleClient:
    return OpenAICompatibleClient(config.LLM_BASE_URL, config.LLM_API_KEY, config.LLM_MODEL)


def get_verifier_client() -> OpenAICompatibleClient | None:
    if not config.VERIFY_BASE_URL or not config.VERIFY_MODEL:
        return None
    return OpenAICompatibleClient(config.VERIFY_BASE_URL, config.VERIFY_API_KEY, config.VERIFY_MODEL)


def get_vision_client() -> OpenAICompatibleClient | None:
    if not config.VISION_BASE_URL or not config.VISION_MODEL:
        return None
    return OpenAICompatibleClient(config.VISION_BASE_URL, config.VISION_API_KEY, config.VISION_MODEL)


def _compact_question(q: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": q["id"],
        "question_number": q["question_number"],
        "subject_hint": q.get("subject"),
        "question": q.get("question_text", "")[:8000],
        "options": q.get("options", {}),
        "provided_analysis_or_solution": q.get("source_solution", "")[:5000],
    }


def analyze_question_batch(client: OpenAICompatibleClient, questions: list[dict[str, Any]], vision_client: OpenAICompatibleClient | None = None) -> dict[str, dict[str, Any]]:
    payload = [_compact_question(q) for q in questions]
    prompt = ANALYSIS_SCHEMA_INSTRUCTIONS + "\n\nINPUT QUESTIONS:\n" + json.dumps(payload, ensure_ascii=False)
    image_items: list[tuple[str, str]] = []
    if vision_client is not None:
        seen = set()
        for q in questions:
            img = q.get("page_image")
            if img and img not in seen and len(image_items) < config.VISION_MAX_IMAGES:
                image_items.append((f"{q.get('id')} — source PDF page {q.get('page_number')}", img))
                seen.add(img)
        if image_items:
            prompt += "\n\nUse each labelled source-page image to recover diagrams, graphs, structures, tables and visual context for the corresponding question. Do not infer details that are not visible."
    if image_items:
        try:
            result = vision_client.json_multimodal(ANALYSIS_SYSTEM, prompt, image_items, max_tokens=max(3000, len(questions) * 1300))
        except Exception:
            result = client.json(ANALYSIS_SYSTEM, prompt + "\n\nNote: visual endpoint was unavailable; analyse extracted text only and flag any diagram-dependent uncertainty.", max_tokens=max(2500, len(questions) * 1100))
    else:
        result = client.json(ANALYSIS_SYSTEM, prompt, max_tokens=max(2500, len(questions) * 1100))
    if isinstance(result, dict):
        result = result.get("questions", result.get("results", [result]))
    if not isinstance(result, list):
        raise LLMError("Question-analysis response was not a JSON list.")
    by_id = {}
    requested = {q["id"] for q in questions}
    for item in result:
        if isinstance(item, dict) and item.get("id") in requested:
            by_id[item["id"]] = item
    return by_id


def analyze_single_question(client: OpenAICompatibleClient, q: dict[str, Any], vision_client: OpenAICompatibleClient | None = None) -> dict[str, Any]:
    by_id = analyze_question_batch(client, [q], vision_client)
    if q["id"] not in by_id:
        raise LLMError(f"Model omitted question {q['question_number']} ({q['id']}).")
    return by_id[q["id"]]


def _candidate_for_prompt(q: dict[str, Any], score: float) -> dict[str, Any]:
    a = q.get("analysis") or {}
    return {
        "id": q["id"],
        "test_number": q.get("test_number"),
        "test_label": q.get("label"),
        "question_number": q["question_number"],
        "subject": q.get("subject") or a.get("subject"),
        "chapter": a.get("chapter"),
        "topic": a.get("topic"),
        "core_concept": a.get("core_concept"),
        "question_type": a.get("question_type"),
        "question": q.get("question_text", "")[:2200],
        "options": q.get("options", {}),
        "solution_steps": a.get("solution_steps", [])[:6],
        "retrieval_score": round(float(score), 4),
    }


def classify_matches(client: OpenAICompatibleClient, neet_q: dict[str, Any], candidates: list[tuple[dict[str, Any], float]], vision_client: OpenAICompatibleClient | None = None) -> tuple[list[dict[str, Any]], str]:
    n_analysis = neet_q.get("analysis") or {}
    n_obj = {
        "id": neet_q["id"], "question_number": neet_q["question_number"],
        "subject": neet_q.get("subject") or n_analysis.get("subject"),
        "chapter": n_analysis.get("chapter"), "topic": n_analysis.get("topic"),
        "core_concept": n_analysis.get("core_concept"),
        "question": neet_q.get("question_text", "")[:4000],
        "options": neet_q.get("options", {}),
        "solution_steps": n_analysis.get("solution_steps", [])[:6],
    }
    c_obj = [_candidate_for_prompt(q, score) for q, score in candidates]
    prompt = MATCH_SCHEMA_INSTRUCTIONS + "\n\nNEET QUESTION:\n" + json.dumps(n_obj, ensure_ascii=False) + "\n\nMOCK CANDIDATES (only these IDs are valid):\n" + json.dumps(c_obj, ensure_ascii=False)
    image_items: list[tuple[str, str]] = []
    chosen_client = client
    if vision_client is not None and config.VISION_MAX_IMAGES > 0:
        if neet_q.get("page_image"):
            image_items.append((f"NEET question {neet_q.get('question_number')} source page", neet_q["page_image"]))
        seen = {neet_q.get("page_image")} if neet_q.get("page_image") else set()
        for candidate, _ in candidates:
            img = candidate.get("page_image")
            if img and img not in seen and len(image_items) < config.VISION_MAX_IMAGES:
                image_items.append((f"Mock {candidate.get('label')} question {candidate.get('question_number')} source page; candidate ID {candidate['id']}", img))
                seen.add(img)
        if image_items:
            chosen_client = vision_client
            prompt += "\n\nPAGE IMAGES: each image is preceded by a precise label naming the question ID and source paper. Use them to inspect diagrams/graphs/tables; do not claim visual reuse unless the same distinctive visual evidence is clearly visible."
    if image_items:
        try:
            result = chosen_client.json_multimodal(MATCH_SYSTEM, prompt, image_items, max_tokens=6000)
        except Exception:
            result = client.json(MATCH_SYSTEM, prompt + "\n\nNote: visual model was unavailable; do not make visual-only claims from text extraction.", max_tokens=5000)
    else:
        result = client.json(MATCH_SYSTEM, prompt, max_tokens=5000)
    if isinstance(result, list):
        result = result[0] if result else {}
    if not isinstance(result, dict):
        raise LLMError("Relationship response was not a JSON object.")
    allowed = {q["id"]: score for q, score in candidates}
    matches = []
    for m in result.get("matches", []) or []:
        if not isinstance(m, dict) or m.get("mock_question_id") not in allowed:
            continue
        rel = m.get("relationship")
        if rel not in RELATIONSHIP_LABELS:
            continue
        conf = max(0.0, min(100.0, float(m.get("confidence", 0))))
        if conf < 35:
            continue
        matches.append({
            "mock_question_id": m["mock_question_id"],
            "relationship": rel,
            "confidence": conf,
            "retrieval_score": allowed[m["mock_question_id"]],
            "rationale": str(m.get("rationale", ""))[:3000],
            "shared_concept": str(m.get("shared_concept", ""))[:1000],
            "differences": str(m.get("differences", ""))[:1500],
            "solution_comparison": str(m.get("solution_comparison", ""))[:1500],
            "evidence": [str(x)[:500] for x in (m.get("evidence", []) or [])[:6]],
            "verification_status": "Primary model only",
        })
    matches.sort(key=lambda x: (x["confidence"], x["retrieval_score"]), reverse=True)
    return matches, str(result.get("no_match_reason", ""))


def verify_match_batch(verifier: OpenAICompatibleClient, neet_q: dict[str, Any], mock_questions: list[dict[str, Any]], matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not matches:
        return matches
    by_id = {q["id"]: q for q in mock_questions}
    # A text-only verifier must not reject a match whose evidence is specifically a diagram/graph.
    visual_matches = [m for m in matches if m["relationship"] == "SAME_DIAGRAM_OR_EXPERIMENTAL_SETUP"]
    text_matches = [m for m in matches if m["relationship"] != "SAME_DIAGRAM_OR_EXPERIMENTAL_SETUP"]
    payload = []
    for m in text_matches:
        q = by_id.get(m["mock_question_id"])
        if q:
            payload.append({
                "match": m,
                "mock_question": q.get("question_text", "")[:3000],
                "mock_analysis": q.get("analysis") or {},
            })
    prompt = "Independently audit these proposed NEET-to-mock matches. Be strict. For each, return mock_question_id, keep (true/false), revised_relationship (one of the following keys or null): " + ", ".join(RELATIONSHIP_LABELS) + ". Also return revised_confidence (0-100), verification_note. A shared chapter alone is not enough. Output JSON object {\"verifications\":[...]}.\n\n" + json.dumps({"neet_question": neet_q.get("question_text", "")[:3000], "neet_analysis": neet_q.get("analysis") or {}, "proposals": payload}, ensure_ascii=False)
    items = []
    if payload:
        result = verifier.json("You are an independent quality auditor for educational question matching. Do not agree just to be agreeable. Return valid JSON only.", prompt, max_tokens=3500)
        if isinstance(result, dict):
            items = result.get("verifications", [])
    audit = {x.get("mock_question_id"): x for x in items if isinstance(x, dict)}
    kept = []
    for m in visual_matches:
        m["verification_status"] = "Primary visual-model classification; not audited by text-only verifier"
        kept.append(m)
    for m in text_matches:
        v = audit.get(m["mock_question_id"])
        if not v:
            m["verification_status"] = "Verifier did not return a decision; primary result retained"
            kept.append(m)
            continue
        if not v.get("keep", False):
            continue
        revised = v.get("revised_relationship")
        if revised in RELATIONSHIP_LABELS:
            m["relationship"] = revised
        m["confidence"] = max(0.0, min(100.0, float(v.get("revised_confidence", m["confidence"]))))
        note = str(v.get("verification_note", ""))
        m["verification_status"] = "Kept by independent verifier" + (f": {note}" if note else "")
        kept.append(m)
    return kept


def image_as_data_url(path: str | Path) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    encoded = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"