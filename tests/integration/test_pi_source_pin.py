from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pi_source_pin_is_explicit_and_uses_latest_durable_runtime() -> None:
    pin = json.loads((ROOT / "packaging/coragent_packaging/pi/source.json").read_text(encoding="utf-8"))
    assert pin == {
        "component": "pi-sdk-runtime",
        "repository": "https://github.com/earendil-works/pi.git",
        "tag": "v1.4.0",
        "commit": "4a080252f06caf63a525d7873c5d94d3c23887e0",
    }
    patch = "\n".join(path.read_text(encoding="utf-8") for path in sorted((ROOT / "packaging/coragent_packaging/pi/patches").glob("*.patch")))
    assert "prepareContext" in patch
    assert "prepareSummary" in patch
    assert "CORAGENT_CREDENTIALS_FILE" in patch
    assert "promptCacheKeyMode" in patch
    assert "src/experimental/" not in patch
    assert "@earendil-works/pi-server" not in patch


def test_prepare_pi_source_verifies_a_matching_checkout() -> None:
    configured = os.environ.get("CORAGENT_TEST_PI_RUNTIME_ROOT")
    if not configured or not Path(configured).is_dir():
        return
    result = subprocess.run(
        ["python3", str(ROOT / "packaging/coragent_packaging/pi/prepare.py"), "--verify", configured],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_prepare_pi_source_rejects_incorrect_package_version(monkeypatch) -> None:
    import pytest
    from coragent_packaging.pi import prepare
    source = Path(os.environ["CORAGENT_TEST_PI_RUNTIME_ROOT"])
    descriptor = {**prepare.pin(), "tag": "v0.0.0"}
    monkeypatch.setattr(prepare, "pin", lambda: descriptor)
    with pytest.raises(prepare.PiSourceError, match="package version"):
        prepare.verify(source)


def test_prepare_pi_source_rejects_unpatched_checkout(tmp_path) -> None:
    source = tmp_path / "pi"
    source.mkdir()
    (source / ".git").mkdir()
    from coragent_packaging.pi import prepare as prepare_pi_source
    original = prepare_pi_source.git
    try:
        prepare_pi_source.git = lambda *_args: prepare_pi_source.pin()["commit"]
        try:
            prepare_pi_source.verify(source)
        except prepare_pi_source.PiSourceError as error:
            assert "missing" in str(error)
        else:
            raise AssertionError("unpatched checkout was accepted")
    finally:
        prepare_pi_source.git = original


def test_patch_groups_are_idempotent_and_reject_partial_application(tmp_path, monkeypatch) -> None:
    """Use a real Git checkout; do not let marker comments stand in for patches."""
    from coragent_packaging.pi import prepare

    source = tmp_path / "source"
    source.mkdir()
    def git(*args):
        return subprocess.run(["git", "-C", str(source), *args], check=True, text=True, capture_output=True).stdout.strip()
    git("init")
    (source / "worker.txt").write_text("one\ntwo\nthree\nfour\nfive\nsix\nseven\neight\nnine\nten\n")
    git("add", "worker.txt")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
    monkeypatch.setattr(prepare, "pin", lambda: {"commit": git("rev-parse", "HEAD")})
    (source / "worker.txt").write_text("ONE\ntwo\nthree\nfour\nfive\nsix\nseven\neight\nnine\nTEN\n")
    patch = tmp_path / "changes.patch"
    patch.write_text(git("diff") + "\n")
    monkeypatch.setattr(prepare, "patches", lambda: [patch])
    (source / "worker.txt").write_text(git("show", "HEAD:worker.txt") + "\n")
    prepare.apply_patch(source)
    assert prepare.patch_check(source, patch, reverse=True)
    prepare.apply_patch(source)
    assert (source / "worker.txt").read_text().startswith("ONE\n")
    partial = (source / "worker.txt").read_text().replace("TEN\n", "ten\n")
    (source / "worker.txt").write_text(partial)
    import pytest
    with pytest.raises(prepare.PiSourceError, match="partially applied"):
        prepare.apply_patch(source)
    assert (source / "worker.txt").read_text() == partial


def test_overlapping_patch_stack_is_idempotent(tmp_path, monkeypatch) -> None:
    from coragent_packaging.pi import prepare

    source = tmp_path / "source"
    source.mkdir()
    def git(*args):
        return subprocess.run(["git", "-C", str(source), *args], check=True, text=True, capture_output=True).stdout.strip()
    git("init")
    worker = source / "worker.txt"
    worker.write_text("one\ntwo\nthree\n")
    git("add", "worker.txt")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
    monkeypatch.setattr(prepare, "pin", lambda: {"commit": git("rev-parse", "HEAD")})
    first = tmp_path / "first.patch"
    worker.write_text("ONE\ntwo\nthree\n")
    first.write_text(git("diff") + "\n")
    git("add", "worker.txt")
    second = tmp_path / "second.patch"
    worker.write_text("ONE AGAIN\ntwo\nthree\n")
    second.write_text(git("diff") + "\n")
    monkeypatch.setattr(prepare, "patches", lambda: [first, second])
    worker.write_text("one\ntwo\nthree\n")
    prepare.apply_patch(source)
    assert worker.read_text() == "ONE AGAIN\ntwo\nthree\n"
    assert not prepare.patch_check(source, first, reverse=True)
    assert prepare.verify_patches(source)
    prepare.apply_patch(source)
    assert worker.read_text() == "ONE AGAIN\ntwo\nthree\n"
