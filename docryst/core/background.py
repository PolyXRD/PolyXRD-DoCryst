"""背景模型：求值、参数打包/解包、端点与锚点辅助。

结晶度分析对背景的口径**极其敏感**：非晶宽包必须留在扣背景后的信号里，
由 pseudo-Voigt 分量去拟合，绝不能连同背景一起被扣掉。因此本模块把
"哪一端是背景、哪一端是被分析信号"写成显式约定：

- 固定背景（``linear_ends`` / ``anchors`` / ``snip``）：只去掉仪器与空气散射
  形成的缓变基线（SNIP 例外，见下方警告），宽包留在信号中；
- 自由背景（``linear_lsq`` / ``poly``）：背景参数与峰参数联合最小二乘，
  需配合"避免宽包被背景吃掉"的约束，故界面上标注为进阶用法。

.. warning::
   ``snip`` 是形态学削峰，会把**宽非晶包当作背景削掉**。用它算结晶度会系统性
   高估 C 值，界面只在"对照/诊断"场景推荐，并在结果卡给出警示。
"""

from __future__ import annotations

import numpy as np

from docryst.core.dtypes import (
    BG_ANCHORS,
    BG_LINEAR_ENDS,
    BG_LINEAR_LSQ,
    BG_NONE,
    BG_POLY,
    BG_SNIP,
    BackgroundConfig,
)


# --------------------------------------------------------------------------- #
# 固定背景（不参与拟合）
# --------------------------------------------------------------------------- #
def linear_end_points(x: np.ndarray, y: np.ndarray, n_end: int = 5) -> tuple[float, float]:
    """取两端各 ``n_end`` 点的中位数作为直线背景的两个端点。

    用中位数而非端点单点值：单点受噪声与截断效应影响大，两端各取 3–10 点
    的中位数在线性背景上几乎无偏，却是抗噪的（Jade 的直线背地同样是以
    区间两端强度定线，本实现只是把"端点"换成"端点邻域的中位数"）。
    """
    k = int(max(1, min(n_end, max(1, x.size // 10))))
    y_lo = float(np.median(y[:k]))
    y_hi = float(np.median(y[-k:]))
    return y_lo, y_hi


def _poly_eval(x: np.ndarray, coeffs: np.ndarray) -> np.ndarray:
    """多项式求值（coeffs 按升幂排列，与 np.polyfit 的返回序相反）。"""
    out = np.zeros_like(x, dtype=float)
    for power, c in enumerate(coeffs):
        out = out + c * x ** power
    return out


def snip_background(x: np.ndarray, y: np.ndarray, n_iter: int = 40) -> np.ndarray:
    """SNIP 削峰背景（递增窗口法，Ryan et al. 1988 的实用变体）。

    逐轮把窗口宽度 p = 1..n_iter 应用 ``y[i] = min(y[i], (y[i−p]+y[i+p])/2)``：
    第 p 轮能直接削掉宽度 ≤ 2p 通道的结构，因此收敛快（固定 1 通道窗口的
    朴素写法要 O(宽度) 轮才能削掉宽峰，对洛伦兹尾尤其慢）。

    在 LLS 域外这里用开方变换（Poisson 计数的方差稳定变换），避免强峰支配
    削峰方向。**注意**：宽非晶包（FWHM 数度以上）在足够迭代次数下会被一并
    削掉，该背景只适合做对照，不建议用于结晶度定量。
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    if n < 3:
        return y.copy()
    work = np.sqrt(np.maximum(y, 1.0))
    n_iter = int(max(1, min(n_iter, n // 2)))
    for p in range(1, n_iter + 1):
        shifted = np.pad(work, p, mode="edge")
        avg = 0.5 * (shifted[: n] + shifted[2 * p: 2 * p + n])
        work = np.minimum(work, avg)
    return np.maximum(work, 0.0) ** 2


# --------------------------------------------------------------------------- #
# 求值
# --------------------------------------------------------------------------- #
def evaluate(x: np.ndarray, y: np.ndarray, cfg: BackgroundConfig,
             params: np.ndarray | None = None) -> np.ndarray:
    """按配置求背景曲线。

    ``params`` 仅对自由背景模型（``linear_lsq`` / ``poly``）有意义：
    拟合过程中传入当前参数向量，拟合结束后传入最优参数。
    固定背景忽略 ``params``，由数据本身确定。
    """
    x = np.asarray(x, dtype=float)
    model = cfg.model

    if model == BG_NONE:
        return np.zeros_like(x)

    if model == BG_LINEAR_ENDS:
        y_lo, y_hi = linear_end_points(x, np.asarray(y, dtype=float), cfg.end_points)
        if x[-1] == x[0]:
            return np.full_like(x, y_lo)
        k = (y_hi - y_lo) / (x[-1] - x[0])
        return y_lo + k * (x - x[0])

    if model == BG_ANCHORS:
        return anchor_curve(x, cfg.anchors)

    if model == BG_SNIP:
        return snip_background(x, np.asarray(y, dtype=float), cfg.snip_iter)

    # ---- 自由背景：需要参数 ---- #
    n = cfg.n_params()
    if params is None or len(params) < n:
        params = default_free_params(x, np.asarray(y, dtype=float), cfg)
    params = np.asarray(params, dtype=float)

    if model == BG_LINEAR_LSQ:
        return params[0] + params[1] * (x - x[0])
    if model == BG_POLY:
        # 自变量归一化到 [-1, 1]，避免高阶幂次导致的条件数灾难
        t = _normalize_x(x)
        return _poly_eval(t, params[:n])
    raise ValueError(f"未知背景模型：{model}")


def _normalize_x(x: np.ndarray) -> np.ndarray:
    """把 x 线性映射到 [-1, 1]（多项式背景的数值稳定化）。"""
    lo, hi = float(x[0]), float(x[-1])
    if hi <= lo:
        return np.zeros_like(x)
    return 2.0 * (x - lo) / (hi - lo) - 1.0


def default_free_params(x: np.ndarray, y: np.ndarray, cfg: BackgroundConfig) -> np.ndarray:
    """自由背景的初值：端点直线作为零阶近似，高阶系数置 0。"""
    y_lo, y_hi = linear_end_points(x, y, cfg.end_points)
    n = cfg.n_params()
    if cfg.model == BG_LINEAR_LSQ:
        return np.array([0.5 * (y_lo + y_hi), (y_hi - y_lo)], dtype=float)
    coeffs = np.zeros(n)
    coeffs[0] = 0.5 * (y_lo + y_hi)
    if n > 1:
        coeffs[1] = 0.5 * (y_hi - y_lo)
    return coeffs


def bounds_free(x: np.ndarray, y: np.ndarray, cfg: BackgroundConfig
                ) -> tuple[np.ndarray, np.ndarray]:
    """自由背景参数的上下界（背景不得为负、幅度不超过数据量级）。"""
    span = float(np.max(y) - np.min(y)) if y.size else 1.0
    span = max(span, 1.0)
    n = cfg.n_params()
    # 常数项可正可负（允许小幅负背景），幅度限制在数据动态范围内
    lo = np.full(n, -2.0 * span)
    hi = np.full(n, 2.0 * span)
    return lo, hi


# --------------------------------------------------------------------------- #
# 锚点折线
# --------------------------------------------------------------------------- #
def anchor_curve(x: np.ndarray, anchors: list[tuple[float, float]]) -> np.ndarray:
    """手动锚点分段折线（锚点需按 2θ 升序；区间外按端点值水平延伸）。"""
    if not anchors:
        return np.zeros_like(x)
    pts = sorted((float(a), float(b)) for a, b in anchors)
    xs = np.array([p[0] for p in pts], dtype=float)
    ys = np.array([p[1] for p in pts], dtype=float)
    if xs.size == 1:
        return np.full_like(x, ys[0])
    return np.interp(x, xs, ys)


def anchors_from_ends(x: np.ndarray, y: np.ndarray) -> list[tuple[float, float]]:
    """以两端点生成初版锚点（用户之后可拖动/增删）。"""
    y_lo, y_hi = linear_end_points(x, y)
    return [(float(x[0]), y_lo), (float(x[-1]), y_hi)]
