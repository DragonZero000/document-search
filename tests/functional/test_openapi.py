import json

from scripts.export_openapi import DOCS_PATH, render


def test_docs_json_matches_app_openapi():
    assert DOCS_PATH.exists(), "docs.json is missing: run `python -m scripts.export_openapi`"
    assert json.loads(DOCS_PATH.read_text(encoding="utf-8")) == json.loads(render()), (
        "docs.json is out of date: run `python -m scripts.export_openapi`"
    )


def test_docs_json_describes_endpoints():
    spec = json.loads(DOCS_PATH.read_text(encoding="utf-8"))

    assert {"/documents/search", "/documents/{id}", "/health"} <= spec["paths"].keys()
    assert set(spec["components"]["schemas"]["Document"]["properties"]) == {
        "id",
        "rubrics",
        "text",
        "created_date",
    }
    search = spec["paths"]["/documents/search"]["get"]["responses"]
    delete = spec["paths"]["/documents/{id}"]["delete"]["responses"]
    assert {"200", "422", "503"} <= search.keys()
    assert {"204", "404", "422", "503"} <= delete.keys()
