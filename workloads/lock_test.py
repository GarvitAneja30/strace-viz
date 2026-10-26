#!/usr/bin/env python3
"""Locking workload for strace-viz: two processes contend for one flock."""
import argparse
import fcntl
import os
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["blocking", "nonblocking"], required=True)
    p.add_argument("--hold", type=float, default=0.3, help="seconds the parent holds the lock")
    p.add_argument("--dir", default="workload_out")
    args = p.parse_args()

    os.makedirs(args.dir, exist_ok=True)
    path = os.path.join(args.dir, "lock.dat")

    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)                 # parent takes the lock

    pid = os.fork()
    if pid == 0:                                    # child
        cfd = os.open(path, os.O_RDWR)              # own open file description
        flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if args.mode == "nonblocking" else 0)
        try:
            fcntl.flock(cfd, flags)
            os.write(cfd, b"child wrote under lock\n")
            fcntl.flock(cfd, fcntl.LOCK_UN)
        except BlockingIOError:
            pass                                    # nonblocking: lock was busy
        os._exit(0)

    time.sleep(args.hold)                           # parent holds the lock
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.waitpid(pid, 0)
    os.close(fd)
    os.remove(path)


if __name__ == "__main__":
    main()