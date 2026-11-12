"""Normas que mezclan asuntos (ómnibus) y enmiendas sueltas del Senado: votar en contra puede deberse a una parte
que no tiene que ver con la promesa (Fran, 2026-10-31)."""
import json
import os
import re
import time

import requests

from src.electoral.llm import PresupuestoAgotado

MODELO = "deepseek/deepseek-v4-flash"
API_TEXTO = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{}/texto"
# Disposiciones de trámite que llevan todas las normas: no dicen nada del contenido.
RUTINA = re.compile(r"[Tt]ítulos? competencial|[Ee]ntrada en vigor|[Ff]acultades de desarrollo|[Hh]abilitación normativa|"
                    r"[Ss]alvaguardia del rango|[Dd]erogación normativa|[Ii]ncorporación de [Dd]erecho")
TITULO_MEZCLA = re.compile(r"y otras medidas|otras? normas? |otra normativa|diversas (leyes|normas|medidas)", re.I)

SISTEMA = """Te doy el título de una norma española (ley o real decreto-ley) y el arranque de cada uno de sus artículos y
disposiciones, según el BOE. Di si la norma mete asuntos que NO tienen que ver con su título: cambios en materias
ajenas a lo que anuncia (por ejemplo, una ley de pensiones que cede un edificio o cambia un impuesto que no es de
pensiones). NO es mezclar: modificar varias leyes del mismo asunto, ni usar otra ley como herramienta para el fin del
título (una exención de IRPF para las ayudas a los damnificados, un plan de movilidad al trabajo en una ley de
movilidad). Ante la duda, false.

"ajenos": SOLO los asuntos ajenos al título, cada uno en pocas palabras y en castellano llano (por ejemplo, «el IRPF»
o «la seguridad privada»). Nunca pongas ahí una norma del mismo asunto que el título ni la relación («modifica…»).
Vacío si no hay.

Responde SOLO con JSON: {"mezcla": bool, "ajenos": [str]}"""


def enmienda_suelta_del_senado(tipo: str | None, expediente: str | None) -> bool:
    return (tipo or "").startswith("Enmiendas del Senado") and         re.search(r"votación (en bloque )?de (la|las) enmiendas?", (expediente or "").lower()) is not None


def nota(conn, v) -> dict | None:
    """La nota de la web para una votación, o None."""
    ident = conn.execute("SELECT identificador FROM boe WHERE clave = ?", (v["clave_iniciativa"],)).fetchone()
    fila = conn.execute("SELECT * FROM mezclas WHERE identificador = ?", (ident[0],)).fetchone() if ident and ident[0] else None
    if fila and fila["mezcla"]:
        ajenos = json.loads(fila["ajenos"] or "[]")
        lista = "; ".join(ajenos[:4]) + (f" y {len(ajenos) - 4} más" if len(ajenos) > 4 else "")
        return {"motivo": f"Esta norma también toca asuntos que no anuncia su título: {lista}. "
                          "El voto puede deberse a esa otra parte."}
    if TITULO_MEZCLA.search(v["expediente"] or ""):
        return {"motivo": "El propio título dice que la norma mezcla varios asuntos: el voto puede deberse a otra parte."}
    return None


def _preceptos(ident: str) -> list[str] | None:
    """Cada artículo y disposición de la norma: su título y el arranque de su texto (versión vigente)."""
    falso = os.environ.get("ELECTORAL_BOE_TEXTO_FALSO")
    if falso:
        return json.loads(open(falso, encoding="utf-8").read()).get(ident)
    import xml.etree.ElementTree as ET
    try:
        r = requests.get(API_TEXTO.format(ident), headers={"Accept": "application/xml", "User-Agent": "PoligrafoES/1.0"},
                         timeout=60)
        raiz = ET.fromstring(r.content)
    except (requests.RequestException, ET.ParseError):
        return None
    finally:
        time.sleep(0.5)
    salida = []
    for b in raiz.iter("bloque"):
        if b.get("tipo") != "precepto" or RUTINA.search(b.get("titulo") or ""):
            continue
        versiones = b.findall("version")
        texto = " ".join(" ".join(p.itertext()) for p in (versiones[-1] if versiones else b).iter("p"))
        texto = " ".join(texto.split())
        if not RUTINA.search(texto[:200]):
            salida.append(texto[:260])
    return salida[:150]


def revisar(conn, llm, boe: dict) -> dict:
    """Mira con el modelo cada norma votada en el Pleno con BOE conocido y aún no revisada. Reanudable."""
    hechas = {r[0] for r in conn.execute("SELECT identificador FROM mezclas")}
    normas = {}
    for v in conn.execute("SELECT clave_iniciativa, expediente FROM votaciones WHERE excluida_tramite = 0 ORDER BY fecha"):
        ident = boe.get(v["clave_iniciativa"])
        if ident and ident not in hechas:
            normas.setdefault(ident, v["expediente"].split("\n")[0])
    for ident, titulo in normas.items():
        afectadas = _preceptos(ident)
        if afectadas is None:
            continue
        if not afectadas:
            conn.execute("INSERT INTO mezclas VALUES (?, 0, '[]')", (ident,))
            conn.commit()
            continue
        try:
            out = llm.json(MODELO, SISTEMA, f"MEZCLA:\nNORMA: {titulo}\nARTÍCULOS Y DISPOSICIONES:\n" + "\n".join(f"- {a}" for a in afectadas),
                           max_tokens=300)
        except PresupuestoAgotado:
            break
        if out is None:
            continue
        ajenos = [str(a) for a in out.get("ajenos") or []]
        conn.execute("INSERT INTO mezclas VALUES (?, ?, ?)", (ident, int(out.get("mezcla") is True and bool(ajenos)),
                                                           json.dumps(ajenos, ensure_ascii=False)))
        conn.commit()
    total = conn.execute("SELECT COUNT(*), COALESCE(SUM(mezcla), 0) FROM mezclas").fetchone()
    return {"total": total[0], "mezclan": total[1]}
