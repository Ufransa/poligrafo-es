# src/electoral/juez.py
"""Cruce promesa ↔ votación con tres jueces de familias distintas (validado: 19/19 con unanimidad)."""
import json
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from src.electoral.llm import PresupuestoAgotado
from src.embeddings import embed_texts, from_blob, to_blob

JUECES = ["deepseek/deepseek-v4-pro", "openai/gpt-5-mini", "google/gemini-2.5-flash-lite"]

SISTEMA = """Eres el juez de PolígrafoES. Comparas promesas electorales de 2023 con votaciones del Congreso.
Neutralidad absoluta: describe, no opines ni califiques.

Para cada partido con promesas candidatas, decide si alguna promesa trata de la MATERIA CONCRETA que se vota.
- Si ninguna: no la incluyas.
- Si sí: chunk_id de la promesa, y veredicto comparando la promesa con el SENTIDO DE VOTO de ese partido:
  "cumple" si votó en coherencia con lo que prometió, "incumple" si votó en contra de lo que prometió.
- Si no puedes afirmarlo con seguridad: veredicto null. Es preferible el silencio a un veredicto dudoso.
- Si un partido no aparece en SENTIDO DE VOTO, no sabes cómo votó: veredicto null siempre.
- Una ABSTENCIÓN nunca es "cumple". Es "incumple" solo si prometió explícitamente actuar en esa materia.
- Compartir vocabulario NO es pronunciarse.
- Una promesa sobre PROCEDIMIENTO parlamentario no es un pronunciamiento sobre la materia que se vota.
- PRUEBA DEL PARAGUAS: ¿serviría esa misma promesa para una ley de un tema completamente distinto? Si sí, null.
- Lee el AVISO sobre el sentido del voto cuando lo haya.

REGLA DE FUERZA (obligatoria en cada match con veredicto):
- "directa": la votación decide EXACTAMENTE la acción prometida: la misma ley, la misma medida o el mismo objeto concreto.
- "indirecta": el tema es cercano pero la votación no decide lo prometido.
- Una proposición no de ley o una moción que pide EXACTAMENTE la medida prometida es "directa": no obliga,
  pero es la posición expresa del partido sobre esa medida.
Si dudas entre directa e indirecta, es indirecta.

Responde SOLO con JSON:
{"matches": [{"party": str, "chunk_id": int, "veredicto": "cumple"|"incumple"|null, "fuerza": "directa"|"indirecta"|null}]}"""


def aviso_sentido(v) -> str:
    if v["subtipo"] == "texto_alternativo":
        return ("AVISO: se vota una ENMIENDA DE TEXTO ALTERNATIVO. Votar Sí es apoyar ese texto alternativo EN LUGAR "
                "del original; votar No es rechazarlo. No es una votación sobre aprobar o tumbar la ley original.")
    if v["subtipo"] == "devolucion":
        return "AVISO: se vota una ENMIENDA DE DEVOLUCIÓN: votar Sí es tumbar el proyecto, votar No es dejar que siga."
    return ""


def significado(subtipo: str, voto: str) -> str:
    """El sentido real del voto, escrito junto al voto: los modelos baratos leen al revés las devoluciones."""
    if subtipo == "devolucion":
        return {"Sí": " (= quiere tumbar el proyecto)", "No": " (= a favor de que el proyecto siga adelante)"}.get(voto, "")
    if subtipo == "texto_alternativo":
        return {"Sí": " (= apoya el texto alternativo en lugar del original)", "No": " (= rechaza el texto alternativo)"}.get(voto, "")
    return ""


def asegurar_embeddings(conn) -> None:
    faltan = conn.execute("SELECT id, texto FROM promesas WHERE embedding IS NULL AND procedimental = 0").fetchall()
    if faltan:
        vecs = embed_texts([p["texto"] for p in faltan], "passage: ")
        conn.executemany("UPDATE promesas SET embedding = ? WHERE id = ?", [(to_blob(v), p["id"]) for p, v in zip(faltan, vecs)])
        conn.commit()


def candidatos(conn, votaciones, k):
    """Top-k promesas por votación, con la similitud normalizada dentro de cada programa (z-score)."""
    P = conn.execute("SELECT id, partido, texto, embedding FROM promesas "
                     "WHERE procedimental = 0 AND embedding IS NOT NULL ORDER BY id").fetchall()
    if not P or not votaciones:
        return {}
    E = np.vstack([from_blob(p["embedding"]) for p in P])   # misma consulta: ids y vectores casan
    partidos = np.array([p["partido"] for p in P])
    Q = embed_texts([v["expediente"] + " " + v["tipo"] for v in votaciones], "query: ")
    S = Q @ E.T
    Z = np.empty_like(S)
    for partido in set(partidos):
        m = partidos == partido
        desv = S[:, m].std() or 1.0
        Z[:, m] = (S[:, m] - S[:, m].mean()) / desv
    return {v["id"]: [P[j] for j in np.argsort(-Z[i])[:k]] for i, v in enumerate(votaciones)}


def prompt(v, votos, cands) -> str:
    partes = [f"VOTACIÓN:\nAsunto: {v['expediente']}\nTipo de sesión: {v['tipo']}"]
    if v["texto_subgrupo"]:
        partes.append(f"Qué se vota exactamente: {v['texto_subgrupo']}")
    partes.append(f"Resultado: {v['resultado']}")
    partes.append("\nSENTIDO DE VOTO DE CADA PARTIDO EN ESTA VOTACIÓN:")
    partes += [f"  {r['partido']}: {r['voto']}{significado(v['subtipo'], r['voto'])}" for r in votos]
    if aviso_sentido(v):
        partes.append("\n" + aviso_sentido(v))
    por_partido = {}
    for p in cands:
        por_partido.setdefault(p["partido"], []).append(p)
    for partido, ps in por_partido.items():
        partes.append(f"\nPromesas del programa electoral de {partido}:")
        partes += [f"[chunk_id={p['id']}] {p['texto']}" for p in ps]
    return "\n".join(partes)


def estables(llm, modelo, texto, validos):
    """Solo lo que el juez repite igual en dos pasadas. None si alguna pasada falla."""
    pasadas = []
    for _ in range(2):
        out = llm.json(modelo, SISTEMA, texto)
        if out is None:
            return None
        pasadas.append({(m.get("party"), m.get("chunk_id")): (m.get("veredicto"), m.get("fuerza"))
                        for m in out.get("matches", []) if m.get("chunk_id") in validos and m.get("veredicto") in ("cumple", "incumple")})
    return {k: x for k, x in pasadas[0].items() if pasadas[1].get(k) == x}


def nivel(respuestas: dict, dividido: bool):
    """(nivel, veredicto) a partir de lo que dijo cada juez sobre un cruce. None si no se publica."""
    dados = [r for r in respuestas.values() if r is not None]
    for veredicto in ("cumple", "incumple"):
        coinciden = [r for r in dados if r[0] == veredicto]
        if len(coinciden) == len(JUECES) and all(r[1] == "directa" for r in coinciden) and not dividido:
            return "veredicto", veredicto
        if len(coinciden) >= 2:
            return "juzga_tu", veredicto
    return None


def juzgar(conn, llm, k=20) -> None:
    asegurar_embeddings(conn)
    hechos = {r[0] for r in conn.execute("SELECT votacion_id FROM juicios WHERE completo = 1")}
    vs = [v for v in conn.execute("SELECT * FROM votaciones WHERE excluida_tramite = 0").fetchall() if v["id"] not in hechos]
    cands = candidatos(conn, vs, k)

    # La conexión SQLite no se comparte entre hilos: todo lo que se lee de la base se lee aquí, antes.
    votos_de = {v["id"]: conn.execute("SELECT * FROM votos_partido WHERE votacion_id = ? ORDER BY partido",
                                      (v["id"],)).fetchall() for v in vs}

    def uno(v):
        votos = votos_de[v["id"]]
        texto = prompt(v, votos, cands.get(v["id"], []))
        validos = {p["id"] for p in cands.get(v["id"], [])}
        return v, votos, {m: estables(llm, m, texto, validos) for m in JUECES}

    with ThreadPoolExecutor(6) as ex:
        for f in [ex.submit(uno, v) for v in vs]:
            try:
                v, votos, por_juez = f.result()
            except PresupuestoAgotado:
                continue
            if any(r is None for r in por_juez.values()):
                continue                       # algún juez falló: el expediente queda pendiente
            dividido = {r["partido"]: bool(r["dividido"]) for r in votos}
            conn.execute("DELETE FROM cruces WHERE votacion_id = ?", (v["id"],))
            for clave in set().union(*[set(r) for r in por_juez.values()]):
                partido, promesa_id = clave
                respuestas = {m: por_juez[m].get(clave) for m in JUECES}
                res = nivel(respuestas, dividido.get(partido, False))
                if res:
                    conn.execute("INSERT INTO cruces VALUES (?,?,?,?,?,?)", (v["id"], promesa_id, partido, res[0], res[1], json.dumps(
                        {m: ({"veredicto": r[0], "fuerza": r[1]} if r else None) for m, r in respuestas.items()}, ensure_ascii=False)))
            conn.execute("INSERT OR REPLACE INTO juicios VALUES (?, 1, ?)", (v["id"], ""))
            conn.commit()
