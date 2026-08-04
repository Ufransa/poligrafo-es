#!/usr/bin/env python3
"""
Backfill v3: reclasifica los votos existentes y prepara el estado del canal.

- Rellena clase y expediente_key en todos los votos (re-descarga los ZIP de sesión
  para recuperar los campos de subgrupo, que no estaban al ingerirlos).
- Purga enriquecimientos y matches: los resúmenes viejos son alucinaciones y los
  matches vienen del prefiltro por keywords.
- Marca mayo y junio como publicados: se conservan en la base para el futuro
  informe acumulado, pero no vuelven al canal.
"""
import sys
from pathlib import Path

# Se invoca como `python3 scripts/reclasificar_v3.py` desde la raíz: sys.path[0]
# es scripts/, no el repo, así que `src` no se encontraría.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import init_db, get_conn
from src.congreso import (download_session_zip, parse_vote_xml, classify_vote,
                          expediente_key)

CORTE_JULIO = "202607"


def run(dry_run=False):
    init_db()
    conn = get_conn()
    try:
        sesiones = conn.execute(
            "SELECT id, session_number, session_date, zip_url FROM sessions"
            " WHERE zip_url IS NOT NULL ORDER BY session_number"
        ).fetchall()

        for s in sesiones:
            print(f"Sesión {s['session_number']} ({s['session_date']})...")
            try:
                xmls = download_session_zip(s["zip_url"])
            except Exception as e:
                print(f"  WARN: no se pudo descargar: {e}")
                continue
            for _, xml_str in xmls:
                try:
                    v = parse_vote_xml(xml_str)
                except Exception:
                    continue
                conn.execute(
                    """UPDATE votes SET titulo_subgrupo=?, texto_subgrupo=?,
                       clase=?, expediente_key=?
                       WHERE session_id=? AND vote_number=?""",
                    (v["titulo_subgrupo"], v["texto_subgrupo"],
                     classify_vote(v["titulo_subgrupo"]),
                     expediente_key(v["texto_expediente"]),
                     s["id"], v["numero_votacion"]),
                )
            conn.commit()

        conn.execute("DELETE FROM vote_program_matches")
        conn.execute("UPDATE votes SET resumen=NULL, que_cambia=NULL, enriched_at=NULL")
        # Julio vuelve a la cola; mayo y junio quedan archivados sin republicar.
        # El corte va por session_date de la sesión, no por el campo fecha del voto
        # (que viene del XML en formato "14/7/2026" y no ordena lexicográficamente).
        conn.execute("""
            UPDATE votes SET published = 1
            WHERE id IN (
                SELECT v.id FROM votes v JOIN sessions s ON v.session_id = s.id
                WHERE s.session_date < ?
            )""", (CORTE_JULIO + "01",))
        conn.execute("""
            UPDATE votes SET published = 0
            WHERE id IN (
                SELECT v.id FROM votes v JOIN sessions s ON v.session_id = s.id
                WHERE s.session_date >= ?
            )""", (CORTE_JULIO + "01",))
        conn.execute("UPDATE boe_entries SET published = 1 WHERE fecha < ?",
                     (CORTE_JULIO + "01",))
        conn.execute("UPDATE boe_entries SET published = 0 WHERE fecha >= ?",
                     (CORTE_JULIO + "01",))

        if dry_run:
            conn.rollback()
            print("\nDry run: nada guardado.")
        else:
            conn.commit()

        pendientes = conn.execute(
            "SELECT COUNT(*) FROM votes WHERE published=0 AND clase='sustantiva'"
        ).fetchone()[0]
        print(f"\nSustantivas pendientes de publicar: {pendientes}")
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
