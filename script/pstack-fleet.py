#!/usr/bin/env python3
"""pstack fleet board for opencode.

Live visualization of running pstack agents (swarm workers, arena
candidates, interrogate reviewers, poteto-agent delegates). This is the
opencode answer to the parallel-agent animation: run it in a second
terminal pane while /swarm, /arena, /interrogate, or /poteto-mode fans
out in the main pane.

Data comes straight from opencode's sqlite store (read-only), so there
is nothing to install and nothing for agents to maintain:

    python3 script/pstack-fleet.py --watch        # animated board
    python3 script/pstack-fleet.py --once --plain # snapshot for chat

A focused view follows one parent and its child sessions (subagents):

    python3 script/pstack-fleet.py --watch --session ses_abc123

An optional fleet manifest overlays swarm/arena labels (worker-1,
candidate-A, ...) that session titles do not carry. The parent agent
writes it with plain bash; the board merges both sources:

    {"fleet": "swarm-auth", "workers": [
      {"name": "worker-1", "slice": "login flow", "status": "running"},
      {"name": "worker-2", "slice": "refresh flow", "status": "done",
       "note": "PASS, 2 issues"}]}

    python3 script/pstack-fleet.py --watch --fleet /tmp/swarm-auth.json

Each session plays a character from fleet/cast.json (override with
--cast PATH, disable with --no-cast). A manifest worker pins one with
"character": "<Name>"; unpinned sessions assign round-robin. A pinned
name missing from the cast gets a stable auto-generated appearance drawn
from the symbols and colors the current cast leaves free.

Status honesty: opencode exposes no explicit running flag. A session is
shown as live when its store row changed recently (default 60s) or its
latest tool part is pending/running. Anything else is idle, not done.
The legend on the board says so.
"""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time

SPIN = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
LIVE_WINDOW_MS = 60_000

C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "white": "\033[37m",
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_magenta": "\033[95m",
    "bright_cyan": "\033[96m",
    "bright_white": "\033[97m",
}


def use_color(plain):
    if plain or os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    return True


def paint(color, text, on):
    if not on or color not in C:
        return text
    return C[color] + text + C["reset"]


def fmt_elapsed(ms):
    s = max(0, int(ms // 1000))
    if s < 60:
        return "%ds" % s
    m, s = divmod(s, 60)
    if m < 60:
        return "%dm%02ds" % (m, s)
    h, m = divmod(m, 60)
    return "%dh%02dm" % (h, m)


def fmt_ago(ms, now):
    return fmt_elapsed(now - ms) + " ago"


def trunc(text, n):
    text = " ".join(str(text).split())
    if len(text) <= n:
        return text
    return text[: max(0, n - 1)] + "…"


def default_db():
    home = os.path.expanduser("~")
    return os.path.join(home, ".local", "share", "opencode", "opencode.db")


def connect_ro(path):
    if not os.path.isfile(path):
        raise SystemExit("opencode db not found: %s" % path)
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)


def load_sessions(con, directory, session_focus, limit, project_all):
    cur = con.cursor()
    if session_focus:
        cur.execute(
            "SELECT id, parent_id, title, agent, model, directory,"
            " time_created, time_updated FROM session"
            " WHERE id = ? OR parent_id = ?"
            " ORDER BY time_created",
            (session_focus, session_focus),
        )
        return cur.fetchall()
    if project_all:
        cur.execute(
            "SELECT id, parent_id, title, agent, model, directory,"
            " time_created, time_updated FROM session"
            " ORDER BY time_updated DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()
    cur.execute(
        "SELECT id, parent_id, title, agent, model, directory,"
        " time_created, time_updated FROM session"
        " WHERE directory = ? ORDER BY time_updated DESC LIMIT ?",
        (directory, limit),
    )
    rows = cur.fetchall()
    if not rows:
        cur.execute(
            "SELECT id, parent_id, title, agent, model, directory,"
            " time_created, time_updated FROM session"
            " ORDER BY time_updated DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
    return rows


def load_todos(con, session_ids):
    if not session_ids:
        return {}
    out = {}
    cur = con.cursor()
    q = "SELECT session_id, content, status FROM todo WHERE session_id IN (%s)" % ",".join(
        "?" for _ in session_ids
    )
    for sid, content, status in cur.execute(q, session_ids):
        out.setdefault(sid, []).append((content, status))
    return out


def load_last_tools(con, session_ids):
    """Latest tool part per session: {sid: (tool, status, time_updated)}."""
    if not session_ids:
        return {}
    out = {}
    cur = con.cursor()
    q = (
        "SELECT session_id, data, time_updated FROM part"
        " WHERE session_id IN (%s) ORDER BY time_updated DESC" % ",".join("?" for _ in session_ids)
    )
    for sid, data, t in cur.execute(q, session_ids):
        if sid in out:
            continue
        try:
            p = json.loads(data)
        except (ValueError, TypeError):
            continue
        if p.get("type") == "tool" and p.get("tool"):
            out[sid] = (p.get("tool"), (p.get("state") or {}).get("status", "?"), t)
        if len(out) == len(session_ids):
            break
    return out


def load_manifest(path):
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        return {"error": "cannot read fleet file %s: %s" % (path, e)}
    workers = doc.get("workers", []) if isinstance(doc, dict) else []
    return {"fleet": doc.get("fleet", path) if isinstance(doc, dict) else path, "workers": workers}


def default_cast():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "fleet", "cast.json"))


def load_cast(path):
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return []
    cast = doc.get("cast", []) if isinstance(doc, dict) else []
    if not isinstance(cast, list):
        return []
    return [e for e in cast if isinstance(e, dict) and e.get("name") and e.get("symbol")]


def cast_lookup(cast):
    return {str(e.get("name", "")).lower(): e for e in cast}


def cast_text(entry):
    return "%s %s" % (entry.get("symbol"), entry.get("name"))


def resolve_pin(lookup, name):
    if not name:
        return None
    return lookup.get(str(name).lower())


# Fallback pools for characters the cast does not define. None of these
# symbols collide with the default Mahabharata cast, so generated entries
# stay visually distinct from authored ones.
AUTO_SYMBOLS = ("✦", "✧", "◐", "◑", "◎", "◍", "▼", "⬣", "◭", "✜", "⬔", "◒")
AUTO_COLORS = (
    "red", "green", "yellow", "blue", "magenta", "cyan", "white",
    "bright_red", "bright_green", "bright_yellow", "bright_blue",
    "bright_magenta", "bright_cyan", "bright_white",
)


def auto_character(cast, cache, name):
    """Generate a stable appearance for a name missing from the cast.

    Seeded by the name so the board never flickers between frames.
    Draws from symbols and colors the current cast leaves free.
    """
    key = str(name).strip().lower()
    if key in cache:
        return cache[key]
    used_symbols = {str(e.get("symbol")) for e in cast}
    used_symbols.update(e["symbol"] for e in cache.values())
    used_colors = {str(e.get("color")) for e in cast}
    used_colors.update(e["color"] for e in cache.values())
    digest = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    symbols = [s for s in AUTO_SYMBOLS if s not in used_symbols] or list(AUTO_SYMBOLS)
    colors = [c for c in AUTO_COLORS if c not in used_colors] or list(AUTO_COLORS)
    entry = {
        "name": str(name).strip(),
        "title": "auto",
        "symbol": symbols[digest % len(symbols)],
        "color": colors[(digest >> 16) % len(colors)],
        "bearing": "",
        "suggested": "",
    }
    cache[key] = entry
    return entry


def model_short(model_json):
    try:
        m = json.loads(model_json) if model_json else {}
        mid = m.get("id", "?")
        return mid.split("/")[-1]
    except (ValueError, TypeError):
        return "?"


def render(args, frame, now, sessions, todos, last_tools, manifest):
    width = shutil.get_terminal_size((100, 30)).columns
    color = use_color(args.plain)
    lines = []

    live = 0
    for r in sessions:
        if now - r[7] <= args.live_window * 1000:
            live += 1
    spin = SPIN[frame % len(SPIN)]
    head = "pstack fleet  %s  %d live / %d shown" % (spin if live else "·", live, len(sessions))
    lines.append(paint("bold", trunc(head, width), color))
    scope = "session " + args.session if args.session else (args.dir if not args.all else "all projects")
    lines.append(paint("dim", trunc("scope: %s   updated: %s" % (
        scope, time.strftime("%H:%M:%S")), width), color))

    man = load_manifest(args.fleet) if args.fleet else None
    cast = []
    if not getattr(args, "no_cast", False):
        cast = load_cast(getattr(args, "cast", None) or default_cast())
    lookup = cast_lookup(cast)
    auto_cache = {}
    no_cast = getattr(args, "no_cast", False)
    if man is not None:
        if "error" in man:
            lines.append(paint("red", trunc(man["error"], width), color))
        else:
            lines.append("")
            lines.append(paint("bold", trunc("fleet: %s" % man.get("fleet"), width), color))
            for i, w in enumerate(man.get("workers", [])[:20]):
                st = str(w.get("status", "?"))
                dot = {"running": "◉", "done": "●", "blocked": "✕", "failed": "✕"}.get(st, "○")
                if st == "running":
                    dot = paint("green", spin + " " + dot, color)
                elif st in ("blocked", "failed"):
                    dot = paint("red", dot, color)
                elif st == "done":
                    dot = paint("dim", dot, color)
                label = w.get("name", "?")
                if w.get("slice"):
                    label += "  " + str(w["slice"])
                if w.get("note"):
                    label += "  (%s)" % w["note"]
                entry = None
                pinned_name = str(w.get("character") or "").strip()
                if pinned_name and not no_cast:
                    entry = resolve_pin(lookup, pinned_name)
                    if entry is None:
                        entry = auto_character(cast, auto_cache, pinned_name)
                elif cast and not no_cast:
                    entry = cast[i % len(cast)]
                if entry:
                    plain = cast_text(entry)
                    styled = paint(entry.get("color", ""), plain, color)
                    room = max(10, width - 22 - len(plain) - 1)
                    lines.append("  %s %-8s %s %s" % (dot, trunc(st, 8), styled, trunc(label, room)))
                else:
                    lines.append("  %s %-8s %s" % (dot, trunc(st, 8), trunc(label, max(10, width - 22))))

    by_parent = {}
    roots = []
    ids = {r[0] for r in sessions}
    for r in sessions:
        pid = r[1]
        if pid and pid in ids:
            by_parent.setdefault(pid, []).append(r)
        else:
            roots.append(r)

    lines.append("")
    lines.append(paint("bold", "sessions (live = store changed <%ds, heuristic)" % args.live_window, color))
    if not sessions:
        lines.append(paint("dim", "  no sessions yet. run /swarm or /poteto-mode first.", color))
    n = 0
    for r in roots:
        lines.extend(render_session(r, 0, frame, now, args, todos, last_tools, width, color,
                                    cast[n % len(cast)] if cast else None))
        n += 1
        for c in sorted(by_parent.get(r[0], []), key=lambda x: x[6]):
            lines.extend(render_session(c, 1, frame, now, args, todos, last_tools, width, color,
                                        cast[n % len(cast)] if cast else None))
            n += 1
    return "\n".join(lines)


def render_session(r, depth, frame, now, args, todos, last_tools, width, color, entry=None):
    sid, _pid, title, agent, model, _dir, created, updated = r
    is_live = now - updated <= args.live_window * 1000
    mark = SPIN[frame % len(SPIN)] if is_live else "·"
    mark = paint("green", mark, color) if is_live else paint("dim", mark, color)
    prefix = "  └─ " if depth else "  "
    td = todos.get(sid, [])
    done = sum(1 for _, s in td if s in ("completed",))
    prog = " %d/%d todos" % (done, len(td)) if td else ""
    lt = last_tools.get(sid)
    tool_txt = ""
    if lt:
        tool_txt = " [%s:%s]" % (lt[0], lt[1])
        if lt[1] in ("error", "failed"):
            tool_txt = paint("red", tool_txt, color)
    cur = ""
    for content, status in td:
        if status == "in_progress":
            cur = " → " + trunc(content, 44)
            break
    head_room = width - 8 - len(prog) - len(" [%s]" % (lt[0] if lt else "")) - 14
    if entry:
        plain = cast_text(entry)
        styled = paint(entry.get("color", ""), plain, color)
        line1 = "%s%s %s %s" % (prefix, mark, styled, trunc(title or sid, max(20, head_room - len(plain) - 1)))
    else:
        line1 = "%s%s %s" % (prefix, mark, trunc(title or sid, max(20, head_room)))
    meta = "%s%s  %s  %s elapsed %s · active %s%s%s" % (
        "     " if depth else "  ",
        paint("dim", sid[-6:], color),
        trunc(agent or "?", 14),
        trunc(model_short(model), 22),
        fmt_elapsed(now - created),
        fmt_ago(updated, now),
        prog,
        paint("dim", tool_txt, color) if tool_txt and not color else tool_txt,
    )
    out = [line1, paint("dim", trunc(meta, width), color) if not color else meta]
    if cur:
        out.append(paint("cyan", trunc(("       " if depth else "    ") + cur, width), color))
    return out


def snapshot(args):
    now = int(time.time() * 1000)
    con = connect_ro(args.db)
    try:
        sessions = load_sessions(con, args.dir, args.session, args.max, args.all)
        ids = [r[0] for r in sessions]
        return render(args, 0, now, sessions, load_todos(con, ids), load_last_tools(con, ids), None)
    finally:
        con.close()


def watch(args):
    try:
        import select  # noqa: F401 (documents no extra deps; loop uses sleep)
    except ImportError:
        pass
    frame = 0
    sys.stdout.write("\033[?25l")
    try:
        while True:
            now = int(time.time() * 1000)
            try:
                con = connect_ro(args.db)
                try:
                    sessions = load_sessions(con, args.dir, args.session, args.max, args.all)
                    ids = [r[0] for r in sessions]
                    out = render(args, frame, now, sessions,
                                 load_todos(con, ids), load_last_tools(con, ids), None)
                finally:
                    con.close()
            except SystemExit as e:
                out = str(e)
            sys.stdout.write("\033[2J\033[H" + out + "\n")
            sys.stdout.flush()
            frame += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h\n")
        sys.stdout.flush()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Animated pstack fleet board for opencode.")
    ap.add_argument("--watch", action="store_true", help="animated live board until Ctrl-C")
    ap.add_argument("--once", action="store_true", help="print one snapshot (default)")
    ap.add_argument("--plain", action="store_true", help="no ANSI colors (for chat paste)")
    ap.add_argument("--db", default=default_db(), help="opencode sqlite path")
    ap.add_argument("--dir", default=os.getcwd(), help="project directory scope")
    ap.add_argument("--all", action="store_true", help="show sessions from all projects")
    ap.add_argument("--session", default=None, help="focus a parent session id (+ children)")
    ap.add_argument("--fleet", default=None, help="fleet manifest JSON (swarm/arena labels)")
    ap.add_argument("--cast", default=default_cast(), help="cast JSON path (default: fleet/cast.json next to script/)")
    ap.add_argument("--no-cast", action="store_true", help="render the board without characters")
    ap.add_argument("--max", type=int, default=25, help="max sessions shown")
    ap.add_argument("--interval", type=float, default=0.5, help="watch redraw seconds")
    ap.add_argument("--live-window", type=int, default=60, help="seconds to count as live")
    args = ap.parse_args(argv)
    if args.watch:
        watch(args)
    else:
        print(snapshot(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
