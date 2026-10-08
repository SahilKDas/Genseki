"""Bounded UHP subprocess transport for protocol tools."""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time

class UhpProcess:
    def __init__(self, command: list[str], *, max_line_bytes: int = 65536,
                 max_response_bytes: int = 1048576, max_queue_lines: int = 256,
                 max_queue_bytes: int = 1048576) -> None:
        if min(max_line_bytes, max_response_bytes, max_queue_lines, max_queue_bytes) <= 0:
            raise ValueError("UHP output limits must be positive")
        self.max_line_bytes = max_line_bytes
        self.max_response_bytes = max_response_bytes
        self.max_queue_bytes = max_queue_bytes
        self.queued_bytes = 0
        self.queue_guard = threading.Lock()
        self.failure: str | None = None
        self.finished = threading.Event()
        self.command_line = command
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=False,
        )
        self.lines: queue.Queue[tuple[str, int]] = queue.Queue(maxsize=max_queue_lines)
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
            while True:
                raw = self.process.stdout.readline(self.max_line_bytes + 1)
                if not raw:
                    break
                if len(raw) > self.max_line_bytes:
                    raise ValueError("UHP line byte limit exceeded")
                line = raw.decode("utf-8", errors="strict").rstrip("\r\n")
                try:
                    with self.queue_guard:
                        if self.queued_bytes + len(raw) > self.max_queue_bytes:
                            raise ValueError("UHP queued byte limit exceeded")
                        self.lines.put_nowait((line, len(raw)))
                        self.queued_bytes += len(raw)
                except queue.Full:
                    raise ValueError("UHP queued output limit exceeded") from None
        except (ValueError, UnicodeError, OSError):
            self.failure = "UHP invalid or excessive output"
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=3)
        finally:
            self.finished.set()

    def read_response(self, timeout: float) -> list[str]:
        deadline = time.perf_counter() + timeout
        result: list[str] = []
        response_bytes = 0
        while True:
            if self.failure:
                self.kill()
                raise RuntimeError(self.failure)
            if self.finished.is_set() and self.lines.empty():
                self.kill()
                raise RuntimeError("UHP engine exited")
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise TimeoutError("UHP response deadline exceeded")
            try:
                line, wire_bytes = self.lines.get(timeout=min(remaining, 0.05))
            except queue.Empty as error:
                if time.perf_counter() >= deadline:
                    raise TimeoutError("UHP response deadline exceeded") from error
                continue
            with self.queue_guard:
                self.queued_bytes -= wire_bytes
            response_bytes += wire_bytes
            if response_bytes > self.max_response_bytes:
                self.failure = "UHP response byte limit exceeded"
                self.kill()
                raise RuntimeError(self.failure)
            result.append(line)
            if line == "ok":
                return result

    def command(self, line: str, timeout: float = 5.0) -> tuple[list[str], float]:
        assert self.process.stdin is not None
        started = time.perf_counter()
        if self.failure:
            self.kill()
            raise RuntimeError(self.failure)
        if "\n" in line or "\r" in line:
            raise ValueError("UHP command must be one line")
        self.process.stdin.write((line + "\n").encode("utf-8"))
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
                self.process.stdin.write(b"exit\n")
                self.process.stdin.flush()
                self.process.wait(timeout=3)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.kill()
        self.kill()
