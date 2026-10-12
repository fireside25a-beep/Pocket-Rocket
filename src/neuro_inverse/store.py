from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .codes import code_hex, parse_code, simhash256
from .contracts import Compatibility, Contract


@dataclass(frozen=True)
class ExpertRecord:
    expert_id: str
    description: str
    code: bytes
    payload_path: str
    payload_sha256: str
    payload_size: int
    compatibility: Compatibility
    contract: Contract


class ExpertStore:
    def __init__(self, root: Path, cache_bytes: int = 64 * 1024 * 1024) -> None:
        self.root = root
        self.index_path = root / "index.json"
        self.payload_dir = root / "payloads"
        self.cache_bytes = cache_bytes
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._cache_size = 0
        self.records: tuple[ExpertRecord, ...] = ()
        if self.index_path.exists():
            self.reload()

    def reload(self) -> None:
        raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        seen: set[str] = set()
        records: list[ExpertRecord] = []
        for item in raw["experts"]:
            expert_id = item["expert_id"]
            if expert_id in seen:
                raise ValueError(f"Duplicate expert ID: {expert_id}")
            seen.add(expert_id)
            records.append(ExpertRecord(
                expert_id=expert_id,
                description=item["description"],
                code=parse_code(item["code"]),
                payload_path=item["payload_path"],
                payload_sha256=item["payload_sha256"],
                payload_size=int(item["payload_size"]),
                compatibility=Compatibility(**item["compatibility"]),
                contract=Contract(**item["contract"]),
            ))
        self.records = tuple(sorted(records, key=lambda r: r.expert_id))

    def initialize(self, definitions: list[dict[str, Any]]) -> None:
        self.payload_dir.mkdir(parents=True, exist_ok=True)
        index: list[dict[str, Any]] = []
        for definition in sorted(definitions, key=lambda d: d["expert_id"]):
            expert_id = definition["expert_id"]
            payload = definition["payload"].encode("utf-8")
            payload_name = f"{expert_id}.txt"
            payload_path = self.payload_dir / payload_name
            payload_path.write_bytes(payload)
            description = definition["description"]
            contract = Contract(**definition.get("contract", {}))
            compatibility = Compatibility(**definition.get("compatibility", {}))
            index.append({
                "expert_id": expert_id,
                "description": description,
                "code": code_hex(simhash256(description)),
                "payload_path": f"payloads/{payload_name}",
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
                "payload_size": len(payload),
                "compatibility": asdict(compatibility),
                "contract": asdict(contract),
            })
        document = {"format": 1, "experts": index}
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.reload()

    def load_payload(self, record: ExpertRecord) -> str:
        if record.expert_id in self._cache:
            data = self._cache.pop(record.expert_id)
            self._cache[record.expert_id] = data
            return data.decode("utf-8")
        path = (self.root / record.payload_path).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Payload path escapes store")
        data = path.read_bytes()
        if len(data) != record.payload_size:
            raise ValueError(f"Payload size mismatch: {record.expert_id}")
        if hashlib.sha256(data).hexdigest() != record.payload_sha256:
            raise ValueError(f"Payload hash mismatch: {record.expert_id}")
        if len(data) <= self.cache_bytes:
            while self._cache and self._cache_size + len(data) > self.cache_bytes:
                _, evicted = self._cache.popitem(last=False)
                self._cache_size -= len(evicted)
            self._cache[record.expert_id] = data
            self._cache_size += len(data)
        return data.decode("utf-8")

