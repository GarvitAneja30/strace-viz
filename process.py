import re
from dataclasses import dataclass, field
from typing import Dict, Iterable

DIR_OR_FD_RE = re.compile(r'^\s*(?:\d+|AT_FDCWD)<([^>]*)>')
QUOTED_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')

OPEN_CALLS = {"open", "openat", "openat2", "creat"}
READ_CALLS = {"read", "pread64", "readv", "preadv"}
WRITE_CALLS = {"write", "pwrite64", "writev", "pwritev"}
# syscalls that take a path string as first quoted argument
PATH_CALLS = {"stat", "lstat", "newfstatat", "statx", "access", "faccessat",
              "faccessat2", "readlink", "readlinkat", "lgetxattr", "getxattr",
              "listxattr", "llistxattr", "statfs", "execve", "unlink",
              "unlinkat", "mkdir", "mkdirat", "rename", "renameat"}


@dataclass
class FileActivity:
    path: str
    opens: int = 0
    reads: int = 0
    writes: int = 0
    bytes_read: int = 0
    bytes_written: int = 0
    other_calls: int = 0
    total_time: float = 0.0
    errors: int = 0
    error_types: Dict[str, int] = field(default_factory=dict)


def resolve_path(e):
    """Best-effort absolute path for the file a syscall touched, else None."""
    m = DIR_OR_FD_RE.match(e.args)
    base = m.group(1) if m else None

    if e.name in OPEN_CALLS or e.name in PATH_CALLS:
        if e.name in OPEN_CALLS and e.ret_path and e.ret_path.startswith("/"):
            return e.ret_path  # -y already resolved it
        q = QUOTED_RE.search(e.args)
        if not q:
            return None
        target = q.group(1)
        if target.startswith("/"):
            return target
        if base and base.startswith("/"):
            return base.rstrip("/") + "/" + target  # relative to dirfd / cwd
        return target
    if base and base.startswith("/"):
        return base
    return None


def build_file_activity(events: Iterable) -> Dict[str, FileActivity]:
    files: Dict[str, FileActivity] = {}
    for e in events:
        path = resolve_path(e)
        if path is None:
            continue
        fa = files.setdefault(path, FileActivity(path))
        fa.total_time += e.duration

        if e.name in OPEN_CALLS:
            fa.opens += 1
        elif e.name in READ_CALLS:
            fa.reads += 1
            if e.ret and e.ret > 0:
                fa.bytes_read += e.ret
        elif e.name in WRITE_CALLS:
            fa.writes += 1
            if e.ret and e.ret > 0:
                fa.bytes_written += e.ret
        else:
            fa.other_calls += 1

        if e.errno:
            fa.errors += 1
            fa.error_types[e.errno] = fa.error_types.get(e.errno, 0) + 1
    return files