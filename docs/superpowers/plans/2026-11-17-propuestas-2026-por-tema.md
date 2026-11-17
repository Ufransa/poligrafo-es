# Propuestas de 2026 por tema: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que la web 29N muestre todas las propuestas de 2026, tema a tema y partido a partido, con resumen, cita literal y enlace a la página del programa oficial.

**Architecture:** el motor (`poligrafo-es`) añade al contrato `datos.json` los programas de 2026 por partido, los motivos de los que no tienen y la lista de temas, y gana un comando que saca una muestra de propuestas para revisarlas a mano. La web (`poligrafo-web`, Astro estático) genera `/temas/` y una página por tema a partir de ese contrato, y enseña los temas de 2026 en la ficha de partido.

**Tech Stack:** Python 3 + pytest (motor). Astro 7 + Playwright (web).

**Spec:** `docs/superpowers/specs/2026-11-17-propuestas-2026-por-tema-design.md` (y el diseño base `2026-10-07-web-electoral-29n-design.md`).

## Global Constraints

- Partidos en **orden alfabético por `nombre`** dentro de cada tema (`localeCompare(..., 'es')`).
- La web no elige promesas: salen **todas** las no procedimentales de 2026, dentro de cada partido en orden de programa (`pagina` y luego `id`).
- Las páginas de tema van **sin JavaScript**: cada partido en un `<details>` cerrado.
- Textos fijos copiados literalmente del spec:
  - Junts, EH Bildu y UPN: «Aún no ha publicado su programa de 2026.».
  - Sumar: «No hemos localizado un programa de Sumar para 2026.».
  - Podemos: «Solo publica un manifiesto breve, sin propuestas concretas.», con enlace a `https://pazcasaytrabajo.es/`.
  - Sin propuestas en un tema: «Sin propuestas sobre este tema».
  - Aviso: «Resumen automático de cada propuesta; la cita es literal y está comprobada contra el programa oficial. Partidos en orden alfabético.».
- Solo propuestas de `anio == 2026`: las de 2023 no aparecen en las páginas de tema.
- Español de Canarias en todo texto («ustedes», nunca «vosotros»). Sin rayas (— –) en los textos de la web.
- Pruebas: solo de comportamiento (pytest por la CLI; Playwright en la web). Nada de tests unitarios.
- Nada se publica hasta que Fran haya revisado la muestra (Task 6).

## Review Focus

1. **`datos.json` antiguo, sin `programa_2026` ni `meta.temas`** (la web se despliega antes de que la noche exporte el contrato nuevo): el build no falla. Los temas salen de las promesas de 2026 y los partidos sin campo se tratan como «sin programa». → test en Task 4.
2. **Nombres con tilde o espacio** (Compromís, EH Bildu, Frente Amplio): el orden alfabético usa la colación española y las anclas `#compromis`, `#eh-bildu` y `#frente-amplio` funcionan desde la ficha. → tests en Task 4 y Task 5.
3. **Partido con programa pero sin propuestas en un tema**: sale al final con «Sin propuestas sobre este tema». No desaparece ni deja un `<details>` vacío. → test en Task 4.
4. **Cita con `<`, `&` o comillas**: se ve como texto, nunca como HTML. → propuesta sintética en la fixture (Task 3), test en Task 4.
5. **Propuestas de 2023 mezcladas**: ninguna página de tema enseña promesas de 2023. → test en Task 4.

---

### Task 1: Motor. Programas de 2026 y temas en el contrato

**Files:**
- Modify: `config/partidos_electoral.json` (los 15 partidos)
- Modify: `src/electoral/exportar.py` (`VERSION_CONTRATO`, `construir`)
- Test: `tests/electoral/test_programas.py`

**Interfaces:**
- Produces: en `datos.json`, cada partido con `programa_2026: str | null`, y `sin_programa_2026: str` cuando es `null`. Además, `meta.temas: list[str]` (= `programas.TEMAS`, 17, en ese orden) y `meta.version_contrato == "1.4.0"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_cada_partido_tiene_programa_de_2026_o_el_motivo(cli):
    for p in cli("exportar")["partidos"]:
        assert bool(p.get("programa_2026")) != bool(p.get("sin_programa_2026")), p["id"]
    podemos = next(p for p in cli("exportar")["partidos"] if p["id"] == "Podemos")
    assert podemos["sin_programa_2026"] == "Solo publica un manifiesto breve, sin propuestas concretas."

def test_el_contrato_lleva_la_lista_de_temas(cli):
    meta = cli("exportar")["meta"]
    assert meta["version_contrato"] == "1.4.0"
    assert len(meta["temas"]) == 17 and meta["temas"][0] == "Vivienda"
```

- [ ] **Step 2: Run them and check they fail**

Run: `python -m pytest tests/electoral/test_programas.py -q -k "2026_o_el_motivo or lista_de_temas"`
Expected: 2 failed.

- [ ] **Step 3: Fill in the config and the export**

`programa_2026` toma las URL oficiales que ya están en `bloques.url_programa` (consulta en la Pi: `select distinct partido, url_programa from bloques where anio=2026`): PP, PSOE, Vox, ERC, PNV, BNG, CC, Compromís, SALF y Frente Amplio. El resto lleva `programa_2026: null` y su `sin_programa_2026` con el texto de las Global Constraints. Para Podemos, añadir además `url_sin_programa_2026: "https://pazcasaytrabajo.es/"`. En `construir`, `meta["temas"] = list(programas.TEMAS)`. `VERSION_CONTRATO = "1.4.0"`.

- [ ] **Step 4: Run the whole electoral suite**

Run: `python -m pytest tests/electoral -q`
Expected: todo en verde.

- [ ] **Step 5: Commit**

`git commit -m "feat(electoral): export 2026 programs, missing-program reasons and topic list"`

### Task 2: Motor. Muestra de propuestas para revisar

**Files:**
- Modify: `electoral.py` (subcomando `muestra-promesas`)
- Test: `tests/electoral/test_muestra.py`

**Interfaces:**
- Produces: `python electoral.py muestra-promesas [--anio 2026] [--n 30] [--semilla 29] [--salida docs/revision_promesas_2026.md]`. Genera un Markdown con una sección `## N. <Partido> · <tema>` por propuesta, y en cada una el resumen, la cita entre «», `pág. N` enlazada a `url_programa_pagina` y tres casillas: `- [ ] Bien`, `- [ ] Resumen no dice lo que dice la cita`, `- [ ] Tema mal puesto o no es una propuesta`.

- [ ] **Step 1: Write the failing test**

```python
def test_la_muestra_de_promesas_es_reproducible_y_lleva_cita_y_pagina(cli, tmp_path):
    cli("ingest-programa", "2026", "PSOE", str(FIX / "programa_prueba.pdf"), env=env)
    cli("extraer", env=env)
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    cli("muestra-promesas", "--anio", "2026", "--n", "2", "--salida", str(a))
    cli("muestra-promesas", "--anio", "2026", "--n", "2", "--salida", str(b))
    texto = a.read_text(encoding="utf-8")
    assert texto == b.read_text(encoding="utf-8")
    assert texto.count("## ") == 2 and "#page=" in texto and "- [ ] Bien" in texto
```

(`env` y `FIX` como en el resto de `test_muestra.py`.)

- [ ] **Step 2: Run it and check it fails**

Run: `python -m pytest tests/electoral/test_muestra.py -q -k promesas`
Expected: FAIL (`invalid choice: 'muestra-promesas'`).

- [ ] **Step 3: Implement `cmd_muestra_promesas(a, conn)` in `electoral.py`**

Usa `exportar.construir(conn, RAIZ)["promesas"]`, filtra por `anio`, ordena por `id`, baraja con `random.Random(a.semilla)` y toma `n`. Con menos de `n` disponibles, toma todas.

- [ ] **Step 4: Run it and check it passes**

Run: `python -m pytest tests/electoral/test_muestra.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -m "feat(electoral): add a reproducible sample of promises for manual review"`

### Task 3: Web. Contrato 1.4 y fixture con propuestas de 2026

**Files:**
- Modify: `src/lib/datos.ts` (tipos y helpers)
- Modify: `scripts/crear_fixture.py`
- Regenerate: `tests/fixtures/datos.json`

**Interfaces:**
- Consumes: el contrato de Task 1.
- Produces en `src/lib/datos.ts`:
  - `Partido.programa_2026?: string | null; sin_programa_2026?: string; url_sin_programa_2026?: string`
  - `Datos.meta.temas?: string[]`
  - `listaTemas(): string[]`: `meta.temas` o, si falta, los temas de las promesas de 2026 en orden de aparición.
  - `propuestas2026(tema: string, partido: string): Promesa[]`: ordenadas por `pagina` y luego `id`.
  - `partidosAlfabeticos(): Partido[]`: por `nombre` con `localeCompare(..., 'es')`.
  - `slugTema(tema: string): string` (= `slug`).

- [ ] **Step 1: Regenerate the fixture with 2026 data**

En la Pi, con Task 1 desplegado: `python3 electoral.py exportar --salida /tmp/datos-1.4.json`, y copiarlo al PC. `crear_fixture.py` conserva ahora además, por partido y tema, hasta 2 promesas de 2026 y añade una sintética de 2026 (partido `PSOE`, tema `Vivienda`, `id: -2`) con `texto` y `cita` que contienen `<i>`, `&` y «comillas». Deja un partido con programa de 2026 sin ninguna promesa en `Pensiones`, para el caso de Review Focus 3. Run: `python scripts/crear_fixture.py /tmp/datos-1.4.json tests/fixtures/datos.json`.

- [ ] **Step 2: Types and helpers**

Los tipos y las cuatro funciones de Interfaces.

- [ ] **Step 3: Run the existing suite**

Run: `npm test`
Expected: las 35 pruebas actuales en verde con la fixture nueva.

- [ ] **Step 4: Commit**

`git commit -m "feat(datos): read contract 1.4 with 2026 programs and topics"`

### Task 4: Web. `/temas/` y una página por tema

**Files:**
- Create: `src/pages/temas/index.astro`, `src/pages/temas/[tema].astro`
- Modify: `src/layouts/Base.astro` (enlace «Propuestas por tema» en la navegación, antes de «Sobre este proyecto»)
- Test: `tests/temas.spec.ts`

**Interfaces:**
- Consumes: los helpers de Task 3.
- Produces: rutas `/temas/` y `/temas/<slugTema>/`. Cada partido está en `<details id="<slug(partido)>" class="partido-tema">`, con un `<summary>` «<nombre> · N propuestas» y, por propuesta, un `.propuesta` con `.resumen`, `.cita` y un enlace `pág. N`. Los partidos sin propuestas van en `ul.sin-propuestas > li`.

- [ ] **Step 1: Write the failing tests** (`tests/temas.spec.ts`)

- `'el índice enlaza los 17 temas'`: `/temas/` tiene 17 enlaces `a[href^="/temas/"]`, en el orden de `meta.temas`.
- `'en cada tema los partidos van en orden alfabético y plegados'`: en `/temas/vivienda/`, los `<summary>` siguen el orden de `[...nombres].sort((a,b)=>a.localeCompare(b,'es'))`, y todos los `details` tienen `open === false`.
- `'cada propuesta lleva resumen, cita y página enlazada'`: dentro de cada `.propuesta`, `.cita` no está vacío y el enlace `pág.` cumple `/#page=\d+$/`.
- `'una cita con < y & se ve como texto'`: la propuesta sintética se ve con `<i>` literal en `innerText`, y no hay ningún elemento `i` dentro de `.cita`.
- `'los partidos sin programa salen con su motivo'`: en `/temas/vivienda/`, `.sin-propuestas` contiene «Aún no ha publicado su programa de 2026.» y el enlace a `https://pazcasaytrabajo.es/`. En `/temas/pensiones/`, el partido preparado en la fixture sale con «Sin propuestas sobre este tema».
- `'ninguna propuesta de 2023 aparece en los temas'`: ningún `.resumen` coincide con el `texto` de una promesa de 2023 de la fixture.
- `'el aviso del resumen automático está en cada tema'`: el texto del aviso de las Global Constraints aparece en `/temas/vivienda/`.
- `'las páginas de tema no cargan JavaScript'`: `page.locator('script')` tiene 0 elementos en `/temas/vivienda/`.
- `'sin meta.temas el build sigue funcionando'`: con `DATOS_JSON` apuntando a una copia de la fixture sin `meta.temas` ni `programa_2026` (un `test.describe` con su propio `webServer` no está soportado, así que se hace como prueba de build en Node: `execSync('npm run build', { env: {...process.env, DATOS_JSON: ruta} })` no lanza).

- [ ] **Step 2: Run them and check they fail**

Run: `npx playwright test tests/temas.spec.ts --project=web`
Expected: FAIL (404 en `/temas/`).

- [ ] **Step 3: Implement the two pages and the navigation link**

Estilo con las clases existentes del diseño «Boletín» (`aviso`, `cita`). `getStaticPaths` desde `listaTemas()`.

- [ ] **Step 4: Run the whole suite**

Run: `npm test`
Expected: todo en verde.

- [ ] **Step 5: Commit**

`git commit -m "feat(web): add 2026 proposals by topic"`

### Task 5: Web. Ficha de partido y «Sobre este proyecto»

**Files:**
- Modify: `src/pages/partido/[id].astro`, `src/pages/index.astro`, `src/pages/sobre.astro`
- Test: `tests/ficha.spec.ts`, `tests/sobre.spec.ts`, `tests/portada.spec.ts`

**Interfaces:**
- Consumes: los helpers de Task 3 y las rutas de Task 4.

- [ ] **Step 1: Write the failing tests**

- ficha: `'los temas de 2026 enlazan a su página de tema'`. En `/partido/frente-amplio/` (o el partido con programa 2026 de la fixture) hay una sección `#temas-2026` con un enlace «Programa de 2026» a `programa_2026`, y cada tema enlaza a `/temas/<slug>/#<slug(partido)>`. Al seguir uno, el `details` con ese id existe.
- ficha: `'sin programa de 2026, la ficha dice el motivo'`. En `/partido/junts/` aparece «Aún no ha publicado su programa de 2026.» y no aparece «aún no está cargado».
- portada: `'un partido sin 2023 pero con 2026 enseña sus temas de 2026'`. La ficha de SALF en la portada lista tres temas y ya no dice solo «No existía en 2023.».
- sobre: `'sobre enlaza los programas de 2026 y explica el orden'`. Hay un enlace por cada `programa_2026` no nulo y aparece «orden alfabético».

- [ ] **Step 2: Run them and check they fail**

Run: `npx playwright test tests/ficha.spec.ts tests/portada.spec.ts tests/sobre.spec.ts --project=web`
Expected: los 4 nuevos fallan.

- [ ] **Step 3: Implement**

- **Ficha:** una sección «A qué dedica su programa de 2026» (`#temas-2026`), con barras como las de 2023 y cada tema enlazado. Desaparece el texto «aún no está cargado».
- **Portada:** si hay temas de 2026, «Dedica más espacio en 2026 a: …», que sustituye o acompaña a la línea de 2023. Si no hay 2026, queda como está.
- **Sobre:** una lista «Los programas electorales de 2026» y un párrafo con el aviso de la página de tema.

- [ ] **Step 4: Run the whole suite**

Run: `npm test`
Expected: todo en verde.

- [ ] **Step 5: Commit**

`git commit -m "feat(web): show 2026 topics on party pages, home and about"`

### Task 6: Revisión de Fran y despliegue

- [ ] **Step 1: Deploy the motor:** `git push` de `poligrafo-es` y `git pull` en la Pi (`/root/projects/poligrafo-es`).
- [ ] **Step 2: Generate the sample:** en la Pi, `python3 electoral.py muestra-promesas --anio 2026 --n 30 --salida docs/revision_promesas_2026.md`. Copiarla al PC y dársela a Fran.
- [ ] **Step 3: Gate:** Fran marca las casillas. Si más de 3 de las 30 fallan, se para: corregir la extracción (prompt o filtro) y repetir antes de seguir. Con 3 o menos, se apuntan en la nota y se sigue.
- [ ] **Step 4: Wait for the night export:** comprobar que `data/datos.json` del repo `poligrafo-web` en GitHub tiene `version_contrato` 1.4.0 (la noche de las 23:30 lo empuja). Si Fran no quiere esperar, se ejecuta la misma exportación a mano en la Pi.
- [ ] **Step 5: Deploy the web:** `git push` de `poligrafo-web` (Cloudflare Pages construye solo). Comprobar en `https://poligrafo-29n.pages.dev/temas/vivienda/` que salen 10 partidos con propuestas y los motivos de los demás.
- [ ] **Step 6: Vault:** en `01_PROYECTOS/poligrafo-es.md`, marcar como hecho el pendiente «La web no enseña nada de 2026», con la fecha y el resultado de la muestra.
