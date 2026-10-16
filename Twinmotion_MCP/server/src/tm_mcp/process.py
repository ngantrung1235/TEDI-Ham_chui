"""Quan ly tien trinh Twinmotion bang psutil (tim, chay, dong). Tach khoi controller de test bang ban gia."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Protocol

import psutil


@dataclass(frozen=True)
class ProcInfo:
    pid: int
    name: str
    exe: str | None
    started_at: float
    rss_mb: float

    def as_dict(self) -> dict:
        return {"pid": self.pid, "name": self.name, "exe": self.exe,
                "uptime_s": round(max(time.time() - self.started_at, 0), 1), "rss_mb": self.rss_mb}


class ProcessApi(Protocol):
    def find(self, names: set[str], hint: str) -> list[ProcInfo]: ...
    def launch(self, target: str | None, shortcut: str | None, args: list[str], cwd: str | None) -> None: ...
    def terminate(self, pid: int, force: bool) -> None: ...
    def alive(self, pid: int) -> bool: ...


class PsutilProcessApi:
    """names: ten file exe (chu thuong) can khop chinh xac; hint: chuoi con trong ten/duong dan exe (chu thuong)."""

    def find(self, names: set[str], hint: str) -> list[ProcInfo]:
        me = os.getpid()
        out: list[ProcInfo] = []
        for p in psutil.process_iter(["pid", "name", "exe", "create_time", "memory_info"]):
            try:
                info = p.info
                if info["pid"] == me:
                    continue
                name = (info["name"] or "").lower()
                exe = (info["exe"] or "").lower()
                if name in names or (hint and (hint in name or hint in os.path.basename(exe))):
                    mem = info["memory_info"].rss / 1048576 if info["memory_info"] else 0.0
                    out.append(ProcInfo(info["pid"], info["name"] or "", info["exe"], info["create_time"] or 0.0, round(mem, 1)))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return out

    def launch(self, target: str | None, shortcut: str | None, args: list[str], cwd: str | None) -> None:
        # Khong doi so + co shortcut: mo qua shortcut (ShellExecute) de giu cai dat cua shortcut (chay Admin, v.v.)
        if shortcut and not args and sys.platform == "win32":
            os.startfile(shortcut)  # type: ignore[attr-defined]
            return
        if not target:
            raise FileNotFoundError("Khong co duong dan exe de chay.")
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        subprocess.Popen([target, *args], cwd=cwd or None, creationflags=flags, close_fds=True)

    def terminate(self, pid: int, force: bool) -> None:
        try:
            p = psutil.Process(pid)
            (p.kill if force else p.terminate)()
        except psutil.NoSuchProcess:
            pass

    def alive(self, pid: int) -> bool:
        try:
            return psutil.Process(pid).is_running() and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False
