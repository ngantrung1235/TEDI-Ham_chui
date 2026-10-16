"""Xu ly anh chup man hinh: PNG, thu nho, ve luoi toa do de LLM chon diem click, cho man hinh on dinh."""

from __future__ import annotations

import io
import time
from typing import Callable

from PIL import Image, ImageChops, ImageDraw


def to_png(img: Image.Image, max_width: int = 1600) -> bytes:
    """PNG (thu nho giu ti le neu rong hon max_width). Anh duoc chuyen RGB (bo kenh alpha)."""
    if img.mode != "RGB":
        img = img.convert("RGB")
    if max_width and img.width > max_width:
        img = img.resize((max_width, max(1, round(img.height * max_width / img.width))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def draw_grid(img: Image.Image, step: int) -> Image.Image:
    """Ve luoi moi `step` pixel, nhan toa do tren duong luoi (toa do GOC cua anh, chua thu nho) -
    giup LLM doc toa do chinh xac khi dung voi tm_click. Tra ve anh moi."""
    if step < 20:
        raise ValueError("step luoi toi thieu 20 px.")
    out = img.convert("RGB").copy()
    draw = ImageDraw.Draw(out, "RGBA")
    for x in range(0, out.width, step):
        draw.line([(x, 0), (x, out.height)], fill=(255, 0, 0, 90), width=1)
        draw.text((x + 2, 2), str(x), fill=(255, 255, 0, 255))
    for y in range(0, out.height, step):
        draw.line([(0, y), (out.width, y)], fill=(255, 0, 0, 90), width=1)
        draw.text((2, y + 2), str(y), fill=(255, 255, 0, 255))
    return out


def mark_point(img: Image.Image, x: int, y: int, radius: int = 10) -> Image.Image:
    """Ve vong tron do tai (x, y) - dung de xac nhan truc quan diem sap click."""
    out = img.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    draw.ellipse([x - radius, y - radius, x + radius, y + radius], outline=(255, 0, 0), width=3)
    draw.line([(x - radius * 2, y), (x + radius * 2, y)], fill=(255, 0, 0), width=1)
    draw.line([(x, y - radius * 2), (x, y + radius * 2)], fill=(255, 0, 0), width=1)
    return out


def difference_ratio(a: Image.Image, b: Image.Image, sample: int = 160) -> float:
    """Ti le diem anh khac nhau dang ke (0..1), so sanh tren ban thu nho `sample` px de nhanh."""
    if a.size != b.size:
        return 1.0
    ta = a.convert("L").resize((sample, max(1, round(sample * a.height / a.width))))
    tb = b.convert("L").resize(ta.size)
    diff = ImageChops.difference(ta, tb).point(lambda v: 255 if v > 12 else 0)
    changed = diff.histogram()[255]                        # so diem khac nhau dang ke (da nhi phan hoa 0/255)
    return changed / (ta.width * ta.height)


def wait_until_stable(
    grab: Callable[[], Image.Image],
    timeout_s: float = 60.0,
    interval_s: float = 1.0,
    stable_frames: int = 3,
    threshold: float = 0.002,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Cho toi khi `stable_frames` khung lien tiep gan nhu khong doi (< threshold diem thay doi)
    - dung sau import / render / luu de biet qua trinh ket thuc."""
    start = clock()
    prev = grab()
    stable = 0
    frames = 1
    last_ratio = 1.0
    while clock() - start < timeout_s:
        sleep(interval_s)
        cur = grab()
        frames += 1
        last_ratio = difference_ratio(prev, cur)
        stable = stable + 1 if last_ratio < threshold else 0
        prev = cur
        if stable >= stable_frames:
            return {"stable": True, "waited_s": round(clock() - start, 2), "frames": frames, "last_change": round(last_ratio, 5)}
    return {"stable": False, "waited_s": round(clock() - start, 2), "frames": frames, "last_change": round(last_ratio, 5)}
