# Web electoral 29N (plan 2 de 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publicar en `poligrafo-29n.pages.dev` una web estática que enseñe, partido a partido, lo que prometieron en 2023 y lo que votaron en la XV legislatura, regenerada cada noche desde la Orange Pi y vigilada por ARGUS.

**Architecture:** Repo nuevo `poligrafo-web` (Astro, HTML estático) que solo lee `data/datos.json` en el build. El motor (`poligrafo-es`) gana un subcomando `noche` que en la Pi descarga lo nuevo, juzga, exporta, avisa por Telegram de cada «incumple» pendiente de revisión, copia `datos.json` al clon de `poligrafo-web` y hace push; Cloudflare Pages construye en cada push. ARGUS vigila el cron y un archivo de salud que escribe `noche`.

**Tech Stack:** Astro (última estable), Playwright (Chromium, viewport 390×844), Node 22 en el PC y en Cloudflare; Python 3.12 + pytest en el motor; ARGUS (Python) en la Pi.

**Spec:** `docs/superpowers/specs/2026-10-07-web-electoral-29n-design.md` (motor ya hecho en el plan 1, mergeado en master el 2026-10-08).

## Global Constraints

- Todo texto visible en español; plural `ustedes`, nunca `vosotros`.
- **Ni una raya ni semirraya** en textos nuestros publicables: coma o dos puntos. Las citas literales y los títulos oficiales se copian tal cual.
- Los votos se describen con el título oficial de la iniciativa: no hay «resumen en lenguaje llano» generado por IA (sería otra capa de interpretación sin revisar).
- Sin ranking ni comparador entre partidos; **la portada no lleva cifras de cumple/incumple** (decisión de Fran, 2026-10-08).
- Ficha: cruces firmes **agrupados por tema**, temas en el orden del espacio que les dedica el programa (decisión de Fran, 2026-10-08). Nadie elige promesas a dedo.
- Un «incumple» solo es veredicto si está en `config/revision_manual.json`; se rotula «Revisado a mano».
- `noindex`: `<meta name="robots" content="noindex, nofollow">` en todas las páginas y `robots.txt` con `Disallow: /`.
- Diseño A «Boletín»: Newsreader (titulares y citas, cursiva) + Source Sans 3; fondo `#F5F5F1`, tinta `#1A1A1A`, gris `#4A4A4A`, líneas `#D6D4CC`, enlaces `#1F3A8A`; cumple `#1E3A8A`, incumple `#9A4A06`; sin colores de partido; pie oscuro con «Sobre este proyecto» y la firma.
- Móvil primero (390 px), objetivos táctiles ≥ 44 px, texto de 15 a 18 px, sin desborde horizontal.
- Toda afirmación lleva su enlace oficial; un enlace nulo no se pinta (nunca `href="null"`).
- Contrato: la web acepta `version_contrato` con mayor `1`; cualquier otra hace fallar el build (Cloudflare conserva el despliegue anterior).
- LLM: ningún modelo de Anthropic; la ejecución nocturna con tope de 0,30 $.
- Pruebas de comportamiento solamente (Playwright en la web, pytest por CLI en el motor). Nada de pruebas unitarias.
- Push, creación de repos públicos, Cloudflare y crontab: **solo con el OK explícito de Fran en ese momento**. Nada se anuncia a los allegados sin su OK.
- Secretos: la clave de OpenRouter y el token de Telegram nunca aparecen en el chat ni en git.

## Review Focus

1. Partido sin programa o sin cruces (Podemos, Compromís, SALF, CC, UPN): la ficha se lee completa, con el motivo, sin encabezados vacíos. Prueba en Tarea 3.
2. Enlaces nulos (`url_bocg`, `url_boe`) o juez sin respuesta (`null`): no hay `href="null"` ni la palabra «null» en pantalla. Prueba en Tarea 3.
3. Títulos de expediente de más de 300 caracteres en 390 px: se parten, sin desborde horizontal. Prueba en Tarea 4 (barrido de todas las páginas).
4. `datos.json` ausente o con versión de contrato distinta: el build falla con un mensaje claro y no se publica nada roto. Prueba en Tarea 1.
5. El push nocturno falla (red, clave de despliegue): la salud lo registra, el comando sale con código ≠ 0 y ARGUS avisa; nunca hay `--force`. Pruebas en Tareas 5 y 6.

---

### Task 0: Registrar en la especificación las decisiones del 2026-10-08

**Files:**
- Modify: `D:\1.Fran\DEV\poligrafo-es\docs\superpowers\specs\2026-10-07-web-electoral-29n-design.md` (§7 y §8)

- [ ] **Step 1: Crear la rama del motor**

```bash
git -C "D:/1.Fran/DEV/poligrafo-es" checkout -b feat/web-29n
```

- [ ] **Step 2: Editar §7, punto 1 («Portada»)** para que diga:

```markdown
1. **Portada, «Los partidos».** Fichas ordenadas por escaños (sin escaño: al final, en orden alfabético). En cada
   una: escaños de 2023 y los tres temas a los que dedica más espacio su programa (o el motivo de que no haya
   programa). **Sin cifras de cumple o incumple** (decisión de Fran, 2026-10-08): quien gobierna acumula
   «cumple» votando sus propias leyes y los «incumple» exigen revisión a mano, así que puestas lado a lado
   se leerían como un ranking. Arriba: *«Aquí no te decimos a quién votar. Te enseñamos lo que prometieron y lo
   que votaron.»*
```

- [ ] **Step 3: Editar §7, punto 2 («Ficha de partido»)**: sustituir «Promesas principales con su estado» por:

```markdown
Cruces con veredicto firme **agrupados por tema**, con los temas en el orden del espacio que les dedica su
programa (decisión de Fran, 2026-10-08: el orden lo pone el partido, nadie elige promesas). Cada «incumple»
firme lleva «Revisado a mano».
```

- [ ] **Step 4: Añadir a §8 («Operación»)**:

```markdown
- **Revisión de «incumple»:** un «incumple» solo es veredicto si Fran lo confirma (`config/revision_manual.json`).
  Cada noche, los nuevos candidatos se le avisan por Telegram (canal privado de PolígrafoES).
- **Dirección:** `poligrafo-29n.pages.dev` (cuenta de Cloudflare de Fran).
```

- [ ] **Step 5: Commit**

```bash
git -C "D:/1.Fran/DEV/poligrafo-es" add docs/superpowers/specs/2026-10-07-web-electoral-29n-design.md
git -C "D:/1.Fran/DEV/poligrafo-es" commit -m "docs(spec): portada sin cifras, ficha por temas y aviso de incumple"
```

---

### Task 1: Esqueleto de `poligrafo-web`: datos, diseño y guardas

**Files:**
- Create: `D:\1.Fran\DEV\poligrafo-web\package.json`, `astro.config.mjs`, `tsconfig.json`, `playwright.config.ts`, `.gitignore`, `README.md`, `LICENSE`
- Create: `src/lib/datos.ts`, `src/lib/config.ts`, `src/layouts/Base.astro`, `src/pages/index.astro` (provisional), `public/estilo.css`, `public/robots.txt`
- Create: `scripts/crear_fixture.py`, `tests/fixtures/datos.json`, `data/datos.json`
- Test: `tests/base.spec.ts`

**Interfaces:**
- Consumes: `datos.json` del motor (contrato 1.x). Campos usados: `meta.{version_contrato,generado,periodo,recuentos}`; `partidos[].{id,nombre,escanos_23j,gobierno,programa_2023,sin_programa,nota_gobierno}`; `votaciones[].{id,fecha,tipo,subtipo,expediente,que_se_vota,resultado,url_sesion,url_bocg,url_boe}`; `promesas[].{id,partido,anio,texto,cita,pagina,tema,url_programa_pagina}`; `cruces[].{votacion_id,promesa_id,partido,voto,dividido,nivel,veredicto,revisado_a_mano,jueces}`; `temas[partido][anio][tema]=pct`; `coherencia[partido][]={clave_iniciativa,a_favor,en_contra}`; `gobierno[partido][]={votacion_id,promesa_id,url_boe}`; `finanzas[partido]={gasto_justificado_eur,endeudamiento_eur,propuesta_reduccion_subvencion,pagina,transparencia,url_informe}`.
- Produces (desde `src/lib/datos.ts`): `datos`, `votacion: Map<string, Votacion>`, `promesa: Map<number, Promesa>`, `slug(id: string): string`, `partidosOrdenados(): Partido[]`, `temasDe(id: string, anio?: string): [string, number][]`, `crucesDe(id: string): { firmes: Cruce[]; juzgaTu: Cruce[] }`, `porTema(id: string, lista: Cruce[]): [string, Cruce[]][]`, `fecha(iso: string): string`, `euros(n: number): string`. Desde `src/lib/config.ts`: `FIRMA`, `REPO_MOTOR`, `REPO_WEB`. Layout `Base.astro` con prop `titulo: string`.

- [ ] **Step 1: Crear el proyecto e instalar**

```bash
mkdir "D:/1.Fran/DEV/poligrafo-web" && cd "D:/1.Fran/DEV/poligrafo-web" && git init -b main
```

`package.json`:

```json
{
  "name": "poligrafo-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "astro dev",
    "build": "astro build",
    "preview": "astro preview --port 4321",
    "test": "playwright test",
    "enlaces": "playwright test --grep @red --grep-invert SIN_EXCLUSIONES"
  }
}
```

```bash
cd "D:/1.Fran/DEV/poligrafo-web" && npm install astro@latest && npm install -D @playwright/test@latest && npx playwright install chromium
```

`astro.config.mjs`:

```js
import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://poligrafo-29n.pages.dev',
  trailingSlash: 'always',
  build: { format: 'directory' },
});
```

`tsconfig.json`:

```json
{ "extends": "astro/tsconfigs/strict", "include": [".astro/types.d.ts", "**/*"], "exclude": ["dist"] }
```

`.gitignore`:

```
node_modules/
dist/
.astro/
test-results/
playwright-report/
```

- [ ] **Step 2: Fixture de pruebas a partir de los datos reales**

`scripts/crear_fixture.py`:

```python
"""Recorta el datos.json real a un fixture pequeño y estable para Playwright.

Uso: python scripts/crear_fixture.py <datos.json del motor> tests/fixtures/datos.json
Conserva todos los partidos, temas, finanzas, coherencia y gobierno; de cruces, todos los revisados a mano,
4 firmes más, 3 «juzga tú» y 1 con voto dividido por partido.
"""
import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
sel = []
for p in d["partidos"]:
    cs = [c for c in d["cruces"] if c["partido"] == p["id"]]
    firmes = [c for c in cs if c["nivel"] == "veredicto"]
    sel += [c for c in firmes if c["revisado_a_mano"]] + [c for c in firmes if not c["revisado_a_mano"]][:4]
    sel += [c for c in cs if c["nivel"] == "juzga_tu"][:3] + [c for c in cs if c["dividido"]][:1]
sel = list({(c["votacion_id"], c["promesa_id"], c["partido"]): c for c in sel}.values())
gob = [g for gs in d["gobierno"].values() for g in gs]
vids = ({c["votacion_id"] for c in sel} | {g["votacion_id"] for g in gob}
        | {x[k] for pares in d["coherencia"].values() for x in pares for k in ("a_favor", "en_contra")})
pids = {c["promesa_id"] for c in sel} | {g["promesa_id"] for g in gob}
d["cruces"] = sel
d["votaciones"] = [v for v in d["votaciones"] if v["id"] in vids]
d["promesas"] = [p for p in d["promesas"] if p["id"] in pids]
json.dump(d, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(sel), "cruces,", len(d["votaciones"]), "votaciones,", len(d["promesas"]), "promesas")
```

```bash
cd "D:/1.Fran/DEV/poligrafo-web" && mkdir -p tests/fixtures data && python scripts/crear_fixture.py ../poligrafo-es/datos.json tests/fixtures/datos.json && cp ../poligrafo-es/datos.json data/datos.json
```

Expected: una línea con unos 100 cruces y sus votaciones y promesas.

- [ ] **Step 3: Escribir la prueba que falla**

`playwright.config.ts`:

```ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'tests',
  grepInvert: /@red/,
  timeout: 60_000,
  use: { baseURL: 'http://localhost:4321', viewport: { width: 390, height: 844 }, browserName: 'chromium' },
  webServer: {
    command: 'npm run build && npm run preview',
    url: 'http://localhost:4321',
    reuseExistingServer: false,
    timeout: 300_000,
    env: { DATOS_JSON: process.env.DATOS_JSON ?? 'tests/fixtures/datos.json' },
  },
});
```

`tests/base.spec.ts`:

```ts
import { test, expect } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

test('ninguna página se deja indexar', async ({ page, request }) => {
  await page.goto('/');
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex, nofollow');
  const robots = await (await request.get('/robots.txt')).text();
  expect(robots).toContain('Disallow: /');
});

test('el pie lleva a «Sobre este proyecto» y va firmado', async ({ page }) => {
  await page.goto('/');
  const pie = page.locator('footer');
  await expect(pie.getByRole('link', { name: 'Sobre este proyecto' })).toHaveAttribute('href', '/sobre/');
  await expect(pie).toContainText('Hecho por');
});

test('un datos.json de otra versión del contrato no se publica', () => {
  const dir = mkdtempSync(join(tmpdir(), 'poligrafo-'));
  const datos = JSON.parse(readFileSync('tests/fixtures/datos.json', 'utf-8'));
  datos.meta.version_contrato = '2.0.0';
  writeFileSync(join(dir, 'datos.json'), JSON.stringify(datos));
  const r = spawnSync('npx', ['astro', 'build', '--outDir', join(dir, 'dist')],
    { env: { ...process.env, DATOS_JSON: join(dir, 'datos.json') }, encoding: 'utf-8', shell: true });
  expect(r.status).not.toBe(0);
  expect(r.stdout + r.stderr).toContain('Versión del contrato');
});
```

- [ ] **Step 4: Ejecutar y ver que falla**

Run: `cd "D:/1.Fran/DEV/poligrafo-web" && npx playwright test tests/base.spec.ts`
Expected: FAIL (el build no tiene páginas ni `robots.txt`; el servidor no arranca o devuelve 404).

- [ ] **Step 5: Implementar datos, configuración, layout y estilos**

`src/lib/config.ts`:

```ts
export const FIRMA = 'Fran';
export const REPO_MOTOR = 'https://github.com/Ufransa/poligrafo-es';
export const REPO_WEB = 'https://github.com/Ufransa/poligrafo-web';
```

`src/lib/datos.ts`:

```ts
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const VERSION_MAYOR = 1;

export type Juez = { postura: 'a_favor' | 'en_contra'; fuerza: 'directa' | 'indirecta' | null } | null;
export interface Partido {
  id: string; nombre: string; escanos_23j: number; gobierno: [string, string | null][];
  programa_2023: string | null; sin_programa?: string; nota_gobierno?: string;
}
export interface Votacion {
  id: string; fecha: string; tipo: string; subtipo: string; expediente: string; que_se_vota: string;
  resultado: string; url_sesion: string | null; url_bocg: string | null; url_boe: string | null;
}
export interface Promesa {
  id: number; partido: string; anio: number; texto: string; cita: string; pagina: number; tema: string;
  url_programa_pagina: string;
}
export interface Cruce {
  votacion_id: string; promesa_id: number; partido: string; voto: string; dividido: boolean;
  nivel: 'veredicto' | 'juzga_tu'; veredicto: 'cumple' | 'incumple'; revisado_a_mano: boolean;
  jueces: Record<string, Juez>;
}
export interface Finanzas {
  gasto_justificado_eur: number; endeudamiento_eur: number; propuesta_reduccion_subvencion: boolean;
  pagina: number; transparencia: string; url_informe: string;
}
export interface Datos {
  meta: { version_contrato: string; generado: string; periodo: { desde: string; hasta: string };
          recuentos: { votaciones: number; promesas: number; veredictos: number } };
  partidos: Partido[]; votaciones: Votacion[]; promesas: Promesa[]; cruces: Cruce[];
  temas: Record<string, Record<string, Record<string, number>>>;
  coherencia: Record<string, { clave_iniciativa: string; a_favor: string; en_contra: string }[]>;
  gobierno: Record<string, { votacion_id: string; promesa_id: number; url_boe: string | null }[]>;
  finanzas: Record<string, Finanzas>;
}

function cargar(): Datos {
  const ruta = resolve(process.env.DATOS_JSON ?? 'data/datos.json');
  let d: Datos;
  try {
    d = JSON.parse(readFileSync(ruta, 'utf-8'));
  } catch (e) {
    throw new Error(`No se puede leer datos.json en ${ruta}: ${e}`);
  }
  const mayor = Number(String(d.meta?.version_contrato ?? '').split('.')[0]);
  if (mayor !== VERSION_MAYOR) {
    throw new Error(`Versión del contrato ${d.meta?.version_contrato} no soportada (se espera ${VERSION_MAYOR}.x)`);
  }
  return d;
}

export const datos = cargar();
export const votacion = new Map(datos.votaciones.map((v) => [v.id, v]));
export const promesa = new Map(datos.promesas.map((p) => [p.id, p]));

export function slug(id: string): string {
  return id.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

/** Por escaños de 2023; empates y partidos sin escaño, en orden alfabético. */
export function partidosOrdenados() {
  return [...datos.partidos].sort((a, b) => (b.escanos_23j - a.escanos_23j) || a.nombre.localeCompare(b.nombre, 'es'));
}

export function temasDe(id: string, anio = '2023'): [string, number][] {
  return Object.entries(datos.temas[id]?.[anio] ?? {}).sort((a, b) => b[1] - a[1]);
}

export function crucesDe(id: string) {
  const c = datos.cruces.filter((x) => x.partido === id && votacion.has(x.votacion_id) && promesa.has(x.promesa_id));
  return { firmes: c.filter((x) => x.nivel === 'veredicto'), juzgaTu: c.filter((x) => x.nivel === 'juzga_tu') };
}

/** Agrupa por tema, en el orden del espacio que el programa del partido dedica a cada tema. */
export function porTema(id: string, lista: Cruce[]): [string, Cruce[]][] {
  const orden = temasDe(id).map(([t]) => t);
  const grupos = new Map<string, Cruce[]>();
  for (const c of lista) {
    const t = promesa.get(c.promesa_id)!.tema;
    grupos.set(t, [...(grupos.get(t) ?? []), c]);
  }
  const rango = (t: string) => (orden.indexOf(t) === -1 ? orden.length : orden.indexOf(t));
  return [...grupos.entries()].sort((a, b) => rango(a[0]) - rango(b[0]));
}

const FECHA = new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Europe/Madrid' });
export const fecha = (iso: string) => FECHA.format(new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso));
const EUROS = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });
export const euros = (n: number) => EUROS.format(n);
```

`src/layouts/Base.astro`:

```astro
---
import { datos, fecha } from '../lib/datos';
import { FIRMA } from '../lib/config';
interface Props { titulo: string }
const { titulo } = Astro.props;
---
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="robots" content="noindex, nofollow" />
    <title>{titulo} · PolígrafoES 29N</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400..700;1,6..72,400..700&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="/estilo.css" />
  </head>
  <body>
    <header class="cabecera"><a href="/" class="marca">PolígrafoES <span>29N</span></a></header>
    <main><slot /></main>
    <footer class="pie">
      <a href="/sobre/">Sobre este proyecto</a>
      <p>Hecho por {FIRMA}. Datos actualizados el {fecha(datos.meta.generado)}.</p>
    </footer>
  </body>
</html>
```

`public/robots.txt`:

```
User-agent: *
Disallow: /
```

`public/estilo.css`:

```css
:root {
  --fondo: #F5F5F1; --tinta: #1A1A1A; --gris: #4A4A4A; --linea: #D6D4CC; --enlace: #1F3A8A;
  --cumple: #1E3A8A; --incumple: #9A4A06;
  --serif: 'Newsreader', Georgia, serif; --sans: 'Source Sans 3', system-ui, sans-serif;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--fondo); color: var(--tinta); font: 17px/1.5 var(--sans); overflow-wrap: anywhere; }
main { max-width: 42rem; margin: 0 auto; padding: 0 16px 48px; }
a { color: var(--enlace); }
h1, h2, h3 { font-family: var(--serif); line-height: 1.2; }
h1 { font-size: 1.9rem; } h2 { font-size: 1.4rem; margin-top: 2.2rem; border-top: 1px solid var(--linea); padding-top: 1rem; }
.cabecera { border-bottom: 1px solid var(--linea); padding: 12px 16px; }
.marca { font-family: var(--serif); font-weight: 700; font-size: 1.2rem; color: var(--tinta); text-decoration: none; display: inline-block; min-height: 44px; line-height: 44px; }
.marca span { color: var(--gris); font-weight: 400; }
.pie { background: var(--tinta); color: var(--fondo); padding: 24px 16px; font-size: 15px; }
.pie a { color: var(--fondo); display: inline-block; min-height: 44px; line-height: 44px; }
.lema { font-family: var(--serif); font-style: italic; font-size: 1.25rem; color: var(--gris); }
.ficha-partido { border-top: 1px solid var(--linea); padding: 14px 0; }
.ficha-partido a.abrir { display: inline-block; min-height: 44px; line-height: 44px; font-weight: 600; }
.cruce { border-left: 4px solid var(--linea); padding: 8px 0 8px 12px; margin: 16px 0; }
.cruce.cumple { border-color: var(--cumple); } .cruce.incumple { border-color: var(--incumple); }
.sello { font-weight: 600; text-transform: uppercase; letter-spacing: .04em; font-size: 15px; margin: 0; }
.cruce.cumple .sello { color: var(--cumple); } .cruce.incumple .sello { color: var(--incumple); }
.revisado { color: var(--gris); text-transform: none; letter-spacing: 0; font-weight: 400; }
.promesa { font-weight: 600; margin: .3rem 0; }
.cita { font-family: var(--serif); font-style: italic; color: var(--gris); margin: .3rem 0; }
.votacion, .voto, .aviso { font-size: 15px; color: var(--gris); margin: .3rem 0; }
.enlaces { list-style: none; padding: 0; margin: .4rem 0; display: flex; flex-wrap: wrap; gap: 0 16px; }
.enlaces a { display: inline-block; min-height: 44px; line-height: 44px; font-size: 15px; }
details > summary { min-height: 44px; line-height: 44px; cursor: pointer; color: var(--enlace); }
.barra { display: grid; grid-template-columns: 1fr auto; gap: 8px; font-size: 15px; }
.barra i { display: block; height: 6px; background: var(--gris); grid-column: 1 / -1; }
```

`src/pages/index.astro` (provisional, la Tarea 2 la reescribe):

```astro
---
import Base from '../layouts/Base.astro';
---
<Base titulo="Los partidos"><h1>Los partidos</h1></Base>
```

`LICENSE`: MIT, `Copyright (c) 2026 Ufransa` (mismo texto que el del motor).

`README.md`:

```markdown
# poligrafo-web

Web estática de PolígrafoES para las generales del 29N: lo que cada partido prometió en 2023 frente a lo que
votó en la XV legislatura. Solo lee `data/datos.json`, que genera el motor
([poligrafo-es](https://github.com/Ufransa/poligrafo-es)) cada noche.

- `npm run build`: genera `dist/` (falla si `datos.json` no es del contrato 1.x).
- `npm test`: pruebas de comportamiento con Playwright sobre `tests/fixtures/datos.json`.
- `npm run enlaces`: comprueba contra internet que responden los enlaces de los veredictos firmes.
- `python scripts/crear_fixture.py <datos.json> tests/fixtures/datos.json`: regenera el fixture.
```

- [ ] **Step 6: Ejecutar y ver que pasa**

Run: `cd "D:/1.Fran/DEV/poligrafo-web" && npx playwright test tests/base.spec.ts`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
cd "D:/1.Fran/DEV/poligrafo-web" && git add -A && git commit -m "feat: esqueleto astro con datos, diseño boletin y guardas de contrato"
```

---

### Task 2: Portada «Los partidos»

**Files:**
- Modify: `src/pages/index.astro`
- Test: `tests/portada.spec.ts`

**Interfaces:**
- Consumes: `partidosOrdenados`, `temasDe`, `slug` (Tarea 1); layout `Base`.
- Produces: enlaces `/partido/<slug>/` que la Tarea 3 sirve.

- [ ] **Step 1: Escribir la prueba que falla**

`tests/portada.spec.ts`:

```ts
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

const datos = JSON.parse(readFileSync('tests/fixtures/datos.json', 'utf-8'));
const esperado = [...datos.partidos]
  .sort((a, b) => (b.escanos_23j - a.escanos_23j) || a.nombre.localeCompare(b.nombre, 'es'))
  .map((p) => p.nombre);

test('todos los partidos, por escaños y los que no tienen, al final por orden alfabético', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.ficha-partido h2')).toHaveText(esperado);
});

test('la portada no compara partidos con cifras de cumple o incumple', async ({ page }) => {
  await page.goto('/');
  const texto = await page.locator('main').innerText();
  expect(texto).not.toMatch(/\d+\s*(cumple|incumple|veredicto)/i);
  await expect(page.locator('main')).toContainText('Aquí no te decimos a quién votar.');
});

test('cada partido enseña sus temas o por qué no tiene programa, y lleva a su ficha', async ({ page }) => {
  await page.goto('/');
  for (const p of datos.partidos) {
    const ficha = page.locator('.ficha-partido', { has: page.getByRole('heading', { name: p.nombre, exact: true }) });
    if (p.programa_2023) await expect(ficha).toContainText('Dedica más espacio a');
    else await expect(ficha).toContainText(p.sin_programa);
    await ficha.getByRole('link', { name: `Ver ficha de ${p.nombre}` }).click();
    await expect(page.locator('h1')).toHaveText(p.nombre);
    await page.goBack();
  }
});
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `npx playwright test tests/portada.spec.ts`
Expected: FAIL (no hay `.ficha-partido`).

- [ ] **Step 3: Implementar**

`src/pages/index.astro`:

```astro
---
import Base from '../layouts/Base.astro';
import { partidosOrdenados, temasDe, slug } from '../lib/datos';
const pct = (n: number) => `${n.toLocaleString('es-ES')} %`;
---
<Base titulo="Los partidos">
  <h1>Los partidos</h1>
  <p class="lema">Aquí no te decimos a quién votar. Te enseñamos lo que prometieron y lo que votaron.</p>
  {partidosOrdenados().map((p) => {
    const temas = temasDe(p.id).slice(0, 3);
    return (
      <section class="ficha-partido">
        <h2>{p.nombre}</h2>
        <p class="aviso">{p.escanos_23j > 0 ? `${p.escanos_23j} escaños en 2023` : 'Sin escaño propio en 2023'}</p>
        {p.programa_2023 && temas.length > 0
          ? <p>Dedica más espacio a: {temas.map(([t, n]) => `${t} (${pct(n)})`).join(', ')}.</p>
          : <p class="aviso">{p.sin_programa}</p>}
        <a class="abrir" href={`/partido/${slug(p.id)}/`}>Ver ficha de {p.nombre}</a>
      </section>
    );
  })}
</Base>
```

Para que la prueba de navegación pase ya, crear `src/pages/partido/[id].astro` mínimo (la Tarea 3 lo completa):

```astro
---
import Base from '../../layouts/Base.astro';
import { datos, slug } from '../../lib/datos';
export function getStaticPaths() {
  return datos.partidos.map((p) => ({ params: { id: slug(p.id) }, props: { p } }));
}
const { p } = Astro.props;
---
<Base titulo={p.nombre}><h1>{p.nombre}</h1></Base>
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `npx playwright test`
Expected: 6 passed (3 de base + 3 de portada).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: portada con partidos por escanos, temas y sin cifras comparables"
```

---

### Task 3: Ficha de partido

**Files:**
- Modify: `src/pages/partido/[id].astro`
- Create: `src/components/Cruce.astro`
- Test: `tests/ficha.spec.ts`

**Interfaces:**
- Consumes: `crucesDe`, `porTema`, `temasDe`, `votacion`, `promesa`, `fecha`, `euros`, `datos` (Tarea 1).
- Produces: componente `Cruce.astro` con props `{ c: Cruce; firme: boolean }` y clases `.cruce.cumple`, `.cruce.incumple`, `.sello`, `.revisado`, `.cita`, `.enlaces`, `details.jueces`; secciones con `id`: `#temas`, `#cruces`, `#juzga-tu`, `#coherencia`, `#gobierno`, `#dinero`.

- [ ] **Step 1: Escribir la prueba que falla**

`tests/ficha.spec.ts`:

```ts
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

const datos = JSON.parse(readFileSync('tests/fixtures/datos.json', 'utf-8'));
const slug = (id: string) => id.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const conFirmes = [...new Set(datos.cruces.filter((c: any) => c.nivel === 'veredicto').map((c: any) => c.partido))] as string[];

test('cada veredicto firme lleva cita, página del programa y enlace a la votación', async ({ page }) => {
  expect(conFirmes.length).toBeGreaterThan(0);
  for (const id of conFirmes) {
    await page.goto(`/partido/${slug(id)}/`);
    const firmes = page.locator('#cruces .cruce');
    expect(await firmes.count()).toBeGreaterThan(0);
    for (const c of await firmes.all()) {
      await expect(c.locator('.cita')).not.toBeEmpty();
      await expect(c.locator('.enlaces a', { hasText: 'Programa, pág.' })).toHaveAttribute('href', /#page=\d+$/);
      await expect(c.locator('.enlaces a', { hasText: 'Votación en el Congreso' })).toHaveAttribute('href', /^https:\/\/www\.congreso\.es\//);
    }
  }
});

test('ningún enlace es nulo y nunca se ve la palabra null', async ({ page }) => {
  for (const p of datos.partidos) {
    await page.goto(`/partido/${slug(p.id)}/`);
    for (const a of await page.locator('main a').all()) {
      expect(await a.getAttribute('href')).toMatch(/^(https:\/\/|\/|#)/);
    }
    expect(await page.locator('main').innerText()).not.toMatch(/\b(null|undefined|NaN)\b/);
  }
});

test('«Juzga tú» empieza plegado', async ({ page }) => {
  const id = datos.cruces.find((c: any) => c.nivel === 'juzga_tu').partido;
  await page.goto(`/partido/${slug(id)}/`);
  const det = page.locator('details#juzga-tu');
  await expect(det).toHaveCount(1);
  expect(await det.evaluate((d: HTMLDetailsElement) => d.open)).toBe(false);
});

test('un incumple firme dice que se revisó a mano', async ({ page }) => {
  const c = datos.cruces.find((x: any) => x.nivel === 'veredicto' && x.veredicto === 'incumple');
  await page.goto(`/partido/${slug(c.partido)}/`);
  await expect(page.locator('#cruces .cruce.incumple .revisado').first()).toContainText('Revisado a mano');
});

test('los cruces firmes salen agrupados por tema, en el orden del espacio del programa', async ({ page }) => {
  for (const id of conFirmes) {
    await page.goto(`/partido/${slug(id)}/`);
    const orden = Object.entries(datos.temas[id]['2023'] as Record<string, number>).sort((a, b) => b[1] - a[1]).map(([t]) => t);
    const vistos = await page.locator('#cruces h3').allInnerTexts();
    const rango = (t: string) => (orden.indexOf(t) === -1 ? orden.length : orden.indexOf(t));
    expect(vistos.map(rango)).toEqual([...vistos.map(rango)].sort((a, b) => a - b));
  }
});

test('un partido sin programa explica por qué y no deja secciones vacías', async ({ page }) => {
  for (const p of datos.partidos.filter((x: any) => !x.programa_2023)) {
    await page.goto(`/partido/${slug(p.id)}/`);
    await expect(page.locator('main')).toContainText(p.sin_programa);
    for (const h of await page.locator('main h2').all()) {
      const seccion = h.locator('xpath=..');
      expect((await seccion.innerText()).trim().length).toBeGreaterThan((await h.innerText()).trim().length + 10);
    }
  }
});

test('«Lo que hicieron gobernando» solo aparece en quien tiene datos de gobierno', async ({ page }) => {
  for (const p of datos.partidos) {
    await page.goto(`/partido/${slug(p.id)}/`);
    await expect(page.locator('#gobierno')).toHaveCount((datos.gobierno[p.id] ?? []).length > 0 ? 1 : 0);
  }
});

test('un voto dividido se dice', async ({ page }) => {
  const c = datos.cruces.find((x: any) => x.dividido);
  test.skip(!c, 'el fixture no trae votos divididos');
  await page.goto(`/partido/${slug(c.partido)}/`);
  await expect(page.locator('main')).toContainText('votó dividido');
});
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `npx playwright test tests/ficha.spec.ts`
Expected: FAIL (la ficha solo tiene el título).

- [ ] **Step 3: Implementar el componente del cruce**

`src/components/Cruce.astro`:

```astro
---
import type { Cruce } from '../lib/datos';
import { votacion, promesa, fecha } from '../lib/datos';
interface Props { c: Cruce; firme: boolean }
const { c, firme } = Astro.props;
const v = votacion.get(c.votacion_id)!;
const p = promesa.get(c.promesa_id)!;
const enlaces = ([
  [`Programa, pág. ${p.pagina}`, p.url_programa_pagina],
  ['Votación en el Congreso', v.url_sesion],
  ['Texto de la iniciativa (BOCG)', v.url_bocg],
  ['Publicación en el BOE', v.url_boe],
] as [string, string | null][]).filter(([, u]) => u);
const juez = (m: string) => m.split('/').pop();
---
<article class={`cruce ${firme ? c.veredicto : ''}`}>
  {firme && (
    <p class="sello">{c.veredicto === 'cumple' ? 'Cumple' : 'Incumple'}{c.revisado_a_mano && <span class="revisado">, Revisado a mano</span>}</p>
  )}
  <p class="promesa">{p.texto}</p>
  <blockquote class="cita">«{p.cita}»</blockquote>
  <p class="votacion"><strong>{fecha(v.fecha)}.</strong> {v.expediente} {v.que_se_vota}</p>
  <p class="voto">
    {c.partido} votó <strong>{c.voto}</strong>{c.dividido && ' (votó dividido)'}. Resultado: {v.resultado}.
    {v.subtipo === 'devolucion' && ' Ojo: aquí se votaba devolver la ley; votar No es dejar que siga adelante.'}
  </p>
  <ul class="enlaces">{enlaces.map(([t, u]) => <li><a href={u} rel="noopener">{t}</a></li>)}</ul>
  <details class="jueces">
    <summary>Qué dijo cada juez</summary>
    <ul>
      {Object.entries(c.jueces).map(([m, j]) => (
        <li>{juez(m)}: {j ? `la promesa está ${j.postura === 'a_favor' ? 'a favor' : 'en contra'} de la iniciativa, relación ${j.fuerza ?? 'sin precisar'}` : 'no vio relación'}</li>
      ))}
    </ul>
  </details>
</article>
```

- [ ] **Step 4: Implementar la ficha**

`src/pages/partido/[id].astro`:

```astro
---
import Base from '../../layouts/Base.astro';
import Cruce from '../../components/Cruce.astro';
import { datos, slug, crucesDe, porTema, temasDe, votacion, promesa, fecha, euros } from '../../lib/datos';
export function getStaticPaths() {
  return datos.partidos.map((p) => ({ params: { id: slug(p.id) }, props: { p } }));
}
const { p } = Astro.props;
const { firmes, juzgaTu } = crucesDe(p.id);
const temas = temasDe(p.id);
const temas2026 = temasDe(p.id, '2026');
const coherencia = (datos.coherencia[p.id] ?? []).filter((x) => votacion.has(x.a_favor) && votacion.has(x.en_contra));
const gobierno = (datos.gobierno[p.id] ?? []).filter((g) => votacion.has(g.votacion_id) && promesa.has(g.promesa_id));
const dinero = datos.finanzas[p.id];
const pct = (n: number) => `${n.toLocaleString('es-ES')} %`;
---
<Base titulo={p.nombre}>
  <h1>{p.nombre}</h1>
  <p class="aviso">{p.escanos_23j > 0 ? `${p.escanos_23j} escaños en 2023.` : 'Sin escaño propio en 2023.'}
    {p.programa_2023 ? <a href={p.programa_2023} rel="noopener">Programa de 2023</a> : p.sin_programa}</p>

  {temas.length > 0 && (
    <section id="temas">
      <h2>A qué dedica su programa</h2>
      <p class="aviso">Porcentaje de sus promesas de 2023 sobre cada tema.{temas2026.length === 0 && ' El programa de 2026 aún no está cargado.'}</p>
      {temas.map(([t, n]) => <div class="barra"><span>{t}</span><span>{pct(n)}</span><i style={`width:${n}%`}></i></div>)}
    </section>
  )}

  {firmes.length > 0 && (
    <section id="cruces">
      <h2>Lo que prometieron y lo que votaron</h2>
      <p class="aviso">{firmes.length} casos en los que los tres jueces coinciden y la votación decide exactamente lo prometido. No se compara entre partidos: quien gobierna vota más leyes propias, y un «incumple» solo se publica si una persona lo ha revisado a mano.</p>
      {porTema(p.id, firmes).map(([t, cs]) => (
        <>
          <h3>{t}</h3>
          {cs.map((c) => <Cruce c={c} firme={true} />)}
        </>
      ))}
    </section>
  )}

  {juzgaTu.length > 0 && (
    <section>
      <h2>Juzga tú</h2>
      <details id="juzga-tu">
        <summary>{juzgaTu.length} casos en los que los jueces no coinciden del todo</summary>
        <p class="aviso">Aquí no damos veredicto: te dejamos la promesa, la votación y las fuentes.</p>
        {juzgaTu.map((c) => <Cruce c={c} firme={false} />)}
      </details>
    </section>
  )}

  {coherencia.length > 0 && (
    <section id="coherencia">
      <h2>Cambios de postura</h2>
      {coherencia.map((x) => {
        const s = votacion.get(x.a_favor)!, n = votacion.get(x.en_contra)!;
        return (
          <article class="cruce">
            <p class="votacion">{s.expediente}</p>
            <p class="voto">A favor el {fecha(s.fecha)} y en contra el {fecha(n.fecha)}.</p>
            <ul class="enlaces">
              {s.url_sesion && <li><a href={s.url_sesion} rel="noopener">Votación a favor</a></li>}
              {n.url_sesion && <li><a href={n.url_sesion} rel="noopener">Votación en contra</a></li>}
            </ul>
          </article>
        );
      })}
    </section>
  )}

  {gobierno.length > 0 && (
    <section id="gobierno">
      <h2>Lo que hicieron gobernando</h2>
      {p.nota_gobierno && <p class="aviso">{p.nota_gobierno}</p>}
      {gobierno.map((g) => {
        const v = votacion.get(g.votacion_id)!, pr = promesa.get(g.promesa_id)!;
        return (
          <article class="cruce cumple">
            <p class="promesa">{pr.texto}</p>
            <p class="voto">Aprobado el {fecha(v.fecha)}:</p>
            <p class="votacion">{v.expediente}</p>
            <ul class="enlaces">
              <li><a href={pr.url_programa_pagina} rel="noopener">Programa, pág. {pr.pagina}</a></li>
              {g.url_boe && <li><a href={g.url_boe} rel="noopener">Publicación en el BOE</a></li>}
            </ul>
          </article>
        );
      })}
    </section>
  )}

  {dinero && (
    <section id="dinero">
      <h2>Dinero de la campaña de 2023</h2>
      <p>Gasto justificado: {euros(dinero.gasto_justificado_eur)}. Deudas con entidades de crédito: {euros(dinero.endeudamiento_eur)}.</p>
      <p>{dinero.propuesta_reduccion_subvencion ? 'El Tribunal de Cuentas propuso reducirle la subvención.' : 'El Tribunal de Cuentas no propuso reducirle la subvención.'}
        {dinero.transparencia === 'sin_dato' && ' El cumplimiento de transparencia está pendiente de transcribir.'}</p>
      <ul class="enlaces"><li><a href={`${dinero.url_informe}#page=${dinero.pagina}`} rel="noopener">Informe del Tribunal de Cuentas, pág. {dinero.pagina}</a></li></ul>
    </section>
  )}
</Base>
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `npx playwright test`
Expected: todo en verde (base + portada + 8 de ficha; `un voto dividido se dice` puede salir *skipped* solo si el fixture no trae ninguno, en cuyo caso se regenera el fixture con uno).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: ficha de partido con cruces por tema, juzga tu plegado, coherencia, gobierno y dinero"
```

---

### Task 4: «Sobre este proyecto», barrido móvil y comprobación de enlaces

**Files:**
- Create: `src/pages/sobre.astro`
- Test: `tests/sobre.spec.ts`, `tests/barrido.spec.ts`, `tests/enlaces.spec.ts`

**Interfaces:**
- Consumes: `datos.meta`, `datos.partidos`, `fecha`, `FIRMA`, `REPO_MOTOR`, `REPO_WEB`.
- Produces: `/sobre/`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/sobre.spec.ts`:

```ts
import { test, expect } from '@playwright/test';

test('«Sobre este proyecto» enlaza todas las fuentes oficiales y el código', async ({ page }) => {
  await page.goto('/sobre/');
  for (const dominio of ['congreso.es', 'boe.es', 'juntaelectoralcentral.es', 'github.com/Ufransa/poligrafo-es', 'github.com/Ufransa/poligrafo-web']) {
    await expect(page.locator(`main a[href*="${dominio}"]`).first()).toBeVisible();
  }
});

test('explica la regla de los «incumple» y no esconde los errores medidos', async ({ page }) => {
  await page.goto('/sobre/');
  const main = page.locator('main');
  await expect(main).toContainText('revisado a mano');
  await expect(main).toContainText('64 %');
  await expect(main).toContainText('Juzga tú');
});
```

`tests/barrido.spec.ts`:

```ts
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

const datos = JSON.parse(readFileSync('tests/fixtures/datos.json', 'utf-8'));
const slug = (id: string) => id.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const rutas = ['/', '/sobre/', ...datos.partidos.map((p: any) => `/partido/${slug(p.id)}/`)];

test('en un móvil de 390 px ninguna página desborda en horizontal, ni con «Juzga tú» abierto', async ({ page }) => {
  for (const r of rutas) {
    await page.goto(r);
    await page.locator('details').evaluateAll((ds) => ds.forEach((d) => ((d as HTMLDetailsElement).open = true)));
    const ancho = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(ancho, r).toBeLessThanOrEqual(390);
  }
});

test('ningún texto nuestro lleva rayas (las citas y los títulos oficiales se copian tal cual)', async ({ page }) => {
  for (const r of rutas) {
    await page.goto(r);
    const texto = await page.evaluate(() => {
      const b = document.body.cloneNode(true) as HTMLElement;
      b.querySelectorAll('.cita, .votacion').forEach((e) => e.remove());
      return b.textContent ?? '';
    });
    expect(texto, r).not.toMatch(/[—–]/);
  }
});
```

`tests/enlaces.spec.ts` (contra internet, solo con `npm run enlaces`):

```ts
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('@red todo enlace de un veredicto firme responde', async ({ request }) => {
  test.setTimeout(30 * 60_000);
  const d = JSON.parse(readFileSync('data/datos.json', 'utf-8'));
  const V = new Map(d.votaciones.map((v: any) => [v.id, v]));
  const P = new Map(d.promesas.map((p: any) => [p.id, p]));
  const urls = new Set<string>();
  for (const c of d.cruces.filter((x: any) => x.nivel === 'veredicto')) {
    const v: any = V.get(c.votacion_id), p: any = P.get(c.promesa_id);
    for (const u of [p.url_programa_pagina, v.url_sesion, v.url_bocg, v.url_boe]) if (u) urls.add(u.split('#')[0]);
  }
  const rotos: string[] = [];
  for (const u of urls) {
    const r = await request.get(u, { maxRedirects: 5, failOnStatusCode: false, timeout: 60_000 }).catch(() => null);
    if (!r || r.status() >= 400) rotos.push(`${r?.status() ?? 'sin respuesta'} ${u}`);
  }
  expect(rotos, rotos.join('\n')).toEqual([]);
});
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `npx playwright test tests/sobre.spec.ts tests/barrido.spec.ts`
Expected: FAIL (no existe `/sobre/`).

- [ ] **Step 3: Implementar la página**

`src/pages/sobre.astro`:

```astro
---
import Base from '../layouts/Base.astro';
import { datos, fecha } from '../lib/datos';
import { FIRMA, REPO_MOTOR, REPO_WEB } from '../lib/config';
const m = datos.meta;
const programas = datos.partidos.filter((p) => p.programa_2023);
const firmes = datos.cruces.filter((c) => c.nivel === 'veredicto').length;
const juzga = datos.cruces.filter((c) => c.nivel === 'juzga_tu').length;
---
<Base titulo="Sobre este proyecto">
  <h1>Sobre este proyecto</h1>

  <h2>Quién y por qué</h2>
  <p>Lo hice yo, {FIRMA}, para votar el 29 de noviembre con datos y no con simpatías, y lo comparto con mi gente
    para que puedan hacer lo mismo. No tiene afiliación, ni financiación, ni publicidad. No dice a quién votar ni
    ordena a los partidos de mejor a peor: ordenar ya sería opinar.</p>

  <h2>En qué se basa</h2>
  <ul>
    <li><a href="https://www.congreso.es/es/opendata/votaciones" rel="noopener">Votaciones del Congreso</a>: el voto de cada diputado en cada votación del pleno de la XV legislatura, desde el {fecha(m.periodo.desde)} hasta el {fecha(m.periodo.hasta)}.</li>
    <li><a href="https://www.congreso.es/es/opendata/iniciativas" rel="noopener">Iniciativas del Congreso</a>: el texto de cada ley o proposición en el Boletín Oficial de las Cortes Generales.</li>
    <li><a href="https://www.boe.es/datosabiertos/" rel="noopener">BOE</a>: las leyes y decretos que se llegaron a publicar.</li>
    <li>Los programas electorales de 2023 de cada partido:
      {programas.map((p, i) => <>{i > 0 && ', '}<a href={p.programa_2023!} rel="noopener">{p.nombre}</a></>)}.</li>
    <li><a href="https://www.juntaelectoralcentral.es/cs/jec/documentos/GENERALES_2023_TCuentas_Resoluci%C3%B3n.pdf" rel="noopener">Informe del Tribunal de Cuentas</a> sobre la contabilidad de la campaña de 2023.</li>
  </ul>

  <h2>Cómo se hizo, paso a paso</h2>
  <ol>
    <li>De cada programa se sacaron las promesas una a una, con su cita literal y su página. Si la cita no aparece tal cual en el programa, la promesa se descarta.</li>
    <li>Para cada votación se buscan las promesas que más se le parecen en cada programa.</li>
    <li>Tres modelos de inteligencia artificial de empresas distintas (DeepSeek, OpenAI y Google) leen la promesa y el título de la iniciativa, <strong>sin saber cómo votó nadie</strong>, y dicen si la promesa está a favor o en contra de lo que se vota. Cada uno lo hace dos veces y solo cuenta lo que repite.</li>
    <li>El veredicto no lo da la inteligencia artificial: sale de comparar esa postura con el voto real del partido. A favor y votó Sí, cumple; a favor y votó No, incumple. En una enmienda de devolución, el voto se invierte. Una abstención nunca da veredicto.</li>
    <li>Solo es veredicto firme cuando los tres coinciden, la votación decide exactamente lo prometido y el partido no votó dividido. Si no, va a «Juzga tú», con las mismas pruebas y sin veredicto.</li>
    <li>Un «incumple» solo se publica como firme si lo he revisado a mano y lo marca así («Revisado a mano»). El resto se queda en «Juzga tú».</li>
  </ol>

  <h2>Cuánto acierta</h2>
  <p>Sin maquillar. Las primeras pruebas acertaban el 64 % de lo que publicaban. Con la configuración final, 19 de 19
    casos revisados a mano salieron bien. En la revisión de una muestra antes de publicar, 4 de 11 «incumple» salían
    al revés: el sistema se rehízo para que la inteligencia artificial no viera los votos. Después, 5 de 11 «incumple»
    seguían siendo dudosos, porque la máquina solo ve el título de la iniciativa y no su contenido: por eso un
    «incumple» solo se publica revisado a mano. Hoy hay {firmes} veredictos firmes y {juzga} casos de «Juzga tú».</p>

  <h2>Qué no mide y por qué</h2>
  <ul>
    <li>La corrupción: no hay una fuente oficial completa y neutral. Los titulares eligen qué contar.</li>
    <li>El texto completo de las leyes: con él, los modelos que usamos empeoraban.</li>
    <li>Los partidos sin programa propio en 2023: lo decimos en su ficha en lugar de atribuirles uno.</li>
    <li>Lo que se negocia fuera del pleno: solo cuenta lo que se vota.</li>
  </ul>

  <h2>Cómo comprobar cualquier dato</h2>
  <p>Cada caso lleva su cita literal, la página del programa, la votación del Congreso y, si existe, el boletín oficial.
    Lo que respondió cada juez está en «Qué dijo cada juez». El código es público: el
    <a href={REPO_MOTOR} rel="noopener">motor que recoge y cruza los datos</a> y
    <a href={REPO_WEB} rel="noopener">esta web</a>, con las instrucciones exactas que reciben los jueces.</p>

  <p class="aviso">Última actualización: {fecha(m.generado)}.</p>
</Base>
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `npx playwright test`
Expected: todo en verde (la de `@red` no se ejecuta).

- [ ] **Step 5: Comprobar los enlaces reales una vez**

Run: `npm run enlaces`
Expected: PASS. Si algún enlace falla, se anota cuál y por qué en el ledger (un servidor que rechaza robots no es un enlace roto: se abre a mano para confirmarlo).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: pagina sobre este proyecto, barrido movil y comprobacion de enlaces"
```

---

### Task 5: Motor: ejecución nocturna `noche` (exporta, avisa y publica)

**Files (repo `poligrafo-es`, rama `feat/web-29n`):**
- Modify: `electoral.py`, `src/electoral/exportar.py`, `src/electoral/db.py`, `schema/datos.schema.json`
- Create: `src/electoral/noche.py`
- Test: `tests/electoral/test_noche.py`

**Interfaces:**
- Consumes: subcomandos existentes `descargar`, `fuentes`, `juzgar`, `exportar`; `src.publisher.send_message(token, channel_id, text)`.
- Produces: `python electoral.py noche --web <clon de poligrafo-web> [--zips D] [--iniciativas F] [--boe F] [--tope 0.3] [--salida datos.json] [--salud noche.json]`; campo de contrato `cruces[].pendiente_revision: bool`; `VERSION_CONTRATO = "1.1.0"`; archivo de salud `{"written_at": iso, "publicado": bool, "avisos": int, "error": str|null}`; tabla `avisos(votacion_id, promesa_id, partido, PRIMARY KEY(...))`; variable de pruebas `ELECTORAL_AVISOS_FALSO=<archivo>` (añade un JSON por línea en lugar de enviar a Telegram).

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/electoral/test_noche.py`:

```python
"""La ejecución nocturna: votaciones nuevas → juicio → datos.json → aviso de «incumple» → push a la web."""
import json
import os
import subprocess
import sys
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"
RAIZ = Path(__file__).resolve().parents[2]


def _git(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


def _web(tmp_path):
    """Un remoto desnudo y su clon: hace de poligrafo-web."""
    remoto = tmp_path / "remoto.git"
    _git("init", "--bare", "-b", "main", str(remoto), cwd=tmp_path)
    clon = tmp_path / "web"
    _git("clone", str(remoto), str(clon), cwd=tmp_path)
    _git("config", "user.email", "t@t", cwd=clon)
    _git("config", "user.name", "t", cwd=clon)
    (clon / "README.md").write_text("web", encoding="utf-8")
    _git("add", "-A", cwd=clon)
    _git("commit", "-m", "inicio", cwd=clon)
    _git("push", "origin", "main", cwd=clon)
    return remoto, clon


def _noche(tmp_path, zips, web, avisos, **env):
    entorno = {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), "LLM_FALSO_TODOS": "1",
               "ELECTORAL_AVISOS_FALSO": str(avisos), **env}
    db = tmp_path / "electoral.db"
    if not db.exists():
        for args in (["ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf")], ["extraer"]):
            subprocess.run([sys.executable, str(RAIZ / "electoral.py"), *args, "--db", str(db)], cwd=RAIZ, env=entorno, check=True)
    return subprocess.run([sys.executable, str(RAIZ / "electoral.py"), "noche", "--zips", zips, "--web", str(web),
                           "--iniciativas", str(FIX / "iniciativas_muestra.json"), "--boe", str(FIX / "boe_muestra.json"),
                           "--salida", str(tmp_path / "datos.json"), "--salud", str(tmp_path / "noche.json"), "--db", str(db)],
                          cwd=RAIZ, env=entorno, capture_output=True, text=True, encoding="utf-8")


def test_la_noche_publica_datos_json_en_la_web(tmp_path, zips):
    remoto, clon = _web(tmp_path)
    r = _noche(tmp_path, zips, clon, tmp_path / "avisos.jsonl")
    assert r.returncode == 0, r.stderr
    publicado = json.loads(_git("show", "main:data/datos.json", cwd=remoto))
    assert publicado["meta"]["version_contrato"].startswith("1.")
    salud = json.loads((tmp_path / "noche.json").read_text(encoding="utf-8"))
    assert salud["publicado"] is True and salud["error"] is None


def test_un_incumple_nuevo_se_avisa_una_sola_vez(tmp_path, zips):
    _, clon = _web(tmp_path)
    avisos = tmp_path / "avisos.jsonl"
    _noche(tmp_path, zips, clon, avisos, LLM_FALSO_POSTURA="en_contra")
    primera = avisos.read_text(encoding="utf-8").splitlines()
    assert primera, "con promesas en contra y votos Sí tiene que haber «incumple» por revisar"
    assert all("Revisar" in json.loads(x)["texto"] for x in primera)
    _noche(tmp_path, zips, clon, avisos, LLM_FALSO_POSTURA="en_contra")
    assert avisos.read_text(encoding="utf-8").splitlines() == primera


def test_si_el_push_falla_la_salud_lo_dice_y_sale_con_error(tmp_path, zips):
    remoto, clon = _web(tmp_path)
    _git("remote", "set-url", "origin", str(tmp_path / "no-existe.git"), cwd=clon)
    r = _noche(tmp_path, zips, clon, tmp_path / "avisos.jsonl")
    assert r.returncode != 0
    salud = json.loads((tmp_path / "noche.json").read_text(encoding="utf-8"))
    assert salud["publicado"] is False and salud["error"]


def test_un_incumple_por_revisar_va_marcado_en_el_contrato(cli, zips):
    entorno = {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), "LLM_FALSO_TODOS": "1",
               "LLM_FALSO_POSTURA": "en_contra"}
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=entorno)
    cli("extraer", env=entorno)
    cli("juzgar", "--k", "3", env=entorno)
    cruces = cli("exportar")["cruces"]
    pendientes = [c for c in cruces if c["pendiente_revision"]]
    assert pendientes and all(c["nivel"] == "juzga_tu" and c["veredicto"] == "incumple" for c in pendientes)
    assert all(not c["pendiente_revision"] for c in cruces if c["veredicto"] == "cumple")
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd "D:/1.Fran/DEV/poligrafo-es" && python -m pytest tests/electoral/test_noche.py -q`
Expected: FAIL (`invalid choice: 'noche'` y falta `pendiente_revision`).

- [ ] **Step 3: Marcar en el contrato los «incumple» por revisar**

En `src/electoral/exportar.py`, `VERSION_CONTRATO = "1.1.0"`, y dentro de `_cruces`, donde hoy se rebaja el «incumple» no revisado:

```python
        pendiente = res == ("veredicto", "incumple") and not revisado
        if pendiente:
            res = ("juzga_tu", "incumple")
```

y en el `dict` del cruce: `"pendiente_revision": pendiente,`.

En `schema/datos.schema.json`, dentro de `cruces.items.properties`: `"pendiente_revision": {"type": "boolean"}` y añadirlo a `required`.

En `src/electoral/db.py`, en el esquema de tablas:

```sql
CREATE TABLE IF NOT EXISTS avisos (
    votacion_id TEXT, promesa_id INTEGER, partido TEXT, fecha TEXT,
    PRIMARY KEY (votacion_id, promesa_id, partido)
);
```

- [ ] **Step 4: Implementar `noche`**

`src/electoral/noche.py`:

```python
"""Ejecución nocturna en la Orange Pi: avisa de los «incumple» por revisar y publica datos.json en poligrafo-web."""
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _enviar(texto: str) -> None:
    falso = os.environ.get("ELECTORAL_AVISOS_FALSO")
    if falso:
        with open(falso, "a", encoding="utf-8") as f:
            f.write(json.dumps({"texto": texto}, ensure_ascii=False) + "\n")
        return
    from dotenv import load_dotenv
    from src.publisher import send_message
    load_dotenv()
    send_message(os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHANNEL_ID"], texto)


def avisar(conn, datos: dict) -> int:
    """Un mensaje por cada «incumple» unánime que aún no está revisado ni avisado."""
    prom = {p["id"]: p for p in datos["promesas"]}
    vots = {v["id"]: v for v in datos["votaciones"]}
    hechos = {(r[0], r[1], r[2]) for r in conn.execute("SELECT votacion_id, promesa_id, partido FROM avisos")}
    n = 0
    for c in datos["cruces"]:
        clave = (c["votacion_id"], c["promesa_id"], c["partido"])
        if not c["pendiente_revision"] or clave in hechos:
            continue
        p, v = prom[c["promesa_id"]], vots[c["votacion_id"]]
        _enviar(f"<b>Revisar «incumple»: {c['partido']}</b>\n{v['fecha']}: {v['expediente'][:300]}\n"
                f"Votó {c['voto']}. Promesa: {p['texto']}\n«{p['cita']}» ({p['url_programa_pagina']})\n"
                f"Para confirmarlo: añadir {json.dumps(dict(zip(('votacion_id', 'promesa_id', 'partido'), clave)) | {'veredicto': 'incumple'}, ensure_ascii=False)} "
                f"a config/revision_manual.json")
        conn.execute("INSERT INTO avisos VALUES (?,?,?, datetime('now'))", clave)
        conn.commit()
        n += 1
    return n


def publicar(datos_json: Path, web: Path) -> None:
    """Copia datos.json al clon de poligrafo-web y hace push. Nunca fuerza: si el remoto cambió, falla."""
    destino = web / "data" / "datos.json"
    destino.parent.mkdir(exist_ok=True)
    shutil.copyfile(datos_json, destino)
    git = lambda *a: subprocess.run(["git", *a], cwd=web, capture_output=True, text=True, check=True)
    git("add", "data/datos.json")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=web).returncode != 0:
        git("commit", "-m", f"datos: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    git("push", "origin", "HEAD")


def escribir_salud(ruta: Path, publicado: bool, avisos: int, error: str | None) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "publicado": publicado, "avisos": avisos, "error": error}, ensure_ascii=False),
                    encoding="utf-8")
```

En `electoral.py`, importar `noche` junto a los demás módulos (`from src.electoral import exportar, fuentes, juez, noche, programas, votaciones`) y añadir:

```python
def cmd_noche(a, conn):
    """Pasos del motor y, al final, aviso y publicación. La salud se escribe siempre, también si algo falla."""
    avisos, error = 0, None
    try:
        main(["descargar", *(["--zips", a.zips] if a.zips else []), "--db", a.db])
        main(["fuentes", *(["--iniciativas", a.iniciativas] if a.iniciativas else []),
              *(["--boe", a.boe] if a.boe else []), "--db", a.db])
        main(["juzgar", "--tope", str(a.tope), "--db", a.db])
        main(["exportar", "--salida", a.salida, "--db", a.db])
        datos = json.loads(Path(a.salida).read_text(encoding="utf-8"))
        avisos = noche.avisar(conn, datos)
        noche.publicar(Path(a.salida), Path(a.web))
    except Exception as e:                       # la salud lo cuenta y ARGUS avisa
        error = f"{type(e).__name__}: {getattr(e, 'stderr', '') or e}"[:500]
    noche.escribir_salud(Path(a.salud), error is None, avisos, error)
    if error:
        raise SystemExit(f"noche: {error}")
```

y en `main`, añadir `"noche"` a la tupla de subcomandos, sus argumentos y su entrada en el diccionario:

```python
    sub.choices["noche"].add_argument("--web", required=True, help="clon local de poligrafo-web")
    sub.choices["noche"].add_argument("--zips", help="carpeta con ZIPs ya bajados (pruebas)")
    sub.choices["noche"].add_argument("--iniciativas")
    sub.choices["noche"].add_argument("--boe")
    sub.choices["noche"].add_argument("--tope", type=float, default=0.3)
    sub.choices["noche"].add_argument("--salida", default=str(RAIZ / "datos.json"))
    sub.choices["noche"].add_argument("--salud", default=str(RAIZ / "electoral_data" / "noche.json"))
```

```python
     "exportar": cmd_exportar, "noche": cmd_noche}[a.cmd](a, conn)
```

- [ ] **Step 5: Ejecutar y ver que pasa, y la suite entera**

Run: `python -m pytest tests/electoral/test_noche.py -q` y después `python -m pytest -q`
Expected: 4 passed; suite completa en verde (179 + 4).

- [ ] **Step 6: Commit**

```bash
git add electoral.py src/electoral/noche.py src/electoral/exportar.py src/electoral/db.py schema/datos.schema.json tests/electoral/test_noche.py
git commit -m "feat(electoral): ejecucion nocturna que avisa de incumple por revisar y publica en la web"
```

---

### Task 6: ARGUS vigila la web

**Files (repo `D:\1.Fran\DEV\ARGUS`, rama `feat/poligrafo-web`):**
- Modify: `src/monitor.py` (constantes junto a `MIDAS_HEALTH_FILE`, `CRON_JOBS`, nueva función tras `check_gaming_catalogue`, registro junto a `checks.append(check_gaming_catalogue())`)
- Test: `tests/test_monitor_poligrafo.py`

**Interfaces:**
- Consumes: archivo de salud de la Tarea 5 en `/root/projects/poligrafo-es/electoral_data/noche.json`.
- Produces: `check_poligrafo_web(path: Path = POLIGRAFO_NOCHE) -> FailedCheck | None` con nombre `poligrafo:web`; entrada `cron:poligrafo-noche` en `CRON_JOBS`.

- [ ] **Step 1: Escribir la prueba que falla**

`tests/test_monitor_poligrafo.py`:

```python
"""La web del 29N: el cron puede correr y aun así no publicar (push rechazado, clave caducada)."""
import json
from datetime import datetime, timedelta, timezone

from src.monitor import check_poligrafo_web


def _salud(tmp_path, horas, publicado=True, error=None):
    p = tmp_path / "noche.json"
    p.write_text(json.dumps({"written_at": (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat(),
                             "publicado": publicado, "avisos": 0, "error": error}))
    return p


def test_publicacion_reciente_pasa(tmp_path):
    assert check_poligrafo_web(_salud(tmp_path, 3)) is None


def test_publicacion_vieja_avisa(tmp_path):
    fallo = check_poligrafo_web(_salud(tmp_path, 49))
    assert fallo and fallo.name == "poligrafo:web" and "49h" in fallo.diagnostics


def test_push_fallido_avisa_con_el_error(tmp_path):
    fallo = check_poligrafo_web(_salud(tmp_path, 1, publicado=False, error="CalledProcessError: rejected"))
    assert fallo and "rejected" in fallo.diagnostics


def test_sin_archivo_avisa(tmp_path):
    assert check_poligrafo_web(tmp_path / "no.json").name == "poligrafo:web"
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd "D:/1.Fran/DEV/ARGUS" && git checkout -b feat/poligrafo-web && python -m pytest tests/test_monitor_poligrafo.py -q`
Expected: FAIL (`ImportError: cannot import name 'check_poligrafo_web'`).

- [ ] **Step 3: Implementar**

Constantes, junto a `MIDAS_HEALTH_FILE`:

```python
POLIGRAFO_NOCHE = Path("/root/projects/poligrafo-es/electoral_data/noche.json")
POLIGRAFO_MAX_AGE_HOURS = 48  # spec 29N §8: datos.json regenerado en menos de 48 h
```

En `CRON_JOBS`:

```python
    {
        "name": "cron:poligrafo-noche",
        "pattern": "electoral.py noche",
        "log": "/var/log/poligrafo-noche.log",
        "max_age_minutes": 26 * 60,  # diario 23:30
    },
```

Función, tras `check_gaming_catalogue`:

```python
def check_poligrafo_web(path: Path = POLIGRAFO_NOCHE) -> FailedCheck | None:
    """La web del 29N se publica cada noche: archivo de salud viejo, ausente o con push fallido."""
    name = "poligrafo:web"
    try:
        if not path.exists():
            return FailedCheck(name=name, diagnostics=f"{path} no existe: la ejecución nocturna nunca ha corrido.")
        data = json.loads(path.read_text())
        age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(data["written_at"])).total_seconds() / 3600
        if age_h > POLIGRAFO_MAX_AGE_HOURS:
            return FailedCheck(name=name, diagnostics=(
                f"{age_h:.0f}h sin ejecutarse (tolerancia {POLIGRAFO_MAX_AGE_HOURS}h): la web no se actualiza."))
        if not data.get("publicado"):
            return FailedCheck(name=name, diagnostics=f"La última noche no publicó: {data.get('error')}")
    except Exception as e:
        logger.warning("check_poligrafo_web unavailable: %s", e)
    return None
```

Registro, junto a `checks.append(check_gaming_catalogue())`:

```python
    checks.append(check_poligrafo_web())
```

- [ ] **Step 4: Ejecutar y ver que pasa, y la suite de ARGUS**

Run: `python -m pytest -q`
Expected: 4 nuevas en verde y el resto de ARGUS igual que antes.

- [ ] **Step 5: Commit**

```bash
git add src/monitor.py tests/test_monitor_poligrafo.py
git commit -m "feat(poligrafo): vigilar la publicacion nocturna de la web del 29n"
```

---

### Task 7: Publicación (con Fran, paso a paso)

Operación, no código. **Cada paso marcado con ⏸ espera el OK de Fran en ese momento.**

- [ ] **Step 1 ⏸: Merge del motor y de ARGUS en sus ramas principales y push**

```bash
git -C "D:/1.Fran/DEV/poligrafo-es" checkout master && git -C "D:/1.Fran/DEV/poligrafo-es" merge --no-ff feat/web-29n && python -m pytest -q
git -C "D:/1.Fran/DEV/poligrafo-es" push origin master
git -C "D:/1.Fran/DEV/ARGUS" checkout main && git -C "D:/1.Fran/DEV/ARGUS" merge --no-ff feat/poligrafo-web && git -C "D:/1.Fran/DEV/ARGUS" push origin main
```

(Comprobar antes el nombre real de la rama principal de ARGUS con `git -C D:/1.Fran/DEV/ARGUS branch -a`.)

- [ ] **Step 2 ⏸: Crear el repo público `poligrafo-web` y subirlo**

Antes, auditoría: `git -C "D:/1.Fran/DEV/poligrafo-web" log -p | grep -iE "api[_-]?key|token|sk-or-|secret"` → sin resultados.

```bash
cd "D:/1.Fran/DEV/poligrafo-web" && gh repo create Ufransa/poligrafo-web --public --source . --push --description "Web de PolígrafoES 29N: promesas de 2023 frente a votos de la XV legislatura"
```

- [ ] **Step 3: Preparar la Orange Pi** (sesión `orange-pi`)

```bash
cd /root/projects/poligrafo-es && git pull && pip3 install -r requirements.txt   # usar el mismo modo de instalación que ya tenga la Pi
ssh-keygen -t ed25519 -f ~/.ssh/poligrafo_web -N "" -C orange-pi-poligrafo-web
printf 'Host github-poligrafo-web\n  HostName github.com\n  User git\n  IdentityFile ~/.ssh/poligrafo_web\n  IdentitiesOnly yes\n' >> ~/.ssh/config
cat ~/.ssh/poligrafo_web.pub
```

Desde el PC, con la clave pública copiada a un archivo temporal del scratchpad:
`gh repo deploy-key add <archivo.pub> --repo Ufransa/poligrafo-web --allow-write --title orange-pi`

En la Pi:

```bash
git clone git@github-poligrafo-web:Ufransa/poligrafo-web.git /root/projects/poligrafo-web
git -C /root/projects/poligrafo-web config user.name "PolígrafoES (Orange Pi)"
git -C /root/projects/poligrafo-web config user.email "poligrafo@orange-pi.local"
```

- [ ] **Step 4: Copiar la base y los ZIP a la Pi, y la clave de OpenRouter sin que pase por el chat**

En el PC: `tar czf <scratchpad>/electoral.tgz -C "D:/1.Fran/DEV/poligrafo-es" electoral.db electoral_data/zips config/revision_manual.json`, subirlo con `mcp__orange-pi__ssh_upload` y descomprimirlo en `/root/projects/poligrafo-es`.

Clave: `grep '^OPENROUTER_API_KEY=' D:/1.Fran/DEV/poligrafo-es/.env > <scratchpad>/k.env` (sin imprimirla), subirla, en la Pi `grep -q OPENROUTER_API_KEY .env || cat /tmp/k.env >> .env; rm /tmp/k.env`, y borrar la copia local.

- [ ] **Step 5: Primera ejecución a mano en la Pi**

```bash
cd /root/projects/poligrafo-es && python3 electoral.py noche --web /root/projects/poligrafo-web >> /var/log/poligrafo-noche.log 2>&1; tail -20 /var/log/poligrafo-noche.log; cat electoral_data/noche.json
```

Expected: `"publicado": true`, un commit `datos: ...` nuevo en `Ufransa/poligrafo-web`, gasto de unos céntimos.

- [ ] **Step 6 ⏸: Cloudflare Pages (lo hace Fran, con guía)**

En dash.cloudflare.com: *Workers & Pages* → *Create* → *Pages* → *Connect to Git* → `Ufransa/poligrafo-web`. Nombre del proyecto: `poligrafo-29n`. *Framework preset*: Astro. *Build command*: `npm run build`. *Output*: `dist`. Variable de entorno: `NODE_VERSION = 22`. Guardar y desplegar.
Comprobar: `https://poligrafo-29n.pages.dev/` carga en el móvil de Fran.

- [ ] **Step 7 ⏸: Cron en la Pi y ARGUS desplegado**

```bash
(crontab -l; echo '30 23 * * * cd /root/projects/poligrafo-es && python3 electoral.py noche --web /root/projects/poligrafo-web >> /var/log/poligrafo-noche.log 2>&1') | crontab -
cd /root/projects/ARGUS && git pull && systemctl restart argus
```

(Comprobar el nombre real del servicio de ARGUS con `systemctl list-units | grep -i argus`.) Invocar la skill `/deploy` para actualizar `Server Orange Pi.md`.

- [ ] **Step 8: Comprobación final y vault**

`npm run enlaces` contra los datos publicados; repaso visual de Fran en su móvil; actualizar `01_PROYECTOS/poligrafo-es.md` (casilla del plan 2, dirección, cron) y `CLAUDE.md` del vault (línea de PolígrafoES: cron `noche` 23:30 y repo `poligrafo-web`), proponiendo antes a Fran los cambios de estado.

- [ ] **Step 9 ⏸: Fran decide cuándo manda el enlace a sus allegados.**
