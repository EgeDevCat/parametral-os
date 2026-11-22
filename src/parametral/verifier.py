"""Deterministic patch -> build -> test verifier (phase 0.3).

This is the OS half of the RSI loop: the model proposes a patch, the verifier
applies it to a throwaway copy, builds it, runs the hidden tests and returns one
machine-readable result. It never runs a shell, never reaches the network when
`bwrap` is available, pins the toolchain by hash, fixes the clock/seed/locale,
and repeats the run so a flaky task is quarantined instead of counted as a win.

Task JSON (the contract with the AI side):

    {
      "task_id": "ue5-fix-0001",
      "repo": "/path/to/repo",
      "patch": "diff --git ...",
      "build": ["cmake", "--build", "build"],
      "test": ["ctest", "--output-on-failure"],
      "timeout_s": 300,
      "repeat": 2,
      "seed": 0,
      "toolchain": {"cmake": "<sha256 of the binary>"},
      "env": {"CC": "clang"}
    }

Result: status `passed|failed|flaky|error`, the two attempt exit codes, logs,
patch hash, toolchain fingerprint and whether the network was isolated.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field

from . import util

DEFAULT_EPOCH = 1795219200  # 2026-11-21T00:00:00Z, the release clock


class VerifyError(RuntimeError):
    def __init__(self, code: str, message: str, detail=None):
        super().__init__(message)
        self.code = code
        self.detail = detail


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command(value, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item
                                               for item in value):
        raise VerifyError("INVALID_TASK",
                          f"{field_name} must be a list of non-empty strings")
    return list(value)


@dataclass
class Task:
    task_id: str
    repo: str
    patch: str | None = None
    build: list[str] = field(default_factory=list)
    test: list[str] = field(default_factory=list)
    timeout_s: int = 300
    repeat: int = 2
    seed: int = 0
    toolchain: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    read_only: list[str] = field(default_factory=list)
    sandbox: str = "auto"  # auto | bwrap | none

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        if not isinstance(data, dict):
            raise VerifyError("INVALID_TASK", "task must be an object")
        task_id = data.get("task_id")
        repo = data.get("repo")
        if not isinstance(task_id, str) or not task_id:
            raise VerifyError("INVALID_TASK", "task_id is required")
        if not isinstance(repo, str) or not repo:
            raise VerifyError("INVALID_TASK", "repo is required")
        patch = data.get("patch")
        if patch is not None and not isinstance(patch, str):
            raise VerifyError("INVALID_TASK", "patch must be a string")
        timeout_s = int(data.get("timeout_s", 300))
        repeat = max(1, min(int(data.get("repeat", 2)), 10))
        toolchain = data.get("toolchain") or {}
        if not isinstance(toolchain, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in toolchain.items()):
            raise VerifyError("INVALID_TASK", "toolchain must be a name -> sha256 map")
        env = data.get("env") or {}
        if not isinstance(env, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            raise VerifyError("INVALID_TASK", "env must be a string -> string map")
        read_only = data.get("read_only") or []
        if not isinstance(read_only, list) or not all(isinstance(p, str) for p in read_only):
            raise VerifyError("INVALID_TASK", "read_only must be a list of paths")
        sandbox = str(data.get("sandbox", "auto"))
        if sandbox not in ("auto", "bwrap", "none"):
            raise VerifyError("INVALID_TASK", "sandbox must be auto, bwrap or none")
        return cls(task_id=task_id, repo=os.path.abspath(repo), patch=patch,
                   build=_command(data.get("build"), "build"),
                   test=_command(data.get("test"), "test"),
                   timeout_s=max(1, min(timeout_s, 86400)),
                   repeat=repeat, seed=int(data.get("seed", 0)),
                   toolchain=dict(toolchain), env=dict(env),
                   read_only=[os.path.abspath(path) for path in read_only],
                   sandbox=sandbox)

    @classmethod
    def load(cls, path: str) -> "Task":
        try:
            with open(path, "rb") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifyError("INVALID_TASK", str(exc)) from exc
        return cls.from_dict(data)


@dataclass
class Attempt:
    kind: str
    argv: list[str]
    exit_code: int | None
    duration_ms: int
    timed_out: bool
    stdout: str
    stderr: str
    isolated: bool

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "argv": self.argv,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
            "stdout": self.stdout[-4000:],
            "stderr": self.stderr[-4000:],
            "isolated": self.isolated,
        }


class Verifier:
    def __init__(self, *, epoch: int = DEFAULT_EPOCH, keep: bool = False):
        self.epoch = int(epoch)
        self.keep = keep
        self.bwrap = shutil.which("bwrap")

    # ---------------------------------------------------------------- setup

    def _toolchain_fingerprint(self, task: Task) -> dict[str, str]:
        found: dict[str, str] = {}
        for name, expected in task.toolchain.items():
            path = shutil.which(name)
            if not path:
                raise VerifyError("TOOLCHAIN_MISSING", f"toolchain binary not found: {name}")
            actual = _sha_file(path)
            if actual != expected:
                raise VerifyError(
                    "TOOLCHAIN_MISMATCH",
                    f"{name}: expected sha256 {expected}, found {actual}",
                    {"name": name, "path": path})
            found[name] = actual
        return found

    def _apply_patch(self, work: str, patch: str) -> dict:
        patch_path = os.path.join(work, ".parametral.patch")
        with open(patch_path, "w", encoding="utf-8") as handle:
            handle.write(patch)
        attempts = []
        if shutil.which("git"):
            attempts.append(["git", "apply", "--whitespace=nowarn", patch_path])
        if shutil.which("patch"):
            attempts.append(["patch", "-p1", "--batch", "--forward",
                             "--no-backup-if-mismatch", "-i", patch_path])
        if not attempts:
            raise VerifyError("PATCH_UNAVAILABLE", "neither git nor patch is installed")
        last = None
        for argv in attempts:
            proc = subprocess.run(argv, cwd=work, capture_output=True, text=True, timeout=60)
            last = proc
            if proc.returncode == 0:
                return {"argv": argv, "stdout": proc.stdout[-2000:],
                        "stderr": proc.stderr[-2000:]}
        raise VerifyError("PATCH_FAILED",
                          f"patch could not be applied ({last.returncode if last else '?'})",
                          {"stderr": (last.stderr if last else "")[-2000:]})

    def _env(self, task: Task, work: str) -> dict[str, str]:
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": os.path.join(work, "home"),
            "LC_ALL": "C",
            "LANG": "C",
            "TZ": "UTC",
            "SOURCE_DATE_EPOCH": str(self.epoch),
            "PYTHONHASHSEED": str(task.seed),
            "PARAMETRAL_SEED": str(task.seed),
            "TMPDIR": "/tmp",
        }
        env.update(task.env)
        return env

    def _bwrap(self, work: str, task: Task, *, ro_work: bool) -> list[str]:
        home = os.path.join(work, "home")
        os.makedirs(home, exist_ok=True)
        args = [
            "bwrap", "--die-with-parent", "--new-session", "--unshare-all",
            "--ro-bind", "/", "/",
            "--tmpfs", "/tmp",
            # `work` lives under /tmp; the tmpfs above hides it, so recreate the mount
            # point before binding the throwaway tree back in.
            "--dir", work,
            "--bind" if not ro_work else "--ro-bind", work, work,
            "--dev", "/dev", "--proc", "/proc",
            "--chdir", work,
            "--setenv", "PATH", self._env(task, work)["PATH"],
            "--setenv", "HOME", home,
            "--setenv", "LC_ALL", "C", "--setenv", "LANG", "C",
            "--setenv", "TZ", "UTC",
            "--setenv", "SOURCE_DATE_EPOCH", str(self.epoch),
            "--setenv", "PYTHONHASHSEED", str(task.seed),
            "--setenv", "PARAMETRAL_SEED", str(task.seed),
            "--setenv", "TMPDIR", "/tmp",
        ]
        for key, value in task.env.items():
            args.extend(["--setenv", key, value])
        return args

    def _run(self, task: Task, work: str, argv: list[str], kind: str,
             *, ro_work: bool) -> Attempt:
        env = self._env(task, work)
        sandbox = task.sandbox
        use_bwrap = sandbox == "bwrap" or (sandbox == "auto" and self.bwrap)
        if use_bwrap and not self.bwrap:
            raise VerifyError("SANDBOX_UNAVAILABLE", "bwrap requested but not installed")
        command = self._bwrap(work, task, ro_work=ro_work) + argv if use_bwrap else argv
        started = time.perf_counter()
        timed_out = False
        try:
            proc = subprocess.run(command, cwd=None if use_bwrap else work, env=env,
                                  capture_output=True, text=True, timeout=task.timeout_s,
                                  start_new_session=True)
            code, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            code = None
            out = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            err = (exc.stderr or b"").decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        elapsed = int((time.perf_counter() - started) * 1000)
        return Attempt(kind=kind, argv=argv, exit_code=code, duration_ms=elapsed,
                       timed_out=timed_out, stdout=out, stderr=err, isolated=use_bwrap)

    def _attempt(self, task: Task, work: str, number: int) -> dict:
        build = self._run(task, work, task.build, "build", ro_work=False) if task.build else None
        if build and (build.timed_out or build.exit_code != 0):
            return {"number": number, "passed": False, "build": build.to_dict(), "test": None}
        test = self._run(task, work, task.test, "test", ro_work=True) if task.test else None
        if test is None:
            return {"number": number, "passed": False, "build": build.to_dict() if build else None,
                    "test": None, "error": "task has no test command"}
        return {"number": number, "passed": (not test.timed_out and test.exit_code == 0),
                "build": build.to_dict() if build else None, "test": test.to_dict()}

    # ------------------------------------------------------------------ run

    def run(self, task: Task) -> dict:
        started = time.perf_counter()
        if not os.path.isdir(task.repo):
            raise VerifyError("REPO_MISSING", f"repo not found: {task.repo}")
        toolchain = self._toolchain_fingerprint(task)
        root = tempfile.mkdtemp(prefix="parametral-verify-")
        work = os.path.join(root, "repo")
        try:
            shutil.copytree(task.repo, work, symlinks=True)
            patch_result = self._apply_patch(work, task.patch) if task.patch else None
            attempts = [self._attempt(task, work, number) for number in range(1, task.repeat + 1)]
            passed = [attempt["passed"] for attempt in attempts]
            if all(passed):
                status = "passed"
            elif not any(passed):
                status = "failed"
            else:
                status = "flaky"
            deterministic = len(set(passed)) == 1
            result = {
                "task_id": task.task_id,
                "status": status,
                "passed": status == "passed",
                "deterministic": deterministic,
                "repeat": task.repeat,
                "seed": task.seed,
                "epoch": self.epoch,
                "patch_sha256": _sha_bytes((task.patch or "").encode()),
                "toolchain": toolchain,
                "network_isolated": bool(self.bwrap and task.sandbox != "none"),
                "attempts": attempts,
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "workdir": work if self.keep else None,
            }
            if patch_result:
                result["patch"] = patch_result
            return result
        finally:
            if not self.keep:
                shutil.rmtree(root, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="parametral-verify",
                                     description="deterministic patch -> build -> test")
    parser.add_argument("task", help="task JSON")
    parser.add_argument("--keep", action="store_true", help="keep the throwaway work tree")
    parser.add_argument("--epoch", type=int, default=DEFAULT_EPOCH)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    task = Task.load(args.task)
    result = Verifier(epoch=args.epoch, keep=args.keep).run(task)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1
