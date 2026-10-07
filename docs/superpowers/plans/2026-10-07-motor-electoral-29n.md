# Motor electoral 29N: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que `python electoral.py todo` genere `datos.json` (votaciones de la XV, promesas con tema, cruces juzgados, coherencia, gobierno y finanzas) con sus fuentes oficiales, listo para que lo lea la web.

**Architecture:** Un CLI nuevo (`electoral.py`) y módulos nuevos en `src/electoral/`, con su propia base de datos `electoral.db`. **No toca** el bot de Telegram (`fetcher.py`, `digest.py`, `poligrafo.db`). Cada paso del CLI es reanudable: lo ya hecho en `electoral.db` no se repite. El LLM va por OpenRouter con tope de gasto. Las pruebas son de comportamiento: ejecutan el CLI sobre ZIPs reales del Congreso con un LLM falso y comprueban el `datos.json` resultante.

**Tech Stack:** Python 3.12, SQLite, requests, pdfplumber, sentence-transformers (`intfloat/multilingual-e5-small`), numpy, jsonschema, pytest.

**Spec:** `docs/superpowers/specs/2026-10-07-web-electoral-29n-design.md`

Este es el **plan 1 de 2**. El plan 2 (web Astro, despliegue en Cloudflare Pages, cron en la Pi y ARGUS) consume el contrato `schema/datos.schema.json` que produce la tarea 8.

## Global Constraints

- Presupuesto LLM: **10 € en total** para todo el proyecto; ya gastados 1,06 $. Ningún modelo de Anthropic. Todo vía OpenRouter con `OPENROUTER_API_KEY` del `.env`.
- Modelos: extracción `deepseek/deepseek-v4-flash`; jueces `deepseek/deepseek-v4-pro`, `openai/gpt-5-mini` y `google/gemini-2.5-flash-lite`. Razonamiento: `{"enabled": false}` en DeepSeek y `{"effort": "minimal"}` en OpenAI.
- Periodo: solo la XV legislatura (`Leg15`, desde el 2023-08-17).
- Veredicto publicado = los 3 jueces coinciden en el veredicto y los 3 dicen `fuerza: directa`. «Juzga tú» = al menos 2 coinciden en el veredicto. Lo demás no se exporta.
- Todo dato exportado lleva su URL de fuente.
- El contrato no lleva colores, orden ni textos valorativos.
- Pruebas de comportamiento, **nunca unitarias**: se invoca el CLI y se inspecciona `datos.json`.
- Textos en español de Canarias (`ustedes`, nunca `vosotros`), sin rayas largas en textos publicables.
- Commits en Conventional Commits, en inglés y en minúsculas.

## Review Focus

1. **Un diputado que cambia de grupo a mitad de legislatura** (Ábalos sale del PSOE el 2024-02-27; Podemos pasa al Mixto el 2023-12-12; Micó, de Compromís, el 2025-07-08; Ortega Smith deja Vox el 2026-07-23): sus votos deben contar para el partido correcto en cada fecha, y nunca para un independiente. Prueba en la tarea 1.
2. **Un decreto-ley derogado** (convalidación rechazada): no puede aparecer en «Lo que hizo gobernando». Prueba en la tarea 6.
3. **Un partido que vota dividido** (más del 10 % del grupo en contra de la mayoría): su cruce nunca llega a «veredicto», como mucho a «juzga tú». Prueba en la tarea 4.
4. **Un partido sin programa propio en 2023** (Podemos, Compromís, SALF): aparece en `partidos` con su motivo, sin promesas ni cruces, y la exportación no falla. Prueba en la tarea 3.
5. **El presupuesto se agota o OpenRouter falla a mitad de la carga**: no se exportan cruces de expedientes a medio juzgar, y al relanzar se continúa sin repetir ni duplicar. Prueba en la tarea 4.

---

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `electoral.py` | CLI: `descargar`, `ingest-programa`, `extraer`, `juzgar`, `exportar`, `muestra`, `todo` |
| `src/electoral/__init__.py` | Vacío |
| `src/electoral/db.py` | Esquema y acceso a `electoral.db` |
| `src/electoral/votaciones.py` | Descarga de ZIPs, lectura voto a voto, clasificación, clave de iniciativa, votos por partido |
| `src/electoral/llm.py` | Cliente OpenRouter con tope de gasto, reintentos y transporte inyectable |
| `src/electoral/programas.py` | PDF → bloques con página → promesas con tema |
| `src/electoral/juez.py` | Candidatos normalizados por programa, tres jueces, nivel del cruce |
| `src/electoral/fuentes.py` | URL del Congreso, BOCG, BOE y programa |
| `src/electoral/analisis.py` | Coherencia, gobierno y temas |
| `src/electoral/exportar.py` | Construye y valida `datos.json` |
| `config/diputados.json` | Diputado → partido con fechas (Mixto y cambios de grupo) |
| `config/partidos_electoral.json` | Partidos, escaños 23J, Gobierno, programa 2023 o motivo de que no haya |
| `config/finanzas_2023.json` | Cifras transcritas del Tribunal de Cuentas, con página |
| `schema/datos.schema.json` | Contrato con la web |
| `tests/electoral/conftest.py` | ZIPs de prueba, LLM falso, ejecutor del CLI |
| `tests/electoral/test_*.py` | Pruebas de comportamiento por tarea |
| `tests/fixtures/electoral/` | ZIPs reales, PDF de prueba, `referencia.json` (los 19 casos revisados por Fran, ya guardado) |

---

### Task 1: Votaciones de la legislatura, clasificadas y por partido

**Files:**
- Create: `electoral.py`, `src/electoral/__init__.py`, `src/electoral/db.py`, `src/electoral/votaciones.py`, `src/electoral/exportar.py`, `config/diputados.json`, `config/partidos_electoral.json`, `tests/electoral/__init__.py`, `tests/electoral/conftest.py`, `tests/electoral/test_votaciones.py`
- Modify: `.gitignore` (añadir `electoral.db`, `datos.json`, `electoral_data/`), `requirements.txt` (añadir `jsonschema`)

**Interfaces:**
- Produces: `python electoral.py descargar [--zips DIR] [--db RUTA]`, `python electoral.py exportar [--db RUTA] [--salida RUTA]`. En `datos.json`: `meta`, `partidos[]` y `votaciones[]` con `{id, fecha, sesion, numero, tipo, subtipo, expediente, clave_iniciativa, resultado, a_favor, en_contra, abstenciones, excluida_tramite, votos: {partido: {voto, dividido}}, url_xml, url_sesion}`.
- `src/electoral/votaciones.py`: `leer_zip(ruta: Path) -> list[dict]`, `clasificar(v: dict) -> tuple[str, bool]` (subtipo ∈ `normal|devolucion|texto_alternativo|tramite`, `es_convalidacion`), `clave_iniciativa(texto: str) -> str`, `votos_por_partido(v: dict, mapa: dict) -> dict`.
- `src/electoral/db.py`: `conectar(ruta: Path) -> sqlite3.Connection` (crea el esquema).

- [ ] **Step 1: Preparar dependencias y `.gitignore`**

```bash
cd D:/1.Fran/DEV/poligrafo-es
echo "jsonschema" >> requirements.txt
pip install jsonschema
printf "\nelectoral.db\ndatos.json\nelectoral_data/\n" >> .gitignore
```

- [ ] **Step 2: Descargar los ZIPs de prueba (reales)**

Cuatro sesiones cubren todos los casos: avocación (20/3/2025), devolución de la ley de lobbies (25/3/2025), texto alternativo de la amnistía (10/1/2024), convalidación y tramitación del decreto-ley 3/2026 (26/2/2026), y diputados del Mixto (todas).

```bash
mkdir -p tests/fixtures/electoral/zips
python - <<'E'
import re, requests, time
H = {"User-Agent": "PoligrafoES/1.0"}
base = "https://www.congreso.es/es/opendata/votaciones?p_p_id=votaciones&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&targetLegislatura=XV&targetDate="
for d in ["10/01/2024", "20/03/2025", "25/03/2025", "26/02/2026"]:
    html = requests.get(base + d, headers=H, timeout=30).text
    ymd = d[6:] + d[3:5] + d[:2]
    for path in sorted(set(re.findall(r"/webpublica/opendata/votaciones/Leg15/Sesion\d+/" + ymd + r"/VOT_[^\"']+\.zip", html))):
        open("tests/fixtures/electoral/zips/" + path.rsplit("/", 1)[1], "wb").write(requests.get("https://www.congreso.es" + path, headers=H, timeout=60).content)
        time.sleep(1.5)
E
ls tests/fixtures/electoral/zips
```

Expected: 4 o más archivos `VOT_*.zip`.

- [ ] **Step 3: Escribir `config/diputados.json` y `config/partidos_electoral.json`**

`config/diputados.json` (las fechas salen del XML real, primera votación en el grupo nuevo):

```json
{
  "grupos": {"GP": "PP", "GS": "PSOE", "GSUMAR": "Sumar", "GVOX": "Vox", "GR": "ERC", "GJxCAT": "Junts", "GEH Bildu": "EH Bildu", "GV (EAJ-PNV)": "PNV"},
  "mixto": [
    {"diputado": "Belarra Urteaga, Ione", "partido": "Podemos", "desde": "2023-12-12"},
    {"diputado": "Santana Perera, Noemí", "partido": "Podemos", "desde": "2023-12-12"},
    {"diputado": "Sánchez Serna, Javier", "partido": "Podemos", "desde": "2023-12-12"},
    {"diputado": "Velarde Gómez, Martina", "partido": "Podemos", "desde": "2023-12-12"},
    {"diputado": "Verstrynge Revuelta, Lilith", "partido": "Podemos", "desde": "2023-12-12"},
    {"diputado": "Catalán Higueras, Alberto", "partido": "UPN", "desde": "2023-08-17"},
    {"diputado": "Rego Candamil, Néstor", "partido": "BNG", "desde": "2023-08-17"},
    {"diputado": "Valido García, Cristina", "partido": "CC", "desde": "2023-08-17"},
    {"diputado": "Micó Micó, Àgueda", "partido": "Compromís", "desde": "2025-07-08"},
    {"diputado": "Ábalos Meco, José Luis", "partido": null, "desde": "2024-02-27", "motivo": "independiente tras salir del PSOE"},
    {"diputado": "Ortega Smith-Molina, Francisco Javier", "partido": null, "desde": "2026-07-23", "motivo": "independiente tras salir de Vox"}
  ]
}
```

`config/partidos_electoral.json` (escaños del 23J; `gobierno` = toda la XV para PSOE y Sumar):

```json
[
  {"id": "PP", "nombre": "Partido Popular", "escanos_23j": 137, "gobierno": [], "programa_2023": "https://www.pp.es/storage/2023/07/programa_electoral_pp_23j_feijoo_2023.pdf"},
  {"id": "PSOE", "nombre": "Partido Socialista Obrero Español", "escanos_23j": 121, "gobierno": [["2023-11-17", null]], "programa_2023": "https://www.elnacional.cat/uploads/s1/42/65/82/06/programa-electoral-psoe-eleccions-generals-2023-pedro-sanchez.pdf"},
  {"id": "Vox", "nombre": "Vox", "escanos_23j": 33, "gobierno": [], "programa_2023": "https://files.mediaset.es/file/2023/0707/15/programa-vox-completo-pdf.pdf"},
  {"id": "Sumar", "nombre": "Sumar", "escanos_23j": 31, "gobierno": [["2023-11-17", null]], "programa_2023": "https://www.newtral.es/wp-content/uploads/2023/07/Programa_electoral_sumar_23j_2023.pdf"},
  {"id": "ERC", "nombre": "Esquerra Republicana", "escanos_23j": 7, "gobierno": [], "programa_2023": "https://defensacatalunya.esquerrarepublicana.cat/documents/e2023-programa.pdf"},
  {"id": "Junts", "nombre": "Junts per Catalunya", "escanos_23j": 7, "gobierno": [], "programa_2023": "https://img.beteve.cat/wp-content/uploads/2023/07/programa-junts-per-catalunya-eleccions-generals-2023.pdf"},
  {"id": "EH Bildu", "nombre": "EH Bildu", "escanos_23j": 6, "gobierno": [], "programa_2023": "https://www.elnacional.cat/uploads/s1/42/81/42/33/programa-electoral-eh-bildu-eleccions-generals-2023.pdf"},
  {"id": "PNV", "nombre": "EAJ-PNV", "escanos_23j": 5, "gobierno": [], "programa_2023": "https://www.eaj-pnv.eus/es/adjuntos-documentos/20945/pdf/con-voz-propia-programa-electoral-23-j"},
  {"id": "BNG", "nombre": "Bloque Nacionalista Galego", "escanos_23j": 1, "gobierno": [], "programa_2023": null, "pendiente": "localizar PDF oficial (tarea 3)"},
  {"id": "CC", "nombre": "Coalición Canaria", "escanos_23j": 1, "gobierno": [], "programa_2023": null, "pendiente": "localizar PDF oficial (tarea 3)"},
  {"id": "UPN", "nombre": "Unión del Pueblo Navarro", "escanos_23j": 1, "gobierno": [], "programa_2023": null, "pendiente": "localizar PDF oficial (tarea 3)"},
  {"id": "Podemos", "nombre": "Podemos", "escanos_23j": 0, "gobierno": [["2023-11-17", "2023-12-12"]], "programa_2023": null, "sin_programa": "En 2023 se presentó dentro de Sumar: sus promesas de 2023 son las de Sumar."},
  {"id": "Compromís", "nombre": "Compromís", "escanos_23j": 0, "gobierno": [], "programa_2023": null, "sin_programa": "En 2023 se presentó dentro de Sumar: sus promesas de 2023 son las de Sumar."},
  {"id": "SALF", "nombre": "Se Acabó La Fiesta", "escanos_23j": 0, "gobierno": [], "programa_2023": null, "sin_programa": "No existía en 2023."}
]
```

- [ ] **Step 4: Escribir las pruebas que fallan** (`tests/electoral/conftest.py` y `tests/electoral/test_votaciones.py`)

```python
# tests/electoral/conftest.py
import json
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
FIX = RAIZ / "tests" / "fixtures" / "electoral"


@pytest.fixture
def cli(tmp_path):
    """Ejecuta electoral.py con una base y una salida temporales y devuelve datos.json ya leído."""
    db = tmp_path / "electoral.db"
    salida = tmp_path / "datos.json"

    def run(*args, env=None):
        cmd = [sys.executable, str(RAIZ / "electoral.py"), *args, "--db", str(db)]
        if args[0] == "exportar":
            cmd += ["--salida", str(salida)]
        r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", env=env)
        assert r.returncode == 0, r.stderr
        return json.loads(salida.read_text(encoding="utf-8")) if args[0] == "exportar" else r.stdout

    run.db = db
    return run


@pytest.fixture
def zips():
    return str(FIX / "zips")
```

```python
# tests/electoral/test_votaciones.py
def _cargar(cli, zips):
    cli("descargar", "--zips", zips)
    return cli("exportar")


def _buscar(datos, texto, subtipo=None):
    return [v for v in datos["votaciones"]
            if texto.lower() in v["expediente"].lower() and (subtipo is None or v["subtipo"] == subtipo)]


def test_una_avocacion_sale_excluida_por_tramite(cli, zips):
    datos = _cargar(cli, zips)
    avoc = [v for v in datos["votaciones"] if "avocación" in v["expediente"].lower()]
    assert avoc and all(v["excluida_tramite"] for v in avoc)


def test_la_devolucion_de_la_ley_de_lobbies_se_marca_como_devolucion(cli, zips):
    datos = _cargar(cli, zips)
    v = _buscar(datos, "grupos de interés", "devolucion")
    assert v and not v[0]["excluida_tramite"]


def test_el_texto_alternativo_no_se_trata_como_devolucion(cli, zips):
    datos = _cargar(cli, zips)
    assert _buscar(datos, "amnistía", "texto_alternativo")
    assert not _buscar(datos, "texto alternativo", "devolucion")


def test_en_un_decreto_ley_cuenta_la_convalidacion_y_no_la_tramitacion(cli, zips):
    datos = _cargar(cli, zips)
    rdl = [v for v in datos["votaciones"] if v["clave_iniciativa"] == "real decreto-ley 3/2026"]
    convalidacion = [v for v in rdl if not v["excluida_tramite"]]
    tramitacion = [v for v in rdl if v["excluida_tramite"]]
    assert len(convalidacion) == 1 and convalidacion[0]["tipo"].startswith("Convalidación")
    assert tramitacion, "la votación de tramitación como proyecto de ley debe existir y estar excluida"


def test_los_diputados_del_mixto_votan_con_su_partido(cli, zips):
    datos = _cargar(cli, zips)
    v = _buscar(datos, "grupos de interés", "devolucion")[0]
    for partido in ("Podemos", "BNG", "CC", "UPN"):
        assert partido in v["votos"], partido
    assert "Mixto" not in v["votos"]


def test_un_independiente_no_cuenta_para_ningun_partido(cli, zips):
    datos = _cargar(cli, zips)
    v = _buscar(datos, "grupos de interés", "devolucion")[0]   # 25/3/2025: Ábalos ya fuera del PSOE
    assert v["votos"]["PSOE"]["voto"] in ("Sí", "No", "Abstención")
    assert None not in v["votos"] and "null" not in v["votos"]


def test_cada_votacion_lleva_sus_fuentes(cli, zips):
    datos = _cargar(cli, zips)
    for v in datos["votaciones"]:
        assert v["url_xml"].startswith("https://www.congreso.es/webpublica/opendata/votaciones/Leg15/")
        assert "targetDate=" in v["url_sesion"]


def test_la_descarga_es_reanudable(cli, zips):
    cli("descargar", "--zips", zips)
    n1 = len(cli("exportar")["votaciones"])
    cli("descargar", "--zips", zips)
    assert len(cli("exportar")["votaciones"]) == n1
```

- [ ] **Step 5: Comprobar que fallan**

Run: `pytest tests/electoral/test_votaciones.py -v`
Expected: FAIL (`electoral.py` no existe).

- [ ] **Step 6: Implementar `src/electoral/db.py`**

```python
# src/electoral/db.py
import sqlite3
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS zips (nombre TEXT PRIMARY KEY, url TEXT, fecha TEXT);
CREATE TABLE IF NOT EXISTS votaciones (
    id TEXT PRIMARY KEY,            -- "<sesion>-<numero>"
    fecha TEXT, sesion INTEGER, numero INTEGER,
    tipo TEXT, subtipo TEXT, es_convalidacion INTEGER,
    expediente TEXT, texto_subgrupo TEXT, clave_iniciativa TEXT,
    resultado TEXT, a_favor INTEGER, en_contra INTEGER, abstenciones INTEGER,
    excluida_tramite INTEGER, url_xml TEXT, url_sesion TEXT
);
CREATE TABLE IF NOT EXISTS votos_partido (
    votacion_id TEXT, partido TEXT, voto TEXT, dividido INTEGER,
    PRIMARY KEY (votacion_id, partido)
);
CREATE TABLE IF NOT EXISTS bloques (
    id INTEGER PRIMARY KEY, partido TEXT, anio INTEGER, pagina INTEGER, texto TEXT,
    url_programa TEXT, extraido INTEGER DEFAULT 0,
    UNIQUE (partido, anio, pagina, texto)
);
CREATE TABLE IF NOT EXISTS promesas (
    id INTEGER PRIMARY KEY, bloque_id INTEGER, partido TEXT, anio INTEGER, pagina INTEGER,
    texto TEXT, cita TEXT, tema TEXT, procedimental INTEGER, embedding BLOB
);
CREATE TABLE IF NOT EXISTS juicios (
    votacion_id TEXT PRIMARY KEY, completo INTEGER DEFAULT 0, respuestas TEXT
);
CREATE TABLE IF NOT EXISTS cruces (
    votacion_id TEXT, promesa_id INTEGER, partido TEXT, nivel TEXT, veredicto TEXT, jueces TEXT,
    PRIMARY KEY (votacion_id, promesa_id)
);
CREATE TABLE IF NOT EXISTS gasto (id INTEGER PRIMARY KEY, fecha TEXT, paso TEXT, usd REAL);
"""


def conectar(ruta: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(ruta, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(ESQUEMA)
    return conn
```

- [ ] **Step 7: Implementar `src/electoral/votaciones.py`**

```python
# src/electoral/votaciones.py
"""Votaciones del Pleno del Congreso (XV legislatura), voto a voto."""
import io
import json
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

import requests

from src.congreso import decode_vote_xml, compute_resultado

BASE = "https://www.congreso.es"
OPENDATA = BASE + "/es/opendata/votaciones"
PAGINA_DIA = (OPENDATA + "?p_p_id=votaciones&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
              "&targetLegislatura=XV&targetDate=")
CABECERAS = {"User-Agent": "PoligrafoES/1.0 (herramienta personal)"}
PAUSA = 1.5   # segundos entre peticiones: el Congreso es un servicio público, no un CDN

# Votaciones que no deciden el fondo de nada: solo cambian el procedimiento.
TRAMITE = re.compile(r"avocaci[oó]n|pr[oó]rroga|lectura [uú]nica|tramitaci[oó]n como proyecto de ley", re.I)

PREFIJOS = (
    "votación de la solicitud de avocación por el pleno de la cámara de la deliberación y votación final del ",
    "votación de la enmienda a la totalidad de devolución al ",
    "votación conjunta de las enmiendas a la totalidad de devolución al ",
    "votación de la enmienda a la totalidad de texto alternativo a la ",
    "votación de la enmienda a la totalidad de texto alternativo al ",
    "tramitación como proyecto de ley por el procedimiento de urgencia del ",
    "acuerdo de tramitación directa y en lectura única del ",
    "acuerdo de tramitación directa y en lectura única de la ",
    "votación del dictamen del ", "votación del dictamen de la ",
    "votación de conjunto del ", "votación de conjunto de la ",
)


def dias_con_votaciones(html: str) -> list[str]:
    """Fechas AAAAMMDD con votaciones según el calendario de la página de open data."""
    m = re.search(r"var diasVotaciones = \[([^\]]*)\]", html)
    return sorted(d.strip() for d in m.group(1).split(",")) if m else []


def urls_zip_del_dia(dia: str) -> list[str]:
    fecha = f"{dia[6:8]}/{dia[4:6]}/{dia[0:4]}"
    html = requests.get(PAGINA_DIA + fecha, headers=CABECERAS, timeout=30).text
    rutas = re.findall(r"/webpublica/opendata/votaciones/Leg15/Sesion\d+/" + dia + r"/VOT_[^\"']+\.zip", html)
    return [BASE + r for r in sorted(set(rutas))]


def descargar_legislatura(destino: Path, ya_bajados: set[str]) -> list[Path]:
    """Baja los ZIP que falten. Reanudable: no repite los de `ya_bajados` (nombres de archivo)."""
    destino.mkdir(parents=True, exist_ok=True)
    html = requests.get(OPENDATA, headers=CABECERAS, timeout=30).text
    nuevos = []
    for dia in dias_con_votaciones(html):
        for url in urls_zip_del_dia(dia):
            nombre = url.rsplit("/", 1)[1]
            if nombre in ya_bajados:
                continue
            r = requests.get(url, headers=CABECERAS, timeout=60)
            r.raise_for_status()
            (destino / nombre).write_bytes(r.content)
            nuevos.append(destino / nombre)
            time.sleep(PAUSA)
        time.sleep(PAUSA)
    return nuevos


def _fecha_iso(fecha_congreso: str) -> str:
    d, m, a = (int(x) for x in fecha_congreso.split("/"))
    return date(a, m, d).isoformat()


def leer_zip(ruta: Path) -> list[dict]:
    """Todas las votaciones de un ZIP de sesión, con el voto de cada diputado."""
    salida = []
    with zipfile.ZipFile(ruta) as zf:
        for nombre in zf.namelist():
            if not nombre.lower().endswith(".xml"):
                continue
            raiz = ET.fromstring(decode_vote_xml(zf.read(nombre)))
            info, tot = raiz.find("Informacion"), raiz.find("Totales")
            fecha = _fecha_iso(info.findtext("Fecha", "").strip())
            sesion = int(info.findtext("Sesion", 0))
            salida.append({
                "id": f"{sesion}-{int(info.findtext('NumeroVotacion', 0))}",
                "sesion": sesion,
                "numero": int(info.findtext("NumeroVotacion", 0)),
                "fecha": fecha,
                "tipo": info.findtext("Titulo", "").strip(),
                "expediente": info.findtext("TextoExpediente", "").strip(),
                "titulo_subgrupo": info.findtext("TituloSubGrupo", "").strip(),
                "texto_subgrupo": info.findtext("TextoSubGrupo", "").strip(),
                "a_favor": int(tot.findtext("AFavor", 0)),
                "en_contra": int(tot.findtext("EnContra", 0)),
                "abstenciones": int(tot.findtext("Abstenciones", 0)),
                "diputados": [
                    {"diputado": v.findtext("Diputado", "").strip(),
                     "grupo": v.findtext("Grupo", "").strip(),
                     "voto": v.findtext("Voto", "").strip()}
                    for v in raiz.findall(".//Votacion")
                ],
                "url_zip_nombre": ruta.name,
            })
    return salida


def clasificar(v: dict) -> tuple[str, bool]:
    """Subtipo de la votación y si es la convalidación de un decreto-ley."""
    texto = " ".join([v["tipo"], v["titulo_subgrupo"], v["texto_subgrupo"], v["expediente"]])
    if TRAMITE.search(texto):
        return "tramite", False
    bajo = texto.lower()
    if "texto alternativo" in bajo:
        return "texto_alternativo", False
    if "devoluci" in bajo:
        return "devolucion", False
    es_conv = v["tipo"].lower().startswith("convalidación") and "real decreto-ley" in v["expediente"].lower()
    return "normal", es_conv


def clave_iniciativa(texto: str) -> str:
    """Identidad de la iniciativa, igual en todas sus votaciones (toma, totalidad, dictamen, conjunto)."""
    t = " ".join(texto.split()).lower()
    m = re.search(r"real decreto-ley \d+/\d{4}", t)
    if m:
        return m.group(0)
    for p in PREFIJOS:
        if t.startswith(p):
            t = t[len(p):]
            break
    return t.split(", presentada por")[0].split(". se vota")[0].strip(" .")


def votos_por_partido(v: dict, mapa: dict) -> dict:
    """{partido: {voto, dividido}}. El Mixto se reparte por diputado; los independientes no cuentan."""
    mixto = {}
    for p in mapa["mixto"]:
        mixto.setdefault(p["diputado"], []).append(p)
    por_partido: dict[str, Counter] = {}
    for d in v["diputados"]:
        if d["grupo"] == "GMx":
            tramos = [p for p in mixto.get(d["diputado"], []) if p["desde"] <= v["fecha"]]
            partido = tramos[-1]["partido"] if tramos else None
        else:
            partido = mapa["grupos"].get(d["grupo"])
        if partido is None:
            continue
        por_partido.setdefault(partido, Counter())[d["voto"]] += 1
    salida = {}
    for partido, c in por_partido.items():
        voto, n = c.most_common(1)[0]
        total = sum(c.values())
        salida[partido] = {"voto": voto, "dividido": (total - n) / total > 0.10}
    return salida


def url_sesion(fecha_iso: str) -> str:
    a, m, d = fecha_iso.split("-")
    return PAGINA_DIA + f"{d}/{m}/{a}"


def url_xml(nombre_zip: str, sesion: int, fecha_iso: str) -> str:
    return f"{BASE}/webpublica/opendata/votaciones/Leg15/Sesion{sesion:03d}/{fecha_iso.replace('-', '')}/{nombre_zip}"


def guardar(conn, v: dict, mapa: dict) -> None:
    subtipo, es_conv = clasificar(v)
    conn.execute(
        "INSERT OR REPLACE INTO votaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (v["id"], v["fecha"], v["sesion"], v["numero"], v["tipo"], subtipo, int(es_conv),
         v["expediente"], v["texto_subgrupo"], clave_iniciativa(v["expediente"]),
         compute_resultado(v["a_favor"], v["en_contra"]), v["a_favor"], v["en_contra"], v["abstenciones"],
         int(subtipo == "tramite"), url_xml(v["url_zip_nombre"], v["sesion"], v["fecha"]), url_sesion(v["fecha"])),
    )
    conn.execute("DELETE FROM votos_partido WHERE votacion_id = ?", (v["id"],))
    for partido, x in votos_por_partido(v, mapa).items():
        conn.execute("INSERT INTO votos_partido VALUES (?,?,?,?)", (v["id"], partido, x["voto"], int(x["dividido"])))


def cargar_mapa(raiz: Path) -> dict:
    return json.loads((raiz / "config" / "diputados.json").read_text(encoding="utf-8"))
```

Nota para el implementador: comprueba en un ZIP real que la carpeta `Sesion` de la URL lleva ceros a la izquierda (`Sesion048`). Si no los lleva, cambia `{sesion:03d}` por `{sesion}`. El paso 4 lo verifica con `startswith`; añade a mano una comprobación con `requests.head(url).status_code == 200` sobre una votación antes de dar la tarea por cerrada.

- [ ] **Step 8: Implementar `src/electoral/exportar.py` (primera versión) y `electoral.py`**

```python
# src/electoral/exportar.py
import json
from datetime import datetime, timezone
from pathlib import Path

VERSION_CONTRATO = "1.0.0"


def _votaciones(conn) -> list[dict]:
    salida = []
    for v in conn.execute("SELECT * FROM votaciones ORDER BY fecha, sesion, numero"):
        votos = {r["partido"]: {"voto": r["voto"], "dividido": bool(r["dividido"])}
                 for r in conn.execute("SELECT * FROM votos_partido WHERE votacion_id = ?", (v["id"],))}
        salida.append({
            "id": v["id"], "fecha": v["fecha"], "sesion": v["sesion"], "numero": v["numero"],
            "tipo": v["tipo"], "subtipo": v["subtipo"], "expediente": v["expediente"],
            "que_se_vota": v["texto_subgrupo"], "clave_iniciativa": v["clave_iniciativa"],
            "resultado": v["resultado"], "a_favor": v["a_favor"], "en_contra": v["en_contra"],
            "abstenciones": v["abstenciones"], "excluida_tramite": bool(v["excluida_tramite"]),
            "votos": votos, "url_xml": v["url_xml"], "url_sesion": v["url_sesion"],
        })
    return salida


def construir(conn, raiz: Path) -> dict:
    partidos = json.loads((raiz / "config" / "partidos_electoral.json").read_text(encoding="utf-8"))
    votaciones = _votaciones(conn)
    return {
        "meta": {
            "version_contrato": VERSION_CONTRATO,
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "periodo": {"desde": "2023-08-17", "hasta": max((v["fecha"] for v in votaciones), default=None)},
            "recuentos": {"votaciones": len(votaciones)},
        },
        "partidos": partidos,
        "votaciones": votaciones,
    }


def escribir(datos: dict, salida: Path) -> None:
    salida.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
```

```python
# electoral.py
"""Motor de datos de la web electoral del 29N. Ver docs/superpowers/specs/2026-10-07-web-electoral-29n-design.md."""
import argparse
from pathlib import Path

from src.electoral import db as edb
from src.electoral import exportar, votaciones

RAIZ = Path(__file__).resolve().parent


def cmd_descargar(a, conn):
    destino = Path(a.zips) if a.zips else RAIZ / "electoral_data" / "zips"
    if not a.zips:
        hechos = {r["nombre"] for r in conn.execute("SELECT nombre FROM zips")}
        votaciones.descargar_legislatura(destino, hechos)
    mapa = votaciones.cargar_mapa(RAIZ)
    for ruta in sorted(destino.glob("*.zip")):
        for v in votaciones.leer_zip(ruta):
            votaciones.guardar(conn, v, mapa)
        conn.execute("INSERT OR IGNORE INTO zips VALUES (?,?,?)", (ruta.name, "", ""))
    conn.commit()


def cmd_exportar(a, conn):
    exportar.escribir(exportar.construir(conn, RAIZ), Path(a.salida))


def main():
    p = argparse.ArgumentParser(prog="electoral")
    sub = p.add_subparsers(dest="cmd", required=True)
    for nombre in ("descargar", "exportar"):
        s = sub.add_parser(nombre)
        s.add_argument("--db", default=str(RAIZ / "electoral.db"))
    sub.choices["descargar"].add_argument("--zips", help="carpeta con ZIPs ya bajados (no descarga nada)")
    sub.choices["exportar"].add_argument("--salida", default=str(RAIZ / "datos.json"))
    a = p.parse_args()
    conn = edb.conectar(Path(a.db))
    {"descargar": cmd_descargar, "exportar": cmd_exportar}[a.cmd](a, conn)


if __name__ == "__main__":
    main()
```

- [ ] **Step 9: Ejecutar las pruebas**

Run: `pytest tests/electoral/test_votaciones.py -v`
Expected: PASS las 8.

- [ ] **Step 10: Verificar contra el Congreso real** (una sola vez, no es una prueba)

```bash
python electoral.py descargar --zips tests/fixtures/electoral/zips --db /tmp/e.db && python electoral.py exportar --db /tmp/e.db --salida /tmp/d.json
python -c "import json,requests;v=json.load(open('/tmp/d.json',encoding='utf-8'))['votaciones'][0];print(v['url_xml'], requests.head(v['url_xml'],timeout=20).status_code)"
```

Expected: `200`. Si da 404, corrige el formato de `Sesion` (ver nota del paso 7) y repite.

- [ ] **Step 11: Commit**

```bash
git add electoral.py src/electoral config/diputados.json config/partidos_electoral.json tests/electoral tests/fixtures/electoral/zips .gitignore requirements.txt
git commit -m "feat(electoral): load xv votes per deputy, classify them and export votaciones"
```

---

### Task 2: Cliente LLM con tope de gasto y transporte inyectable

Sin prueba propia: el cliente se ejercita a través del CLI en las tareas 3 y 4 (pruebas de comportamiento, nunca unitarias). Esta tarea solo crea el módulo y el LLM falso de las pruebas.

**Files:**
- Create: `src/electoral/llm.py`
- Modify: `tests/electoral/conftest.py` (añadir el LLM falso)

**Interfaces:**
- Produces: `class LLM(tope_usd: float, transporte=None)`, con `.json(modelo, sistema, usuario, max_tokens=1500) -> dict | None`, `.gastado: float` y la excepción `PresupuestoAgotado`. `transporte(body: dict) -> dict` imita la respuesta de OpenRouter (`{"choices": [{"message": {"content": str}}], "usage": {"cost": float}}`). Variable de entorno `ELECTORAL_LLM_FALSO=<ruta a un .py>`: si existe, el CLI carga de ese archivo una función `transporte(body)` en lugar de llamar a OpenRouter.

- [ ] **Step 1: Implementar `src/electoral/llm.py`**

```python
# src/electoral/llm.py
"""Cliente de OpenRouter con tope de gasto. Ningún modelo de Anthropic (decisión de Fran)."""
import importlib.util
import json
import os
import threading
import time

import requests
from dotenv import load_dotenv

URL = "https://openrouter.ai/api/v1/chat/completions"
RAZONAMIENTO = {   # el razonamiento oculto se cobra como salida: apagado o al mínimo
    "deepseek/deepseek-v4-flash": {"enabled": False},
    "deepseek/deepseek-v4-pro": {"enabled": False},
    "openai/gpt-5-mini": {"effort": "minimal"},
    "openai/gpt-5-nano": {"effort": "minimal"},
}


class PresupuestoAgotado(Exception):
    pass


def _transporte_openrouter(clave):
    sesion = requests.Session()

    def enviar(body):
        for intento in range(3):
            r = sesion.post(URL, json=body, headers={"Authorization": f"Bearer {clave}"}, timeout=120)
            if r.status_code == 200:
                return r.json()
            time.sleep(3 * (intento + 1))
        return {"error": r.status_code}
    return enviar


def _transporte_falso(ruta):
    spec = importlib.util.spec_from_file_location("llm_falso", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.transporte


class LLM:
    def __init__(self, tope_usd: float, transporte=None):
        self.tope = tope_usd
        self.gastado = 0.0
        self._lock = threading.Lock()
        if transporte is None:
            falso = os.environ.get("ELECTORAL_LLM_FALSO")
            if falso:
                transporte = _transporte_falso(falso)
            else:
                load_dotenv()
                transporte = _transporte_openrouter(os.environ["OPENROUTER_API_KEY"])
        self._enviar = transporte

    def json(self, modelo: str, sistema: str, usuario: str, max_tokens: int = 1500):
        with self._lock:
            if self.gastado >= self.tope:
                raise PresupuestoAgotado(f"gastados {self.gastado:.4f} $ de {self.tope} $")
        body = {"model": modelo, "max_tokens": max_tokens, "temperature": 0,
                "response_format": {"type": "json_object"}, "usage": {"include": True},
                "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}
        if modelo in RAZONAMIENTO:
            body["reasoning"] = RAZONAMIENTO[modelo]
        d = self._enviar(body)
        with self._lock:
            self.gastado += float((d.get("usage") or {}).get("cost") or 0)
        try:
            texto = d["choices"][0]["message"]["content"] or ""
            return json.loads(texto[texto.find("{"): texto.rfind("}") + 1])
        except (KeyError, IndexError, ValueError):
            return None
```

- [ ] **Step 2: Añadir el LLM falso a las pruebas** (`tests/fixtures/electoral/llm_falso.py`)

Responde de forma determinista según el modelo y el contenido. Con eso las pruebas fijan qué hace el motor con cada combinación de jueces sin gastar dinero.

```python
# tests/fixtures/electoral/llm_falso.py
"""LLM falso para las pruebas. Reglas por contenido del mensaje del usuario."""
import json
import os
import re

COSTE = float(os.environ.get("LLM_FALSO_COSTE", "0.001"))
# Comportamiento de cada juez, configurable por entorno: "acuerdo" (3/3 directa), "dos" (2 de 3), "indirecta".
MODO = os.environ.get("LLM_FALSO_MODO", "acuerdo")
FALLA_JUEZ = os.environ.get("LLM_FALSO_FALLA", "")   # modelo que devuelve basura


def _resp(obj):
    return {"choices": [{"message": {"content": json.dumps(obj, ensure_ascii=False)}}], "usage": {"cost": COSTE}}


def transporte(body):
    modelo = body["model"]
    usuario = body["messages"][1]["content"]
    if "FRAGMENTO:" in usuario:                       # extracción de promesas
        promesas = []
        for trozo in usuario.split("PROMESA:")[1:]:      # el bloque llega en una sola línea
            texto = trozo.split(" Hemos")[0].strip()
            if texto:
                promesas.append({"promesa": texto, "cita": texto, "tema": "Vivienda" if "alquiler" in texto else "Instituciones y calidad democrática",
                                 "procedimental": "real decreto" in texto.lower()})
        return _resp({"promesas": promesas})
    if FALLA_JUEZ and modelo == FALLA_JUEZ:
        return {"choices": [{"message": {"content": "no es json"}}], "usage": {"cost": COSTE}}
    ids = re.findall(r"\[chunk_id=(\d+)\]", usuario)
    partidos = re.findall(r"Promesas del programa electoral de ([^:]+):", usuario)
    if not ids:
        return _resp({"resumen": "", "que_cambia": "", "matches": []})
    fuerza = "directa"
    if MODO == "indirecta" or (MODO == "dos" and modelo == "google/gemini-2.5-flash-lite"):
        fuerza = "indirecta" if MODO == "indirecta" else None
    veredicto = None if fuerza is None else "cumple"
    return _resp({"resumen": "r", "que_cambia": "q", "matches": [
        {"party": partidos[0], "chunk_id": int(ids[0]), "promesa": "p", "veredicto": veredicto, "fuerza": fuerza}]})
```

- [ ] **Step 3: Commit**

```bash
git add src/electoral/llm.py tests/fixtures/electoral/llm_falso.py
git commit -m "feat(electoral): add openrouter client with spending cap and fake transport"
```

---

### Task 3: Programas → promesas sueltas con tema

**Files:**
- Create: `src/electoral/programas.py`, `tests/electoral/test_programas.py`, `tests/fixtures/electoral/programa_prueba.pdf` (generado en el paso 1)
- Modify: `electoral.py` (subcomandos `ingest-programa` y `extraer`), `src/electoral/exportar.py` (bloques `promesas` y `temas`), `config/partidos_electoral.json` (URL de BNG, CC y UPN)

**Interfaces:**
- Consumes: `LLM` (tarea 2), `conectar` (tarea 1).
- Produces: `python electoral.py ingest-programa <anio> <partido> <url_o_ruta>`, `python electoral.py extraer [--tope USD]`. En `datos.json`: `promesas[]` con `{id, partido, anio, texto, cita, pagina, tema, url_programa_pagina}` (las procedimentales no se exportan) y `temas: {partido: {anio: {tema: porcentaje}}}`. `TEMAS` (lista fija de 17) en `src/electoral/programas.py`.

- [ ] **Step 1: Generar un PDF de prueba de dos páginas**

```bash
python - <<'E'
import fitz
doc = fitz.open()
for texto in ["PROMESA: Limitaremos el precio del alquiler en zonas tensionadas.\nPROMESA: Crearemos una oficina de transparencia legislativa.",
              "PROMESA: Limitaremos el uso del real decreto-ley.\nHemos aprobado la ley de vivienda."]:
    doc.new_page().insert_text((72, 72), texto)
doc.save("tests/fixtures/electoral/programa_prueba.pdf")
E
```

- [ ] **Step 2: Escribir las pruebas que fallan**

```python
# tests/electoral/test_programas.py
import os
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def _env(**extra):
    return {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), **extra}


def test_cada_promesa_lleva_cita_pagina_y_enlace_a_esa_pagina(cli):
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    datos = cli("exportar")
    psoe = [p for p in datos["promesas"] if p["partido"] == "PSOE"]
    assert len(psoe) == 2
    alquiler = next(p for p in psoe if "alquiler" in p["texto"])
    assert alquiler["pagina"] == 1 and alquiler["cita"]
    assert alquiler["url_programa_pagina"].endswith("#page=1")


def test_las_promesas_de_procedimiento_no_se_exportan(cli):
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    assert not any("real decreto" in p["texto"].lower() for p in cli("exportar")["promesas"])


def test_el_reparto_por_temas_suma_cien(cli):
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    temas = cli("exportar")["temas"]["PSOE"]["2023"]
    assert abs(sum(temas.values()) - 100) < 0.5


def test_un_partido_sin_programa_aparece_con_su_motivo_y_sin_promesas(cli):
    datos = cli("exportar")
    podemos = next(p for p in datos["partidos"] if p["id"] == "Podemos")
    assert "Sumar" in podemos["sin_programa"]
    assert not [p for p in datos["promesas"] if p["partido"] == "Podemos"]


def test_si_se_agota_el_presupuesto_la_extraccion_se_reanuda_sin_duplicar(cli):
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", "--tope", "0", env=_env())          # tope 0: se para antes de la primera llamada
    assert cli("exportar")["promesas"] == []
    cli("extraer", env=_env())
    textos = [p["texto"] for p in cli("exportar")["promesas"]]
    assert len(textos) == len(set(textos)) == 2
```

- [ ] **Step 3: Comprobar que fallan**

Run: `pytest tests/electoral/test_programas.py -v`
Expected: FAIL (subcomandos inexistentes).

- [ ] **Step 4: Implementar `src/electoral/programas.py`**

```python
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
```

Nota: el `pdfplumber` del PDF de prueba deja cada línea `PROMESA: …` en el texto del bloque, que es lo que lee el LLM falso.

- [ ] **Step 5: Ampliar `exportar.py` con `promesas` y `temas`**

Añadir a `src/electoral/exportar.py`:

```python
from collections import Counter, defaultdict


def _promesas(conn) -> list[dict]:
    salida = []
    for p in conn.execute("""SELECT p.*, b.url_programa FROM promesas p JOIN bloques b ON b.id = p.bloque_id
                             WHERE p.procedimental = 0 ORDER BY p.partido, p.anio, p.pagina, p.id"""):
        salida.append({"id": p["id"], "partido": p["partido"], "anio": p["anio"], "texto": p["texto"],
                       "cita": p["cita"], "pagina": p["pagina"], "tema": p["tema"],
                       "url_programa_pagina": f"{p['url_programa']}#page={p['pagina']}"})
    return salida


def _temas(promesas: list[dict]) -> dict:
    cuenta = defaultdict(Counter)
    for p in promesas:
        cuenta[(p["partido"], str(p["anio"]))][p["tema"]] += 1
    salida = defaultdict(dict)
    for (partido, anio), c in cuenta.items():
        total = sum(c.values())
        salida[partido][anio] = {t: round(100 * n / total, 1) for t, n in c.most_common()}
    return dict(salida)
```

Y en `construir`:

```python
    promesas = _promesas(conn)
    ...
        "promesas": promesas,
        "temas": _temas(promesas),
```

Añade también `"promesas": len(promesas)` a `meta.recuentos`.

- [ ] **Step 6: Añadir los subcomandos a `electoral.py`**

```python
from src.electoral import programas
from src.electoral.llm import LLM


def cmd_ingest(a, conn):
    print(programas.ingerir(conn, int(a.anio), a.partido, a.origen), "bloques nuevos")


def cmd_extraer(a, conn):
    llm = LLM(a.tope)
    programas.extraer(conn, llm)
    conn.execute("INSERT INTO gasto (fecha, paso, usd) VALUES (datetime('now'), 'extraer', ?)", (llm.gastado,))
    conn.commit()
    print(f"gastado {llm.gastado:.4f} $")
```

En `main()`, registrar `ingest-programa` (argumentos posicionales `anio partido origen`) y `extraer` (`--tope`, por defecto `1.0`), ambos con `--db`, y añadirlos al diccionario de comandos.

- [ ] **Step 7: Ejecutar las pruebas**

Run: `pytest tests/electoral/test_programas.py -v`
Expected: PASS las 5.

- [ ] **Step 8: Localizar los programas de BNG, CC y UPN de 2023**

Para cada uno, busca el PDF oficial de las generales del 23J de 2023 (web del partido; si no está, un medio que lo enlace) y comprueba que es un PDF:

```bash
python -c "import requests,sys;r=requests.get(sys.argv[1],timeout=60,headers={'User-Agent':'PoligrafoES/1.0'});print(r.status_code, r.content[:4])" "<URL>"
```

Expected: `200 b'%PDF'`. Anota cada URL en `config/partidos_electoral.json` (campo `programa_2023`) y borra la clave `pendiente`. Si un partido no tiene programa de generales localizable, sustituye `pendiente` por `"sin_programa": "<motivo verificable>"`; no se inventa nada.

- [ ] **Step 9: Commit**

```bash
git add src/electoral/programas.py src/electoral/exportar.py electoral.py tests/electoral/test_programas.py tests/fixtures/electoral/programa_prueba.pdf config/partidos_electoral.json
git commit -m "feat(electoral): extract atomic promises with theme from program pdfs"
```

---

### Task 4: Juez de tres modelos y nivel de cada cruce

**Files:**
- Create: `src/electoral/juez.py`, `tests/electoral/test_juez.py`
- Modify: `electoral.py` (subcomando `juzgar`), `src/electoral/exportar.py` (bloque `cruces`)

**Interfaces:**
- Consumes: `votaciones`, `promesas` en `electoral.db`; `LLM`.
- Produces: `python electoral.py juzgar [--tope USD] [--k 20]`. En `datos.json`: `cruces[]` con `{votacion_id, promesa_id, partido, voto, nivel: "veredicto"|"juzga_tu", veredicto: "cumple"|"incumple", jueces: {modelo: {veredicto, fuerza}}}`. `JUECES` (3 modelos) en `src/electoral/juez.py`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/electoral/test_juez.py
import os
import sqlite3
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def _env(**extra):
    return {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), **extra}


def _preparar(cli, zips, **env):
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env(**env))
    cli("extraer", env=_env(**env))


def test_tres_jueces_de_acuerdo_con_relacion_directa_dan_veredicto(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", env=_env())
    cruces = cli("exportar")["cruces"]
    assert cruces and all(c["nivel"] == "veredicto" for c in cruces if c["partido"] == "PSOE" and not c["dividido"])
    assert all(len(c["jueces"]) == 3 for c in cruces)


def test_dos_de_tres_se_quedan_en_juzga_tu(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", env=_env(LLM_FALSO_MODO="dos"))
    cruces = cli("exportar")["cruces"]
    assert cruces and {c["nivel"] for c in cruces} == {"juzga_tu"}


def test_relacion_indirecta_nunca_es_veredicto(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", env=_env(LLM_FALSO_MODO="indirecta"))
    assert all(c["nivel"] == "juzga_tu" for c in cli("exportar")["cruces"])


def test_las_votaciones_de_tramite_no_se_juzgan(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", env=_env())
    datos = cli("exportar")
    tramite = {v["id"] for v in datos["votaciones"] if v["excluida_tramite"]}
    assert not [c for c in datos["cruces"] if c["votacion_id"] in tramite]


def test_un_partido_que_vota_dividido_nunca_recibe_veredicto(cli, zips):
    _preparar(cli, zips)
    conn = sqlite3.connect(cli.db)
    conn.execute("UPDATE votos_partido SET dividido = 1 WHERE partido = 'PSOE'")
    conn.commit(); conn.close()
    cli("juzgar", "--k", "3", env=_env())
    assert all(c["nivel"] == "juzga_tu" for c in cli("exportar")["cruces"] if c["partido"] == "PSOE")


def test_un_juez_que_falla_deja_el_expediente_pendiente_y_se_reanuda(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", env=_env(LLM_FALSO_FALLA="openai/gpt-5-mini"))
    assert cli("exportar")["cruces"] == []                     # nada a medio juzgar
    cli("juzgar", "--k", "3", env=_env())
    cruces = cli("exportar")["cruces"]
    claves = [(c["votacion_id"], c["promesa_id"]) for c in cruces]
    assert cruces and len(claves) == len(set(claves))


def test_si_se_agota_el_presupuesto_no_se_publica_nada_a_medias(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", "--tope", "0.002", env=_env(LLM_FALSO_COSTE="0.001"))
    parcial = cli("exportar")["cruces"]
    cli("juzgar", "--k", "3", env=_env())
    completo = cli("exportar")["cruces"]
    assert len(completo) >= len(parcial)
    assert all(len(c["jueces"]) == 3 for c in parcial + completo)
```

- [ ] **Step 2: Comprobar que fallan**

Run: `pytest tests/electoral/test_juez.py -v`
Expected: FAIL (`juzgar` no existe).

- [ ] **Step 3: Implementar `src/electoral/juez.py`**

Las instrucciones del juez se copian aquí, en un solo sitio, porque el código será público y tienen que poder auditarse.

```python
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
    partes += [f"  {r['partido']}: {r['voto']}" for r in votos]
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

    def uno(v):
        votos = conn.execute("SELECT * FROM votos_partido WHERE votacion_id = ? ORDER BY partido", (v["id"],)).fetchall()
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
```

Nota: `prompt()` necesita `v["texto_subgrupo"]`, que la tabla `votaciones` ya guarda desde la tarea 1.

- [ ] **Step 4: Añadir `cruces` a la exportación y el subcomando `juzgar`**

En `src/electoral/exportar.py`:

```python
def _cruces(conn) -> list[dict]:
    salida = []
    for c in conn.execute("""SELECT c.*, vp.voto, vp.dividido FROM cruces c
                             JOIN votos_partido vp ON vp.votacion_id = c.votacion_id AND vp.partido = c.partido
                             ORDER BY c.votacion_id, c.partido"""):
        salida.append({"votacion_id": c["votacion_id"], "promesa_id": c["promesa_id"], "partido": c["partido"],
                       "voto": c["voto"], "dividido": bool(c["dividido"]), "nivel": c["nivel"],
                       "veredicto": c["veredicto"], "jueces": json.loads(c["jueces"])})
    return salida
```

Y en `construir`: `"cruces": _cruces(conn)` y el recuento `"veredictos": sum(c["nivel"] == "veredicto" for c in cruces)`.

En `electoral.py`:

```python
from src.electoral import juez


def cmd_juzgar(a, conn):
    llm = LLM(a.tope)
    juez.juzgar(conn, llm, k=a.k)
    conn.execute("INSERT INTO gasto (fecha, paso, usd) VALUES (datetime('now'), 'juzgar', ?)", (llm.gastado,))
    conn.commit()
    print(f"gastado {llm.gastado:.4f} $")
```

Registrar `juzgar` con `--tope` (por defecto `4.0`), `--k` (por defecto `20`) y `--db`.

- [ ] **Step 5: Ejecutar las pruebas**

Run: `pytest tests/electoral -v`
Expected: PASS todas (tareas 1, 3 y 4).

- [ ] **Step 6: Commit**

```bash
git add src/electoral/juez.py src/electoral/exportar.py electoral.py tests/electoral/test_juez.py
git commit -m "feat(electoral): judge promises against votes with three model families"
```

---

### Task 5: Fuentes oficiales de cada cruce (BOCG, BOE)

**Files:**
- Create: `src/electoral/fuentes.py`, `tests/electoral/test_fuentes.py`, `tests/fixtures/electoral/iniciativas_muestra.json`, `tests/fixtures/electoral/boe_muestra.json`
- Modify: `electoral.py` (`fuentes`), `src/electoral/exportar.py` (añadir `url_bocg` y `url_boe` a `votaciones`), `src/electoral/db.py` (columnas nuevas)

**Interfaces:**
- Produces: `python electoral.py fuentes [--iniciativas DIR] [--boe JSON]`. En `votaciones[]`: `url_bocg: str|null`, `url_boe: str|null`. `fuentes.url_bocg(expediente, iniciativas) -> str|None`, `fuentes.url_boe(votacion, resolver) -> str|None`.

- [ ] **Step 1: Verificar a mano cómo resolver el BOE**

El decreto-ley 3/2026 y la ley de atención a la clientela tienen que dar una URL de `boe.es` que funcione. Prueba primero la API de datos abiertos de legislación consolidada:

```bash
curl -s "https://www.boe.es/datosabiertos/api/legislacion-consolidada?query=%7B%22query%22%3A%7B%22query_string%22%3A%7B%22query%22%3A%22titulo%3A%5C%22Real%20Decreto-ley%203%2F2026%5C%22%22%7D%7D%7D" -H "Accept: application/json" | head -c 600
```

Si devuelve un identificador `BOE-A-…`, la URL es `https://www.boe.es/buscar/act.php?id=<identificador>`. Si no funciona, usa el sumario diario del BOE, que el bot ya consulta en `src/boe.py`: busca en el sumario del día de publicación del decreto el título que empiece por `Real Decreto-ley 3/2026` y toma su `identificador`. Anota en un comentario de `fuentes.py` el método que funcionó, y guarda la respuesta real en `tests/fixtures/electoral/boe_muestra.json` como `{"real decreto-ley 3/2026": "BOE-A-…"}`.

- [ ] **Step 2: Guardar una muestra real de iniciativas**

```bash
python - <<'E'
import json, re, requests
H = {"User-Agent": "PoligrafoES/1.0"}
html = requests.get("https://www.congreso.es/es/opendata/iniciativas", headers=H, timeout=30).text
muestra = []
for path in sorted(set(re.findall(r"/webpublica/opendata/iniciativas/(?:ProyectosDeLey|ProposicionesDeLey)__\d+\.json", html))):
    for x in requests.get("https://www.congreso.es" + path, headers=H, timeout=60).json():
        if any(s in x["OBJETO"] for s in ("grupos de interés", "amnistía", "atención a la clientela")):
            muestra.append(x)
json.dump(muestra, open("tests/fixtures/electoral/iniciativas_muestra.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(muestra))
E
```

Expected: 3 o más iniciativas.

- [ ] **Step 3: Escribir las pruebas que fallan**

```python
# tests/electoral/test_fuentes.py
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def test_la_devolucion_de_la_ley_de_lobbies_enlaza_su_texto_en_el_bocg(cli, zips):
    cli("descargar", "--zips", zips)
    cli("fuentes", "--iniciativas", str(FIX / "iniciativas_muestra.json"), "--boe", str(FIX / "boe_muestra.json"))
    v = next(v for v in cli("exportar")["votaciones"] if "grupos de interés" in v["expediente"] and v["subtipo"] == "devolucion")
    assert v["url_bocg"].startswith("https://www.congreso.es/public_oficiales/L15/CONG/BOCG/")


def test_la_convalidacion_de_un_decreto_ley_enlaza_el_boe(cli, zips):
    cli("descargar", "--zips", zips)
    cli("fuentes", "--iniciativas", str(FIX / "iniciativas_muestra.json"), "--boe", str(FIX / "boe_muestra.json"))
    v = next(v for v in cli("exportar")["votaciones"] if v["clave_iniciativa"] == "real decreto-ley 3/2026" and not v["excluida_tramite"])
    assert v["url_boe"].startswith("https://www.boe.es/")


def test_una_mocion_no_inventa_enlaces(cli, zips):
    cli("descargar", "--zips", zips)
    cli("fuentes", "--iniciativas", str(FIX / "iniciativas_muestra.json"), "--boe", str(FIX / "boe_muestra.json"))
    for v in cli("exportar")["votaciones"]:
        if v["tipo"].startswith("Mociones"):
            assert v["url_boe"] is None
```

- [ ] **Step 4: Comprobar que fallan**

Run: `pytest tests/electoral/test_fuentes.py -v`
Expected: FAIL.

- [ ] **Step 5: Implementar `src/electoral/fuentes.py` y conectarlo**

```python
# src/electoral/fuentes.py
"""Enlaces a las fuentes oficiales de cada votación."""
import difflib
import json
import re
from pathlib import Path

import requests

from src.electoral.votaciones import clave_iniciativa

CABECERAS = {"User-Agent": "PoligrafoES/1.0"}


def cargar_iniciativas(origen: str | None) -> list[dict]:
    if origen:
        return json.loads(Path(origen).read_text(encoding="utf-8"))
    html = requests.get("https://www.congreso.es/es/opendata/iniciativas", headers=CABECERAS, timeout=30).text
    todas = []
    for path in sorted(set(re.findall(r"/webpublica/opendata/iniciativas/[A-Za-z]+__\d+\.json", html))):
        todas += requests.get("https://www.congreso.es" + path, headers=CABECERAS, timeout=60).json()
    return todas


def url_bocg(expediente: str, iniciativas: list[dict]) -> str | None:
    clave = clave_iniciativa(expediente)
    objetos = [clave_iniciativa(x.get("OBJETO", "")) for x in iniciativas]
    m = difflib.get_close_matches(clave[:250], [o[:250] for o in objetos], n=1, cutoff=0.75)
    if not m:
        return None
    x = iniciativas[[o[:250] for o in objetos].index(m[0])]
    enlaces = (x.get("ENLACESBOCG") or "").split()
    return enlaces[0].split("#")[0] if enlaces else None


def url_boe(v: dict, boe: dict) -> str | None:
    """Solo para lo que acaba en el BOE: convalidaciones de decretos-ley y leyes aprobadas en su votación final."""
    final = v["es_convalidacion"] or v["tipo"].startswith(("Dictámenes de Comisiones sobre iniciativas", "Enmiendas del Senado"))
    if not final or v["resultado"] != "aprobada":
        return None
    ident = boe.get(v["clave_iniciativa"])
    return f"https://www.boe.es/buscar/act.php?id={ident}" if ident else None
```

`boe` es un diccionario `clave_iniciativa → identificador BOE`. En las pruebas sale de `boe_muestra.json`. En producción (`fuentes` sin `--boe`), implementa en `fuentes.py` una función `resolver_boe(clave: str) -> str | None` con el método que funcionó en el paso 1. Llámala solo para las votaciones finales aprobadas (las que pasan el filtro de `url_boe`) y guarda el resultado en una tabla `boe (clave TEXT PRIMARY KEY, identificador TEXT)` para no repetir consultas. Si no encuentra el identificador, la URL queda `null`: no se inventa ningún enlace.

En `db.py`, añade tras el esquema (las bases existentes no tienen las columnas):

```python
    for col in ("url_bocg", "url_boe"):
        try:
            conn.execute(f"ALTER TABLE votaciones ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
```

En `electoral.py`, el subcomando `fuentes` carga iniciativas y el mapa del BOE y hace `UPDATE votaciones SET url_bocg = ?, url_boe = ? WHERE id = ?` para cada votación. En `exportar._votaciones`, añade `"url_bocg": v["url_bocg"], "url_boe": v["url_boe"]`.

- [ ] **Step 6: Ejecutar las pruebas y hacer commit**

Run: `pytest tests/electoral -v` → PASS todas.

```bash
git add src/electoral/fuentes.py src/electoral/db.py src/electoral/exportar.py electoral.py tests/electoral/test_fuentes.py tests/fixtures/electoral/iniciativas_muestra.json tests/fixtures/electoral/boe_muestra.json
git commit -m "feat(electoral): link each vote to its bocg text and boe entry"
```

---

### Task 6: Coherencia, gobierno y finanzas

**Files:**
- Create: `src/electoral/analisis.py`, `config/finanzas_2023.json`, `tests/electoral/test_analisis.py`
- Modify: `src/electoral/exportar.py` (bloques `coherencia`, `gobierno`, `finanzas`)

**Interfaces:**
- Consumes: `votaciones`, `votos_partido`, `cruces`.
- Produces: en `datos.json`: `coherencia: {partido: [{clave_iniciativa, a_favor: votacion_id, en_contra: votacion_id}]}`, `gobierno: {partido: [{votacion_id, promesa_id, url_boe}]}` (solo partidos con `gobierno` no vacío) y `finanzas: {partido: {gasto_electoral_eur, subvencion_eur, transparencia, url_informe, pagina}}`.

**Desviación de la spec que hay que consultar con Fran:** la spec pedía comparar el comportamiento de cada partido en el Gobierno y en la oposición. En la XV nadie cambia de lado (PSOE y Sumar gobiernan toda la legislatura; Podemos solo hasta diciembre de 2023), así que esa comparación no tiene datos. Esta tarea implementa solo los **cambios de postura sobre una misma iniciativa**. Avisa a Fran al cerrar la tarea.

- [ ] **Step 1: Transcribir `config/finanzas_2023.json`**

Del Informe 1.616 del Tribunal de Cuentas (generales del 23J; https://www.juntaelectoralcentral.es/cs/jec/documentos/GENERALES_2023_TCuentas_Resoluci%C3%B3n.pdf), anota para cada partido con escaño el gasto electoral declarado y la subvención propuesta, con la página exacta del informe. Del informe de transparencia (2023-2024), si cumple o no y su página. Formato:

```json
{
  "url_informe_campana": "https://www.juntaelectoralcentral.es/cs/jec/documentos/GENERALES_2023_TCuentas_Resoluci%C3%B3n.pdf",
  "partidos": {
    "PP": {"gasto_electoral_eur": 0, "subvencion_eur": 0, "pagina": 0, "transparencia": "cumple|no_cumple|sin_dato", "pagina_transparencia": 0}
  }
}
```

Los `0` del ejemplo son el formato, no valores: cada cifra se copia del PDF. Las que no aparezcan van como `null` con `"motivo"`. Revisa dos cifras al azar contra el PDF antes de hacer commit.

- [ ] **Step 2: Escribir las pruebas que fallan**

```python
# tests/electoral/test_analisis.py
import json
import os
import sqlite3
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def _env(**extra):
    return {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), **extra}


def test_un_partido_que_cambia_de_postura_en_la_misma_ley_aparece_en_coherencia(cli, zips):
    cli("descargar", "--zips", zips)
    conn = sqlite3.connect(cli.db)
    clave = conn.execute("SELECT clave_iniciativa FROM votaciones WHERE subtipo = 'devolucion' LIMIT 1").fetchone()[0]
    vid = conn.execute("SELECT id FROM votaciones WHERE subtipo = 'devolucion' LIMIT 1").fetchone()[0]
    # Una votación final inventada de la misma ley en la que Vox vota Sí tras haber pedido devolverla
    conn.execute("INSERT INTO votaciones (id, fecha, sesion, numero, tipo, subtipo, es_convalidacion, expediente, texto_subgrupo, clave_iniciativa, resultado, a_favor, en_contra, abstenciones, excluida_tramite, url_xml, url_sesion) "
                 "VALUES ('999-1', '2025-12-01', 999, 1, 'Dictámenes de Comisiones sobre iniciativas legislativas.', 'normal', 0, 'x', '', ?, 'aprobada', 200, 100, 0, 0, 'u', 'u')", (clave,))
    conn.execute("INSERT INTO votos_partido VALUES ('999-1', 'Vox', 'Sí', 0)")
    conn.commit(); conn.close()
    pares = cli("exportar")["coherencia"].get("Vox", [])
    assert any(p["clave_iniciativa"] == clave and vid in (p["a_favor"], p["en_contra"]) for p in pares)


def test_un_decreto_ley_derogado_no_sale_en_lo_que_hizo_gobernando(cli, zips):
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    cli("juzgar", "--k", "3", env=_env())
    conn = sqlite3.connect(cli.db)
    conn.execute("UPDATE votaciones SET resultado = 'rechazada' WHERE es_convalidacion = 1")
    conn.commit(); conn.close()
    gob = cli("exportar")["gobierno"].get("PSOE", [])
    rechazadas = {v["id"] for v in cli("exportar")["votaciones"] if v["resultado"] == "rechazada"}
    assert not [g for g in gob if g["votacion_id"] in rechazadas]


def test_solo_los_partidos_de_gobierno_tienen_bloque_de_gobierno(cli, zips):
    cli("descargar", "--zips", zips)
    gob = cli("exportar")["gobierno"]
    assert set(gob) <= {"PSOE", "Sumar", "Podemos"}


def test_cada_cifra_de_finanzas_lleva_su_pagina_y_su_informe(cli):
    fin = cli("exportar")["finanzas"]
    assert fin
    for partido, f in fin.items():
        assert f["url_informe"].startswith("https://")
        assert f["gasto_electoral_eur"] is None or f["pagina"] > 0
```

- [ ] **Step 3: Comprobar que fallan**

Run: `pytest tests/electoral/test_analisis.py -v`
Expected: FAIL.

- [ ] **Step 4: Implementar `src/electoral/analisis.py` y ampliar la exportación**

```python
# src/electoral/analisis.py
"""Cálculos sin LLM: cambios de postura, lo hecho desde el Gobierno, finanzas."""
import json
from collections import defaultdict
from pathlib import Path


def postura(subtipo: str, voto: str) -> str | None:
    """'a_favor' o 'en_contra' de la iniciativa. La devolución invierte el voto; el texto alternativo no cuenta."""
    if subtipo == "texto_alternativo" or voto not in ("Sí", "No"):
        return None
    favorable = voto == "Sí"
    if subtipo == "devolucion":
        favorable = not favorable
    return "a_favor" if favorable else "en_contra"


def coherencia(conn) -> dict:
    filas = conn.execute("""SELECT v.id, v.clave_iniciativa, v.subtipo, vp.partido, vp.voto FROM votaciones v
                            JOIN votos_partido vp ON vp.votacion_id = v.id
                            WHERE v.excluida_tramite = 0 AND vp.dividido = 0 ORDER BY v.fecha""").fetchall()
    por = defaultdict(lambda: defaultdict(dict))
    for f in filas:
        p = postura(f["subtipo"], f["voto"])
        if p:
            por[f["partido"]][f["clave_iniciativa"]].setdefault(p, f["id"])
    salida = {}
    for partido, inis in por.items():
        pares = [{"clave_iniciativa": c, "a_favor": d["a_favor"], "en_contra": d["en_contra"]}
                 for c, d in inis.items() if "a_favor" in d and "en_contra" in d]
        if pares:
            salida[partido] = pares
    return salida


def gobierno(conn, partidos: list[dict]) -> dict:
    de_gobierno = {p["id"] for p in partidos if p.get("gobierno")}
    salida = defaultdict(list)
    for c in conn.execute("""SELECT c.*, v.url_boe FROM cruces c JOIN votaciones v ON v.id = c.votacion_id
                             WHERE c.nivel = 'veredicto' AND c.veredicto = 'cumple' AND v.resultado = 'aprobada'
                             AND (v.es_convalidacion = 1 OR v.tipo LIKE 'Dictámenes de Comisiones sobre iniciativas%'
                                  OR v.tipo LIKE 'Enmiendas del Senado%')"""):
        if c["partido"] in de_gobierno:
            salida[c["partido"]].append({"votacion_id": c["votacion_id"], "promesa_id": c["promesa_id"], "url_boe": c["url_boe"]})
    return dict(salida)


def finanzas(raiz: Path) -> dict:
    d = json.loads((raiz / "config" / "finanzas_2023.json").read_text(encoding="utf-8"))
    return {p: {**f, "url_informe": d["url_informe_campana"]} for p, f in d["partidos"].items()}
```

En `exportar.construir`: `"coherencia": analisis.coherencia(conn)`, `"gobierno": analisis.gobierno(conn, partidos)` y `"finanzas": analisis.finanzas(raiz)`.

Nota: la prueba de gobierno con un decreto rechazado usa la consulta `v.resultado = 'aprobada'`. No la quites aunque parezca redundante.

- [ ] **Step 5: Ejecutar las pruebas y hacer commit**

Run: `pytest tests/electoral -v` → PASS todas.

```bash
git add src/electoral/analisis.py src/electoral/exportar.py config/finanzas_2023.json tests/electoral/test_analisis.py
git commit -m "feat(electoral): add stance changes, government delivery and campaign finance"
```

---

### Task 7: Contrato `datos.json` validado

**Files:**
- Create: `schema/datos.schema.json`, `tests/electoral/test_contrato.py`
- Modify: `src/electoral/exportar.py` (validación antes de escribir)

**Interfaces:**
- Produces: `schema/datos.schema.json` (JSON Schema draft 2020-12), que lee el plan 2. `exportar.escribir` lanza `jsonschema.ValidationError` si los datos no cumplen el contrato y no escribe nada.

- [ ] **Step 1: Escribir `schema/datos.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "datos.json de PolígrafoES 29N",
  "type": "object",
  "required": ["meta", "partidos", "votaciones", "promesas", "temas", "cruces", "coherencia", "gobierno", "finanzas"],
  "properties": {
    "meta": {"type": "object", "required": ["version_contrato", "generado", "periodo", "recuentos"]},
    "partidos": {"type": "array", "items": {"type": "object", "required": ["id", "nombre", "escanos_23j", "gobierno"],
      "properties": {"programa_2023": {"type": ["string", "null"]}, "sin_programa": {"type": "string"}}}},
    "votaciones": {"type": "array", "items": {"type": "object",
      "required": ["id", "fecha", "tipo", "subtipo", "expediente", "resultado", "excluida_tramite", "votos", "url_xml", "url_sesion", "url_bocg", "url_boe"],
      "properties": {
        "subtipo": {"enum": ["normal", "devolucion", "texto_alternativo", "tramite"]},
        "resultado": {"enum": ["aprobada", "rechazada"]},
        "url_xml": {"type": "string", "pattern": "^https://www\\.congreso\\.es/"},
        "url_sesion": {"type": "string", "pattern": "^https://www\\.congreso\\.es/"},
        "url_bocg": {"type": ["string", "null"]},
        "url_boe": {"type": ["string", "null"], "pattern": "^https://www\\.boe\\.es/"}}}},
    "promesas": {"type": "array", "items": {"type": "object",
      "required": ["id", "partido", "anio", "texto", "cita", "pagina", "tema", "url_programa_pagina"],
      "properties": {"url_programa_pagina": {"type": "string", "pattern": "#page=\\d+$"}}}},
    "temas": {"type": "object"},
    "cruces": {"type": "array", "items": {"type": "object",
      "required": ["votacion_id", "promesa_id", "partido", "voto", "dividido", "nivel", "veredicto", "jueces"],
      "properties": {"nivel": {"enum": ["veredicto", "juzga_tu"]}, "veredicto": {"enum": ["cumple", "incumple"]},
        "jueces": {"type": "object", "minProperties": 3, "maxProperties": 3}}}},
    "coherencia": {"type": "object"},
    "gobierno": {"type": "object"},
    "finanzas": {"type": "object"}
  }
}
```

- [ ] **Step 2: Escribir la prueba que falla**

```python
# tests/electoral/test_contrato.py
import json
from pathlib import Path

import jsonschema

RAIZ = Path(__file__).resolve().parents[2]


def test_el_json_exportado_cumple_el_contrato_y_todo_cruce_apunta_a_algo_que_existe(cli, zips):
    cli("descargar", "--zips", zips)
    datos = cli("exportar")
    jsonschema.validate(datos, json.loads((RAIZ / "schema" / "datos.schema.json").read_text(encoding="utf-8")))
    ids_v = {v["id"] for v in datos["votaciones"]}
    ids_p = {p["id"] for p in datos["promesas"]}
    for c in datos["cruces"]:
        assert c["votacion_id"] in ids_v and c["promesa_id"] in ids_p
```

- [ ] **Step 3: Comprobar que falla, añadir la validación y que pase**

Run: `pytest tests/electoral/test_contrato.py -v` → FAIL si falta algún bloque o campo. Corrige `exportar.construir` hasta que no falte nada. Después añade la validación en `escribir`:

```python
import jsonschema

ESQUEMA = Path(__file__).resolve().parents[2] / "schema" / "datos.schema.json"


def escribir(datos: dict, salida: Path) -> None:
    jsonschema.validate(datos, json.loads(ESQUEMA.read_text(encoding="utf-8")))
    salida.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
```

Run: `pytest tests/electoral -v` → PASS todas.

- [ ] **Step 4: Commit**

```bash
git add schema/datos.schema.json src/electoral/exportar.py tests/electoral/test_contrato.py
git commit -m "feat(electoral): validate datos.json against the published contract"
```

---

### Task 8: Referencia de calidad y muestra para Fran

**Files:**
- Create: `tests/electoral/test_referencia.py`
- Modify: `electoral.py` (subcomandos `muestra` y `todo`), `pytest.ini` o `pyproject.toml` (marcador `llm`)

**Interfaces:**
- Consumes: `tests/fixtures/electoral/referencia.json` (19 casos revisados por Fran, ya en el repo), `juez.SISTEMA`, `juez.JUECES`, `juez.estables`, `juez.nivel`.
- Produces: `pytest -m llm` (llamadas reales, unos 0,05 $), `python electoral.py muestra --n 30` → `docs/revision_muestra.md`, `python electoral.py todo --tope-extraer 1 --tope-juzgar 4`.

- [ ] **Step 1: Registrar el marcador `llm` y excluirlo por defecto**

Añadir a `pytest.ini` (créalo si no existe):

```ini
[pytest]
markers =
    llm: llama a modelos reales de OpenRouter (cuesta dinero); ejecutar con -m llm
addopts = -m "not llm"
```

- [ ] **Step 2: Escribir la prueba de referencia**

```python
# tests/electoral/test_referencia.py
"""Los 19 cruces revisados por Fran el 2026-10-07. Un cambio de modelo o de instrucciones que empeore esto no se despliega."""
import json
from pathlib import Path

import pytest

from src.electoral import juez
from src.electoral.llm import LLM

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


@pytest.mark.llm
def test_los_19_casos_revisados_por_fran_siguen_saliendo_igual():
    llm = LLM(tope_usd=0.5)
    fallos = []
    for n, caso in enumerate(json.loads((FIX / "referencia.json").read_text(encoding="utf-8"))):
        v = {"expediente": caso["expediente"], "tipo": caso["titulo"], "texto_subgrupo": caso["subgrupo"],
             "resultado": "", "subtipo": "devolucion" if "devoluci" in (caso["expediente"] + caso["subgrupo"]).lower() else "normal"}
        votos = [{"partido": p, "voto": x} for p, x in sorted(caso["votos"].items())]
        cands = [{"id": 1, "partido": caso["partido"], "texto": caso["promesa"]}]
        texto = juez.prompt(v, votos, cands)
        por_juez = {m: juez.estables(llm, m, texto, {1}) for m in juez.JUECES}
        res = juez.nivel({m: (r or {}).get((caso["partido"], 1)) for m, r in por_juez.items()}, False)
        if res != ("veredicto", caso["veredicto_esperado"]):
            fallos.append((n, caso["partido"], caso["expediente"][:80], res))
    print(f"gastado {llm.gastado:.4f} $")
    assert not fallos, fallos
```

- [ ] **Step 3: Ejecutarla con modelos reales**

Run: `pytest -m llm tests/electoral/test_referencia.py -v -s`
Expected: PASS y `gastado` por debajo de 0,10 $. Si falla algún caso, **no se toca la referencia**: se revisan las instrucciones de `juez.SISTEMA` o el armado del prompt.

- [ ] **Step 4: Subcomandos `muestra` y `todo`**

```python
import random


def cmd_muestra(a, conn):
    datos = exportar.construir(conn, RAIZ)
    prom = {p["id"]: p for p in datos["promesas"]}
    vots = {v["id"]: v for v in datos["votaciones"]}
    veredictos = [c for c in datos["cruces"] if c["nivel"] == "veredicto"]
    random.Random(a.semilla).shuffle(veredictos)
    L = ["# Muestra de veredictos para revisar antes de publicar", "",
         "Marca la casilla si estás de acuerdo. Si no, déjala vacía y escribe por qué en «Nota».", ""]
    for n, c in enumerate(veredictos[: a.n], 1):
        p, v = prom[c["promesa_id"]], vots[c["votacion_id"]]
        L += [f"## {n}. {c['partido']}: {c['veredicto'].upper()}", "",
              f"- **Se votó ({v['fecha']}):** {v['expediente'][:300]}",
              f"- **{c['partido']} votó:** {c['voto']}",
              f"- **Promesa:** {p['texto']}",
              f"- **Cita literal (pág. {p['pagina']}):** «{p['cita']}» ({p['url_programa_pagina']})", "",
              f"- [ ] De acuerdo con «{c['veredicto']}»", "- Nota: ", ""]
    (RAIZ / "docs" / "revision_muestra.md").write_text("\n".join(L), encoding="utf-8")
    print(f"{min(a.n, len(veredictos))} casos en docs/revision_muestra.md")


def cmd_todo(a, conn):
    for paso, args in (("descargar", []), ("fuentes", []), ("extraer", ["--tope", str(a.tope_extraer)]),
                       ("juzgar", ["--tope", str(a.tope_juzgar)]), ("exportar", [])):
        print("==>", paso, flush=True)
        main([paso, *args, "--db", a.db])
```

Para que `todo` pueda llamar a `main([...])`, cambia la firma a `def main(argv=None)` y usa `p.parse_args(argv)`. Registrar `muestra` (`--n` 30, `--semilla` 29) y `todo` (`--tope-extraer` 1.0, `--tope-juzgar` 4.0).

- [ ] **Step 5: Ejecutar todas las pruebas y hacer commit**

Run: `pytest tests/electoral -v` → PASS (la de referencia queda excluida por defecto).

```bash
git add tests/electoral/test_referencia.py electoral.py pytest.ini
git commit -m "feat(electoral): add reviewed reference gate, review sample and full run"
```

---

### Task 9: Carga completa, revisión de Fran y código abierto

Esta tarea no lleva TDD: es operación. Cada paso tiene una salida esperada concreta.

**Files:**
- Create: `LICENSE` (MIT), `docs/revision_muestra.md` (generado)
- Modify: `README.md` (sección del motor electoral), `config/partidos_electoral.json` (si se ha cargado algún programa nuevo)

- [ ] **Step 1: Comprobar el límite de la clave antes de gastar**

```bash
python -c "import requests;from dotenv import dotenv_values;k=dotenv_values('.env')['OPENROUTER_API_KEY'];print(requests.get('https://openrouter.ai/api/v1/key',headers={'Authorization':'Bearer '+k},timeout=20).json()['data'])"
```

Expected: `limit_remaining` de 6 $ o más. Si es menor, **para** y pide a Fran que suba el límite (la spec lo prevé: de 5 $ a unos 10 $).

- [ ] **Step 2: Cargar los programas de 2023**

Para cada partido de `config/partidos_electoral.json` con `programa_2023`:

```bash
python electoral.py ingest-programa 2023 PP "https://www.pp.es/storage/2023/07/programa_electoral_pp_23j_feijoo_2023.pdf"
```

Para el PSOE, si el espejo falla, usa el PDF local `psoe_programa.pdf` (el mismo recurso que ya documenta `bootstrap_programs.py`). Expected: «N bloques nuevos» con N > 0 para cada partido.

- [ ] **Step 3: Carga completa**

Run: `python electoral.py todo --tope-extraer 1 --tope-juzgar 4`
Expected: termina con `datos.json` escrito. El gasto acumulado (`SELECT SUM(usd) FROM gasto`) queda por debajo de 4 $. Si un tope corta la carga, se vuelve a lanzar el mismo comando: es reanudable.

- [ ] **Step 4: Muestra para Fran**

Run: `python electoral.py muestra --n 30`
Expected: `docs/revision_muestra.md` con 30 casos. **Se para aquí** hasta que Fran la revise. Si hay menos de 27 acuerdos (90 %), no se publica: se analizan los fallos con Fran.

- [ ] **Step 5: Auditoría de secretos antes de hacer público el repositorio**

```bash
git log --all --oneline -- .env psoe_programa.pdf
git grep -I -n -E "(sk-or-v1-|sk-ant-|ghp_|[0-9]{9,10}:[A-Za-z0-9_-]{35})" $(git rev-list --all) | head
```

Expected: ninguna salida en las dos órdenes. Si sale algo: (1) rota esa clave en su proveedor **antes de nada**, (2) limpia el historial con `git filter-repo` y (3) avisa a Fran. El token del bot de Telegram (`[0-9]{9,10}:…`) es el más probable si alguna vez se comiteó.

- [ ] **Step 6: README y licencia**

Añade al `README.md` una sección «Motor electoral 29N» con: qué hace, cómo se ejecuta (`python electoral.py todo`), de dónde salen los datos, el criterio de veredicto (3 de 3 con relación directa) y el resultado de la referencia (19/19). Crea `LICENSE` con la licencia MIT a nombre de Fran.

- [ ] **Step 7: Commit (el push lo decide Fran)**

```bash
git add README.md LICENSE config/partidos_electoral.json docs/revision_muestra.md
git commit -m "docs(electoral): document the engine and add mit license"
```

No hacer `push` ni cambiar la visibilidad del repositorio en GitHub sin el OK explícito de Fran.
