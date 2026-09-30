# Auto Typer (educational purpose only)

Types text into another window as if a person were typing it: randomized speed, optional typos,
a precomputed plan with an exact time estimate, and an optional invisible mark.
Comes as a macOS app with a window (`.app` / `.dmg`) and as a terminal program.

## Build the macOS app (.dmg)

1. Double-click `BuildMacApp.command`. The first run takes about 5-10 minutes.
   If macOS warns about an unidentified developer, right-click the file and choose Open.
   If it does not run, execute `chmod +x BuildMacApp.command` once in a terminal.
2. When it finishes, `AutoTyper.dmg` is created. Open it and drag AutoTyper into Applications.
3. On first launch, grant permissions in System Settings > Privacy & Security to **AutoTyper**:
   - **Accessibility** (needed for typing)
   - **Input Monitoring** (needed for the F9/F10 hotkeys)

   Then restart the app.

Notes:
- The app you build yourself normally opens without a warning. On another Mac you may need right-click > Open.
- Rebuilding the app can make macOS treat it as a different app, so you may have to grant the permissions again.
- To try the window without building the app, double-click `AutoTyperGUI.command`.
  In that case grant the permissions to **Terminal** instead.

## Using the app window

Paste your text, set the speed and other options on the right, then press **Build Plan** to see the
estimated time and interval distribution. Press **Start**; the app minimizes, and you have the start delay
to click the window you want to type into. Once a plan is built, that exact plan is typed until you change
the text or a setting. When typing ends, the actual interval distribution is shown next to the plan.

F9 stops, F10 pauses/resumes, and moving the mouse to a screen corner stops immediately.

## Terminal version

Double-click `AutoTyper.command`, or run:

```
python3 auto_typer_console.py
```

On first run it creates a `venv` folder next to the script and installs the required packages
(pyautogui, pyperclip, pynput). Later runs start immediately.

| Command | What it does |
| --- | --- |
| `/prompt` | Enter the text; finish with `/end` on a new line |
| `/load <path>` | Load the text from a UTF-8 file |
| `/plan` | Build and lock a plan; shows the estimated time and interval distribution |
| `/start` | Start typing (uses the locked plan if there is one) |
| `/set <key> <value>` | Change a setting (see below) |
| `/error <typo%> [fix%]` | Typo chance and the chance a typo is corrected (per English letter) |
| `/mark on\|off` | Append an invisible mark at the end of the typed text |
| `/check` | Paste a text to check whether it contains the mark |
| `/graph`, `/status`, `/show`, `/clear`, `/help`, `/quit` | Utilities |

Settings for `/set`: `delay`, `speed` (mean interval, s), `sd` (standard deviation, s), `repeat`,
`jitter` (on/off), `pause` (long pause chance, %), `pausesec` (long pause length, s).

Example: `/error 3 85` gives a 3% typo chance, and 85% of typos are deleted and retyped. Uncorrected typos
stay in the typed text, and `/plan` shows where they will be.

## The invisible mark

With the mark on, 26 zero-width characters are appended once at the very end of the typed text (never in
the middle, and not when typing is stopped). Tools that strip zero-width characters or formatting remove it.
Do not enable it for inputs that need exact characters, such as code, URLs or passwords.
To turn it on by default, set `WATERMARK_DEFAULT = True` in `auto_typer_console.py`.

## Notes

- Non-ASCII characters (for example Korean) are typed by pasting through the clipboard.
- On macOS the terminal version needs the Accessibility and Input Monitoring permissions for **Terminal**.
