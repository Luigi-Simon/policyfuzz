"""Published Judge examples must remain identical to their authored source."""

from app.v2.export_judge import DEFAULT_OUTPUT, render_contracts


def test_judge_artifacts_match_exporter():
    actual = {
        str(path.relative_to(DEFAULT_OUTPUT)): path.read_bytes()
        for path in DEFAULT_OUTPUT.rglob("*")
        if path.is_file()
    }
    assert actual == render_contracts()
