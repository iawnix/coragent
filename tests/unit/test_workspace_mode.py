import json
import pytest
from research_agent.research.workspace import (
    initialize_workspace, admit_research_workspace,
    validate_workspace_manifest, DIRECTORIES, WorkspaceModeError,
)
from research_agent.application.memory_context import read
from research_agent.research.doctor import inspect_workspace


def test_workspace_admission_and_identity(tmp_path):
    manifest = initialize_workspace(tmp_path, "workspace_test", "research")
    assert manifest["state"] == "admission_pending"
    with pytest.raises(WorkspaceModeError): read(tmp_path)
    admit_research_workspace(tmp_path)
    assert read(tmp_path)["nodes"] == []
    assert read(tmp_path)["schema_version"] == "research-snapshot/3"
    assert inspect_workspace(tmp_path)["valid"]
    with pytest.raises(WorkspaceModeError): initialize_workspace(tmp_path, "different", "research")
    with pytest.raises(WorkspaceModeError): initialize_workspace(tmp_path, "workspace_test", "invalid")


def test_nested_and_symlink_workspaces_rejected(tmp_path):
    root=tmp_path/"outer"
    initialize_workspace(root, "outer", "research")
    with pytest.raises(WorkspaceModeError): initialize_workspace(root/"inner", "inner", "research")
    link=tmp_path/"link"; link.symlink_to(root)
    with pytest.raises(WorkspaceModeError): admit_research_workspace(link)


def test_new_workspace_omits_retired_directories(tmp_path):
    manifest = initialize_workspace(tmp_path, "compact", "research")
    assert manifest["directories"] == list(DIRECTORIES)
    assert (tmp_path / "inputs").is_dir()
    assert not (tmp_path / "logs").exists()
    assert not (tmp_path / "environments").exists()


@pytest.mark.parametrize("entry", ["initialize", "validate", "admit"])
def test_old_directory_contract_is_rejected_without_migration(tmp_path, entry):
    manifest = initialize_workspace(tmp_path, "old", "research")
    manifest["directories"] = ["inputs", "artifacts", "runs", "logs", "research", "operations", "environments", "reports"]
    path = tmp_path / "workspace_manifest.json"
    path.write_text(json.dumps(manifest))
    for name in ("logs", "environments"):
        (tmp_path / name).mkdir()
    original = path.read_bytes()
    with pytest.raises(WorkspaceModeError, match="workspace_directories_mismatch"):
        if entry == "initialize":
            initialize_workspace(tmp_path, "old", "research")
        elif entry == "validate":
            validate_workspace_manifest(manifest, tmp_path)
        else:
            admit_research_workspace(tmp_path)
    assert path.read_bytes() == original
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "environments").is_dir()
