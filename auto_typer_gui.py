"""AutoTyper app window (GUI).

Types the given text into another window as if a person were typing it.
The engine is auto_typer_console.py, used as is.

Run:    python3 auto_typer_gui.py        (installs the required packages automatically on first run)
Global hotkeys: F9 stops, F10 pauses/resumes
"""

import os
import platform
import statistics
import subprocess
import sys
from string import Template

os.environ["AUTO_TYPER_GUI"] = "1"          # tell the engine to prepare PySide6 as well
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import auto_typer_console as core           # noqa: E402  (imported after the required packages are ready)

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF   # noqa: E402
from PySide6.QtGui import (                              # noqa: E402
    QColor, QFont, QIcon, QLinearGradient, QPainter, QPalette, QPen,
)
from PySide6.QtWidgets import (                          # noqa: E402
    QAbstractButton, QAbstractSpinBox, QApplication, QDoubleSpinBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit, QProgressBar,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

APP_NAME = "AutoTyper"

# ---------- Theme ----------

LIGHT = dict(bg="#f5f5f7", card="#ffffff", border="#e6e6eb", text="#1d1d1f", muted="#86868b",
             accent="#0a7aff", accent_hover="#2a8cff", accent2="#30b566", track="#d5d5da",
             field="#f3f3f6", danger="#ff3b30", warn="#ff9f0a", ok="#28c76f",
             banner_bg="#fff4d6", banner_fg="#6b4e00")
DARK = dict(bg="#161618", card="#232326", border="#333338", text="#f5f5f7", muted="#98989f",
            accent="#0a84ff", accent_hover="#3d9bff", accent2="#32d17a", track="#4a4a50",
            field="#1a1a1d", danger="#ff453a", warn="#ffa01e", ok="#32d74b",
            banner_bg="#3a3116", banner_fg="#ffd77a")
T = dict(LIGHT)

QSS = Template("""
* { font-size: 13px; }
QMainWindow, QWidget#root { background: $bg; }
QLabel { color: $text; background: transparent; }
QLabel#title { font-size: 22px; font-weight: 700; }
QLabel#subtitle, QLabel#muted { color: $muted; }
QLabel#heading { color: $muted; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#cap { color: $muted; font-size: 11px; }
QLabel#val { font-size: 19px; font-weight: 650; }
QFrame#card { background: $card; border: 1px solid $border; border-radius: 14px; }
QFrame#banner { background: $banner_bg; border-radius: 10px; }
QFrame#banner QLabel { color: $banner_fg; }
QPlainTextEdit { background: transparent; color: $text; border: none; font-size: 14px;
                 selection-background-color: $accent; selection-color: white; }
QDoubleSpinBox, QSpinBox { background: $field; color: $text; border: 1px solid transparent;
                 border-radius: 8px; padding: 5px 10px; min-width: 84px; }
QDoubleSpinBox:hover, QSpinBox:hover { border: 1px solid $border; }
QDoubleSpinBox:focus, QSpinBox:focus { border: 1px solid $accent; }
QProgressBar { background: $track; border: none; border-radius: 3px; }
QProgressBar::chunk { background: $accent; border-radius: 3px; }
QPushButton { background: $card; color: $text; border: 1px solid $border; border-radius: 10px;
              padding: 9px 18px; font-weight: 600; }
QPushButton:hover { border-color: $muted; }
QPushButton:disabled { color: $muted; background: transparent; border-color: $border; }
QPushButton#primary { background: $accent; color: white; border: none; padding: 10px 30px; }
QPushButton#primary:hover { background: $accent_hover; }
QPushButton#primary:disabled { background: $track; color: $muted; }
QPushButton#danger { color: $danger; }
QPushButton#danger:disabled { color: $muted; }
QPushButton#ghost { background: transparent; border: none; color: $muted; padding: 9px 10px; }
QPushButton#ghost:hover { color: $text; }
QPushButton#ghost:disabled { color: $track; }
QToolTip { background: $card; color: $text; border: 1px solid $border; padding: 4px; }
""")

STATE_COLOR = {
    "idle": "muted", "countdown": "warn", "typing": "ok",
    "paused": "warn", "stopped": "muted", "done": "accent", "error": "danger",
}


def apply_theme(app):
    global T
    dark = app.palette().color(QPalette.ColorRole.Window).lightness() < 128
    T = dict(DARK if dark else LIGHT)
    app.setStyleSheet(QSS.substitute(T))


def rgba(hex_color, alpha):
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


# ---------- Small widgets ----------

class Switch(QAbstractButton):
    """A toggle switch (behaves like a checkbox)."""

    def __init__(self, checked=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 24)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T["accent"] if self.isChecked() else T["track"]))
        p.drawRoundedRect(QRectF(0, 0, 42, 24), 12, 12)
        p.setBrush(QColor("white"))
        x = 21 if self.isChecked() else 3
        p.drawEllipse(QRectF(x, 3, 18, 18))


def card():
    f = QFrame()
    f.setObjectName("card")
    return f


def heading(text):
    label = QLabel(text.upper())
    label.setObjectName("heading")
    return label


class Tile(QWidget):
    """A small statistic: a caption above a large value."""

    def __init__(self, caption):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        self.cap = QLabel(caption)
        self.cap.setObjectName("cap")
        self.val = QLabel("—")
        self.val.setObjectName("val")
        lay.addWidget(self.cap)
        lay.addWidget(self.val)

    def set(self, value, caption=None):
        self.val.setText(value)
        if caption:
            self.cap.setText(caption)


# ---------- Distribution chart ----------

def histogram(xs, bins=30):
    """Trim the top 5% and compute bar heights. Returns (range start, range end, counts, trimmed count)."""
    if not xs:
        return None
    s = sorted(xs)
    cut = s[min(len(s) - 1, int(len(s) * 0.95))]
    lo = s[0]
    hi = max(cut, lo + 1e-6)
    counts = [0] * bins
    over = 0
    for x in s:
        if x > hi:
            over += 1
            continue
        i = min(bins - 1, int((x - lo) / (hi - lo) * bins))
        counts[i] += 1
    return lo, hi, counts, over


class ChartWidget(QWidget):
    """Draws the distribution of intervals between characters as vertical bars."""

    def __init__(self, title, color_key):
        super().__init__()
        self.title = title
        self.color_key = color_key
        self.xs = []
        self.setMinimumHeight(150)

    def set_data(self, xs):
        self.xs = list(xs)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(T[self.color_key])
        muted = QColor(T["muted"])
        text = QColor(T["text"])
        w, h = self.width(), self.height()

        small = QFont(self.font())
        small.setPixelSize(11)
        p.setFont(small)
        p.setPen(muted)
        p.drawText(QRectF(0, 0, w, 16), Qt.AlignLeft | Qt.AlignVCenter, self.title)

        left, right, top, bottom = 0, 0, 24, 22
        area = QRectF(left, top, w - left - right, h - top - bottom)

        # faint grid
        grid = QColor(T["border"])
        p.setPen(QPen(grid, 1))
        for k in range(4):
            y = area.top() + area.height() * k / 3
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))

        data = histogram(self.xs)
        if not data:
            p.setPen(muted)
            p.drawText(area, Qt.AlignCenter, "No data yet")
            return
        lo, hi, counts, over = data
        n = len(counts)
        mean = statistics.fmean(self.xs)
        sd = statistics.pstdev(self.xs) if len(self.xs) > 1 else 0.0
        span = hi - lo

        def xpos(v):
            return area.left() + (min(max(v, lo), hi) - lo) / span * area.width()

        # ±1σ band
        band = QColor(color)
        band.setAlpha(28)
        x0, x1 = xpos(mean - sd), xpos(mean + sd)
        p.setPen(Qt.NoPen)
        p.setBrush(band)
        p.drawRoundedRect(QRectF(x0, area.top(), max(2.0, x1 - x0), area.height()), 6, 6)

        # bars
        peak = max(counts) or 1
        slot = area.width() / n
        bw = max(2.0, slot * 0.68)
        for i, c in enumerate(counts):
            if c == 0:
                continue
            bh = max(3.0, area.height() * c / peak)
            rect = QRectF(area.left() + i * slot + (slot - bw) / 2, area.bottom() - bh, bw, bh)
            g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            top_c = QColor(color)
            bot_c = QColor(color)
            bot_c.setAlpha(150)
            g.setColorAt(0, top_c)
            g.setColorAt(1, bot_c)
            p.setBrush(g)
            p.drawRoundedRect(rect, min(3.0, bw / 2), min(3.0, bw / 2))

        # mean line
        mx = xpos(mean)
        p.setPen(QPen(text, 1, Qt.DashLine))
        p.drawLine(QPointF(mx, area.top()), QPointF(mx, area.bottom()))

        # axis labels
        y = h - bottom + 5
        p.setPen(muted)
        p.drawText(QRectF(0, y, 80, 16), Qt.AlignLeft | Qt.AlignVCenter, f"{lo:.2f}s")
        p.drawText(QRectF(w - 80, y, 80, 16), Qt.AlignRight | Qt.AlignVCenter, f"{hi:.2f}s")
        p.setPen(text)
        p.drawText(QRectF(mx - 60, y, 120, 16), Qt.AlignCenter, f"mean {mean:.3f}s")
        if over:
            p.setPen(muted)
            p.drawText(QRectF(w - 220, 0, 220, 16), Qt.AlignRight | Qt.AlignVCenter,
                       f"{over} above the top 5% omitted")


# ---------- macOS permissions ----------

def accessibility_granted():
    """Whether macOS 'Accessibility' permission is granted. Assumes True if it cannot be checked."""
    if platform.system() != "Darwin":
        return True
    try:
        import ctypes
        import ctypes.util
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return True


def open_privacy_settings(kind):
    try:
        subprocess.Popen(["open", f"x-apple.systempreferences:com.apple.preference.security?Privacy_{kind}"])
    except Exception:
        pass


# ---------- Main window ----------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1120, 800)
        self.setMinimumSize(980, 740)
        self.typer = core.Typer()
        self.plan = None
        self.plan_text = None
        self.running = False
        self.last_chart_update = 0.0
        self.shown_state = None

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        # header
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        t = QLabel("Auto Typer")
        t.setObjectName("title")
        st = QLabel("Types your text into any window, the way a person would.")
        st.setObjectName("subtitle")
        titles.addWidget(t)
        titles.addWidget(st)
        head.addLayout(titles)
        head.addStretch(1)
        self.state_pill = QLabel()
        head.addWidget(self.state_pill, 0, Qt.AlignVCenter)
        outer.addLayout(head)

        # permission notice (only shown on macOS when the permission is missing)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(14, 8, 10, 8)
        bl.addWidget(QLabel("Accessibility permission is missing, so typing may not work."), 1)
        b = QPushButton("Open Settings")
        b.clicked.connect(lambda: open_privacy_settings("Accessibility"))
        bl.addWidget(b)
        b2 = QPushButton("Check Again")
        b2.clicked.connect(self.refresh_banner)
        bl.addWidget(b2)
        outer.addWidget(self.banner)

        # body
        body = QHBoxLayout()
        body.setSpacing(16)
        outer.addLayout(body, 1)

        left = QVBoxLayout()
        left.setSpacing(16)
        body.addLayout(left, 1)

        # text card
        text_card = card()
        tl = QVBoxLayout(text_card)
        tl.setContentsMargins(18, 14, 18, 12)
        tl.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(heading("Text to type"))
        row.addStretch(1)
        self.count_label = QLabel("0 chars")
        self.count_label.setObjectName("muted")
        row.addWidget(self.count_label)
        tl.addLayout(row)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Paste the text you want to type here.")
        self.text.textChanged.connect(self.on_text_changed)
        tl.addWidget(self.text, 1)
        left.addWidget(text_card, 3)

        # results card
        res = card()
        rl = QVBoxLayout(res)
        rl.setContentsMargins(18, 14, 18, 14)
        rl.setSpacing(10)
        rl.addWidget(heading("Plan"))
        tiles = QHBoxLayout()
        tiles.setSpacing(22)
        self.t_time = Tile("Estimated time")
        self.t_chars = Tile("Characters")
        self.t_mean = Tile("Mean interval")
        self.t_sd = Tile("Std. deviation")
        self.t_pause = Tile("Long pauses")
        self.t_typo = Tile("Typos (fixed / kept)")
        for tile in (self.t_time, self.t_chars, self.t_mean, self.t_sd, self.t_pause, self.t_typo):
            tiles.addWidget(tile)
        tiles.addStretch(1)
        rl.addLayout(tiles)
        charts = QHBoxLayout()
        charts.setSpacing(22)
        self.plan_chart = ChartWidget("PLANNED INTERVALS", "accent")
        self.actual_chart = ChartWidget("ACTUAL INTERVALS", "accent2")
        charts.addWidget(self.plan_chart)
        charts.addWidget(self.actual_chart)
        rl.addLayout(charts, 1)
        self.plan_info = QLabel("No plan yet. Press Build Plan to see the estimated time and distribution.")
        self.plan_info.setObjectName("muted")
        self.plan_info.setWordWrap(True)
        rl.addWidget(self.plan_info)
        left.addWidget(res, 3)

        # settings column
        side = QVBoxLayout()
        side.setSpacing(16)
        side.addWidget(self.build_timing_card())
        side.addWidget(self.build_typo_card())
        side.addWidget(self.build_options_card())
        side.addStretch(1)
        side_w = QWidget()
        side_w.setLayout(side)
        side_w.setFixedWidth(310)
        side.setContentsMargins(0, 0, 0, 0)
        body.addWidget(side_w)

        # progress + buttons
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        outer.addWidget(self.bar)

        foot = QHBoxLayout()
        foot.setSpacing(10)
        self.progress_label = QLabel("F9 stop · F10 pause/resume · mouse to a screen corner = emergency stop")
        self.progress_label.setObjectName("muted")
        foot.addWidget(self.progress_label, 1)
        self.plan_btn = QPushButton("Build Plan")
        self.plan_btn.clicked.connect(self.make_plan)
        self.check_btn = QPushButton("Check Mark")
        self.check_btn.setObjectName("ghost")
        self.check_btn.setToolTip("Checks whether the text above contains this program's mark")
        self.check_btn.clicked.connect(self.check_mark)
        self.pause_btn = QPushButton("Pause  F10")
        self.pause_btn.clicked.connect(self.typer.toggle_pause)
        self.stop_btn = QPushButton("Stop  F9")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.clicked.connect(self.typer.stop)
        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("primary")
        self.start_btn.setDefault(True)
        self.start_btn.clicked.connect(self.start)
        for b in (self.check_btn, self.plan_btn, self.pause_btn, self.stop_btn, self.start_btn):
            b.setCursor(Qt.PointingHandCursor)
            foot.addWidget(b)
        outer.addLayout(foot)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)

        self.hotkeys = None
        self.hotkey_note = ""
        self.start_hotkeys()
        self.refresh_banner()
        self.set_running_ui(False)
        self.set_state("idle")

    # --- settings cards ---

    def _dspin(self, lo, hi, step, dec, val, suffix="", plan=True):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setDecimals(dec)
        s.setValue(val)
        s.setSuffix(suffix)
        s.setAlignment(Qt.AlignRight)
        s.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        s.setKeyboardTracking(False)
        if plan:
            s.valueChanged.connect(self.invalidate_plan)
        return s

    def _grid_card(self, title, rows, switches=()):
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(10)
        lay.addWidget(heading(title))
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(8)
        r = 0
        for name, w in rows:
            g.addWidget(QLabel(name), r, 0)
            g.addWidget(w, r, 1, Qt.AlignRight)
            r += 1
        for name, sw in switches:
            g.addWidget(QLabel(name), r, 0)
            g.addWidget(sw, r, 1, Qt.AlignRight)
            r += 1
        g.setColumnStretch(0, 1)
        lay.addLayout(g)
        return c

    def build_timing_card(self):
        cfg = core.Config()
        self.delay = self._dspin(0, 60, 1, 0, cfg.delay, " s", plan=False)   # not part of the plan
        self.speed = self._dspin(0, 2, 0.01, 3, cfg.speed, " s")
        self.sd = self._dspin(0, 1, 0.01, 3, cfg.sd, " s")
        self.repeat = QSpinBox()
        self.repeat.setRange(1, 1000)
        self.repeat.setValue(cfg.repeat)
        self.repeat.setAlignment(Qt.AlignRight)
        self.repeat.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.repeat.valueChanged.connect(self.invalidate_plan)
        self.jitter = Switch(cfg.jitter)
        self.jitter.toggled.connect(self.invalidate_plan)
        return self._grid_card("Timing", [
            ("Start delay", self.delay), ("Mean interval", self.speed),
            ("Std. deviation", self.sd), ("Repeat", self.repeat)],
            [("Human-like rhythm", self.jitter)])

    def build_typo_card(self):
        cfg = core.Config()
        self.pause_prob = self._dspin(0, 100, 0.5, 1, cfg.pause_prob, " %")
        self.pause_sec = self._dspin(0, 10, 0.1, 1, cfg.pause_sec, " s")
        self.typo_prob = self._dspin(0, 100, 0.5, 1, cfg.typo_prob, " %")
        self.fix_prob = self._dspin(0, 100, 5, 0, cfg.fix_prob, " %")
        return self._grid_card("Pauses & typos", [
            ("Long pause chance", self.pause_prob), ("Long pause length", self.pause_sec),
            ("Typo chance", self.typo_prob), ("Typo fix chance", self.fix_prob)])

    def build_options_card(self):
        cfg = core.Config()
        self.mark = Switch(cfg.mark)
        self.mark.toggled.connect(self.invalidate_plan)
        self.hide_on_start = Switch(True)
        return self._grid_card("Options", [], [
            ("Invisible mark at end", self.mark), ("Minimize on start", self.hide_on_start)])

    def read_cfg(self):
        c = core.Config()
        c.delay = self.delay.value()
        c.speed = self.speed.value()
        c.sd = self.sd.value()
        c.repeat = self.repeat.value()
        c.jitter = self.jitter.isChecked()
        c.pause_prob = self.pause_prob.value()
        c.pause_sec = self.pause_sec.value()
        c.typo_prob = self.typo_prob.value()
        c.fix_prob = self.fix_prob.value()
        c.mark = self.mark.isChecked()
        return c

    # --- plan ---

    def content(self):
        return self.text.toPlainText()

    def on_text_changed(self):
        self.count_label.setText(f"{len(self.content()):,} chars")
        self.invalidate_plan()

    def clear_tiles(self):
        for tile in (self.t_time, self.t_chars, self.t_mean, self.t_sd, self.t_pause, self.t_typo):
            tile.set("—")
        self.t_time.set("—", "Estimated time")

    def invalidate_plan(self, *_):
        if self.running or self.plan is None:
            return
        self.plan = None
        self.plan_chart.set_data([])
        self.clear_tiles()
        self.plan_info.setText("The settings or text changed, so the plan was cleared. "
                               "Press Build Plan or Start to build a new one.")

    def make_plan(self):
        content = self.content()
        if not content.strip():
            self.plan_info.setText("Please enter some text first.")
            return None
        cfg = self.read_cfg()
        self.plan = core.build_plan(content, cfg)
        self.plan_text = content
        self.plan_chart.set_data(self.plan.intervals())
        self.show_plan_info(cfg)
        return self.plan

    def show_plan_info(self, cfg):
        plan = self.plan
        xs = plan.intervals()
        self.t_time.set(core.fmt_time(plan.total), "Estimated time")
        self.t_chars.set(f"{len(plan.steps):,}")
        self.t_mean.set(f"{statistics.fmean(xs):.3f} s" if xs else "—")
        self.t_sd.set(f"{statistics.pstdev(xs):.3f} s" if xs else "—")
        self.t_pause.set(str(plan.long_count))
        self.t_typo.set(f"{plan.typo_count} / {plan.unfixed_count}")
        note = "Plan locked: this exact plan will be typed until you change the text or a setting."
        if plan.watermark:
            note += " An invisible mark will be added at the end."
        self.plan_info.setText(note)

    def check_mark(self):
        if core.find_watermark(self.content()):
            self.plan_info.setText("The mark is present. This text was typed by this program.")
        else:
            self.plan_info.setText("No mark was found.")

    # --- running ---

    def start(self):
        if self.running:
            return
        if self.plan is None or self.plan_text != self.content():
            if self.make_plan() is None:
                return
        cfg = self.read_cfg()
        self.actual_chart.set_data([])
        self.bar.setValue(0)
        self.running = True
        self.set_running_ui(True)
        self.typer.start(self.plan, cfg.delay)
        if self.hide_on_start.isChecked():
            self.showMinimized()

    def finish(self):
        self.running = False
        self.set_running_ui(False)
        self.actual_chart.set_data(self.typer.actual_intervals())
        t = self.typer
        if self.plan:
            self.t_time.set(core.fmt_time(self.plan.total), "Estimated time")
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        if t.state == "done":
            xs = t.actual_intervals()
            extra = ""
            if len(xs) > 1:
                extra = f" · actual mean {statistics.fmean(xs):.3f} s · sd {statistics.pstdev(xs):.3f} s"
            self.progress_label.setText("Finished typing" + extra)
        elif t.message:
            self.progress_label.setText(t.message)
        else:
            self.progress_label.setText("Stopped")

    def set_running_ui(self, running):
        self.start_btn.setEnabled(not running)
        self.plan_btn.setEnabled(not running)
        self.check_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running)
        self.stop_btn.setEnabled(running)
        self.text.setReadOnly(running)

    def set_state(self, state):
        if state == self.shown_state:
            return
        self.shown_state = state
        color = T[STATE_COLOR.get(state, "muted")]
        self.state_pill.setText(f"●  {core.STATE_NAMES.get(state, state)}")
        self.state_pill.setStyleSheet(
            f"background:{rgba(color, 0.16)}; color:{color}; border-radius:13px;"
            f"padding:5px 14px; font-weight:600;")

    def tick(self):
        t = self.typer
        self.set_state(t.state)
        if not self.running:
            return
        plan = t.plan
        if t.state in ("countdown", "typing", "paused") and plan:
            total = max(1, len(plan.steps))
            self.bar.setValue(int(1000 * t.done / total))
            remain = max(0.0, plan.total - plan.consumed(t.done))
            self.t_time.set(core.fmt_time(remain), "Remaining")
            if t.state == "countdown":
                self.progress_label.setText(t.message + " · click the window you want to type into")
            else:
                self.progress_label.setText(f"{t.done:,} / {total:,} chars typed")
            now = core.time.time()
            if now - self.last_chart_update > 1.0 and len(t.stamps) > 10:
                self.actual_chart.set_data(t.actual_intervals())
                self.last_chart_update = now
        if not t.running():
            if t.state == "done":
                self.bar.setValue(1000)
            self.finish()

    # --- hotkeys ---

    def start_hotkeys(self):
        if core.pk is None:
            self.progress_label.setText("Hotkeys unavailable (pynput missing). Use the buttons.")
            return
        try:
            self.hotkeys = core.pk.GlobalHotKeys({
                "<f9>": self.typer.stop, "<f10>": self.typer.toggle_pause})
            self.hotkeys.daemon = True
            self.hotkeys.start()
        except Exception:
            self.progress_label.setText("Could not enable the hotkeys. Please check the macOS 'Input Monitoring' permission.")

    def refresh_banner(self):
        self.banner.setVisible(not accessibility_granted())

    def closeEvent(self, event):
        self.typer.stop()
        try:
            if self.hotkeys:
                self.hotkeys.stop()
        except Exception:
            pass
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    if "--dark" in sys.argv:                 # for checking the dark layout
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor(28, 28, 30))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("white"))
        app.setPalette(pal)
    apply_theme(app)
    icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    win = MainWindow()

    if "--selftest" in sys.argv:            # for checking the layout: save a picture and exit
        out = sys.argv[sys.argv.index("--selftest") + 1]
        win.text.setPlainText("This is a sample sentence for checking the layout. Hello, world! "
                              "The quick brown fox jumps over the lazy dog.\n" * 6)
        win.typo_prob.setValue(3)
        win.make_plan()
        win.actual_chart.set_data(win.plan.intervals())
        win.show()
        app.processEvents()
        win.grab().save(out)
        return 0

    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
