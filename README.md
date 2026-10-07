# PolígrafoES

Herramienta personal para cotejar lo que prometieron los partidos en su programa electoral con lo que votaron
después en el Congreso de los Diputados. Sin afiliación, sin financiación y sin publicidad.

El repositorio tiene dos piezas independientes:

- **Bot de Telegram** (`fetcher.py`, `digest.py`): vigila cada día las votaciones del Pleno y el BOE y publica un
  resumen semanal en un canal privado.
- **Motor electoral 29N** (`electoral.py`): genera `datos.json`, la base de la web de las elecciones generales del
  29 de noviembre de 2026.

## Motor electoral 29N

```bash
pip install -r requirements.txt
# OPENROUTER_API_KEY en .env (clave con límite de gasto)
python electoral.py todo --tope-extraer 1 --tope-juzgar 4
python electoral.py muestra --n 30      # muestra al azar para revisar a mano antes de publicar
```

Cada paso es reanudable: si un tope de gasto corta la carga, se vuelve a lanzar el mismo comando.

### De dónde salen los datos

| Dato | Fuente |
|---|---|
| Votaciones (voto de cada diputado) | [Datos abiertos del Congreso](https://www.congreso.es/es/opendata/votaciones), XV legislatura |
| Texto de cada iniciativa | Boletín Oficial de las Cortes Generales (enlaces del open data de iniciativas) |
| Leyes y decretos-ley aprobados | [API de legislación consolidada del BOE](https://www.boe.es/datosabiertos/) |
| Promesas | Programas electorales oficiales de las generales del 23J de 2023 (enlazados en `config/partidos_electoral.json`) |
| Gasto de campaña | Tribunal de Cuentas, Informe 1.616 (generales de 2023) |

### Cómo se decide un veredicto

1. Cada programa se divide en **promesas sueltas**, con su cita literal y su página.
2. Para cada votación se buscan las promesas más parecidas, **normalizando dentro de cada programa** para que los
   programas largos no acaparen candidatos.
3. Las votaciones de **trámite** (avocaciones, prórrogas, lectura única, tramitación de un decreto como proyecto
   de ley) no se juzgan. De un decreto-ley cuenta la **convalidación**.
4. Tres modelos de familias distintas (`deepseek-v4-pro`, `gpt-5-mini` y `gemini-2.5-flash-lite`) juzgan cada
   cruce dos veces. Las instrucciones exactas están en `src/electoral/juez.py`.
5. **Veredicto** solo si los tres coinciden y los tres ven una relación directa. Si coinciden dos, el cruce se
   muestra como **«juzga tú»**, sin veredicto. Un partido que vota dividido nunca recibe veredicto.

### Cuánto acierta

Antes de publicar se revisan a mano 19 cruces de referencia (`tests/fixtures/electoral/referencia.json`): los 19
fueron correctos según la revisión de su autor. La prueba `pytest -m llm` los vuelve a juzgar con los modelos
reales y exige **cero veredictos al revés** y al menos 16 de 19 que sigan siendo veredicto. Además, cada carga
completa genera una muestra de 30 veredictos al azar que se revisa antes de publicar.

### Qué no mide

- **Corrupción**: no hay una fuente de verdad fiable y completa; los titulares tienen sesgo de selección.
- **El texto completo de las leyes**: con los modelos actuales empeoraba el acierto.
- **Partidos sin programa propio en 2023** (Podemos y Compromís iban dentro de Sumar; SALF no existía; no se ha
  localizado el de CC ni el de UPN): se muestran sus votos, pero no promesas que no fueron suyas.

## Pruebas

```bash
pytest                # suite completa, sin coste
pytest -m llm         # referencia con modelos reales (unos 0,03 $)
```

## Licencia

MIT. Ver `LICENSE`.
