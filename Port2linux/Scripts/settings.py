#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import math
import shutil
import subprocess
import curses
import textwrap
from pathlib import Path
from dataclasses import dataclass

# -----------------------------
# Paths / Allowlist
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent        # π.χ. Port2linux/
REPO_ROOT = BASE_DIR.parent.parent               # ανέβα 2 επίπεδα
ALLOW = REPO_ROOT / "PORT_ALLOW.txt"

# Hard safety: never run excluded dirs even if allowlist is wrong
BAD_MARKERS = [
    "Scripts/Fake Pages",
    "Scripts/Personal Information Capture",
]

# -----------------------------
# Model
# -----------------------------
@dataclass(frozen=True)
class ScriptItem:
    path: Path
    label: str   # what we show in the menu

def blocked_by_policy(p: Path) -> bool:
    s = str(p)
    return any(m in s for m in BAD_MARKERS)

def load_allowlist() -> list[ScriptItem]:
    if not ALLOW.exists():
        raise SystemExit(f"PORT_ALLOW.txt not found at {ALLOW}")

    items: list[ScriptItem] = []
    for line in ALLOW.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = Path(line)
        print(p)
        if not (p.exists() and p.is_file() and p.suffix == ".py"):
            continue

        if blocked_by_policy(p):
            # silently skip (or print if you prefer)
            continue

        # Friendly label: show allowlist relative path if possible
        try:
            rel = p.relative_to(REPO_ROOT)
            label = str(rel)
        except ValueError:
            label = str(p)

        items.append(ScriptItem(path=p, label=label))

    # stable ordering
    items.sort(key=lambda x: x.label.lower())
    return items

def run_script(target: Path) -> int:
    env = os.environ.copy()
    # keep the extra safety gate
    if blocked_by_policy(target):
        print("Blocked by safe policy (excluded directory).")
        return 1
    proc = subprocess.run(["python3", str(target)], env=env, check=False)
    return proc.returncode

# -----------------------------
# Renderer: Number menu
# -----------------------------
def number_menu(items: list[ScriptItem]) -> ScriptItem | None:
    print("Linux Safe Edition (allowlist-only)\n")
    for i, it in enumerate(items, 1):
        print(f"{i:2d}) {it.label}")

    choice = input("\nSelect number (or q): ").strip().lower()
    if choice in ("q", "quit", "exit"):
        return None

    try:
        idx = int(choice) - 1
        return items[idx]
    except Exception:
        print("Invalid choice.")
        return None

# -----------------------------
# Renderer: List menu (fzf if available)
# -----------------------------
def list_menu(items: list[ScriptItem]) -> ScriptItem | None:
    if not shutil.which("fzf"):
        # fallback to number menu if no fzf
        return number_menu(items)

    menu_text = "\n".join(it.label for it in items)
    r = subprocess.run(
        ["fzf", "--prompt", "Select> "],
        input=menu_text,
        text=True,
        capture_output=True
    )
    selected = r.stdout.strip()
    if not selected:
        return None

    # map back to item
    by_label = {it.label: it for it in items}
    return by_label.get(selected)

# -----------------------------
# Renderer: Grid menu (curses)
# -----------------------------
def grid_menu(items: list[ScriptItem]) -> ScriptItem | None:
    labels = [it.label for it in items]

    def draw_box(stdscr, y, x, h, w, highlight: bool):
        # simplistic DedSec-like box
        attr = curses.A_REVERSE if highlight else curses.A_NORMAL
        term_h, term_w = stdscr.getmaxyx()
        if y + h > term_h or x + w > term_w:
            return

        # border
        for i in range(x, x + w):
            stdscr.addch(y, i, curses.ACS_HLINE)
            stdscr.addch(y + h - 1, i, curses.ACS_HLINE)
        for j in range(y, y + h):
            stdscr.addch(j, x, curses.ACS_VLINE)
            stdscr.addch(j, x + w - 1, curses.ACS_VLINE)

        stdscr.addch(y, x, curses.ACS_ULCORNER)
        stdscr.addch(y, x + w - 1, curses.ACS_URCORNER)
        stdscr.addch(y + h - 1, x, curses.ACS_LLCORNER)
        stdscr.addch(y + h - 1, x + w - 1, curses.ACS_LRCORNER)

        # fill area when highlighted (cleaner highlight)
        if highlight:
            for yy in range(y + 1, y + h - 1):
                for xx in range(x + 1, x + w - 1):
                    stdscr.addch(yy, xx, " ", attr)

    def ui(stdscr):
        curses.curs_set(0)
        stdscr.keypad(True)

        current = 0
        n = len(labels)

        while True:
            stdscr.clear()
            term_h, term_w = stdscr.getmaxyx()

            # DedSec-like sizing
            box_w = max(24, term_w // 3)
            box_h = max(5, term_h // 5)
            cols = max(1, term_w // box_w)
            rows = max(1, (term_h - 2) // box_h)
            per_page = cols * rows

            if per_page <= 0:
                stdscr.addstr(0, 0, "Terminal window is too small.")
                stdscr.refresh()
                key = stdscr.getch()
                if key in (ord("q"), ord("Q"), 10, 13):
                    return None
                continue

            page_start = (current // per_page) * per_page
            page_end = min(page_start + per_page, n)

            # title
            title = "Linux Safe Edition (grid) — arrows, Enter, q"
            stdscr.addstr(0, max(0, (term_w - len(title)) // 2), title[:term_w - 1])

            # draw page
            for idx_on_page, idx in enumerate(range(page_start, page_end)):
                r = idx_on_page // cols
                c = idx_on_page % cols
                y = 1 + r * box_h
                x = c * box_w

                highlight = (idx == current)
                draw_box(stdscr, y, x, box_h, box_w, highlight)

                # text centered
                inner_w = box_w - 4
                lines = textwrap.wrap(labels[idx], inner_w)
                lines = lines[: max(1, box_h - 2)]
                pad_y = (box_h - len(lines)) // 2
                for li, line in enumerate(lines):
                    yy = y + pad_y + li
                    xx = x + 2
                    try:
                        stdscr.addstr(yy, xx, line[:inner_w], curses.A_REVERSE if highlight else curses.A_NORMAL)
                    except curses.error:
                        pass

            # footer
            page_no = (current // per_page) + 1
            total_pages = max(1, math.ceil(n / per_page))
            footer = f"Page {page_no}/{total_pages} | Enter: run | q: quit"
            stdscr.addstr(term_h - 1, 0, footer[:term_w - 1])

            stdscr.refresh()
            key = stdscr.getch()

            if key in (ord("q"), ord("Q")):
                return None
            if key in (10, 13):
                return current

            # navigation
            if key == curses.KEY_LEFT and (current % cols) > 0:
                current -= 1
            elif key == curses.KEY_RIGHT and (current % cols) < (cols - 1) and current + 1 < n:
                current += 1
            elif key == curses.KEY_UP and current - cols >= 0:
                current -= cols
            elif key == curses.KEY_DOWN and current + cols < n:
                current += cols

            # page shortcuts
            elif key in (ord("n"), ord("N")):
                current = min(n - 1, page_start + per_page)
            elif key in (ord("p"), ord("P")):
                current = max(0, page_start - per_page)

    idx = curses.wrapper(ui)
    if idx is None:
        return None
    return items[idx]

# -----------------------------
# CLI
# -----------------------------
def parse_style(argv: list[str]) -> str:
    # default: number
    style = "number"
    if "--style" in argv:
        i = argv.index("--style")
        if i + 1 < len(argv):
            style = argv[i + 1].strip().lower()
    return style

def main() -> None:
    items = load_allowlist()
    if not items:
        print("No allowed scripts found.")
        return

    style = parse_style(sys.argv[1:])

    if style == "list":
        selected = list_menu(items)
    elif style == "grid":
        selected = grid_menu(items)
    else:
        selected = number_menu(items)

    if not selected:
        return

    # run
    rc = run_script(selected.path)
    if rc not in (0, None):
        # keep it quiet; you can print rc if you want
        pass

if __name__ == "__main__":
    main()