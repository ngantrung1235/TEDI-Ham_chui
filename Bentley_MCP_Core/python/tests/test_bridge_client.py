import json

import pytest

from bentley_mcp_core import BridgeClient, BridgeError, BridgeUnavailable, ProductConfig
from bentley_mcp_core.testing import FakeBridge

PRODUCT = ProductConfig(code="TST", name="San pham thu", version="0", tool_prefix="tst", addin_name="TSTMcpBridge",
                        keyin="TSTMCP", env_prefix="TST_MCP_", discovery_folder="TSTMcp")


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    discovery = tmp_path / "bridge.json"
    monkeypatch.setenv("TST_MCP_DISCOVERY", str(discovery))
    monkeypatch.delenv("TST_MCP_URL", raising=False)
    monkeypatch.delenv("TST_MCP_TOKEN", raising=False)
    with FakeBridge() as fb:
        fb.write_discovery(discovery)
        fb.discovery = discovery
        yield fb


def test_call_sends_token_and_timeout(bridge):
    result = BridgeClient(PRODUCT).call("session.info", {"a": 1}, timeout_s=7)
    assert result["active_file"].endswith("model.dgn")
    method, params = bridge.calls[-1]
    assert method == "session.info" and params == {"a": 1, "_timeout_s": 7}


def test_bridge_error_is_raised_with_type(bridge):
    with pytest.raises(BridgeError, match="ArgumentException: Khong tim thay element id=999"):
        BridgeClient(PRODUCT).call("elements.get", {"id": 999})


def test_token_refresh_after_restart(bridge):
    # San pham khoi dong lai: token moi, file discovery duoc ghi lai sau lan doc dau.
    client = BridgeClient(PRODUCT)
    old = json.loads(bridge.discovery.read_text())
    bridge.token = "tok-new"
    assert old["token"] != bridge.token
    with pytest.raises(BridgeError):
        client.call("ping")                       # van token cu -> 401 ca 2 lan
    bridge.write_discovery(bridge.discovery)
    assert client.call("ping") == {"echo": "ping"}


def test_unavailable_message_names_product_addin(tmp_path, monkeypatch):
    monkeypatch.setenv("TST_MCP_DISCOVERY", str(tmp_path / "khong_co.json"))
    monkeypatch.delenv("TST_MCP_URL", raising=False)
    with pytest.raises(BridgeUnavailable, match="mdl load TSTMcpBridge"):
        BridgeClient(PRODUCT).call("ping")


def test_env_endpoint_override(bridge, monkeypatch):
    monkeypatch.setenv("TST_MCP_URL", f"http://127.0.0.1:{bridge.port}/")
    monkeypatch.setenv("TST_MCP_TOKEN", bridge.token)
    monkeypatch.setenv("TST_MCP_DISCOVERY", "/khong/ton/tai.json")
    assert BridgeClient(PRODUCT).health()["name"] == "FakeMcpBridge"


def test_products_are_isolated(bridge, monkeypatch):
    # Discovery cua san pham khac (env prefix khac) khong duoc dung nham.
    other = ProductConfig(code="OTH", name="Khac", version="0", tool_prefix="oth", addin_name="OTHMcpBridge",
                          keyin="OTHMCP", env_prefix="OTH_MCP_", discovery_folder="OTHMcp")
    monkeypatch.setenv("OTH_MCP_DISCOVERY", str(bridge.discovery.parent / "oth.json"))
    with pytest.raises(BridgeUnavailable, match="OTHMcpBridge"):
        BridgeClient(other).call("ping")
