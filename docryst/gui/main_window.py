"""PolyXRD DoCryst 主窗口。

布局：左侧文件列表；中部交互分峰画布；右侧垂直三段——参数面板 / 峰表 /
结果卡。菜单：文件 / 工具（批量、工程存档）/ 语言 / 帮助（方法说明、关于、
版权、注册）。状态栏：语言 · 文件 · 版次/注册信息。

核心交互流（对齐 Jade 的分峰思路，操作现代化）：
    导入 → 自动分析（寻峰+迭代补峰+全谱拟合）→ 结果卡出 C；
    手动精修：加峰模式点击加峰 / 画布拖峰 / 峰表改参 / 锁定参数 → 拟合；
    手动改判结晶/非晶（峰表类型列，锁定后自动判据不再覆盖）→ 重算。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from docryst import edition
from docryst.core.dtypes import (
    BackgroundConfig,
    CrystResult,
    KIND_AMORPHOUS,
    Pattern,
    PeakSpec,
)
from docryst.core import project as project_mod
from docryst.core.report import build_csv, build_html_report
from docryst.core.plot import render_png
from docryst.gui import services
from docryst.gui.batch import run_batch
from docryst.gui.canvas import MODE_ADD, MODE_SELECT, PatternCanvas
from docryst.gui.dialogs import AboutDialog, CopyrightDialog, MethodDialog
from docryst.gui.panels import ControlPanel
from docryst.gui.peaktable import PeakTable
from docryst.gui.resources import resource_path
from docryst.gui.resultcard import ResultCard
from docryst.gui.workers import BusyDialog, Worker
from docryst.i18n import (
    current_language,
    load_language,
    save_language,
    set_language,
    tr,
)
from docryst.version import APP_NAME, __version__

LANG_ORDER = ("zh_CN", "en_US", "ja_JP")

#: 内部评估版状态栏提示的字色（醒目红，状态栏灰底上对比度足够）
INTERNAL_NOTICE_COLOR = "#C00000"


@dataclass
class Session:
    """单个谱图的完整分析会话（切换文件时保留）。"""

    pattern: Pattern
    peaks: list[PeakSpec] = field(default_factory=list)
    bg_model: str = "poly"
    bg_order: int = 3
    threshold: float = 3.0
    lo: float | None = None
    hi: float | None = None
    result: CrystResult | None = None
    undo_stack: list[list[PeakSpec]] = field(default_factory=list)

    def push_undo(self) -> None:
        self.undo_stack.append([p.copy() for p in self.peaks])
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)


class MainWindow(QMainWindow):
    """主窗口：导入 → 自动分析 → 手动精修 → 导出。"""

    def __init__(self) -> None:
        super().__init__()
        load_language()
        self._sessions: dict[str, Session] = {}
        self._worker: Worker | None = None
        self._busy: BusyDialog | None = None
        self._batch_csv: list[tuple[str, CrystResult]] = []
        self._reg = None
        self.act_regcode = None
        if not edition.IS_INTERNAL:
            from docryst.gui import registration
            registration.set_language(current_language().split("_")[0])
            self._reg = registration.RegistrationManager(
                APP_NAME, registration.default_state_path("PolyXRD-DoCryst"))
        self._build_actions()
        self._build_menus()
        self._build_central()
        self._build_status()
        self.retranslateUi()

    # ================================================================== #
    # 界面构建
    # ================================================================== #
    def _build_actions(self) -> None:
        self.act_open = QAction(self)
        self.act_open.triggered.connect(self._on_open)
        self.act_add_folder = QAction(self)
        self.act_add_folder.triggered.connect(self._on_add_folder)
        self.act_export_html = QAction(self)
        self.act_export_html.triggered.connect(self._on_export_html)
        self.act_export_csv = QAction(self)
        self.act_export_csv.triggered.connect(self._on_export_csv)
        self.act_export_png = QAction(self)
        self.act_export_png.triggered.connect(self._on_export_png)
        self.act_save_project = QAction(self)
        self.act_save_project.triggered.connect(self._on_save_project)
        self.act_load_project = QAction(self)
        self.act_load_project.triggered.connect(self._on_load_project)
        self.act_batch = QAction(self)
        self.act_batch.triggered.connect(self._on_batch)
        self.act_exit = QAction(self)
        self.act_exit.triggered.connect(self.close)

        self.act_method = QAction(self)
        self.act_method.triggered.connect(lambda: MethodDialog(self).exec())
        self.act_about = QAction(self)
        self.act_about.triggered.connect(lambda: AboutDialog(self).exec())
        self.act_copyright = QAction(self)
        self.act_copyright.triggered.connect(lambda: CopyrightDialog(self).exec())

        self.lang_group = QActionGroup(self)
        self.lang_group.setExclusive(True)
        self.act_langs: dict[str, QAction] = {}
        for code in LANG_ORDER:
            act = QAction(self)
            act.setCheckable(True)
            act.triggered.connect(lambda _c=False, k=code: self._on_language(k))
            self.lang_group.addAction(act)
            self.act_langs[code] = act

    def _build_menus(self) -> None:
        self.menu_file = self.menuBar().addMenu("")
        self.menu_file.addAction(self.act_open)
        self.menu_file.addAction(self.act_add_folder)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.act_export_html)
        self.menu_file.addAction(self.act_export_csv)
        self.menu_file.addAction(self.act_export_png)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.act_exit)

        self.menu_tools = self.menuBar().addMenu("")
        self.menu_tools.addAction(self.act_batch)
        self.menu_tools.addSeparator()
        self.menu_tools.addAction(self.act_save_project)
        self.menu_tools.addAction(self.act_load_project)

        self.menu_language = self.menuBar().addMenu("")
        for code in LANG_ORDER:
            self.menu_language.addAction(self.act_langs[code])

        self.menu_help = self.menuBar().addMenu("")
        self.menu_help.addAction(self.act_method)
        self.menu_help.addAction(self.act_about)
        self.menu_help.addAction(self.act_copyright)
        if not edition.IS_INTERNAL and self._reg is not None:
            self._reg.add_help_action(self.menu_help, self)
            self.act_regcode = self.menu_help.actions()[-1]

    def _build_central(self) -> None:
        splitter = QSplitter(Qt.Horizontal, self)

        # 左：文件列表
        left = QWidget(self)
        lv = QVBoxLayout(left)
        self.grp_files = QGroupBox(left)
        fv = QVBoxLayout(self.grp_files)
        self.file_list = QListWidget(self.grp_files)
        self.file_list.currentRowChanged.connect(self._on_file_selected)
        fv.addWidget(self.file_list)
        hb = QHBoxLayout()
        self.btn_add = QPushButton(self.grp_files)
        self.btn_add.clicked.connect(self._on_open)
        self.btn_remove = QPushButton(self.grp_files)
        self.btn_remove.clicked.connect(self._on_remove_file)
        self.btn_clear = QPushButton(self.grp_files)
        self.btn_clear.clicked.connect(self._on_clear_files)
        for w in (self.btn_add, self.btn_remove, self.btn_clear):
            hb.addWidget(w)
        fv.addLayout(hb)
        lv.addWidget(self.grp_files)
        splitter.addWidget(left)

        # 中：画布
        self.canvas = PatternCanvas(self)
        self.canvas.peak_add_requested.connect(self._on_canvas_add_peak)
        self.canvas.peak_delete_requested.connect(self._on_canvas_delete_peak)
        self.canvas.peak_selected.connect(self._on_canvas_select_peak)
        self.canvas.peak_moved.connect(self._on_canvas_peak_moved)
        self.canvas.drag_preview.connect(self._on_canvas_drag_preview)
        splitter.addWidget(self.canvas)

        # 右：参数面板 + (峰表/结果卡 垂直分组)
        self.panel = ControlPanel(self)
        self.panel.auto_requested.connect(self.run_auto)
        self.panel.fit_requested.connect(self.run_fit)
        self.panel.undo_requested.connect(self._on_undo)
        self.panel.range_changed.connect(self._on_params_changed)
        self.panel.params_changed.connect(self._on_params_changed)
        self.panel.add_mode_requested.connect(self._on_add_mode)
        self.peak_table = PeakTable(self)
        self.peak_table.peak_edited.connect(self._on_peak_edited)
        self.peak_table.peak_delete_requested.connect(self._delete_peak)
        self.peak_table.selection_changed.connect(self._on_table_select)
        self.result_card = ResultCard(self)
        from docryst.gui.panels import ResultDock

        right_dock = ResultDock(self.peak_table, self.result_card, self)
        splitter.addWidget(self.panel)
        splitter.addWidget(right_dock)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setStretchFactor(3, 0)
        splitter.setSizes([210, 560, 300, 430])
        self.setCentralWidget(splitter)
        icon = resource_path("app-icon.png")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

    def _build_status(self) -> None:
        self.lbl_lang = QLabel(self)
        self.lbl_file = QLabel(self)
        self.statusBar().addWidget(self.lbl_lang, 0)
        self.statusBar().addWidget(self.lbl_file, 0)
        if not edition.IS_INTERNAL and self._reg is not None:
            self._reg.attach_status_label(self.statusBar(), self)
        else:
            self.lbl_edition = QLabel(self)
            self.lbl_edition.setObjectName("editionStatusLabel")
            self.lbl_edition.setAlignment(Qt.AlignCenter)
            font = self.lbl_edition.font()
            font.setBold(True)
            self.lbl_edition.setFont(font)
            self.lbl_edition.setStyleSheet(f"color: {INTERNAL_NOTICE_COLOR};")
            self.statusBar().addPermanentWidget(self.lbl_edition, 1)

    def startup_registration(self) -> None:
        if self._reg is not None:
            self._reg.startup_check(self)

    # ================================================================== #
    # 多语言
    # ================================================================== #
    def retranslateUi(self) -> None:
        self.setWindowTitle(f"{APP_NAME} v{__version__} · {tr('app.title')}")
        self.menu_file.setTitle(tr("menu.file"))
        self.menu_tools.setTitle(tr("menu.tools"))
        self.menu_language.setTitle(tr("menu.language"))
        self.menu_help.setTitle(tr("menu.help"))
        self.act_open.setText(tr("menu.file.open"))
        self.act_add_folder.setText(tr("menu.file.add_folder"))
        self.act_export_html.setText(tr("menu.file.export_html"))
        self.act_export_csv.setText(tr("menu.file.export_csv"))
        self.act_export_png.setText(tr("menu.file.export_png"))
        self.act_exit.setText(tr("menu.file.exit"))
        self.act_batch.setText(tr("menu.tools.batch"))
        self.act_save_project.setText(tr("menu.tools.save_project"))
        self.act_load_project.setText(tr("menu.tools.load_project"))
        self.act_method.setText(tr("menu.help.method"))
        self.act_about.setText(tr("menu.help.about"))
        self.act_copyright.setText(tr("menu.help.copyright"))
        for code, act in self.act_langs.items():
            act.setText(tr(f"lang.{code}"))
            act.setChecked(code == current_language())
        self.grp_files.setTitle(tr("panel.files"))
        self.btn_add.setText(tr("panel.files.add"))
        self.btn_remove.setText(tr("panel.files.remove"))
        self.btn_clear.setText(tr("panel.files.clear"))
        self.panel.retranslate()
        self.peak_table.retranslate()
        self.result_card.retranslate()
        self.lbl_lang.setText(tr("status.lang",
                                 lang=tr(f"lang.{current_language()}")))
        if getattr(self, "lbl_edition", None) is not None:
            self.lbl_edition.setText(tr("status.internal_edition"))
        self._set_file_status(self._current_path() or tr("status.ready"))

    def _on_language(self, code: str) -> None:
        set_language(code)
        save_language(code)
        self.retranslateUi()
        if not edition.IS_INTERNAL and self._reg is not None:
            from docryst.gui import registration
            registration.set_language(code.split("_")[0])
            if self.act_regcode is not None:
                self.act_regcode.setText(registration.tr("输入注册码 (&R)…"))
            self._reg.refresh()

    # ================================================================== #
    # 文件
    # ================================================================== #
    def _on_open(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("dlg.open_pattern"), "", services.pattern_ext_filter())
        self._import_paths(paths)

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("dlg.add_folder"), "")
        if not folder:
            return
        paths = [str(p) for ext in services.PATTERN_EXTS
                 for p in sorted(Path(folder).glob(f"*{ext}"))]
        self._import_paths(paths)

    def _import_paths(self, paths) -> None:
        if not paths:
            return
        failed: list[str] = []
        last_ok = None
        for p in paths:
            name = Path(p).name
            if p in self._sessions:
                last_ok = p
                continue
            try:
                pat = services.load_pattern(p)
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{name}: {exc}")
                continue
            self._sessions[p] = Session(pattern=pat)
            self.file_list.addItem(name)
            last_ok = p
        if last_ok:
            self.file_list.setCurrentRow(
                list(self._sessions).index(last_ok))
        if failed:
            preview = "、".join(failed[:5]) + ("…" if len(failed) > 5 else "")
            self._msg_box(tr("msg.import_fail", names=preview), error=True)

    def _on_remove_file(self) -> None:
        row = self.file_list.currentRow()
        if row < 0:
            return
        path = list(self._sessions)[row]
        del self._sessions[path]
        self.file_list.takeItem(row)
        self._refresh_all()

    def _on_clear_files(self) -> None:
        self._sessions.clear()
        self.file_list.clear()
        self._refresh_all()

    def _on_file_selected(self, row: int) -> None:
        if 0 <= row < len(self._sessions):
            self._refresh_all()

    def _current_path(self) -> str | None:
        row = self.file_list.currentRow()
        if 0 <= row < len(self._sessions):
            return list(self._sessions)[row]
        return None

    def _session(self) -> Session | None:
        path = self._current_path()
        return self._sessions.get(path) if path else None

    # ================================================================== #
    # 状态同步
    # ================================================================== #
    def _refresh_all(self) -> None:
        """按当前会话同步面板/峰表/画布/结果卡。"""
        sess = self._session()
        if sess is None:
            self.canvas.clear()
            self.peak_table.setRowCount(0)
            self.result_card.clear()
            self._set_file_status(tr("status.ready"))
            return
        pat = sess.pattern
        self.panel.set_data_span(*pat.span)
        lo = sess.lo if sess.lo is not None else pat.span[0]
        hi = sess.hi if sess.hi is not None else pat.span[1]
        self.panel.set_range(lo, hi)
        self.panel.set_bg_config(sess.bg_model, sess.bg_order)
        self.panel.sp_threshold.blockSignals(True)
        self.panel.sp_threshold.setValue(sess.threshold)
        self.panel.sp_threshold.blockSignals(False)
        if sess.result is not None:
            fit = sess.result.fit
            # 分量配色必须用**拟合后**的峰类型（result.peaks 已按判据分类），
            # fit.peaks 里保留的是寻峰阶段的初判
            kinds = [p.kind for p in sess.result.peaks]
            self.canvas.update_model(
                fit.x, fit.y_obs, fit.y_bg, fit.components, kinds, fit.peaks)
            self.peak_table.load_peaks(fit.peaks, sess.result.area_all)
            self.result_card.set_result(sess.result)
        elif sess.peaks:
            self._refresh_preview(sess)
        else:
            self.canvas.set_pattern(pat.two_theta, pat.intensity)
            self.peak_table.setRowCount(0)
            self.result_card.clear()
        self._set_file_status(str(sess.pattern.source))

    def _refresh_preview(self, sess: Session) -> None:
        """按当前峰参数做不拟合预览（拖峰/改参的即时反馈）。"""
        params = self._collect_params(sess)
        try:
            x, y, bg, comps, _ = services.preview_curves(sess.pattern, params)
        except Exception:  # noqa: BLE001 —— 预览失败静默（如区间过窄）
            return
        self.canvas.update_model(x, y, bg, comps, [p.kind for p in params.peaks or []],
                                 list(params.peaks or []))

    def _collect_params(self, sess: Session) -> services.AnalysisParams:
        lo, hi = self.panel.range_values()
        a, b = sess.pattern.span
        lo = lo if lo > a + 1e-9 else None
        hi = hi if hi < b - 1e-9 else None
        bg_cfg = self.panel.bg_config()
        return services.AnalysisParams(
            lo=lo, hi=hi, bg_cfg=bg_cfg, fwhm_threshold=self.panel.threshold(),
            fit_opt=self.panel.fit_options(), peaks=sess.peaks,
            auto_add_peaks=self.panel.auto_add_peaks())

    def _set_file_status(self, text: str) -> None:
        self.lbl_file.setToolTip(text)
        cap = max(120, int(self.statusBar().width() * 0.3))
        self.lbl_file.setText(
            self.lbl_file.fontMetrics().elidedText(text, Qt.ElideMiddle, cap))

    # ================================================================== #
    # 参数联动
    # ================================================================== #
    def _on_params_changed(self) -> None:
        sess = self._session()
        if sess is None:
            return
        lo, hi = self.panel.range_values()
        sess.lo = lo if lo > sess.pattern.span[0] + 1e-9 else None
        sess.hi = hi if hi < sess.pattern.span[1] - 1e-9 else None
        sess.bg_model = self.panel.cmb_bg.currentData() or "poly"
        sess.bg_order = int(self.panel.sp_bg_order.value())
        sess.threshold = self.panel.threshold()
        if sess.peaks:
            self._refresh_preview(sess)

    def _on_add_mode(self, on: bool) -> None:
        self.canvas.set_mode(MODE_ADD if on else MODE_SELECT)

    # ================================================================== #
    # 计算（后台线程）
    # ================================================================== #
    def run_auto(self) -> None:
        """一键自动分析：寻峰 + 迭代补峰 + 全谱拟合。"""
        self._run_analysis(self._job_auto)

    def run_fit(self) -> None:
        """按当前峰表拟合（不寻峰）。"""
        self._run_analysis(self._job_fit)

    def _job_auto(self, sess: Session):
        params = self._collect_params(sess)
        params.peaks = None
        return services.run_auto(sess.pattern, params)

    def _job_fit(self, sess: Session):
        params = self._collect_params(sess)
        return services.run_fit(sess.pattern, params)

    def _run_analysis(self, job) -> None:
        sess = self._session()
        if sess is None:
            self._msg_box(tr("msg.no_pattern"), error=True)
            return
        if self._worker is not None:
            return
        # 记录面板参数到会话（后台任务按会话参数执行）
        self._on_params_changed()
        sess.push_undo()
        self._busy = BusyDialog(self, tr("busy.analyze"))
        self._worker = Worker(lambda: job(sess))
        self._worker.done.connect(self._on_analysis_done)
        self._worker.failed.connect(self._on_task_failed)
        self._worker.start()
        self._busy.exec()
        self._busy = None

    def _on_analysis_done(self, result: CrystResult) -> None:
        self._finish_task()
        sess = self._session()
        if sess is None or result is None:
            return
        sess.result = result
        # sess.peaks 与 fit.peaks 引用**同一组** PeakSpec 实例：此后画布拖动、
        # 峰表编辑都作用在这些实例上，重新拟合无需来回拷贝（单一事实来源）
        if result.fit is not None:
            sess.peaks = list(result.fit.peaks)
        if result.fit is not None and not result.fit.success:
            self._msg_box(tr("msg.fit_not_converged",
                             detail=result.fit.message), error=True)
        self._refresh_all()

    def _on_task_failed(self, tb: str) -> None:
        self._finish_task()
        self._msg_box(tr("msg.task_failed", detail=tb.splitlines()[-1]),
                      error=True)

    def _finish_task(self) -> None:
        if self._busy is not None:
            self._busy.accept()
            self._busy = None
        if self._worker is not None:
            self._worker.wait()
            self._worker = None

    # ================================================================== #
    # 画布交互
    # ================================================================== #
    def _on_canvas_add_peak(self, pos: float) -> None:
        sess = self._session()
        if sess is None:
            return
        lo, hi = self.panel.range_values()
        a, b = sess.pattern.span
        mask = (sess.pattern.two_theta >= lo) & (sess.pattern.two_theta <= hi)
        x = sess.pattern.two_theta[mask]
        if x.size < 5:
            return
        bg = self.panel.bg_config()
        y_net = np.maximum(
            sess.pattern.intensity[mask]
            - _quick_bg(x, sess.pattern.intensity[mask], bg), 0.0)
        peak = services.new_peak_at(x, y_net, pos,
                                    fwhm_threshold=self.panel.threshold())
        if peak.is_amorphous:
            peak.kind_locked = True
        sess.push_undo()
        sess.peaks.append(peak)
        sess.peaks.sort(key=lambda p: p.pos)
        sess.result = None
        self._refresh_preview(sess)
        self.peak_table.load_peaks(sess.peaks)
        self.statusBar().showMessage(tr("msg.peak_added", pos=peak.pos), 4000)

    def _on_canvas_delete_peak(self, idx: int) -> None:
        self._delete_peak(idx)

    def _on_canvas_select_peak(self, idx: int) -> None:
        self.peak_table.selectRow(idx)

    def _on_table_select(self, row: int) -> None:
        sess = self._session()
        if sess is None:
            return
        peaks = self._active_peaks(sess)
        if 0 <= row < len(peaks):
            self.canvas.set_peaks(peaks)
            self.canvas.set_selected(row)

    def _on_canvas_peak_moved(self, idx: int, pos: float) -> None:
        sess = self._session()
        if sess is None:
            return
        peaks = self._active_peaks(sess)
        if not (0 <= idx < len(peaks)):
            return
        sess.push_undo()
        peaks[idx].pos = float(pos)
        sess.result = None
        self._refresh_preview(sess)
        self._sync_table(sess)

    def _on_canvas_drag_preview(self, idx: int, pos: float) -> None:
        sess = self._session()
        if sess is None:
            return
        peaks = self._active_peaks(sess)
        if not (0 <= idx < len(peaks)):
            return
        old = peaks[idx].pos
        peaks[idx].pos = float(pos)
        self._refresh_preview(sess)
        peaks[idx].pos = old

    def _active_peaks(self, sess: Session) -> list[PeakSpec]:
        return sess.result.fit.peaks if (sess.result and sess.result.fit) else sess.peaks

    def _delete_peak(self, idx: int) -> None:
        sess = self._session()
        if sess is None:
            return
        peaks = self._active_peaks(sess)
        if not (0 <= idx < len(peaks)):
            return
        sess.push_undo()
        del peaks[idx]
        sess.result = None
        self._refresh_preview(sess)
        self._sync_table(sess)

    def _on_peak_edited(self, row: int, field: str, value) -> None:
        sess = self._session()
        if sess is None:
            return
        peaks = self._active_peaks(sess)
        if not (0 <= row < len(peaks)):
            return
        p = peaks[row]
        if field in ("pos", "fwhm", "eta", "area"):
            sess.push_undo()
            setattr(p, field, float(value))
            if field in ("fwhm",) and not p.kind_locked:
                p.kind = (KIND_AMORPHOUS
                          if p.fwhm > self.panel.threshold() else p.kind)
            sess.result = None
            self._refresh_preview(sess)
        elif field == "kind":
            sess.push_undo()
            p.kind = str(value)
            p.kind_locked = True
            self._refresh_preview(sess)
        elif field.startswith("fix_"):
            setattr(p, field, bool(value))
        self._sync_table(sess)

    def _sync_table(self, sess: Session) -> None:
        peaks = self._active_peaks(sess)
        total = (sess.result.area_all if sess.result
                 else sum(p.area for p in peaks))
        self.peak_table.load_peaks(peaks, total,
                                   selected=self.peak_table.selected_row())

    def _on_undo(self) -> None:
        sess = self._session()
        if sess is None or not sess.undo_stack:
            return
        sess.peaks = sess.undo_stack.pop()
        sess.result = None
        self._refresh_preview(sess)
        self._sync_table(sess)
        self.statusBar().showMessage(tr("msg.undone"), 3000)

    # ================================================================== #
    # 导出与批量
    # ================================================================== #
    def _require_result(self) -> CrystResult | None:
        sess = self._session()
        if sess is None or sess.result is None:
            self._msg_box(tr("msg.need_result"), error=True)
            return None
        return sess.result

    def _on_export_html(self) -> None:
        result = self._require_result()
        if result is None:
            return
        sess = self._session()
        default = f"{sess.pattern.sample_name()}_crystallinity.html"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dlg.export_html"), default, "HTML (*.html)")
        if not path:
            return
        png = str(Path(path).with_suffix(".fit.png"))
        fit = result.fit
        render_png(png, fit.x, fit.y_obs, fit.y_calc, fit.y_bg,
                   fit.components, [p.kind for p in result.peaks],
                   result.fwhm_threshold, labels=_plot_labels())
        html = build_html_report(
            sample=sess.pattern.sample_name(),
            file_name=sess.pattern.source, result=result, png_path=png,
            range_text=_range_text(result, sess),
            bg_text=tr("bg." + sess.bg_model) + f" (n={sess.bg_order})"
            if sess.bg_model == "poly" else tr("bg." + sess.bg_model))
        Path(path).write_text(html, encoding="utf-8")
        self.statusBar().showMessage(tr("msg.exported", path=path), 5000)

    def _on_export_csv(self) -> None:
        result = self._require_result()
        if result is None:
            return
        sess = self._session()
        default = f"{sess.pattern.sample_name()}_peaks.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dlg.export_csv"), default, "CSV (*.csv)")
        if not path:
            return
        text = build_csv(result, sample=sess.pattern.sample_name(),
                         file_name=sess.pattern.source)
        Path(path).write_text(text, encoding="utf-8-sig")
        self.statusBar().showMessage(tr("msg.exported", path=path), 5000)

    def _on_export_png(self) -> None:
        result = self._require_result()
        if result is None:
            return
        sess = self._session()
        default = f"{sess.pattern.sample_name()}_fit.png"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dlg.export_png"), default, "PNG (*.png)")
        if not path:
            return
        fit = result.fit
        render_png(path, fit.x, fit.y_obs, fit.y_calc, fit.y_bg,
                   fit.components, [p.kind for p in result.peaks],
                   result.fwhm_threshold, labels=_plot_labels())
        self.statusBar().showMessage(tr("msg.exported", path=path), 5000)

    def _on_save_project(self) -> None:
        sess = self._session()
        if sess is None:
            self._msg_box(tr("msg.no_pattern"), error=True)
            return
        default = f"{sess.pattern.sample_name()}{project_mod.EXT}"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dlg.save_project"), default,
            "DoCryst Project (*.dcy.json)")
        if not path:
            return
        peaks = self._active_peaks(sess)
        result = sess.result
        project_mod.save_project(
            path, pattern_path=sess.pattern.source,
            sample=sess.pattern.sample_name(),
            lo=sess.lo, hi=sess.hi,
            bg_cfg=BackgroundConfig(sess.bg_model, order=sess.bg_order),
            peaks=peaks, fwhm_threshold=sess.threshold,
            preprocess={}, note="",
            result={"degree": result.degree if result else None})
        self.statusBar().showMessage(tr("msg.exported", path=path), 5000)

    def _on_load_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("dlg.load_project"), "",
            "DoCryst Project (*.dcy.json);;All Files (*.*)")
        if not path:
            return
        try:
            data = project_mod.load_project(path)
        except Exception as exc:  # noqa: BLE001
            self._msg_box(tr("msg.task_failed", detail=str(exc)), error=True)
            return
        # 目标谱图：与存档同路径的已导入谱图，否则请用户选择
        target = str(Path(data.get("pattern_path", "")))
        if target not in self._sessions:
            self._msg_box(tr("msg.load_project_import_first",
                             path=target), error=True)
            return
        sess = self._sessions[target]
        sess.peaks = project_mod.peaks_from_project(data)
        bg = project_mod.background_from_project(data)
        sess.bg_model, sess.bg_order = bg.model, bg.order
        sess.threshold = float(data.get("fwhm_threshold", 3.0))
        self._refresh_all()
        self.statusBar().showMessage(tr("msg.project_loaded"), 5000)

    def _on_batch(self) -> None:
        if len(self._sessions) == 0:
            self._msg_box(tr("msg.no_pattern"), error=True)
            return
        self._on_params_changed()
        paths = list(self._sessions)
        lo, hi = self.panel.range_values()
        params = services.AnalysisParams(
            lo=lo, hi=hi, bg_cfg=self.panel.bg_config(),
            fwhm_threshold=self.panel.threshold(),
            fit_opt=self.panel.fit_options(),
            auto_add_peaks=self.panel.auto_add_peaks())
        self._busy = BusyDialog(self, tr("busy.batch", n=len(paths)))
        self._worker = Worker(run_batch, paths, params,
                              progress=self._on_batch_progress)
        self._worker.done.connect(self._on_batch_done)
        self._worker.failed.connect(self._on_task_failed)
        self._worker.start()
        self._busy.exec()
        self._busy = None

    def _on_batch_progress(self, done: int, total: int, name: str) -> None:
        if self._busy is not None:
            self._busy.set_message(
                tr("busy.batch_progress", done=done, total=total, name=name))

    def _on_batch_done(self, rows) -> None:
        self._finish_task()
        if not rows:
            self._msg_box(tr("msg.batch_empty"), error=True)
            return
        default = "crystallinity_batch.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dlg.export_csv"), default, "CSV (*.csv)")
        if not path:
            return
        write_batch_csv(path, rows)
        self.statusBar().showMessage(tr("msg.exported", path=path), 5000)

    # ================================================================== #
    # 工具
    # ================================================================== #
    def _msg_box(self, text: str, *, error: bool = False) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical if error else QMessageBox.Information)
        box.setWindowTitle(tr("msg.error") if error else tr("msg.info"))
        box.setText(text)
        box.exec()


def _quick_bg(x: np.ndarray, y: np.ndarray, cfg) -> np.ndarray:
    """加峰时的快速净信号估计（与 core 背景同参，但不做全局拟合）。"""
    from docryst.core import background as bgmod

    return bgmod.evaluate(x, y, cfg)


def _range_text(result: CrystResult, sess: Session) -> str:
    fit = result.fit
    return f"{fit.x[0]:.2f} – {fit.x[-1]:.2f}°" if fit is not None else ""


def _plot_labels() -> dict[str, str]:
    return {k: tr("canvas.legend." + k)
            for k in ("obs", "calc", "bg", "diff", "crystal", "amorph")}
