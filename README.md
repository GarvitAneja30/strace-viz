# strace-viz

A small Python tool that runs a command under `strace` and summarizes its
filesystem activity: which syscalls it made, which files it touched, how many
bytes it read and wrote, and where the time went.

Linux only. Standard library only, no third-party dependencies.

## Requirements

- Linux with `strace` (`sudo apt install strace`)
- Python 3.8+

## Usage

```bash
python3 strace_viz.py run [options] -- <command> [args...]
```

Put options before the `--`. Everything after it is the traced command.

```bash
python3 strace_viz.py run -- cat /tmp/t.txt
python3 strace_viz.py run --repeat 9 -- ls -l /etc
python3 strace_viz.py run --tree --show-output -- sh -c "ls /etc | wc -l"
python3 strace_viz.py run --errors-only --top 20 -- ls -l /etc
```

## Output

Three tables per run:

1. **Syscalls**: count, total time, share of time, and errors per syscall.
2. **Categories**: calls and time grouped by kind of work (see below).
3. **Files**: per file, the opens, reads, writes, bytes read, bytes written,
   time and errors. Paths are resolved from file descriptors using `strace -y`.

With `--tree`, a fourth section shows the process tree (built from
`clone`/`execve`) with per-process call counts, time and bytes.

Colors: errors are red, slow rows are yellow, zero-error cells are dim. Colors
turn off automatically when output is piped, when `NO_COLOR` is set, or with
`--no-color`.

## Options

| Option | Meaning |
|---|---|
| `--keep` | Keep the raw strace trace file and print its path |
| `--show-output` | Show the traced command's stdout (discarded by default) |
| `--top N` | Rows in the file table (default 10) |
| `--repeat N` | Run N times and report median timings |
| `--tree` | Show the process tree (also traces clone/exec/wait) |
| `--pid PID` | Only this pid (repeatable) |
| `--syscall NAME` | Only this syscall (repeatable) |
| `--path GLOB` | Only calls touching a matching path, e.g. `'/etc/p*'` |
| `--errors-only` | Only failed syscalls |
| `--category KEY` | One of `data`, `metadata`, `openclose`, `memexec`, `sync`, `locking`, `process`, `other` |
| `--min-duration MS` | Only calls at least this long |
| `--slow-ms MS` | File time (ms) at which the file table turns yellow |
| `--no-color` | Disable colored output |

## Categories

| Category | Syscalls |
|---|---|
| Data I/O | read, write, pread64, pwrite64, readv, writev |
| Metadata | stat family, getxattr family, getdents, readlink, access |
| Open/close | open, openat, creat, close |
| Memory/exec | mmap, munmap, mprotect, brk, execve |
| Sync | fsync, fdatasync, sync, syncfs, msync |
| Locking | flock |
| Process/wait | clone, fork, wait4, exit_group |
| Other | everything else |

## Example results

Measured on ext4 on an NVMe drive. Counts, bytes and errors are exact and
repeatable. Timings are approximate (strace adds per-call overhead), so compare
ratios rather than absolute milliseconds.

### Data vs. metadata: `ls -l /etc`

886 syscalls: 87% metadata calls (about 80% of the time), 3% data I/O. Each
directory entry costs a `statx`, an `lgetxattr` and a `listxattr`, and all 244
`lgetxattr` calls fail because the files have no extended attributes. Only
about 20 KB of data is actually written. For a long directory listing, the cost
is almost entirely metadata access, not data transfer.

### Durability cost: `workloads/write_test.py`

200 writes of 4 KB (819,200 bytes) in three modes:

| Mode | fsync calls | Approx. total time |
|---|---|---|
| buffered | 0 | 1.3 ms |
| fsync-end | 1 | 3.7 ms |
| fsync-each | 200 | 257 ms |

Syncing after every write is roughly 200x slower than not syncing, and about
110x slower than one sync at the end, for the same data.

### Lock contention: `workloads/lock_test.py`

Two processes contend for one exclusive `flock`:

| Mode | Child's lock call | Result |
|---|---|---|
| blocking | about 300 ms | waits for the parent to release |
| nonblocking | about 8 microseconds | fails immediately with `EAGAIN` |

The blocking cost is idle waiting, not CPU work.

## Reproducing the experiments

```bash
python3 strace_viz.py run --repeat 5 --syscall write --syscall fsync -- python3 workloads/write_test.py --mode buffered
python3 strace_viz.py run --repeat 5 --syscall write --syscall fsync -- python3 workloads/write_test.py --mode fsync-end
python3 strace_viz.py run --repeat 5 --syscall write --syscall fsync -- python3 workloads/write_test.py --mode fsync-each

python3 strace_viz.py run --tree --syscall flock -- python3 workloads/lock_test.py --mode blocking
python3 strace_viz.py run --tree --syscall flock -- python3 workloads/lock_test.py --mode nonblocking
```

Run the `fsync` experiment on a real disk filesystem. On tmpfs, `fsync` does
almost nothing. Check with `df -T .`.

## Project layout

```
strace_viz.py     CLI entry point
strace_parse.py   strace output -> SyscallEvent
process.py        fd/path resolution, per-file activity
process_tree.py   process tree from clone/exec
categories.py     syscall categories
filters.py        event filters
colors.py         ANSI color helpers
workloads/        write_test.py, lock_test.py
tests/            unit tests
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Limitations

- Traces `file` and `desc` syscalls only (plus process calls with `--tree`).
  Network and other syscalls are not captured.
- Per-process time in a pipeline includes time spent blocked on other
  processes. Prefer call counts and byte counts there.
- `--repeat` takes medians of timings only. Counts and bytes come from run 1.
- Tracing requires permission to `ptrace` the command (your own processes work
  by default on most systems).