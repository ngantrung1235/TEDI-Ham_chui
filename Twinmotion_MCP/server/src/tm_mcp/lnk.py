"""Doc shortcut Windows (.lnk): muc tieu (exe), doi so, thu muc lam viec.

Tren Windows uu tien WScript.Shell (qua PowerShell) vi xu ly du moi truong hop (ke ca shortcut quang cao cua
MSI). Neu khong dung duoc (khong phai Windows, PowerShell bi chan) thi doc truc tiep theo dac ta MS-SHLLINK.
Bo doc nhi phan chi lay duong dan tu LinkInfo / StringData; shortcut chi co IDList (khong co LinkInfo) se khong
doc duoc - truong hop do roi ve WScript.Shell.
"""

from __future__ import annotations

import json
import ntpath
import os
import struct
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

_HAS_LINK_TARGET_IDLIST = 0x01
_HAS_LINK_INFO = 0x02
_HAS_NAME = 0x04
_HAS_RELATIVE_PATH = 0x08
_HAS_WORKING_DIR = 0x10
_HAS_ARGUMENTS = 0x20
_HAS_ICON_LOCATION = 0x40
_IS_UNICODE = 0x80
_LINK_CLSID = bytes.fromhex("0114020000000000c000000000000046")


class ShortcutError(RuntimeError):
    pass


@dataclass(frozen=True)
class Shortcut:
    path: str
    target: str | None
    arguments: str
    working_dir: str | None
    source: str                         # "wscript" | "parser"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["target_exists"] = bool(self.target) and os.path.exists(self.target)
        return d


def _cstr(data: bytes, offset: int, unicode: bool) -> str:
    if unicode:
        end = offset
        while end + 1 < len(data) and data[end:end + 2] != b"\x00\x00":
            end += 2
        return data[offset:end].decode("utf-16-le")
    end = data.index(b"\x00", offset)
    return data[offset:end].decode("mbcs" if os.name == "nt" else "cp1252", errors="replace")


def parse_lnk_bytes(data: bytes, path: str = "") -> Shortcut:
    if len(data) < 0x4C or struct.unpack_from("<I", data, 0)[0] != 0x4C or data[4:20] != _LINK_CLSID:
        raise ShortcutError("Khong phai file .lnk hop le (sai header).")
    flags = struct.unpack_from("<I", data, 0x14)[0]
    unicode = bool(flags & _IS_UNICODE)
    pos = 0x4C

    if flags & _HAS_LINK_TARGET_IDLIST:
        (idlist_size,) = struct.unpack_from("<H", data, pos)
        pos += 2 + idlist_size

    target: str | None = None
    if flags & _HAS_LINK_INFO:
        base = pos
        size, header_size, li_flags, _vol_off, local_off, _net_off, suffix_off = struct.unpack_from("<IIIIIII", data, base)
        has_local = bool(li_flags & 0x1)
        if has_local:
            local_unicode_off = suffix_unicode_off = 0
            if header_size >= 0x24:
                local_unicode_off, suffix_unicode_off = struct.unpack_from("<II", data, base + 0x1C)
            if local_unicode_off:
                local = _cstr(data, base + local_unicode_off, True)
                suffix = _cstr(data, base + suffix_unicode_off, True) if suffix_unicode_off else ""
            else:
                local = _cstr(data, base + local_off, False)
                suffix = _cstr(data, base + suffix_off, False) if suffix_off else ""
            target = local + suffix
        pos = base + size

    def read_string() -> str:
        nonlocal pos
        (count,) = struct.unpack_from("<H", data, pos)
        pos += 2
        width = 2 if unicode else 1
        raw = data[pos:pos + count * width]
        pos += count * width
        return raw.decode("utf-16-le") if unicode else raw.decode("cp1252", errors="replace")

    working_dir = arguments = ""
    if flags & _HAS_NAME:
        read_string()
    if flags & _HAS_RELATIVE_PATH:
        relative = read_string()
        if target is None and path:
            # Duong dan trong .lnk luon kieu Windows: dung ntpath de chuan hoa dung ca khi chay o he khac.
            target = ntpath.normpath(ntpath.join(ntpath.dirname(path), relative))
    if flags & _HAS_WORKING_DIR:
        working_dir = read_string()
    if flags & _HAS_ARGUMENTS:
        arguments = read_string()
    if flags & _HAS_ICON_LOCATION:
        read_string()

    return Shortcut(path=path, target=target, arguments=arguments, working_dir=working_dir or None, source="parser")


def _resolve_with_wscript(path: str) -> Shortcut:
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($args[0]);"
        "[pscustomobject]@{t=$s.TargetPath;a=$s.Arguments;w=$s.WorkingDirectory}|ConvertTo-Json -Compress"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script, path],
        capture_output=True, text=True, timeout=20, check=True,
    ).stdout.strip()
    info = json.loads(out)
    return Shortcut(path=path, target=info.get("t") or None, arguments=info.get("a") or "",
                    working_dir=info.get("w") or None, source="wscript")


def resolve_shortcut(path: str) -> Shortcut:
    p = Path(path)
    if not p.is_file():
        raise ShortcutError(f"Khong tim thay shortcut: {path}")
    if os.name == "nt":
        try:
            sc = _resolve_with_wscript(str(p))
            if sc.target:
                return sc
        except Exception:                       # PowerShell bi chan / loi COM -> thu bo doc nhi phan
            pass
    sc = parse_lnk_bytes(p.read_bytes(), str(p))
    if not sc.target:
        raise ShortcutError("Shortcut khong chua duong dan muc tieu doc duoc (co the la shortcut quang cao).")
    return sc
