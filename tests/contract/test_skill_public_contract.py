"""Keep the generated developer tool index synchronized with runtime tool contracts."""
from pathlib import Path
import subprocess


def test_generated_model_tool_index_is_current():
    root = Path(__file__).resolve().parents[2]
    subprocess.run(["node", str(root / "tools/update_public_contract.mjs"), "--check"], cwd=root, check=True, capture_output=True, text=True)
