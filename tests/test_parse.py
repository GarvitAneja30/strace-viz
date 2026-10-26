import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from categories import categorize
from filters import apply_filters
from process import build_file_activity, resolve_path
from process_tree import build_tree
from strace_parse import parse_trace

SAMPLE = """\
22651 12:25:01.100000 execve("/usr/bin/sh", ["sh", "-c", "ls | wc -l"], 0x7ffd /* 40 vars */) = 0 <0.000300>
22651 12:25:01.101000 clone(child_stack=NULL, flags=CLONE_CHILD_CLEARTID|SIGCHLD) = 22652 <0.000100>
22652 12:25:01.102000 execve("/usr/bin/ls", ["ls", "/etc"], 0x7ffd /* 40 vars */) = 0 <0.000250>
22652 12:25:01.103000 openat(AT_FDCWD</home/garvit>, "/tmp/t.txt", O_RDONLY) = 3</tmp/t.txt> <0.000020>
22652 12:25:01.104000 read(3</tmp/t.txt>, "hello\\n", 131072) = 6 <0.000012>
22652 12:25:01.105000 openat(AT_FDCWD</etc>, "passwd", O_RDONLY) = -1 ENOENT (No such file or directory) <0.000015>
22652 12:25:01.106000 lgetxattr("/etc/hosts", "security.selinux", 0x0, 0) = -1 ENODATA (No data available) <0.000007>
22652 12:25:01.107000 read(4<pipe:[123]>,  <unfinished ...>
22652 12:25:01.107900 <... read resumed>"abc", 131072) = 3 <0.000900>
22652 12:25:01.108000 write(1</dev/null>, "x", 1) = 1 <0.000010>
22652 12:25:01.109000 --- SIGCHLD {si_signo=SIGCHLD} ---
22652 12:25:01.110000 +++ exited with 0 +++
"""


def events():
    return list(parse_trace(SAMPLE.splitlines()))


class ParserTests(unittest.TestCase):
    def test_skips_signal_and_exit_lines(self):
        names = [e.name for e in events()]
        self.assertNotIn("SIGCHLD", names)
        self.assertEqual(len(names), 9)

    def test_basic_fields(self):
        e = [x for x in events() if x.name == "read" and x.ret == 6][0]
        self.assertEqual(e.pid, 22652)
        self.assertAlmostEqual(e.duration, 0.000012)
        self.assertIsNone(e.errno)

    def test_fd_return_path(self):
        e = [x for x in events() if x.name == "openat" and x.ret == 3][0]
        self.assertEqual(e.ret_path, "/tmp/t.txt")

    def test_errno_parsed(self):
        e = [x for x in events() if x.name == "lgetxattr"][0]
        self.assertEqual(e.ret, -1)
        self.assertEqual(e.errno, "ENODATA")

    def test_unfinished_resumed_merged(self):
        e = [x for x in events() if x.name == "read" and x.ret == 3][0]
        self.assertAlmostEqual(e.duration, 0.0009)
        self.assertIn("pipe:[123]", e.args)


class ProcessTests(unittest.TestCase):
    def test_relative_path_resolved_against_dirfd(self):
        e = [x for x in events() if x.errno == "ENOENT"][0]
        self.assertEqual(resolve_path(e), "/etc/passwd")

    def test_pipe_fd_has_no_path(self):
        e = [x for x in events() if x.name == "read" and x.ret == 3][0]
        self.assertIsNone(resolve_path(e))

    def test_file_activity_totals(self):
        files = build_file_activity(events())
        f = files["/tmp/t.txt"]
        self.assertEqual((f.opens, f.reads, f.bytes_read), (1, 1, 6))
        self.assertEqual(files["/etc/passwd"].errors, 1)
        self.assertEqual(files["/etc/hosts"].error_types, {"ENODATA": 1})
        self.assertEqual(files["/dev/null"].bytes_written, 1)


class CategoryAndFilterTests(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(categorize("read"), "Data I/O")
        self.assertEqual(categorize("lgetxattr"), "Metadata")
        self.assertEqual(categorize("openat"), "Open/close")
        self.assertEqual(categorize("execve"), "Memory/exec")
        self.assertEqual(categorize("wait4"), "Process/wait")
        self.assertEqual(categorize("ioctl"), "Other")

    def test_errors_only(self):
        out = apply_filters(events(), errors_only=True)
        self.assertEqual({e.name for e in out}, {"openat", "lgetxattr"})

    def test_path_glob(self):
        out = apply_filters(events(), path="/etc/*")
        self.assertEqual({e.name for e in out}, {"openat", "lgetxattr"})

    def test_pid_and_syscall(self):
        out = apply_filters(events(), pids=[22652], syscalls=["read"])
        self.assertEqual(len(out), 2)

    def test_min_duration(self):
        out = apply_filters(events(), min_duration_ms=0.2)
        self.assertEqual({e.name for e in out}, {"execve", "read"})


class TreeTests(unittest.TestCase):
    def test_parent_child_and_cmd(self):
        evs = events()
        roots = build_tree(evs, evs)
        self.assertEqual(len(roots), 1)
        root = roots[0]
        self.assertEqual(root.pid, 22651)
        self.assertEqual(len(root.children), 1)
        self.assertEqual(root.children[0].pid, 22652)
        self.assertTrue(root.children[0].cmd.startswith("ls"))

    def test_stats_come_from_filtered_events(self):
        evs = events()
        data_only = apply_filters(evs, category="data")
        root = build_tree(evs, data_only)[0]
        self.assertEqual(root.calls, 0)
        self.assertEqual(root.children[0].calls, 3)  # 2 reads + 1 write


if __name__ == "__main__":
    unittest.main()