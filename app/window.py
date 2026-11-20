"""The main window: inputs on the left, results in tabs on the right, progress at the bottom."""

import multiprocessing
import os
import queue as queue_module
import time
from datetime import datetime

from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                             QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
                             QSlider, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
                             QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from app import APP_NAME, SOURCE_URL, __version__, engine, export, plots
from app.inputs import (FIELDS, GROUPS, PRESETS, THETA_SOLVE, defaults, gallet_crest_kV, load_json, save_json,
                        validate)


# ----------------------------------------------------------------------------- background run
class Worker(QObject):
    """Runs engine.run in a separate process (spawn) and relays its messages as Qt signals.
    A process, not a thread: the heavy quadratures would otherwise starve the window of the GIL."""
    progress = pyqtSignal(float, int, str, str)
    message = pyqtSignal(str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, values, name, parent=None):
        super().__init__(parent)
        ctx = multiprocessing.get_context("spawn")
        self.queue = ctx.Queue()
        self.cancel_event = ctx.Event()
        self.process = ctx.Process(target=engine.run_in_process, args=(values, name, self.queue, self.cancel_event))
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)
        self.done = False
        self.cancel_requested_at = None

    def start(self):
        self.process.start()
        self.timer.start()

    def running(self):
        return not self.done

    def cancel(self):
        self.cancel_event.set()
        self.cancel_requested_at = time.time()

    def kill(self):
        if self.process.is_alive():
            self.process.terminate()
        self.done = True
        self.timer.stop()

    def _poll(self):
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue_module.Empty:
                break
            if kind == "progress":
                self.progress.emit(*payload)
            elif kind == "message":
                self.message.emit(payload)
            else:
                self._finish()
                {"finished": self.finished, "failed": self.failed}.get(kind, self.cancelled).emit(
                    *(() if kind == "cancelled" else (payload,)))
                return
        if self.cancel_requested_at and time.time() - self.cancel_requested_at > 10 and self.process.is_alive():
            self.kill()                       # a single long quadrature step: stop it the hard way
            self.cancelled.emit()
        elif not self.process.is_alive() and self.queue.empty() and not self.done:
            self._finish()
            self.failed.emit(f"The simulation process ended unexpectedly (exit code {self.process.exitcode}).")

    def _finish(self):
        self.done = True
        self.timer.stop()
        self.process.join(timeout=5)


# ----------------------------------------------------------------------------- helpers
class PlotTab(QWidget):
    """A matplotlib figure with its toolbar (zoom, pan, save)."""

    def __init__(self, extra=None):
        super().__init__()
        self.figure = Figure(figsize=(7, 5), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        top = QHBoxLayout()
        top.addWidget(NavigationToolbar2QT(self.canvas, self))
        top.addStretch()
        lay.addLayout(top)
        if extra is not None:
            lay.addWidget(extra)
        lay.addWidget(self.canvas, 1)

    def placeholder(self, text="Run a simulation to see the results here."):
        self.figure.clear()
        self.figure.text(0.5, 0.5, text, ha="center", va="center", color="#6B7090")
        self.canvas.draw_idle()


def default_output_folder():
    """Documents/<app name> (the working directory makes no sense for an installed program)."""
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), APP_NAME)


def _num(x, digits=5):
    if x is None:
        return "–"
    if isinstance(x, float):
        return f"{x:.{digits}g}"
    return str(x)


# ----------------------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__} · space charge of impulse corona in a rod-plane gap")
        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction("&About", self._about)
        self.resize(1500, 920)
        self.widgets = {}
        self.runs = []                 # RunResult list, same order as the runs list widget
        self.worker = None
        self.t_started = 0.0

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._left_panel())
        splitter.addWidget(self._right_panel())
        splitter.setSizes([480, 1020])
        self.setCentralWidget(splitter)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setFormat("%p %")
        self.progress.setMinimumWidth(260)
        self.stage_label = QLabel("Ready.")
        self.clock_label = QLabel("")
        self.statusBar().addWidget(self.stage_label, 1)
        self.statusBar().addPermanentWidget(self.clock_label)
        self.statusBar().addPermanentWidget(self.progress)
        self.clock = QTimer(self)
        self.clock.timeout.connect(self._tick_clock)

        self.set_values(defaults())
        self._refresh_all()

    # ------------------------------------------------------------------ left panel
    def _left_panel(self):
        panel = QWidget()
        lay = QVBoxLayout(panel)

        row = QHBoxLayout()
        self.preset_box = QComboBox()
        self.preset_box.addItems(PRESETS)
        apply_btn = QPushButton("Apply preset")
        apply_btn.clicked.connect(lambda: self.set_values(PRESETS[self.preset_box.currentText()]))
        row.addWidget(self.preset_box, 1)
        row.addWidget(apply_btn)
        lay.addLayout(row)
        row = QHBoxLayout()
        for text, slot in (("Load inputs…", self._load_inputs), ("Save inputs…", self._save_inputs),
                           ("Reset", lambda: self.set_values(defaults()))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)

        form_host = QWidget()
        form_lay = QVBoxLayout(form_host)
        for title, fields in GROUPS:
            box = QGroupBox(title)
            form = QFormLayout(box)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            for f in fields:
                w = self._make_widget(f)
                self.widgets[f.key] = w
                label = QLabel(f.label)
                label.setToolTip(f.tooltip)
                form.addRow(label, w)
                if f.key == "crest_kV":
                    b = QPushButton("Set crest to the Gallet U50 of the gap")
                    b.setToolTip("U50 = 3400 / (1 + 8/d) kV, d in m")
                    b.clicked.connect(lambda: self.widgets["crest_kV"].setValue(
                        gallet_crest_kV(self.widgets["D_cm"].value())))
                    form.addRow("", b)
            form_lay.addWidget(box)
        form_lay.addStretch()
        self.widgets["theta_mode"].currentTextChanged.connect(self._theta_mode_changed)
        self.widgets["until_crest"].toggled.connect(self._until_crest_changed)
        self.widgets["front_us"].valueChanged.connect(lambda _: self._until_crest_changed(self.widgets["until_crest"].isChecked()))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(form_host)
        lay.addWidget(scroll, 1)

        out = QGroupBox("Output")
        ol = QVBoxLayout(out)
        self.show_check = QCheckBox("Show the results in the program (plots)")
        self.show_check.setChecked(True)
        self.csv_check = QCheckBox("Save CSV files")
        self.xlsx_check = QCheckBox("Save an Excel workbook (.xlsx)")
        for c in (self.show_check, self.csv_check, self.xlsx_check):
            ol.addWidget(c)
        row = QHBoxLayout()
        self.folder_edit = QLineEdit(default_output_folder())
        self.folder_edit.setToolTip("Every run is saved in its own sub-folder.")
        browse = QPushButton("…")
        browse.setFixedWidth(32)
        browse.clicked.connect(self._choose_folder)
        row.addWidget(QLabel("Folder"))
        row.addWidget(self.folder_edit, 1)
        row.addWidget(browse)
        ol.addLayout(row)
        lay.addWidget(out)

        row = QHBoxLayout()
        self.run_btn = QPushButton("▶  Run simulation")
        self.run_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.run_btn.clicked.connect(self.start_run)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_run)
        row.addWidget(self.run_btn, 2)
        row.addWidget(self.cancel_btn, 1)
        lay.addLayout(row)

        runs_box = QGroupBox("Runs (select one to show it; tick others to compare)")
        rl = QVBoxLayout(runs_box)
        self.runs_list = QListWidget()
        self.runs_list.setMaximumHeight(90)
        self.runs_list.currentRowChanged.connect(lambda _: self._refresh_all())
        self.runs_list.itemChanged.connect(lambda _: self._refresh_all())
        rl.addWidget(self.runs_list)
        row = QHBoxLayout()
        for text, slot in (("Export selected…", self._export_selected), ("Load its inputs", self._load_run_inputs),
                           ("Remove", self._remove_run)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        rl.addLayout(row)
        lay.addWidget(runs_box)
        return panel

    def _make_widget(self, f):
        if f.kind == "bool":
            w = QCheckBox()
        elif f.kind == "choice":
            w = QComboBox()
            w.addItems(f.choices)
        elif f.kind == "int":
            w = QSpinBox()
            w.setRange(int(f.minimum), int(f.maximum))
        else:
            w = QDoubleSpinBox()
            w.setDecimals(f.decimals)
            w.setRange(f.minimum, f.maximum)
            w.setSingleStep(10 ** -min(f.decimals, 2) if f.decimals else 1)
        if f.kind in ("int", "float"):
            w.setKeyboardTracking(False)
            w.setAccelerated(True)
            if f.unit:
                w.setSuffix(" " + f.unit)
            if f.special:
                w.setSpecialValueText(f.special)
        w.setToolTip(f.tooltip)
        return w

    def values(self):
        v = {}
        for k, f in FIELDS.items():
            w = self.widgets[k]
            v[k] = (w.isChecked() if f.kind == "bool" else w.currentText() if f.kind == "choice" else w.value())
        return v

    def set_values(self, v):
        for k, f in FIELDS.items():
            if k not in v:
                continue
            w = self.widgets[k]
            if f.kind == "bool":
                w.setChecked(bool(v[k]))
            elif f.kind == "choice":
                w.setCurrentText(str(v[k]))
            elif f.kind == "int":
                w.setValue(int(v[k]))
            else:
                w.setValue(float(v[k]))
        self._theta_mode_changed(self.widgets["theta_mode"].currentText())
        self._until_crest_changed(self.widgets["until_crest"].isChecked())

    def _until_crest_changed(self, on):
        """With 'whole front' ticked, the end time follows the time to crest and cannot be edited."""
        self.widgets["t_end_us"].setEnabled(not on and self.run_btn.isEnabled() if hasattr(self, "run_btn") else not on)
        if on:
            self.widgets["t_end_us"].setValue(self.widgets["front_us"].value())

    def _theta_mode_changed(self, mode):
        solve = mode == THETA_SOLVE
        self.widgets["theta_deg"].setEnabled(not solve)
        for k in ("ref_D_cm", "ref_V_kV", "ref_L_cm"):
            self.widgets[k].setEnabled(solve)

    def _load_inputs(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load inputs", self.folder_edit.text(), "JSON (*.json)")
        if path:
            try:
                self.set_values(load_json(path))
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Load inputs", f"Could not read {path}:\n{exc}")

    def _save_inputs(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save inputs", os.path.join(self.folder_edit.text(), "inputs.json"),
                                              "JSON (*.json)")
        if path:
            save_json(path, self.values())

    def _choose_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.folder_edit.text())
        if d:
            self.folder_edit.setText(d)

    # ------------------------------------------------------------------ right panel
    def _right_panel(self):
        self.tabs = QTabWidget()
        self.tab_vt = PlotTab()
        self.tab_pos = PlotTab()
        self.tab_drift = PlotTab()

        controls = QWidget()
        rows = QVBoxLayout(controls)
        rows.setContentsMargins(4, 0, 4, 0)
        cl = QHBoxLayout()
        rows.addLayout(cl)
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setCheckable(True)
        self.play_btn.toggled.connect(self._toggle_play)
        self.snap_slider = QSlider(Qt.Horizontal)
        self.snap_slider.valueChanged.connect(lambda _: self._draw_profile())
        self.snap_label = QLabel("t = –")
        self.snap_label.setMinimumWidth(260)
        cl.addWidget(self.play_btn)
        cl.addWidget(self.snap_slider, 1)
        cl.addWidget(self.snap_label)
        cl = QHBoxLayout()
        rows.addLayout(cl)
        cl.addWidget(QLabel("Show:"))
        self.comp_checks = {}
        for k in engine.COMPONENTS:
            c = QCheckBox(k)
            c.setChecked(True)
            c.toggled.connect(lambda _: self._draw_profile())
            self.comp_checks[k] = c
            cl.addWidget(c)
        self.logx_check = QCheckBox("log z")
        self.logx_check.toggled.connect(lambda _: self._draw_profile())
        self.fixy_check = QCheckBox("fixed y-axis")
        self.fixy_check.setToolTip("Same y-range at every instant (steadier while playing).")
        self.fixy_check.setChecked(True)
        self.fixy_check.toggled.connect(lambda _: self._draw_profile())
        cl.addStretch()
        cl.addWidget(self.logx_check)
        cl.addWidget(self.fixy_check)
        self.tab_prof = PlotTab(controls)
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(450)
        self.play_timer.timeout.connect(self._play_step)

        bursts = QSplitter(Qt.Vertical)
        self.burst_table = QTableWidget()
        self.burst_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tab_bars = PlotTab()
        bursts.addWidget(self.burst_table)
        bursts.addWidget(self.tab_bars)
        bursts.setSizes([260, 520])

        self.param_table = QTableWidget()
        self.param_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: monospace;")

        self.tabs.addTab(self.tab_vt, "Voltage && tip field")
        self.tabs.addTab(self.tab_prof, "Field profiles E(z)")
        self.tabs.addTab(self.tab_pos, "Cloud positions")
        self.tabs.addTab(self.tab_drift, "Drift && charge")
        self.tabs.addTab(bursts, "Bursts")
        self.tabs.addTab(self.param_table, "Parameters")
        self.tabs.addTab(self.log_view, "Log")
        return self.tabs

    def _about(self):
        QMessageBox.about(self, f"About {APP_NAME}", (
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Estimation of the development of the impulse corona discharge in a non-uniform gap: "
            "successive corona bursts and drifting space charge in a rod-plane air gap, after the model "
            "of Wang Wenduan and Wang Haiting (1988).</p>"
            "<p>Diploma thesis of Nikolaos Bampaliaris, School of Electrical and Computer Engineering, "
            "Aristotle University of Thessaloniki. Supervisor: Prof. Pantelis Mikropoulos.</p>"
            "<p>Free software under the GNU General Public License v3.0: you may use, study, share and modify it. "
            f"Source code: <a href='{SOURCE_URL}'>{SOURCE_URL}</a></p>"))

    # ------------------------------------------------------------------ running
    def start_run(self):
        v = self.values()
        problems = validate(v)
        if problems:
            QMessageBox.warning(self, "Inputs", "\n".join(problems))
            return
        name = f"#{len(self.runs) + 1}  D {v['D_cm']:g} cm · {v['crest_kV']:g} kV · {v['front_us']:g} µs"
        self.log_view.appendPlainText(f"\n===== {name}  ({datetime.now():%H:%M:%S}) =====")
        self.worker = Worker(v, name, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.message.connect(self.log_view.appendPlainText)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self._set_running(True)
        self.worker.start()

    def cancel_run(self):
        if self.worker:
            self.worker.cancel()
            self.stage_label.setText("Cancelling…")
            self.cancel_btn.setEnabled(False)

    def _set_running(self, running):
        self.run_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        for w in self.widgets.values():
            w.setEnabled(not running)
        if not running:
            self._theta_mode_changed(self.widgets["theta_mode"].currentText())
        self._until_crest_changed(self.widgets["until_crest"].isChecked())
        if running:
            self.progress.setValue(0)
            self.t_started = time.time()
            self.clock.start(500)
        else:
            self.clock.stop()

    def _tick_clock(self):
        s = int(time.time() - self.t_started)
        self.clock_label.setText(f"elapsed {s // 60:02d}:{s % 60:02d}")

    def _on_progress(self, frac, stage, stage_name, detail):
        self.progress.setValue(int(frac * 1000))
        self.stage_label.setText(f"Stage {stage}/4 · {stage_name} — {detail}")

    def _on_finished(self, result):
        self._set_running(False)
        self.progress.setValue(1000)
        why = result.derived.get("stopped because", "")
        self.stage_label.setText(f"Finished {result.name} in {result.elapsed_s:.1f} s · {len(result.clouds)} burst(s)"
                                 + (f" · {why}" if why.startswith("model limit") else "") + ".")
        if why.startswith("model limit"):
            QMessageBox.information(self, "Successive-burst model limit", (
                f"The run stopped at {why[len('model limit at '):]}.\n\nBeyond this point the tip field no longer "
                "falls below the inception threshold between bursts, so the successive-burst model does not apply. "
                "The results up to this instant are shown."))
        self.runs.append(result)
        item = QListWidgetItem(result.name)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Unchecked)
        self.runs_list.blockSignals(True)
        self.runs_list.addItem(item)
        self.runs_list.blockSignals(False)
        saved = self._save_outputs(result, self.csv_check.isChecked(), self.xlsx_check.isChecked())
        if self.show_check.isChecked():
            self.runs_list.setCurrentRow(len(self.runs) - 1)
        if saved:
            self.log_view.appendPlainText("Saved: " + ", ".join(saved))
            self.stage_label.setText(self.stage_label.text() + "  Saved to " + os.path.dirname(saved[0]))

    def _on_failed(self, text):
        self._set_running(False)
        self.stage_label.setText("The simulation stopped with an error (see the Log tab).")
        self.log_view.appendPlainText(text)
        QMessageBox.critical(self, "Simulation error", text.strip().splitlines()[-1])

    def _on_cancelled(self):
        self._set_running(False)
        self.progress.setValue(0)
        self.stage_label.setText("Cancelled.")
        self.log_view.appendPlainText("Cancelled by the user.")

    def _save_outputs(self, result, csv, xlsx, folder=None):
        if not (csv or xlsx):
            return []
        if folder is None:
            tag = result.name.split()[0].lstrip("#")
            folder = os.path.join(self.folder_edit.text(), f"run{tag}_{datetime.now():%Y%m%d_%H%M%S}")
        saved = []
        try:
            if csv:
                export.save_csv(result, folder)
                saved.append(os.path.join(folder, "*.csv"))
            if xlsx:
                saved.append(export.save_xlsx(result, os.path.join(folder, "results.xlsx")))
        except OSError as exc:
            QMessageBox.warning(self, "Save", f"Could not save the results:\n{exc}")
        return saved

    def closeEvent(self, event):
        if self.worker is not None and self.worker.running():
            self.worker.kill()
        event.accept()

    # ------------------------------------------------------------------ runs list
    def _current(self):
        i = self.runs_list.currentRow()
        return self.runs[i] if 0 <= i < len(self.runs) else None

    def _others(self):
        cur = self.runs_list.currentRow()
        return [self.runs[i] for i in range(self.runs_list.count())
                if i != cur and self.runs_list.item(i).checkState() == Qt.Checked]

    def _export_selected(self):
        r = self._current()
        if r is None:
            return
        d = QFileDialog.getExistingDirectory(self, "Export the selected run to", self.folder_edit.text())
        if not d:
            return
        csv, xlsx = self.csv_check.isChecked(), self.xlsx_check.isChecked()
        saved = self._save_outputs(r, csv or not xlsx, xlsx, folder=d)
        if saved:
            self.stage_label.setText("Saved: " + ", ".join(saved))

    def _load_run_inputs(self):
        r = self._current()
        if r is not None:
            self.set_values(r.inputs)

    def _remove_run(self):
        i = self.runs_list.currentRow()
        if 0 <= i < len(self.runs):
            del self.runs[i]
            self.runs_list.takeItem(i)
            self._refresh_all()

    # ------------------------------------------------------------------ drawing
    def _refresh_all(self):
        r = self._current()
        tabs = (self.tab_vt, self.tab_pos, self.tab_drift, self.tab_prof, self.tab_bars)
        if r is None:
            for t in tabs:
                t.placeholder()
            self.burst_table.clear()
            self.burst_table.setRowCount(0)
            self.param_table.clear()
            self.param_table.setRowCount(0)
            return
        others = self._others()
        plots.voltage_and_tip(self.tab_vt.figure, r, others)
        plots.cloud_positions(self.tab_pos.figure, r, others)
        plots.drift_distance(self.tab_drift.figure, r, others)
        plots.burst_bars(self.tab_bars.figure, r, others)
        for t in (self.tab_vt, self.tab_pos, self.tab_drift, self.tab_bars):
            t.canvas.draw_idle()
        self.snap_slider.blockSignals(True)
        self.snap_slider.setRange(0, len(r.snap_t_us) - 1)
        self.snap_slider.setValue(len(r.snap_t_us) - 1)
        self.snap_slider.blockSignals(False)
        self._draw_profile()
        self._fill_tables(r)

    def _draw_profile(self):
        r = self._current()
        if r is None:
            return
        i = self.snap_slider.value()
        shown = [k for k, c in self.comp_checks.items() if c.isChecked()]
        limits = None
        if self.fixy_check.isChecked() and shown:
            lo = min(float(r.profiles[k].min()) for k in shown)
            hi = max(float(r.profiles[k].max()) for k in shown)
            pad = 0.05 * (hi - lo or 1.0)
            limits = (lo - pad, hi + pad)
        plots.field_profile(self.tab_prof.figure, r, self._others(), i, shown, self.logx_check.isChecked(), limits)
        self.tab_prof.canvas.draw_idle()
        note = r.snap_labels[i]
        self.snap_label.setText(f"t = {r.snap_t_us[i]:.4g} µs ({i + 1}/{len(r.snap_t_us)})" + (f" · {note}" if note else ""))

    def _toggle_play(self, on):
        self.play_btn.setText("❚❚ Pause" if on else "▶ Play")
        if on:
            if self.snap_slider.value() >= self.snap_slider.maximum():
                self.snap_slider.setValue(0)
            self.play_timer.start()
        else:
            self.play_timer.stop()

    def _play_step(self):
        if self.snap_slider.value() >= self.snap_slider.maximum():
            self.play_btn.setChecked(False)
        else:
            self.snap_slider.setValue(self.snap_slider.value() + 1)

    def _fill_tables(self, r):
        cols = [("number", "Burst"), ("t_birth_us", "t [µs]"), ("V_kV", "V [kV]"), ("L_cm", "L [cm]"), ("Q_nC", "Q [nC]"),
                ("A_SI", "A [C m^(B−3)]"), ("z_c0_cm", "z_c0 [cm]"), ("t_absorbed_us", "absorbed at [µs]"),
                ("dip_cm", "dip crossed [cm]")]
        t = self.burst_table
        t.clear()
        t.setColumnCount(len(cols))
        t.setRowCount(len(r.clouds))
        t.setHorizontalHeaderLabels([h for _, h in cols])
        for i, c in enumerate(r.clouds):
            for j, (k, _) in enumerate(cols):
                item = QTableWidgetItem(_num(c[k]))
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(i, j, item)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.horizontalHeader().setStretchLastSection(True)

        rows = engine.input_rows(r)
        p = self.param_table
        p.clear()
        p.setColumnCount(3)
        p.setRowCount(len(rows))
        p.setHorizontalHeaderLabels(["Parameter", "Value", "Unit"])
        for i, (a, b, c) in enumerate(rows):
            for j, x in enumerate((a, _num(b, 6) if not isinstance(b, bool) else str(b), c)):
                p.setItem(i, j, QTableWidgetItem(str(x)))
        p.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        p.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        p.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
