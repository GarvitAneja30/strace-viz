DATA_IO = {"read", "pread64", "readv", "preadv", "write", "pwrite64", "writev", "pwritev"}

METADATA = {
    "stat", "lstat", "fstat", "newfstatat", "statx", "statfs", "fstatfs",
    "getxattr", "lgetxattr", "fgetxattr", "listxattr", "llistxattr", "flistxattr",
    "getdents", "getdents64", "readlink", "readlinkat",
    "access", "faccessat", "faccessat2",
}

OPEN_CLOSE = {"open", "openat", "openat2", "creat", "close"}

MEM_EXEC = {"mmap", "munmap", "mprotect", "brk", "execve"}

PROCESS = {"clone", "clone3", "fork", "vfork", "wait4", "waitid", "exit", "exit_group"}

SYNC = {"fsync", "fdatasync", "sync", "syncfs", "sync_file_range", "msync"}

ORDER = ["Data I/O", "Metadata", "Open/close", "Memory/exec", "Sync", "Process/wait", "Other"]

def categorize(name):
    if name in DATA_IO:
        return "Data I/O"
    if name in METADATA:
        return "Metadata"
    if name in OPEN_CLOSE:
        return "Open/close"
    if name in MEM_EXEC:
        return "Memory/exec"
    if name in PROCESS:
        return "Process/wait"
    if name in SYNC:
        return "Sync"
    return "Other"