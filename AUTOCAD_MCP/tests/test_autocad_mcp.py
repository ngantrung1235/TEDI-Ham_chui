import asyncio
import math

import ezdxf
import pytest

import fake_acad
from autocad_mcp.backends.com import ComBackend
from autocad_mcp.backends.dxf import DxfBackend
from autocad_mcp.com_worker import ComWorker, with_retry
from autocad_mcp.engineering import drawings
from autocad_mcp.versions import release_name


# -- versions & worker ---------------------------------------------------------------------------------
def test_release_names():
    assert release_name("24.3s (LMS Tech)") == "AutoCAD 2024"
    assert release_name("15.0s") == "AutoCAD 2000"
    assert release_name("25.1") == "AutoCAD 2026"
    assert release_name("99.0").startswith("AutoCAD (version")


def test_retry_on_busy():
    calls = {"n": 0}

    class Busy(Exception):
        pass

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Busy(-2147418111, "Call was rejected by callee.")
        return "ok"

    assert with_retry(flaky, delay=0.001) == "ok" and calls["n"] == 3
    with pytest.raises(ValueError):
        with_retry(lambda: (_ for _ in ()).throw(ValueError("real error")), delay=0.001)


def test_worker_single_thread():
    import threading

    w = ComWorker(init_com=False)
    ids = {w.call(lambda: threading.get_ident()) for _ in range(5)}
    assert len(ids) == 1 and threading.get_ident() not in ids


# -- COM backend on the fake AutoCAD -----------------------------------------------------------------------
@pytest.fixture
def com():
    app = fake_acad.App()
    be = ComBackend(connector=fake_acad.connector(app), variants=fake_acad.VARIANTS)
    be.connect()
    be.app_fake = app
    return be


def test_com_info_and_documents(com):
    info = com.info()
    assert info["release"] == "AutoCAD 2024" and info["documents"] == []
    com.new_document()
    com.save_document(r"D:\out.dwg", "2010_dwg")
    assert com.app_fake.ActiveDocument.saved == [(r"D:\out.dwg", 48)]
    with pytest.raises(RuntimeError, match="Unknown format"):
        com.save_document(r"D:\x.dwg", "2030_dwg")


def test_com_drawing_and_query(com):
    com.create_layer("KC_TRUC", color=1, linetype="CENTER", current=True)
    doc = com.app_fake.ActiveDocument
    assert doc.ActiveLayer.Name == "KC_TRUC" and doc.Layers.Item("KC_TRUC").Linetype == "CENTER"
    h1 = com.add_line((0, 0), (3000, 4000), {"layer": "KC_TRUC", "color": 1})
    h2 = com.add_polyline([(0, 0), (1000, 0), (1000, 1000)], True, {})
    h3 = com.add_polyline([(0, 0, 0), (1, 0, 5)], False, {})
    com.add_arc((0, 0), 10, 0, 90, {})
    e = com.get_entity(h1)
    assert e["kind"] == "line" and e["length"] == pytest.approx(5000) and e["layer"] == "KC_TRUC"
    pl = com.get_entity(h2)
    assert pl["points"] == [[0, 0], [1000, 0], [1000, 1000]] and pl["closed"] is True
    assert com.get_entity(h3)["kind"] == "polyline3d"
    arc = [x for x in com.list_entities(None, ["arc"], None, 10)][0]
    assert arc["end_angle"] == pytest.approx(90)
    assert [x["handle"] for x in com.list_entities(["kc_truc"], None, None, 10)] == [h1]
    assert [x["handle"] for x in com.list_entities(None, None, [2000, 2000, 9000, 9000], 10)] == [h1]


def test_com_modify_and_blocks(com):
    h = com.add_circle((0, 0), 5, {})
    com.transform([h], "rotate", base=(0, 0), angle=90)
    ent = com._entity(h)
    assert ent.calls[-1][0] == "Rotate" and ent.calls[-1][2] == pytest.approx(math.pi / 2)
    copies = com.transform([h], "move", base=(0, 0), to=(10, 0), copy=True)
    assert copies[0] != h
    assert com.set_properties([h], {"layer": "A", "NoSuchProp": 1}) == []  # fake accepts any attribute
    ref = com.insert_block("KHUNG_TEN", (0, 0), 1.0, 0.0, {"so_hieu": "KC-01"}, {})
    assert com.get_entity(ref)["attributes"] == {"SO_HIEU": "KC-01", "TEN_BV": ""}
    assert com.delete([h]) == 1


def test_com_hatch_and_dimension(com):
    hid = com.add_hatch([(0, 0), (10, 0), (10, 10)], [], "ANSI31", 2.0, {"layer": "H"})
    hatch = com._entity(hid)
    assert hatch.PatternType == 1 and hatch.PatternScale == 2.0 and ("evaluate",) in hatch.calls
    d = com.add_dimension((0, 0), (4000, 0), (0, -500), 0.0, {"text_height": 125})
    assert com._entity(d).TextHeight == 125


def test_com_lisp_and_command(com):
    com.new_document()
    r = com.eval_lisp("(+ 40 2)", wait=1)
    assert r["result"] == "42" and r["complete"]
    com.send_command("_.ZOOM _E")
    assert com.app_fake.ActiveDocument.commands[-1] == "_.ZOOM _E\n"


# -- DXF backend (real ezdxf) --------------------------------------------------------------------------------
@pytest.fixture
def dxf():
    be = DxfBackend()
    be.new_document(version="2013")
    return be


def test_dxf_roundtrip(dxf, tmp_path):
    dxf.create_layer("KC_BETONG", color=7)
    h = dxf.add_polyline([(0, 0), (4000, 0), (4000, 3000), (0, 3000)], True, {"layer": "KC_BETONG"})
    dxf.add_text("Cống hộp 4x3", (0, 3500), 250, 0, {})
    e = dxf.get_entity(h)
    assert e["area"] == pytest.approx(12e6) and e["length"] == pytest.approx(14000)
    path = tmp_path / "a.dxf"
    dxf.save_document(str(path))
    doc = ezdxf.readfile(path)
    assert doc.dxfversion == "AC1027"
    texts = [t.dxf.text for t in doc.modelspace().query("TEXT")]
    assert texts == ["Cống hộp 4x3"]
    # other versions
    dxf.save_document(str(tmp_path / "r2000.dxf"), "2000_dxf")
    assert ezdxf.readfile(tmp_path / "r2000.dxf").dxfversion == "AC1015"
    dxf.save_document(str(tmp_path / "r12.dxf"), "R12_dxf")
    assert ezdxf.readfile(tmp_path / "r12.dxf").dxfversion == "AC1009"


def test_dxf_transform_and_filters(dxf):
    h = dxf.add_line((0, 0), (10, 0), {"layer": "L1"})
    dxf.transform([h], "rotate", base=(0, 0), angle=90)
    e = dxf.get_entity(h)
    assert e["end"][0] == pytest.approx(0, abs=1e-9) and e["end"][1] == pytest.approx(10)
    c = dxf.transform([h], "move", base=(0, 0), to=(5, 5), copy=True)[0]
    assert dxf.get_entity(c)["start"] == pytest.approx([5, 5, 0])
    m = dxf.transform([c], "mirror", base=(0, 0), base2=(0, 1))[0]
    assert dxf.get_entity(m)["start"][0] == pytest.approx(-5)
    assert len(dxf.list_entities(["l1"], ["line"], [-100, -100, 100, 100], 10)) == 2
    assert dxf.list_entities(None, None, [1000, 1000, 2000, 2000], 10) == []
    assert dxf.delete([h]) == 1


def test_dxf_blocks_and_attributes(dxf):
    blk = dxf.doc.blocks.new("KHUNG_TEN")
    blk.add_attdef("SO_HIEU", (0, 0))
    ref = dxf.insert_block("KHUNG_TEN", (100, 100), 1.0, 0.0, {"SO_HIEU": "KC-02"}, {})
    assert dxf.get_entity(ref)["attributes"] == {"SO_HIEU": "KC-02"}
    rows = drawings.extract_attributes(dxf, "khung_ten")["rows"]
    assert rows[0]["SO_HIEU"] == "KC-02" and rows[0]["x"] == 100
    blocks = {b["name"]: b for b in dxf.list_blocks()}
    assert blocks["KHUNG_TEN"]["attributes"] == ["SO_HIEU"]


# -- engineering drawings -----------------------------------------------------------------------------------
def test_culvert_outline_area():
    s = drawings.CulvertSection()
    outer, inner = drawings.culvert_outline(s)
    bo, ho = 4000 + 800, 3200 + 950
    assert outer[2] == (bo, ho)
    concrete = bo * ho - (4000 * 3200 - 4 * 0.5 * 200 * 200)
    r = drawings.draw_culvert_section(DxfBackend(), s)
    assert r["concrete_area_m2_per_m"] == pytest.approx(concrete / 1e6, abs=1e-4)


def test_culvert_section_on_both_backends(com, dxf, tmp_path):
    for be in (dxf, com):
        r = drawings.draw_culvert_section(be, drawings.CulvertSection(scale=50))
        assert len(r["handles"]["dimensions"]) == 10
        layers = {l["name"] for l in be.list_layers()}
        assert {"KC_BETONG", "KC_KICHTHUOC", "KC_TRUC"} <= layers
    # the DXF renders with correct dimension values
    dxf.save_document(str(tmp_path / "cong.dxf"))
    doc = ezdxf.readfile(tmp_path / "cong.dxf")
    values = sorted(round(d.get_measurement()) for d in doc.modelspace().query("DIMENSION"))
    assert {200, 400, 450, 500, 3200, 4000, 4150, 4800} <= set(values)
    texts = {d.dxf.get("text", "") for d in doc.modelspace().query("DIMENSION")}
    assert all(t in ("", "<>") for t in texts)  # measured values, no overrides


def test_culvert_rejects_bad_haunch(dxf):
    with pytest.raises(RuntimeError, match="Haunch"):
        drawings.draw_culvert_section(dxf, drawings.CulvertSection(haunch=2000))


def test_table_and_quantities(dxf):
    t = drawings.draw_table(dxf, [0, 0], [["STT", "Hạng mục", "KL"], [1, "Bê tông B30", "12.5 m3"]],
                            [800, 4000, 1500], 600, 250, "BANG")
    assert t["size"] == [6300, 1200]
    q = drawings.quantities_by_layer(dxf)
    assert q["BANG"]["length"] == pytest.approx(3 * 6300 + 4 * 1200)
    texts = drawings.extract_texts(dxf)["texts"]
    assert [x["text"] for x in texts[:3]] == ["STT", "Hạng mục", "KL"]


# -- MCP layer --------------------------------------------------------------------------------------------
def test_server_tools_and_dxf_fallback(tmp_path):
    from autocad_mcp import server

    async def run():
        names = {t.name for t in await server.mcp.list_tools()}
        info = await server.mcp.call_tool("cad_connect", {"backend": "auto"})
        await server.mcp.call_tool("draw_box_culvert_section", {"params": {"clear_width": 6000, "clear_height": 4500}})
        await server.mcp.call_tool("doc_save", {"path": str(tmp_path / "c.dxf")})
        return names, info

    names, info = asyncio.run(run())
    for t in ("cad_connect", "draw_polyline", "entities_list", "cad_lisp", "draw_box_culvert_section",
              "preview_image", "block_attributes_extract", "quantities_by_layer"):
        assert t in names
    assert "dxf" in str(info)  # no AutoCAD on the test machine -> DXF backend
    assert (tmp_path / "c.dxf").exists()
