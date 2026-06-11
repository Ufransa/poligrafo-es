# PolígrafoES v2 — Digest legible

**Fecha:** 2026-06-11
**Estado:** Aprobado por Fran
**Contexto:** El canal es una herramienta personal de Fran (único lector). Diagnóstico: lee el digest pero no lo entiende — títulos legalese truncados, siglas crípticas, sin resultado de la votación, sin consecuencias prácticas. Además el matcher voto↔programa genera ~713 matches por voto (32.788 matches / 46 votos): ruido, no señal.

---

## 1. Objetivo

Que el digest semanal sea comprensible de un vistazo: qué se votó (en cristiano), qué cambia en la práctica, si salió adelante, y qué prometía cada partido **solo cuando el cruce es real**. Se eliminan las alertas diarias: el canal publica únicamente el digest del lunes.

## 2. Decisiones de diseño (cerradas)

| Decisión | Valor |
|---|---|
| LLM | Claude Haiku 4.5 (`claude-haiku-4-5`), SDK oficial `anthropic` |
| Arquitectura | Enriquecer al ingestar (fetcher diario), digest = plantilla sin LLM |
| Alertas diarias | Eliminadas (vote_alert y boe_alert dejan de publicarse) |
| Matcher | Keyword matching = pre-filtro (top-5 chunks/partido); LLM = juez de relevancia |
| Resultado aprobada/rechazada | Computado en código desde `<Totales>` del XML — sin LLM |
| Structured outputs | `client.messages.parse()` + modelos Pydantic |
| Coste estimado | ~1€/mes (~10 votos × ~15k tokens + ~12 BOE × ~2k tokens por semana) |

## 3. Flujo

```
fetcher.py (cron 21:00 diario)
  1. Ingesta votos + BOE (sin cambios)
  2. NUEVO: parsea <Totales> → a_favor/en_contra/abstenciones → resultado
  3. NUEVO: enriquece items pendientes (enriched_at IS NULL):
       voto → Haiku: {resumen, que_cambia, matches validados por partido}
       BOE  → Haiku: {resumen}
  4. Ya NO publica alertas

digest.py (cron lunes 10:30)
  - Plantilla sobre datos enriquecidos → Telegram (HTML, límite 4096 chars con split)
  - Item sin enriquecer → línea en formato crudo (fallback, nunca digest vacío)
```

Reintentos: si la llamada LLM falla, `enriched_at` queda NULL y el siguiente run del fetcher lo reintenta. El SDK ya reintenta 429/5xx automáticamente.

## 4. Matcher v2

1. `matcher.py` calcula score por keywords como hoy, pero solo selecciona **top-5 chunks por partido** como candidatos (deja de escribir todo match con score ≥ 2).
2. `llm.py` recibe el voto (título + texto_expediente) + candidatos y devuelve, por partido, el chunk pertinente **o ninguno**. Criterio del prompt: el extracto debe pronunciarse sobre la materia concreta que se vota, no compartir vocabulario.
3. Solo los matches validados se insertan en `vote_program_matches` (≤ 4 por voto, uno por partido).
4. Migración: purgar los 32.788 matches existentes (ruido del umbral de 2 keywords).

## 5. Cambios de esquema (SQLite)

```sql
ALTER TABLE votes ADD COLUMN a_favor INTEGER;
ALTER TABLE votes ADD COLUMN en_contra INTEGER;
ALTER TABLE votes ADD COLUMN abstenciones INTEGER;
ALTER TABLE votes ADD COLUMN resultado TEXT;      -- 'aprobada' | 'rechazada'
ALTER TABLE votes ADD COLUMN resumen TEXT;        -- título en cristiano
ALTER TABLE votes ADD COLUMN que_cambia TEXT;     -- consecuencia práctica, 1-2 frases
ALTER TABLE votes ADD COLUMN enriched_at TEXT;

ALTER TABLE boe_entries ADD COLUMN resumen TEXT;
ALTER TABLE boe_entries ADD COLUMN enriched_at TEXT;

DELETE FROM vote_program_matches;                  -- purga del ruido
```

Sin backfill de votos históricos (no se re-digieren). Migración idempotente al estilo del `init_db()` existente.

## 6. Nuevo módulo `src/llm.py`

- Cliente `anthropic.Anthropic()` (lee `ANTHROPIC_API_KEY` del `.env`).
- `enrich_vote(vote, candidates) -> VoteEnrichment` — una llamada por voto: resumen + qué cambia + juicio de matches. Pydantic: `VoteEnrichment{resumen: str, que_cambia: str, matches: list[PartyMatch{party, chunk_id | None, razon}]}`.
- `summarize_boe(entry) -> str` — una llamada por entrada BOE (fallos aislados por item; el volumen no justifica agrupar).
- Prompt en español, instrucciones de formato como bloque explícito no-negociable (lección ARGUS #15).
- `max_tokens` holgado (~2048 por llamada); sin parámetros de sampling.

## 7. Formato del digest (Telegram HTML)

```
📊 Congreso — semana del 9 jun
3 votaciones · 4 leyes BOE

🗳️ Subida del SMI a 1.250€ — ✅ APROBADA (paso a trámite)
Se acepta tramitar la ley; aún no es definitiva.
A favor: PSOE, Sumar, ERC, Bildu · En contra: PP, Vox

📋 PSOE lo prometía (p.45): "elevaremos el SMI hasta…"

🗳️ [siguiente votación…]

📜 BOE en cristiano
· Ayudas al alquiler joven: hasta 250€/mes para menores de 35 — ver
· …

PolígrafoES
```

- Partidos con nombre completo (config/parties.json), agrupados por sentido del voto.
- El cruce 📋 solo aparece si el juez validó el match; incluye página del programa.
- División interna se conserva como nota `(división interna)`.
- Split en dos mensajes si supera 4096 chars (mecanismo actual).

## 8. Eliminación de alertas

- `fetcher.py`: se elimina la publicación inmediata (vote_alert + boe_alert).
- `publisher.py`: se eliminan `format_vote_alert` y `format_boe_alert`; entra `format_digest_v2`.
- `published_messages` conserva su historial; los nuevos registros son solo `weekly_digest`.

## 9. Testing (pytest, patrón existente del repo)

- `resultado` desde `<Totales>` usando el fixture real `tests/fixtures/vote_session.xml`.
- Contrato de `llm.py` con la API mockeada (sin llamadas reales): entrada voto+candidatos → `VoteEnrichment` válido; manejo de respuesta con `chunk_id` inexistente (descartar match).
- Pre-filtro del matcher: top-5 por partido, no inserta nada sin validación.
- Digest: render con items enriquecidos, fallback con items sin enriquecer, split a 4096.
- Fetcher: item con fallo LLM queda `enriched_at IS NULL` y se reintenta en el siguiente run.

## 10. Deploy

- `requirements.txt` += `anthropic`.
- `.env` (local y Orange Pi) += `ANTHROPIC_API_KEY`.
- Migración se ejecuta sola al arrancar (init_db).
- Deploy a Orange Pi vía protocolo habitual (`git fetch && git reset --hard`, lección #10).
- Crons sin cambios (21:00 fetcher, lunes 10:30 digest).

## 11. Fuera de alcance

- Alertas excepcionales por contradicción flagrante (posible fase futura).
- Marcador acumulado de coherencia por partido (depende de acumular matches validados; evaluar tras ~1 mes de datos limpios).
- Re-enriquecer votos históricos.
- Cambiar la visibilidad del canal (sigue privado — herramienta personal).
