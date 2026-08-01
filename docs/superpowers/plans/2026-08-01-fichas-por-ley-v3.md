# PolígrafoES v3 — Fichas por ley: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el digest semanal publique un mensaje veraz por ley en vez de decenas de mensajes duplicados que invierten el resultado de la votación.

**Architecture:** El XML del Congreso trae dos campos (`TituloSubGrupo`, `TextoSubGrupo`) que el parser actual ignora; recuperarlos permite clasificar cada votación como sustantiva o parcial de forma determinista y agrupar todas las votaciones de una misma ley bajo una clave de expediente. El digest pasa a emitir un bloque por expediente en vez de uno por votación, el enriquecimiento LLM baja a una llamada por expediente, y el matcher de programas sustituye el solapamiento de palabras por similitud coseno sobre embeddings multilingües.

**Tech Stack:** Python 3.12, SQLite, `requests`, `anthropic` (Haiku 4.5 con structured outputs vía Pydantic), `sentence-transformers` + `numpy`, `pytest`.

## Global Constraints

- Spec de referencia: `docs/superpowers/specs/2026-08-01-fichas-por-ley-v3-design.md`.
- Producción: Orange Pi `root@192.168.1.172`, `/root/projects/poligrafo-es`. **Sin auto-deploy**: `git pull` manual tras cada push.
- Crons: `fetcher.py` 21:00 diario, `digest.py` lunes 10:30. Logs en `/var/log/poligrafo-{fetcher,digest}.log`.
- Modelo LLM: `claude-haiku-4-5` (constante `MODEL` en `src/llm.py`). No cambiar.
- Modelo de embeddings: `intfloat/multilingual-e5-small`. Requiere los prefijos `"query: "` y `"passage: "` en los textos; sin ellos la calidad cae notablemente.
- Migraciones de esquema: patrón `_migrate_v2` de `src/db.py` — `ALTER TABLE` idempotente comprobando `PRAGMA table_info`. Nunca `DROP`.
- Tests: comportamiento observable, no estructura interna. `pytest` desde la raíz del repo.
- Commits en Conventional Commits, descripción en minúscula e imperativo, sin punto final.
- **El canal de Telegram no se toca hasta la Task 10**, y solo tras validación humana del dry-run.

---

### Task 0: Parar el cron del digest antes del lunes

El cron dispara el lunes 3 de agosto a las 10:30 y volverá a enviar la misma avalancha falsa. Se para antes de empezar y se rearma en la Task 10.

**Files:**
- Modify: crontab de root en la Orange Pi (no está en el repo)

- [ ] **Step 1: Comentar la línea del digest**

```bash
ssh root@192.168.1.172 "crontab -l | sed 's|^30 10 \* \* 1 cd /root/projects/poligrafo-es|#PAUSED-v3 &|' | crontab -"
```

- [ ] **Step 2: Verificar que quedó comentada y que el fetcher sigue vivo**

```bash
ssh root@192.168.1.172 "crontab -l | grep -i polig"
```

Esperado: la línea del `digest.py` empieza por `#PAUSED-v3`, la de `fetcher.py` intacta. El fetcher debe seguir corriendo: sigue ingiriendo sesiones nuevas y no publica nada.

---

### Task 1: Fixture real y parseo de los campos de subgrupo

**Files:**
- Create: `tests/fixtures/sesion192.zip`
- Modify: `src/congreso.py:49-70` (`parse_vote_xml`)
- Modify: `src/db.py:79-108` (columnas v3)
- Test: `tests/test_congreso.py`

**Interfaces:**
- Produces: `parse_vote_xml(xml_str)` devuelve además las claves `titulo_subgrupo: str` y `texto_subgrupo: str` (cadena vacía si el campo no existe en el XML).

- [ ] **Step 1: Descargar el ZIP real de la sesión 192 como fixture**

```bash
curl -A "Mozilla/5.0" -o tests/fixtures/sesion192.zip \
  "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/Sesion192/20260714/VOT_20260714201930.zip"
```

Verificar que tiene 56 XML:

```bash
python -c "import zipfile; print(len([n for n in zipfile.ZipFile('tests/fixtures/sesion192.zip').namelist() if n.endswith('.xml')]))"
```

Esperado: `56`

- [ ] **Step 2: Escribir el test que falla**

En `tests/test_congreso.py`, añadir al final:

```python
import zipfile
from pathlib import Path

FIXTURE_ZIP = Path(__file__).parent / "fixtures" / "sesion192.zip"


def _xml_from_zip(numero):
    with zipfile.ZipFile(FIXTURE_ZIP) as zf:
        for name in zf.namelist():
            if name.endswith(f"votacion{numero}.xml"):
                return zf.read(name).decode("utf-8", "replace")
    raise AssertionError(f"votacion{numero} no está en el fixture")


def test_parse_extrae_subgrupo_de_enmienda():
    vote = parse_vote_xml(_xml_from_zip(20))
    assert "Euskal Herria Bildu" in vote["titulo_subgrupo"]
    assert vote["texto_subgrupo"] == "Enmienda 270."


def test_votacion_de_conjunto_no_tiene_subgrupo():
    vote = parse_vote_xml(_xml_from_zip(54))
    assert vote["titulo_subgrupo"] == ""
    assert vote["texto_subgrupo"] == ""


def test_votacion_de_conjunto_de_la_ley_de_discapacidad_fue_aprobada():
    vote = parse_vote_xml(_xml_from_zip(54))
    assert vote["a_favor"] == 179
    assert vote["en_contra"] == 33
    assert compute_resultado(vote["a_favor"], vote["en_contra"]) == "aprobada"
```

- [ ] **Step 3: Ejecutar y confirmar que falla**

Run: `pytest tests/test_congreso.py -k subgrupo -v`
Esperado: FAIL con `KeyError: 'titulo_subgrupo'`

- [ ] **Step 4: Añadir los dos campos al parser**

En `src/congreso.py`, dentro del `return` de `parse_vote_xml`, tras la línea `"texto_expediente": ...`:

```python
        "titulo_subgrupo": info.findtext("TituloSubGrupo", "").strip(),
        "texto_subgrupo": info.findtext("TextoSubGrupo", "").strip(),
```

- [ ] **Step 5: Ejecutar y confirmar que pasa**

Run: `pytest tests/test_congreso.py -v`
Esperado: PASS, incluidos los tests preexistentes sobre `vote_session.xml`

- [ ] **Step 6: Añadir las columnas v3 al esquema**

En `src/db.py`, tras el bloque `_VOTE_V2_COLUMNS`:

```python
_VOTE_V3_COLUMNS = {
    "titulo_subgrupo": "TEXT",
    "texto_subgrupo": "TEXT",
    "clase": "TEXT",
    "expediente_key": "TEXT",
}
```

Y dentro de `_migrate_v2`, justo antes del `if first_time:` (renombrar la función a `_migrate` y actualizar la llamada en `init_db`):

```python
    for col, ctype in _VOTE_V3_COLUMNS.items():
        if col not in vote_cols:
            conn.execute(f"ALTER TABLE votes ADD COLUMN {col} {ctype}")
```

Ojo: `vote_cols` se calcula al principio de la función, antes de los `ALTER` de v2, así que sigue siendo válido para v3.

- [ ] **Step 7: Verificar que la migración es idempotente**

En `tests/test_db_migration.py`, añadir:

```python
def test_migracion_v3_es_idempotente(tmp_path):
    from src.db import init_db, get_conn
    db = tmp_path / "m.db"
    init_db(db)
    init_db(db)  # segunda pasada: no debe reventar
    conn = get_conn(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(votes)")}
    assert {"titulo_subgrupo", "texto_subgrupo", "clase", "expediente_key"} <= cols
    conn.close()
```

Run: `pytest tests/test_db_migration.py -v`
Esperado: PASS

- [ ] **Step 8: Commit**

```bash
git add tests/fixtures/sesion192.zip tests/test_congreso.py tests/test_db_migration.py src/congreso.py src/db.py
git commit -m "feat(congreso): parsear TituloSubGrupo y TextoSubGrupo del xml"
```

---

### Task 2: Clasificador de votaciones y clave de expediente

**Files:**
- Modify: `src/congreso.py`
- Test: `tests/test_congreso.py`

**Interfaces:**
- Produces: `classify_vote(titulo_subgrupo: str) -> str` devuelve `"sustantiva"` o `"parcial"`.
- Produces: `expediente_key(texto_expediente: str) -> str` devuelve la clave normalizada de agrupación.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/test_congreso.py`:

```python
def test_clasifica_sustantiva_cuando_no_hay_subgrupo():
    from src.congreso import classify_vote
    assert classify_vote("") == "sustantiva"


def test_clasifica_enmienda_a_la_totalidad_como_sustantiva():
    from src.congreso import classify_vote
    assert classify_vote("Enmiendas a la totalidad de texto alternativo.") == "sustantiva"


def test_clasifica_enmienda_parcial_como_parcial():
    from src.congreso import classify_vote
    assert classify_vote("Enmiendas presentadas por el Grupo Parlamentario VOX") == "parcial"


def test_clasifica_correccion_tecnica_como_parcial():
    from src.congreso import classify_vote
    assert classify_vote("Corrección técnica.") == "parcial"


def test_sesion_192_produce_7_sustantivas_de_56_votaciones():
    from src.congreso import classify_vote
    import zipfile
    with zipfile.ZipFile(FIXTURE_ZIP) as zf:
        xmls = [zf.read(n).decode("utf-8", "replace")
                for n in zf.namelist() if n.endswith(".xml")]
    clases = [classify_vote(parse_vote_xml(x)["titulo_subgrupo"]) for x in xmls]
    assert len(clases) == 56
    assert clases.count("sustantiva") == 7


def test_expediente_key_agrupa_el_dictamen_con_sus_enmiendas():
    from src.congreso import expediente_key
    enmienda = expediente_key("Proyecto de Ley por la que se modifican el Texto Refundido")
    conjunto = expediente_key("Votación del dictamen del Proyecto de Ley por la que se modifican el Texto Refundido")
    assert enmienda == conjunto


def test_expediente_key_normaliza_espacios_y_mayusculas():
    from src.congreso import expediente_key
    assert expediente_key("  Proyecto   de LEY X ") == expediente_key("proyecto de ley x")
```

- [ ] **Step 2: Ejecutar y confirmar que fallan**

Run: `pytest tests/test_congreso.py -k "clasifica or expediente_key or sustantivas" -v`
Esperado: FAIL con `ImportError: cannot import name 'classify_vote'`

- [ ] **Step 3: Implementar en `src/congreso.py`**

```python
_PREFIJOS_EXPEDIENTE = (
    "votación del dictamen del ",
    "votacion del dictamen del ",
    "votación de conjunto del ",
)


def classify_vote(titulo_subgrupo):
    """
    Clasifica una votación por su TituloSubGrupo.

    'sustantiva' = la votación que decide algo (conjunto de ley, convalidación
    de decreto, toma en consideración, moción, PNL, enmienda a la totalidad).
    'parcial'    = enmienda concreta o trámite dentro de una tramitación; su
                   sentido de voto es táctica parlamentaria, no posicionamiento.
    """
    sg = (titulo_subgrupo or "").strip()
    if not sg:
        return "sustantiva"
    if "totalidad" in sg.lower():
        return "sustantiva"
    return "parcial"


def expediente_key(texto_expediente):
    """Clave de agrupación: todas las votaciones de una misma ley comparten una."""
    key = " ".join((texto_expediente or "").split()).lower()
    for prefijo in _PREFIJOS_EXPEDIENTE:
        if key.startswith(prefijo):
            key = key[len(prefijo):]
            break
    return key
```

- [ ] **Step 4: Ejecutar y confirmar que pasan**

Run: `pytest tests/test_congreso.py -v`
Esperado: PASS, 56 votaciones clasificadas, 7 sustantivas

- [ ] **Step 5: Commit**

```bash
git add src/congreso.py tests/test_congreso.py
git commit -m "feat(congreso): clasificador sustantiva/parcial y clave de expediente"
```

---

### Task 3: Persistir clasificación y consultar por expediente

**Files:**
- Modify: `fetcher.py:98-122` (bloque de inserción de votos)
- Modify: `src/db.py` (`insert_vote`, nueva `get_expedientes_for_digest`)
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `classify_vote`, `expediente_key` de la Task 2.
- Produces: `insert_vote(...)` acepta los kwargs `titulo_subgrupo`, `texto_subgrupo`, `clase`, `expediente_key`.
- Produces: `get_expedientes_for_digest(conn) -> list[dict]`. Cada dict:
  `{"expediente_key": str, "sustantiva": sqlite3.Row, "parciales": list[sqlite3.Row]}`.
  Solo expedientes con al menos una sustantiva `published=0`. Si un expediente tiene varias
  sustantivas, produce una entrada por cada una, todas con la misma lista de parciales.

- [ ] **Step 1: Escribir el test que falla**

En `tests/test_db.py`:

```python
def test_get_expedientes_agrupa_parciales_bajo_su_sustantiva(tmp_path):
    from src.db import (init_db, get_conn, insert_session, insert_vote,
                        get_expedientes_for_digest)
    db = tmp_path / "e.db"
    init_db(db)
    conn = get_conn(db)
    sid = insert_session(conn, 192, "20260714")
    for n in range(1, 4):
        insert_vote(conn, sid, n, "Dictámenes", "Proyecto de Ley X", "14/7/2026",
                    titulo_subgrupo="Enmiendas presentadas por el Grupo Parlamentario VOX",
                    texto_subgrupo=f"Enmienda {n}.", clase="parcial",
                    expediente_key="proyecto de ley x")
    insert_vote(conn, sid, 54, "Dictámenes",
                "Votación del dictamen del Proyecto de Ley X", "14/7/2026",
                titulo_subgrupo="", texto_subgrupo="", clase="sustantiva",
                expediente_key="proyecto de ley x", resultado="aprobada")

    exps = get_expedientes_for_digest(conn)
    assert len(exps) == 1
    assert exps[0]["sustantiva"]["vote_number"] == 54
    assert len(exps[0]["parciales"]) == 3
    conn.close()


def test_expediente_sin_sustantiva_no_se_publica(tmp_path):
    from src.db import (init_db, get_conn, insert_session, insert_vote,
                        get_expedientes_for_digest)
    db = tmp_path / "e2.db"
    init_db(db)
    conn = get_conn(db)
    sid = insert_session(conn, 192, "20260714")
    insert_vote(conn, sid, 1, "Dictámenes", "Proyecto de Ley Y", "14/7/2026",
                titulo_subgrupo="Enmiendas presentadas por el GP VOX",
                texto_subgrupo="Enmienda 1.", clase="parcial",
                expediente_key="proyecto de ley y")
    assert get_expedientes_for_digest(conn) == []
    conn.close()
```

- [ ] **Step 2: Ejecutar y confirmar que falla**

Run: `pytest tests/test_db.py -k expediente -v`
Esperado: FAIL con `TypeError: insert_vote() got an unexpected keyword argument 'titulo_subgrupo'`

- [ ] **Step 3: Ampliar `insert_vote` en `src/db.py`**

Reemplazar la función entera:

```python
def insert_vote(conn, session_id, vote_number, titulo, texto_expediente, fecha,
                categories=None, a_favor=None, en_contra=None,
                abstenciones=None, resultado=None,
                titulo_subgrupo="", texto_subgrupo="", clase=None,
                expediente_key=None):
    conn.execute(
        """INSERT OR IGNORE INTO votes
           (session_id, vote_number, titulo, texto_expediente, fecha, categories,
            a_favor, en_contra, abstenciones, resultado,
            titulo_subgrupo, texto_subgrupo, clase, expediente_key)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (session_id, vote_number, titulo, texto_expediente, fecha,
         json.dumps(categories or []), a_favor, en_contra, abstenciones, resultado,
         titulo_subgrupo, texto_subgrupo, clase, expediente_key)
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM votes WHERE session_id=? AND vote_number=?", (session_id, vote_number)
    ).fetchone()
    return row["id"]
```

- [ ] **Step 4: Añadir `get_expedientes_for_digest` en `src/db.py`**

```python
def get_expedientes_for_digest(conn):
    """
    Expedientes con al menos una votación sustantiva pendiente de publicar.
    Devuelve [{expediente_key, sustantiva: Row, parciales: [Row, ...]}, ...]
    ordenado cronológicamente. Las parciales acompañan a su sustantiva aunque
    ya estuvieran marcadas: son contexto, no contenido publicable por sí mismo.
    """
    sustantivas = conn.execute(
        """SELECT v.*, s.session_number
           FROM votes v JOIN sessions s ON v.session_id = s.id
           WHERE v.published = 0 AND v.clase = 'sustantiva'
           ORDER BY s.session_number, v.vote_number"""
    ).fetchall()

    resultado = []
    for sus in sustantivas:
        parciales = conn.execute(
            """SELECT * FROM votes
               WHERE expediente_key = ? AND clase = 'parcial'
               ORDER BY vote_number""",
            (sus["expediente_key"],),
        ).fetchall()
        resultado.append({
            "expediente_key": sus["expediente_key"],
            "sustantiva": sus,
            "parciales": parciales,
        })
    return resultado
```

- [ ] **Step 5: Conectar el fetcher**

En `fetcher.py`, en el bloque que llama a `insert_vote` (líneas ~108-120), añadir el import y los kwargs:

```python
from src.congreso import (
    fetch_opendata_html, discover_latest_session, download_session_zip,
    parse_vote_xml, compute_resultado, classify_vote, expediente_key,
)
```

```python
                    vote_id = insert_vote(
                        conn,
                        session_id,
                        vote["numero_votacion"],
                        vote["titulo"],
                        vote["texto_expediente"],
                        vote["fecha"],
                        categories=vote_cats,
                        a_favor=vote["a_favor"],
                        en_contra=vote["en_contra"],
                        abstenciones=vote["abstenciones"],
                        resultado=compute_resultado(vote["a_favor"], vote["en_contra"]),
                        titulo_subgrupo=vote["titulo_subgrupo"],
                        texto_subgrupo=vote["texto_subgrupo"],
                        clase=classify_vote(vote["titulo_subgrupo"]),
                        expediente_key=expediente_key(vote["texto_expediente"]),
                    )
```

- [ ] **Step 6: Ejecutar toda la suite**

Run: `pytest -v`
Esperado: PASS

- [ ] **Step 7: Commit**

```bash
git add src/db.py fetcher.py tests/test_db.py
git commit -m "feat(db): agrupar votaciones por expediente con su sustantiva"
```

---

### Task 4: Envío robusto — backoff ante 429 y marcado incremental

Esta es la causa de que veas los mismos mensajes cada lunes. Se arregla antes que el formato porque sin ella cualquier digest largo se vuelve a reenviar entero.

**Files:**
- Modify: `src/publisher.py:11-29`
- Modify: `digest.py:141-167`
- Modify: `src/db.py` (`mark_votes_published`)
- Test: `tests/test_publisher.py`

**Interfaces:**
- Produces: `send_message(token, channel_id, text, max_retries=3, sleep=time.sleep) -> int | None`.
  El parámetro `sleep` es inyectable para que los tests no esperen de verdad.
- Produces: `mark_votes_published(conn, vote_ids, telegram_message_id)` — marca un subconjunto.

- [ ] **Step 1: Escribir los tests que fallan**

Reemplazar `tests/test_publisher.py` por:

```python
from src.publisher import send_message, load_parties


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_devuelve_message_id_en_exito(monkeypatch):
    monkeypatch.setattr("src.publisher.requests.post",
                        lambda *a, **k: FakeResponse(200, {"ok": True, "result": {"message_id": 7}}))
    assert send_message("t", "c", "hola") == 7


def test_reintenta_tras_429_y_acaba_enviando(monkeypatch):
    respuestas = [
        FakeResponse(429, {"ok": False, "parameters": {"retry_after": 2}}),
        FakeResponse(200, {"ok": True, "result": {"message_id": 9}}),
    ]
    monkeypatch.setattr("src.publisher.requests.post", lambda *a, **k: respuestas.pop(0))
    esperas = []
    assert send_message("t", "c", "hola", sleep=esperas.append) == 9
    assert esperas == [2]  # respeta el retry_after que dice Telegram


def test_se_rinde_tras_agotar_reintentos(monkeypatch):
    monkeypatch.setattr("src.publisher.requests.post",
                        lambda *a, **k: FakeResponse(429, {"ok": False, "parameters": {"retry_after": 1}}))
    assert send_message("t", "c", "hola", max_retries=2, sleep=lambda s: None) is None


def test_error_no_429_no_reintenta(monkeypatch):
    llamadas = []

    def post(*a, **k):
        llamadas.append(1)
        return FakeResponse(400, {"ok": False, "description": "Bad Request: message is too long"})

    monkeypatch.setattr("src.publisher.requests.post", post)
    assert send_message("t", "c", "x", sleep=lambda s: None) is None
    assert len(llamadas) == 1


def test_load_parties_mapea_siglas():
    assert load_parties()["GP"] == "PP"
```

Y en `tests/test_digest.py`:

```python
def test_envio_parcial_marca_solo_lo_enviado(tmp_path, monkeypatch):
    from src.db import init_db, get_conn, insert_session, insert_vote, get_votes_for_digest
    import digest as digest_mod

    db = tmp_path / "p.db"
    init_db(db)
    conn = get_conn(db)
    sid = insert_session(conn, 1, "20260714")
    for n in (1, 2):
        insert_vote(conn, sid, n, "Ley", f"Proyecto de Ley {n}", "14/7/2026",
                    clase="sustantiva", expediente_key=f"proyecto de ley {n}",
                    resultado="aprobada")
    conn.close()

    enviados = [11, None]  # el segundo bloque falla
    monkeypatch.setattr(digest_mod, "TOKEN", "t")
    monkeypatch.setattr(digest_mod, "CHANNEL", "c")
    monkeypatch.setattr(digest_mod, "send_message", lambda *a, **k: enviados.pop(0))
    monkeypatch.setattr(digest_mod.time, "sleep", lambda s: None)
    digest_mod.run(db_path=db)

    conn = get_conn(db)
    pendientes = get_votes_for_digest(conn)
    assert len(pendientes) == 1  # el que falló sigue pendiente, el otro no vuelve
    conn.close()
```

- [ ] **Step 2: Ejecutar y confirmar que fallan**

Run: `pytest tests/test_publisher.py -v`
Esperado: FAIL — `send_message() got an unexpected keyword argument 'sleep'`

- [ ] **Step 3: Reescribir `send_message` en `src/publisher.py`**

```python
import json
import time

import requests

TELEGRAM_MAX_RETRIES = 3
THROTTLE_SECONDS = 4


def load_parties(config_path="config/parties.json"):
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def send_message(token, channel_id, text, max_retries=TELEGRAM_MAX_RETRIES, sleep=time.sleep):
    """
    Envía un mensaje al canal. Devuelve el message_id o None.

    Ante 429 respeta el retry_after que indica Telegram y reintenta. Cualquier
    otro error se registra con su cuerpo: el silencio de la versión anterior
    ocultó seis semanas de rate limiting.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": channel_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    for intento in range(1, max_retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=15)
        except requests.exceptions.RequestException as e:
            print(f"  WARN: error de red al enviar (intento {intento}/{max_retries}): {e}")
            if intento == max_retries:
                return None
            sleep(THROTTLE_SECONDS)
            continue

        if r.status_code == 200 and r.json().get("ok"):
            return r.json()["result"]["message_id"]

        if r.status_code == 429:
            espera = r.json().get("parameters", {}).get("retry_after", THROTTLE_SECONDS)
            print(f"  Rate limit: esperando {espera}s (intento {intento}/{max_retries})")
            if intento == max_retries:
                return None
            sleep(espera)
            continue

        print(f"  WARN: Telegram devolvió {r.status_code}: {r.text[:300]}")
        return None
    return None
```

- [ ] **Step 4: Añadir marcado por subconjunto en `src/db.py`**

```python
def mark_votes_published(conn, vote_ids, telegram_message_id):
    """Marca solo los votos indicados. Un envío parcial no reenvía el resto."""
    if not vote_ids:
        return
    for vid in vote_ids:
        conn.execute("UPDATE votes SET published=1 WHERE id=?", (vid,))
    conn.execute(
        "INSERT INTO published_messages (type, ref_id, telegram_message_id, sent_at)"
        " VALUES ('expediente', NULL, ?, ?)",
        (telegram_message_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def mark_boe_published(conn, boe_ids, telegram_message_id):
    if not boe_ids:
        return
    for bid in boe_ids:
        conn.execute("UPDATE boe_entries SET published=1 WHERE id=?", (bid,))
    conn.execute(
        "INSERT INTO published_messages (type, ref_id, telegram_message_id, sent_at)"
        " VALUES ('boe_block', NULL, ?, ?)",
        (telegram_message_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
```

- [ ] **Step 5: Ejecutar los tests de publisher**

Run: `pytest tests/test_publisher.py -v`
Esperado: PASS. El test de `digest` seguirá fallando hasta la Task 8, que reescribe `run()`.

- [ ] **Step 6: Commit**

```bash
git add src/publisher.py src/db.py tests/test_publisher.py tests/test_digest.py
git commit -m "fix(publisher): respetar retry_after en 429 y marcar publicaciones parciales"
```

---

### Task 5: Filtrar el BOE a normas con rango de ley

197 entradas pendientes; el filtro por categorías no basta. Sobre julio, este filtro reduce de 131 a 22.

**Files:**
- Modify: `src/db.py` (`get_boe_for_digest`, `get_unenriched_boe_entries`)
- Test: `tests/test_boe.py`

**Interfaces:**
- Produces: constante `RANGOS_CON_FUERZA_DE_LEY` en `src/db.py`.

- [ ] **Step 1: Escribir el test que falla**

En `tests/test_boe.py`:

```python
def test_digest_boe_solo_incluye_rangos_con_fuerza_de_ley(tmp_path):
    from src.db import init_db, get_conn, insert_boe_entry, get_boe_for_digest
    db = tmp_path / "b.db"
    init_db(db)
    conn = get_conn(db)
    casos = [
        ("BOE-A-1", "Ley 5/2026 de vivienda", "Ley"),
        ("BOE-A-2", "Ley Orgánica 2/2026", "Ley Orgánica"),
        ("BOE-A-3", "Real Decreto-ley 9/2026", "Real Decreto-ley"),
        ("BOE-A-4", "Real Decreto 300/2026 de nombramiento", "Real Decreto"),
        ("BOE-A-5", "Resolución de la Subsecretaría", "Resolución"),
        ("BOE-A-6", "Ley Foral 3/2026 de Navarra", "Ley Foral"),
    ]
    for ident, titulo, rango in casos:
        insert_boe_entry(conn, ident, titulo, rango, "Dpto", "20260714",
                         "url", ["vivienda"], "texto")

    idents = {r["identificador"] for r in get_boe_for_digest(conn)}
    assert idents == {"BOE-A-1", "BOE-A-2", "BOE-A-3"}
    conn.close()
```

- [ ] **Step 2: Ejecutar y confirmar que falla**

Run: `pytest tests/test_boe.py -k fuerza_de_ley -v`
Esperado: FAIL — devuelve los 6 identificadores

- [ ] **Step 3: Implementar el filtro en `src/db.py`**

Junto a las demás constantes del módulo:

```python
RANGOS_CON_FUERZA_DE_LEY = ("Ley", "Ley Orgánica", "Real Decreto-ley", "Decreto-ley")
```

Reemplazar las dos consultas de BOE:

```python
def get_boe_for_digest(conn):
    marcas = ",".join("?" * len(RANGOS_CON_FUERZA_DE_LEY))
    return conn.execute(
        f"""SELECT * FROM boe_entries
            WHERE published=0 AND categories != '[]' AND rango IN ({marcas})
            ORDER BY fecha, id""",
        RANGOS_CON_FUERZA_DE_LEY,
    ).fetchall()


def get_unenriched_boe_entries(conn):
    marcas = ",".join("?" * len(RANGOS_CON_FUERZA_DE_LEY))
    return conn.execute(
        f"""SELECT * FROM boe_entries
            WHERE enriched_at IS NULL AND published = 0
              AND categories != '[]' AND rango IN ({marcas})
            ORDER BY id""",
        RANGOS_CON_FUERZA_DE_LEY,
    ).fetchall()
```

El filtro en `get_unenriched_boe_entries` además deja de gastar API en normas que nunca se van a publicar.

- [ ] **Step 4: Ejecutar y confirmar que pasa**

Run: `pytest tests/test_boe.py -v`
Esperado: PASS

- [ ] **Step 5: Commit**

```bash
git add src/db.py tests/test_boe.py
git commit -m "feat(boe): filtrar digest a normas con fuerza de ley"
```

---

### Task 6: Matcher por embeddings

**Files:**
- Create: `src/embeddings.py`
- Create: `embed_programs.py`
- Modify: `src/db.py` (columna `embedding`, `get_chunks_with_embeddings`, `set_chunk_embedding`)
- Modify: `src/matcher.py` (`top_candidates_per_party`)
- Modify: `requirements.txt`
- Test: `tests/test_matcher.py`

**Interfaces:**
- Produces: `src/embeddings.py:embed_texts(textos: list[str], prefijo: str) -> numpy.ndarray`
  con forma `(n, 384)`, filas normalizadas a norma 1. `prefijo` es `"query: "` o `"passage: "`.
- Produces: `src/matcher.py:top_candidates_per_party(vote_text, chunks, per_party=3, min_similarity=0.80)`
  con la misma forma de retorno que la versión de keywords:
  `{party: [{chunk_id, party, score, text, page_start}, ...]}`. `score` pasa a ser
  la similitud coseno (float 0-1) en vez de un recuento de palabras.
- Consumes: `chunks` debe traer ahora la columna `embedding` (BLOB) además de `id, party, text, page_start`.

- [ ] **Step 1: Añadir la dependencia**

En `requirements.txt`:

```
sentence-transformers
numpy
```

Instalar: `pip install sentence-transformers numpy`

- [ ] **Step 2: Escribir el test que falla**

Reemplazar el contenido de `tests/test_matcher.py` que prueba el prefiltro (conservar los tests de `categorize_text`, que no cambian) y añadir:

```python
import numpy as np
from src.matcher import top_candidates_per_party


def _fake_chunk(cid, party, text, vector):
    v = np.array(vector, dtype=np.float32)
    v = v / np.linalg.norm(v)
    return {"id": cid, "party": party, "text": text, "page_start": 10,
            "embedding": v.tobytes()}


def test_devuelve_candidatos_por_encima_del_umbral(monkeypatch):
    # El voto apunta en la dirección [1,0]; el chunk A coincide, el B es ortogonal.
    monkeypatch.setattr("src.matcher.embed_texts",
                        lambda textos, prefijo: np.array([[1.0, 0.0]], dtype=np.float32))
    chunks = [
        _fake_chunk(1, "PP", "accesibilidad universal", [1.0, 0.02]),
        _fake_chunk(2, "PP", "política pesquera", [0.0, 1.0]),
    ]
    res = top_candidates_per_party("ley de discapacidad", chunks, min_similarity=0.80)
    assert [c["chunk_id"] for c in res["PP"]] == [1]


def test_no_hay_sesgo_por_numero_de_chunks(monkeypatch):
    # PSOE tiene 5 chunks irrelevantes, PNV tiene 1 relevante. Debe ganar PNV.
    monkeypatch.setattr("src.matcher.embed_texts",
                        lambda textos, prefijo: np.array([[1.0, 0.0]], dtype=np.float32))
    chunks = [_fake_chunk(i, "PSOE", "irrelevante", [0.0, 1.0]) for i in range(5)]
    chunks.append(_fake_chunk(99, "PNV", "accesibilidad", [1.0, 0.01]))
    res = top_candidates_per_party("ley de discapacidad", chunks, min_similarity=0.80)
    assert "PSOE" not in res
    assert [c["chunk_id"] for c in res["PNV"]] == [99]


def test_limita_a_per_party_candidatos(monkeypatch):
    monkeypatch.setattr("src.matcher.embed_texts",
                        lambda textos, prefijo: np.array([[1.0, 0.0]], dtype=np.float32))
    chunks = [_fake_chunk(i, "PP", f"texto {i}", [1.0, 0.01 * i]) for i in range(10)]
    res = top_candidates_per_party("ley", chunks, per_party=3, min_similarity=0.80)
    assert len(res["PP"]) == 3
```

- [ ] **Step 3: Ejecutar y confirmar que falla**

Run: `pytest tests/test_matcher.py -k candidatos -v`
Esperado: FAIL — `AttributeError: module 'src.matcher' has no attribute 'embed_texts'`

- [ ] **Step 4: Crear `src/embeddings.py`**

```python
"""
src/embeddings.py — PolígrafoES
Embeddings multilingües para cruzar votaciones con programas electorales.

multilingual-e5-small exige prefijos: "query: " para el texto de búsqueda y
"passage: " para los documentos indexados. Sin ellos la calidad cae.
"""
import numpy as np

MODEL_NAME = "intfloat/multilingual-e5-small"
DIM = 384

_model = None


def _get_model():
    """Carga perezosa: importar sentence-transformers cuesta segundos."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(textos, prefijo):
    """
    textos: list[str]. prefijo: "query: " o "passage: ".
    Returns: np.ndarray (n, DIM) float32, filas normalizadas → el producto
    escalar entre dos filas es directamente su similitud coseno.
    """
    if not textos:
        return np.zeros((0, DIM), dtype=np.float32)
    vectores = _get_model().encode(
        [prefijo + t for t in textos],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vectores, dtype=np.float32)


def to_blob(vector):
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob):
    return np.frombuffer(blob, dtype=np.float32)
```

- [ ] **Step 5: Reescribir `top_candidates_per_party` en `src/matcher.py`**

Borrar `_STOPWORDS`, `_keywords` y el cuerpo antiguo de `top_candidates_per_party`. Conservar
`load_categories` y `categorize_text` sin tocar. Añadir:

```python
import numpy as np

from src.embeddings import embed_texts, from_blob

MIN_SIMILARITY = 0.80


def top_candidates_per_party(vote_text, chunks, per_party=3, min_similarity=MIN_SIMILARITY):
    """
    Top-N chunks por partido por similitud coseno con el texto de la votación.

    A diferencia del prefiltro por keywords que sustituye, no premia a los
    partidos con programas largos: el umbral es absoluto, no relativo.
    """
    chunks = [c for c in chunks if c["embedding"]]
    if not chunks:
        return {}

    consulta = embed_texts([vote_text], "query: ")[0]
    matriz = np.vstack([from_blob(c["embedding"]) for c in chunks])
    similitudes = matriz @ consulta

    by_party = {}
    for chunk, sim in zip(chunks, similitudes):
        if sim < min_similarity:
            continue
        by_party.setdefault(chunk["party"], []).append({
            "chunk_id": chunk["id"],
            "party": chunk["party"],
            "score": float(sim),
            "text": chunk["text"],
            "page_start": chunk["page_start"],
        })

    return {
        party: sorted(cands, key=lambda c: -c["score"])[:per_party]
        for party, cands in by_party.items()
    }
```

- [ ] **Step 6: Ejecutar y confirmar que pasa**

Run: `pytest tests/test_matcher.py -v`
Esperado: PASS

- [ ] **Step 7: Añadir la columna y los accesores en `src/db.py`**

Junto a `_VOTE_V3_COLUMNS`:

```python
_CHUNK_V3_COLUMNS = {"embedding": "BLOB"}
```

Dentro de `_migrate`:

```python
    chunk_cols = {r[1] for r in conn.execute("PRAGMA table_info(program_chunks)")}
    for col, ctype in _CHUNK_V3_COLUMNS.items():
        if col not in chunk_cols:
            conn.execute(f"ALTER TABLE program_chunks ADD COLUMN {col} {ctype}")
```

Y los accesores:

```python
def set_chunk_embedding(conn, chunk_id, blob):
    conn.execute("UPDATE program_chunks SET embedding=? WHERE id=?", (blob, chunk_id))
    conn.commit()


def get_all_program_chunks(conn):
    return conn.execute(
        "SELECT id, party, category, page_start, text, embedding FROM program_chunks"
    ).fetchall()
```

- [ ] **Step 8: Crear `embed_programs.py`**

```python
#!/usr/bin/env python3
"""
embed_programs.py — one-off
Vectoriza los chunks de programa electoral que aún no tienen embedding.
Idempotente: re-ejecutarlo solo procesa lo que falte.
"""
from src.db import init_db, get_conn, set_chunk_embedding
from src.embeddings import embed_texts, to_blob

LOTE = 64


def run():
    init_db()
    conn = get_conn()
    try:
        pendientes = conn.execute(
            "SELECT id, text FROM program_chunks WHERE embedding IS NULL"
        ).fetchall()
        print(f"{len(pendientes)} chunks pendientes de vectorizar.")
        for i in range(0, len(pendientes), LOTE):
            lote = pendientes[i:i + LOTE]
            vectores = embed_texts([r["text"] for r in lote], "passage: ")
            for row, vector in zip(lote, vectores):
                set_chunk_embedding(conn, row["id"], to_blob(vector))
            print(f"  {min(i + LOTE, len(pendientes))}/{len(pendientes)}")
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
```

- [ ] **Step 9: Ejecutar la vectorización en local y comprobar la mejora**

```bash
python embed_programs.py
python -c "
import sqlite3
from src.db import get_conn
from src.matcher import top_candidates_per_party
conn = get_conn()
chunks = conn.execute('SELECT id, party, page_start, text, embedding FROM program_chunks').fetchall()
r = top_candidates_per_party('Proyecto de Ley de derechos de las personas con discapacidad, accesibilidad universal y dependencia', [dict(c) for c in chunks])
for party, cands in sorted(r.items()):
    print(party, [round(c['score'], 3) for c in cands])
"
```

Esperado: aparecen partidos distintos de PSOE/PP/SUMAR (los nacionalistas ya no salen a cero).
Si ningún partido supera el umbral, bajar `MIN_SIMILARITY` a `0.78` y repetir; si salen más de
6-7 partidos con puntuaciones muy juntas, subirlo a `0.82`. Anotar el valor elegido en el commit.

- [ ] **Step 10: Commit**

```bash
git add src/embeddings.py src/matcher.py src/db.py embed_programs.py requirements.txt tests/test_matcher.py
git commit -m "feat(matcher): similitud coseno con embeddings multilingues en vez de keywords"
```

---

### Task 7: Enriquecimiento por expediente con veredicto de coherencia

**Files:**
- Modify: `src/llm.py`
- Modify: `fetcher.py:31-56` (`enrich_pending`)
- Modify: `src/db.py` (`get_unenriched_expedientes`, `insert_vote_program_match` con veredicto)
- Test: `tests/test_llm.py`

**Interfaces:**
- Produces: `enrich_expediente(expediente: dict, candidates: dict, client=None) -> VoteEnrichment`
  donde `expediente` es `{"texto_expediente": str, "titulo": str, "resultado": str,
  "a_favor": int, "en_contra": int, "enmiendas": [{"grupo": str, "detalle": str, "resultado": str}]}`.
- Produces: modelo Pydantic `PartyMatch` con campos `party: str`, `chunk_id: int | None`,
  `promesa: str`, `veredicto: Literal["cumple", "incumple"] | None`.
- Consumes: `top_candidates_per_party` de la Task 6.

- [ ] **Step 1: Escribir el test que falla**

En `tests/test_llm.py`:

```python
from src.llm import PartyMatch, VoteEnrichment, build_expediente_prompt


def test_prompt_incluye_resultado_y_recuento_de_enmiendas():
    prompt = build_expediente_prompt(
        {
            "texto_expediente": "Proyecto de Ley de discapacidad",
            "titulo": "Dictámenes de Comisiones sobre iniciativas legislativas.",
            "resultado": "aprobada",
            "a_favor": 179,
            "en_contra": 33,
            "enmiendas": [
                {"grupo": "Junts", "detalle": "Enmienda 174.", "resultado": "rechazada"},
                {"grupo": "PNV", "detalle": "Enmienda 14.", "resultado": "rechazada"},
            ],
        },
        {},
    )
    assert "aprobada" in prompt
    assert "179" in prompt
    assert "Junts" in prompt
    assert "2 votaciones de enmiendas" in prompt


def test_match_sin_veredicto_es_valido_pero_se_descarta_al_publicar():
    m = PartyMatch(party="PP", chunk_id=None, promesa="", veredicto=None)
    assert m.chunk_id is None
    assert m.veredicto is None


def test_match_con_veredicto_conserva_la_promesa():
    m = PartyMatch(party="PP", chunk_id=12,
                   promesa="blindar por ley el apoyo a la discapacidad",
                   veredicto="incumple")
    assert m.veredicto == "incumple"
    assert "blindar" in m.promesa
```

- [ ] **Step 2: Ejecutar y confirmar que falla**

Run: `pytest tests/test_llm.py -v`
Esperado: FAIL — `ImportError: cannot import name 'build_expediente_prompt'`

- [ ] **Step 3: Reescribir los modelos y el prompt en `src/llm.py`**

Sustituir `PartyMatch` y añadir el constructor de prompt:

```python
from typing import Literal, Optional


class PartyMatch(BaseModel):
    party: str
    chunk_id: Optional[int]      # None si ningún extracto del partido es pertinente
    promesa: str                 # la promesa parafraseada en una línea; "" si no hay match
    veredicto: Optional[Literal["cumple", "incumple"]]  # None si no se puede afirmar


class VoteEnrichment(BaseModel):
    resumen: str
    que_cambia: str
    matches: list[PartyMatch]


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

    valid_ids = set()
    for party, cands in candidates.items():
        partes.append(f"\nExtractos del programa electoral de {party}:")
        for c in cands:
            valid_ids.add(c["chunk_id"])
            partes.append(f"[chunk_id={c['chunk_id']}] (p.{c['page_start']}) {c['text'][:600]}")
    if not candidates:
        partes.append("\n(No hay extractos de programas candidatos para esta votación.)")

    return "\n".join(partes)
```

- [ ] **Step 4: Actualizar el system prompt**

En `_SYSTEM_VOTE`, sustituir la regla de `matches` por:

```
- matches: por cada partido con extractos, decide si ese partido se pronunció en su
  programa sobre la materia CONCRETA que se vota.
  · Si no se pronunció: chunk_id null, promesa "", veredicto null.
  · Si se pronunció: chunk_id del extracto, promesa = esa promesa parafraseada en una
    línea llana (máximo 15 palabras), y veredicto comparando la promesa con el sentido
    de voto del partido en esta votación: "cumple" si votó en coherencia con lo que
    prometió, "incumple" si votó en contra de lo que prometió.
  · Si hay extracto pertinente pero no puedes afirmar con seguridad si cumple o
    incumple: veredicto null. Es preferible el silencio a un veredicto dudoso.
  · Compartir vocabulario NO es pronunciarse. Para tratados internacionales, solo hay
    match si el extracto menciona ese país, ese tipo de acuerdo bilateral o esa
    política exterior concreta. En caso de duda, null.
```

- [ ] **Step 5: Sustituir `enrich_vote` por `enrich_expediente`**

```python
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
```

- [ ] **Step 6: Guardar promesa y veredicto**

En `src/db.py`, añadir columnas a `vote_program_matches` siguiendo el patrón de migración:

```python
_MATCH_V3_COLUMNS = {"promesa": "TEXT", "veredicto": "TEXT"}
```

```python
    match_cols = {r[1] for r in conn.execute("PRAGMA table_info(vote_program_matches)")}
    for col, ctype in _MATCH_V3_COLUMNS.items():
        if col not in match_cols:
            conn.execute(f"ALTER TABLE vote_program_matches ADD COLUMN {col} {ctype}")
```

Y actualizar los dos accesores:

```python
def insert_vote_program_match(conn, vote_id, chunk_id, party, score, promesa, veredicto):
    conn.execute(
        """INSERT OR IGNORE INTO vote_program_matches
           (vote_id, chunk_id, party, score, promesa, veredicto)
           VALUES (?,?,?,?,?,?)""",
        (vote_id, chunk_id, party, score, promesa, veredicto),
    )
    conn.commit()


def get_validated_matches(conn, vote_id):
    """Solo matches con veredicto: un extracto sin conclusión es ruido."""
    return conn.execute(
        """SELECT vm.party, vm.promesa, vm.veredicto, pc.page_start
           FROM vote_program_matches vm
           JOIN program_chunks pc ON vm.chunk_id = pc.id
           WHERE vm.vote_id = ? AND vm.veredicto IS NOT NULL
           ORDER BY vm.party""",
        (vote_id,),
    ).fetchall()
```

- [ ] **Step 7: Crear el mapa de nombres largos de grupo**

Los `TituloSubGrupo` traen el nombre largo del grupo, no la sigla. Crear
`config/grupos_enmienda.json`:

```json
{
  "Enmiendas presentadas por el Grupo Parlamentario Popular en el Congreso": "PP",
  "Enmienda presentada por el Grupo Parlamentario Popular en el Congreso": "PP",
  "Enmiendas presentadas por el Grupo Parlamentario Socialista": "PSOE",
  "Enmienda presentada por el Grupo Parlamentario Socialista": "PSOE",
  "Enmiendas presentadas por el Grupo Parlamentario VOX": "Vox",
  "Enmiendas presentadas por el Grupo Parlamentario Plurinacional SUMAR": "Sumar",
  "Enmiendas presentadas por el Grupo Parlamentario Republicano": "ERC",
  "Enmiendas presentadas por el Grupo Parlamentario Junts per Catalunya": "Junts",
  "Enmiendas presentadas por el Grupo Parlamentario Euskal Herria Bildu": "EH Bildu",
  "Enmiendas presentadas por el Grupo Parlamentario Vasco (EAJ-PNV)": "PNV",
  "Enmiendas presentadas por el Grupo Parlamentario Mixto (Sra. Belarra Urteaga)": "Podemos",
  "Enmiendas presentadas por el Grupo Parlamentario Mixto (Sr. Rego Candamil)": "BNG",
  "Enmiendas presentadas por el Grupo Parlamentario Mixto (Sr. Catalán Higueras)": "UPN",
  "Corrección técnica.": "Corrección técnica"
}
```

En `src/publisher.py`:

```python
def load_parties_largo(config_path="config/grupos_enmienda.json"):
    """Nombres largos de grupo tal como vienen en TituloSubGrupo → etiqueta corta."""
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)
```

Un grupo no mapeado saldrá con su nombre largo — feo pero veraz. Al aparecer uno nuevo, se
añade al JSON.

- [ ] **Step 8: Reescribir `enrich_pending` en `fetcher.py`**

Sustituir el bucle de votos por uno sobre expedientes. El enriquecimiento se guarda en la
votación **sustantiva**; las parciales no se enriquecen nunca.

```python
def enrich_pending(conn):
    """Enriquece los expedientes pendientes (una llamada LLM por expediente).
    Un fallo en uno no detiene el resto: queda NULL y se reintenta mañana."""
    from src.db import get_expedientes_for_digest
    all_chunks = [dict(c) for c in get_all_program_chunks(conn)]
    parties = load_parties_largo()

    for exp in get_expedientes_for_digest(conn):
        sus = exp["sustantiva"]
        if sus["enriched_at"]:
            continue
        try:
            enmiendas = [
                {"grupo": parties.get(p["titulo_subgrupo"], p["titulo_subgrupo"]),
                 "detalle": p["texto_subgrupo"],
                 "resultado": p["resultado"] or "desconocido"}
                for p in exp["parciales"]
            ]
            candidates = top_candidates_per_party(
                sus["texto_expediente"] + " " + (sus["titulo"] or ""), all_chunks
            )
            enrichment = enrich_expediente(
                {
                    "texto_expediente": sus["texto_expediente"],
                    "titulo": sus["titulo"],
                    "resultado": sus["resultado"],
                    "a_favor": sus["a_favor"],
                    "en_contra": sus["en_contra"],
                    "enmiendas": enmiendas,
                },
                candidates,
            )
            score_by_chunk = {c["chunk_id"]: c["score"]
                              for cands in candidates.values() for c in cands}
            for m in enrichment.matches:
                insert_vote_program_match(
                    conn, sus["id"], m.chunk_id, m.party,
                    score_by_chunk.get(m.chunk_id, 0.0), m.promesa, m.veredicto,
                )
            set_vote_enrichment(conn, sus["id"], enrichment.resumen, enrichment.que_cambia)
            print(f"  Enriched expediente {sus['id']}: {enrichment.resumen}")
        except Exception as e:
            print(f"  WARN: enrichment failed for expediente {sus['id']}: {e}")
```

Actualizar los imports de `fetcher.py`: `enrich_expediente` en vez de `enrich_vote`, y añadir
`load_parties_largo` desde `src.publisher`. El `.get(clave, clave)` sobre el mapa del Step 7
hace de fallback para grupos no mapeados.

- [ ] **Step 9: Ejecutar los tests**

Run: `pytest tests/test_llm.py -v`
Esperado: PASS

- [ ] **Step 10: Commit**

```bash
git add src/llm.py src/db.py src/publisher.py fetcher.py config/grupos_enmienda.json tests/test_llm.py
git commit -m "feat(llm): enriquecer por expediente y emitir veredicto de coherencia"
```

---

### Task 8: El digest emite una ficha por ley

**Files:**
- Modify: `digest.py`
- Test: `tests/test_digest.py`

**Interfaces:**
- Produces: `format_expediente_block(exp: dict, parties: dict, grupos_largos: dict) -> str`
  donde `exp` tiene la forma que devuelve `get_expedientes_for_digest`, más las claves
  `groups` (`{code: {voto, divided}}`) y `matches` (lista de filas de `get_validated_matches`).
- Consumes: `get_expedientes_for_digest`, `mark_votes_published`, `mark_boe_published`.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/test_digest.py`:

```python
GRUPOS_LARGOS = {"Enmiendas presentadas por el Grupo Parlamentario Junts per Catalunya": "Junts"}

EXPEDIENTE = {
    "sustantiva": {
        "titulo": "Dictámenes de Comisiones sobre iniciativas legislativas.",
        "resumen": "Ley de discapacidad: más accesibilidad, autonomía y dependencia",
        "que_cambia": "Ya es ley: amplía prestaciones y accesibilidad universal.",
        "resultado": "aprobada", "a_favor": 179, "en_contra": 33,
    },
    "parciales": [
        {"titulo_subgrupo": "Enmiendas presentadas por el Grupo Parlamentario Junts per Catalunya",
         "texto_subgrupo": "Enmienda 174.", "resultado": "rechazada"},
        {"titulo_subgrupo": "Enmiendas presentadas por el Grupo Parlamentario Junts per Catalunya",
         "texto_subgrupo": "Enmienda 178.", "resultado": "rechazada"},
    ],
    "groups": {
        "GS": {"voto": "Sí", "divided": False},
        "GP": {"voto": "Abstención", "divided": False},
        "GVOX": {"voto": "No", "divided": False},
    },
    "matches": [
        {"party": "PP", "promesa": "blindar por ley el apoyo a la discapacidad",
         "veredicto": "incumple", "page_start": 30},
    ],
}


def test_ficha_muestra_resultado_real_con_totales():
    block = format_expediente_block(EXPEDIENTE, PARTIES, GRUPOS_LARGOS)
    assert "APROBADA" in block
    assert "179" in block and "33" in block
    assert "RECHAZADA" not in block


def test_ficha_agrega_las_enmiendas_en_una_linea():
    block = format_expediente_block(EXPEDIENTE, PARTIES, GRUPOS_LARGOS)
    assert "2 enmiendas" in block
    assert "Junts 2" in block
    assert "Enmienda 174" not in block  # el detalle no se publica


def test_ficha_publica_veredicto_no_extracto_crudo():
    block = format_expediente_block(EXPEDIENTE, PARTIES, GRUPOS_LARGOS)
    assert "blindar por ley" in block
    assert "p.30" in block
    assert "Incoherente" in block


def test_match_sin_veredicto_no_se_publica():
    exp = {**EXPEDIENTE, "matches": [
        {"party": "PSOE", "promesa": "algo", "veredicto": None, "page_start": 10}]}
    block = format_expediente_block(exp, PARTIES, GRUPOS_LARGOS)
    assert "PSOE" not in block.split("Absten")[-1]
```

Importar `format_expediente_block` al principio del fichero.

- [ ] **Step 2: Ejecutar y confirmar que falla**

Run: `pytest tests/test_digest.py -k ficha -v`
Esperado: FAIL — `ImportError: cannot import name 'format_expediente_block'`

- [ ] **Step 3: Implementar el formateador en `digest.py`**

Sustituir `format_vote_block` por:

```python
import collections

_VEREDICTO_TEXTO = {
    "cumple": "Coherente con su programa.",
    "incumple": "Incoherente con su programa.",
}


def format_expediente_block(exp, parties, grupos_largos):
    """Una ficha por ley: qué se votó, cómo acabó, quién votó qué."""
    sus = exp["sustantiva"]
    lines = []

    titulo = sus.get("resumen") or (sus["titulo"] or "")[:120]
    lines.append(f"🗳️ <b>{html.escape(titulo)}</b>")

    resultado = _RESULT_LABEL.get(sus.get("resultado"), "")
    if resultado:
        totales = ""
        if sus.get("a_favor") is not None and sus.get("en_contra") is not None:
            totales = f" ({sus['a_favor']} a favor / {sus['en_contra']} en contra)"
        lines.append(f"{resultado}{totales}")
    if sus.get("que_cambia"):
        lines.append(html.escape(sus["que_cambia"]))

    lines.append("")
    by_sense = {}
    for code, gv in exp.get("groups", {}).items():
        name = parties.get(code, code)
        if gv.get("divided"):
            name += " (div.)"
        by_sense.setdefault(gv["voto"], []).append(name)
    for s in _SENSE_ORDER:
        if s in by_sense:
            lines.append(
                f"{_SENSE_ICON[s]} {_SENSE_LABEL[s]}: "
                f"{html.escape(' · '.join(by_sense[s]))}"
            )

    parciales = exp.get("parciales") or []
    if parciales:
        por_grupo = collections.Counter(
            grupos_largos.get(p["titulo_subgrupo"], p["titulo_subgrupo"])
            for p in parciales
        )
        detalle = " · ".join(f"{g} {n}" for g, n in por_grupo.most_common())
        lines.append("")
        lines.append(f"🔎 {len(parciales)} enmiendas votadas antes del texto final.")
        lines.append(f"   {html.escape(detalle)}")

    veredictos = [m for m in exp.get("matches", []) if m.get("veredicto")]
    if veredictos:
        lines.append("")
        for m in veredictos:
            lines.append(
                f"📋 <b>{html.escape(m['party'])}</b> prometió (p.{m['page_start']}): "
                f"<i>{html.escape(m['promesa'])}</i> → "
                f"{_VEREDICTO_TEXTO[m['veredicto']]}"
            )

    return "\n".join(lines)
```

- [ ] **Step 4: Reescribir `run()` en `digest.py`**

```python
def run(dry_run=False, db_path=None):
    if not TOKEN or not CHANNEL:
        print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID must be set in .env")
        sys.exit(1)

    db_path = db_path or DEFAULT_DB
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        parties = load_parties()
        grupos_largos = load_parties_largo()
        expedientes = get_expedientes_for_digest(conn)
        boe_rows = get_boe_for_digest(conn)

        print(f"Digest: {len(expedientes)} expedientes, {len(boe_rows)} BOE pendientes.")
        if not expedientes and not boe_rows:
            print("Nothing to digest this week.")
            return

        # Un mensaje por expediente: cada uno se marca en cuanto sale.
        for exp in expedientes:
            sus = exp["sustantiva"]
            exp["groups"] = {
                g["grupo_code"]: {"voto": g["voto"], "divided": bool(g["divided"])}
                for g in get_vote_groups(conn, sus["id"])
            }
            exp["matches"] = [dict(m) for m in get_validated_matches(conn, sus["id"])]
            texto = format_expediente_block(exp, parties, grupos_largos)

            if dry_run:
                print(f"\n--- DRY RUN expediente {sus['id']} ---\n{texto}\n--- END ---")
                continue

            msg_id = send_message(TOKEN, CHANNEL, texto)
            if msg_id:
                ids = [sus["id"]] + [p["id"] for p in exp["parciales"]]
                mark_votes_published(conn, ids, msg_id)
                print(f"  Sent expediente {sus['id']} -> msg {msg_id}")
            else:
                print(f"  WARN: falló el envío del expediente {sus['id']}; sigue pendiente")
            time.sleep(THROTTLE_SECONDS)

        if boe_rows:
            boe_lines = ["📜 <b>BOE — normas con rango de ley</b>"]
            boe_lines += [format_boe_line(dict(r)) for r in boe_rows]
            for texto in build_messages("", ["\n".join(boe_lines)], "PolígrafoES"):
                if dry_run:
                    print(f"\n--- DRY RUN BOE ---\n{texto}\n--- END ---")
                    continue
                msg_id = send_message(TOKEN, CHANNEL, texto)
                if msg_id:
                    mark_boe_published(conn, [r["id"] for r in boe_rows], msg_id)
                time.sleep(THROTTLE_SECONDS)

        if dry_run:
            print("\nDry run: nada marcado como publicado.")
        print("\nDone.")
    finally:
        conn.close()
```

Actualizar los imports de `digest.py`: añadir `time`, `collections`,
`get_expedientes_for_digest`, `mark_votes_published`, `mark_boe_published`,
`load_parties_largo`, `THROTTLE_SECONDS`; quitar `get_votes_for_digest` y
`mark_digest_published`.

- [ ] **Step 5: Ejecutar toda la suite**

Run: `pytest -v`
Esperado: PASS, incluido `test_envio_parcial_marca_solo_lo_enviado` de la Task 4

- [ ] **Step 6: Commit**

```bash
git add digest.py tests/test_digest.py
git commit -m "feat(digest): una ficha por ley en vez de un mensaje por votacion"
```

---

### Task 9: Test end-to-end sobre la sesión 192

El test que demuestra que el problema original está resuelto.

**Files:**
- Create: `tests/test_e2e_sesion192.py`

- [ ] **Step 1: Escribir el test**

```python
"""
End-to-end sobre el ZIP real de la sesión 192 (14/7/2026).
Regresión del fallo original: 56 votaciones producían 49 mensajes contradictorios
que decían que la ley de discapacidad fue RECHAZADA. Se aprobó, 179-33.
"""
import zipfile
from pathlib import Path

import pytest

from src.congreso import parse_vote_xml, compute_resultado, classify_vote, expediente_key
from src.db import (init_db, get_conn, insert_session, insert_vote, insert_vote_groups,
                    get_expedientes_for_digest, get_vote_groups)
from digest import format_expediente_block
from src.publisher import load_parties, load_parties_largo

FIXTURE_ZIP = Path(__file__).parent / "fixtures" / "sesion192.zip"


@pytest.fixture
def db_sesion192(tmp_path):
    """Ingesta completa del ZIP real, sin LLM ni red."""
    db = tmp_path / "e2e.db"
    init_db(db)
    conn = get_conn(db)
    sid = insert_session(conn, 192, "20260714")
    with zipfile.ZipFile(FIXTURE_ZIP) as zf:
        for name in sorted(n for n in zf.namelist() if n.endswith(".xml")):
            v = parse_vote_xml(zf.read(name).decode("utf-8", "replace"))
            vid = insert_vote(
                conn, sid, v["numero_votacion"], v["titulo"], v["texto_expediente"],
                v["fecha"], categories=["social"],
                a_favor=v["a_favor"], en_contra=v["en_contra"],
                abstenciones=v["abstenciones"],
                resultado=compute_resultado(v["a_favor"], v["en_contra"]),
                titulo_subgrupo=v["titulo_subgrupo"], texto_subgrupo=v["texto_subgrupo"],
                clase=classify_vote(v["titulo_subgrupo"]),
                expediente_key=expediente_key(v["texto_expediente"]),
            )
            insert_vote_groups(conn, vid, v["group_votes"])
    yield conn
    conn.close()


def test_56_votaciones_producen_7_fichas(db_sesion192):
    assert len(get_expedientes_for_digest(db_sesion192)) == 7


def _ficha_discapacidad(conn):
    parties, largos = load_parties(), load_parties_largo()
    for exp in get_expedientes_for_digest(conn):
        if "discapacidad" not in exp["expediente_key"]:
            continue
        sus = exp["sustantiva"]
        exp["groups"] = {g["grupo_code"]: {"voto": g["voto"], "divided": bool(g["divided"])}
                         for g in get_vote_groups(conn, sus["id"])}
        exp["matches"] = []
        return exp, format_expediente_block(exp, parties, largos)
    raise AssertionError("la ley de discapacidad no aparece en el digest")


def test_la_ley_de_discapacidad_sale_como_aprobada(db_sesion192):
    _, ficha = _ficha_discapacidad(db_sesion192)
    assert "APROBADA" in ficha
    assert "RECHAZADA" not in ficha
    assert "179 a favor / 33 en contra" in ficha


def test_la_ley_de_discapacidad_sale_en_una_sola_ficha(db_sesion192):
    fichas = [e for e in get_expedientes_for_digest(db_sesion192)
              if "discapacidad" in e["expediente_key"]]
    assert len(fichas) == 1


def test_las_49_parciales_no_generan_ficha_propia(db_sesion192):
    exp, ficha = _ficha_discapacidad(db_sesion192)
    assert len(exp["parciales"]) == 49
    assert "49 enmiendas" in ficha
    assert "Enmienda 270" not in ficha


def test_la_abstencion_del_pp_aparece_en_la_ficha(db_sesion192):
    _, ficha = _ficha_discapacidad(db_sesion192)
    assert "Abstención: PP" in ficha
    assert "En contra: Vox" in ficha
```

- [ ] **Step 2: Ejecutar**

Run: `pytest tests/test_e2e_sesion192.py -v`
Esperado: PASS, 5 tests

Si `test_56_votaciones_producen_7_fichas` falla por un número distinto, no ajustar el número
sin más: imprimir los `titulo_subgrupo` de las sustantivas y comprobar si el clasificador está
dejando pasar algo que no debería.

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e_sesion192.py
git commit -m "test: e2e sobre la sesion 192 real, la ley de discapacidad se aprobo"
```

---

### Task 10: Despliegue, backfill y migración del canal

**Files:**
- Create: `scripts/reclasificar_v3.py`
- Create: `scripts/limpiar_canal.py`

**Interfaces:**
- Consumes: todo lo anterior.

- [ ] **Step 1: Escribir el script de reclasificación**

`scripts/reclasificar_v3.py`:

```python
#!/usr/bin/env python3
"""
Backfill v3: reclasifica los 225 votos existentes y prepara el estado del canal.

- Rellena clase y expediente_key en todos los votos (re-descarga los ZIP de sesión
  para recuperar los campos de subgrupo, que no estaban al ingerirlos).
- Purga enriquecimientos y matches: los resúmenes viejos son alucinaciones y los
  matches vienen del prefiltro por keywords.
- Marca mayo y junio como publicados: se conservan en la base para el futuro
  informe acumulado, pero no vuelven al canal.
"""
import sys

from src.db import init_db, get_conn
from src.congreso import (download_session_zip, parse_vote_xml, classify_vote,
                          expediente_key)

CORTE_JULIO = "202607"


def run(dry_run=False):
    init_db()
    conn = get_conn()
    try:
        sesiones = conn.execute(
            "SELECT id, session_number, session_date, zip_url FROM sessions"
            " WHERE zip_url IS NOT NULL ORDER BY session_number"
        ).fetchall()

        for s in sesiones:
            print(f"Sesión {s['session_number']} ({s['session_date']})...")
            try:
                xmls = download_session_zip(s["zip_url"])
            except Exception as e:
                print(f"  WARN: no se pudo descargar: {e}")
                continue
            for _, xml_str in xmls:
                try:
                    v = parse_vote_xml(xml_str)
                except Exception:
                    continue
                conn.execute(
                    """UPDATE votes SET titulo_subgrupo=?, texto_subgrupo=?,
                       clase=?, expediente_key=?
                       WHERE session_id=? AND vote_number=?""",
                    (v["titulo_subgrupo"], v["texto_subgrupo"],
                     classify_vote(v["titulo_subgrupo"]),
                     expediente_key(v["texto_expediente"]),
                     s["id"], v["numero_votacion"]),
                )
            conn.commit()

        conn.execute("DELETE FROM vote_program_matches")
        conn.execute("UPDATE votes SET resumen=NULL, que_cambia=NULL, enriched_at=NULL")
        # Julio vuelve a la cola; mayo y junio quedan archivados sin republicar.
        # El corte va por session_date de la sesión, no por el campo fecha del voto
        # (que viene del XML en formato "14/7/2026" y no ordena lexicográficamente).
        conn.execute("""
            UPDATE votes SET published = 1
            WHERE id IN (
                SELECT v.id FROM votes v JOIN sessions s ON v.session_id = s.id
                WHERE s.session_date < ?
            )""", (CORTE_JULIO + "01",))
        conn.execute("""
            UPDATE votes SET published = 0
            WHERE id IN (
                SELECT v.id FROM votes v JOIN sessions s ON v.session_id = s.id
                WHERE s.session_date >= ?
            )""", (CORTE_JULIO + "01",))
        conn.execute("UPDATE boe_entries SET published = 1 WHERE fecha < ?",
                     (CORTE_JULIO + "01",))
        conn.execute("UPDATE boe_entries SET published = 0 WHERE fecha >= ?",
                     (CORTE_JULIO + "01",))

        if dry_run:
            conn.rollback()
            print("\nDry run: nada guardado.")
        else:
            conn.commit()

        pendientes = conn.execute(
            "SELECT COUNT(*) FROM votes WHERE published=0 AND clase='sustantiva'"
        ).fetchone()[0]
        print(f"\nSustantivas pendientes de publicar: {pendientes}")
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
```

- [ ] **Step 2: Desplegar el código en la Orange Pi**

```bash
git push
ssh root@192.168.1.172 "cd /root/projects/poligrafo-es && git pull && pip3 install -r requirements.txt"
```

- [ ] **Step 3: Vectorizar los programas en la Pi**

```bash
ssh root@192.168.1.172 "cd /root/projects/poligrafo-es && python3 embed_programs.py"
```

La primera ejecución descarga el modelo (~470 MB). Con 4 cores y ~2.000 chunks tarda unos
minutos. Si la Pi se queda sin memoria, bajar `LOTE` a 16.

- [ ] **Step 4: Backfill en dry-run, luego de verdad**

```bash
ssh root@192.168.1.172 "cd /root/projects/poligrafo-es && python3 scripts/reclasificar_v3.py --dry-run"
ssh root@192.168.1.172 "cd /root/projects/poligrafo-es && python3 scripts/reclasificar_v3.py"
```

- [ ] **Step 5: Enriquecer los expedientes de julio**

```bash
ssh root@192.168.1.172 "cd /root/projects/poligrafo-es && python3 -c 'from src.db import init_db, get_conn; from fetcher import enrich_pending; init_db(); c=get_conn(); enrich_pending(c); c.close()'"
```

- [ ] **Step 6: Dry-run del digest y revisión humana — GATE**

```bash
ssh root@192.168.1.172 "cd /root/projects/poligrafo-es && python3 digest.py --dry-run"
```

**Criterio de aceptación, verificado por Fran antes de continuar:**
- La ley de discapacidad aparece **una vez**, como **APROBADA (179/33)**.
- El PP figura en abstención, Vox en contra.
- Ninguna ficha repite el asunto de otra.
- Los veredictos de programa que aparezcan son legibles y defendibles.

**No continuar a la Step 7 sin el visto bueno explícito.** El paso siguiente borra el canal.

- [ ] **Step 7: Vaciar el canal**

`scripts/limpiar_canal.py`:

```python
#!/usr/bin/env python3
"""
Borra el historial del canal de Telegram. Irreversible.
El bot es administrador con can_delete_messages, así que no le aplica el límite
de 48 horas de la API.
"""
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL = os.environ["TELEGRAM_CHANNEL_ID"]


def run(hasta, dry_run=False):
    url = f"https://api.telegram.org/bot{TOKEN}/deleteMessage"
    borrados = 0
    for msg_id in range(1, hasta + 1):
        if dry_run:
            continue
        r = requests.post(url, json={"chat_id": CHANNEL, "message_id": msg_id}, timeout=15)
        if r.status_code == 200 and r.json().get("ok"):
            borrados += 1
        elif r.status_code == 429:
            espera = r.json().get("parameters", {}).get("retry_after", 5)
            time.sleep(espera)
            continue
        time.sleep(0.1)
    print(f"Borrados {borrados} de {hasta} intentos.")


if __name__ == "__main__":
    hasta = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 260
    run(hasta, dry_run="--dry-run" in sys.argv)
```

Antes de ejecutarlo, comprobar cuál es el ID más alto real (el fetcher no publica, pero
conviene confirmarlo):

```bash
ssh root@192.168.1.172 "grep -o 'Telegram msg [0-9]*' /var/log/poligrafo-digest.log | tail -1"
```

Ejecutar con ese número más un margen de 25:

```bash
ssh root@192.168.1.172 "cd /root/projects/poligrafo-es && python3 scripts/limpiar_canal.py 260"
```

- [ ] **Step 8: Republicar julio**

```bash
ssh root@192.168.1.172 "cd /root/projects/poligrafo-es && python3 digest.py"
```

Con el throttle de 4 s y ~20 fichas más 1-2 bloques de BOE, tarda unos 2 minutos.

- [ ] **Step 9: Rearmar el cron del digest**

```bash
ssh root@192.168.1.172 "crontab -l | sed 's|^#PAUSED-v3 ||' | crontab -"
ssh root@192.168.1.172 "crontab -l | grep -i polig"
```

Esperado: la línea del digest vuelve a estar activa, sin el prefijo.

- [ ] **Step 10: Verificar que el ciclo cierra bien**

```bash
ssh root@192.168.1.172 "tail -30 /var/log/poligrafo-digest.log"
```

Esperado: cero líneas `WARN: falló el envío`, y una consulta a la base confirmando que la cola
quedó vacía:

```bash
ssh root@192.168.1.172 "cd /root/projects/poligrafo-es && python3 -c \"
from src.db import get_conn
c=get_conn()
print('sustantivas pendientes:', c.execute(\\\"SELECT COUNT(*) FROM votes WHERE published=0 AND clase='sustantiva'\\\").fetchone()[0])\""
```

Esperado: `0`

- [ ] **Step 11: Actualizar la documentación del vault**

Invocar la skill `/deploy`, que actualiza `03_PROMPTS/claude_desktop/Server Orange Pi.md`.
Además, actualizar `C:\Obsidian\Jarvis\01_PROYECTOS\poligrafo-es.md`: la sección Arquitectura
debe reflejar la agrupación por expediente, el matcher por embeddings y el nuevo
`embed_programs.py`.

- [ ] **Step 12: Commit final**

```bash
git add scripts/
git commit -m "chore: scripts de backfill v3 y limpieza del canal"
```

---

## Notas de riesgo

**El modelo de embeddings en la Pi.** 470 MB de descarga y ~1 GB de RAM al cargar. Hay 3.3 GB
libres, así que entra, pero el fetcher pasa a tardar más en arrancar por la carga perezosa del
modelo. Si diera problemas, la alternativa es vectorizar en el PC y copiar la base con los
BLOBs ya calculados: los embeddings de los programas no cambian nunca.

**El umbral de similitud (0.80) es una conjetura razonable, no un valor medido.** La Step 9 de
la Task 6 es donde se calibra con datos reales. Un umbral mal puesto no rompe nada: o no
aparecen veredictos de programa, o aparecen de más y el juez LLM los descarta.

**El borrado del canal es el único paso irreversible del plan.** Está detrás de un gate humano
explícito y es lo último que ocurre antes de republicar.
