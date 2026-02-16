"""Integration test for per-thread exclusive locking.

Run with:
  .venv/bin/python test_thread_lock.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

from deepagents_cli.sessions import ThreadLockError, acquire_thread_lock


def _child(thread_id: str) -> None:
    # Hold the lock until terminated by the parent.
    with acquire_thread_lock(thread_id):
        print("LOCKED", flush=True)
        while True:
            time.sleep(0.25)


def _parent() -> None:
    thread_id = "locktest1"
    proc = subprocess.Popen(
        [sys.executable, __file__, "--child", thread_id],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        line = proc.stdout.readline().strip()
        assert line == "LOCKED", f"Expected child to print LOCKED, got: {line!r}"

        # Second lock attempt must fail while child holds it.
        failed = False
        try:
            with acquire_thread_lock(thread_id):
                pass
        except ThreadLockError:
            failed = True

        assert failed, "Expected ThreadLockError when thread is locked by another process"

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    # After child exits, lock should be acquirable again.
    with acquire_thread_lock(thread_id):
        pass

    print("✅ thread lock test passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", nargs=1)
    args = parser.parse_args()

    if args.child:
        _child(args.child[0])
        return

    _parent()


if __name__ == "__main__":
    main()

