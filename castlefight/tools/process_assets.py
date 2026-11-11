"""Подготовка сгенерированных картинок: вырезать фон (magenta), порезать листы, сохранить PNG.

Запуск: python -m castlefight.tools.process_assets <папка_с_сырыми_картинками>
Ожидаемые файлы: bg.jpg, castle_blue.jpg, castle_red.jpg, gold.jpg,
units_<key>.jpg и bld_<key>.jpg (4 спрайта в ряд: melee, ranged, summon, ult).
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "assets"
KEYS = ["kingdom", "horde", "forest", "necro", "arcana", "forge"]
ROLES = ["melee", "ranged", "summon", "ult"]


def key_out(img: Image.Image) -> Image.Image:
    """Убрать однотонный фон: заливка от краёв + мягкий край + despill."""
    rgb = np.asarray(img.convert("RGB")).astype(np.float32)
    h, w, _ = rgb.shape
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    key = np.median(border, axis=0)
    dist = np.sqrt(((rgb - key) ** 2).sum(axis=2))
    # «пурпурность»: R и B высоко, G низко
    mag = np.minimum(rgb[:, :, 0], rgb[:, :, 2]) - rgb[:, :, 1]
    cand = (dist < 120) | ((mag > 90) & (dist < 170))
    # заливка от краёв только по кандидатам
    bg = np.zeros((h, w), dtype=bool)
    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        for y in (0, h - 1):
            if cand[y, x] and not bg[y, x]:
                bg[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if cand[y, x] and not bg[y, x]:
                bg[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < h and 0 <= nx < w and cand[ny, nx] and not bg[ny, nx]:
                bg[ny, nx] = True
                q.append((ny, nx))
    # закрытые «дырки» фона (между ног и т.п.) — только очень близкие к ключу
    bg |= dist < 70
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    a_img = Image.fromarray(alpha).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    alpha = np.asarray(a_img).astype(np.float32)
    # despill по краю: срезаем пурпурный оттенок
    out = rgb.copy()
    edge = alpha < 250
    m = np.minimum(out[:, :, 0], out[:, :, 2])
    spill = np.clip(m - out[:, :, 1] - 20, 0, None)
    for c in (0, 2):
        out[:, :, c] = np.where(edge | (mag > 120), out[:, :, c] - spill * 0.85, out[:, :, c])
    out = np.clip(out, 0, 255)
    rgba = np.dstack([out, alpha]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def crop_alpha(img: Image.Image, pad: int = 2) -> Image.Image:
    bbox = img.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    if bbox is None:
        return img
    l, t, r, b = bbox
    return img.crop((max(0, l - pad), max(0, t - pad), min(img.width, r + pad), min(img.height, b + pad)))


def split_row(img: Image.Image, n: int = 4) -> list[Image.Image]:
    """Порезать лист на n спрайтов по пустым колонкам."""
    a = np.asarray(img.getchannel("A")) > 40
    cols = a.sum(axis=0)
    runs: list[list[int]] = []
    start = None
    for x, v in enumerate(cols):
        if v > 2 and start is None:
            start = x
        elif v <= 2 and start is not None:
            runs.append([start, x])
            start = None
    if start is not None:
        runs.append([start, len(cols)])
    # массы
    def mass(r):
        return int(a[:, r[0]:r[1]].sum())

    # мелочь (частицы) выкидываем, если она далеко; иначе сливаем с соседом
    while len(runs) > n:
        i = min(range(len(runs)), key=lambda k: mass(runs[k]))
        if i == 0:
            j = 1
        elif i == len(runs) - 1:
            j = i - 1
        else:
            gl = runs[i][0] - runs[i - 1][1]
            gr = runs[i + 1][0] - runs[i][1]
            j = i - 1 if gl <= gr else i + 1
        lo, hi = sorted((i, j))
        runs[lo] = [runs[lo][0], runs[hi][1]]
        del runs[hi]
    # слипшиеся (оружие касается соседа): режем самый широкий кусок по самой «тонкой» колонке
    while len(runs) < n:
        i = max(range(len(runs)), key=lambda k: runs[k][1] - runs[k][0])
        s0, s1 = runs[i]
        w = s1 - s0
        lo, hi = s0 + int(w * 0.25), s0 + int(w * 0.75)
        sm = np.convolve(cols.astype(float), np.ones(9) / 9, mode="same")
        cut = lo + int(np.argmin(sm[lo:hi]))
        runs[i:i + 1] = [[s0, cut], [cut, s1]]
    out = []
    for r in runs:
        piece = img.crop((r[0], 0, r[1], img.height))
        out.append(crop_alpha(_main_parts(piece)))
    return out


def _main_parts(piece: Image.Image) -> Image.Image:
    """Оставить главный силуэт и крупные куски; обрезки соседей у краёв выкинуть."""
    from scipy import ndimage

    arr = np.asarray(piece).copy()
    mask = arr[:, :, 3] > 40
    lab, num = ndimage.label(mask)
    if num <= 1:
        return piece
    sizes = ndimage.sum(mask, lab, range(1, num + 1))
    big = int(np.argmax(sizes)) + 1
    keep = np.zeros_like(mask)
    w = mask.shape[1]
    for k in range(1, num + 1):
        ys, xs = np.nonzero(lab == k)
        touches = xs.min() <= 1 or xs.max() >= w - 2
        if k == big or (sizes[k - 1] > 0.004 * sizes[big - 1] and not touches):
            keep |= lab == k
    keep = ndimage.binary_dilation(keep, iterations=2)
    arr[:, :, 3] = np.where(keep, arr[:, :, 3], 0)
    return Image.fromarray(arr, "RGBA")


def fit_height(img: Image.Image, h: int) -> Image.Image:
    w = max(1, round(img.width * h / img.height))
    return img.resize((w, h), Image.LANCZOS)


def fit_box(img: Image.Image, w: int, h: int) -> Image.Image:
    k = min(w / img.width, h / img.height)
    return img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)


def main(raw: Path) -> None:
    (OUT / "units").mkdir(parents=True, exist_ok=True)
    (OUT / "buildings").mkdir(parents=True, exist_ok=True)

    bg = Image.open(raw / "bg.jpg").convert("RGB").resize((1280, 720), Image.LANCZOS)
    bg.save(OUT / "bg_battlefield.jpg", quality=88)

    for side in ("blue", "red"):
        c = crop_alpha(key_out(Image.open(raw / f"castle_{side}.jpg")))
        fit_box(c, 260, 260).save(OUT / f"castle_{side}.png", optimize=True)

    g = crop_alpha(key_out(Image.open(raw / "gold.jpg")))
    fit_box(g, 64, 64).save(OUT / "icon_gold.png", optimize=True)

    for key in KEYS:
        units = split_row(key_out(Image.open(raw / f"units_{key}.jpg")))
        hmax = max(u.height for u in units)
        for role, u in zip(ROLES, units):
            # сохраняем относительный масштаб внутри листа; ult самый крупный
            target = round(150 * u.height / hmax)
            fit_height(u, max(60, target)).save(OUT / "units" / f"{key}_{role}.png", optimize=True)
        blds = split_row(key_out(Image.open(raw / f"bld_{key}.jpg")))
        for role, b in zip(ROLES, blds):
            fit_box(b, 128, 128).save(OUT / "buildings" / f"{key}_{role}.png", optimize=True)
    print("ok ->", OUT)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "raw_assets"))
