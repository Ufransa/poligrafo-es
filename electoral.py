# electoral.py
"""Motor de datos de la web electoral del 29N. Ver docs/superpowers/specs/2026-10-07-web-electoral-29n-design.md."""
import argparse
from pathlib import Path

from src.electoral import db as edb
from src.electoral import exportar, votaciones

RAIZ = Path(__file__).resolve().parent


def cmd_descargar(a, conn):
    destino = Path(a.zips) if a.zips else RAIZ / "electoral_data" / "zips"
    if not a.zips:
        hechos = {r["nombre"] for r in conn.execute("SELECT nombre FROM zips")}
        votaciones.descargar_legislatura(destino, hechos)
    mapa = votaciones.cargar_mapa(RAIZ)
    for ruta in sorted(destino.glob("*.zip")):
        for v in votaciones.leer_zip(ruta):
            votaciones.guardar(conn, v, mapa)
        conn.execute("INSERT OR IGNORE INTO zips VALUES (?,?,?)", (ruta.name, "", ""))
    conn.commit()


def cmd_exportar(a, conn):
    exportar.escribir(exportar.construir(conn, RAIZ), Path(a.salida))


def main():
    p = argparse.ArgumentParser(prog="electoral")
    sub = p.add_subparsers(dest="cmd", required=True)
    for nombre in ("descargar", "exportar"):
        s = sub.add_parser(nombre)
        s.add_argument("--db", default=str(RAIZ / "electoral.db"))
    sub.choices["descargar"].add_argument("--zips", help="carpeta con ZIPs ya bajados (no descarga nada)")
    sub.choices["exportar"].add_argument("--salida", default=str(RAIZ / "datos.json"))
    a = p.parse_args()
    conn = edb.conectar(Path(a.db))
    {"descargar": cmd_descargar, "exportar": cmd_exportar}[a.cmd](a, conn)


if __name__ == "__main__":
    main()
