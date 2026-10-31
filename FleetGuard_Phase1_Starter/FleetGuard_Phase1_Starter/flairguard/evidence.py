"""Strict evidence serialization. Existing run outputs are never overwritten."""
from pathlib import Path
import hashlib
import json
import math


def jsonable(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": str(value)}
    return value


def canonical(value):
    return json.dumps(jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(jsonable(value), stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def load_protocol(path, train=None):
    p = json.loads(Path(path).read_text(encoding="utf-8"))
    if p.get("protocol_id") != "phase-a-fd001-v1" or p.get("subset") != "FD001":
        raise ValueError("Only the frozen Phase A FD001 v1 protocol is supported")
    roles = p["partitions"]
    sets = [set(roles[k]) for k in ("fit", "calibration", "evaluation")]
    if [len(s) for s in sets] != [60, 20, 20] or set.union(*sets) != set(range(1, 101)):
        raise ValueError("Partition membership/count mismatch")
    if any(sets[i] & sets[j] for i in range(3) for j in range(i)):
        raise ValueError("Engine leakage across partitions")
    if len(p["cv_folds"]) != 5 or sorted(x for f in p["cv_folds"] for x in f) != sorted(sets[0]):
        raise ValueError("CV must cover fit engines exactly once")
    if set(p["endpoint_cycles"]) != {str(x) for x in range(1, 101)}:
        raise ValueError("Missing frozen endpoint cutoff")
    if train is not None and file_sha(train) != p["data_sha256"]:
        raise ValueError("Dataset hash differs from frozen protocol")
    return p
