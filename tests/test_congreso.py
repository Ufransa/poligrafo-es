import pytest
from pathlib import Path
from src.congreso import parse_vote_xml, aggregate_group_votes

FIXTURE_XML = (Path(__file__).parent / "fixtures" / "vote_session.xml").read_text(encoding="utf-8")


def test_parse_vote_xml_extracts_metadata():
    vote = parse_vote_xml(FIXTURE_XML)
    assert vote["sesion"] == 177
    assert vote["numero_votacion"] == 1
    assert vote["titulo"] == "Proposición de Ley de regularización extraordinaria"
    assert "arraigo laboral" in vote["texto_expediente"]


def test_parse_vote_xml_aggregates_by_group():
    vote = parse_vote_xml(FIXTURE_XML)
    groups = vote["group_votes"]

    assert groups["GP"]["voto"] == "No"
    assert groups["GS"]["voto"] == "Sí"
    assert groups["GSUMAR"]["voto"] == "Sí"
    assert groups["GVOX"]["voto"] == "No"


def test_divided_group_detected_when_dissent_exceeds_10_percent():
    # GP has 3 No + 1 Sí = 25% dissent → divided
    vote = parse_vote_xml(FIXTURE_XML)
    assert vote["group_votes"]["GP"]["divided"] is True


def test_unanimous_group_not_marked_divided():
    # GS has 3 Sí, no dissent
    vote = parse_vote_xml(FIXTURE_XML)
    assert vote["group_votes"]["GS"]["divided"] is False


def test_aggregate_group_votes_majority_wins():
    raw = [
        {"grupo": "GP", "voto": "No"},
        {"grupo": "GP", "voto": "No"},
        {"grupo": "GP", "voto": "Sí"},
        {"grupo": "GS", "voto": "Sí"},
    ]
    result = aggregate_group_votes(raw)
    assert result["GP"]["voto"] == "No"
    assert result["GP"]["total"] == 3
    assert result["GS"]["voto"] == "Sí"
