"""
src/llm.py — PolígrafoES
Enriquecimiento con Claude Haiku 4.5: resúmenes en español llano y juez de
relevancia voto↔programa. Structured outputs vía Pydantic.
"""
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel

MODEL = "claude-haiku-4-5"


class PartyMatch(BaseModel):
    party: str
    chunk_id: Optional[int]      # None si ningún extracto del partido es pertinente
    promesa: str                 # la promesa parafraseada en una línea; "" si no hay match
    veredicto: Optional[Literal["cumple", "incumple"]]  # None si no se puede afirmar


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
("toma en consideración", "proposición de ley orgánica"...).
- que_cambia: 1 o 2 frases. La consecuencia práctica según el tipo de votación:
  · Autorización de tratado o convenio internacional: es definitivo. Si APROBADA → \
"El tratado entra en vigor; España queda vinculada." Si RECHAZADA → "España no \
ratifica el acuerdo." Nunca digas "aún requiere pasos" — el Congreso es la autorización final.
  · Proyecto o proposición de ley: qué cambia en la vida cotidiana del ciudadano.
  · Proposición no de ley: no es vinculante. Escribe: "Declaración política sin efecto \
jurídico inmediato."
  · Enmienda a la totalidad: si RECHAZADA → el proyecto de ley sigue tramitándose. \
Si APROBADA → el proyecto cae completamente.
- matches: por cada partido con extractos, decide si ese partido se pronunció en su \
programa sobre la materia CONCRETA que se vota.
  · Si no se pronunció: chunk_id null, promesa "", veredicto null.
  · Si se pronunció: chunk_id del extracto, promesa = esa promesa parafraseada en una \
línea llana (máximo 15 palabras), y veredicto comparando la promesa con el sentido \
de voto del partido en esta votación: "cumple" si votó en coherencia con lo que \
prometió, "incumple" si votó en contra de lo que prometió.
  · Si hay extracto pertinente pero no puedes afirmar con seguridad si cumple o \
incumple: veredicto null. Es preferible el silencio a un veredicto dudoso.
  · Compartir vocabulario NO es pronunciarse. Para tratados internacionales, solo hay \
match si el extracto menciona ese país, ese tipo de acuerdo bilateral o esa \
política exterior concreta. En caso de duda, null.
- Neutralidad absoluta: describe, no opines ni califiques."""

_SYSTEM_BOE = """Eres el redactor de PolígrafoES. Resumes entradas del BOE para un \
ciudadano sin formación jurídica.

FORMAT RULES (no negociables):
- resumen: una sola frase (máximo 25 palabras) en español llano con la consecuencia \
práctica de la norma. Sin números de expediente ni jerga legal.
- Neutralidad absoluta: describe, no opines."""


def _client():
    return anthropic.Anthropic()  # ANTHROPIC_API_KEY del entorno


def build_expediente_prompt(expediente, candidates):
    """Construye el user prompt de una votación agrupada por expediente."""
    partes = [
        "VOTACIÓN:",
        f"Asunto: {expediente['texto_expediente']}",
        f"Tipo de sesión: {expediente['titulo']}",
        f"Resultado: {expediente['resultado']} "
        f"({expediente['a_favor']} a favor / {expediente['en_contra']} en contra)",
    ]
    enmiendas = expediente.get("enmiendas") or []
    if enmiendas:
        partes.append(f"\nAntes del texto final hubo {len(enmiendas)} votaciones de enmiendas:")
        for e in enmiendas[:40]:
            partes.append(f"  · {e['grupo']}: {e['detalle']} → {e['resultado']}")

    for party, cands in candidates.items():
        partes.append(f"\nExtractos del programa electoral de {party}:")
        for c in cands:
            partes.append(f"[chunk_id={c['chunk_id']}] (p.{c['page_start']}) {c['text'][:600]}")
    if not candidates:
        partes.append("\n(No hay extractos de programas candidatos para esta votación.)")

    return "\n".join(partes)


def enrich_expediente(expediente, candidates, client=None):
    """
    Una llamada por expediente en vez de una por votación.
    Returns: VoteEnrichment con matches filtrados a chunk_ids realmente candidatos.
    """
    client = client or _client()
    valid_ids = {c["chunk_id"] for cands in candidates.values() for c in cands}

    response = client.messages.parse(
        model=MODEL,
        max_tokens=2048,
        system=_SYSTEM_VOTE,
        messages=[{"role": "user",
                   "content": build_expediente_prompt(expediente, candidates)}],
        output_format=VoteEnrichment,
    )
    enrichment = response.parsed_output
    enrichment.matches = [
        m for m in enrichment.matches
        if m.chunk_id in valid_ids and m.veredicto is not None
    ]
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
