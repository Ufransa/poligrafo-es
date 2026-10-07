# PolígrafoES 29N: web de promesas frente a votos (diseño)

> Fecha: 2026-10-07. Elecciones generales el **domingo 29 de noviembre de 2026** (convocadas el 5 de octubre).
> Estado: diseño acordado con Fran por secciones. Pendiente de revisión de este documento.

## 1. Objetivo

Que Fran vote el 29N satisfecho y basándose en **cifras comprobables, no en predisposición política**, y que
pueda compartir la misma herramienta con sus allegados (unas 100 personas, poco tecnológicas) para que
también lo intenten.

**Criterio de éxito:** cada afirmación de la web se puede rastrear hasta una fuente oficial (Congreso, BOE,
programa electoral, Tribunal de Cuentas), y los veredictos publicados aciertan en la muestra de control que
Fran revisa antes de publicar.

**No es un producto de medios.** No busca audiencia, ni monetización, ni crecimiento. Es una herramienta
personal con enlace compartido.

## 2. Decisiones cerradas

| Tema | Decisión | Motivo |
|---|---|---|
| Periodo de votos y promesas | Solo la XV legislatura (desde agosto de 2023) | Igual para todos; «los errores del padre no juzgan al hijo» |
| Partidos | Todo partido con escaño en la XV, más los que las encuestas den con opciones el 29N (p. ej. SALF) | Regla objetiva, no elegida a dedo |
| Qué es «cumplir» | Dos capas: coherencia de voto (todos, comparable) y «lo que hicieron gobernando» (solo PSOE y Sumar, aparte) | Gobierno y oposición no pueden cumplir lo mismo |
| Veredicto o evidencia | Veredicto solo si es claro; si no, evidencia con «juzga tú» | Prefiero pocos veredictos buenos a muchos dudosos |
| Promesas principales | Criterio medible: los temas a los que cada partido dedica más espacio en su programa | Lo decide el partido con su espacio, no nosotros |
| Corrupción | **Aparcada** | No hay una fuente de verdad fiable: los titulares tienen sesgo de selección y el CENDOJ anonimiza |
| Finanzas | Solo la campaña del 23J (gasto y subvención) y el cumplimiento de transparencia del Tribunal de Cuentas | Lo único oficial que cae dentro del periodo |
| Acceso | Web estática pública en Cloudflare Pages, sin login, `noindex`, repositorio privado | Gente poco tecnológica; un enlace por WhatsApp |
| LLM | Máximo **10 € en total**, **ningún modelo de Anthropic**, todo vía OpenRouter | Restricción de Fran |
| Ranking entre partidos | **No** | Ordenar de mejor a peor ya es opinar |

Si en el futuro se retoma la corrupción, lo único que se acerca a una fuente fiable son las **condenas firmes**
anunciadas por los propios tribunales.

## 3. Evidencia: pruebas previas (2026-10-05 a 2026-10-07)

| Prueba | Resultado |
|---|---|
| 1. Volumen y coste | 146 días de pleno, 2.175 votaciones, **660 expedientes**. Unos 0,24 $ por cada 50 expedientes con la configuración final |
| 2. Jueces | Bloques de página con modelos ultrabaratos: 64 % de acierto en lo publicado. Promesas sueltas: 74 %. **Configuración final, con los 3 jueces de acuerdo: 19/19 correctos** (9 en ajuste y 10 en validación ciega), **revisados y confirmados por Fran** |
| 3. Texto de la ley | El bloque completo mejora mucho. Añadir el texto entero de la ley **empeora** a los modelos baratos: se vuelven demasiado prudentes y pierden veredictos correctos |
| 4. Reparto de candidatos | El método actual sobrerrepresenta a los programas cortos (EH Bildu, 15× más que Sumar). El top global sobrerrepresenta al PSOE. **La normalización por programa (z-score) es la más equilibrada** |

**Causa raíz de los errores de la v3:** el juez solo leía los primeros 600 caracteres de bloques de unos 3.200
(`llm.py`: `c['text'][:600]`), y esos bloques mezclaban unas diez propuestas.

**Otros hallazgos:**
- El XML del Congreso trae `<Diputado>` en cada voto, así que el Grupo Mixto se puede desglosar por partido.
- Las votaciones de «debate de totalidad» tienen subtipos de sentido opuesto: en la **devolución**, Sí es tumbar
  la ley; en el **texto alternativo**, Sí es apoyar otro texto.
- Un decreto-ley tiene dos votaciones: la convalidación decide; la «tramitación como proyecto de ley» es trámite.

## 4. Arquitectura

```
UNA VEZ (PC de Fran)                 CADA NOCHE (Orange Pi)              SIEMPRE
────────────────────                 ──────────────────────              ───────
Legislatura completa        ──►      Votaciones nuevas, programas  ──►   Cloudflare Pages
Promesas, temas, veredictos  copia   2026 bajo demanda              push  (repo poligrafo-web)
Exporta datos.json          a la Pi  Regenera datos.json
```

- **`poligrafo-es`** (repo actual) es el **motor**. El bot de Telegram sigue como está hasta después del 29N.
- **`poligrafo-web`** (repo privado nuevo) solo lee `datos.json` y genera una web estática.
- **`datos.json`** es el contrato entre los dos. Lleva versión.

## 5. El motor

1. **Votaciones.** Descarga de los ZIP de sesión (calendario `diasVotaciones` de la página de open data + `targetDate`).
   Se guarda **el voto de cada diputado**. Una tabla `diputado → partido` con fechas de alta y baja resuelve el
   Mixto (Podemos, BNG, CC, UPN, Compromís) y los cambios de grupo (Ortega Smith, Ábalos).
2. **Clasificación de la votación.**
   - Trámite (avocación, prórroga, lectura única, tramitación como proyecto de ley): se excluye.
   - Decreto-ley: cuenta la convalidación.
   - Devolución o texto alternativo: aviso explícito del sentido del voto al juez, con el grupo que presenta la enmienda.
   - Se pasa al juez el campo `TextoSubGrupo` («qué se vota exactamente»).
3. **Promesas.** Extracción con `deepseek-v4-flash` de cada bloque de programa → promesas sueltas con
   `promesa` (castellano, autocontenida), `cita` literal, página y **tema** de una lista fija (§5.1). Cuentan
   también los compromisos de mantener u oponerse. Se marcan y excluyen los logros pasados, los paraguas y las
   **promesas de procedimiento** («limitaremos el uso del real decreto-ley»).
4. **Candidatos.** Embeddings `multilingual-e5-small`. Top 20 por similitud **normalizada por programa** (z-score).
5. **Juez.** Tres modelos de familias distintas: `deepseek/deepseek-v4-pro`, `openai/gpt-5-mini` y
   `google/gemini-2.5-flash-lite`. Razonamiento desactivado o al mínimo. Cada uno pasa dos veces; solo cuenta lo
   que coincide en sus dos pasadas. Cada cruce lleva `veredicto` (cumple / incumple) y `fuerza` (directa / indirecta).
   - **Veredicto publicado:** los 3 jueces coinciden, con relación directa.
   - **«Juzga tú»:** 2 de 3 coinciden. Se muestra sin veredicto.
   - Lo demás no se muestra.
6. **Coherencia.** Sin LLM: pares de votos opuestos del mismo partido sobre la misma materia, y su patrón
   estando en el Gobierno frente a estando en la oposición.
7. **Gobierno.** Para PSOE y Sumar: cruces con veredicto «cumple» cuya votación aprueba una ley o convalida un
   decreto, con su enlace al BOE.
8. **Finanzas.** Carga manual desde los informes del Tribunal de Cuentas (campaña del 23J y transparencia).
9. **Exportación** a `datos.json` (§6).

### 5.1 Temas (lista fija, igual para todos los programas y años)

Vivienda · Inmigración · Sanidad · Educación · Empleo y trabajo · Pensiones · Fiscalidad · Economía e
industria · Energía y clima · Agricultura y medio rural · Justicia · Seguridad e interior · Organización
territorial · Igualdad y derechos sociales · Política exterior y defensa · Instituciones y calidad democrática ·
Cultura y lengua.

El tema lo asigna el extractor. «Principales» = la promesa más representativa de cada uno de los 10 temas con
más promesas en ese programa. El reparto por temas (en %) se muestra para 2023 y, cuando exista, para 2026.

### 5.2 Programas

- **Con programa propio en 2023:** PP, PSOE, Sumar, Vox, ERC, Junts, EH Bildu, PNV (ya cargados), BNG, CC y UPN (por cargar).
- **Sin programa propio en 2023:** Podemos y Compromís concurrieron dentro de Sumar; SALF no existía. Para ellos
  hay votos (Podemos y Compromís), pero sus promesas de 2023 son las de Sumar. **La web lo dice explícitamente**
  en lugar de atribuirles un programa que no fue suyo.
- **2026:** se cargan bajo demanda cuando cada partido publique (`ingest-programa 2026 <partido> <url>`).

## 6. Contrato: `datos.json`

| Bloque | Contenido |
|---|---|
| `meta` | versión del contrato, fecha de generación, periodo cubierto, modelos usados, recuentos, URL de la metodología |
| `partidos` | id, nombre, siglas, grupo, escaños, periodos en el Gobierno, URL del programa de 2023 (o el motivo de que no haya) |
| `votaciones` | id, fecha, tipo, subtipo, resumen en lenguaje llano, resultado, URL del Congreso, voto por partido (+ si votó dividido), `excluida_tramite` |
| `promesas` | id, partido, año, texto, cita, página, tema, `principal` |
| `cruces` | promesa, votación, voto del partido, `nivel` (`veredicto` / `juzga_tu`), veredicto, respuesta de cada juez |
| `coherencia` | por partido: pares de votos opuestos; patrón Gobierno / oposición |
| `gobierno` | solo PSOE y Sumar: cruces materializados en una ley o un decreto, con la URL del BOE |
| `temas` | por partido y año: porcentaje de promesas por tema |
| `finanzas` | por partido: gasto y subvención de campaña 2023, cumplimiento de transparencia, URL del informe |
| `programas_2026` | estado por partido (`pendiente` / `cargado`) |

**Reglas del contrato:**
1. Todo dato lleva su URL de fuente.
2. Cada cruce guarda lo que dijo cada juez.
3. El contrato no lleva colores, orden ni textos valorativos. Eso lo decide la web.

## 7. La web

Tres pantallas, móvil primero, sin jerga:

1. **Portada, «Los partidos».** Fichas ordenadas por escaños (sin escaño: al final, en orden alfabético). En cada
   una: veredictos, cuántos cumple e incumple, y coherencia. Arriba: *«Aquí no te decimos a quién votar. Te
   enseñamos lo que prometieron y lo que votaron.»*
2. **Ficha de partido.** Promesas principales con su estado; promesa → votación → voto con cita y enlace oficial;
   «A qué dedica su programa» (temas en %, 2023 y 2026); coherencia; «Lo que hicieron gobernando» (solo PSOE y
   Sumar, en una sección aparte); dinero; «Juzga tú» plegado por defecto.
3. **«Cómo funciona».** Fuentes, qué es un veredicto y por qué exige tres jueces, qué no se mide (corrupción y
   por qué) y fecha de la última actualización.

**No lleva:** ranking ni comparador de «mejores», comentarios ni nada social. Los colores de partido no son
protagonistas; se decide con las propuestas visuales.

**Diseño visual:** 2 o 3 propuestas con **Claude Design** sobre datos de ejemplo, antes de construir. Fran elige.

**Tecnología:** web estática generada a partir del JSON. Recomendación: **Angular con prerenderizado estático**,
porque es lo que Fran domina y mantendrá. Alternativa más ligera: Astro. *(Confirmar en la revisión de este documento.)*

## 8. Operación

- **Carga inicial** en el PC de Fran. Al terminar, **muestra al azar de 30 veredictos** para que Fran la revise;
  sin su aprobación no se publica nada.
- **Orange Pi, cada noche:** votaciones nuevas → `datos.json` → push a `poligrafo-web` → Cloudflare Pages.
- **ARGUS:** vigila que `datos.json` se haya regenerado en menos de 48 horas.
- **Gasto:** tope por ejecución en el código, más el límite de la clave en OpenRouter. Estimación de la carga
  completa: unos 3,5 $. Gastado en las pruebas: 1,06 $. **Subir el límite de la clave de 5 $ a unos 10 $.**

## 9. Pruebas

Según las reglas de Fran: de comportamiento, nunca unitarias. Playwright para la web.

- **Web (Playwright):**
  - Portada con todos los partidos en orden de escaños.
  - Todo veredicto visible tiene cita y enlace que responde.
  - «Juzga tú» empieza plegado.
  - Sin desbordes horizontales en un móvil.
- **Motor** (XML reales guardados como referencia):
  - Una avocación sale excluida.
  - Una devolución invierte el sentido del voto.
  - Un texto alternativo no se trata como devolución.
  - Un diputado del Mixto se asigna a su partido.
  - `datos.json` cumple el contrato.
- **Calidad:** los 19 casos revisados por Fran son la **referencia fija**. Un cambio de modelo o de instrucciones
  que empeore el acierto sobre ellos no se despliega.

## 10. Calendario

| Semana | Trabajo |
|---|---|
| 7-13 oct | Motor: voto por diputado, clasificación de votaciones, extracción con temas, programas de BNG, CC y UPN |
| 14-20 oct | Carga completa, revisión de los 30 de Fran, coherencia, gobierno, finanzas, `datos.json` |
| 21-27 oct | Propuestas con Claude Design, elección de Fran, construcción de la web |
| 28 oct-3 nov | Playwright, Cloudflare Pages, cron en la Pi, ARGUS. **Publicación** |
| Noviembre | Programas de 2026 según se publiquen; campaña del 13 al 27; elecciones el 29 |

## 11. Fuera de alcance (trabajo futuro)

- Corrupción (ver §2).
- Juez con el texto completo de la ley (empeora con los modelos actuales; reevaluar con modelos mejores).
- Cuentas anuales completas de los partidos (desfase de unos 4 años).
- Cruce «prometen en 2026 X, pero votaron contra X en la XV»: va **después** de cargar los programas de 2026,
  con el mismo juez.

## 12. Riesgos

| Riesgo | Mitigación |
|---|---|
| Pocos veredictos firmes (≈130 estimados) | Es el precio de la precisión; la capa «juzga tú» aporta volumen con honestidad |
| Los programas de 2026 llegan tarde | La web funciona sin ellos; el bloque aparece como «pendiente» |
| Un error visible daña la confianza de los allegados | Muestra de 30 revisada antes de publicar; cada veredicto lleva su fuente; página «Cómo funciona» |
| Cambios de grupo de diputados mal asignados | Tabla con fechas de alta y baja, y prueba con un caso real |
| OpenRouter cambia precios o modelos | Modelos configurables; la referencia fija detecta pérdidas de calidad |
