"""Bounded UHP subprocess transport for protocol tools."""
from __future__ import annotations

import queue
import math
import subprocess
import sys
import threading
import time

class UhpProcess:
    def __init__(self, command: list[str], *, max_line_bytes: int = 65536,
                 max_response_bytes: int = 1048576, max_queue_lines: int = 256,
                 max_queue_bytes: int = 1048576, stderr=None) -> None:
        if min(max_line_bytes, max_response_bytes, max_queue_lines, max_queue_bytes) <= 0:
            raise ValueError("UHP output limits must be positive")
        self.max_line_bytes = max_line_bytes
        self.max_response_bytes = max_response_bytes
        self.max_queue_bytes = max_queue_bytes
        self.queued_bytes = 0
        self.queue_guard = threading.Lock()
        self.failure: str | None = None
        self.finished = threading.Event()
        self.command_guard = threading.Lock()
        self.writes = queue.Queue(maxsize=1)
        self.closed = False
        self.command_line = command
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr if stderr is None else stderr,
            text=False,
        )
        self.lines: queue.Queue[tuple[str, int]] = queue.Queue(maxsize=max_queue_lines)
        self.reader = threading.Thread(target=self._read_lines, daemon=True)
        self.writer = threading.Thread(target=self._write_lines, daemon=True)
        self.reader.start()
        self.writer.start()
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
        return self._read_until(time.perf_counter() + timeout)

    def _read_until(self, deadline: float) -> list[str]:
        result: list[str] = []
        response_bytes = 0
        while True:
            if self.failure:
                self._abort(self.failure)
                raise RuntimeError(self.failure)
            if self.finished.is_set() and self.lines.empty():
                self._abort('UHP engine exited')
                raise RuntimeError("UHP engine exited")
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                self._abort('UHP response deadline exceeded')
                raise TimeoutError("UHP response deadline exceeded")
            try:
                line, wire_bytes = self.lines.get(timeout=min(remaining, 0.05))
            except queue.Empty as error:
                if time.perf_counter() >= deadline:
                    self._abort('UHP response deadline exceeded')
                    raise TimeoutError("UHP response deadline exceeded") from error
                continue
            with self.queue_guard:
                self.queued_bytes -= wire_bytes
            response_bytes += wire_bytes
            if response_bytes > self.max_response_bytes:
                self.failure = "UHP response byte limit exceeded"
                self._abort(self.failure)
                raise RuntimeError(self.failure)
            result.append(line)
            if line == "ok":
                return result

    def _abort(self, reason: str) -> None:
        self.failure = self.failure or reason
        if self.process.poll() is None:
            try:
                self.process.kill()
            except ProcessLookupError:
                pass

    def _write_lines(self) -> None:
        while not self.closed:
            item = self.writes.get()
            if item is None:
                return
            payload, done, errors = item
            try:
                if self.failure or self.closed:
                    raise RuntimeError(self.failure or 'UHP session closed')
                assert self.process.stdin is not None
                offset = 0
                while offset < len(payload):
                    count = self.process.stdin.write(payload[offset:])
                    if not count:
                        raise BrokenPipeError('UHP write made no progress')
                    offset += count
                self.process.stdin.flush()
            except (OSError, ValueError, RuntimeError) as error:
                errors.append(error)
                self._abort('UHP write failed')
            finally:
                done.set()

    def command(self, line: str, timeout: float = 5.0) -> tuple[list[str], float]:
        started = time.perf_counter()
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('UHP timeout must be positive and finite')
        deadline = started + timeout
        if "\n" in line or "\r" in line:
            raise ValueError("UHP command must be one line")
        payload = (line + '\n').encode('utf-8')
        if len(payload) > self.max_response_bytes:
            raise ValueError('UHP command byte limit exceeded')
        if not self.command_guard.acquire(timeout=max(0, deadline-time.perf_counter())):
            self._abort('UHP command deadline exceeded')
            raise TimeoutError('UHP command deadline exceeded')
        try:
            if self.failure or self.closed:
                raise RuntimeError(self.failure or 'UHP session closed')
            done = threading.Event()
            errors = []
            self.writes.put_nowait((payload, done, errors))
            if not done.wait(max(0, deadline-time.perf_counter())):
                self._abort('UHP write deadline exceeded')
                raise TimeoutError('UHP write deadline exceeded')
            if errors:
                raise RuntimeError('UHP write failed') from errors[0]
            return self._read_until(deadline), time.perf_counter() - started
        finally:
            self.command_guard.release()

    def drain_after_timeout(self) -> None:
        try:
            self.read_response(3.0)
        except (TimeoutError, RuntimeError):
            self.kill()

    def kill(self) -> None:
        self.closed = True
        self._abort('UHP session closed')
        deadline = time.perf_counter() + 3
        self.process.wait(timeout=max(.001, deadline-time.perf_counter()))
        try:
            self.writes.put_nowait(None)
        except queue.Full:
            pass
        if threading.current_thread() is not self.reader:
            self.reader.join(timeout=max(0, deadline-time.perf_counter()))
        if threading.current_thread() is not self.writer:
            self.writer.join(timeout=max(0, deadline-time.perf_counter()))
        for stream in (self.process.stdin, self.process.stdout):
            owner = self.writer if stream is self.process.stdin else self.reader
            if stream is not None and not owner.is_alive():
                stream.close()

    def close(self) -> None:
        self.kill()
