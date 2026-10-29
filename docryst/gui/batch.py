"""批量结晶度计算与汇总 CSV。"""

from __future__ import annotations

from pathlib import Path

from docryst.core.report import build_csv
from docryst.gui import services
from docryst.i18n import tr


def run_batch(paths: list[str], params: services.AnalysisParams,
              progress=None):
    """对路径列表逐一自动分析，返回 [(路径, CrystResult)]。

    ``params`` 为面板当前参数（区间按各谱图自身 span 裁剪）；``progress(done,
    total, name)`` 回调驱动忙窗文案；单文件失败**跳过并记录**，不中断整批。
    """
    rows = []
    total = len(paths)
    for i, p in enumerate(paths):
        if progress is not None:
            progress(i, total, Path(p).name)
        try:
            pat = services.load_pattern(p)
            res = services.run_auto(pat, params)
            rows.append((p, res))
        except Exception:  # noqa: BLE001 —— 批量容错：失败行进 CSV 备注列
            rows.append((p, None))
    if progress is not None:
        progress(total, total, "")
    return rows


def write_batch_csv(path: str, rows) -> None:
    """把批量结果写成 UTF-8 BOM 汇总 CSV（每文件：结果摘要，失败行注明）。"""
    lines: list[str] = []
    sep = ","
    header = [
        tr("report.file"), tr("report.sample"),
        tr("result.degree"), "sigma", tr("report.area_crystal"),
        tr("report.area_amorphous"), tr("result.n_crystal"),
        tr("result.n_amorphous"), tr("result.threshold"),
        tr("result.degree_total"), tr("result.coverage"),
        tr("result.rwp"), tr("result.r2"), tr("result.note"),
    ]
    lines.append(sep.join(header))
    for p, res in rows:
        name = Path(p).name
        sample = Path(p).stem
        if res is None:
            lines.append(sep.join(
                [name, sample] + [""] * 11 + [tr("result.batch_failed")]))
            continue
        warn = "; ".join(res.warnings)
        lines.append(sep.join([
            name, sample, f"{res.degree:.2f}", f"{res.sigma:.2f}",
            f"{res.area_crystal:.0f}", f"{res.area_amorphous:.0f}",
            str(res.n_crystal), str(res.n_amorphous),
            f"{res.fwhm_threshold:.1f}", f"{res.degree_total:.2f}",
            f"{res.coverage:.3f}", f"{res.rwp:.4f}", f"{res.r2:.5f}", warn,
        ]))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
