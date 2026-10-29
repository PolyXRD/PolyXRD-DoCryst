"""核心数据类型（纯 dataclass，无 Qt / 无 matplotlib 依赖）。

设计要点
--------
* 峰参数采用 **面积参数化**：``PeakSpec.area`` 就是该峰的积分面积（面积归一的
  pseudo-Voigt 幅值），无需再做数值积分，也让「结晶峰面积 / 总面积」这一
  结晶度公式在数学上闭合（数值积分会引入截断误差，宽非晶包尤甚）。
* ``kind`` 只有两种取值：``"crystal"``（结晶峰）与 ``"amorphous"``（非晶宽包）。
  自动判据默认 FWHM > :data:`DEFAULT_FWHM_AMORPH` 度判为非晶，且**允许逐峰手动
  改判**——判据只是助手，最终归属由用户决定（与 Jade 报告中勾选非晶峰的
  交互口径一致）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
#: 非晶峰判据的出厂默认值（度）：FWHM > 3° 判为非晶宽包。
#: 依据：Jade 全谱拟合计算相对结晶度的通行做法（"将半高宽大于 3° 的衍射峰
#: 标定为非晶峰"），见 README「方法学」一节列出的文献与操作口径。
DEFAULT_FWHM_AMORPH = 3.0

#: Cu Kα1 波长（Å），d 值换算与 Scherrer 粒径用
CU_KA1 = 1.540598

#: 峰形（模型）标识
SHAPE_PV = "pseudo_voigt"

#: 峰类型标识
KIND_CRYSTAL = "crystal"
KIND_AMORPHOUS = "amorphous"

#: 背景模型标识
BG_NONE = "none"
BG_LINEAR_ENDS = "linear_ends"
BG_LINEAR_LSQ = "linear_lsq"
BG_POLY = "poly"
BG_ANCHORS = "anchors"
BG_SNIP = "snip"

#: 需要与峰参数一起参与最小二乘的背景模型（其余为固定背景）
BG_FREE_MODELS = (BG_LINEAR_LSQ, BG_POLY)


def d_spacing(two_theta_deg: float | np.ndarray, wavelength: float = CU_KA1):
    """由 2θ（度）换算晶面间距 d（Å）。"""
    tt = np.radians(np.asarray(two_theta_deg, dtype=float) / 2.0)
    return wavelength / (2.0 * np.sin(tt))


# --------------------------------------------------------------------------- #
# 谱图
# --------------------------------------------------------------------------- #
@dataclass
class Pattern:
    """一条待分析的谱图（2θ 升序、强度已按需要平滑/剥 Kα2）。"""

    two_theta: np.ndarray
    intensity: np.ndarray
    wavelength: float = CU_KA1
    source: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.two_theta = np.asarray(self.two_theta, dtype=float)
        self.intensity = np.asarray(self.intensity, dtype=float)
        if self.two_theta.shape != self.intensity.shape:
            raise ValueError(
                f"2θ 与强度长度不一致：{self.two_theta.size} vs {self.intensity.size}")
        if self.two_theta.size < 10:
            raise ValueError(f"数据点过少（{self.two_theta.size}），无法分峰拟合")
        if np.any(np.diff(self.two_theta) <= 0):
            raise ValueError("2θ 轴不是严格递增，请先按 2θ 排序")

    # -- 派生量 ---------------------------------------------------------- #
    @property
    def n(self) -> int:
        return int(self.two_theta.size)

    @property
    def span(self) -> tuple[float, float]:
        """2θ 全范围。"""
        return float(self.two_theta[0]), float(self.two_theta[-1])

    @property
    def step(self) -> float:
        """平均步长（度）。"""
        return float(np.mean(np.diff(self.two_theta)))

    def crop(self, lo: float, hi: float) -> "Pattern":
        """按 2θ 区间裁切（含端点内最近的采样点）。"""
        mask = (self.two_theta >= lo) & (self.two_theta <= hi)
        if mask.sum() < 10:
            raise ValueError(f"区间 {lo:.2f}–{hi:.2f}° 内数据点不足（{int(mask.sum())}）")
        return Pattern(self.two_theta[mask], self.intensity[mask],
                       self.wavelength, self.source, dict(self.meta))

    def sample_name(self) -> str:
        """样品名：文件名主干（无扩展名），导入时用于报告抬头。"""
        from pathlib import Path

        if not self.source:
            return "sample"
        return Path(self.source).stem


# --------------------------------------------------------------------------- #
# 峰
# --------------------------------------------------------------------------- #
@dataclass
class PeakSpec:
    """一个分峰分量（结晶峰或非晶宽包）。

    参数化：面积归一的 pseudo-Voigt，``area`` 即积分面积，
    ``fwhm`` 为半高全宽（度），``eta`` 为洛伦兹成分占比（0=纯高斯，1=纯洛伦兹）。
    ``fix_*`` 为 True 时该参数在拟合中锁定不参与优化。
    """

    pos: float
    fwhm: float
    area: float
    eta: float = 0.6
    kind: str = KIND_CRYSTAL
    fix_pos: bool = False
    fix_fwhm: bool = False
    fix_area: bool = False
    label: str = ""
    #: 用户手动改判过结晶/非晶后置 True —— 自动判据不再覆盖该峰
    kind_locked: bool = False
    #: 拟合后的参数标准偏差（由协方差回填；未拟合时为 0）
    pos_err: float = 0.0
    fwhm_err: float = 0.0
    area_err: float = 0.0

    def __post_init__(self) -> None:
        self.pos = float(self.pos)
        self.fwhm = float(self.fwhm)
        self.area = float(self.area)
        self.eta = float(min(max(self.eta, 0.0), 1.0))
        if self.kind not in (KIND_CRYSTAL, KIND_AMORPHOUS):
            raise ValueError(f"未知峰类型：{self.kind}")

    @property
    def is_amorphous(self) -> bool:
        return self.kind == KIND_AMORPHOUS

    @property
    def height(self) -> float:
        """峰高（由面积/半高宽反算，pseudo-Voigt 的峰顶值）。"""
        if self.fwhm <= 0:
            return 0.0
        g = (2.0 / self.fwhm) * np.sqrt(np.log(2.0) / np.pi)
        lor = 2.0 / (np.pi * self.fwhm)
        return float(self.area * (self.eta * lor + (1.0 - self.eta) * g))

    def copy(self, **kw) -> "PeakSpec":
        """浅拷贝并覆盖指定字段。"""
        data = dict(
            pos=self.pos, fwhm=self.fwhm, area=self.area, eta=self.eta,
            kind=self.kind, fix_pos=self.fix_pos, fix_fwhm=self.fix_fwhm,
            fix_area=self.fix_area, label=self.label,
            kind_locked=self.kind_locked, pos_err=self.pos_err,
            fwhm_err=self.fwhm_err, area_err=self.area_err)
        data.update(kw)
        return PeakSpec(**data)


# --------------------------------------------------------------------------- #
# 背景
# --------------------------------------------------------------------------- #
@dataclass
class BackgroundConfig:
    """背景配置。

    model:
        ``linear_ends``  两端点直线（Jade 常用口径：直线背地两点定线，固定不拟合）。
                         注意：宽非晶包在区间端点仍有强度时，端点直线会系统性吃掉
                         非晶包下沿，C 值偏高（合成数据实测 +4~+8 pp，见 README 验证表）
        ``linear_lsq``   直线，截距/斜率与峰参数一同最小二乘
        ``poly``         多项式（2–5 阶，自变量归一化），与峰参数一同最小二乘。
                         **默认模型**：能跟随弯曲/递减基线，又不易吸收宽包
                         （多项式阶数固定且远低于宽包的自由度）
        ``anchors``      手动锚点分段折线（固定）——最可控，推荐进阶用户
        ``snip``         SNIP 迭代削峰（固定；会削弱宽非晶包，仅作对照）
        ``none``         不扣背景
    """

    model: str = BG_POLY
    order: int = 3
    anchors: list[tuple[float, float]] = field(default_factory=list)
    snip_iter: int = 40
    #: 两端点直线取端部多少个采样点的中位数（抑制噪声）
    end_points: int = 5

    def is_free(self) -> bool:
        return self.model in BG_FREE_MODELS

    def n_params(self) -> int:
        """自由背景参数个数。"""
        if self.model == BG_LINEAR_LSQ:
            return 2
        if self.model == BG_POLY:
            return int(max(2, min(self.order, 5))) + 1
        return 0


# --------------------------------------------------------------------------- #
# 拟合结果
# --------------------------------------------------------------------------- #
@dataclass
class PeakResult:
    """单峰拟合结果（含参数标准偏差与派生量）。"""

    index: int
    pos: float
    fwhm: float
    area: float
    eta: float
    kind: str
    area_err: float = 0.0
    pos_err: float = 0.0
    fwhm_err: float = 0.0
    height: float = 0.0
    label: str = ""
    #: 全部拟合峰面积之和（汇总时回填，供面积占比计算）
    total_area: float = 0.0

    @property
    def area_pct(self) -> float:
        """该峰面积占**全部拟合峰**面积之和的百分比（Jade 报告口径）。"""
        return 0.0 if self.total_area <= 0 else self.area / self.total_area * 100.0

    @property
    def d(self) -> float:
        return float(d_spacing(self.pos))


@dataclass
class FitResult:
    """一次全谱拟合的产物：曲线、指标、协方差。"""

    x: np.ndarray
    y_obs: np.ndarray
    y_calc: np.ndarray
    y_bg: np.ndarray
    components: list[np.ndarray]
    peaks: list[PeakSpec]
    bg_params: np.ndarray
    rwp: float
    r2: float
    chi2: float
    n_iter: int
    success: bool
    message: str
    #: 自由参数协方差矩阵（与 :attr:`free_index` 同序）；无法估计时为 None
    cov: np.ndarray | None = None
    #: {"pos"/"fwhm"/"area"/"eta"/"bg"}[peak_index] -> 参数在自由向量中的下标
    free_index: dict[str, dict[int, int]] = field(default_factory=dict)
    elapsed_s: float = 0.0

    @property
    def residual(self) -> np.ndarray:
        return self.y_obs - self.y_calc


@dataclass
class CrystResult:
    """结晶度分析汇总。"""

    degree: float                 # 结晶度 C（%），面积比法
    sigma: float                  # C 的 1σ 标准偏差（由协方差传播）
    area_crystal: float
    area_amorphous: float
    n_crystal: int
    n_amorphous: int
    area_obs_total: float         # 观测谱扣背景后积分面积
    degree_total: float           # 总面积法交叉验证（%）
    coverage: float               # (Ac+Aa)/A_obs 拟合覆盖度
    fwhm_threshold: float
    peaks: list[PeakResult]
    rwp: float
    r2: float
    fit: FitResult | None = None
    warnings: list[str] = field(default_factory=list)
    #: 非晶包在区间端点的强度/峰顶最大比（背景体检指标，>3% 提示）
    halo_edge_ratio: float = 0.0

    @property
    def area_all(self) -> float:
        return self.area_crystal + self.area_amorphous
