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
        confirmar = dict(zip(("votacion_id", "promesa_id", "partido"), clave)) | {"veredicto": "incumple"}
        _enviar(f"<b>Revisar «incumple»: {c['partido']}</b>\n{v['fecha']}: {v['expediente'][:300]}\n"
                f"Votó {c['voto']}. Promesa: {p['texto']}\n«{p['cita']}» ({p['url_programa_pagina']})\n"
                f"Para confirmarlo: añadir {json.dumps(confirmar, ensure_ascii=False)} a config/revision_manual.json")
        conn.execute("INSERT INTO avisos VALUES (?,?,?, datetime('now'))", clave)
        conn.commit()
        n += 1
    return n


def publicar(datos_json: Path, web: Path) -> None:
    """Copia datos.json al clon de poligrafo-web y hace push. Nunca fuerza: si el remoto cambió, falla."""
    destino = web / "data" / "datos.json"
    destino.parent.mkdir(exist_ok=True)
    shutil.copyfile(datos_json, destino)

    def git(*a):
        return subprocess.run(["git", *a], cwd=web, capture_output=True, text=True, check=True)

    git("add", "data/datos.json")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=web).returncode != 0:
        git("commit", "-m", f"datos: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    git("push", "origin", "HEAD")


def escribir_salud(ruta: Path, publicado: bool, avisos: int, error: str | None) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "publicado": publicado, "avisos": avisos, "error": error}, ensure_ascii=False),
                    encoding="utf-8")
