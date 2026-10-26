#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
import statistics


from categories import categorize, ORDER
from filters import apply_filters, CATEGORY_KEYS
from process import build_file_activity
from strace_parse import parse_trace
from colors import setup as setup_colors, paint, RED, YELLOW, DIM, BOLD
from process_tree import build_tree, print_tree

SLOW_PCT = 20.0  # syscall rows at or above this % of total time turn yellow

BASE_ARGS = ["-f", "-tt", "-T", "-y"]


def collect(cmd, show_output=False, tree=False):
    """Run cmd under strace; return (trace_path, command_exit_code)."""
    if shutil.which("strace") is None:
        sys.exit("strace not found. Install it with: sudo apt install strace")
    fd, path = tempfile.mkstemp(prefix="strace_", suffix=".trace")
    os.close(fd)
    out = None if show_output else subprocess.DEVNULL
    trace = "trace=file,desc,process" if tree else "trace=file,desc"
    proc = subprocess.run(["strace", *BASE_ARGS, "-e", trace, "-o", path, *cmd], stdout=out)
    return path, proc.returncode

def summarize(events):
    stats = defaultdict(lambda: [0, 0.0, 0])  # count, total seconds, errors
    for e in events:
        s = stats[e.name]
        s[0] += 1
        s[1] += e.duration
        s[2] += 1 if e.errno else 0
    return stats


def print_summary(stats):
    total_time = sum(s[1] for s in stats.values()) or 1e-12
    print(paint(f"{'syscall':<14}{'count':>8}{'time(ms)':>12}{'%time':>8}{'errors':>8}", BOLD))
    print("-" * 50)
    for name, (count, secs, errs) in sorted(stats.items(), key=lambda kv: -kv[1][1]):
        pct = secs / total_time * 100
        hot = YELLOW if pct >= SLOW_PCT else None
        time_s = paint(f"{secs * 1000:>12.3f}", hot)
        pct_s = paint(f"{pct:>8.1f}", hot)
        err_s = paint(f"{errs:>8}", RED if errs else DIM)
        print(f"{name:<14}{count:>8}{time_s}{pct_s}{err_s}")


def category_summary(events):
    cats = {c: [0, 0.0] for c in ORDER}  # count, seconds
    for e in events:
        c = cats[categorize(e.name)]
        c[0] += 1
        c[1] += e.duration
    return cats


def print_categories(cats):
    total_n = sum(c[0] for c in cats.values()) or 1
    total_t = sum(c[1] for c in cats.values()) or 1e-12
    print("\nBy category")
    print(f"{'category':<14}{'calls':>8}{'%calls':>9}{'time(ms)':>11}{'%time':>8}")
    print("-" * 50)
    for name in ORDER:
        n, t = cats[name]
        print(f"{name:<14}{n:>8}{n / total_n * 100:>9.1f}{t * 1000:>11.3f}{t / total_t * 100:>8.1f}")


def print_files(files, top, slow_ms):
    rows = sorted(files.values(), key=lambda f: -f.total_time)[:top]
    print(f"\nTop {len(rows)} files by time")
    print(paint(f"{'path':<46}{'opens':>6}{'reads':>6}{'writes':>7}{'B read':>10}{'B written':>11}{'ms':>8}{'err':>5}", BOLD))
    print("-" * 99)
    for f in rows:
        p = f.path if len(f.path) <= 45 else "…" + f.path[-44:]
        ms = f.total_time * 1000
        ms_s = paint(f"{ms:>8.3f}", YELLOW if ms >= slow_ms else None)
        err_s = paint(f"{f.errors:>5}", RED if f.errors else DIM)
        print(f"{p:<46}{f.opens:>6}{f.reads:>6}{f.writes:>7}{f.bytes_read:>10}"
              f"{f.bytes_written:>11}{ms_s}{err_s}")

def median_timings(runs):
    """runs: list of event lists, one per run. Returns {syscall: median total seconds}."""
    per_run = []
    for events in runs:
        totals = defaultdict(float)
        for e in events:
            totals[e.name] += e.duration
        per_run.append(totals)
    names = set().union(*per_run)
    return {n: statistics.median(r.get(n, 0.0) for r in per_run) for n in names}

def median_file_times(runs):
    per_run = [{p: fa.total_time for p, fa in build_file_activity(r).items()} for r in runs]
    paths = set().union(*per_run)
    return {p: statistics.median(d.get(p, 0.0) for d in per_run) for p in paths}

def main():
    p = argparse.ArgumentParser(prog="strace_viz")
    sub = p.add_subparsers(dest="mode", required=True)
    r = sub.add_parser("run", help="run a command under strace and summarize it")
    r.add_argument("--keep", action="store_true", help="keep the raw trace file")
    r.add_argument("--show-output", action="store_true", help="show the command's stdout")
    r.add_argument("--top", type=int, default=10, help="rows in the file table")
    r.add_argument("--pid", type=int, action="append", help="only this pid (repeatable)")
    r.add_argument("--syscall", action="append", help="only this syscall (repeatable)")
    r.add_argument("--path", help="glob on file path, quote it: '/etc/*'")
    r.add_argument("--errors-only", action="store_true", help="only failed syscalls")
    r.add_argument("--category", choices=list(CATEGORY_KEYS), help="only one category")
    r.add_argument("--min-duration", type=float, default=0.0, help="min call time in ms")
    r.add_argument("cmd", nargs=argparse.REMAINDER, help="-- <command> [args...]")
    r.add_argument("--no-color", action="store_true", help="disable colored output")
    r.add_argument("--slow-ms", type=float, default=0.1, help="file time (ms) that turns yellow")
    r.add_argument("--tree", action="store_true", help="show the process tree (traces clone/exec too)")
    r.add_argument("--repeat", type=int, default=1, help="run N times, report median timings")
    args = p.parse_args()
    setup_colors(args.no_color)

    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd
    if not cmd:
        p.error("no command given. Usage: strace_viz.py run [options] -- <command> [args...]")

    runs = []
    path = code = None
    for _ in range(max(1, args.repeat)):
        if path:
            os.remove(path)
        path, code = collect(cmd, args.show_output, args.tree)
        with open(path, errors="replace") as f:
            runs.append(list(parse_trace(f)))
    events = runs[0]
    total = len(runs[0])
    all_events = runs[0]
    filt = dict(pids=args.pid, syscalls=args.syscall, path=args.path,
                errors_only=args.errors_only, category=args.category,
                min_duration_ms=args.min_duration)
    filtered_runs = [apply_filters(r, **filt) for r in runs]
    events = filtered_runs[0]

    print(f"Command: {' '.join(cmd)}  (exit code {code})")
    print(f"Parsed {total} syscalls, showing {len(events)}\n")

    stats = summarize(events)
    cats = category_summary(events)
    files = build_file_activity(events)
    if args.repeat > 1:
        med = median_timings(filtered_runs)
        for name, s in stats.items():
            s[1] = med.get(name, s[1])
        for c in cats.values():
            c[1] = 0.0
        for name, secs in med.items():
            cats[categorize(name)][1] += secs
        fmed = median_file_times(filtered_runs)
        for p, fa in files.items():
            fa.total_time = fmed.get(p, fa.total_time)
        print(f"(timings are the median of {args.repeat} runs; counts and bytes are from run 1)")

    print_summary(stats)
    print_categories(cats)
    print_files(files, args.top, args.slow_ms)
    if args.tree:
        print_tree(build_tree(all_events, events))

    if args.keep:
        print(f"\nTrace kept at: {path}")
    else:
        os.remove(path)


if __name__ == "__main__":
    main()