import fnmatch

from categories import categorize
from process import resolve_path

CATEGORY_KEYS = {
    "data": "Data I/O",
    "metadata": "Metadata",
    "openclose": "Open/close",
    "memexec": "Memory/exec",
    "other": "Other",
    "process": "Process/wait",
}


def apply_filters(events, pids=None, syscalls=None, path=None,
                  errors_only=False, category=None, min_duration_ms=0.0):
    wanted_cat = CATEGORY_KEYS.get(category)
    out = []
    for e in events:
        if pids and e.pid not in pids:
            continue
        if syscalls and e.name not in syscalls:
            continue
        if errors_only and not e.errno:
            continue
        if wanted_cat and categorize(e.name) != wanted_cat:
            continue
        if e.duration * 1000 < min_duration_ms:
            continue
        if path:
            p = resolve_path(e)
            if p is None or not fnmatch.fnmatch(p, path):
                continue
        out.append(e)
    return out