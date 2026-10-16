import asyncio
import base64
import json

import pytest

from mcp_bridge_common.testing import FakeBridge, PNG_1PX
from nw_mcp import snippets
from nw_mcp.server import create_server

mcp_client = pytest.importorskip("mcp").__dict__.get("Client")


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    discovery = tmp_path / "bridge.json"
    monkeypatch.setenv("NW_MCP_DISCOVERY", str(discovery))
    monkeypatch.delenv("NW_MCP_URL", raising=False)
    monkeypatch.delenv("NW_MCP_TOKEN", raising=False)
    with FakeBridge() as fb:
        fb.write_discovery(discovery)
        yield fb


def run_with_client(coro_fn):
    if mcp_client is None:
        pytest.skip("mcp.Client (in-process) chi co tu mcp 2.x")

    async def runner():
        async with mcp_client(create_server()) as client:
            return await coro_fn(client)

    return asyncio.run(runner())


def call(name, args=None):
    return run_with_client(lambda c: c.call_tool(name, args or {}))


def payload(res):
    assert not res.is_error, res.content[0].text
    return res.structured_content or json.loads(res.content[0].text)


def script_ok(value):
    return {"ok": True, "result": {"compiled": True, "return_value": value, "output": ""}}


def script_fail(*errors):
    return {"ok": True, "result": {"compiled": False, "errors": list(errors)}}


EXPECTED = {
    "nw_status", "nw_tree", "nw_search", "nw_get_item", "nw_get_selection", "nw_select", "nw_open_file",
    "nw_save_file", "nw_set_visibility", "nw_set_appearance", "nw_list_viewpoints", "nw_save_viewpoint",
    "nw_apply_viewpoint", "nw_focus_selection", "nw_capture_view", "nw_list_selection_sets",
    "nw_create_selection_set", "nw_select_selection_set", "nw_clash_list_tests", "nw_clash_create_test",
    "nw_clash_run_test", "nw_clash_results", "nw_clash_report", "nw_timeliner_tasks", "nw_explore_api",
    "nw_run_csharp", "nw_bridge_methods",
}


def test_tools_registered_and_annotated(bridge):
    tools = run_with_client(lambda c: c.list_tools())
    by_name = {t.name: t for t in tools.tools}
    assert set(by_name) == EXPECTED
    assert by_name["nw_open_file"].annotations.destructive_hint is True
    assert by_name["nw_search"].annotations.read_only_hint is True
    assert "{{" not in (by_name["nw_search"].description or "")      # dau { } da duoc format dung
    assert '{"refs"' in by_name["nw_select"].description


def test_typed_tools_route_to_core_rpc(bridge):
    payload(call("nw_status"))
    payload(call("nw_tree", {"ref": "0/3", "limit": 50}))
    payload(call("nw_get_item", {"ref": "0/3/12"}))
    payload(call("nw_select", {"selector": {"refs": ["0/3/12"]}}))
    assert [m for m, _ in bridge.calls] == ["nw.doc.info", "nw.tree", "nw.item.get", "nw.selection.set"]
    assert bridge.calls[1][1]["ref"] == "0/3" and bridge.calls[3][1]["selector"] == {"refs": ["0/3/12"]}


def test_search_requires_a_criterion_and_forwards_where(bridge):
    res = call("nw_search", {"limit": 5})
    assert res.is_error and "ít nhất một tiêu chí" in res.content[0].text
    assert bridge.calls == []
    where = [{"category": "Item", "property": "Name", "op": "contains", "value": "Dầm"}]
    payload(call("nw_search", {"where": where, "geometry_only": True, "select": True}))
    method, params = bridge.calls[-1]
    assert method == "nw.search" and params["where"] == where and params["select"] is True


def test_visibility_sends_snippet_with_args(bridge):
    bridge.respond = lambda m, p: script_ok({"action": "hide", "items": 3})
    out = payload(call("nw_set_visibility", {"action": "hide", "selector": {"selection": True}}))
    assert out == {"action": "hide", "items": 3}
    method, params = bridge.calls[-1]
    assert method == "script.csharp" and "SetHidden" in params["code"]
    assert params["args"] == {"action": "hide", "selector": {"selection": True}}


def test_visibility_needs_selector_except_reset(bridge):
    assert call("nw_set_visibility", {"action": "hide"}).is_error
    bridge.respond = lambda m, p: script_ok({"action": "reset_all"})
    assert not call("nw_set_visibility", {"action": "reset_all"}).is_error


@pytest.mark.parametrize("args,msg", [
    ({"selector": {"selection": True}, "color": [300, 0, 0]}, "0-255"),
    ({"selector": {"selection": True}, "color": [1, 2]}, "0-255"),
    ({"selector": {"selection": True}, "transparency": 1.5}, "0..1"),
    ({"color": [1, 2, 3]}, "selector"),
])
def test_appearance_validation(bridge, args, msg):
    res = call("nw_set_appearance", args)
    assert res.is_error and msg in res.content[0].text
    assert bridge.calls == []


def test_compile_error_lists_diagnostics_and_hints_explore_api(bridge):
    bridge.respond = lambda m, p: script_fail("(3,5): error CS1061: 'Document' does not contain a definition for 'SaveFile'")
    res = call("nw_save_file", {"path": "C:/m.nwd"})
    assert res.is_error
    text = res.content[0].text
    assert "CS1061" in text and "nw_explore_api" in text and "lưu file" in text


def test_clash_tries_using_variants_until_one_compiles(bridge):
    attempts = []

    def respond(method, params):
        header = [ln for ln in params["code"].split("\n") if ln.startswith("using Autodesk")]
        attempts.append("|".join(header))
        if len(attempts) < 3:
            return script_fail("error CS0234: namespace 'Autodesk.Navisworks.Api.DocumentParts' does not exist")
        return script_ok({"tests": [{"name": "A vs B", "summary": {"total": "12"}}]})

    bridge.respond = respond
    out = payload(call("nw_clash_list_tests"))
    assert out["tests"][0]["name"] == "A vs B"
    assert len(attempts) == 3 and len(set(attempts)) == 3          # 3 dong using khac nhau


def test_clash_create_maps_test_type_and_forwards_selectors(bridge):
    bridge.respond = lambda m, p: script_ok({"created": "MEP-KC", "ran": True})
    sel_a = {"selection_set": "Kết cấu"}
    sel_b = {"where": [{"category": "Item", "property": "Layer", "op": "equals", "value": "MEP"}]}
    payload(call("nw_clash_create_test", {"name": "MEP-KC", "selection_a": sel_a, "selection_b": sel_b,
                                          "test_type": "clearance", "tolerance_m": 0.05}))
    params = bridge.calls[-1][1]
    assert params["args"]["test_type"] == "Clearance" and params["args"]["tolerance_m"] == 0.05
    assert params["args"]["selection_a"] == sel_a and params["args"]["selection_b"] == sel_b
    assert params["timeout_s"] >= 1800
    assert call("nw_clash_create_test", {"name": "x", "selection_a": sel_a, "selection_b": sel_b,
                                         "tolerance_m": -1}).is_error


CLASH_DATA = {
    "test": "KC-MEP", "total_results": 3, "matched": 3, "returned": 3,
    "results": [
        {"name": "Clash1", "status": "New", "distance_m": -0.0123, "point_m": [10.5, 20.25, 3.0],
         "item1": {"ref": "0/1/2", "name": "Dầm D1", "path": "Tầng 1 > Dầm D1"},
         "item2": {"ref": "1/5", "name": "Ống <gió>", "path": "MEP > Ống <gió>"}},
        {"name": "Clash2", "status": "Resolved", "distance_m": -0.05, "point_m": [1, 2, 3], "item1": {}, "item2": None},
        {"name": "Clash3", "status": "New", "item1": {"name": "A"}, "item2": {"name": "B"}},
    ],
}


def test_clash_report_csv_and_html(bridge, tmp_path):
    bridge.respond = lambda m, p: script_ok(CLASH_DATA)
    csv_path = tmp_path / "out" / "bc.csv"
    out = payload(call("nw_clash_report", {"test": "KC-MEP", "path": str(csv_path), "format": "csv"}))
    assert out["written"] == 3 and out["file"] == str(csv_path)
    raw = csv_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")                                   # BOM de Excel doc dung tieng Viet
    text = raw.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("STT,Tên va chạm,Trạng thái")
    assert "Clash1,New,-0.0123,10.5,20.25,3.0,Dầm D1,Tầng 1 > Dầm D1,Ống <gió>" in text

    html_path = tmp_path / "bc.html"
    payload(call("nw_clash_report", {"test": "KC-MEP", "path": str(html_path), "format": "html"}))
    page = html_path.read_text(encoding="utf-8")
    assert "&lt;gió&gt;" in page and "<gió>" not in page                     # thoat HTML
    assert "Tổng: <b>3</b>" in page and "New: <b>2</b>" in page and "Resolved: <b>1</b>" in page


def test_capture_view_prefers_viewport_then_falls_back_to_window(bridge):
    png = base64.b64encode(PNG_1PX).decode()

    def viewport_ok(method, params):
        return script_ok({"method": "RenderToImage", "width": 1, "height": 1, "data_base64": png})

    bridge.respond = viewport_ok
    res = call("nw_capture_view")
    assert res.content[0].type == "image" and [m for m, _ in bridge.calls] == ["script.csharp"]

    bridge.calls.clear()

    def viewport_fails_then_window(method, params):
        if method == "script.csharp":
            return script_fail("error: khong co ham tra ve anh")
        return {"ok": True, "result": {"mime_type": "image/png", "data_base64": png}}

    bridge.respond = viewport_fails_then_window
    res = call("nw_capture_view", {"method": "screen"})
    assert res.content[0].type == "image"
    assert [m for m, _ in bridge.calls] == ["script.csharp", "view.capture"]
    assert bridge.calls[-1][1]["method"] == "screen"

    bridge.calls.clear()
    res = call("nw_capture_view", {"mode": "viewport"})        # ep viewport, loi thi bao loi
    assert res.is_error


def test_run_csharp_passes_args_and_guide_resource(bridge):
    bridge.respond = lambda m, p: script_ok(42)
    out = payload(call("nw_run_csharp", {"code": "return Arg<int>(\"n\");", "args": {"n": 42}}))
    assert bridge.calls[-1][1]["args"] == {"n": 42} and out is not None
    res = run_with_client(lambda c: c.read_resource("nw://guide"))
    text = res.contents[0].text
    assert "ref" in text and "nw_search" in text and "otd_" not in text


# --------------------------------------------------------------------------- cu phap snippet C#
def _snippet_cases():
    cases = []
    for name in dir(snippets):
        if not name.isupper() or name.endswith("HEADERS"):
            continue
        header = ""
        if name.startswith("CLASH"):
            header = snippets.CLASH_HEADERS[0]
        elif name.startswith("TIMELINER"):
            header = snippets.TIMELINER_HEADERS[0]
        cases.append(pytest.param(header + getattr(snippets, name), id=name))
    return cases


def _error_nodes(node, src, out):
    if node.type == "ERROR" or node.is_missing:
        out.append(src[node.start_byte:node.start_byte + 70].decode(errors="replace"))
    for child in node.children:
        _error_nodes(child, src, out)


@pytest.mark.parametrize("code", _snippet_cases())
def test_snippets_are_syntactically_valid_csharp(code):
    ts = pytest.importorskip("tree_sitter")
    tcs = pytest.importorskip("tree_sitter_c_sharp")
    parser = ts.Parser(ts.Language(tcs.language()))
    src = code.encode()
    errors = []
    _error_nodes(parser.parse(src).root_node, src, errors)
    assert not errors, errors[:3]


def test_syntax_checker_actually_detects_errors():
    ts = pytest.importorskip("tree_sitter")
    tcs = pytest.importorskip("tree_sitter_c_sharp")
    parser = ts.Parser(ts.Language(tcs.language()))
    src = b"var x = new JObject { [\"a\"] = 1 ;\nreturn x"
    errors = []
    _error_nodes(parser.parse(src).root_node, src, errors)
    assert errors


def test_snippets_do_not_use_format_braces_unescaped():
    # snippet la chuoi thuan (khong .format) - phong khi ai do doi sang template
    assert "{{" not in snippets.FILE_OPEN
