# Test a ciegas: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** página `/test` en la web 29N donde el usuario vota sí/no propuestas de 2026 resumidas de forma neutral, con sus condiciones jurídicas visibles, y al final ve de qué partido era cada una.

**Architecture:** un módulo nuevo del motor (`src/electoral/test_ciegas.py`) selecciona, resume y prueba la neutralidad con LLM barato sobre una copia de `electoral.db` en el PC; las condiciones salen de una tabla escrita a mano (`config/condiciones.json`); Fran revisa en un Markdown y lo aprobado queda en `config/test_ciegas.json`, versionado. `exportar` lo añade a `datos.json` como clave `test` (contrato 1.2.0) y la web lo pinta con un `<script>` de Astro sin framework.

**Tech Stack:** Python 3.12, SQLite, OpenRouter (`deepseek/deepseek-v4-flash`, `google/gemini-2.5-flash-lite`), `multilingual-e5-small`, pytest por CLI; Astro 7 + Playwright.

**Spec:** `docs/superpowers/specs/2026-10-30-test-a-ciegas-design.md` (léela entera antes de empezar).

## Global Constraints

- Ningún modelo de Anthropic; todo por `src/electoral/llm.LLM`, cada subcomando con `--tope` y una fila en la tabla `gasto` aunque falle (patrón `cmd_juzgar`).
- Topes por defecto: `test-seleccionar` 0,10; `test-resumir` 0,30; `test-neutralidad` 0,30 (USD).
- Pruebas solo de comportamiento: motor por CLI con el fixture `cli` y `ELECTORAL_LLM_FALSO`; web con Playwright a 390 px. Nada de pruebas unitarias de funciones internas.
- La web: nada de `localStorage`, `sessionStorage`, cookies, analítica ni peticiones de red tras cargar. Ningún total, porcentaje ni agrupación por partido en ninguna pantalla.
- El partido y la cita nunca se ven antes de votar esa tarjeta.
- Textos de la web en castellano de Canarias (`ustedes`, nunca `vosotros`) y **sin rayas** (`—`, `–`).
- Condiciones: el LLM solo devuelve claves de materia; mayoría, artículo, explicación y enlace salen siempre de `config/condiciones.json`. Una competencia compartida nunca es `inviable`.
- Solo se publica lo que Fran marca en la revisión. Sin marca, no sale.
- La web publica solo el año 2026; 2023 es para pruebas (`--test-anio`).
- Antes de tocar `poligrafo-web`: `git pull` (la Pi añade un commit de datos cada noche).

## Review Focus

1. Tema elegido sin propuestas (un partido o todos sin propuestas en ese tema): la entrada lo enseña con 0 y deshabilitado, no rompe el flujo.
2. «Empezar» sin ningún tema marcado: el botón está deshabilitado.
3. «Ver de quién eran» antes de votar ninguna: el destape dice «Aún no has votado ninguna propuesta» y ofrece volver.
4. Texto del LLM o del programa con `<`, `&` o comillas: se pinta como texto, nunca como HTML (`textContent`).
5. Partido de 2026 que no está en `config/partidos_electoral.json` (partido nuevo): `exportar` falla con un mensaje que lo nombra, en vez de publicar un id crudo.

---

### Task 1: Selección de propuestas

**Files:**
- Create: `src/electoral/test_ciegas.py`
- Modify: `src/electoral/db.py` (tabla nueva en `ESQUEMA`), `electoral.py` (subcomando), `tests/fixtures/electoral/llm_falso.py`
- Test: `tests/electoral/test_test_ciegas.py`

**Interfaces:**
- Produces:
  - Tabla `test_propuestas (promesa_id INTEGER PRIMARY KEY, anio INTEGER, partido TEXT, tema TEXT, resumen TEXT, concreta INTEGER, materias TEXT, coste INTEGER, reescrituras INTEGER DEFAULT 0, adivinado TEXT, delata INTEGER DEFAULT 0)` y `test_hechos (anio INTEGER, partido TEXT, tema TEXT, PRIMARY KEY (anio, partido, tema))` (qué pares ya se seleccionaron, para reanudar).
  - Constantes en `test_ciegas.py`: `MODELO = "deepseek/deepseek-v4-flash"`, `ADIVINO = "google/gemini-2.5-flash-lite"`, `MAX_POR_PARTIDO_TEMA = 3`, `MAX_REESCRITURAS = 2`, `TEMAS_LANZAMIENTO = ["Economía e industria", "Vivienda", "Sanidad", "Fiscalidad", "Empleo y trabajo", "Pensiones"]`.
  - `seleccionar(conn, llm, anio: int, temas: list[str]) -> int` (propuestas nuevas).
  - CLI: `electoral.py test-seleccionar --anio N [--temas "A,B"] [--tope 0.1]`. Sin `--temas`, `TEMAS_LANZAMIENTO`.
  - Falso: si el mensaje contiene `SELECCIONAR:`, devuelve `{"ids": [...]}` con los primeros 3 ids que encuentre en líneas `[id=N]`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
def test_la_seleccion_respeta_temas_y_tope_por_partido(cli):
    _cargar_programa(cli, "2023")                      # ingest + extraer con el falso
    cli("test-seleccionar", "--anio", "2023", "--temas", "Vivienda", env=_env())
    filas = _filas(cli.db, "SELECT partido, tema, COUNT(*) n FROM test_propuestas GROUP BY partido, tema")
    assert filas and all(f["tema"] == "Vivienda" and f["n"] <= 3 for f in filas)

def test_la_seleccion_no_coge_promesas_de_procedimiento(cli): ...
    # ninguna promesa_id seleccionada tiene procedimental = 1

def test_sin_presupuesto_se_para_y_se_reanuda_sin_duplicar(cli):
    # --tope 0 → 0 filas y una fila en gasto con paso 'test-seleccionar'; después sin tope → filas sin repetir
```

`_cargar_programa`, `_env` y `_filas` son ayudantes del propio fichero de pruebas (mismo patrón que `test_programas.py`). Si el PDF de prueba no da promesas de Vivienda suficientes, amplía el falso de extracción, no el PDF.

- [ ] **Step 2: Ejecutar y ver que fallan**

Run: `pytest tests/electoral/test_test_ciegas.py -v`
Expected: FAIL (`invalid choice: 'test-seleccionar'`).

- [ ] **Step 3: Implementar**

Script: promesas del año y temas, `procedimental = 0`, sin texto repetido dentro del partido. Una llamada por (partido, tema) no hecha aún, con las promesas en líneas `[id=N] texto` precedidas de `SELECCIONAR:`; el prompt pide las `MAX_POR_PARTIDO_TEMA` más concretas y de más alcance (todas si hay menos). Ids devueltos que no estaban en la lista se ignoran. `PresupuestoAgotado` corta y deja el resto pendiente. El comando registra `gasto` en un `finally`.

- [ ] **Step 4: Ejecutar y ver que pasan**

Run: `pytest tests/electoral -v`
Expected: PASS, y las pruebas previas siguen en verde.

- [ ] **Step 5: Commit**

```bash
git add src/electoral/test_ciegas.py src/electoral/db.py electoral.py tests/
git commit -m "feat(test): select blind test proposals per party and topic"
```

### Task 2: Resumen neutral y materias

**Files:**
- Modify: `src/electoral/test_ciegas.py`, `electoral.py`, `tests/fixtures/electoral/llm_falso.py`
- Create: `config/condiciones.json` (solo las claves aquí; el contenido completo es la Task 4)
- Test: `tests/electoral/test_test_ciegas.py`

**Interfaces:**
- Consumes: tabla `test_propuestas` (Task 1).
- Produces:
  - `resumir(conn, llm, anio: int, raiz: Path) -> int`: rellena `resumen`, `concreta`, `materias` (JSON, lista de claves) y `coste` de las filas con `resumen IS NULL`.
  - `materias_validas(raiz: Path) -> set[str]`: claves de `config/condiciones.json`.
  - CLI: `test-resumir --anio N [--tope 0.3]`.
  - Falso: con `RESUMIR:` devuelve `{"resumen": "Resumen neutral: <texto de la promesa>", "concreta": true, "materias": <LLM_FALSO_MATERIAS, por defecto ["ley_ordinaria"]>, "coste": false}`.

- [ ] **Step 1: Pruebas que fallan**

```python
def test_cada_propuesta_seleccionada_queda_resumida(cli): ...
    # tras test-resumir, ninguna fila de test_propuestas tiene resumen NULL

def test_una_materia_que_no_esta_en_la_tabla_se_descarta(cli):
    env = _env(LLM_FALSO_MATERIAS='["ley_ordinaria", "inventada"]')
    ...
    assert all(json.loads(f["materias"]) == ["ley_ordinaria"] for f in filas)

def test_resumir_dos_veces_no_vuelve_a_pagar(cli): ...
    # segunda ejecución: 0 $ en su fila de gasto
```

- [ ] **Step 2: Ejecutar y ver que fallan** (`pytest tests/electoral/test_test_ciegas.py -v`, FAIL por subcomando inexistente).

- [ ] **Step 3: Implementar**

Una llamada a `MODELO` por propuesta con `RESUMIR:`, la promesa, su cita y el texto del bloque (`bloques.texto` por `bloque_id`). El prompt lleva las reglas del §5.2 de la spec tal cual (sin partido ni líderes, sin primera persona, sin balance de gestión, sin léxico identitario salvo que sea el objeto, en castellano, ninguna cifra que no esté en el texto) y la lista de claves de `materias_validas` con una línea de descripción de cada una. 2-4 frases. Paralelo con `ThreadPoolExecutor(8)` como `programas.extraer`.

- [ ] **Step 4: Ejecutar y ver que pasan** (`pytest tests/electoral -v`, PASS).

- [ ] **Step 5: Commit** — `feat(test): neutral summaries and legal subject tags`

### Task 3: Prueba de neutralidad

**Files:**
- Modify: `src/electoral/test_ciegas.py`, `electoral.py`, `tests/fixtures/electoral/llm_falso.py`
- Test: `tests/electoral/test_test_ciegas.py`

**Interfaces:**
- Consumes: `resumir` (Task 2); reescribir es volver a llamar al resumen con una pista.
- Produces:
  - `neutralidad(conn, llm, anio: int, raiz: Path) -> dict` con `{"total": int, "acertadas_al_final": int, "delata": int}`; rellena `adivinado`, `reescrituras`, `delata`.
  - CLI: `test-neutralidad --anio N [--tope 0.3]`; imprime `acierto final: X de N (P %)`.
  - Falso: con `ADIVINAR:` devuelve `{"partido": ...}`; con `LLM_FALSO_ADIVINA=acierta` devuelve `PSOE` (el único partido del programa de prueba) y con `falla`, `PP`.

- [ ] **Step 1: Pruebas que fallan**

```python
def test_si_el_adivino_acierta_se_reescribe_dos_veces_y_se_marca(cli):
    ...  # LLM_FALSO_ADIVINA=acierta
    assert all(f["reescrituras"] == 2 and f["delata"] == 1 for f in filas)

def test_si_el_adivino_falla_no_se_toca(cli):
    ...  # LLM_FALSO_ADIVINA=falla
    assert all(f["reescrituras"] == 0 and f["delata"] == 0 for f in filas)

def test_el_adivino_no_recibe_el_partido(cli): ...
    # el falso falla la llamada (no JSON) si el mensaje ADIVINAR contiene el nombre del partido real
```

- [ ] **Step 2: Ejecutar y ver que fallan.**
- [ ] **Step 3: Implementar.** `ADIVINO` recibe solo el resumen y la lista de partidos del año (ids de `config/partidos_electoral.json` con promesas ese año). Si acierta, `resumir` de esa fila con la pista «el adivinador lo atribuyó a su partido; quita lo que lo delate sin cambiar el fondo», hasta `MAX_REESCRITURAS`; si sigue acertando, `delata = 1`.
- [ ] **Step 4: Ejecutar y ver que pasan.**
- [ ] **Step 5: Commit** — `feat(test): measure and fix party leaks in summaries`

### Task 4: Tabla de condiciones

**Files:**
- Create: `src/electoral/condiciones.py`
- Modify: `config/condiciones.json`
- Test: las pruebas de comportamiento de las condiciones van en la Task 6, donde se ven en `datos.json`

**Interfaces:**
- Produces:
  - `config/condiciones.json`: `{"materias": {"<clave>": {"nivel": int, "etiqueta": str, "explicacion": str, "norma": str, "url": str, "inviable": bool, "descripcion_para_el_modelo": str}}, "coste": {"etiqueta": "Coste para las cuentas públicas", "explicacion": str, "url": str}}`.
  - `cargar(raiz: Path) -> dict` y `resolver(materias: list[str], coste: bool, tabla: dict) -> dict` → `{"condiciones": [{"clave", "etiqueta", "explicacion", "norma", "url", "inviable"}...] ordenadas por nivel, "inviable": bool}`. Una clave desconocida no produce condición.

- [ ] **Step 1: Escribir `config/condiciones.json`** con estas claves y niveles (spec §5.3). URLs: Constitución `https://www.boe.es/buscar/act.php?id=BOE-A-1978-31229#aNN` (ancla del artículo: `a97`, `a81`, `a134`, `a148`, `a149`, `a167`, `a168`); TFUE `https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:12016E/TXT`; Directiva del IVA `https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:32006L0112`.

| clave | nivel | inviable | norma |
|---|---|---|---|
| `gobierno` | 1 | no | art. 97 CE |
| `ley_ordinaria` | 2 | no | art. 66 y 90 CE |
| `ley_organica` | 3 | no | art. 81 CE (176 votos) |
| `compartida_vivienda` | 3 | no | art. 148.1.3 y 149.1.13 CE |
| `compartida_sanidad` | 3 | no | art. 149.1.16 CE |
| `compartida_educacion` | 3 | no | art. 149.1.30 CE |
| `reforma_constitucional` | 4 | no | art. 167 CE (3/5) |
| `reforma_constitucional_agravada` | 5 | sí | art. 168 CE |
| `ue_fiscalidad_armonizada` | 6 | sí | Directiva 2006/112/CE; art. 113 TFUE |
| `ue_comercio_aranceles` | 6 | sí | art. 3 y 207 TFUE |
| `ue_ayudas_estado` | 6 | sí | art. 107 y 108 TFUE |
| `ue_pac` | 6 | sí | art. 38-43 TFUE |
| `exclusiva_autonomica` | 7 | sí | art. 148 CE y Estatuto |

Las explicaciones, en lenguaje llano y sin valorar; las de `compartida_*` dicen qué puede hacer el Estado (bases, financiación, coordinación) y qué las comunidades. `coste`: gasto recurrente necesita crédito en los Presupuestos y el Gobierno puede oponerse a tramitar una proposición que suba el gasto o baje los ingresos del año (art. 134.6 CE); no afirma que vaya en la Ley de Presupuestos.

- [ ] **Step 2: PARADA. Fran revisa `config/condiciones.json`** y lo aprueba o corrige. No se usa en producción sin su OK.
- [ ] **Step 3: Implementar `condiciones.py`.** `materias_validas` (Task 2) pasa a leer de `cargar`.
- [ ] **Step 4: Commit** — `feat(test): hand-written legal conditions table`

### Task 5: Revisión de Fran y aprobación

**Files:**
- Modify: `src/electoral/test_ciegas.py`, `electoral.py`
- Create: `config/test_ciegas.json` (se crea al aprobar)
- Test: `tests/electoral/test_test_ciegas.py`

**Interfaces:**
- Consumes: `condiciones.resolver` (Task 4); `juez.asegurar_embeddings`, `src.embeddings.from_blob`; cruces firmes de `exportar._cruces` (nivel `veredicto`).
- Produces:
  - `generar_revision(conn, raiz: Path, anio: int, salida: Path) -> int`. CLI `test-revision --anio N [--salida docs/revision_test_<N>.md]`.
  - `aprobar(raiz: Path, anio: int, revision: Path, destino: Path) -> int`. CLI `test-aprobar --anio N --revision <md> [--destino config/test_ciegas.json]`.
  - `config/test_ciegas.json`: `{"<anio>": [{"promesa_id": int, "resumen": str, "concreta": bool, "materias": [str], "coste": bool, "promesa_2023_id": int|null, "revisado_por": "Fran", "fecha": "YYYY-MM-DD"}]}`. Aprobar reemplaza solo la lista de ese año.
  - Formato de cada tarjeta del Markdown (el parser depende de esto):

```markdown
## 12 · id=5433 · Vivienda · PSOE
**Resumen:** ...
**Concreta:** sí · **Condiciones:** Ley ordinaria; Coste para las cuentas públicas
**Cita (p. 34):** «...» (url#page=34)
⚠️ El adivinador sigue acertando el partido.            ← solo si delata
**Posible cruce 2023:** «texto 2023» (id=176), votó de acuerdo con su promesa en «expediente»   ← si hay candidato
- [ ] Publicar
- [ ] Descartar
- [ ] El cruce 2023 es la misma promesa
Resumen corregido:
```

- [ ] **Step 1: Pruebas que fallan**

```python
def test_sin_marca_no_se_publica(cli, tmp_path): ...       # revisión sin tocar → lista vacía para el año
def test_publicar_y_descartar(cli, tmp_path): ...           # marca una [x] Publicar y otra [x] Descartar → solo la primera
def test_el_resumen_corregido_sustituye_al_del_modelo(cli, tmp_path): ...
def test_el_cruce_2023_solo_se_guarda_si_fran_lo_confirma(cli, zips, tmp_path):
    # programa de prueba ingerido como 2023 y como 2026, juzgar con el falso → hay candidato;
    # sin marcar la casilla del cruce → promesa_2023_id es null; marcada → el id
def test_publicar_y_descartar_a_la_vez_es_un_error(cli, tmp_path): ...  # returncode != 0, nombra la tarjeta
```

- [ ] **Step 2: Ejecutar y ver que fallan.**
- [ ] **Step 3: Implementar.** Candidato de cruce: coseno entre la promesa del año y las promesas de 2023 del **mismo partido** con algún cruce firme; el mejor por encima de 0,85 (umbral medido del matcher, `MIN_SIMILARITY`), o ninguno. Orden de tarjetas: por tema y partido. El parser lee por `id=N` y las casillas `[x]`/`[X]`; «Resumen corregido:» con texto no vacío sustituye al resumen.
- [ ] **Step 4: Ejecutar y ver que pasan.**
- [ ] **Step 5: Commit** — `feat(test): review file and approval into versioned config`

### Task 6: Contrato 1.2 y exportación

**Files:**
- Modify: `src/electoral/exportar.py`, `schema/datos.schema.json`, `electoral.py` (`--test-anio` en `exportar` y `noche`, por defecto 2026)
- Test: `tests/electoral/test_test_ciegas.py`, `tests/electoral/test_contrato.py`

**Interfaces:**
- Consumes: `config/test_ciegas.json` (Task 5), `condiciones.resolver` (Task 4), los cruces que `construir` ya calcula.
- Produces: `VERSION_CONTRATO = "1.2.0"`; clave `test` (lista, `[]` si no hay fichero o año) con objetos:
  `{"id": int, "tema": str, "resumen": str, "concreta": bool, "condiciones": [...], "inviable": bool, "partido": str, "partido_nombre": str, "cita": str, "pagina": int, "url_programa_pagina": str, "cruce_2023": null | {"veredicto": "cumple"|"incumple", "votacion_id": str, "expediente": str, "fecha": str, "url_sesion": str|null}}`.
  El esquema añade `test` como propiedad **no obligatoria**.

- [ ] **Step 1: Pruebas que fallan**

```python
def test_lo_aprobado_sale_en_datos_json_con_sus_condiciones(cli, tmp_path): ...
def test_sin_fichero_de_test_la_clave_es_una_lista_vacia(cli): ...
def test_el_cruce_2023_usa_el_veredicto_firme_mas_reciente(cli, zips, tmp_path): ...
def test_un_incumple_sin_confirmar_no_sale_como_cruce_2023(cli, zips, tmp_path): ...
def test_las_condiciones_salen_de_la_tabla(cli, tmp_path): ...
    # etiqueta, explicación y url de cada condición son las de config/condiciones.json; una materia desconocida no sale
def test_una_competencia_compartida_nunca_es_inviable(cli, tmp_path): ...
    # LLM_FALSO_MATERIAS='["compartida_vivienda"]' → inviable False; '["ue_fiscalidad_armonizada"]' → True
def test_un_partido_desconocido_hace_fallar_la_exportacion(cli, tmp_path):
    # aprobada una propuesta de un partido que no está en partidos_electoral.json → returncode != 0 y lo nombra
```

- [ ] **Step 2: Ejecutar y ver que fallan.**
- [ ] **Step 3: Implementar.** `cruce_2023`: entre los cruces de `promesa_2023_id` con `nivel == "veredicto"`, el de la votación más reciente. Si una propuesta aprobada ya no existe en la base, se omite con un aviso por stderr (no se publica a medias).
- [ ] **Step 4: Ejecutar** `pytest tests -v`. Expected: PASS, incluido `test_contrato.py` con la nueva versión.
- [ ] **Step 5: Commit** — `feat(contract): add blind test block, contract 1.2.0`

### Task 7: Prueba real con la muestra de 2023 (operativa, sin código nuevo)

- [ ] **Step 1:** copiar la base de la Pi al PC: `scp root@192.168.1.172:/root/projects/poligrafo-es/electoral.db electoral_data/pi.db` (o `mcp__orange-pi__ssh_download`).
- [ ] **Step 2:** `python electoral.py test-seleccionar --anio 2023 --temas "Vivienda,Fiscalidad" --db electoral_data/pi.db`, luego `test-resumir` y `test-neutralidad`. Anotar el gasto total (objetivo < 0,10 $).
- [ ] **Step 3:** barrera: `acierto final` ≤ 25 %. Si no, ajustar el prompt del resumen (Task 2) y repetir solo `test-resumir`/`test-neutralidad` sobre filas reseteadas. No pasar de aquí sin cumplirla.
- [ ] **Step 4:** `test-revision --anio 2023`, recortado a ~20 tarjetas variadas para Fran. **PARADA: Fran las juzga.** Sus correcciones vuelven a los prompts o a `condiciones.json`.
- [ ] **Step 5:** `test-aprobar --anio 2023` con lo que Fran marque y `exportar --test-anio 2023 --salida electoral_data/datos_test_2023.json`. Este fichero alimenta el fixture de la web.
- [ ] **Step 6:** commit de los ajustes de prompts/tabla — `fix(test): tune prompts after 2023 sample`. La base copiada no se versiona.

### Task 8: Página `/test` en la web

**Files (repo `poligrafo-web`):**
- Modify: `src/lib/datos.ts` (tipo `PropuestaTest`, `Datos.test?: PropuestaTest[]`), `scripts/crear_fixture.py` (conserva `test` y añade una entrada sintética de Vivienda con `<i>`, `&` y «comillas» en el resumen), `tests/fixtures/datos.json` (regenerado desde `datos_test_2023.json`), `src/pages/index.astro` (enlace «Test a ciegas»), `src/layouts/Base.astro` (enlace en el pie)
- Create: `src/pages/test.astro`, `tests/test-ciegas.spec.ts`

**Interfaces:**
- Consumes: clave `test` del contrato 1.2 (Task 6).
- Produces (el DOM en el que se apoyan las pruebas): `input.tema-opcion` con etiqueta `"<Tema> (<n>)"`, botón «Empezar»; `.tarjeta` con `.tema`, `.resumen`, `.sin-concrecion` (si `concreta` es false), `details.condicion` por condición, `.inviable` si `inviable`, botones «Sí» y «No», `.progreso` con `"<i> de <n>"`; botón «Ver de quién eran» siempre visible durante las tarjetas; `.destape` con un `.resultado` por tarjeta votada (`.tu-voto`, `.partido`, `.cita`, enlace al programa, `.cruce-2023` si lo hay); botón «Volver a empezar».

- [ ] **Step 1:** `git pull` en `poligrafo-web`.
- [ ] **Step 2: Pruebas que fallan** en `tests/test-ciegas.spec.ts`, derivando lo esperado del fixture como hace `portada.spec.ts`:

```ts
test('elegir un tema solo enseña tarjetas de ese tema y el número coincide')
test('ninguna tarjeta enseña partido ni cita antes de votarla')
test('las condiciones se despliegan antes de votar y enlazan a la norma')
test('votar todas lleva al destape con voto, partido, cita y página de cada una')
test('ver de quién eran a mitad destapa solo las votadas')
test('ver de quién eran sin votar ninguna lo dice y deja volver')
test('el destape no tiene totales, porcentajes ni agrupación por partido')   // /\d+\s*%/, /\d+\s+(de las|propuestas de)/
test('el cruce 2023 sale solo donde existe')
test('sin temas marcados no se puede empezar; un tema sin propuestas está deshabilitado')
test('un resumen con < & y comillas se ve como texto')
test('no guarda nada ni hace peticiones tras cargar')   // localStorage.length, sessionStorage.length, document.cookie, page.on('request')
test('volver a empezar y recargar dejan la página como nueva')
test('el texto no lleva rayas ni vosotros')
```

- [ ] **Step 3: Ejecutar** `npx playwright test tests/test-ciegas.spec.ts --project web`. Expected: FAIL (404 en `/test`).
- [ ] **Step 4: Implementar `test.astro`.** Los datos van en `<script type="application/json" id="datos-test">` con `JSON.stringify(datos.test ?? [])` (escapando `</`); un `<script>` de Astro sin dependencias mezcla al azar las tarjetas de los temas elegidos (Fisher-Yates) y pinta todo con `textContent`. Textos de entrada (spec §4): qué es, que nada se guarda, que no da resultado por partido, y «Incluye los programas de: …» con los partidos presentes en `datos.test` (lo calcula la página; sin cambio de contrato). Estilo con las clases de `public/estilo.css`.
- [ ] **Step 5: Ejecutar** `npm test`. Expected: PASS las 19 previas y las nuevas.
- [ ] **Step 6: Commit** — `feat(test): blind proposal test page`. No hacer push sin el OK de Fran.

### Task 9: Ensayo completo y guion del 13-14

- [ ] **Step 1:** ensayo de punta a punta con 2023: `exportar --test-anio 2023` → copiar a `data/datos.json` local de la web → `npm run build && npm run preview` → Fran lo prueba en el móvil. **PARADA: OK de Fran.**
- [ ] **Step 2:** escribir en `README.md` del motor el guion del día:
  1. En la Pi, por cada partido: `python3 electoral.py ingest-programa 2026 <partido> <url>`; después `python3 electoral.py extraer --tope 1`.
  2. Comprobar que no quedan bloques pendientes: `sqlite3 electoral.db "SELECT COUNT(*) FROM bloques WHERE extraido = 0"` → `0` (si no, la noche deja de juzgar).
  3. Copiar la base al PC; `test-seleccionar --anio 2026`, `test-resumir`, `test-neutralidad`, `test-revision`.
  4. Fran revisa; `test-aprobar --anio 2026`; commit de `config/test_ciegas.json` y push (con OK); `git pull` en la Pi. La noche publica la clave `test`.
  5. Programas que lleguen después: repetir 1-4 solo para ese partido (lo ya seleccionado no se repite gracias a `test_hechos`).
- [ ] **Step 3:** push del motor y de la web con el OK de Fran, `git pull` en la Pi, y comprobar a la mañana siguiente que `/test` sale en `poligrafo-29n.pages.dev` con `test: []` hasta el 13 (la página dice que las propuestas llegan con los programas).
- [ ] **Step 4:** actualizar la nota `01_PROYECTOS/poligrafo-es.md` (sección nueva o pendiente; la reescritura de estado, con OK de Fran).
