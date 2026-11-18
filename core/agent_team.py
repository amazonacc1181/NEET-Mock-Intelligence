from __future__ import annotations

from typing import Any


AGENT_TEAM = [
    {"name": "AI Operations Manager", "role": "Coordinates the workflow, checks stage gates, assigns work and refuses to label incomplete work complete."},
    {"name": "PDF & Layout Specialist", "role": "Extracts page text, question blocks, page references and page previews; flags OCR/layout uncertainty."},
    {"name": "NEET Subject Analyst", "role": "Classifies subject, NCERT chapter, topic, exact concept, question style, formulas/reactions and solution steps."},
    {"name": "Independent Solution Auditor", "role": "Checks the proposed answer, concepts, formulas and solution independently when hardware supports a second model."},
    {"name": "Semantic Retrieval Specialist", "role": "Uses BGE-M3 embeddings together with word, character and exact-text signals to retrieve candidate mock questions."},
    {"name": "Relationship Examiner", "role": "Compares the full NEET question against retrieved mock candidates and assigns one of seven relationship categories."},
    {"name": "Independent Match Verifier", "role": "Challenges accepted matches, corrects over-strong labels and rejects chapter-only overlap."},
    {"name": "Report QA Editor", "role": "Checks paper/question counts, flags unmatched/unprocessed questions and creates the final detailed PDF and workbook."},
]


def team_status(primary_model: str, verifier_model: str, vision_model: str, embedding_model: str) -> list[dict[str, Any]]:
    return [
        {"name": AGENT_TEAM[0]["name"], "model": primary_model, "mode": "Coordinator / stage gates"},
        {"name": AGENT_TEAM[1]["name"], "model": "PyMuPDF + Tesseract OCR", "mode": "Local document extraction"},
        {"name": AGENT_TEAM[2]["name"], "model": primary_model, "mode": "Primary multimodal model"},
        {"name": AGENT_TEAM[3]["name"], "model": verifier_model or primary_model, "mode": "Independent second model" if verifier_model else "Same-model review; lower independence"},
        {"name": AGENT_TEAM[4]["name"], "model": embedding_model, "mode": "Local embedding + lexical retrieval"},
        {"name": AGENT_TEAM[5]["name"], "model": primary_model, "mode": "Primary multimodal model"},
        {"name": AGENT_TEAM[6]["name"], "model": verifier_model or primary_model, "mode": "Independent second model" if verifier_model else "Same-model review; lower independence"},
        {"name": AGENT_TEAM[7]["name"], "model": "Python + ReportLab", "mode": "Deterministic report generation and QA"},
    ]