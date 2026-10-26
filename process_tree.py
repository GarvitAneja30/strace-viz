import re
from dataclasses import dataclass, field
from typing import List

from colors import paint, RED, DIM, BOLD
from process import QUOTED_RE, READ_CALLS, WRITE_CALLS

SPAWN_CALLS = {"clone", "clone3", "fork", "vfork"}
ARGV_RE = re.compile(r'\[(.*?)\]')


@dataclass
class ProcNode:
    pid: int
    parent: int = 0
    cmd: str = "?"
    calls: int = 0
    time: float = 0.0
    bytes_read: int = 0
    bytes_written: int = 0
    errors: int = 0
    children: List["ProcNode"] = field(default_factory=list)


def _cmd_from_execve(args):
    m = ARGV_RE.search(args)
    parts = QUOTED_RE.findall(m.group(1)) if m else []
    if not parts:
        q = QUOTED_RE.search(args)
        return q.group(1) if q else None
    cmd = " ".join(parts)
    return cmd if len(cmd) <= 70 else cmd[:69] + "…"


def build_tree(structure_events, stat_events):
    """Structure (who spawned whom) comes from all events; stats from filtered ones."""
    nodes = {}

    def get(pid):
        if pid not in nodes:
            nodes[pid] = ProcNode(pid)
        return nodes[pid]

    for e in structure_events:
        node = get(e.pid)
        if e.name in SPAWN_CALLS and e.ret and e.ret > 0:
            child = get(e.ret)
            child.parent = e.pid
            if child.cmd == "?":      # child may already have exec'd (race)
                child.cmd = node.cmd
        elif e.name == "execve" and e.ret == 0:
            cmd = _cmd_from_execve(e.args)
            if cmd:
                node.cmd = cmd

    for e in stat_events:
        n = get(e.pid)
        n.calls += 1
        n.time += e.duration
        if e.errno:
            n.errors += 1
        if e.ret and e.ret > 0:
            if e.name in READ_CALLS:
                n.bytes_read += e.ret
            elif e.name in WRITE_CALLS:
                n.bytes_written += e.ret

    roots = []
    for n in sorted(nodes.values(), key=lambda x: x.pid):
        if n.parent in nodes:
            nodes[n.parent].children.append(n)
        else:
            roots.append(n)
    return roots


def _label(n):
    err = paint(f"err={n.errors}", RED if n.errors else DIM)
    return (f"{paint(n.cmd, BOLD)} [pid {n.pid}]  calls={n.calls}  "
            f"time={n.time * 1000:.3f}ms  read={n.bytes_read}B  "
            f"written={n.bytes_written}B  {err}")


def print_tree(roots):
    print("\nProcess tree")

    def walk(node, prefix, is_last, is_root):
        if is_root:
            print(_label(node))
            child_prefix = ""
        else:
            print(prefix + ("└── " if is_last else "├── ") + _label(node))
            child_prefix = prefix + ("    " if is_last else "│   ")
        for i, c in enumerate(node.children):
            walk(c, child_prefix, i == len(node.children) - 1, False)

    for r in roots:
        walk(r, "", True, True)