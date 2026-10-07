import json
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
FIX = RAIZ / "tests" / "fixtures" / "electoral"


@pytest.fixture
def cli(tmp_path):
    """Ejecuta electoral.py con una base y una salida temporales y devuelve datos.json ya leído."""
    db = tmp_path / "electoral.db"
    salida = tmp_path / "datos.json"

    def run(*args, env=None):
        cmd = [sys.executable, str(RAIZ / "electoral.py"), *args, "--db", str(db)]
        if args[0] == "exportar":
            cmd += ["--salida", str(salida)]
        r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", env=env)
        assert r.returncode == 0, r.stderr
        return json.loads(salida.read_text(encoding="utf-8")) if args[0] == "exportar" else r.stdout

    run.db = db
    return run


@pytest.fixture
def zips():
    return str(FIX / "zips")
