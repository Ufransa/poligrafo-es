# tests/electoral/test_referencia.py
"""Los 19 cruces revisados por Fran el 2026-10-07. Un cambio de modelo o de instrucciones que empeore esto no se despliega.

Dos exigencias distintas:
- Precisión (innegociable): ningún caso puede salir con el veredicto contrario al que revisó Fran.
- Cobertura (con margen): al menos 16 de 19 siguen saliendo como «veredicto». Los 19 se eligieron por haber
  salido unánimes en una tirada, así que repetirla siempre pierde alguno por azar (medido: 17-18 de 19, y los
  que se pierden bajan a «juzga tú», nunca a un veredicto erróneo).
"""
import json
from pathlib import Path

import pytest

from src.electoral import juez
from src.electoral.llm import LLM

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"
COBERTURA_MINIMA = 16


@pytest.mark.llm
def test_los_casos_revisados_por_fran_nunca_salen_al_reves_y_casi_todos_siguen_siendo_veredicto():
    llm = LLM(tope_usd=0.5)
    casos = json.loads((FIX / "referencia.json").read_text(encoding="utf-8"))
    al_reves, veredictos = [], 0
    for n, caso in enumerate(casos):
        v = {"expediente": caso["expediente"], "tipo": caso["titulo"], "texto_subgrupo": caso["subgrupo"],
             "resultado": caso["resultado"],
             "subtipo": "devolucion" if "devoluci" in (caso["expediente"] + caso["subgrupo"]).lower() else "normal"}
        votos = [{"partido": p, "voto": x} for p, x in sorted(caso["votos"].items())]
        texto = juez.prompt(v, votos, [{"id": 1, "partido": caso["partido"], "texto": caso["promesa"]}])
        por_juez = {m: juez.estables(llm, m, texto, {1}) for m in juez.JUECES}
        res = juez.nivel({m: (r or {}).get((caso["partido"], 1)) for m, r in por_juez.items()}, False)
        if res and res[1] != caso["veredicto_esperado"]:
            al_reves.append((n, caso["partido"], caso["expediente"][:80], res))
        if res == ("veredicto", caso["veredicto_esperado"]):
            veredictos += 1
    print(f"veredictos {veredictos}/{len(casos)} · gastado {llm.gastado:.4f} $")
    assert not al_reves, al_reves
    assert veredictos >= COBERTURA_MINIMA
