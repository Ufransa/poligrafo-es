# PolígrafoES v3 — Fichas por ley

**Fecha:** 2026-08-01
**Estado:** aprobado, pendiente de plan de implementación

## Problema

El digest semanal no cumple su objetivo (que Fran llegue a unas elecciones con la decisión
formada). Los mensajes se repiten, y lo que publican es falso.

Cuatro causas independientes, todas verificadas contra datos de producción:

### 1. Campos del XML no parseados → información falsa (crítico)

`src/congreso.py:parse_vote_xml` lee `Sesion`, `NumeroVotacion`, `Fecha`, `Titulo`,
`TextoExpediente` y `Totales`. El XML del Congreso trae además dos campos que se ignoran:

```
<TituloSubGrupo> = Enmiendas presentadas por el Grupo Parlamentario Euskal Herria Bildu
<TextoSubGrupo>  = Enmienda 270.
```

Consecuencias:

- El LLM recibe el **mismo input** para las 49 votaciones de una misma ley (`Titulo` es
  genérico: "Dictámenes de Comisiones sobre iniciativas legislativas"). Genera 49 paráfrasis
  del mismo concepto porque no tiene nada que las distinga. La duplicación no es un fallo del
  prompt: es alucinación forzada por input idéntico.
- El campo `resultado` significa lo contrario de lo que el mensaje sugiere. El digest publicó
  ocho veces `Refuerzo de derechos para personas con discapacidad — ❌ RECHAZADA`. Lo
  rechazado fueron enmiendas parciales. **La ley se aprobó, 179 a favor / 33 en contra**
  (sesión 192, votación 54).

### 2. Granularidad equivocada

La unidad del XML es la votación; la unidad informativa es la ley. Datos en producción:

| Métrica | Valor |
|---|---|
| Votaciones almacenadas | 225 en 12 sesiones |
| "Dictámenes de Comisiones" (= enmiendas parciales) | 95 (42%) |
| Votaciones de un solo expediente (ley de discapacidad) | 49 |

Además, el sentido de voto en una enmienda parcial no es posicionamiento ideológico: el PSOE
votando en contra de una enmienda de Bildu a su propia ley es táctica parlamentaria.

### 3. Matcher sesgado por longitud de PDF

`src/matcher.py:top_candidates_per_party` puntúa por solapamiento de palabras de 5+ caracteres.
Los programas largos ganan siempre:

| Partido | Matches |
|---|---|
| SUMAR | 75 |
| PP | 71 |
| PSOE | 59 |
| Vox | 7 |
| PNV, ERC, Junts, EH Bildu | 0 |

No mide posicionamiento, mide extensión del documento. El juez LLM (`src/llm.py`) solo elige
entre candidatos ya sesgados, así que no puede corregirlo. El resultado publicado es un
extracto crudo truncado a 200 caracteres a media frase, sin conclusión.

### 4. Rate limit 429 no manejado → el digest se reenvía entero cada semana

`src/publisher.py:send_message` devuelve `None` ante cualquier fallo sin inspeccionar el código
de estado. `digest.py` solo marca los ítems como publicados si **todos** los mensajes salieron:

```python
elif sent_ids and len(sent_ids) == len(messages):
    mark_digest_published(...)
```

El digest genera 19-21 mensajes; Telegram corta en ~20/minuto con HTTP 429. Nunca salen todos
→ nunca marca → el lunes siguiente republica desde cero. Los mensajes 224-235 del 27/07 son
idénticos a los 212-223 del 20/07.

Es un bucle que se aprieta: cada semana la cola crece, el digest es más largo, falla antes.
Estado actual: 76 votos y 197 entradas BOE pendientes. En 5 ejecuciones registradas: 3
completas, 2 incompletas, 16 mensajes perdidos.

## Objetivo

Un mensaje por ley, veraz, con los partidos posicionados de forma legible. El listón: leyendo
el canal, Fran debe poder decir cómo votó cada partido en las leyes que le importan.

Mensaje objetivo (datos reales, sesión 192):

```
🗳️ Ley de discapacidad: más accesibilidad, autonomía y dependencia
✅ APROBADA (179 a favor / 33 en contra) · ya es ley

✅ Sí       PSOE · SUMAR · ERC · Junts · EH Bildu · PNV · Mixto
⚪ Absten.  PP (137 diputados)
❌ No       Vox

🔎 48 enmiendas votadas y rechazadas antes del texto final.
   Junts 14 · PNV 9 · Podemos 7 · BNG 5 · Bildu 4 · ERC 3 · Sumar 3

📋 PP prometió (p.30) blindar por ley el apoyo a la discapacidad
   → se abstuvo en la votación final. Incoherente con el programa.
```

## Diseño

### Parseo (`src/congreso.py`)

`parse_vote_xml` devuelve además `titulo_subgrupo` y `texto_subgrupo`.

Migración v3 en `src/db.py`: dos columnas `TEXT` en `votes` (`titulo_subgrupo`,
`texto_subgrupo`), más `expediente_key TEXT` y `clase TEXT` (ver abajo). Sigue el patrón de
`_migrate_v2`: `ALTER TABLE` idempotente comprobando `PRAGMA table_info`.

### Clasificador determinista (`src/congreso.py:classify_vote`)

Sin LLM. Sobre `titulo_subgrupo`:

| Condición | Clase | Efecto |
|---|---|---|
| Vacío | `sustantiva` | Se publica. Conjunto de ley, convalidación de RDL, toma en consideración, moción, PNL |
| Contiene `"totalidad"` | `sustantiva` | Enmienda a la totalidad: querer tumbar la ley entera es posicionamiento |
| Contiene `"Enmienda"` | `parcial` | No se publica sola; se agrega al recuento |
| Resto (`"Corrección técnica."`…) | `parcial` | Se agrega |

Validación esperada sobre la sesión 192: 56 votaciones → 7 sustantivas (87% menos ruido).

### Agrupación por expediente

`expediente_key` = `texto_expediente` normalizado: minúsculas, espacios colapsados, y quitando
el prefijo `"votación del dictamen del "`. Sin ese strip, la votación de conjunto (#54) no
agrupa con sus 49 votaciones parciales (48 de enmiendas + 1 corrección técnica), porque el
Congreso antepone esa fórmula solo a la de conjunto.

Un bloque del digest = un `expediente_key`, compuesto por:

- su votación **sustantiva** como cabecera (resultado, totales, voto por grupo)
- el recuento de sus votaciones **parciales** (cuántas enmiendas presentó cada grupo y cuántas
  se rechazaron)

Si un expediente tiene varias sustantivas (p. ej. dos enmiendas a la totalidad de la misma
proposición, sesión 192 #55 y #56), cada una genera su propio bloque: son votaciones
políticamente distintas.

Si un expediente solo tiene parciales dentro de la ventana del digest (la ley se votó en una
sesión anterior), no se publica bloque. Queda pendiente hasta que aparezca su sustantiva.

### Enriquecimiento LLM por expediente (`src/llm.py`)

Una llamada por expediente en vez de una por votación. El prompt recibe el expediente, la
votación sustantiva con su resultado, y el recuento de enmiendas. De 50 llamadas Haiku a 1
para la ley de discapacidad; ~85% menos gasto de API.

El bloque de `FORMAT RULES` de `_SYSTEM_VOTE` sobre tipos de votación se conserva: sigue siendo
correcto y es lo que distingue un tratado de una PNL.

### Matcher por embeddings (`src/matcher.py`)

- Modelo `intfloat/multilingual-e5-small`. Multilingüe real, a diferencia del
  `all-MiniLM-L6-v2` (inglés) que usa el vectorstore del vault. La Orange Pi ya tiene
  `torch 2.12.0+cpu`, 4 cores y 3.3 GB libres.
- Vectores persistidos como BLOB en una columna nueva de `program_chunks`, similitud coseno con
  numpy. **Sin ChromaDB**: ~2.000 chunks no justifican la dependencia.
- Script one-off `embed_programs.py` para vectorizar los chunks existentes.
- Top-3 por partido por similitud → juez LLM como filtro final (se conserva).
- **Cambia el output**: no se publica el extracto crudo. El juez emite un veredicto de
  coherencia (`cumple` / `incumple`) con la promesa parafraseada y la página. Sin veredicto,
  no se publica nada para ese partido. Un extracto sin conclusión es ruido.

### Publicación robusta (`src/publisher.py`, `digest.py`)

- `send_message` inspecciona el status: ante 429, lee `parameters.retry_after` del cuerpo,
  espera y reintenta (máx. 3 intentos). Registra el código y el cuerpo del error en el fallo
  definitivo — el silencio actual es lo que ocultó el problema durante seis semanas.
- Throttle base de 4 s entre mensajes.
- **Marcado incremental**: cada bloque enviado con éxito marca sus propios ítems como
  publicados, en lugar del all-or-nothing actual. Un envío parcial deja de reenviarlo todo.

### Filtro del BOE

197 entradas pendientes; el filtro actual (`categories != '[]'`) no basta. Se restringe a los
rangos con fuerza de ley estatal: `Ley`, `Ley Orgánica`, `Real Decreto-ley`, `Decreto-ley`.

Sobre julio, reduce de 131 a 22 entradas. Quedan fuera Real Decreto (41), Resolución (24),
Orden (12), Ley Foral (4, autonómico) y demás. Se siguen agrupando en un bloque de lista, no
un mensaje por entrada.

## Migración del canal

El bot `@ManifiestoBot` es administrador del canal con `can_delete_messages: True`, así que
puede borrar todo el historial sin el límite de 48 horas.

Orden acordado — el borrado no ocurre hasta que el reemplazo esté generado y revisado:

1. **Implementar** v3 completo.
2. **Reprocesar** los 225 votos con el pipeline nuevo en `--dry-run`. Criterio de aceptación:
   la ley de discapacidad aparece como **aprobada**, en **un** bloque, con la abstención del PP.
   Fran revisa la salida.
3. **Vaciar** el canal: `deleteMessage` iterando desde el ID 1 hasta el más alto conocido en
   el momento de ejecutar (235 según el log del 27/07, más un margen por si el cron ha
   publicado otro digest entretanto). Los IDs inexistentes devuelven error y se ignoran.
4. **Republicar solo julio** (sesiones 192 y 193, que son exactamente los 76 votos con
   `published=0`) más las ~22 entradas BOE de julio que pasen el filtro de rango. Estimado:
   ~20 fichas de votaciones + 2-3 mensajes BOE agrupados. Se envía de una tacada con el
   throttle nuevo (~2 min).

Los votos de mayo y junio se marcan `published=1` sin republicar: permanecen en la base de
datos para el futuro informe acumulado, pero no vuelven al canal.

## Tests

Behavioral, sobre el pipeline completo. Fixture: el ZIP real de la sesión 192, guardado en
`tests/fixtures/`.

- Entra el ZIP → el digest produce 7 bloques, no 56.
- La ley de discapacidad aparece **una vez**, como `aprobada`, con PP en abstención y Vox en
  contra.
- Las 49 enmiendas no generan bloque propio; aparecen como recuento agregado.
- Ante un 429 simulado, `send_message` reintenta y los ítems ya enviados quedan marcados.

Verifican comportamiento observable, no estructura interna: sobreviven a que el parser se
reescriba entero.

## Fuera de alcance

Deliberadamente **no** entra en esta iteración:

- Informe acumulado por ejes temáticos y partido.
- Comandos de Telegram (`/informe`, `/siguiente`).
- Republicación de mayo y junio.

Si con el digest arreglado Fran sigue sin poder decidir su voto, la agregación por partido es
la siguiente iteración — y entonces tendrá datos limpios debajo, que es cuando tiene sentido
construirla.
