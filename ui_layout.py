# -*- coding: utf-8 -*-
"""
Раскладка кадра WC3 для VR: мир (обрезанный под поле зрения) + панели интерфейса
отдельными регионами, упакованными в ОДИН компактный атлас (один JPEG, один декод
в шлеме). Клиент раскладывает регионы по своим плашкам через UV.

Границы интерфейса — доли клиентской области окна (замерены на живом окне
1920x1017; у WC3 1.26 в широких разрешениях они те же).
"""
import numpy as np
import cv2

UI_FRACTIONS = {
    "top_h":   0.045,   # верхняя полоса: кнопки меню/задания/союзники/журнал + ресурсы
    "ui_top":  0.745,   # верх нижней панели интерфейса (с листвой)
    "mm_x1":   0.230,   # правый край миникарты + столбик кнопок рядом
    "cmd_x0":  0.765,   # левый край панели команд (сетка 4x3)
    "hero_x1": 0.060,   # столбик иконок героев слева над панелью
    "hero_y0": 0.580,
}

# порядок и раскладка панелей в атласе (ряды под миром)
ROWS = (("minimap", "unit", "cmd", "heroes"), ("top",))


class Layout:
    def __init__(self, split=True, world_crop_x=0.80, world_crop_y=0.0,
                 panel_scale=0.85, heroes=True, fractions=None):
        self.split = split
        self.world_crop_x = world_crop_x
        self.world_crop_y = world_crop_y
        self.panel_scale = panel_scale
        self.heroes = heroes
        self.fr = dict(UI_FRACTIONS)
        if fractions:
            self.fr.update(fractions)

    # ---- регионы в пикселях окна игры: name -> [x0,y0,x1,y1] (от левого верха) ----
    def regions(self, W, H):
        if not self.split:
            return {"world": [0, 0, W, H]}
        f = self.fr
        cx = min(1.0, max(0.3, float(self.world_crop_x)))
        cy = min(0.6, max(0.0, float(self.world_crop_y)))
        wy0 = int(H * f["top_h"]); wy1 = int(H * f["ui_top"])
        wh = wy1 - wy0
        wy0 += int(wh * cy / 2); wy1 -= int(wh * cy / 2)
        wx0 = int(W * (0.5 - cx / 2)); wx1 = int(W * (0.5 + cx / 2))
        r = {
            "world":   [wx0, wy0, wx1, wy1],
            "top":     [0, 0, W, int(H * f["top_h"])],
            "minimap": [0, int(H * f["ui_top"]), int(W * f["mm_x1"]), H],
            "unit":    [int(W * f["mm_x1"]), int(H * f["ui_top"]), int(W * f["cmd_x0"]), H],
            "cmd":     [int(W * f["cmd_x0"]), int(H * f["ui_top"]), W, H],
        }
        if self.heroes:
            r["heroes"] = [0, int(H * f["hero_y0"]), int(W * f["hero_x1"]), int(H * f["ui_top"])]
        return r

    # ---- упаковка: frame HxWx3 -> (atlas, layout) ----
    def pack(self, frame):
        H, W = frame.shape[:2]
        regs = self.regions(W, H)
        if not self.split:
            return frame, {"win": [W, H], "atlas": [W, H], "split": False,
                           "regions": {"world": {"src": [0, 0, W, H], "dst": [0, 0, W, H]}}}
        wx0, wy0, wx1, wy1 = regs["world"]
        world = frame[wy0:wy1, wx0:wx1]
        wh, ww = world.shape[:2]
        ps = float(self.panel_scale)

        def cut(name):
            x0, y0, x1, y1 = regs[name]
            img = frame[y0:y1, x0:x1]
            if abs(ps - 1.0) > 1e-3:
                img = cv2.resize(img, (max(2, int(img.shape[1] * ps)), max(2, int(img.shape[0] * ps))),
                                 interpolation=cv2.INTER_AREA)
            return img, [x0, y0, x1, y1]

        rows = []
        for row in ROWS:
            items = [(n,) + cut(n) for n in row if n in regs]
            if items:
                rows.append(items)
        AW = max([ww] + [sum(it[1].shape[1] for it in row) for row in rows])
        AH = wh + sum(max(it[1].shape[0] for it in row) for row in rows)
        atlas = np.zeros((AH, AW, 3), np.uint8)
        atlas[0:wh, 0:ww] = world
        out = {"world": {"src": [wx0, wy0, wx1, wy1], "dst": [0, 0, ww, wh]}}
        y = wh
        for row in rows:
            x = 0; rh = max(it[1].shape[0] for it in row)
            for name, img, src in row:
                h, w = img.shape[:2]
                atlas[y:y + h, x:x + w] = img
                out[name] = {"src": src, "dst": [x, y, x + w, y + h]}
                x += w
            y += rh
        return atlas, {"win": [W, H], "atlas": [AW, AH], "split": True, "regions": out}


def scale_layout(layout, s):
    """После даунскейла атласа на коэффициент s пересчитать dst (src не меняется)."""
    if abs(s - 1.0) < 1e-6:
        return layout
    L = {"win": layout["win"],
         "atlas": [max(2, int(layout["atlas"][0] * s)), max(2, int(layout["atlas"][1] * s))],
         "split": layout["split"], "regions": {}}
    for k, v in layout["regions"].items():
        d = v["dst"]
        L["regions"][k] = {"src": v["src"],
                           "dst": [int(d[0] * s), int(d[1] * s), int(d[2] * s), int(d[3] * s)]}
    return L
