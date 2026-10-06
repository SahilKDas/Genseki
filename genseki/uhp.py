"""Bounded UHP subprocess transport shared by Rho and protocol tools."""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time

class UhpProcess:
    def __init__(self, command: list[str]) -> None:
        self.command_line = command
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            bufsize=1,
        )
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.reader = threading.Thread(target=self._read_lines, daemon=True)
        self.reader.start()
        try:
            self.read_response(5.0)
        except BaseException:
            self.kill()
            raise

    def _read_lines(self) -> None:
        assert self.process.stdout is not None
        try:
            for line in self.process.stdout:
                self.lines.put(line.rstrip("\r\n"))
        finally:
            self.lines.put(None)

    def read_response(self, timeout: float) -> list[str]:
        deadline = time.perf_counter() + timeout
        result: list[str] = []
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise TimeoutError("UHP response deadline exceeded")
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError("UHP response deadline exceeded") from error
            if line is None:
                raise RuntimeError(f"UHP engine exited: {self.command_line}")
            result.append(line)
            if line == "ok":
                return result

    def command(self, line: str, timeout: float = 5.0) -> tuple[list[str], float]:
        assert self.process.stdin is not None
        started = time.perf_counter()
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()
        return self.read_response(timeout), time.perf_counter() - started

    def drain_after_timeout(self) -> None:
        try:
            self.read_response(3.0)
        except (TimeoutError, RuntimeError):
            self.kill()

    def kill(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=3)
        self.reader.join(timeout=3)
        for stream in (self.process.stdin, self.process.stdout):
            if stream is not None:
                stream.close()

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                assert self.process.stdin is not None
                self.process.stdin.write("exit\n")
                self.process.stdin.flush()
                self.process.wait(timeout=3)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.kill()
        self.kill()
