"""auto_typer_console: types the given text into another window as if a person were typing it.

Run:    python3 auto_typer_console.py
On first run it creates a venv next to this file and installs pyautogui, pyperclip and pynput.

Global hotkeys: F9 stops, F10 pauses/resumes
On macOS the terminal needs the 'Accessibility' and 'Input Monitoring' permissions.
"""

# --- Dependency setup (if missing, install into a local venv and re-run with that interpreter) ---
import importlib.util
import os
import subprocess
import sys

REQUIRED = ("pyautogui", "pyperclip", "pynput")
CORE = ("pyautogui", "pyperclip")   # works without pynput (only the hotkeys are disabled)
if os.environ.get("AUTO_TYPER_GUI"):
    # the GUI also needs the UI library
    REQUIRED = REQUIRED + ("PySide6",)
    CORE = CORE + ("PySide6",)
_PIP_NAME = {"PySide6": "PySide6-Essentials"}   # packages whose import name differs from the pip name
_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")


def _venv_python():
    sub, exe = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    return os.path.join(_VENV, sub, exe)


def _has(python, names):
    code = ("import importlib.util as u, sys; "
            "sys.exit(0 if all(u.find_spec(n) for n in %r) else 1)" % (list(names),))
    return subprocess.call([python, "-c", code],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def _pip_install(python):
    print("Installing the required packages. This only happens on the first run.")
    base = [python, "-m", "pip", "install", "--disable-pip-version-check"]
    pkgs = [_PIP_NAME.get(n, n) for n in REQUIRED]
    if subprocess.call(base + pkgs) != 0:
        for pkg in pkgs:
            subprocess.call(base + [pkg])
    if not _has(python, CORE):
        sys.exit("Installation failed. Check your internet connection and run again.")


def _bootstrap():
    if getattr(sys, "frozen", False):   # a packaged app already bundles everything
        return
    if all(importlib.util.find_spec(n) for n in REQUIRED):
        return
    if os.path.realpath(sys.prefix) == os.path.realpath(_VENV):
        _pip_install(sys.executable)
        return
    vpy = _venv_python()
    if not os.path.exists(vpy):
        print("Creating a virtual environment (venv):", _VENV)
        import venv
        venv.create(_VENV, with_pip=True)
    if not _has(vpy, REQUIRED):
        _pip_install(vpy)
    sys.exit(subprocess.call([vpy] + sys.argv))


_bootstrap()

# --- Main ---
import math
import re
import platform
import random
import shutil
import statistics
import threading
import time
import unicodedata

import pyautogui
import pyperclip

try:
    from pynput import keyboard as pk
except Exception:
    pk = None

pyautogui.FAILSAFE = True    # moving the mouse to a screen corner aborts
pyautogui.PAUSE = 0

PASTE_MOD = "command" if platform.system() == "Darwin" else "ctrl"

# Adjacent keys for typos (QWERTY)
NEIGHBORS = {
    "q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh",
    "u": "yij", "i": "uok", "o": "ipl", "p": "ol", "a": "qsz", "s": "awdx",
    "d": "sefc", "f": "drgv", "g": "fthb", "h": "gyjn", "j": "hukm",
    "k": "jil", "l": "kop", "z": "asx", "x": "zsc", "c": "xdv", "v": "cfb",
    "b": "vgn", "n": "bhm", "m": "nj",
}

# Invisible mark appended to the end of the text once typing finishes.
# To enable it by default, change WATERMARK_DEFAULT below to True.
WATERMARK_DEFAULT = False
_SIGNATURE = b"AT1"
_ZERO, _ONE, _FRAME = "\u200b", "\u200c", "\u2060"
_MARK_RE = re.compile(_FRAME + "([" + _ZERO + _ONE + "]{%d})" % (len(_SIGNATURE) * 8) + _FRAME)


def make_watermark():
    bits = "".join(f"{b:08b}" for b in _SIGNATURE)
    return _FRAME + "".join(_ONE if c == "1" else _ZERO for c in bits) + _FRAME


def find_watermark(text):
    """True if the text contains the mark."""
    for m in _MARK_RE.finditer(text):
        bits = "".join("1" if c == _ONE else "0" for c in m.group(1))
        raw = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
        if raw == _SIGNATURE:
            return True
    return False


HELP = """\
Commands
  /prompt           Enter the text (finish with /end on a new line, Ctrl+C to cancel)
  /load <path>      Load the text from a UTF-8 file
  /show             Preview the current text
  /clear            Clear the current text
  /set <key> <val>  Change a setting
  /error <typo%> [fix%]
                    Set the chance of a typo and the chance a typo gets corrected (per English letter)
                    e.g. /error 3 85 (3% typos, 85% of them corrected), /error 0 (no typos)
                    Typos that are not corrected stay in the typed text
  /mark [on|off]    Choose whether to append an invisible mark at the end (no argument shows the state)
  /check            Paste a text to check whether it contains this program's mark
  /plan             Build and lock a typing plan, and show its duration and interval distribution
                    (/start reuses this plan until you run /plan again)
  /start            Start typing (uses the locked plan if there is one, otherwise builds a new one)
  /graph            Show the interval distribution of the last run
  /status           Show the current settings
  /help, /quit      Show this help or exit

Settings
  delay     Wait before starting (seconds)
  speed     Mean interval between characters (seconds)
  sd        Standard deviation of the interval between characters (seconds)
  repeat    Number of repetitions
  jitter    Randomize the intervals (off = always exactly the speed value)
  pause     Chance of a long pause (%)
  pausesec  Length of a long pause (seconds)

While typing, F9 stops and F10 pauses or resumes.
"""


class Config:
    def __init__(self):
        self.delay = 5.0
        self.speed = 0.12
        self.sd = 0.04
        self.repeat = 1
        self.jitter = True
        self.typo_prob = 0.0    # % : chance of a typo per English letter (0 = no typos)
        self.fix_prob = 85.0    # % : chance that a typo gets corrected (the rest stay in the text)
        self.pause_prob = 1.0
        self.pause_sec = 0.7
        self.mark = WATERMARK_DEFAULT



# --- Plan ---

def sample_interval(mean, sd):
    """Draw one value from a positive (log-normal) distribution with the given mean and sd."""
    if sd <= 0:
        return mean
    var = math.log(1 + (sd / mean) ** 2)
    return random.lognormvariate(math.log(mean) - var / 2, math.sqrt(var))


class Step:
    """One character.
    typo=(wrong char, wait after it, wait after backspace): typed wrong, then corrected right away
    orig: for an uncorrected typo, the character that should have been typed (ch is the wrong char actually typed)
    delay: wait after typing
    """
    __slots__ = ("ch", "typo", "delay", "is_long", "cost", "orig")

    def __init__(self, ch, typo, delay, is_long, orig=None):
        self.ch = ch
        self.orig = orig
        self.typo = typo
        self.delay = delay
        self.is_long = is_long
        self.cost = delay + (typo[1] + typo[2] if typo else 0.0)

    def typo_time(self):
        return self.typo[1] + self.typo[2] if self.typo else 0.0


class Plan:
    def __init__(self, steps):
        self.steps = steps
        self.prefix = []          # prefix[i]: time at which step i finishes (seconds from the start)
        acc = 0.0
        for s in steps:
            acc += s.cost
            self.prefix.append(acc)
        self.total = acc
        self.watermark = ""      # mark appended at the end (empty string if none)
        self.long_count = sum(s.is_long for s in steps)
        self.typo_count = sum(1 for s in steps if s.typo)          # corrected typos
        self.unfixed_count = sum(1 for s in steps if s.orig is not None)   # uncorrected typos

    def consumed(self, done):
        if done <= 0:
            return 0.0
        return self.prefix[min(done, len(self.prefix)) - 1]

    def intervals(self):
        """Intervals between character input times. Same definition as the measured values."""
        return [self.steps[i - 1].delay + self.steps[i].typo_time()
                for i in range(1, len(self.steps))]

    def unfixed_marks(self, limit):
        """Uncorrected typos: (character index, intended char, char actually typed)"""
        marks = []
        for i, s in enumerate(self.steps):
            if s.orig is not None:
                marks.append((i + 1, s.orig, s.ch))
                if len(marks) >= limit:
                    break
        return marks

    def long_marks(self, limit):
        marks = []
        for i, s in enumerate(self.steps):
            if s.is_long:
                marks.append((i + 1, self.prefix[i] - s.cost))
                if len(marks) >= limit:
                    break
        return marks


def next_delay(prev_ch, ch, cfg):
    base = cfg.speed
    if base <= 0:
        return 0.0, False
    if not cfg.jitter:
        return base, False
    d = sample_interval(base, cfg.sd)
    if ch == " ":
        d *= random.uniform(1.0, 1.7)
    if prev_ch in ",;":
        d += base * random.uniform(1.5, 3)
    elif prev_ch in ".!?\n":
        d += base * random.uniform(3, 6)
    is_long = random.random() < cfg.pause_prob / 100
    if is_long:
        d += cfg.pause_sec
    return d, is_long


def build_plan(content, cfg):
    steps = []
    for i in range(cfg.repeat):
        prev = ""
        for ch in content:
            typo = None
            wrong = None
            if ch.lower() in NEIGHBORS and random.random() < cfg.typo_prob / 100:
                wrong = random.choice(NEIGHBORS[ch.lower()])
                wrong = wrong.upper() if ch.isupper() else wrong
            if wrong is not None and random.random() < cfg.fix_prob / 100:
                # type it wrong, pause briefly, delete it, then type it correctly
                hold = random.uniform(0.1, 0.4)
                if cfg.speed > 0:
                    hold += sample_interval(cfg.speed, cfg.sd)
                typo = (wrong, hold, random.uniform(0.05, 0.2))
                wrong = None
            if wrong is not None:
                # uncorrected typo: the wrong character stays in the text
                delay, is_long = next_delay(prev, wrong, cfg)
                steps.append(Step(wrong, None, delay, is_long, orig=ch))
                prev = wrong
                continue
            delay, is_long = next_delay(prev, ch, cfg)
            steps.append(Step(ch, typo, delay, is_long))
            prev = ch
        if i < cfg.repeat - 1:
            steps.append(Step("\n", None, 0.0, False))
    plan = Plan(steps)
    if cfg.mark:
        plan.watermark = make_watermark()
    return plan


# --- Running ---

class Typer:
    def __init__(self):
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.state = "idle"
        self.done = 0
        self.plan = None
        self.message = ""
        self.paused_total = 0.0
        self.stamps = []          # (step index, input time)
        self.pause_hits = set()   # step indices at which a pause happened
        self.worker = None

    def type_char(self, ch):
        if ch == "\n":
            pyautogui.press("enter")
        elif ch == "\t":
            pyautogui.press("tab")
        elif ord(ch) < 128:
            pyautogui.write(ch)
        else:
            # non-ASCII characters are pasted through the clipboard
            pyperclip.copy(ch)
            time.sleep(0.02)
            pyautogui.hotkey(PASTE_MOD, "v")

    def paste_text(self, text):
        """Paste several characters at once through the clipboard."""
        pyperclip.copy(text)
        time.sleep(0.02)
        pyautogui.hotkey(PASTE_MOD, "v")

    def wait_if_paused(self):
        """If paused, wait until resumed. Returns True if stopped."""
        if self.pause_event.is_set() and not self.stop_event.is_set():
            began = time.time()
            self.state = "paused"
            self.pause_hits.add(self.done)
            while self.pause_event.is_set() and not self.stop_event.is_set():
                time.sleep(0.05)
            self.paused_total += time.time() - began
            if not self.stop_event.is_set():
                self.state = "typing"
        return self.stop_event.is_set()

    def run(self, plan, start_delay):
        try:
            self.state = "countdown"
            end = time.time() + start_delay
            while time.time() < end:
                if self.stop_event.is_set():
                    self.state = "stopped"
                    return
                self.message = f"Starting in {end - time.time():.0f} s"
                time.sleep(0.1)

            self.message = ""
            self.state = "typing"
            t0 = time.time()
            self.paused_total = 0.0
            for idx, step in enumerate(plan.steps):
                if self.wait_if_paused():
                    self.state = "stopped"
                    return
                if step.typo:
                    wrong, hold, back = step.typo
                    pyautogui.write(wrong)
                    self.stop_event.wait(hold)
                    pyautogui.press("backspace")
                    self.stop_event.wait(back)
                self.type_char(step.ch)
                self.stamps.append((idx, time.perf_counter()))
                self.done = idx + 1

                # Keep to the plan's schedule. Shift the baseline back by the time spent paused.
                target = t0 + self.paused_total + plan.prefix[idx]
                lag = time.time() - target
                if lag > 0.5:
                    t0 += lag
                elif target > time.time() and self.stop_event.wait(target - time.time()):
                    self.state = "stopped"
                    return
            if plan.watermark and not self.stop_event.is_set():
                self.paste_text(plan.watermark)
            self.state = "done"
        except pyautogui.FailSafeException:
            self.state = "stopped"
            self.message = "Stopped because the mouse moved to a screen corner"
        except Exception as e:
            self.state = "error"
            self.message = f"An error occurred: {e}"

    def start(self, plan, start_delay):
        self.stop_event.clear()
        self.pause_event.clear()
        self.done = 0
        self.plan = plan
        self.message = ""
        self.stamps = []
        self.pause_hits = set()
        self.state = "countdown"
        self.worker = threading.Thread(target=self.run, args=(plan, start_delay), daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
        else:
            self.pause_event.set()

    def running(self):
        return self.worker is not None and self.worker.is_alive()

    def actual_intervals(self):
        """Actual intervals between consecutive characters. Intervals spanning a pause are excluded."""
        out = []
        for (i0, t0), (i1, t1) in zip(self.stamps, self.stamps[1:]):
            if i1 == i0 + 1 and i1 not in self.pause_hits:
                out.append(t1 - t0)
        return out


# --- Output ---

STATE_NAMES = {
    "idle": "Idle", "countdown": "Getting ready", "typing": "Typing",
    "paused": "Paused", "stopped": "Stopped", "done": "Done", "error": "Error",
}


def fmt_time(sec):
    sec = int(round(max(0, sec)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fit(s, width):
    """Trim to the terminal display width (full-width characters take 2 columns) and pad with spaces."""
    out, w = "", 0
    for c in s:
        cw = 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
        if w + cw > width:
            break
        out += c
        w += cw
    return out + " " * (width - w)


def render_progress(t):
    cols = shutil.get_terminal_size((100, 20)).columns
    if t.state == "countdown":
        return fit(t.message, cols - 1)
    plan = t.plan
    n = max(len(plan.steps), 1)
    frac = min(t.done / n, 1.0)
    bar_w = max(10, min(30, cols - 70))
    filled = int(bar_w * frac)
    used = plan.consumed(t.done)
    line = (f"[{'#' * filled}{'-' * (bar_w - filled)}] {frac * 100:5.1f}%  {t.done}/{n}"
            f"  {STATE_NAMES.get(t.state, t.state)}"
            f"  elapsed {fmt_time(used)} / {fmt_time(plan.total)}  remaining {fmt_time(plan.total - used)}")
    return fit(line, cols - 1)


def print_distribution(title, xs):
    """Print the mean, standard deviation and histogram of a list of intervals."""
    if len(xs) < 2:
        print(f"{title}: not enough data")
        return
    mean = statistics.fmean(xs)
    sd = statistics.pstdev(xs)
    within = sum(1 for x in xs if abs(x - mean) <= sd) / len(xs) * 100
    print(f"{title}  n={len(xs)}  mean {mean:.3f}s  sd {sd:.3f}s  "
          f"median {statistics.median(xs):.3f}s  within ±1σ {within:.0f}%")
    if sd < 1e-9:
        print(f"  All intervals are {mean:.3f}s (standard deviation 0)")
        return
    if len(xs) < 10:
        print("  (fewer than 10 intervals, so no graph is shown)")
        return

    srt = sorted(xs)
    hi = srt[min(len(srt) - 1, int(len(srt) * 0.95))]         # the top 5% is trimmed from the chart (count shown below)
    lo = max(0.0, math.floor(srt[0] * 200) / 200)             # round the minimum down to a multiple of 0.005
    if hi - lo < 1e-6:
        hi = lo + 1e-6
    size = shutil.get_terminal_size((80, 24))
    cols = size.columns
    bins = max(16, min(30, (cols - 12) // 2))                 # each bar is 1 column wide plus a 1-column gap
    height = 10                                               # number of rows (even)
    step = (hi - lo) / bins
    counts = [0] * bins
    over = 0
    for x in xs:
        if x > hi:
            over += 1
        else:
            counts[min(int((x - lo) / step), bins - 1)] += 1
    peak = max(counts) or 1

    color = sys.stdout.isatty()
    inside, outside, reset = ("\033[36m", "\033[90m", "\033[0m") if color else ("", "", "")
    levels = " ▁▂▃▄▅▆▇█"

    def bin_of(v):
        return min(bins - 1, max(0, int((v - lo) / step)))

    lo_b, hi_b, mean_b = bin_of(mean - sd), bin_of(mean + sd), bin_of(mean)

    print("  vertical: count / horizontal: interval between characters (s)")
    for r in range(height - 1, -1, -1):
        if r == height - 1:
            label = f"{peak:>5} ┤"
        elif r == height // 2 - 1:
            label = f"{round(peak / 2):>5} ┤"
        else:
            label = "      │"
        cells = []
        for b, c in enumerate(counts):
            lvl = round(c / peak * height * 8)
            if c and lvl == 0:
                lvl = 1                                       # show it if there is at least one
            lvl = max(0, min(8, lvl - r * 8))
            tint = inside if lo_b <= b <= hi_b else outside
            cells.append((f"{tint}{levels[lvl]}{reset}" if lvl else " ") + " ")
        print(label + "".join(cells))

    width = bins * 2
    print("    0 └" + "─" * width)

    ticks = [" "] * width
    for i in range(5):
        text = f"{lo + (hi - lo) * i / 4:.3f}"
        pos = i * (width - len(text)) // 4
        ticks[pos:pos + len(text)] = text
    print("       " + "".join(ticks))

    marker = [" "] * width
    x_lo, x_hi = lo_b * 2, hi_b * 2
    for x in range(x_lo, x_hi + 1):
        marker[x] = "─"
    marker[x_lo], marker[x_hi] = "└", "┘"
    marker[min(width - 1, mean_b * 2)] = "▲"
    print("       " + inside + "".join(marker) + reset)
    print(f"       ▲ mean {mean:.3f}s    └─┘ mean±1σ ({max(0.0, mean - sd):.3f} ~ {mean + sd:.3f}s)"
          + ("    (teal bars are within ±1σ)" if color else ""))
    if over:
        print(f"       above {hi:.3f}s: {over} (max {srt[-1]:.3f}s)")


def print_plan(plan, cfg, chart=True):
    n = len(plan.steps)
    print(f"{n} characters, estimated time {fmt_time(plan.total)} (excluding the {cfg.delay:g} s start delay)")
    typos = plan.typo_count + plan.unfixed_count
    line = (f"{plan.long_count} long pause{'' if plan.long_count == 1 else 's'} "
            f"and {typos} typo{'' if typos == 1 else 's'}")
    if typos:
        line += f" (corrected {plan.typo_count}, left as is {plan.unfixed_count})"
    print(line)
    marks = plan.unfixed_marks(5)
    if marks:
        pos = ", ".join(f"#{i} ({o} -> {w})" for i, o, w in marks)
        print(f"Uncorrected typos at: {pos}{' ...' if plan.unfixed_count > len(marks) else ''}")
        print("Uncorrected typos stay in the typed text as mistakes.")
    marks = plan.long_marks(5)
    if marks:
        pos = ", ".join(f"#{i} ({fmt_time(sec)})" for i, sec in marks)
        print(f"Long pauses at: {pos}{' ...' if plan.long_count > len(marks) else ''}")
    if plan.watermark:
        print("An invisible mark will be appended at the end when typing finishes. (turn it off with /mark off)")
    if not chart:
        return
    print_distribution("Interval distribution (plan)", plan.intervals())
    if cfg.jitter:
        print(f"The configured values are mean {cfg.speed:g}s and sd {cfg.sd:g}s; pauses after spaces and punctuation "
              f"are added on top, so the distribution above is wider than that.")


def print_result(t):
    actual = t.actual_intervals()
    if len(actual) < 2:
        return
    print()
    print_distribution("Interval distribution (actual)", actual)
    planned = t.plan.intervals()[: len(actual)]
    if len(planned) > 1:
        print(f"Plan vs actual: mean {statistics.fmean(planned):.3f}s -> {statistics.fmean(actual):.3f}s, "
              f"sd {statistics.pstdev(planned):.3f}s -> {statistics.pstdev(actual):.3f}s")


def monitor(t):
    print("F9 stops, F10 pauses/resumes (Ctrl+C also stops)")
    try:
        while t.running():
            sys.stdout.write("\r" + render_progress(t))
            sys.stdout.flush()
            time.sleep(0.2)
    except KeyboardInterrupt:
        t.stop()
        t.worker.join(timeout=2)
    if t.plan and t.state != "countdown":
        sys.stdout.write("\r" + render_progress(t) + "\n")
    else:
        sys.stdout.write("\n")
    if t.message:
        print(t.message)
    print(f"Typed {t.done}/{len(t.plan.steps)} characters. (state: {STATE_NAMES.get(t.state, t.state)})")
    print_result(t)


def show_status(cfg, t, text, plan):
    onoff = lambda b: "on" if b else "off"
    print(f"text      {len(text)} chars")
    print(f"state     {STATE_NAMES.get(t.state, t.state)}")
    print(f"delay     {cfg.delay:g}s")
    print(f"speed     {cfg.speed:g}s")
    print(f"sd        {cfg.sd:g}s")
    print(f"repeat    {cfg.repeat}")
    print(f"jitter    {onoff(cfg.jitter)}")
    print("error     " + (f"typos {cfg.typo_prob:g}%, fix {cfg.fix_prob:g}%"
                          if cfg.typo_prob > 0 else "off"))
    print(f"mark      {'on' if cfg.mark else 'off'}")
    print(f"pause     {cfg.pause_prob:g}%, {cfg.pause_sec:g}s")
    print("plan      " + (f"{fmt_time(plan.total)} (long pauses {plan.long_count}, typos {plan.typo_count + plan.unfixed_count}) - locked"
                          if plan else "none (/start builds one and uses it once)"))


# --- Input handling ---

def start_hotkeys(t):
    if pk is None:
        print("pynput is not installed, so the F9/F10 hotkeys are unavailable. Use Ctrl+C to stop.")
        return
    try:
        listener = pk.GlobalHotKeys({"<f9>": t.stop, "<f10>": t.toggle_pause})
        listener.daemon = True
        listener.start()
    except Exception as e:
        print(f"Could not enable the hotkeys: {e}")


def parse_bool(v):
    return v.strip().lower() in ("on", "true", "1", "yes", "y")


def do_set(cfg, args):
    if len(args) != 2:
        return "Usage: /set <key> <value>"
    key, val = args[0].lower(), args[1]
    try:
        if key == "delay":
            cfg.delay = max(0.0, float(val))
        elif key == "speed":
            cfg.speed = max(0.0, float(val))
        elif key == "sd":
            cfg.sd = max(0.0, float(val))
        elif key == "repeat":
            cfg.repeat = max(1, int(val))
        elif key == "jitter":
            cfg.jitter = parse_bool(val)
        elif key in ("typos", "typoprob", "fixprob"):
            return "Use /error <typo chance %> [fix chance %] to set typos"
        elif key == "pause":
            cfg.pause_prob = min(100.0, max(0.0, float(val)))
        elif key == "pausesec":
            cfg.pause_sec = max(0.0, float(val))
        else:
            return f"'{key}' is not a valid setting"
    except ValueError:
        return f"'{val}' is not a valid value"
    return f"Set {key} = {val}"


def read_paste():
    """Read until /end. Returns None if cancelled with Ctrl+C."""
    print("Paste or type the text, then enter /end on a new line to finish. (Ctrl+C to cancel)")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        except KeyboardInterrupt:
            print("\nCancelled.")
            return None
        stripped = line.rstrip()
        if stripped.strip() == "/end":
            break
        if stripped.endswith((" /end", "\t/end")):
            lines.append(stripped[:-4].rstrip())    # a trailing /end on a line counts as the terminator
            break
        lines.append(line)
    return "\n".join(lines)


def main():
    cfg = Config()
    t = Typer()
    text = ""
    plan = None          # plan built and locked with /plan
    plan_text = None     # the text at the time that plan was built
    start_hotkeys(t)
    print("Auto Typer. Type /help to see the commands.")

    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        raw = raw.lstrip("﻿​‎‏")     # invisible characters that get mixed in when pasting
        if raw.startswith("／"):
            raw = "/" + raw[1:]
        if not raw:
            continue
        if not raw.startswith("/"):
            print("Commands start with /. Try /help.")
            continue

        parts = raw.split()
        cmd, args = parts[0].lower(), parts[1:]

        if cmd in ("/quit", "/exit", "/q"):
            break
        elif cmd == "/help":
            print(HELP)
        elif cmd == "/prompt":
            pasted = read_paste()
            if pasted is not None:
                text = pasted
                print(f"Received {len(text)} characters.")
        elif cmd == "/load":
            path = raw[len("/load"):].strip().strip("\"'")
            try:
                with open(os.path.expanduser(path), encoding="utf-8") as f:
                    text = f.read()
                print(f"Loaded {len(text)} characters.")
            except OSError as e:
                print(f"Could not read the file: {e}")
        elif cmd == "/show":
            if not text:
                print("No text has been entered.")
            else:
                print(text if len(text) <= 300 else text[:300] + " ...")
                print(f"({len(text)} characters total)")
        elif cmd == "/clear":
            text = ""
            print("Text cleared.")
        elif cmd == "/set":
            msg = do_set(cfg, args)
            print(msg)
            if plan is not None and msg.startswith("Set ") and args[0].lower() != "delay":
                print("This does not affect the plan already built. Run /plan again to build one with the new settings.")
        elif cmd == "/mark":
            if not args:
                print("mark: " + ("on" if cfg.mark else "off") + " (usage: /mark on or /mark off)")
            elif args[0].lower() in ("on", "off"):
                cfg.mark = args[0].lower() == "on"
                print("An invisible mark will be appended at the end when typing finishes." if cfg.mark else "Mark turned off.")
                if plan is not None:
                    print("This does not affect the plan already built. Run /plan again to build one with the new settings.")
            else:
                print("Usage: /mark on or /mark off")
        elif cmd == "/check":
            sample = read_paste()
            if sample is not None:
                print("This program's mark is present." if find_watermark(sample)
                      else "This program's mark was not found.")
        elif cmd == "/error":
            if not args:
                if cfg.typo_prob > 0:
                    print(f"Typo chance {cfg.typo_prob:g}%, fix chance {cfg.fix_prob:g}%")
                else:
                    print("Typos are off. Usage: /error <typo chance %> [fix chance %]")
            else:
                try:
                    if len(args) > 2:
                        raise ValueError
                    typo_p = float(args[0])
                    fix_p = float(args[1]) if len(args) > 1 else cfg.fix_prob
                except ValueError:
                    print("Usage: /error <typo chance %> [fix chance %]  (0 = no typos)")
                else:
                    cfg.typo_prob = min(100.0, max(0.0, typo_p))
                    cfg.fix_prob = min(100.0, max(0.0, fix_p))
                    if cfg.typo_prob == 0:
                        print("Typos turned off.")
                    else:
                        print(f"Set typo chance {cfg.typo_prob:g}%, fix chance {cfg.fix_prob:g}%.")
                    if plan is not None:
                        print("This does not affect the plan already built. Run /plan again to build one with the new settings.")
        elif cmd == "/status":
            show_status(cfg, t, text, plan)
        elif cmd == "/graph":
            if len(t.actual_intervals()) < 2:
                print("Nothing has been run yet.")
            else:
                print_result(t)
        elif cmd == "/plan":
            if not text.strip():
                print("No text has been entered. Use /prompt first.")
                continue
            plan = build_plan(text, cfg)
            plan_text = text
            print_plan(plan, cfg)
            print("This plan is reused on every /start until you run /plan again.")
        elif cmd == "/start":
            if not text.strip():
                print("No text has been entered. Use /prompt first.")
                continue
            run_plan = plan if plan is not None else build_plan(text, cfg)
            print_plan(run_plan, cfg, chart=False)
            if plan is not None:
                print("Typing with the plan built by /plan.")
            print(f"\nStarting in {cfg.delay:g} s. Click the window you want to type into.")
            t.start(run_plan, cfg.delay)
            monitor(t)
        else:
            print(f"Unknown command: {cmd}")

        # if the text changes, the locked plan no longer fits, so clear it
        if plan is not None and plan_text != text:
            plan = plan_text = None
            print("The text changed, so the earlier plan was cleared. Run /plan again if needed.")


if __name__ == "__main__":
    main()
