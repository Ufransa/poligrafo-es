def _cargar(cli, zips):
    cli("descargar", "--zips", zips)
    return cli("exportar")


def _buscar(datos, texto, subtipo=None):
    return [v for v in datos["votaciones"]
            if texto.lower() in v["expediente"].lower() and (subtipo is None or v["subtipo"] == subtipo)]


def test_una_avocacion_sale_excluida_por_tramite(cli, zips):
    datos = _cargar(cli, zips)
    avoc = [v for v in datos["votaciones"] if "avocación" in v["expediente"].lower()]
    assert avoc and all(v["excluida_tramite"] for v in avoc)


def test_la_devolucion_de_la_ley_de_lobbies_se_marca_como_devolucion(cli, zips):
    datos = _cargar(cli, zips)
    v = _buscar(datos, "grupos de interés", "devolucion")
    assert v and not v[0]["excluida_tramite"]


def test_el_texto_alternativo_no_se_trata_como_devolucion(cli, zips):
    datos = _cargar(cli, zips)
    assert _buscar(datos, "amnistía", "texto_alternativo")
    assert not _buscar(datos, "texto alternativo", "devolucion")


def test_en_un_decreto_ley_cuenta_la_convalidacion_y_no_la_tramitacion(cli, zips):
    datos = _cargar(cli, zips)
    rdl = [v for v in datos["votaciones"] if v["clave_iniciativa"] == "real decreto-ley 3/2026"]
    convalidacion = [v for v in rdl if not v["excluida_tramite"]]
    tramitacion = [v for v in rdl if v["excluida_tramite"]]
    assert len(convalidacion) == 1 and convalidacion[0]["tipo"].startswith("Convalidación")
    assert tramitacion, "la votación de tramitación como proyecto de ley debe existir y estar excluida"


def test_los_diputados_del_mixto_votan_con_su_partido(cli, zips):
    datos = _cargar(cli, zips)
    v = _buscar(datos, "grupos de interés", "devolucion")[0]
    for partido in ("Podemos", "BNG", "CC", "UPN"):
        assert partido in v["votos"], partido
    assert "Mixto" not in v["votos"]


def test_un_independiente_no_cuenta_para_ningun_partido(cli, zips):
    datos = _cargar(cli, zips)
    v = _buscar(datos, "grupos de interés", "devolucion")[0]   # 25/3/2025: Ábalos ya fuera del PSOE
    assert v["votos"]["PSOE"]["voto"] in ("Sí", "No", "Abstención")
    assert None not in v["votos"] and "null" not in v["votos"]


def test_cada_votacion_lleva_sus_fuentes(cli, zips):
    datos = _cargar(cli, zips)
    for v in datos["votaciones"]:
        assert v["url_xml"].startswith("https://www.congreso.es/webpublica/opendata/votaciones/Leg15/")
        assert "targetDate=" in v["url_sesion"]


def test_la_descarga_es_reanudable(cli, zips):
    cli("descargar", "--zips", zips)
    n1 = len(cli("exportar")["votaciones"])
    cli("descargar", "--zips", zips)
    assert len(cli("exportar")["votaciones"]) == n1
