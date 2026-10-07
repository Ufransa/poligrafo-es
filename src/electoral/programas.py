# src/electoral/programas.py
"""Programas electorales: PDF → bloques con página → promesas sueltas con tema."""
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pdfplumber
import requests

from src.electoral.llm import PresupuestoAgotado

MODELO_EXTRACCION = "deepseek/deepseek-v4-flash"
CARACTERES_POR_BLOQUE = 3000

TEMAS = ["Vivienda", "Inmigración", "Sanidad", "Educación", "Empleo y trabajo", "Pensiones", "Fiscalidad",
         "Economía e industria", "Energía y clima", "Agricultura y medio rural", "Justicia",
         "Seguridad e interior", "Organización territorial", "Igualdad y derechos sociales",
         "Política exterior y defensa", "Instituciones y calidad democrática", "Cultura y lengua"]

SISTEMA = f"""Extraes PROMESAS de un fragmento de programa electoral español.

Una promesa es un COMPROMISO DE ACCIÓN FUTURA, CONCRETO Y VERIFICABLE: aprobar, derogar, crear,
subir, bajar, prohibir, reformar algo identificable. Cada promesa es una sola acción.
También son promesas los compromisos de MANTENER o de OPONERSE a algo concreto ("mantenemos el
actual modelo de elección del CGPJ", "nos opondremos a cualquier copago").

NO son promesas (descártalas):
- Logros pasados o balance de gestión ("hemos aprobado", "se ha puesto en marcha"), aunque aparezcan en una lista.
- Diagnósticos, críticas a otros partidos, valores y declaraciones genéricas.
- Paraguas que valdrían para cualquier tema ("mejorar la cooperación", "defender los derechos").

Para cada promesa devuelve:
- "promesa": una frase en castellano, autocontenida (máx. 30 palabras). Si el original está en otra lengua, tradúcela fielmente.
- "cita": el fragmento literal del original que la contiene (máx. 40 palabras), sin traducir.
- "tema": exactamente uno de: {", ".join(TEMAS)}.
- "procedimental": true si la promesa trata del procedimiento parlamentario o legislativo (uso del decreto-ley,
  de la urgencia, del reglamento de las Cámaras) y no de una materia; false en otro caso.

No inventes nada que no esté en el texto. Responde SOLO con JSON:
{{"promesas": [{{"promesa": str, "cita": str, "tema": str, "procedimental": bool}}]}}"""


def leer_pdf(origen: str) -> bytes:
    if Path(origen).exists():
        return Path(origen).read_bytes()
    r = requests.get(origen, timeout=(10, 120), headers={"User-Agent": "PoligrafoES/1.0"})
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise ValueError(f"{origen} no devuelve un PDF")
    return r.content


def bloques_por_pagina(pdf: bytes) -> list[tuple[int, str]]:
    """Bloques de ~3.000 caracteres sin partir páginas por la mitad; cada bloque guarda su primera página."""
    bloques, actual, pagina_inicio = [], "", None
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        for n, pagina in enumerate(doc.pages, start=1):
            texto = " ".join((pagina.extract_text() or "").split())
            if not texto:
                continue
            if pagina_inicio is None:
                pagina_inicio = n
            actual += ("\n" if actual else "") + texto
            if len(actual) >= CARACTERES_POR_BLOQUE:
                bloques.append((pagina_inicio, actual)); actual, pagina_inicio = "", None
    if actual:
        bloques.append((pagina_inicio, actual))
    return bloques


def ingerir(conn, anio: int, partido: str, origen: str) -> int:
    url = origen if not Path(origen).exists() else Path(origen).resolve().as_uri()
    n = 0
    for pagina, texto in bloques_por_pagina(leer_pdf(origen)):
        cur = conn.execute("INSERT OR IGNORE INTO bloques (partido, anio, pagina, texto, url_programa) VALUES (?,?,?,?,?)",
                           (partido, anio, pagina, texto, url))
        n += cur.rowcount
    conn.commit()
    return n


def extraer(conn, llm) -> None:
    """Extrae los bloques pendientes. Reanudable: un bloque solo se marca cuando sus promesas están guardadas."""
    pendientes = conn.execute("SELECT * FROM bloques WHERE extraido = 0").fetchall()

    def uno(b):
        out = llm.json(MODELO_EXTRACCION, SISTEMA, f"Partido: {b['partido']}\n\nFRAGMENTO:\n{b['texto']}", max_tokens=3000)
        return b, out

    with ThreadPoolExecutor(8) as ex:
        futuros = [ex.submit(uno, b) for b in pendientes]
        for f in futuros:
            try:
                b, out = f.result()
            except PresupuestoAgotado:
                continue
            if out is None:
                continue
            for p in out.get("promesas", []):
                tema = p.get("tema") if p.get("tema") in TEMAS else "Instituciones y calidad democrática"
                conn.execute("INSERT INTO promesas (bloque_id, partido, anio, pagina, texto, cita, tema, procedimental) VALUES (?,?,?,?,?,?,?,?)",
                             (b["id"], b["partido"], b["anio"], b["pagina"], p["promesa"], p.get("cita", ""), tema, int(bool(p.get("procedimental")))))
            conn.execute("UPDATE bloques SET extraido = 1 WHERE id = ?", (b["id"],))
            conn.commit()
