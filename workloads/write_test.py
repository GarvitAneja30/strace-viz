#!/usr/bin/env python3
"""Write workload for strace-viz: buffered vs fsync'd writes."""
import argparse
import os


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["buffered", "fsync-end", "fsync-each"], required=True)
    p.add_argument("--blocks", type=int, default=200)
    p.add_argument("--block-size", type=int, default=4096)
    p.add_argument("--dir", default="workload_out")
    args = p.parse_args()

    os.makedirs(args.dir, exist_ok=True)
    path = os.path.join(args.dir, f"{args.mode}.dat")
    data = b"x" * args.block_size

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        for _ in range(args.blocks):
            os.write(fd, data)
            if args.mode == "fsync-each":
                os.fsync(fd)
        if args.mode == "fsync-end":
            os.fsync(fd)
    finally:
        os.close(fd)
        os.remove(path)


if __name__ == "__main__":
    main()