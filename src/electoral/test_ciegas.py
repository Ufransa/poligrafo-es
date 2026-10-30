# src/electoral/test_ciegas.py
"""Test a ciegas: propuestas de un programa, resumidas sin delatar al partido y con sus condiciones jurídicas.
Ver docs/superpowers/specs/2026-10-30-test-a-ciegas-design.md."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.electoral.llm import PresupuestoAgotado

MODELO = "deepseek/deepseek-v4-flash"
ADIVINO = "google/gemini-2.5-flash-lite"
MAX_POR_PARTIDO_TEMA = 3
MAX_REESCRITURAS = 2
TEMAS_LANZAMIENTO = ["Economía e industria", "Vivienda", "Sanidad", "Fiscalidad", "Empleo y trabajo", "Pensiones"]

SISTEMA_SELECCION = f"""Eliges propuestas de un programa electoral español para un test donde la gente las vota sin saber
de qué partido son. De la lista, elige como mucho {MAX_POR_PARTIDO_TEMA}: las más CONCRETAS (qué se hace, a quién, cuánto)
y de MÁS ALCANCE (a cuánta gente afecta o cuánto cambia). Si hay {MAX_POR_PARTIDO_TEMA} o menos, elígelas todas.
No valores si son buenas o malas.

Responde SOLO con JSON: {{"ids": [int, ...]}}"""


def seleccionar(conn, llm, anio: int, temas: list[str]) -> int:
    """Una llamada por (partido, tema) aún no hecho. Reanudable: el par se marca cuando su selección está guardada."""
    hechos = {(r["partido"], r["tema"]) for r in conn.execute("SELECT partido, tema FROM test_hechos WHERE anio = ?", (anio,))}
    grupos: dict[tuple, list] = {}
    vistos = set()
    for p in conn.execute(f"SELECT id, partido, tema, texto FROM promesas WHERE anio = ? AND procedimental = 0 "
                          f"AND tema IN ({','.join('?' * len(temas))}) ORDER BY id", (anio, *temas)):
        if (p["partido"], p["tema"]) in hechos or (p["partido"], p["texto"]) in vistos:
            continue
        vistos.add((p["partido"], p["texto"]))
        grupos.setdefault((p["partido"], p["tema"]), []).append(p)
    n = 0
    for (partido, tema), promesas in grupos.items():
        lista = "\n".join(f"[id={p['id']}] {p['texto']}" for p in promesas)
        try:
            out = llm.json(MODELO, SISTEMA_SELECCION, f"Tema: {tema}\n\nSELECCIONAR:\n{lista}", max_tokens=300)
        except PresupuestoAgotado:
            break
        if out is None:
            continue
        validos = {p["id"] for p in promesas}
        ids = [int(i) for i in out.get("ids", []) if str(i).isdigit()]
        elegidos = [i for i in dict.fromkeys(ids) if i in validos][:MAX_POR_PARTIDO_TEMA]
        for i in elegidos:
            conn.execute("INSERT OR IGNORE INTO test_propuestas (promesa_id, anio, partido, tema) VALUES (?,?,?,?)",
                         (i, anio, partido, tema))
        conn.execute("INSERT INTO test_hechos VALUES (?,?,?)", (anio, partido, tema))
        conn.commit()
        n += len(elegidos)
    return n


SISTEMA_RESUMEN = """Resumes una propuesta de un programa electoral español para un test donde la gente la vota SIN SABER
de qué partido es. Tu resumen es lo único que verán antes de votar.

Escribe 2-4 frases en castellano con lo CRÍTICO: qué se hace, a quién afecta, cuánto (si el programa lo dice) y cómo
se paga (si el programa lo dice). Nada de titulares vacíos: «bajar impuestos» no vale; «bajar el IRPF a las rentas de
menos de 30.000 euros» sí, si el texto lo dice.

Reglas de neutralidad (obligatorias):
- Ni el nombre del partido ni el de sus líderes, ni ninguna pista de quién gobierna o gobernó.
- Nada de primera persona («haremos», «nuestro»): describe la medida en impersonal.
- Nada de balance de gestión («como ya hicimos», «seguiremos»). Tampoco digas que la medida ya existe, se
  amplía o se mantiene, ni qué gobierno o institución la aplica hoy: describe lo que quedaría tras aplicarla
  (no «se amplía hasta 37.800 € el umbral de las ayudas a hipotecados», sino «ayudas a hipotecados con ingresos
  de hasta 37.800 €»).
- Nada de nombres propios de organismos de un partido o de una comunidad salvo que sean el objeto: usa una
  descripción genérica («el organismo público de vivienda de Galicia»).
- Nada de léxico identitario o de marca («Euskal Herria», «la Nación española», «justicia climática», «Països
  Catalans»). Si el territorio o la identidad es el objeto mismo de la propuesta, usa el término jurídico neutro
  (p. ej. «la Comunidad Autónoma del País Vasco», «Cataluña»).
- Ninguna cifra, plazo o dato que no esté en el texto del programa. Si el programa no concreta, no inventes.
- No valores la propuesta.

Además:
- "concreta": false SOLO si no se sabe qué medida se tomaría: intenciones como «mejorar», «impulsar», «apostar
  por», «avanzar hacia» sin decir cómo. Si se sabe qué se hace (crear un impuesto, subir un tipo, extender una
  deducción, construir viviendas), es true aunque falten cifras, plazos o financiación.
- "materias": claves de la lista de MATERIAS que describen lo que haría falta jurídicamente para aprobarla.
  Varias si aplica. Ninguna si no encaja ninguna.
- "coste": true si implica gasto público o pérdida de ingresos.

Responde SOLO con JSON: {"resumen": str, "concreta": bool, "materias": [str], "coste": bool}"""


def materias_validas(raiz: Path) -> dict:
    """Clave -> descripción para el modelo, de config/condiciones.json."""
    tabla = json.loads((raiz / "config" / "condiciones.json").read_text(encoding="utf-8"))
    return {k: v["descripcion_para_el_modelo"] for k, v in tabla["materias"].items()}


def _resumir_una(conn, llm, fila, materias: dict, pista: str | None = None) -> bool:
    lista = "\n".join(f"- {k}: {d}" for k, d in materias.items())
    usuario = (f"MATERIAS:\n{lista}\n\nTema: {fila['tema']}\n\nRESUMIR:\nPROMESA: {fila['texto']}\n"
               f"CITA LITERAL: {fila['cita']}\n\nTEXTO DEL PROGRAMA DE DONDE SALE:\n{fila['bloque']}")
    if pista:
        usuario += f"\n\nREESCRIBE: {pista}\nResumen anterior: {fila['resumen']}"
    out = llm.json(MODELO, SISTEMA_RESUMEN, usuario, max_tokens=600)
    if not out or not str(out.get("resumen", "")).strip():
        return False
    elegidas = [m for m in dict.fromkeys(out.get("materias") or []) if m in materias]
    conn.execute("UPDATE test_propuestas SET resumen = ?, concreta = ?, materias = ?, coste = ? WHERE promesa_id = ?",
                 (out["resumen"].strip(), int(out.get("concreta") is not False), json.dumps(elegidas),
                  int(bool(out.get("coste"))), fila["promesa_id"]))
    return True


FILAS = """SELECT t.*, p.texto, p.cita, b.texto AS bloque FROM test_propuestas t
           JOIN promesas p ON p.id = t.promesa_id JOIN bloques b ON b.id = p.bloque_id WHERE t.anio = ?"""


def resumir(conn, llm, anio: int, raiz: Path) -> int:
    """Resume las propuestas sin resumen. Reanudable."""
    materias = materias_validas(raiz)
    pendientes = conn.execute(FILAS + " AND t.resumen IS NULL", (anio,)).fetchall()

    def una(f):
        try:
            return _resumir_una(conn, llm, f, materias)
        except PresupuestoAgotado:
            return False

    with ThreadPoolExecutor(8) as ex:
        n = sum(ex.map(una, pendientes))
    conn.commit()
    return n


SISTEMA_ADIVINO = """Te dan el resumen de una propuesta de un programa electoral español de este año y la lista de partidos.
Di de qué partido crees que es. Si no hay pistas, elige igualmente el más probable.

Di también QUÉ te dio la pista:
- "forma": una palabra, expresión, nombre propio, tono o referencia (a un gobierno, a una gestión pasada, a un
  organismo) que delata al partido aunque la medida la pudiera proponer otro.
- "postura": la medida en sí, es decir, la posición política que defiende. Otro redactado no lo cambiaría.

Responde SOLO con JSON: {"partido": str, "pista": "forma"|"postura", "por_que": str}"""


def neutralidad(conn, llm, anio: int, raiz: Path) -> dict:
    """Otro modelo intenta adivinar el partido y dice qué le dio la pista. Solo una fuga de FORMA se reescribe
    (como mucho MAX_REESCRITURAS veces) y, si sigue, queda marcada `delata` para Fran. Acertar por la POSTURA es
    adivinar la propuesta misma: no se toca (Fran, 2026-10-30). Reanudable."""
    materias = materias_validas(raiz)
    partidos = [r["partido"] for r in conn.execute("SELECT DISTINCT partido FROM promesas WHERE anio = ? ORDER BY partido", (anio,))]
    pendientes = conn.execute(FILAS + " AND t.resumen IS NOT NULL AND t.adivinado IS NULL", (anio,)).fetchall()

    def adivinar(resumen):
        out = llm.json(ADIVINO, SISTEMA_ADIVINO, f"Partidos: {', '.join(partidos)}\n\nADIVINAR:\n{resumen}", max_tokens=150) or {}
        pista = out.get("pista") if out.get("pista") in ("forma", "postura") else "forma"   # ante la duda, se reescribe
        return out.get("partido"), f"{pista}: {out.get('por_que') or ''}".strip()

    def una(f):
        f = dict(f)
        try:
            adivinado, pista = adivinar(f["resumen"])
            while adivinado == f["partido"] and pista.startswith("forma") and f["reescrituras"] < MAX_REESCRITURAS:
                if not _resumir_una(conn, llm, f, materias, f"el adivinador lo atribuyó a su partido por esto: «{pista}»; "
                                                           "quítalo sin cambiar el fondo de la medida"):
                    break
                f["reescrituras"] += 1
                f["resumen"] = conn.execute("SELECT resumen FROM test_propuestas WHERE promesa_id = ?", (f["promesa_id"],)).fetchone()[0]
                adivinado, pista = adivinar(f["resumen"])
        except PresupuestoAgotado:
            return
        if adivinado is None:
            return
        delata = adivinado == f["partido"] and pista.startswith("forma")
        conn.execute("UPDATE test_propuestas SET adivinado = ?, pista = ?, reescrituras = ?, delata = ? WHERE promesa_id = ?",
                     (adivinado, pista, f["reescrituras"], int(delata), f["promesa_id"]))

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(una, pendientes))
    conn.commit()
    filas = conn.execute("SELECT partido, adivinado, delata FROM test_propuestas WHERE anio = ? AND adivinado IS NOT NULL", (anio,)).fetchall()
    return {"total": len(filas), "acertadas_al_final": sum(r["partido"] == r["adivinado"] for r in filas),
            "delata": sum(r["delata"] for r in filas)}


SIMILITUD_CRUCE = 0.95      # medido 2026-10-30: promesas repetidas 0,95-0,99; del mismo tema pero distintas, hasta ~0,946
CASILLAS = ("Publicar", "Descartar", "El cruce 2023 es la misma promesa")


def cruces_firmes(conn, raiz: Path) -> dict:
    """promesa de 2023 -> cruces firmes (los que la web publica como veredicto), el más reciente primero."""
    from src.electoral import exportar
    fechas = {r["id"]: r["fecha"] for r in conn.execute("SELECT id, fecha FROM votaciones")}
    firmes: dict[int, list] = {}
    for c in exportar._cruces(conn, exportar._confirmados(raiz / "config" / "revision_manual.json")):
        if c["nivel"] == "veredicto":
            firmes.setdefault(c["promesa_id"], []).append(c)
    for lista in firmes.values():
        lista.sort(key=lambda c: fechas.get(c["votacion_id"]) or "", reverse=True)
    return firmes


def _candidatos_cruce(conn, raiz: Path, filas) -> dict:
    """promesa del año -> (promesa de 2023 del mismo partido con cruce firme, su texto, su cruce más reciente)."""
    import numpy as np
    from src.electoral import juez
    from src.embeddings import from_blob
    firmes = cruces_firmes(conn, raiz)
    if not firmes:
        return {}
    juez.asegurar_embeddings(conn)
    previas = conn.execute(f"SELECT id, partido, texto, embedding FROM promesas WHERE id IN ({','.join('?' * len(firmes))})",
                           list(firmes)).fetchall()
    salida = {}
    for f in filas:
        propia = conn.execute("SELECT embedding FROM promesas WHERE id = ?", (f["promesa_id"],)).fetchone()[0]
        if propia is None:
            continue
        v = from_blob(propia)
        mejor = None
        for p in previas:
            if p["partido"] != f["partido"] or p["id"] == f["promesa_id"]:
                continue
            w = from_blob(p["embedding"])
            sim = float(np.dot(v, w) / (np.linalg.norm(v) * np.linalg.norm(w)))
            if sim >= SIMILITUD_CRUCE and (mejor is None or sim > mejor[0]):
                mejor = (sim, p)
        if mejor:
            salida[f["promesa_id"]] = (mejor[1]["id"], mejor[1]["texto"], firmes[mejor[1]["id"]][0])
    return salida


def frase_cruce(veredicto: str) -> str:
    return "votó de acuerdo con su promesa" if veredicto == "cumple" else "votó en contra de su promesa"


def _decididas(destino: Path, anio: int) -> tuple[list, list]:
    """Lo que Fran ya aprobó y descartó ese año en config/test_ciegas.json."""
    datos = json.loads(destino.read_text(encoding="utf-8")) if destino.exists() else {}
    return datos.get(str(anio), []), datos.get("descartadas", {}).get(str(anio), [])


def generar_revision(conn, raiz: Path, anio: int, salida: Path, destino: Path) -> int:
    """Solo trae lo que Fran aún no ha decidido: un programa que llega tarde no reabre lo ya revisado."""
    from src.electoral import condiciones
    tabla = condiciones.cargar(raiz)
    aprobadas, descartadas = _decididas(destino, anio)
    hechas = {a["promesa_id"] for a in aprobadas} | set(descartadas)
    filas = [f for f in conn.execute(FILAS.replace("SELECT t.*", "SELECT t.*, p.pagina, b.url_programa")
                                     + " AND t.resumen IS NOT NULL ORDER BY t.tema, t.partido, t.promesa_id", (anio,))
             if f["promesa_id"] not in hechas]
    cruces = _candidatos_cruce(conn, raiz, filas)
    expedientes = {r["id"]: r["expediente"] for r in conn.execute("SELECT id, expediente FROM votaciones")}
    L = [f"# Revisión del test a ciegas ({anio})", "",
         "Marca «Publicar» o «Descartar» en cada tarjeta. Si el resumen no vale, escribe el bueno tras «Resumen corregido:».",
         "Si hay posible cruce con 2023, márcalo solo si es la misma promesa. Sin marca, la tarjeta no se publica."]
    for n, f in enumerate(filas, 1):
        cond = condiciones.resolver(json.loads(f["materias"] or "[]"), bool(f["coste"]), tabla)
        etiquetas = "; ".join(c["etiqueta"] for c in cond["condiciones"]) or "ninguna"
        L += ["", f"## {n} · id={f['promesa_id']} · {f['tema']} · {f['partido']}",
              f"**Resumen:** {f['resumen']}",
              f"**Concreta:** {'sí' if f['concreta'] else 'no'} · **Condiciones:** {etiquetas}"
              + (" · **INVIABLE**" if cond["inviable"] else ""),
              f"**Cita (p. {f['pagina']}):** «{f['cita']}» ({f['url_programa']}#page={f['pagina']})"]
        if f["delata"]:
            L.append(f"⚠️ Se delata por la forma: {f['pista']}")
        elif f["adivinado"] == f["partido"]:
            L.append(f"(El adivinador acierta por la postura, no se toca: {f['pista']})")
        if f["promesa_id"] in cruces:
            pid, texto, c = cruces[f["promesa_id"]]
            L.append(f"**Posible cruce 2023:** «{texto}» (id={pid}), {frase_cruce(c['veredicto'])} en "
                     f"«{(expedientes.get(c['votacion_id']) or '')[:200]}»")
        L += [f"- [ ] {c}" for c in CASILLAS] + ["Resumen corregido:"]
    salida.write_text("\n".join(L) + "\n", encoding="utf-8")
    return len(filas)


def aprobar(conn, raiz: Path, anio: int, revision: Path, destino: Path) -> int:
    """Lo marcado «Publicar» se suma a config/test_ciegas.json y lo marcado «Descartar» se apunta para no volver a
    revisarlo. Lo decidido antes se conserva (una tarjeta que se vuelve a decidir sustituye a la anterior)."""
    import re
    from datetime import date
    previas, descartadas = _decididas(destino, anio)
    aprobadas, descartes = [], []
    for tarjeta in revision.read_text(encoding="utf-8").split("\n## ")[1:]:
        pid = int(re.search(r"id=(\d+)", tarjeta).group(1))
        marcada = {c: bool(re.search(r"- \[[xX]\] " + re.escape(c), tarjeta)) for c in CASILLAS}
        if marcada["Publicar"] and marcada["Descartar"]:
            raise SystemExit(f"La tarjeta id={pid} está marcada como Publicar y Descartar a la vez")
        if marcada["Descartar"]:
            descartes.append(pid)
        if not marcada["Publicar"]:
            continue
        f = conn.execute("SELECT * FROM test_propuestas WHERE promesa_id = ?", (pid,)).fetchone()
        corregido = tarjeta.split("Resumen corregido:", 1)[1].strip() if "Resumen corregido:" in tarjeta else ""
        cruce = re.search(r"\*\*Posible cruce 2023:\*\*.*?\(id=(\d+)\)", tarjeta)
        aprobadas.append({"promesa_id": pid, "resumen": corregido or f["resumen"], "concreta": bool(f["concreta"]),
                          "materias": json.loads(f["materias"] or "[]"), "coste": bool(f["coste"]),
                          "promesa_2023_id": int(cruce.group(1)) if cruce and marcada[CASILLAS[2]] else None,
                          "revisado_por": "Fran", "fecha": date.today().isoformat()})
    nuevas = {a["promesa_id"] for a in aprobadas} | set(descartes)
    datos = json.loads(destino.read_text(encoding="utf-8")) if destino.exists() else {}
    datos[str(anio)] = [a for a in previas if a["promesa_id"] not in nuevas] + aprobadas
    datos.setdefault("descartadas", {})[str(anio)] = sorted((set(descartadas) - {a["promesa_id"] for a in aprobadas}) | set(descartes))
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(datos[str(anio)])
