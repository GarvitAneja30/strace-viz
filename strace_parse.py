import re
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

LINE_RE = re.compile(r'^(?:(?P<pid>\d+)\s+)?(?P<ts>\d{2}:\d{2}:\d{2}\.\d+)\s+(?P<body>.*)$')
UNFINISHED_RE = re.compile(r'^(?P<name>\w+)\((?P<args>.*?)\s*<unfinished \.\.\.>$')
RESUMED_RE = re.compile(r'^<\.\.\. (?P<name>\w+) resumed>(?P<rest>.*)$')
COMPLETE_RE = re.compile(
    r'^(?P<name>\w+)\((?P<args>.*)\)\s+=\s+'
    r'(?P<ret>-?\d+|\?|0x[0-9a-fA-F]+)'
    r'(?:<(?P<ret_path>[^>]*)>)?'
    r'(?P<tail>[^<]*?)'
    r'(?:\s*<(?P<dur>\d+\.\d+)>)?\s*$'
)
ERRNO_RE = re.compile(r'^\s*(E[A-Z0-9]+)')


@dataclass
class SyscallEvent:
    pid: int
    ts: str
    name: str
    args: str
    ret: Optional[int]
    ret_path: Optional[str]   # path resolved by -y when ret is an fd
    errno: Optional[str]
    duration: float           # seconds


def parse_trace(lines: Iterable[str]) -> Iterator[SyscallEvent]:
    pending = {}  # pid -> (syscall name, args seen so far)
    for raw in lines:
        m = LINE_RE.match(raw.rstrip("\n"))
        if not m:
            continue
        pid = int(m["pid"]) if m["pid"] else 0
        body = m["body"]

        if body.startswith(("+++", "---")):  # exit / signal lines
            continue

        u = UNFINISHED_RE.match(body)
        if u:
            pending[pid] = (u["name"], u["args"].rstrip())
            continue

        r = RESUMED_RE.match(body)
        if r:
            if pid not in pending:
                continue
            name, prefix = pending.pop(pid)
            sep = " " if prefix.endswith(",") else ""
            body = f"{name}({prefix}{sep}{r['rest']}"

        c = COMPLETE_RE.match(body)
        if not c:
            continue

        try:
            ret = int(c["ret"], 0)
        except ValueError:
            ret = None

        e = ERRNO_RE.match(c["tail"] or "")
        yield SyscallEvent(
            pid=pid,
            ts=m["ts"],
            name=c["name"],
            args=c["args"],
            ret=ret,
            ret_path=c["ret_path"],
            errno=e.group(1) if e else None,
            duration=float(c["dur"]) if c["dur"] else 0.0,
        )
