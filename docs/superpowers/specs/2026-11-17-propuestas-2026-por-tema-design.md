# Propuestas de 2026 por tema (web 29N)

> Fecha: 2026-11-17. Diseño corto (cambio pequeño sobre la web 29N, ver `2026-10-07-web-electoral-29n-design.md`).

## Para qué

Los programas de 2026 ya están cargados en el motor (10 partidos, 4.228 promesas, 2026-11-17), pero la web no
enseña nada de ellos. Fran quiere que sus allegados, antes del 29N, elijan un tema y vean **qué propone en concreto
cada partido**, con la cita literal y la página del programa oficial. Se lee **tema a tema**, comparando partidos.

## Objetivos, no objetivos y antiobjetivos

- **Objetivo:** todas las propuestas de 2026, agrupadas por tema y por partido, cada una con resumen en castellano,
  cita literal y enlace a la página exacta del PDF oficial.
- **No objetivo:** cruzar 2026 con los votos de la XV (sigue en «más adelante»), buscar por texto libre, filtros
  combinados.
- **Antiobjetivos:** que la web elija promesas («principales», «destacadas»): nadie elige promesas (Fran,
  2026-10-08). Que el orden de los partidos sugiera un ranking. Que se publique algo que nadie ha revisado.

## Enfoques considerados

1. **Página estática por tema (elegido por Fran).** Astro genera las páginas desde `datos.json`, sin JavaScript,
   con `<details>` plegado por partido. Es coherente con el resto de la web, va rápida en el móvil y se prueba con Playwright.
2. Una página con filtros en el navegador. Descartado: obliga a descargar unos 2 MB antes de ver nada y mete
   JavaScript para algo que no lo necesita.
3. Búsqueda por texto libre. Descartado: los programas usan palabras distintas para lo mismo y daría resultados engañosos.

## Decidido por Fran

- Tema a tema, comparando partidos (2026-11-17).
- **Partidos en orden alfabético** dentro de cada tema (2026-11-17).
- Página estática por tema.
- Sumar sin programa de 2026: no se presenta dentro de Frente Amplio y no se ha localizado programa propio.
  Podemos fuera: solo publica una web de 244 palabras.
- Frente Amplio sin pasado, como SALF.

## Diseño

- **`/temas/`:** los 17 temas del extractor (`programas.TEMAS`), cada uno con su número total de propuestas de 2026
  y enlace a su página. Enlace a `/temas/` en la cabecera, junto a «Sobre este proyecto» y «Test a ciegas».
- **`/temas/<slug>/`:** título «<Tema> · qué propone cada partido en 2026». Debajo, un `<details>` cerrado por cada
  partido con propuestas en ese tema, en orden alfabético por `nombre`, con el resumen «<Partido> · N propuestas».
  Dentro de cada uno, en el orden del programa (página y luego id): el resumen (`texto`), la cita literal
  (`cita`, en su lengua original) y «pág. N» enlazada a `url_programa_pagina`. Al final de la página, los partidos
  sin programa de 2026 o sin propuestas en ese tema, cada uno con su motivo en una línea.
- **Motivos sin programa de 2026:** campo nuevo `sin_programa_2026` en `config/partidos_electoral.json`. Con estos textos:
  - Junts, EH Bildu y UPN: «Aún no ha publicado su programa de 2026.».
  - Sumar: «No hemos localizado un programa de Sumar para 2026.».
  - Podemos: «Solo publica un manifiesto breve, sin propuestas concretas.» con enlace a https://pazcasaytrabajo.es/.

  Un partido con programa de 2026 pero sin propuestas en un tema aparece como «Sin propuestas sobre este tema».
- **Ficha de partido:** «A qué dedica su programa» muestra los temas en % de 2026 junto a los de 2023 (lo que
  pedía el diseño del 07-10), con enlace a programa oficial 2026. Cada tema de 2026 enlaza a su página
  `/temas/<slug>/#<partido>`. SALF y Frente Amplio dejan de salir vacíos.
- **Aviso en cada página de tema:** «Resumen automático de cada propuesta; la cita es literal y está comprobada
  contra el programa oficial. Partidos en orden alfabético.» «Sobre este proyecto» explica lo mismo.
- **Solo propuestas no procedimentales** (las mismas que ya exporta `exportar._promesas`).

## Revisión antes de publicar

Antes del primer push de la web con esto, Fran revisa una **muestra al azar de 30 propuestas de 2026** (semilla
fija, en Markdown, con resumen, cita, tema, página y enlace), como se hizo con los veredictos de 2023. Hace falta
una variante del comando `muestra` para promesas (hoy solo muestrea veredictos). Si la muestra sale mal
(resúmenes que no dicen lo que dice la cita, temas mal puestos, diagnósticos tomados por promesas), se corrige
antes de publicar.

## Lo que queda al constructor

- Slugs de tema (sin tildes, en minúsculas y con guiones) y el ancla por partido.
- Estilo dentro del diseño «Boletín» existente.
- Pruebas Playwright con la fixture `tests/fixtures/datos.json` ampliada con promesas de 2026: orden alfabético,
  plegado por defecto, enlace de página con `#page=`, motivos de los partidos sin programa y página de tema sin JavaScript.
