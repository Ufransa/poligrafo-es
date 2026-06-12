"""
src/llm.py — PolígrafoES
Enriquecimiento con Claude Haiku 4.5: resúmenes en español llano y juez de
relevancia voto↔programa. Structured outputs vía Pydantic.
"""
from typing import Optional

import anthropic
from pydantic import BaseModel

MODEL = "claude-haiku-4-5"


class PartyMatch(BaseModel):
    party: str
    chunk_id: Optional[int]  # None si ningún extracto del partido es pertinente


class VoteEnrichment(BaseModel):
    resumen: str
    que_cambia: str
    matches: list[PartyMatch]


class BoeSummary(BaseModel):
    resumen: str


_SYSTEM_VOTE = """Eres el redactor de PolígrafoES, una herramienta personal que traduce \
votaciones del Congreso de los Diputados a español llano. Tu lector es un ciudadano \
informado sin formación jurídica.

FORMAT RULES (no negociables):
- resumen: máximo 12 palabras. Qué se vota, en cristiano. Sin jerga parlamentaria \
("toma en consideración", "proposición de ley orgánica"...). Si es un trámite y no \
una ley definitiva, no lo digas aquí (va en que_cambia).
- que_cambia: 1 o 2 frases. La consecuencia práctica: qué cambia si sale adelante, \
o qué se ha rechazado. Si es solo un paso del trámite, dilo ("se acepta tramitarla; \
aún no es ley").
- matches: por cada partido del que recibas extractos, devuelve el chunk_id del ÚNICO \
extracto que se pronuncia sobre la materia concreta que se vota, o null si ninguno lo \
hace. Compartir vocabulario NO es pronunciarse. En caso de duda, null.
- Neutralidad absoluta: describe, no opines ni califiques."""

_SYSTEM_BOE = """Eres el redactor de PolígrafoES. Resumes entradas del BOE para un \
ciudadano sin formación jurídica.

FORMAT RULES (no negociables):
- resumen: una sola frase (máximo 25 palabras) en español llano con la consecuencia \
práctica de la norma. Sin números de expediente ni jerga legal.
- Neutralidad absoluta: describe, no opines."""


def _client():
    return anthropic.Anthropic()  # ANTHROPIC_API_KEY del entorno


def enrich_vote(vote, candidates, client=None):
    """
    vote: dict con 'titulo' y 'texto_expediente'.
    candidates: {party: [{chunk_id, score, text, page_start}, ...]} (pre-filtro del matcher).
    Returns: VoteEnrichment con matches filtrados a chunk_ids realmente candidatos.
    """
    client = client or _client()

    parts = [
        "VOTACIÓN:",
        f"Título oficial: {vote['titulo']}",
        f"Expediente: {(vote.get('texto_expediente') or '')[:1500]}",
    ]
    valid_ids = set()
    for party, cands in candidates.items():
        parts.append(f"\nExtractos del programa electoral de {party}:")
        for c in cands:
            valid_ids.add(c["chunk_id"])
            parts.append(f"[chunk_id={c['chunk_id']}] (p.{c['page_start']}) {c['text'][:600]}")
    if not candidates:
        parts.append("\n(No hay extractos de programas candidatos para esta votación.)")

    response = client.messages.parse(
        model=MODEL,
        max_tokens=2048,
        system=_SYSTEM_VOTE,
        messages=[{"role": "user", "content": "\n".join(parts)}],
        output_format=VoteEnrichment,
    )
    enrichment = response.parsed_output
    enrichment.matches = [m for m in enrichment.matches if m.chunk_id in valid_ids]
    return enrichment


def summarize_boe(entry, client=None):
    """entry: dict con titulo, rango, departamento, texto_preview. Returns: str."""
    client = client or _client()
    prompt = (
        f"Título: {entry['titulo']}\n"
        f"Rango: {entry.get('rango', '')}\n"
        f"Departamento: {entry.get('departamento', '')}\n"
        f"Texto (inicio): {(entry.get('texto_preview') or '')[:1200]}"
    )
    response = client.messages.parse(
        model=MODEL,
        max_tokens=512,
        system=_SYSTEM_BOE,
        messages=[{"role": "user", "content": prompt}],
        output_format=BoeSummary,
    )
    return response.parsed_output.resumen
