"""AutoCAD releases, COM ProgIDs and file formats.

The ActiveX/COM object model (AcadApplication, AcadDocument, ModelSpace...) has
been kept backward compatible by Autodesk since AutoCAD 2000 (R15), which is why
this server talks COM with late binding: the same calls work in every release
and in AutoCAD-based verticals (Civil 3D, Map 3D, Plant 3D...). Several
AutoCAD-compatible CADs expose the same object model under another ProgID.
"""

from __future__ import annotations

# AcadApplication.Version starts with "<major>.<minor>" (e.g. "24.3s (LMS Tech)")
RELEASES = {
    "15.0": "AutoCAD 2000", "15.1": "AutoCAD 2000i", "15.2": "AutoCAD 2002",
    "16.0": "AutoCAD 2004", "16.1": "AutoCAD 2005", "16.2": "AutoCAD 2006",
    "17.0": "AutoCAD 2007", "17.1": "AutoCAD 2008", "17.2": "AutoCAD 2009",
    "18.0": "AutoCAD 2010", "18.1": "AutoCAD 2011", "18.2": "AutoCAD 2012",
    "19.0": "AutoCAD 2013", "19.1": "AutoCAD 2014",
    "20.0": "AutoCAD 2015", "20.1": "AutoCAD 2016",
    "21.0": "AutoCAD 2017", "22.0": "AutoCAD 2018",
    "23.0": "AutoCAD 2019", "23.1": "AutoCAD 2020",
    "24.0": "AutoCAD 2021", "24.1": "AutoCAD 2022", "24.2": "AutoCAD 2023", "24.3": "AutoCAD 2024",
    "25.0": "AutoCAD 2025", "25.1": "AutoCAD 2026",
}

# Tried in order when attaching to a running CAD or starting one.
PROGIDS = [
    "AutoCAD.Application",  # latest registered AutoCAD (any release, incl. Civil 3D)
    *[f"AutoCAD.Application.{v}" for v in (25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15)],
    "BricscadApp.AcadApplication",  # BricsCAD
    "ZWCAD.Application",  # ZWCAD
    "GCAD.Application",  # GstarCAD
]

# AcSaveAsType enumeration
SAVE_FORMATS = {
    "R12_dxf": 1,
    "2000_dwg": 12, "2000_dxf": 13,
    "2004_dwg": 24, "2004_dxf": 25,
    "2007_dwg": 36, "2007_dxf": 37,
    "2010_dwg": 48, "2010_dxf": 49,
    "2013_dwg": 60, "2013_dxf": 61,
    "2018_dwg": 64, "2018_dxf": 65,
}

# ezdxf DXF versions for the headless backend
DXF_VERSIONS = {
    "R12": "R12", "2000": "R2000", "2004": "R2004", "2007": "R2007",
    "2010": "R2010", "2013": "R2013", "2018": "R2018",
}


def release_name(version: str) -> str:
    key = ".".join(version.split(".")[:2])[:4]
    return RELEASES.get(key, f"AutoCAD (version {version})")
