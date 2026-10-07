# src/electoral/exportar.py
import json
from datetime import datetime, timezone
from pathlib import Path

VERSION_CONTRATO = "1.0.0"


def _votaciones(conn) -> list[dict]:
    salida = []
    for v in conn.execute("SELECT * FROM votaciones ORDER BY fecha, sesion, numero"):
        votos = {r["partido"]: {"voto": r["voto"], "dividido": bool(r["dividido"])}
                 for r in conn.execute("SELECT * FROM votos_partido WHERE votacion_id = ?", (v["id"],))}
        salida.append({
            "id": v["id"], "fecha": v["fecha"], "sesion": v["sesion"], "numero": v["numero"],
            "tipo": v["tipo"], "subtipo": v["subtipo"], "expediente": v["expediente"],
            "que_se_vota": v["texto_subgrupo"], "clave_iniciativa": v["clave_iniciativa"],
            "resultado": v["resultado"], "a_favor": v["a_favor"], "en_contra": v["en_contra"],
            "abstenciones": v["abstenciones"], "excluida_tramite": bool(v["excluida_tramite"]),
            "votos": votos, "url_xml": v["url_xml"], "url_sesion": v["url_sesion"],
        })
    return salida


def construir(conn, raiz: Path) -> dict:
    partidos = json.loads((raiz / "config" / "partidos_electoral.json").read_text(encoding="utf-8"))
    votaciones = _votaciones(conn)
    return {
        "meta": {
            "version_contrato": VERSION_CONTRATO,
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "periodo": {"desde": "2023-08-17", "hasta": max((v["fecha"] for v in votaciones), default=None)},
            "recuentos": {"votaciones": len(votaciones)},
        },
        "partidos": partidos,
        "votaciones": votaciones,
    }


def escribir(datos: dict, salida: Path) -> None:
    salida.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
