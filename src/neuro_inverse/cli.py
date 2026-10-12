from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import tempfile
from pathlib import Path

from .aegis_c2r import AegisC2R
from .aegis_runtime import AegisRuntime
from .aegis_boundary import AegisBoundaryError
from .agent_fabric import FabricLimits, RecursiveFabricRuntime, plan_as_dict
from .attest import create_receipt
from .nprq import meta_from_dict
from .nprq_verify import prove_monotone
from .ternary_ssm import load_diagonal_checkpoint, compare_checkpoint
from .defaults import DEFAULT_EXPERTS
from .ds4_runtime import DS4LocalTransport, PRODUCT_MAX_NEW_TOKENS
from .lumus_arh import LumusARHService, serve_loopback
from .model_pages import ModelManifest, ModelPageStore, analyze_compression, build_manifest
from .spatial_pool import GoldenHammingRouter
from .store import ExpertStore
from .ternary_exact import ExactRational, TernaryVector, Triadic
from .typed_decision import Choice, Criterion, ScoreLevel, choose, gate, ordered_score


def _root() -> Path:
    return Path(os.environ.get("NEURO_ROOT", Path.cwd())).resolve()


def _store(root: Path) -> ExpertStore:
    return ExpertStore(root / "var/store")


def _aliases(left: Path, right: Path) -> bool:
    if left.resolve(strict=False) == right.resolve(strict=False):
        return True
    try:
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except OSError:
        return False


def _validate_output(output: Path, protected: tuple[Path, ...], store: Path | None = None) -> None:
    if output.is_symlink() or output.parent.is_symlink():
        raise ValueError("output path must not be a symbolic link")
    if any(_aliases(output, path) for path in protected):
        raise ValueError("output aliases a protected input")
    if store is not None and output.resolve(strict=False).is_relative_to(store.resolve(strict=False)):
        raise ValueError("output must not be placed inside the model-page store")


def _atomic_output(output: Path, data: bytes) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=output.name + ".", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def _triadic(text: str) -> Triadic:
    fields = text.split(":")
    if len(fields) != 2:
        raise argparse.ArgumentTypeError("expected NUMERATOR:POWER_OF_THREE")
    try:
        return Triadic(int(fields[0], 10), int(fields[1], 10))
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _criterion(text: str) -> Criterion:
    fields = text.split(":")
    if len(fields) not in (3, 5):
        raise argparse.ArgumentTypeError("expected NAME:SCORE_NUM:SCORE_EXP[:WEIGHT_NUM:WEIGHT_EXP]")
    try:
        weight = Triadic(1) if len(fields) == 3 else Triadic(int(fields[3]), int(fields[4]))
        return Criterion(fields[0], Triadic(int(fields[1]), int(fields[2])), weight)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _exact_rational(text: str) -> ExactRational:
    fields = text.split(":")
    if len(fields) != 2:
        raise argparse.ArgumentTypeError("expected NUMERATOR:DENOMINATOR")
    try:
        return ExactRational(int(fields[0], 10), int(fields[1], 10))
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _score_level(text: str) -> ScoreLevel:
    fields = text.split(":")
    if len(fields) != 3:
        raise argparse.ArgumentTypeError("expected NAME:SUPPORT_NUM:SUPPORT_EXP")
    try:
        return ScoreLevel(fields[0], Triadic(int(fields[1], 10), int(fields[2], 10)))
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _trits(text: str) -> TernaryVector:
    mapping = {"-": -1, "0": 0, "+": 1}
    if not text or any(character not in mapping for character in text):
        raise argparse.ArgumentTypeError("trits use only '-', '0', '+'")
    return TernaryVector.from_trits(mapping[character] for character in text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="neuro-inverse")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-store")
    route = sub.add_parser("route")
    route.add_argument("text")
    route.add_argument("--top-k", type=int, default=3)
    route.add_argument("--domain")
    route.add_argument("--task-kind")
    route_decide = sub.add_parser("route-decide", help="typed exact decision over local expert routes")
    route_decide.add_argument("text")
    route_decide.add_argument("--minimum-margin", type=int, default=1)
    route_decide.add_argument("--domain")
    route_decide.add_argument("--task-kind")
    chat = sub.add_parser("chat")
    chat.add_argument("text")
    chat.add_argument("--max-new-tokens", type=int, default=PRODUCT_MAX_NEW_TOKENS)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--max-new-tokens", type=int, default=PRODUCT_MAX_NEW_TOKENS)
    c2r_check = sub.add_parser("aegis-c2r-check", help="check C against actual Aegis-C2R S0 translator")
    c2r_check.add_argument("source", type=Path)
    c2r_translate = sub.add_parser("aegis-c2r-translate", help="emit real Rust, AST and Aegis certificates")
    c2r_translate.add_argument("source", type=Path)
    c2r_translate.add_argument("output_dir", type=Path)
    sub.add_parser("doctor")
    sub.add_parser("aegis-doctor", help="verify and install bundled Aegis 2.4.3 locally")
    aegis_run = sub.add_parser("aegis-run", help="compile and execute a DXL/DXS/DXASM source with the real Aegis toolchain")
    aegis_run.add_argument("source", type=Path)
    aegis_run.add_argument("--timeout", type=float, default=30.0)
    ternary_dot = sub.add_parser("ternary-dot", help="exact sign-plane ternary dot product")
    ternary_dot.add_argument("left", type=_trits)
    ternary_dot.add_argument("right", type=_trits)
    decide = sub.add_parser("decide", help="proof-carrying exact triadic gate")
    decide.add_argument("--criterion", action="append", type=_criterion, required=True)
    decide.add_argument("--reject-below", type=_triadic, required=True)
    decide.add_argument("--accept-at", type=_triadic, required=True)
    decide.add_argument("--model-root", required=True)
    decide.add_argument("--request-root", required=True)
    score_parser = sub.add_parser("score", help="proof-carrying exact ordered score")
    score_parser.add_argument("--level", action="append", type=_score_level, required=True)
    score_parser.add_argument(
        "--minimum-confidence", type=_exact_rational, default=ExactRational(0)
    )
    score_parser.add_argument("--model-root", required=True)
    score_parser.add_argument("--request-root", required=True)
    manifest = sub.add_parser("model-manifest", help="hash a model into authenticated pages")
    manifest.add_argument("source", type=Path)
    manifest.add_argument("output", type=Path)
    manifest.add_argument("--page-bytes", type=int, default=1024 * 1024)
    model_import = sub.add_parser("model-import", help="attach or materialize an authenticated model")
    model_import.add_argument("manifest", type=Path)
    model_import.add_argument("source", type=Path)
    model_import.add_argument("store", type=Path)
    model_import.add_argument("--mode", choices=("static", "demand"), required=True)
    model_analyze = sub.add_parser(
        "model-analyze", help="measure exact lossless page-codec competition"
    )
    model_analyze.add_argument("manifest", type=Path)
    model_analyze.add_argument("source", type=Path)
    model_read = sub.add_parser("model-read", help="bounded authenticated range read")
    model_read.add_argument("manifest", type=Path)
    model_read.add_argument("source", type=Path)
    model_read.add_argument("store", type=Path)
    model_read.add_argument("offset", type=int)
    model_read.add_argument("length", type=int)
    model_read.add_argument("output", type=Path)
    cache_verify = sub.add_parser("model-verify-cache", help="authenticate materialized pages")
    cache_verify.add_argument("manifest", type=Path)
    cache_verify.add_argument("store", type=Path)
    agent_plan = sub.add_parser(
        "agent-plan", help="plan a bounded recursive run over the 1,024-cell fabric"
    )
    agent_plan.add_argument("goal")
    agent_run = sub.add_parser(
        "agent-run", help="execute a bounded recursive run through pinned local DS4"
    )
    agent_run.add_argument("goal")
    for command_parser in (agent_plan, agent_run):
        command_parser.add_argument("--max-depth", type=int, default=2)
        command_parser.add_argument("--max-nodes", type=int, default=9)
        command_parser.add_argument("--quorum", type=int, default=3)
        command_parser.add_argument("--max-new-tokens", type=int, default=512)
        command_parser.add_argument("--max-model-calls", type=int, default=27)
    attest = sub.add_parser("attest", help="emit a portable verified governance receipt")
    attest.add_argument("input", type=Path, help="JSON output from agent-run, decide, or score")
    attest.add_argument("--source-kind", choices=("agent-run", "decide", "score"), required=True)
    attest.add_argument("--arithmetic-mode", choices=("integer_oracle", "x87_verified", "avx2_verified"), required=True)
    attest.add_argument("--model-root")
    attest.add_argument("--request-root")
    nprq_verify = sub.add_parser("nprq-verify", help="verify NPRQ stages and optionally prove monotone SSE")
    nprq_verify.add_argument("meta", type=Path)
    nprq_verify.add_argument("--source-npy", type=Path)
    nprq_verify.add_argument("--prove-monotone", action="store_true")
    ssm_compare = sub.add_parser("ssm-compare", help="compare a real diagonal NPZ checkpoint with fixed exact ternarization")
    ssm_compare.add_argument("checkpoint", type=Path)
    ssm_compare.add_argument("input_npy", type=Path)
    args = parser.parse_args(argv)
    root = _root()

    if args.command == "attest":
        try:
            raw = json.loads(args.input.read_text(encoding="utf-8"))
            transcript = raw.get("transcript")
            certificate = raw.get("certificate")
            if not isinstance(transcript, dict) or not isinstance(certificate, str):
                raise ValueError("input must contain transcript and certificate")
            model_root = args.model_root or transcript.get("model_root")
            request_root = args.request_root or transcript.get("request_root")
            if not isinstance(model_root, str) or not isinstance(request_root, str):
                raise ValueError("model_root/request_root must be present in input or supplied")
            receipt = create_receipt(
                source_kind=args.source_kind, transcript=transcript, certificate=certificate,
                model_root=model_root, request_root=request_root,
                arithmetic_mode=args.arithmetic_mode, answer=raw.get("answer"),
            )
            print(json.dumps(receipt.as_dict(), sort_keys=True))
            return 0
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            parser.error(str(exc))

    if args.command == "ssm-compare":
        try:
            import numpy as np
            checkpoint = load_diagonal_checkpoint(args.checkpoint)
            inputs = np.load(args.input_npy, allow_pickle=False)
            print(json.dumps(compare_checkpoint(checkpoint, inputs), sort_keys=True))
            return 0
        except (OSError, TypeError, ValueError, OverflowError) as exc:
            parser.error(str(exc))

    if args.command == "nprq-verify":
        try:
            meta = meta_from_dict(json.loads(args.meta.read_text(encoding="utf-8")))
            if args.prove_monotone:
                if args.source_npy is None:
                    raise ValueError("--prove-monotone requires --source-npy")
                payload = prove_monotone(args.meta.parent, meta, args.source_npy)
                print(json.dumps(payload, sort_keys=True))
                return 0 if payload["monotone_non_increasing"] else 4
            from .nprq import verify_tensor
            verify_tensor(args.meta.parent, meta)
            print(json.dumps({"verified": True, "stages": meta.stages}, sort_keys=True))
            return 0
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            parser.error(str(exc))

    if args.command in ("agent-plan", "agent-run"):
        try:
            limits = FabricLimits(args.max_depth, args.max_nodes, args.quorum,
                                  args.max_new_tokens, args.max_model_calls)
            if args.command == "agent-plan":
                print(json.dumps(plan_as_dict(args.goal, limits), sort_keys=True))
                return 0
            result = RecursiveFabricRuntime(DS4LocalTransport(root), limits).run(args.goal)
            print(json.dumps({
                "status": {-1: "reject", 0: "abstain", 1: "accept"}[int(result.status)],
                "status_trit": int(result.status),
                "answer": result.answer,
                "certificate": result.certificate,
                "transcript": result.transcript,
            }, sort_keys=True))
            return 0 if int(result.status) == 1 else 3
        except (TypeError, ValueError, RuntimeError) as exc:
            parser.error(str(exc))

    if args.command == "ternary-dot":
        result = args.left.dot(args.right)
        print(json.dumps({"dot": result, "trits": len(args.left)}, sort_keys=True))
        return 0

    if args.command == "decide":
        result = gate(
            args.criterion,
            reject_below=args.reject_below,
            accept_at=args.accept_at,
            model_root=args.model_root,
            request_root=args.request_root,
        )
        transcript = {
            "domain": "pocket-ternary-gate-v1",
            "status": int(result.status),
            "score": {"numerator": result.score.numerator, "power_of_three": result.score.exponent},
            "reject_below": {"numerator": result.reject_below.numerator, "power_of_three": result.reject_below.exponent},
            "accept_at": {"numerator": result.accept_at.numerator, "power_of_three": result.accept_at.exponent},
            "model_root": args.model_root, "request_root": args.request_root,
            "evidence_root": result.evidence_root,
        }
        print(json.dumps({
            "status": result.status.name.lower(),
            "status_trit": int(result.status),
            "score": transcript["score"],
            "evidence_root": result.evidence_root,
            "certificate": result.certificate,
            "transcript": transcript,
        }, sort_keys=True))
        return 0

    if args.command == "score":
        result = ordered_score(
            args.level,
            minimum_confidence=args.minimum_confidence,
            model_root=args.model_root,
            request_root=args.request_root,
        )
        transcript = {
            "domain": "pocket-ordered-score-v1",
            "status": int(result.status),
            "level_index": result.level_index,
            "expected_score": {"numerator": result.expected_score.numerator, "denominator": result.expected_score.denominator},
            "confidence": {"numerator": result.confidence.numerator, "denominator": result.confidence.denominator},
            "minimum_confidence": {"numerator": args.minimum_confidence.numerator, "denominator": args.minimum_confidence.denominator},
            "model_root": args.model_root, "request_root": args.request_root,
            "evidence_root": result.evidence_root,
        }
        print(json.dumps({
            "status": result.status.name.lower(),
            "status_trit": int(result.status),
            "level": result.level,
            "level_index": result.level_index,
            "legend": list(result.legend),
            "expected_score": {
                "numerator": result.expected_score.numerator,
                "denominator": result.expected_score.denominator,
            },
            "confidence": {
                "numerator": result.confidence.numerator,
                "denominator": result.confidence.denominator,
            },
            "probabilities": [
                {"numerator": value.numerator, "denominator": value.denominator}
                for value in result.probabilities
            ],
            "evidence_root": result.evidence_root,
            "certificate": result.certificate,
            "transcript": transcript,
        }, sort_keys=True))
        return 0

    if args.command == "model-manifest":
        try:
            _validate_output(args.output, (args.source,))
        except ValueError as exc:
            parser.error(str(exc))
        result = build_manifest(args.source, page_bytes=args.page_bytes)
        result.write(args.output)
        print(json.dumps({
            "model_root": result.model_root,
            "pages": len(result.pages),
            "source_bytes": result.source_bytes,
            "source_sha256": result.source_sha256,
        }, sort_keys=True))
        return 0

    if args.command == "model-analyze":
        manifest_data = ModelManifest.read(args.manifest)
        report = analyze_compression(args.source, manifest_data)
        payload = report.as_dict()
        payload["model_root"] = manifest_data.model_root
        print(json.dumps(payload, sort_keys=True))
        return 0

    if args.command == "model-import":
        manifest_data = ModelManifest.read(args.manifest)
        if args.source.stat().st_size != manifest_data.source_bytes:
            parser.error("source size does not match manifest")
        page_store = ModelPageStore(args.store, manifest_data, args.source)
        materialized = page_store.materialize_all() if args.mode == "static" else 0
        print(json.dumps({
            "mode": args.mode,
            "model_root": manifest_data.model_root,
            "materialized_pages": materialized,
            "total_pages": len(manifest_data.pages),
        }, sort_keys=True))
        return 0

    if args.command == "model-read":
        manifest_data = ModelManifest.read(args.manifest)
        try:
            _validate_output(
                args.output, (args.source, args.manifest), store=args.store
            )
        except ValueError as exc:
            parser.error(str(exc))
        page_store = ModelPageStore(args.store, manifest_data, args.source)
        data = page_store.read_range(args.offset, args.length)
        _atomic_output(args.output, data)
        print(json.dumps({"bytes": len(data), "model_root": manifest_data.model_root}, sort_keys=True))
        return 0

    if args.command == "model-verify-cache":
        manifest_data = ModelManifest.read(args.manifest)
        present, total = ModelPageStore(args.store, manifest_data).verify_cached()
        print(json.dumps({
            "model_root": manifest_data.model_root, "verified_pages": present, "total_pages": total
        }, sort_keys=True))
        return 0

    if args.command == "init-store":
        store = _store(root)
        store.initialize(DEFAULT_EXPERTS)
        print(f"initialized {len(store.records)} experts at {store.root}")
        return 0

    if args.command in ("aegis-c2r-check", "aegis-c2r-translate"):
        try:
            translator = AegisC2R()
            if args.command == "aegis-c2r-check":
                print(translator.check(args.source).strip())
            else:
                print(json.dumps(translator.translate(args.source, args.output_dir).as_dict(), sort_keys=True))
            return 0
        except (AegisBoundaryError, FileNotFoundError, ValueError) as exc:
            print(f"AEGIS_C2R_ERROR: {exc}", file=sys.stderr)
            return 2

    if args.command in ("aegis-doctor", "aegis-run"):
        try:
            runtime = AegisRuntime(timeout=getattr(args, "timeout", 30.0))
            if args.command == "aegis-doctor":
                tool_dir = runtime.prepare()
                print(json.dumps({"aegis_version": "2.4.3", "installed_bin": str(tool_dir),
                                  "status": "verified and installed"}, sort_keys=True))
            else:
                print(json.dumps(runtime.execute(args.source).as_dict(), sort_keys=True))
            return 0
        except (AegisBoundaryError, FileNotFoundError, ValueError) as exc:
            print(f"AEGIS_ERROR: {exc}", file=sys.stderr)
            return 2

    if args.command == "doctor":
        store = _store(root)
        report = {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "root": str(root),
            "store_exists": store.index_path.exists(),
            "experts": len(store.records),
            "models": [str(p) for p in sorted((root / "models").glob("*"))] if (root / "models").exists() else [],
        }
        print(json.dumps(report, indent=2))
        return 0

    if args.command in ("chat", "serve"):
        transport = DS4LocalTransport(root)
        service = LumusARHService(transport=transport, max_new_tokens=args.max_new_tokens)
        if args.command == "serve":
            server = serve_loopback(service, port=args.port)
            print(f"Pocket Rocket listening on http://127.0.0.1:{args.port} (/ask, /reset)")
            server.serve_forever()
            return 0
        status, response = service.ask({"question": args.text})
        print(response.get("answer", ""))
        return 0 if status == 200 else 2

    store = _store(root)
    if not store.records:
        parser.error("expert store is missing; run: neuro-inverse init-store")

    if args.command in ("route", "route-decide"):
        top_k = args.top_k if args.command == "route" else min(256, len(store.records))
        routes = GoldenHammingRouter(store.records).route(
            args.text, top_k=top_k, domain=args.domain, task_kind=args.task_kind
        )
        if args.command == "route-decide":
            if len(routes) < 2:
                parser.error("route-decide needs at least two compatible experts")
            if args.minimum_margin < 0:
                parser.error("--minimum-margin must be non-negative")
            decision = choose(
                [Choice(route.expert.expert_id, Triadic(256 - route.distance)) for route in routes],
                minimum_margin=Triadic(args.minimum_margin),
            )
            request_root = hashlib.sha256(args.text.encode("utf-8")).hexdigest()
            model_root = hashlib.sha256(store.index_path.read_bytes()).hexdigest()
            transcript = {
                "domain": "pocket-route-choice-v1",
                "status": int(decision.status),
                "choice": decision.choice,
                "margin": {
                    "numerator": decision.margin.numerator,
                    "power_of_three": decision.margin.exponent,
                },
                "minimum_margin": args.minimum_margin,
                "model_root": model_root,
                "request_root": request_root,
                "routes": [
                    {"expert_id": route.expert.expert_id, "distance": route.distance}
                    for route in routes
                ],
            }
            certificate = hashlib.sha256(
                json.dumps(transcript, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            transcript["status_name"] = decision.status.name.lower()
            transcript["certificate"] = certificate
            print(json.dumps(transcript, sort_keys=True))
            return 0
        print(json.dumps([{"expert_id": r.expert.expert_id, "distance": r.distance} for r in routes], indent=2))
        return 0

    parser.error("unsupported command")


if __name__ == "__main__":
    raise SystemExit(main())
