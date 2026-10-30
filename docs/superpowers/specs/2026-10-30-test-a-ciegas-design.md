# PolígrafoES 29N: test a ciegas (diseño)

> Fecha: 2026-10-30. Elecciones generales el **domingo 29 de noviembre de 2026**. Los programas de 2026 se
> esperan para el **13-11**; el test debe estar publicado **antes del 15-11**.
> Estado: diseño acordado con Fran en conversación. Pendiente de revisión de este documento.
> Especificación madre: `2026-10-07-web-electoral-29n-design.md`.

## 1. Objetivo

Que quien entre en la web pueda **votar propuestas de los programas de 2026 sin saber de qué partido son**,
juzgándolas por su contenido y por lo que haría falta para llevarlas a cabo, y que al final vea de quién era
cada una.

Lo que lo distingue de un test de afinidad cualquiera:

1. **El resumen dice lo crítico de la propuesta**, no el titular. «Bajar impuestos» no vale; vale «bajar el IRPF
   a las rentas de menos de 30.000 € y compensarlo subiendo el impuesto de sociedades», si el programa lo dice.
2. **Las condiciones se ven antes de votar**: qué mayoría necesita, si depende de Europa, si es competencia de
   las comunidades, si necesita Presupuestos. Si no la puede aprobar España por sí sola, se explica por qué y se
   enlaza la norma.
3. **Al destapar**, si el partido ya lo prometió en 2023, se dice cómo votó en la XV legislatura.

**Criterio de éxito:** (a) el adivinador no acierta el partido de los resúmenes publicados mucho más que el azar
(§5.4); (b) ninguna condición publicada es jurídicamente falsa (revisión de Fran); (c) toda propuesta enlaza a
su página del programa y toda condición a su norma.

## 2. Decisiones cerradas (Fran, 2026-10-30)

| Tema | Decisión |
|---|---|
| Resultado | **Sin recuento por partido.** Se destapa propuesta a propuesta. Fran: «te da a ti tu resultado y ahí muere» |
| Persistencia | **Nada se guarda**: ni servidor, ni `localStorage`, ni cookies, ni analítica. Recargar es empezar de cero |
| Programas | **Solo 2026.** Los de 2023 sirven únicamente para probar el sistema antes del 13-11 |
| Partidos | Todos los que publiquen programa de 2026. En la prueba de 2023, los que tienen programa (los 9 cargados) |
| Volumen por partido | No se iguala ni se rellena: quien presenta menos propuestas sale menos. La selección pone un **tope** de 3 por partido y tema (§5.1), no un mínimo (Fran aprobó el plan de ~150 propuestas) |
| Temas | **Los elige el usuario** |
| Voto | **Sí / No** |
| Condiciones | **Visibles antes de votar.** Si es inviable, explicar por qué |
| Propuestas vagas | **Se enseñan marcadas «sin concreción»** (Fran eligió la opción b) |
| Destape con 2023 | **Sí**, cuando exista un cruce firme de esa promesa en 2023 |
| Neutralidad | **Se mide**: un modelo distinto intenta adivinar el partido; si acierta, se reescribe |
| Revisión | **Fran revisa a mano** todo lo que se publica (resumen y condiciones). Tiene tiempo el 13 y el 14 |
| Alcance del lanzamiento | **Opción B**: el 15-11 salen los temas grandes; el resto se añade según Fran revise |
| Código fuente | Puede verse el partido en el código fuente de la página. **No se ofusca** |
| Fuentes | Cada propuesta enlaza al PDF del programa (página y cita literal). Cada condición, a su norma (CE, TFUE, directiva, BOE) |
| Presupuesto LLM | **No se sube el tope de 10 €** (gastado: 5,47 $, de los que 3,96 $ están registrados en `gasto`). Scripts antes que LLM; ahorrar tokens es prioridad |
| LLM | Ningún modelo de Anthropic, todo vía OpenRouter (regla de la especificación madre) |

**Anti-objetivos.** Fallaría aunque funcione si:
- un resumen deja adivinar el partido por su lenguaje;
- un resumen cambia el sentido de la propuesta o se inventa una cifra que el programa no da;
- se publica una condición jurídica falsa (p. ej. «necesita ley orgánica» cuando no);
- la interfaz enseña el partido antes de votar;
- aparece cualquier cifra o ranking por partido;
- algo del usuario sale del navegador.

## 3. Evidencia de partida (informe del especialista, 2026-10-30)

- 5.639 promesas de 2023 publicables, de **una sola acción** cada una, con tema (17 fijos), cita literal y
  página. Es la granularidad correcta para asignar un rango normativo y una competencia a cada una.
- El texto **delata al partido**: citas en catalán (ERC), balance de gestión («como ya hemos hecho con el Mar
  Menor», PSOE), y en Organización territorial y Cultura y lengua el contenido identifica al partido.
- Reparto muy desigual por tema (PP y Vox: 1 promesa de Pensiones cada uno; EH Bildu: 0 de Agricultura).
- Para las condiciones solo se reutiliza `MAYORIA_ABSOLUTA = 176` y `TRES_QUINTOS = 210`
  (`src/electoral/votaciones.py:342-343`) y `resolver_boe` (`src/electoral/fuentes.py:67-88`). Nada de
  competencias, art. 149 CE ni derecho de la UE.
- La web tiene **cero JavaScript** (Astro 7.3.7, `<details>` para plegar). Esta será la primera página interactiva.
- El esquema de `datos.json` (contrato 1.1.0) no prohíbe claves nuevas.
- Coste de referencia: extracción con `deepseek-v4-flash` ≈ 0,00047 $ por bloque.
- **Trampa conocida:** `juzgar` se niega a correr mientras haya bloques sin extraer (`juez.py:148-151`), y
  `extraer` deja bloques pendientes en silencio si se queda sin tope (`programas.py:128-129`). Si la extracción
  de 2026 se corta a medias, **la noche deja de juzgar**.

## 4. La página del test (web)

Una página nueva, `/test`, enlazada desde la portada. Móvil primero, mismo estilo «Boletín» que el resto.
Textos en castellano de Canarias (`ustedes`, nunca `vosotros`) y sin rayas.

1. **Entrada.** Qué es en tres líneas, que nada se guarda y que no da ningún resultado por partido. Lista de temas
   con casilla y el número de propuestas de cada uno. Botón «Empezar».
2. **Tarjetas, una a una**, en **orden aleatorio** dentro de cada sesión (mezclando partidos y temas elegidos).
   Cada tarjeta lleva:
   - tema;
   - el **resumen neutral** (2-4 frases: qué se hace, a quién afecta, cuánto si el programa lo dice, cómo se paga
     si el programa lo dice);
   - la marca **«sin concreción»** si el programa no da detalle;
   - las **condiciones** (§5.3): una etiqueta corta por condición y, al desplegar, la explicación en lenguaje llano
     con el enlace a la norma;
   - botones **Sí** y **No**. Progreso «7 de 23».
   - Se enseñan **todas** las tarjetas de los temas elegidos, sin tope por sesión. Un botón **«Ver de quién eran»**,
     siempre visible, lleva al destape con lo votado hasta ese momento (Fran, 2026-10-30).
3. **Destape.** Lista de todas las tarjetas votadas, cada una con: tu voto, **el partido**, la cita literal con su
   página y enlace al PDF del programa, las condiciones, y si hay cruce 2023 confirmado: «Ya lo prometió en 2023. En la XV votó **de
   acuerdo con / en contra de** esa promesa en [iniciativa]», con enlace a la votación del Congreso. Se usa el
   veredicto firme que ya publica la web (`cumple`, o `incumple` confirmado por Fran), que tiene en cuenta
   devoluciones y textos alternativos; nunca el Sí/No en bruto. Si hay varios cruces firmes, se enseña el de
   la votación sustantiva más reciente y se enlaza la ficha del partido para el resto. *(Decisión de Claude.)* Botón «Volver a empezar».
   **Ningún total, porcentaje ni agrupación por partido.**

Implementación: un `<script>` de Astro sin framework y los datos del test incrustados en la página como JSON
(solo las propuestas publicadas, no el `datos.json` entero). Sin peticiones de red después de cargar la página.

## 5. El motor

Todo nuevo vive en un módulo `src/electoral/test_ciegas.py` con subcomandos de `electoral.py`. Corre **en el PC**
contra una copia de `electoral.db` traída de la Pi; el resultado revisado se guarda en un fichero versionado del
repo (§5.6), así no toca la base de la noche. *(Decisión de Claude.)*

### 5.1 Selección (script + una pasada barata)

1. Script: promesas del año pedido, de los temas pedidos, no procedimentales, sin textos repetidos dentro del
   partido.
2. Una llamada a `deepseek-v4-flash` **por (partido, tema)** con la lista de sus promesas: devuelve las **3 más
   concretas y de más alcance** (o todas si hay menos de 3). Con 9 partidos y 6 temas son ≤54 llamadas.

**Temas del lanzamiento (opción B):** Economía e industria, Vivienda, Sanidad, Fiscalidad, Empleo y trabajo y
Pensiones. Unas 150 propuestas como máximo. El resto de temas se añade después en el mismo orden de tamaño.
*(La lista concreta es propuesta de Claude; Fran eligió la opción B.)*

### 5.2 Resumen neutral y materias (una llamada por propuesta)

Una llamada a `deepseek-v4-flash` por propuesta elegida, con la promesa, su cita y **el bloque de programa del
que sale** como contexto (ahí están las cifras y el cómo). Devuelve:

- `resumen`: neutral. Reglas: sin nombre de partido ni de sus líderes; sin primera persona; sin balance de
  gestión; sin léxico identitario («Euskal Herria», «la Nación española», «justicia climática») salvo que sea el
  objeto mismo de la propuesta, y entonces con el término jurídico neutro; siempre en castellano; ninguna cifra
  que no esté en el texto del programa.
- `concreta`: sí / no.
- `materias`: lista de claves del vocabulario cerrado de `config/condiciones.json` (§5.3). Si ninguna encaja,
  `ninguna`.
- `coste`: si la propuesta implica gasto o pérdida de ingresos que pasaría por los Presupuestos.

### 5.3 Condiciones (script, sin LLM)

`config/condiciones.json`, escrito a mano y revisado por Fran una sola vez. Cada **materia** lleva: requisito,
etiqueta corta, explicación en lenguaje llano y enlace a la norma. El LLM solo elige materias; el artículo, la
mayoría y el «por qué» salen de la tabla, nunca del modelo.

Niveles de requisito (de menos a más exigente):

| Nivel | Ejemplos de materia | Norma |
|---|---|---|
| Lo puede hacer el Gobierno | reglamentos, real decreto | art. 97 CE |
| Ley ordinaria (mayoría simple) | la mayoría de reformas fiscales y laborales | art. 66 y 90 CE |
| Ley orgánica (176 votos en la votación final) | derechos fundamentales, régimen electoral, Estatutos, Poder Judicial | art. 81 CE |
| Reforma de la Constitución, vía ordinaria (3/5 de cada Cámara) | cambios fuera del art. 168 | art. 167 CE |
| Reforma de la Constitución, vía agravada (2/3, disolución, 2/3 y referéndum) | Título preliminar, derechos fundamentales (Sección 1.ª del Cap. II del Título I), Corona | art. 168 CE |
| **No depende de España sola: UE** | IVA e impuestos especiales armonizados, aranceles, ayudas de Estado, política agraria común | Directiva 2006/112/CE; art. 113 TFUE (unanimidad fiscal); art. 107 TFUE |
| **Competencia compartida** | vivienda, sanidad, educación: el Estado fija bases, financia o coordina; las comunidades desarrollan y gestionan | art. 149.1 CE (p. ej. 149.1.1, 149.1.13, 149.1.16, 149.1.30), art. 148.1.3 CE |
| **No es competencia del Estado** | materias que solo pueden hacer las comunidades, sin título estatal posible | art. 148 y 149 CE, Estatuto correspondiente |

Más la marca **«Coste para las cuentas públicas»** si `coste` es sí. No afirma que vaya en la Ley de Presupuestos (los tributos no se crean ahí, art. 134.7 CE). Explica dos cosas ciertas: el gasto recurrente necesita crédito en los Presupuestos, y el Gobierno puede oponerse a tramitar una proposición que suba el gasto o baje los ingresos del año en curso (art. 134.6 CE). *(Decisión de Claude, tras la revisión.)*

**«Inviable» se dice solo** cuando el requisito queda fuera de lo que el Parlamento español puede aprobar por sí
solo (UE, competencia exclusiva autonómica) o exige la reforma agravada. **Una competencia compartida nunca es
«inviable»**: se explica qué parte puede hacer el Estado y qué parte las comunidades. El texto explica por qué,
sin valorar. *(Decisión de Claude, tras la revisión.)*

### 5.4 Prueba de neutralidad

`gemini-2.5-flash-lite` recibe cada resumen y la lista de partidos del año, y dice de cuál cree que es. Si acierta,
el resumen se reescribe (§5.2, indicándole qué lo delata), como mucho dos veces; si sigue acertando, se marca
`delata` para que Fran decida. Barrera sobre la muestra de 2023: **tras reescribir, el adivinador acierta como
mucho el 25 %** de los resúmenes (el azar con 9 partidos es el 11 %). En 2026 se vuelve a medir, pero **no frena el
lanzamiento**: las tarjetas que sigan marcadas `delata` las decide Fran una a una en la revisión. *(Decisión de Claude.)*

### 5.5 Cruce con 2023 (sin LLM)

Para cada propuesta de 2026, se buscan por embeddings (`multilingual-e5-small`, ya en el motor) las promesas de 2023
**del mismo partido** que tengan un cruce firme publicado (`cumple`, o `incumple` confirmado en
`config/revision_manual.json`). El mejor candidato se enseña a Fran en la revisión; **solo se publica si él lo
confirma**.

### 5.6 Revisión de Fran

Un comando genera un fichero de revisión con cada propuesta: resumen, marca de concreción, condiciones, cita, página
y enlace al PDF, aviso `delata` si lo hay y el candidato de cruce 2023. Fran marca cada una: **publicar**,
**corregir** (con su texto) o **descartar**, y si confirma o no el cruce. Objetivo de ergonomía: ~2 minutos por
propuesta. El formato lo decide quien construya, siguiendo el patrón de `config/revision_manual.json`.

Lo aprobado queda en `config/test_ciegas.json`, versionado. `exportar` lo lee y lo añade a `datos.json` como clave
`test` (contrato **1.2.0**, esquema actualizado). La Pi lo recoge con el `git pull` manual de siempre y la noche lo
sigue publicando.

### 5.7 Presupuesto

Cada subcomando tiene su tope y registra en la tabla `gasto`, como `extraer` y `juzgar`.

| Tirada | Llamadas aprox. | Coste estimado |
|---|---|---|
| Prueba 2023: 2 temas (Vivienda y Fiscalidad) | 18 selección + ~54 resúmenes + ~54-100 adivinanzas | < 0,10 $ |
| Producción 2026: 6 temas | 54 + ~150 + ~150-300 | 0,30-0,60 $ |
| Extracción de los programas 2026 | ~560 bloques | ~0,30 $ |

Total previsto por debajo de 1,50 $, dentro del tope de 10 € que ya existe.

## 6. Calendario

| Fechas | Qué |
|---|---|
| 31-10 a 5-11 | `condiciones.json`, selección, resumen, neutralidad, cruce y revisión sobre la muestra de 2023. Fran juzga ~20 tarjetas |
| 6-11 a 12-11 | Página `/test`, pruebas Playwright, contrato 1.2 y ensayo completo con 2023 |
| 13-11 y 14-11 | Ingesta y extracción de 2026 **en la Pi** (base real), copia al PC, generación y revisión de Fran |
| 15-11 | Publicación. Programas que lleguen después: se añaden con el mismo proceso |

## 7. Pruebas (Playwright, comportamiento)

Sobre un fixture con propuestas de prueba:

- Elegir temas solo muestra tarjetas de esos temas; el número de la entrada coincide.
- Ninguna tarjeta enseña el partido ni la cita antes de votar.
- Las condiciones se ven y se despliegan antes de votar; el enlace a la norma está presente.
- Votar todas lleva al destape con partido, cita, página y voto de cada una.
- «Ver de quién eran» a mitad destapa solo las tarjetas ya votadas.
- El destape no contiene ningún total, porcentaje ni agrupación por partido.
- El cruce 2023 sale solo en las propuestas que lo tienen.
- No se escribe nada en `localStorage`, `sessionStorage` ni cookies, y no hay peticiones de red tras la carga.
- «Volver a empezar» y recargar dejan la página como nueva.
- Móvil de 390 px, como el resto de pruebas.

En el motor, pruebas de comportamiento del pipeline con el LLM simulado: la selección respeta temas y tope, las
condiciones salen solo de la tabla, una materia desconocida no produce condición, y sin aprobación de Fran nada
llega a `test_ciegas.json`.

## 8. Riesgos

- **Programas tardíos o escalonados:** el test sale el 15 con los que haya; la entrada dice qué partidos faltan.
- **Extracción de 2026 cortada a medias bloquea la noche** (§3): lanzarla con tope suficiente y comprobar que no
  quedan bloques pendientes antes de dar el día por cerrado.
- **El «Instituciones y calidad democrática» puede estar inflado** (destino por defecto del extractor si el tema
  no encaja, `programas.py:137`). No está en los temas del lanzamiento.
- **Condiciones discutibles:** una propuesta puede tocar varias materias o depender de cómo se redacte la ley. La
  tabla da el requisito mínimo seguro y la explicación lo dice; ante la duda, Fran descarta la condición.
- **Revisión:** son 5-7 horas de Fran el 13 y 14. Si no da tiempo, salen menos temas (opción B).

## 9. Lo que queda a quien construya

- Formato del fichero de revisión y forma exacta de `config/condiciones.json` y de la clave `test` del contrato.
- Prompts de selección, resumen y adivinanza, ajustados sobre la muestra de 2023.
- Diseño visual de tarjetas y destape dentro del estilo existente.
- Cómo se copia la base de la Pi al PC.
