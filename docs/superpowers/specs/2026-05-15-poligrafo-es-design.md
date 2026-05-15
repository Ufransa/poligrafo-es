# PolígrafoES — Design Spec

**Fecha:** 2026-05-15  
**Estado:** Aprobado por Fran

---

## 1. Propósito y filosofía

Canal de Telegram push-only que mide la coherencia de los partidos políticos españoles entre sus promesas electorales, sus votos en el Congreso y la legislación publicada en el BOE.

**Principio rector:** datos puros, sin interpretación editorial. El sistema presenta hechos verificables; el lector juzga.

**Unidad de análisis:** partido (grupo parlamentario), no individuo. No se rastrea a diputados concretos.

**Ámbito:** España nacional, Legislatura XV. Madrid como fase 2.

---

## 2. Fuentes de datos

### 2.1 Congreso — Votos por grupo parlamentario

**Endpoint:** HTML scraping de `https://www.congreso.es/es/opendata/votaciones`

**Estrategia de polling:**
1. Scraping diario de la página HTML (sin JS rendering necesario — confirmado con plain requests)
2. Extracción del número de sesión más alto visible en los links (`SesionNNN`)
3. Si `SesionNNN > last_processed_session` en DB → descargar ZIP de sesión:  
   `https://www.congreso.es/webpublica/opendata/votaciones/Leg15/SesionNNN/YYYYMMDD/VOT_TIMESTAMP.zip`
4. Parsear cada `VOT_*.xml` del ZIP

**Estructura del XML de votación:**
```xml
<Resultado>
  <Informacion>
    <Sesion>34</Sesion>
    <NumeroVotacion>1</NumeroVotacion>
    <Fecha>9/4/2024</Fecha>
    <Titulo>Toma en consideración...</Titulo>
    <TextoExpediente>Descripción de la proposición...</TextoExpediente>
  </Informacion>
  <Totales>
    <AFavor>310</AFavor><EnContra>33</EnContra><Abstenciones>0</Abstenciones>
  </Totales>
  <Votaciones>
    <Votacion>
      <Grupo>GP</Grupo>      <!-- PP -->
      <Voto>Sí</Voto>
    </Votacion>
    ...
  </Votaciones>
</Resultado>
```

**Códigos de grupo parlamentario:**

| Código | Partido |
|--------|---------|
| `GP` | PP |
| `GS` | PSOE |
| `GSUMAR` | Sumar |
| `GVOX` | Vox |
| `GR` | ERC |
| `GJxCAT` | Junts |
| `GEH Bildu` | EH Bildu |
| `GV (EAJ-PNV)` | PNV |
| `GMx` | Mixto |

**Agregación:** por `<Grupo>`, no por diputado individual. El XML contiene una entrada `<Votacion>` por diputado. Para obtener la posición del grupo: contar `Sí` / `No` / `Abstención` / `No vota` dentro del mismo `<Grupo>`. El voto con más entradas es la posición del grupo. Si todos votan igual → "unánime". Si hay división (> 10% de miembros discrepan) → publicar el mayoritario con nota `(división interna)`.

### 2.2 BOE — Legislación publicada

**Endpoint sumario:** `GET https://www.boe.es/datosabiertos/api/boe/sumario/YYYYMMDD`  
Accept: `application/json`

**Filtro de ingesta:** solo sección I (`"codigo": "1"` — Disposiciones generales) y sección II (Disposiciones no normativas relevantes). Las secciones de anuncios y licitaciones se descartan.

**Endpoint por entrada:** URL embebida en el sumario como `url_xml`:  
`https://www.boe.es/diario_boe/xml.php?id=BOE-A-XXXXXXXXXX`  
Devuelve XML con metadatos + texto completo. Si el XML es solo metadatos (a confirmar en implementación), fallback a `url_pdf` + pdfplumber.

**Campos de interés:** `<identificador>`, `<titulo>`, `<rango>` (Ley/Decreto/etc.), `<departamento>`, `<texto>`.

### 2.3 Programas electorales — Setup one-time

Procesado una vez (`bootstrap_programs.py`), resultado almacenado en SQLite.

| Partido | URL | Estado |
|---------|-----|--------|
| PP | `https://www.pp.es/storage/2023/07/programa_electoral_pp_23j_feijoo_2023.pdf` | ✅ Confirmado (8MB) |
| PSOE | `https://www.psoe.es/media-content/2023/07/PROGRAMA_ELECTORAL-GENERALES-2023.pdf` | ⚠️ Cloudflare — usar `scrapling.fetchers.StealthyFetcher` |
| Sumar | `https://www.newtral.es/wp-content/uploads/2023/07/Programa_electoral_sumar_23j_2023.pdf` | ✅ Confirmado (2.4MB, extracción desde p.10) |
| Vox | `https://files.mediaset.es/file/2023/0707/15/programa-vox-completo-pdf.pdf` | ✅ Confirmado (29MB, 178pp) |

**Procesado:** pdfplumber → segmentación por sección/capítulo → chunks de ~500 palabras → almacenados con metadata `(party, category, page_start, text)`.

---

## 3. Categorías temáticas

12 categorías fijas. El sistema las usa para tagging de votos, entradas BOE y chunks de programa.

```
vivienda · fiscalidad · empleo · sanidad · educación · pensiones
seguridad · medio_ambiente · digitalización · libertades_civiles · inmigración · infraestructuras
```

Implementación: `config/categories.json` — lista de keywords por categoría en español. El matching es por presencia de keywords en el texto (`Titulo` + `TextoExpediente` para votos; `titulo` + primeras 500 chars de `texto` para BOE). Sin NLP, sin stemming en MVP.

---

## 4. Detección de coherencia (keyword matching)

Al ingestar un voto nuevo:
1. Extraer keywords de `<Titulo>` + `<TextoExpediente>` (eliminando stopwords)
2. Buscar en `program_chunks` por partido + coincidencia de keywords
3. Si hay match con score > umbral (default: 2 keywords coincidentes) → marcar el voto con `program_match_id`
4. Al publicar: incluir el extracto del programa como contexto

**Lo que el sistema NO hace en MVP:** determinar automáticamente si hay contradicción. Publica la posición del partido en el programa + cómo votó. El lector concluye.

**Fase 2:** correlación voto ↔ BOE (cuando una ley que pasó el Congreso aparece en BOE, enlazar ambos registros).

---

## 5. Formato de publicación Telegram

**Canal:** push-only. Sin comandos, sin callbacks. Bot con rol de administrador del canal.

### Alerta de votación (inmediata si hay match con programa)

```
🗳️ Congreso · [CATEGORÍA]
[Título de la votación]

GP (PP)      ✅ Sí
GS (PSOE)    ✅ Sí
GVOX         ❌ No
GSUMAR       ✅ Sí
GR (ERC)     ⚠️ Abstención

📋 PP en su programa (2023): "..."
📋 Vox en su programa (2023): "..."

🔗 [Enlace al XML del Congreso]
```

### Digest semanal (lunes 10:30)

```
📊 Semana del [fecha]
[N] votaciones · [N] leyes BOE relevantes

🗳️ VOTACIONES
[título abreviado]  GP✅ GS✅ VOX❌ SUM✅
[título abreviado]  GP❌ GS✅ VOX❌ SUM⚠️
...

📜 BOE RELEVANTE
· [título ley] — [categoría] · [enlace]
...

PolígrafoES · datos sin editar
```

**Formato técnico:** HTML parse mode de Telegram. Sin imágenes en MVP. Longitud máxima por mensaje: 4096 chars (límite Telegram); si excede, dividir en dos mensajes.

---

## 6. Arquitectura de código

```
poligrafo-es/
├── config/
│   ├── parties.json          # código grupo → nombre display
│   └── categories.json       # categoría → lista de keywords
├── src/
│   ├── congreso.py           # HTML scraper + ZIP downloader + XML parser
│   ├── boe.py                # Sumario fetcher + entry XML parser
│   ├── programs.py           # PDF downloader + pdfplumber extractor + chunker
│   ├── matcher.py            # keyword matching voto ↔ program_chunks
│   ├── db.py                 # SQLite schema + queries
│   └── publisher.py          # Telegram Bot API sender
├── fetcher.py                # Cron entry: Congreso + BOE
├── digest.py                 # Cron entry: weekly digest
├── bootstrap_programs.py     # One-shot: download + parse + store programs
├── .env                      # TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
└── poligrafo.db              # SQLite (gitignored)
```

### 6.1 SQLite schema

```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    session_number INTEGER UNIQUE,
    session_date TEXT,
    processed_at TEXT
);

CREATE TABLE votes (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id),
    vote_number INTEGER,
    titulo TEXT,
    texto_expediente TEXT,
    fecha TEXT,
    categories TEXT,           -- JSON array de categorías detectadas
    published INTEGER DEFAULT 0
);

CREATE TABLE vote_groups (
    id INTEGER PRIMARY KEY,
    vote_id INTEGER REFERENCES votes(id),
    grupo_code TEXT,
    voto TEXT                  -- 'Sí' | 'No' | 'Abstención' | 'No vota'
);

CREATE TABLE boe_entries (
    id INTEGER PRIMARY KEY,
    identificador TEXT UNIQUE,
    titulo TEXT,
    rango TEXT,
    departamento TEXT,
    fecha TEXT,
    url_xml TEXT,
    categories TEXT,           -- JSON array
    texto_preview TEXT,        -- primeros 1000 chars
    published INTEGER DEFAULT 0
);

CREATE TABLE program_chunks (
    id INTEGER PRIMARY KEY,
    party TEXT,                -- 'PP' | 'PSOE' | 'SUMAR' | 'VOX'
    category TEXT,
    page_start INTEGER,
    text TEXT
);

CREATE TABLE vote_program_matches (
    vote_id INTEGER REFERENCES votes(id),
    chunk_id INTEGER REFERENCES program_chunks(id),
    party TEXT,
    score REAL
);

CREATE TABLE published_messages (
    id INTEGER PRIMARY KEY,
    type TEXT,                 -- 'vote_alert' | 'weekly_digest'
    ref_id INTEGER,
    telegram_message_id INTEGER,
    sent_at TEXT
);
```

---

## 7. Cron schedule (Orange Pi)

| Job | Hora | Conflictos |
|-----|------|-----------|
| `fetcher.py` | 21:00 diario | — (cryptoTrading a las 09:30) |
| `digest.py` | 10:30 lunes | — (github-radar a las 08:00) |

---

## 8. Dependencias Python

```
requests          # HTTP base
pdfplumber        # PDF text extraction
scrapling[fetchers] + scrapling install  # PSOE PDF (Cloudflare bypass)
python-telegram-bot  # Telegram Bot API
```

SQLite: stdlib (`sqlite3`). Sin ORM.

---

## 9. Deploy

Desarrollo local en `D:\1.Fran\DEV\poligrafo-es\`. Deploy en Orange Pi Zero 3 (`root@192.168.1.172`) vía repo Git.

`bootstrap_programs.py` se ejecuta una vez tras el primer deploy (descarga y parsea los 4 PDFs).

Evaluar si añadir a ARGUS: `fetcher.py` es cron diario con consecuencias reales → sí, añadir `check_cron_jobs()`.

---

## 10. Fuera de alcance (MVP)

- Detección automática de contradicción (sí/no — el sistema solo presenta los datos)
- Rastreo de declaraciones en medios
- Ámbito autonómico (Madrid)
- Histórico de legislaturas anteriores a XV
- Interfaz web o bot interactivo
- Notificaciones por partido específico (push global único)
