import json

from dak_maintenance.cli import main


def test_triage_single_dep_still_works(tmp_path, capsys):
    changelog = tmp_path / "changelog.txt"
    changelog.write_text("Fixed a typo and improved docs.")
    rc = main([
        "triage", "--package", "pkg", "--from", "1.0.0", "--to", "1.0.1",
        "--ci-passed", "true", "--changelog-file", str(changelog),
    ])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["packages"] == ["pkg"]
    assert out["decision"]["action"] == "auto-merge"


def test_triage_deps_json_combines_worst_case(capsys):
    deps = [
        {"package": "a", "from": "1.0.0", "to": "1.0.1"},
        {"package": "b", "from": "1.0.0", "to": "2.0.0"},
    ]
    rc = main([
        "triage", "--deps-json", json.dumps(deps), "--ci-passed", "true",
    ])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["packages"] == ["a", "b"]
    assert out["bump"] == "major"
    assert out["decision"]["action"] == "needs-human-review"
    assert len(out["per_dependency"]) == 2
    assert "内訳" in out["decision"]["reason"]


def test_triage_missing_package_and_deps_json_errors():
    try:
        main(["triage", "--ci-passed", "true"])
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 2
