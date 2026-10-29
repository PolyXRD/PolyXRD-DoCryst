"""HTML 报告生成（自包含：谱图 base64 内嵌，浏览器直接打开/打印）。

报告结构：抬头 → 样品信息 → 结果表 → 峰表（2θ/d/FWHM/面积/面积%/类型）→
方法说明（公式、判据、注意事项）→ 谱图 → 落款。文案经 i18n 三语。
"""

from __future__ import annotations

import base64
import datetime
import html
from pathlib import Path

from docryst.core.dtypes import CrystResult, d_spacing
from docryst.i18n import tr
from docryst.version import APP_NAME, __version__

_STYLE = """
  body{ font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
        color:#1e293b; background:#f1f5f9; margin:0; line-height:1.6; }
  .page{ max-width:820px; margin:24px auto; background:#fff; border:1px solid #e2e8f0;
         border-radius:14px; padding:28px 32px; box-shadow:0 8px 28px rgba(15,23,42,.08); }
  h1{ font-size:20px; color:#0F172A; margin:0 0 4px; }
  .meta{ font-size:12px; color:#64748B; margin-bottom:16px; }
  h2{ font-size:13px; color:#0284C7; text-transform:uppercase;
      letter-spacing:1px; border-bottom:1px solid #e2e8f0; padding-bottom:4px; }
  table{ width:100%; border-collapse:collapse; font-size:13px; }
  td,th{ padding:4px 6px; border-bottom:1px solid #f1f5f9; text-align:right; }
  td.k,th:first-child{ color:#64748B; text-align:left; }
  td.v{ font-weight:600; }
  th{ border-bottom:2px solid #0F172A; font-weight:600; }
  .big{ font-size:30px; font-weight:700; color:#0284C7; }
  .unit{ font-size:14px; color:#64748B; font-weight:400; }
  .warn{ color:#B45309; font-size:12px; }
  .method{ font-size:12px; color:#475569; }
  img{ max-width:100%; border:1px solid #e2e8f0; border-radius:8px; margin-top:8px; }
  .foot{ font-size:11px; color:#94A3B8; margin-top:18px; text-align:center; }
"""


def build_html_report(*, sample: str, file_name: str, result: CrystResult,
                      png_path: str | None = None,
                      range_text: str = "",
                      bg_text: str = "") -> str:
    """构建自包含 HTML 报告。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    big = (f"<span class='big'>{result.degree:.2f}</span>"
           f"<span class='unit'> ± {result.sigma:.2f} %</span>"
           if result.sigma > 0 else
           f"<span class='big'>{result.degree:.2f}</span><span class='unit'> %</span>")

    rows = [
        (tr("report.area_crystal"), f"{result.area_crystal:.1f}"),
        (tr("report.area_amorphous"), f"{result.area_amorphous:.1f}"),
        (tr("report.n_peaks"),
         f"{result.n_crystal} / {result.n_amorphous}"),
        (tr("result.threshold"), f"> {result.fwhm_threshold:.1f}°"),
        (tr("result.degree_total"), f"{result.degree_total:.2f} %"),
        (tr("result.coverage"), f"{result.coverage * 100:.1f} %"),
        (tr("result.rwp"), f"{result.rwp * 100:.2f} %"),
        (tr("result.r2"), f"{result.r2:.5f}"),
        (tr("result.bg_model"), bg_text),
        (tr("panel.range"), range_text),
    ]
    row_html = "".join(
        f"<tr><td class='k'>{html.escape(k)}</td><td class='v'>{html.escape(v)}</td></tr>"
        for k, v in rows)

    th = ("<tr>" + "".join(
        f"<th>{html.escape(t)}</th>" for t in (
            "#", tr("peak.pos"), "d (Å)", tr("peak.fwhm"), tr("peak.height"),
            tr("peak.area"), tr("peak.area_pct"), tr("peak.eta"), tr("peak.kind")))
        + "</tr>")
    trs = []
    for p in result.peaks:
        kind_txt = tr("peak.kind_amorphous") if p.kind == "amorphous" else tr("peak.kind_crystal")
        err = f" ± {p.area_err:.0f}" if p.area_err > 0 else ""
        trs.append(
            "<tr>" + "".join(
                f"<td>{v}</td>" for v in (
                    str(p.index + 1), f"{p.pos:.3f}", f"{d_spacing(p.pos):.4f}",
                    f"{p.fwhm:.3f}", f"{p.height:.0f}",
                    f"{p.area:.0f}{err}", f"{p.area_pct:.2f}", f"{p.eta:.2f}",
                    kind_txt)) + "</tr>")
    peak_table = f"<table>{th}{''.join(trs)}</table>"

    warn_html = ""
    if result.warnings:
        items = "".join(f"<li>{html.escape(tr(k))}</li>" for k in result.warnings)
        warn_html = f"<ul class='warn'>{items}</ul>"

    img_html = ""
    if png_path and Path(png_path).exists():
        b64 = base64.b64encode(Path(png_path).read_bytes()).decode("ascii")
        img_html = f"<img src='data:image/png;base64,{b64}' alt='pattern'>"

    method = (
        f"<p class='method'>{html.escape(tr('report.method.p1'))}</p>"
        f"<p class='method'>{html.escape(tr('report.method.p2'))}</p>"
        f"<p class='method'>{html.escape(tr('report.method.p3'))}</p>")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{html.escape(tr('report.title'))} · {html.escape(sample)}</title>
<style>{_STYLE}</style>
</head>
<body>
  <div class="page">
    <h1>{html.escape(tr('report.title'))}</h1>
    <div class="meta">{html.escape(APP_NAME)} v{__version__} ·
      {html.escape(tr('report.generated', ts=now))}</div>

    <h2>{html.escape(tr('report.sample'))}</h2>
    <table>
      <tr><td class="k">{html.escape(tr('report.sample'))}</td>
          <td class="v">{html.escape(sample)}</td></tr>
      <tr><td class="k">{html.escape(tr('report.file'))}</td>
          <td class="v">{html.escape(file_name)}</td></tr>
    </table>

    <h2>{html.escape(tr('report.result_h'))}</h2>
    <p>{big}</p>
    <table>{row_html}</table>
    {warn_html}

    <h2>{html.escape(tr('report.peaks_h'))}</h2>
    {peak_table}

    <h2>{html.escape(tr('report.method_h'))}</h2>
    {method}

    {img_html}

    <div class="foot">{html.escape(tr('report.footnote'))}<br>
      © 2026 PolyXRD Team</div>
  </div>
</body>
</html>
"""


def build_csv(result: CrystResult, *, sample: str, file_name: str,
              delimiter: str = ",") -> str:
    """峰表 + 结果摘要 CSV（UTF-8 BOM 由调用方写入）。"""
    lines = [delimiter.join([
        "#", tr("peak.pos"), "d(A)", tr("peak.fwhm"), tr("peak.height"),
        tr("peak.area"), "area_err", tr("peak.area_pct"), tr("peak.eta"),
        tr("peak.kind")])]
    for p in result.peaks:
        kind = tr("peak.kind_amorphous") if p.kind == "amorphous" else tr("peak.kind_crystal")
        lines.append(delimiter.join([
            str(p.index + 1), f"{p.pos:.4f}", f"{d_spacing(p.pos):.5f}",
            f"{p.fwhm:.4f}", f"{p.height:.1f}", f"{p.area:.1f}",
            f"{p.area_err:.1f}", f"{p.area_pct:.3f}", f"{p.eta:.3f}", kind]))
    lines.append("")
    summary = [
        (tr("report.sample"), sample), (tr("report.file"), file_name),
        (tr("result.degree"), f"{result.degree:.3f}"),
        (f"{tr('result.degree')} sigma", f"{result.sigma:.3f}"),
        (tr("report.area_crystal"), f"{result.area_crystal:.1f}"),
        (tr("report.area_amorphous"), f"{result.area_amorphous:.1f}"),
        (tr("result.n_crystal"), str(result.n_crystal)),
        (tr("result.n_amorphous"), str(result.n_amorphous)),
        (tr("result.threshold"), f"{result.fwhm_threshold:.2f}"),
        (tr("result.degree_total"), f"{result.degree_total:.3f}"),
        (tr("result.coverage"), f"{result.coverage:.4f}"),
        (tr("result.rwp"), f"{result.rwp:.4f}"),
        (tr("result.r2"), f"{result.r2:.5f}"),
        (tr("result.halo_edge"), f"{result.halo_edge_ratio:.3f}"),
    ]
    lines.extend(f"{k}{delimiter}{v}" for k, v in summary)
    return "\n".join(lines) + "\n"
