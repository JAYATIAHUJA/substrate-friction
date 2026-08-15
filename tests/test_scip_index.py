from pathlib import Path

import pytest

from friction.scip import index as I


def test_command_always_passes_project_version(tmp_path):
    cmd = I.build_command(tmp_path, tmp_path / "o.scip", "django", "4.2", "django")
    assert "--project-version" in cmd
    assert cmd[cmd.index("--project-version") + 1] == "4.2"


def test_command_targets_only_the_named_package(tmp_path):
    cmd = I.build_command(tmp_path, tmp_path / "o.scip", "django", "4.2", "django")
    assert "--target-only" in cmd
    assert cmd[cmd.index("--target-only") + 1] == "django"


def test_command_omits_target_when_none(tmp_path):
    cmd = I.build_command(tmp_path, tmp_path / "o.scip", "p", "1", None)
    assert "--target-only" not in cmd


def test_command_writes_output_outside_the_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    out = tmp_path / "out" / "o.scip"
    cmd = I.build_command(repo, out, "p", "1", None)
    written = Path(cmd[cmd.index("--output") + 1])
    assert written.is_absolute()
    assert repo not in written.parents


def test_index_repo_raises_when_binary_missing(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("scip-python")
    with pytest.raises(I.ScipUnavailable):
        I.index_repo(tmp_path, tmp_path / "o.scip", runner=boom)


def test_index_repo_raises_on_nonzero_exit(tmp_path):
    class R:
        returncode = 1
        stdout = b""
        stderr = b"normalizeNameOrVersion"
    with pytest.raises(I.ScipUnavailable) as exc:
        I.index_repo(tmp_path, tmp_path / "o.scip", runner=lambda *a, **k: R())
    assert "normalizeNameOrVersion" in str(exc.value)


@pytest.mark.engine
def test_index_real_fixture_package(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "scip_pkg"
    out = tmp_path / "fixture.scip"
    res = I.index_repo(fixture, out, name="scip_pkg", version="0.0.1")
    assert res.path.exists()
    assert res.documents > 0
    assert res.occurrences > 0
