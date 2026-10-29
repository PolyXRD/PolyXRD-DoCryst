"""工程存档（JSON）：保存/加载完整分析状态，保证结果可复现。

存档内容 = 复算所需的最小集合：谱图来源、拟合区间、背景配置、峰表（含锁定
与手动改判）、非晶判据、拟合选项、结果摘要。谱图本体不内嵌（体积与版权
考虑），只存路径；加载时若原文件不在，用户重新导入后按存档峰表复算。

设计对齐家族约定（RutAna 的工程存档铁律）：**所有影响数值的参数都必须写入
存档**——判据、背景模型、平滑/剥 Kα2 开关一个都不能漏。
"""

from __future__ import annotations

import json
from pathlib import Path

from docryst.core.dtypes import BackgroundConfig, PeakSpec
from docryst.core.peakfind import FindOptions
from docryst.core import fitting as fitmod

#: 存档格式版本（结构变更时递增）
FORMAT = 1

#: 文件扩展名
EXT = ".dcy.json"


def save_project(path: str | Path, *, pattern_path: str, sample: str,
                 lo: float | None, hi: float | None,
                 bg_cfg: BackgroundConfig,
                 peaks: list[PeakSpec],
                 fwhm_threshold: float,
                 fit_opt: fitmod.FitOptions | None = None,
                 find_opt: FindOptions | None = None,
                 preprocess: dict | None = None,
                 result: dict | None = None,
                 note: str = "") -> Path:
    """把当前分析状态写入 ``path``，返回实际写入的路径。"""
    fit_opt = fit_opt or fitmod.FitOptions()
    data = {
        "format": FORMAT,
        "app": "PolyXRD DoCryst",
        "pattern_path": pattern_path,
        "sample": sample,
        "range": [lo, hi],
        "background": {
            "model": bg_cfg.model,
            "order": bg_cfg.order,
            "anchors": [list(a) for a in bg_cfg.anchors],
            "snip_iter": bg_cfg.snip_iter,
            "end_points": bg_cfg.end_points,
        },
        "peaks": [
            {
                "pos": p.pos, "fwhm": p.fwhm, "area": p.area, "eta": p.eta,
                "kind": p.kind, "fix_pos": p.fix_pos, "fix_fwhm": p.fix_fwhm,
                "fix_area": p.fix_area, "kind_locked": p.kind_locked,
                "label": p.label,
            }
            for p in peaks
        ],
        "fwhm_threshold": float(fwhm_threshold),
        "fit_options": {
            "fit_background": fit_opt.fit_background,
            "free_eta": fit_opt.free_eta,
            "tie_eta": fit_opt.tie_eta,
            "robust": fit_opt.robust,
            "weight": fit_opt.weight,
            "max_nfev": fit_opt.max_nfev,
            "with_covariance": fit_opt.with_covariance,
        },
        "find_options": {
            "prominence_frac": (find_opt.prominence_frac if find_opt else 0.02),
            "height_frac": find_opt.height_frac if find_opt else 0.01,
            "min_distance_deg": find_opt.min_distance_deg if find_opt else 0.12,
            "max_peaks": find_opt.max_peaks if find_opt else 24,
        },
        "preprocess": dict(preprocess or {}),
        "result": dict(result or {}),
        "note": note,
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_project(path: str | Path) -> dict:
    """读取存档为原始 dict（由调用方解释；格式不认识时抛 ValueError）。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    fmt = int(data.get("format", 0))
    if fmt > FORMAT:
        raise ValueError(f"存档格式版本过新（{fmt} > {FORMAT}），请升级本工具")
    return data


def peaks_from_project(data: dict) -> list[PeakSpec]:
    """从存档 dict 还原峰表。"""
    out: list[PeakSpec] = []
    for d in data.get("peaks", []):
        out.append(PeakSpec(
            pos=d["pos"], fwhm=d["fwhm"], area=d["area"],
            eta=d.get("eta", 0.6), kind=d.get("kind", "crystal"),
            fix_pos=d.get("fix_pos", False), fix_fwhm=d.get("fix_fwhm", False),
            fix_area=d.get("fix_area", False),
            kind_locked=d.get("kind_locked", False), label=d.get("label", "")))
    return out


def background_from_project(data: dict) -> BackgroundConfig:
    """从存档 dict 还原背景配置。"""
    d = data.get("background", {})
    return BackgroundConfig(
        model=d.get("model", "poly"),
        order=int(d.get("order", 3)),
        anchors=[tuple(a) for a in d.get("anchors", [])],
        snip_iter=int(d.get("snip_iter", 40)),
        end_points=int(d.get("end_points", 5)),
    )


def fit_options_from_project(data: dict) -> fitmod.FitOptions:
    """从存档 dict 还原拟合选项。"""
    d = data.get("fit_options", {})
    known = {f for f in fitmod.FitOptions().__dict__}
    return fitmod.FitOptions(**{k: v for k, v in d.items() if k in known})
