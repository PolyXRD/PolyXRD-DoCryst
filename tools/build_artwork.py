"""PolyXRD DoCryst 品牌资产生成器
=================================
参照 RutAna / CifCalc 的家族视觉血统（Pillow 纯代码绘制，可复现、颜色精确）。

设计血统（与家族严格一致）
--------------------------
- 品牌深色 #0F172A (slate-950) → 品牌蓝 #0284C7 (sky-600) 对角线渐变
- 家族符号 = 「白色正六边形」。本工具内部 motif =
  「尖锐结晶衍射峰（3 支，天蓝）+ 宽非晶包（琥珀填充）」——
  即结晶度分峰法的一图速览：Ac / (Ac + Aa)
- 子工具强调色 = 青色 #22D3EE（词标 "DoCryst"）；琥珀 #FCD34D 仅用于
  motif 中非晶包，代表 Aa

产出（写入 <root>/resources/）
------------------------------
- app-icon.png        256×256   运行时窗口图标
- app-icon@2x.png     512×512   高分屏备份
- app-icon.ico        多分辨率  给 exe 资源使用
- crystal-mark.png    256×256   透明底深色 mark（浅色背景用）
- logo-horizontal.png 512×160   横向 logo：mark + 「PolyXRD DoCryst」
- splash-screen.png   480×270   启动图（深空底 + logo + 版本 + tagline）
- hero-banner.png     1600×600  About 页头图

使用：
    python tools/build_artwork.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from docryst.version import APP_TAGLINE, __version__  # noqa: E402

RES_DIR = ROOT / "resources"

# --------------------------------------------------------------------------- #
# 品牌常量（家族色，严格一致）
# --------------------------------------------------------------------------- #
BRAND_DARK = (15, 23, 42)        # #0F172A  slate-950  "Poly"
BRAND_BLUE = (2, 132, 199)       # #0284C7  sky-600    "XRD"
WHITE = (255, 255, 255)
SOFT = (226, 232, 240)           # #E2E8F0  slate-200
SLATE = (100, 116, 139)          # #64748B  slate-500
CYAN = (34, 211, 238)            # #22D3EE  子工具强调色
CYAN_LIGHT = (125, 211, 252)     # #7DD3FC
CYAN_DARK = (8, 145, 178)        # #0891B2  浅色背景上的青色词标
AMBER = (252, 211, 77)           # #FCD34D  非晶包（motif 专用）
AMBER_DEEP = (217, 119, 6)       # #D97706  非晶包描边

# 启动图 / 横幅的深空背景（与家族 splash 的墨青基调一致）
BG_INNER = (12, 48, 70)
BG_OUTER = (5, 12, 24)

FONT_BOLD = r"C:/Windows/Fonts/segoeuib.ttf"
FONT_SEMI = r"C:/Windows/Fonts/seguisb.ttf"
FONT_CN = r"C:/Windows/Fonts/msyh.ttc"

ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]
COS30 = math.cos(math.radians(30.0))

# motif 峰参数：3 支尖峰（结晶）+ 1 个宽包（非晶），t ∈ [0,1] 横轴
CRYST_PEAKS = ((0.22, 0.62), (0.55, 1.00), (0.80, 0.45))
CRYST_SIGMA = 0.016
AMORPH_CENTER, AMORPH_SIGMA, AMORPH_REL = 0.40, 0.16, 0.30


# --------------------------------------------------------------------------- #
# 基础几何 / 绘制工具
# --------------------------------------------------------------------------- #
def hex_points(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    """尖顶正六边形顶点（顶点在正上/正下）。"""
    return [
        (cx + r * math.cos(math.radians(-90 + 60 * k)),
         cy + r * math.sin(math.radians(-90 + 60 * k)))
        for k in range(6)
    ]


def diagonal_gradient(size: int, c1, c2) -> Image.Image:
    """左上 → 右下 对角线渐变（低分辨率生成再放大，保证平滑）。"""
    small = Image.new("RGB", (96, 96))
    px = small.load()
    for y in range(96):
        for x in range(96):
            t = (x + y) / (2 * 95.0)
            px[x, y] = (round(c1[0] + (c2[0] - c1[0]) * t),
                        round(c1[1] + (c2[1] - c1[1]) * t),
                        round(c1[2] + (c2[2] - c1[2]) * t))
    return small.resize((size, size), Image.BICUBIC)


def radial_gradient(w: int, h: int, inner, outer) -> Image.Image:
    """径向渐变背景（中心亮 → 四周暗）。"""
    small = Image.new("RGB", (120, 68))
    px = small.load()
    cx, cy = 59.5, 33.0
    maxd = math.hypot(cx, cy)
    for y in range(68):
        for x in range(120):
            d = min(1.0, math.hypot(x - cx, y - cy) / maxd) ** 0.85
            px[x, y] = (round(inner[0] + (outer[0] - inner[0]) * d),
                        round(inner[1] + (outer[1] - inner[1]) * d),
                        round(inner[2] + (outer[2] - inner[2]) * d))
    return small.resize((w, h), Image.BICUBIC)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


# --------------------------------------------------------------------------- #
# DoCryst motif：尖峰 + 宽包
# --------------------------------------------------------------------------- #
def draw_motif(draw: ImageDraw.ImageDraw, x0: float, y0: float, width: float,
               amp: float, peak_color, amorph_fill, lw: int) -> None:
    """在 (x0,y0) 基线上绘制「宽非晶包 + 3 支尖峰」的抽象谱形。

    非晶包：琥珀半透明填充 + 深琥珀描边；尖峰：实线折线（无填充）。
    """
    n = 180

    def height(t: float) -> float:
        a = AMORPH_REL * math.exp(-((t - AMORPH_CENTER) ** 2) / (2 * AMORPH_SIGMA ** 2))
        c = sum(rel * math.exp(-((t - pos) ** 2) / (2 * CRYST_SIGMA ** 2))
                for pos, rel in CRYST_PEAKS)
        return a + c

    # 非晶包填充（多边形，只含宽包成分）
    poly = [(x0, y0)]
    for i in range(n + 1):
        t = i / n
        a = AMORPH_REL * math.exp(-((t - AMORPH_CENTER) ** 2) / (2 * AMORPH_SIGMA ** 2))
        poly.append((x0 + t * width, y0 - amp * a))
    poly.append((x0 + width, y0))
    draw.polygon(poly, fill=amorph_fill + (110,))
    draw.line(poly[1:-1], fill=AMBER_DEEP, width=max(2, lw // 2), joint="curve")

    # 尖峰折线（结晶分量）
    pts: list[tuple[float, float]] = [(x0, y0)]
    for i in range(n + 1):
        t = i / n
        c = sum(rel * math.exp(-((t - pos) ** 2) / (2 * CRYST_SIGMA ** 2))
                for pos, rel in CRYST_PEAKS)
        pts.append((x0 + t * width, y0 - amp * c))
    pts.append((x0 + width, y0))
    draw.line(pts, fill=peak_color, width=lw, joint="curve")


def make_mark(size: int, hex_color, peak_color, amorph_fill,
              hex_w_ratio: float = 0.070, glow: bool = False) -> Image.Image:
    """生成 DoCryst 家族符号：六边形 + 尖峰宽包 motif（透明底 RGBA）。"""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cx = cy = size / 2.0
    r = size * 0.44
    hex_w = max(2, int(round(size * hex_w_ratio)))
    peak_lw = max(2, int(size * 0.028))
    pts = hex_points(cx, cy, r)

    def motif(d: ImageDraw.ImageDraw) -> None:
        draw_motif(d, cx - size * 0.26, cy + size * 0.22,
                   size * 0.52, size * 0.34, peak_color, amorph_fill, peak_lw)

    if glow:
        gl = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gl)
        gd.line(pts + [pts[0]], fill=hex_color, width=hex_w, joint="curve")
        motif(gd)
        gl = gl.filter(ImageFilter.GaussianBlur(max(2, size * 0.02)))
        im.alpha_composite(gl)

    d = ImageDraw.Draw(im)
    d.line(pts + [pts[0]], fill=hex_color, width=hex_w, joint="curve")
    motif(d)
    return im


# --------------------------------------------------------------------------- #
# 各资产
# --------------------------------------------------------------------------- #
def build_icons() -> None:
    """应用图标：深蓝渐变底 + 白六边形 + 彩色 motif。"""
    for size, name in ((256, "app-icon.png"), (512, "app-icon@2x.png")):
        im = diagonal_gradient(size, BRAND_DARK, BRAND_BLUE).convert("RGBA")
        mark = make_mark(size, WHITE, CYAN_LIGHT, AMBER, glow=True)
        im.alpha_composite(mark)
        im.save(RES_DIR / name)

    base = Image.open(RES_DIR / "app-icon.png").convert("RGBA")
    base.save(RES_DIR / "app-icon.ico", sizes=[(s, s) for s in ICON_SIZES])


def build_crystal_mark() -> None:
    """透明底深色 mark（浅色文档/网页用）。"""
    make_mark(256, BRAND_DARK, BRAND_BLUE, AMBER).save(RES_DIR / "crystal-mark.png")


def build_logo_horizontal() -> None:
    """横向 logo 512×160：mark + 「PolyXRD │ DoCryst」+ 副标。"""
    w, h = 512, 160
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mark = make_mark(140, BRAND_DARK, BRAND_BLUE, AMBER)
    im.alpha_composite(mark, (4, 10))

    d = ImageDraw.Draw(im)
    font_big = _font(FONT_SEMI, 52)
    font_sub = _font(FONT_CN, 20)

    seg_w = (d.textlength("PolyXRD ", font=font_big)
             + d.textlength("DoCryst", font=font_big))
    tx = 152 + (w - 152 - seg_w) / 2.0
    d.text((tx, 38), "PolyXRD ", font=font_big, fill=BRAND_DARK)
    d.text((tx + d.textlength("PolyXRD ", font=font_big), 38),
           "DoCryst", font=font_big, fill=CYAN_DARK)
    sub = "XRD 结晶度分峰定量分析"
    d.text((tx + (seg_w - d.textlength(sub, font=font_sub)) / 2.0, 104),
           sub, font=font_sub, fill=SLATE)
    im.save(RES_DIR / "logo-horizontal.png")


def _wordmark_light(d: ImageDraw.ImageDraw, cx: float, y: float,
                    font_t) -> float:
    """深底上的词标：「PolyXRD 」浅灰 + 「DoCryst」亮青，返回总宽。"""
    seg_w = d.textlength("PolyXRD ", font=font_t) + d.textlength("DoCryst", font=font_t)
    x = cx - seg_w / 2.0
    d.text((x, y), "PolyXRD ", font=font_t, fill=SOFT)
    d.text((x + d.textlength("PolyXRD ", font=font_t), y),
           "DoCryst", font=font_t, fill=CYAN_LIGHT)
    return seg_w


def build_splash() -> None:
    """启动图 480×270：深空底 + 白 mark + 词标 + 版本 + tagline。"""
    w, h = 480, 270
    im = radial_gradient(w, h, BG_INNER, BG_OUTER).convert("RGBA")
    d = ImageDraw.Draw(im)

    mark = make_mark(150, WHITE, CYAN_LIGHT, AMBER, glow=True)
    im.alpha_composite(mark, (int(w / 2 - 75), 14))
    d = ImageDraw.Draw(im)

    font_t = _font(FONT_SEMI, 34)
    _wordmark_light(d, w / 2, 168, font_t)

    ver = f"v{__version__}"
    font_v = _font(FONT_SEMI, 15)
    d.text((w / 2 - d.textlength(ver, font=font_v) / 2, 210),
           ver, font=font_v, fill=(148, 163, 184))

    tag = APP_TAGLINE
    font_c = _font(FONT_CN, 14)
    d.text((w / 2 - d.textlength(tag, font=font_c) / 2, 236),
           tag, font=font_c, fill=(148, 163, 184))
    im.convert("RGB").save(RES_DIR / "splash-screen.png")


def build_hero_banner() -> None:
    """About 页头图 1600×600：深空底 + 大 mark + 词标 + 家族名。"""
    w, h = 1600, 600
    im = radial_gradient(w, h, BG_INNER, BG_OUTER).convert("RGBA")

    mark = make_mark(330, WHITE, CYAN_LIGHT, AMBER, glow=True)
    im.alpha_composite(mark, (int(w / 2 - 165), 70))
    d = ImageDraw.Draw(im)

    font_t = _font(FONT_SEMI, 76)
    _wordmark_light(d, w / 2, 420, font_t)

    sub = f"{APP_TAGLINE} · {__version__}"
    font_c = _font(FONT_CN, 26)
    d.text((w / 2 - d.textlength(sub, font=font_c) / 2, 520),
           sub, font=font_c, fill=(148, 163, 184))
    im.convert("RGB").save(RES_DIR / "hero-banner.png")


def main() -> None:
    RES_DIR.mkdir(exist_ok=True)
    build_icons()
    build_crystal_mark()
    build_logo_horizontal()
    build_splash()
    build_hero_banner()
    for f in sorted(RES_DIR.iterdir()):
        print(f"  {f.name:24s} {f.stat().st_size:>8,} bytes")


if __name__ == "__main__":
    main()
