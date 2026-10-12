"""Pinned DwarfStar installation and measured 16 GiB execution gate."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .model_target import DEEPSEEK_V4_FLASH, verify_weight_file
from .host_preflight import inspect_host, require_cpu_host


DS4_REPOSITORY = "https://github.com/antirez/ds4.git"
DS4_REVISION = "84cc882352757baf628a1776badf7cc54d584e28"
REQUIRED_SOURCE = ("Makefile", "LICENSE", "ds4.c", "ds4.h", "ds4_cli.c", "ds4_help.c")
REQUIRED_FLAGS = (
    "--prompt-file", "--ssd-streaming", "--ssd-streaming-cache-experts",
    "--ctx", "--tokens", "--nothink",
)
GIB = 1024**3
DEFAULT_RSS_CAP = 15_569_256_448  # 14.5 GiB; reserves 1.5 GiB of a 16 GiB host.
SMOKE_CONTEXT_TOKENS = 512
SMOKE_OUTPUT_TOKENS = 16
PRODUCT_CONTEXT_TOKENS = 8192
PRODUCT_MAX_NEW_TOKENS = 2048
QUALIFICATION_LADDER = ((512, 16), (2048, 128), (4096, 512), (8192, 2048))


def validate_token_profile(context_tokens: int, output_tokens: int) -> None:
    if isinstance(context_tokens, bool) or not isinstance(context_tokens, int):
        raise ValueError("context_tokens must be an integer")
    if isinstance(output_tokens, bool) or not isinstance(output_tokens, int):
        raise ValueError("output_tokens must be an integer")
    if not 2 <= context_tokens <= PRODUCT_CONTEXT_TOKENS:
        raise ValueError(f"Pocket Rocket context must be between 2 and {PRODUCT_CONTEXT_TOKENS}")
    if not 1 <= output_tokens <= PRODUCT_MAX_NEW_TOKENS:
        raise ValueError(f"Pocket Rocket output must be between 1 and {PRODUCT_MAX_NEW_TOKENS} tokens")
    if output_tokens >= context_tokens:
        raise ValueError("output token reserve must be smaller than the context")


def build_ds4_command(binary: Path, model: Path, prompt: Path, *, system: str,
                      context_tokens: int, output_tokens: int) -> list[str]:
    """Construct the one admitted CPU/SSD command without environment aliases."""
    validate_token_profile(context_tokens, output_tokens)
    if not system or "\0" in system:
        raise ValueError("system prompt must be non-empty and NUL-free")
    return [
        str(binary), "-m", str(model), "--prompt-file", str(prompt),
        "-sys", system, "--ctx", str(context_tokens), "--tokens",
        str(output_tokens), "--temp", "0", "--power", "100",
        "--ssd-streaming", "--ssd-streaming-cache-experts", "1GB",
        "--nothink",
    ]


def _run(argv: list[str], *, cwd: Path | None = None, timeout: int = 3600) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        detail = (result.stdout + result.stderr)[-12000:]
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(argv)}\n{detail}")
    return result


def _origin_matches(value: str) -> bool:
    def normalized(item: str) -> str:
        return item.strip().removesuffix("/").removesuffix(".git")
    return normalized(value) == normalized(DS4_REPOSITORY)


def choose_build_target(requested: str = "auto") -> str:
    if requested not in {"auto", "cpu"}:
        raise ValueError("CPU-only build target must be auto or cpu")
    return "cpu"


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def recover_ds4_install(root: Path) -> dict[str, bool]:
    """Recover only transaction artifacts; never invent or repair source bytes."""
    runtime_parent = root.resolve() / "runtime"
    runtime = runtime_parent / "ds4"
    staging = runtime_parent / "ds4.installing"
    previous = runtime_parent / "ds4.previous"
    runtime_parent.mkdir(parents=True, exist_ok=True)
    restored_previous = False
    removed_staging = False
    removed_previous = False
    if staging.exists():
        shutil.rmtree(staging)
        removed_staging = True
    if not runtime.exists() and previous.exists():
        os.replace(previous, runtime)
        restored_previous = True
    elif runtime.exists() and previous.exists():
        shutil.rmtree(previous)
        removed_previous = True
    for temporary in runtime_parent.glob("ds4-install-manifest.json.*.tmp"):
        temporary.unlink(missing_ok=True)
    return {"restored_previous": restored_previous, "removed_staging": removed_staging,
            "removed_previous": removed_previous}


def _validate_existing_checkout(runtime: Path) -> None:
    if not (runtime / ".git").is_dir():
        raise RuntimeError(f"refusing non-Git runtime path: {runtime}")
    origin = _run(["git", "-C", str(runtime), "remote", "get-url", "origin"], timeout=30).stdout
    if not _origin_matches(origin):
        raise RuntimeError(f"refusing unexpected ds4 origin: {origin.strip()}")
    dirty = _run(["git", "-C", str(runtime), "status", "--porcelain"], timeout=30).stdout
    if dirty:
        raise RuntimeError("refusing to replace a modified ds4 checkout")


def _verify_ds4_source(runtime: Path) -> None:
    missing = [name for name in REQUIRED_SOURCE if not (runtime / name).is_file()]
    if missing:
        raise RuntimeError("ds4 source contract missing: " + ", ".join(missing))
    license_text = (runtime / "LICENSE").read_text(encoding="utf-8", errors="replace")
    if "MIT License" not in license_text:
        raise RuntimeError("ds4 license contract changed")


def _verify_ds4_binary(runtime: Path, expected_revision: str = DS4_REVISION) -> str:
    commit = _run(["git", "-C", str(runtime), "rev-parse", "HEAD"], timeout=30).stdout.strip()
    if commit != expected_revision:
        raise RuntimeError(f"ds4 revision mismatch: {commit}")
    binary = runtime / "ds4"
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError("ds4 build did not produce an executable")
    help_result = _run([str(binary), "--help=all"], cwd=runtime, timeout=30)
    help_text = help_result.stdout + help_result.stderr
    missing_flags = [flag for flag in REQUIRED_FLAGS if flag not in help_text]
    if missing_flags:
        raise RuntimeError("ds4 CLI contract missing: " + ", ".join(missing_flags))
    return commit


def install_ds4(root: Path, *, target: str = "auto", run_tests: bool = True) -> dict[str, object]:
    """Transactionally fetch one immutable ds4 commit, build it, and verify its CLI contract."""
    root = root.resolve()
    if not shutil.which("git") or not shutil.which("make"):
        raise RuntimeError("git and make are required")
    selected = choose_build_target(target)
    runtime_parent = root / "runtime"
    runtime = runtime_parent / "ds4"
    runtime_parent.mkdir(parents=True, exist_ok=True)
    recover_ds4_install(root)
    # Refuse unsafe local states before any clone/fetch/network mutation.
    if runtime.exists():
        _validate_existing_checkout(runtime)
    host = inspect_host()
    require_cpu_host(host)
    staging = runtime_parent / "ds4.installing"
    previous = runtime_parent / "ds4.previous"
    if runtime.exists():
        _run(["git", "clone", "--no-hardlinks", str(runtime), str(staging)])
        _run(["git", "-C", str(staging), "remote", "set-url", "origin", DS4_REPOSITORY])
    else:
        _run(["git", "clone", "--filter=blob:none", "--no-checkout", DS4_REPOSITORY, str(staging)])
    try:
        _run(["git", "-C", str(staging), "fetch", "--depth", "1", "origin", DS4_REVISION])
        _run(["git", "-C", str(staging), "checkout", "--detach", DS4_REVISION])
        commit = _run(["git", "-C", str(staging), "rev-parse", "HEAD"], timeout=30).stdout.strip()
        if commit != DS4_REVISION:
            raise RuntimeError(f"ds4 revision mismatch: {commit}")
        _verify_ds4_source(staging)
        _run(["make", "clean"], cwd=staging)
        jobs = str(max(1, min(os.cpu_count() or 2, 12)))
        _run(["make", "-j", jobs, selected], cwd=staging)
        _verify_ds4_binary(staging, DS4_REVISION)
        if run_tests:
            _run(["make", "q4k-dot-test", "tests/test_layer_pack"], cwd=staging)
            for argv in (["./ds4-eval", "--self-test-extractors"], ["./tests/test_layer_pack"]):
                _run(list(argv), cwd=staging, timeout=1800)
        report = {"repository": DS4_REPOSITORY, "revision": commit, "build_target": selected,
                  "binary": str(runtime / "ds4"), "tests_run": run_tests, "contract_ok": True,
                  "gpu_backend": "disabled", "host_preflight_sha256": host.certificate_sha256,
                  "default_arithmetic_mode": host.default_arithmetic_mode}
        if runtime.exists():
            os.replace(runtime, previous)
        os.replace(staging, runtime)
        _atomic_json(runtime_parent / "ds4-install-manifest.json", report)
        if previous.exists():
            shutil.rmtree(previous)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        if previous.exists():
            if runtime.exists():
                shutil.rmtree(runtime)
            os.replace(previous, runtime)
        raise
    return report


def _descendants(root_pid: int) -> set[int]:
    parents: dict[int, int] = {}
    for item in Path("/proc").iterdir():
        if not item.name.isdigit():
            continue
        try:
            fields = (item / "stat").read_text().split()
            parents[int(item.name)] = int(fields[3])
        except (OSError, ValueError, IndexError):
            continue
    found = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, parent in parents.items():
            if parent in found and pid not in found:
                found.add(pid)
                changed = True
    return found


def _rss_bytes(pid: int) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


@dataclass(frozen=True)
class GateReport:
    status: str
    model_sha256: str
    runtime_revision: str
    command_sha256: str
    stdout_sha256: str
    exit_code: int
    peak_rss_bytes: int
    rss_cap_bytes: int
    context_tokens: int
    output_tokens: int
    expert_cache: str
    elapsed_seconds: float
    profile: str = "custom"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _execute_guarded(command: list[str], *, cwd: Path, env: dict[str, str],
                     rss_cap_bytes: int, timeout: int,
                     term_grace_seconds: float = 10.0) -> tuple[str, int, float]:
    """Execute one native model process under the shared process-tree RSS gate."""
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    if process.stdout is None:
        process.kill()
        raise RuntimeError("unable to capture ds4 output")
    output: list[str] = []
    reader = threading.Thread(target=lambda: output.extend(iter(process.stdout.readline, "")), daemon=True)
    reader.start()
    peak = 0
    reason: str | None = None
    while process.poll() is None:
        peak = max(peak, sum(_rss_bytes(pid) for pid in _descendants(process.pid)))
        if peak > rss_cap_bytes:
            reason = f"RSS cap exceeded: {peak} > {rss_cap_bytes}"
        elif time.monotonic() - started > timeout:
            reason = f"timeout exceeded: {timeout}s"
        if reason is not None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=term_grace_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=max(1.0, term_grace_seconds))
            break
        time.sleep(0.05)
    reader.join(timeout=10)
    process.stdout.close()
    peak = max(peak, sum(_rss_bytes(pid) for pid in _descendants(process.pid)))
    text = "".join(output)
    elapsed = time.monotonic() - started
    if reason is not None:
        raise RuntimeError(f"ds4 execution stopped: {reason}")
    if process.returncode != 0:
        raise RuntimeError(f"ds4 inference failed ({process.returncode})\n{text[-12000:]}")
    if not text.strip():
        raise RuntimeError("ds4 returned no inference output")
    return text, peak, elapsed


class DS4LocalTransport:
    """Single local-model transport used by the Lumus ARH `/ask` path."""

    name = "pinned-ds4-deepseek-v4-flash"

    def __init__(self, root: Path, *, context_tokens: int = PRODUCT_CONTEXT_TOKENS,
                 rss_cap_bytes: int = DEFAULT_RSS_CAP, timeout: int = 1800) -> None:
        self.host = inspect_host()
        require_cpu_host(self.host)
        self.root = root.resolve()
        self.runtime = self.root / "runtime" / "ds4"
        self.binary = self.runtime / "ds4"
        self.model = self.root / "models" / "DeepSeek-V4-Flash" / DEEPSEEK_V4_FLASH.weight_filename
        validate_token_profile(context_tokens, 1)
        if rss_cap_bytes < GIB:
            raise ValueError("RSS cap is too small for the model runtime")
        self.context_tokens = context_tokens
        self.rss_cap_bytes = rss_cap_bytes
        self.timeout = timeout
        self.verification = verify_weight_file(self.model)
        try:
            _verify_ds4_binary(self.runtime, DS4_REVISION)
        except RuntimeError as exc:
            raise RuntimeError(f"pinned ds4 runtime contract failed: {exc}") from exc

    def generate(self, prompt: str, *, max_new_tokens: int) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be non-empty text")
        validate_token_profile(self.context_tokens, max_new_tokens)
        temp_root = self.root / "var"
        temp_root.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix="lumus-", suffix=".prompt", dir=temp_root)
        prompt_path = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(prompt)
            command = build_ds4_command(
                self.binary, self.model, prompt_path,
                system="Lumus Pocket Rocket local worker",
                context_tokens=self.context_tokens, output_tokens=max_new_tokens,
            )
            env = os.environ.copy()
            text, _peak, _elapsed = _execute_guarded(
                command, cwd=self.runtime, env=env, rss_cap_bytes=self.rss_cap_bytes,
                timeout=self.timeout,
            )
            return text
        finally:
            prompt_path.unlink(missing_ok=True)


def run_16gb_gate(root: Path, *, context_tokens: int = SMOKE_CONTEXT_TOKENS,
                  output_tokens: int = SMOKE_OUTPUT_TOKENS,
                  rss_cap_bytes: int = DEFAULT_RSS_CAP, timeout: int = 1800) -> GateReport:
    """Generate real tokens and fail if the ds4 process tree crosses the RAM cap."""
    host = inspect_host()
    require_cpu_host(host)
    root = root.resolve()
    runtime = root / "runtime" / "ds4"
    binary = runtime / "ds4"
    model = root / "models" / "DeepSeek-V4-Flash" / DEEPSEEK_V4_FLASH.weight_filename
    verification = verify_weight_file(model)
    commit = _verify_ds4_binary(runtime, DS4_REVISION)
    validate_token_profile(context_tokens, output_tokens)
    prompt_dir = root / "var"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt = prompt_dir / "16gb-gate-prompt.txt"
    prompt.write_text("Reply with one short sentence confirming local inference.\n", encoding="utf-8")
    command = build_ds4_command(
        binary, model, prompt,
        system="You are the Pocket Rocket local runtime acceptance test.",
        context_tokens=context_tokens, output_tokens=output_tokens,
    )
    env = os.environ.copy()
    text, peak, elapsed = _execute_guarded(
        command, cwd=runtime, env=env, rss_cap_bytes=rss_cap_bytes, timeout=timeout,
    )
    command_hash = hashlib.sha256("\0".join(command).encode()).hexdigest()
    profile = ("smoke" if (context_tokens, output_tokens) ==
               (SMOKE_CONTEXT_TOKENS, SMOKE_OUTPUT_TOKENS) else
               "product" if (context_tokens, output_tokens) ==
               (PRODUCT_CONTEXT_TOKENS, PRODUCT_MAX_NEW_TOKENS) else "custom")
    report = GateReport("PASS", str(verification["sha256"]), commit, command_hash,
                        hashlib.sha256(text.encode()).hexdigest(), 0, peak,
                        rss_cap_bytes, context_tokens, output_tokens, "1GB",
                        round(elapsed, 6), profile)
    report_path = root / "var" / "16gb-gate-report.json"
    report_path.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "var" / "16gb-gate-output.txt").write_text(text, encoding="utf-8")
    (root / "var" / f"16gb-gate-{context_tokens}-report.json").write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "var" / f"16gb-gate-{context_tokens}-output.txt").write_text(text, encoding="utf-8")
    return report


def run_context_ladder(root: Path, *, rss_cap_bytes: int = DEFAULT_RSS_CAP,
                       timeout: int = 7200) -> tuple[GateReport, ...]:
    """Qualify every context frontier in order; the first failure aborts."""
    reports: list[GateReport] = []
    for context_tokens, output_tokens in QUALIFICATION_LADDER:
        reports.append(run_16gb_gate(
            root, context_tokens=context_tokens, output_tokens=output_tokens,
            rss_cap_bytes=rss_cap_bytes, timeout=timeout,
        ))
    return tuple(reports)
