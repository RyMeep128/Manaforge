"""Private bootstrap validation and cleanup for the live-engine probe tools."""

import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "native_metadata_tool",
    Path(__file__).resolve().parents[3] / "tools/play_native_metadata.py",
)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


@pytest.mark.parametrize("oversized", [False, True])
def test_invalid_context_is_consumed_or_bounded_without_provisioning(
    tmp_path, monkeypatch, oversized
):
    context = tmp_path / "context.json"
    context.write_text("x" * 4097 if oversized else json.dumps({"game": "invalid"}))
    server_input = io.StringIO()
    gateway = SimpleNamespace(stdin=io.BytesIO(), poll=lambda: None)
    server = SimpleNamespace(stdin=server_input, poll=lambda: None)
    cleared = []

    class ObservedKey(bytearray):
        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            cleared.append(not any(self))

    monkeypatch.setattr(tool, "bytearray", ObservedKey, raising=False)
    with pytest.raises(tool.transport.ProofError, match="METADATA_STARTUP_INVALID"):
        tool.provision_metadata(gateway, server, tmp_path, context, "a" * 64)
    assert cleared == [True]
    assert server_input.getvalue() == ""
    assert context.exists() is oversized


def test_gateway_exit_aborts_provisioning(tmp_path):
    gateway = SimpleNamespace(stdin=io.BytesIO(), poll=lambda: 2)
    server_input = io.StringIO()
    server = SimpleNamespace(stdin=server_input, poll=lambda: None)
    with pytest.raises(tool.transport.ProofError, match="METADATA_STARTUP_FAILED"):
        tool.provision_metadata(
            gateway, server, tmp_path, tmp_path / "missing.json", "a" * 64
        )
    assert server_input.getvalue() == ""
