# src/electoral/juez.py
"""Cruce promesa ↔ votación. Tres jueces de familias distintas dicen si la promesa está a favor o en contra de la
iniciativa; el veredicto (cumple / incumple) lo calcula el código comparando esa postura con el voto."""
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from src.electoral import analisis
from src.electoral.llm import PresupuestoAgotado
from src.embeddings import embed_texts, from_blob, to_blob

JUECES = ["deepseek/deepseek-v4-pro", "openai/gpt-5-mini", "google/gemini-2.5-flash-lite"]

SISTEMA = """Eres el juez de PolígrafoES. Comparas promesas electorales de 2023 con iniciativas votadas en el Congreso.
Neutralidad absoluta: describe, no opines ni califiques. No sabes cómo votó nadie y no debes suponerlo.

Para cada partido con promesas candidatas, decide si alguna promesa trata de la MATERIA CONCRETA de la iniciativa.
- Si ninguna: no la incluyas.
- Si sí: chunk_id de la promesa y su POSTURA frente a la INICIATIVA:
  "a_favor" si cumplir la promesa exige que la iniciativa salga adelante;
  "en_contra" si la promesa quiere suprimir, derogar o rechazar lo que la iniciativa impulsa.
  Ejemplos: «suprimiremos las oficinas de la Agenda 2030» frente a «impulsar la Agenda 2030»: en_contra.
  «Aprobaremos una ley de atención a la clientela» frente a esa misma ley: a_favor.
- Si no puedes afirmarlo con seguridad: postura null. Es preferible el silencio a una postura dudosa.
- Compartir vocabulario NO es pronunciarse.
- Una promesa sobre PROCEDIMIENTO parlamentario no es un pronunciamiento sobre la materia que se vota.
- PRUEBA DEL PARAGUAS: ¿serviría esa misma promesa para una ley de un tema completamente distinto? Si sí, null.

REGLA DE FUERZA (obligatoria en cada match con postura):
- "directa": la iniciativa decide EXACTAMENTE la acción prometida: la misma ley, la misma medida o el mismo objeto concreto.
- "indirecta": el tema es cercano pero la iniciativa no decide lo prometido.
- Una proposición no de ley o una moción que pide EXACTAMENTE la medida prometida es "directa": no obliga,
  pero es la posición expresa del partido sobre esa medida.
Si dudas entre directa e indirecta, es indirecta.

Responde SOLO con JSON:
{"matches": [{"party": str, "chunk_id": int, "postura": "a_favor"|"en_contra"|null, "fuerza": "directa"|"indirecta"|null}]}"""


def asegurar_embeddings(conn) -> None:
    faltan = conn.execute("SELECT id, texto FROM promesas WHERE embedding IS NULL AND procedimental = 0").fetchall()
    if faltan:
        vecs = embed_texts([p["texto"] for p in faltan], "passage: ")
        conn.executemany("UPDATE promesas SET embedding = ? WHERE id = ?", [(to_blob(v), p["id"]) for p, v in zip(faltan, vecs)])
        conn.commit()


def candidatos(conn, votaciones, k):
    """Top-k promesas por votación, con la similitud normalizada dentro de cada programa (z-score)."""
    # Solo promesas de 2023: un programa de 2026 no se puede «incumplir» con votos de la legislatura anterior.
    P = conn.execute("SELECT id, partido, texto, embedding FROM promesas "
                     "WHERE procedimental = 0 AND embedding IS NOT NULL AND anio = 2023 ORDER BY id").fetchall()
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


DEVOLUCION = re.compile(r"^.*?devoluci[oó]n (?:al|a la|del|de la) ", re.IGNORECASE)


def prompt(v, cands) -> str:
    """Solo la iniciativa y las promesas. Sin votos: el juez no puede acomodar la postura a lo que se votó."""
    if v["subtipo"] == "devolucion":
        # Solo el proyecto: si el juez ve la enmienda, la toma por la iniciativa. El voto se invierte en el código.
        partes = [f"INICIATIVA:\nAsunto: {DEVOLUCION.sub('', v['expediente'])}"]
    else:
        partes = [f"INICIATIVA:\nAsunto: {v['expediente']}\nTipo de sesión: {v['tipo']}"]
        if v["texto_subgrupo"]:
            partes.append(f"Qué se vota exactamente: {v['texto_subgrupo']}")
    por_partido = {}
    for p in cands:
        por_partido.setdefault(p["partido"], []).append(p)
    for partido, ps in por_partido.items():
        partes.append(f"\nPromesas del programa electoral de {partido}:")
        partes += [f"[chunk_id={p['id']}] {p['texto']}" for p in ps]
    return "\n".join(partes)


def estables(llm, modelo, texto, validos: dict):
    """Solo lo que el juez repite igual en dos pasadas. None si alguna pasada falla.

    `validos` es {promesa_id: partido dueño}. El partido del cruce es siempre el dueño de la promesa: si el
    juez se lo atribuye a otro, ese match se descarta.
    """
    pasadas = []
    for _ in range(2):
        out = llm.json(modelo, SISTEMA, texto)
        if out is None:
            return None
        pasada = {}
        for m in out.get("matches", []):
            try:
                pid = int(m.get("chunk_id"))
            except (TypeError, ValueError):
                continue
            if validos.get(pid) and m.get("party") == validos[pid] and m.get("postura") in ("a_favor", "en_contra"):
                pasada[(validos[pid], pid)] = (m.get("postura"), m.get("fuerza"))
        pasadas.append(pasada)
    return {k: x for k, x in pasadas[0].items() if pasadas[1].get(k) == x}


def nivel(respuestas: dict, dividido: bool, postura_voto: str | None):
    """(nivel, veredicto). El juez da la postura de la promesa; el veredicto sale de compararla con el voto.

    None si no se publica: sin acuerdo de los jueces, o si el voto no expresa postura (abstención, no vota,
    texto alternativo).
    """
    if postura_voto is None:
        return None
    dados = [r for r in respuestas.values() if r is not None]
    for postura in ("a_favor", "en_contra"):
        coinciden = [r for r in dados if r[0] == postura]
        veredicto = "cumple" if postura == postura_voto else "incumple"
        if len(coinciden) == len(JUECES) and all(r[1] == "directa" for r in coinciden) and not dividido:
            return "veredicto", veredicto
        if len(coinciden) >= 2:
            return "juzga_tu", veredicto
    return None


def huella(cands) -> str:
    """Lo que vio el juez: si cambian los candidatos o las instrucciones, el expediente se vuelve a juzgar."""
    base = json.dumps([sorted(p["id"] for p in cands), hashlib.sha1(SISTEMA.encode("utf-8")).hexdigest()])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def conjunto(conn, k) -> str:
    """Huella de las promesas que pueden ser candidatas (y de k). Si cambia, los candidatos se recalculan."""
    ids = [r[0] for r in conn.execute("SELECT id FROM promesas WHERE procedimental = 0 AND embedding IS NOT NULL "
                                      "AND anio = 2023 ORDER BY id")]
    return hashlib.sha1(json.dumps([ids, k]).encode("utf-8")).hexdigest()


def juzgar(conn, llm, k=20) -> int:
    """Juzga lo pendiente. Devuelve cuántos expedientes ha cerrado. No juzga si quedan bloques sin extraer."""
    pendientes = conn.execute("SELECT COUNT(*) FROM bloques WHERE extraido = 0").fetchone()[0]
    if pendientes:
        print(f"Quedan {pendientes} bloques de programa sin extraer: no se juzga hasta completarlos (extraer).")
        return 0
    asegurar_embeddings(conn)
    previos = conn.execute("SELECT * FROM juicios WHERE completo = 1").fetchall()
    hechas = {r["votacion_id"]: r["respuestas"] for r in previos}
    # El texto alternativo no se juzga: votar un texto que sustituye al original no es una postura sobre la ley.
    todas = conn.execute("SELECT * FROM votaciones WHERE excluida_tramite = 0 AND subtipo != 'texto_alternativo'").fetchall()
    # Los candidatos de lo ya juzgado se reutilizan mientras no cambien las promesas: la normalización depende de
    # todas las votaciones y los vectores varían algo entre máquinas, y eso no puede reabrir juicios cerrados.
    base = conjunto(conn, k)
    P = {p["id"]: p for p in conn.execute("SELECT id, partido, texto FROM promesas")}
    cands = {}
    for r in previos:
        ids = json.loads(r["candidatos"]) if r["candidatos"] else None
        if ids is not None and r["promesas"] == base and all(i in P for i in ids):
            cands[r["votacion_id"]] = [P[i] for i in ids]
    sin_fijar = [v for v in todas if v["id"] not in cands]
    if sin_fijar:
        nuevos = candidatos(conn, todas, k)
        cands.update({v["id"]: nuevos.get(v["id"], []) for v in sin_fijar})
    # La conexión SQLite no se comparte entre hilos: todo lo que se lee de la base se lee aquí, antes.
    votos_de = {v["id"]: conn.execute("SELECT * FROM votos_partido WHERE votacion_id = ? ORDER BY partido",
                                      (v["id"],)).fetchall() for v in todas}
    huellas = {v["id"]: huella(cands.get(v["id"], [])) for v in todas}
    vs = [v for v in todas if hechas.get(v["id"]) != huellas[v["id"]]]

    def uno(v):
        c = cands.get(v["id"], [])
        if not c:
            return v, {m: {} for m in JUECES}          # sin candidatos no hay nada que preguntar
        texto = prompt(v, c)
        validos = {p["id"]: p["partido"] for p in c}
        return v, {m: estables(llm, m, texto, validos) for m in JUECES}

    cerrados = 0
    with ThreadPoolExecutor(6) as ex:
        for f in [ex.submit(uno, v) for v in vs]:
            try:
                v, por_juez = f.result()
            except Exception:                  # presupuesto agotado o fallo inesperado: el expediente queda pendiente
                continue
            if any(r is None for r in por_juez.values()):
                continue                       # algún juez falló: el expediente queda pendiente
            dividido = {r["partido"]: bool(r["dividido"]) for r in votos_de[v["id"]]}
            voto = {r["partido"]: r["voto"] for r in votos_de[v["id"]]}
            conn.execute("DELETE FROM cruces WHERE votacion_id = ?", (v["id"],))
            for clave in set().union(*[set(r) for r in por_juez.values()]):
                partido, promesa_id = clave
                respuestas = {m: por_juez[m].get(clave) for m in JUECES}
                res = nivel(respuestas, dividido.get(partido, True), analisis.postura(v["subtipo"], voto.get(partido)))
                if res:
                    conn.execute("INSERT INTO cruces VALUES (?,?,?,?,?,?)", (v["id"], promesa_id, partido, res[0], res[1], json.dumps(
                        {m: ({"postura": r[0], "fuerza": r[1]} if r else None) for m, r in respuestas.items()}, ensure_ascii=False)))
            conn.execute("INSERT OR REPLACE INTO juicios (votacion_id, completo, respuestas, candidatos, promesas) "
                         "VALUES (?, 1, ?, ?, ?)", (v["id"], huellas[v["id"]],
                                                    json.dumps([p["id"] for p in cands.get(v["id"], [])]), base))
            conn.commit()
            cerrados += 1
    return cerrados
