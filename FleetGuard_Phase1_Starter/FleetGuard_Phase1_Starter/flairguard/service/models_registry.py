"""Hash-verified, transactional model releases with durable rollback history."""
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
import joblib
from .config import settings
from flairguard.evidence import file_sha


class ModelRegistry:
    def __init__(self, state_dir=None):
        self.state_dir = Path(state_dir or settings.db_path.parent / "model_governance")
        self._bundles = {}
        self._metadata = {}
        self._loaded = False
        self._lock = threading.RLock()

    @contextmanager
    def _connect(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.state_dir / "registry.sqlite", timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA synchronous=FULL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS releases (
          id TEXT PRIMARY KEY, dataset TEXT NOT NULL, artifact TEXT NOT NULL,
          sha256 TEXT NOT NULL, metadata TEXT NOT NULL, previous TEXT);
        CREATE TABLE IF NOT EXISTS active (dataset TEXT PRIMARY KEY, release_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS history (
          seq INTEGER PRIMARY KEY, dataset TEXT, operation TEXT, release_id TEXT,
          created TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        try:
            with c:
                yield c
        finally:
            c.close()

    def _register(self, c, ds, bundle, meta, previous=None):
        release = uuid.uuid4().hex
        path = self.state_dir / (release + ".joblib")
        joblib.dump(bundle, path)
        # Close and fsync the immutable artifact before committing its pointer.
        import os
        with path.open("r+b") as stream:
            os.fsync(stream.fileno())
        if os.name != "nt":
            directory = os.open(self.state_dir, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        sha = file_sha(path)
        if file_sha(path) != sha:
            raise RuntimeError("Artifact changed while registering")
        metadata = dict(meta)
        metadata["provenance"] = dict(metadata.get("provenance", {}),
                                      sha256=sha, release_id=release,
                                      artifact_path=path.name)
        c.execute("INSERT INTO releases VALUES (?,?,?,?,?,?)",
                  (release, ds, path.name, sha, json.dumps(metadata), previous))
        return release

    def load_models(self):
        with self._lock, self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            for ds, path, kind in [
                ("FD001", settings.fd001_bundle_path, "Phase A saved predictor"),
                ("FD002", settings.fd002_bundle_path, "Phase B saved predictor"),
            ]:
                if not c.execute("SELECT 1 FROM active WHERE dataset=?", (ds,)).fetchone() and path.is_file():
                    bundle = joblib.load(path)
                    meta = dict(dataset=ds, model_id=bundle["model_id"], model_type=kind,
                                champion=True, features_count=len(bundle.get("features", [])) or
                                len(bundle["models"][bundle["selected"]].columns_),
                                target_cap=bundle.get("rul_cap", 125), metrics={},
                                provenance=dict(source_artifact=str(path), source_sha256=file_sha(path),
                                                metrics_status="Unavailable in serving metadata; consult verified evidence"))
                    release = self._register(c, ds, bundle, meta)
                    c.execute("INSERT INTO active VALUES (?,?)", (ds, release))
                    c.execute("INSERT INTO history(dataset,operation,release_id) VALUES (?,?,?)", (ds,"INITIALIZE",release))
            self._loaded = True
        self._refresh()

    def _refresh(self):
        with self._lock, self._connect() as c:
            rows = c.execute("SELECT r.* FROM releases r JOIN active a ON a.release_id=r.id").fetchall()
            bundles, metadata = {}, {}
            for row in rows:
                path = self.state_dir / row["artifact"]
                if file_sha(path) != row["sha256"]:
                    raise RuntimeError("Active artifact hash mismatch: " + row["dataset"])
                old = self._metadata.get(row["dataset"], {}).get("provenance", {}).get("release_id")
                bundles[row["dataset"]] = self._bundles[row["dataset"]] if old == row["id"] else joblib.load(path)
                bundles[row["dataset"]]["artifact_sha256"] = row["sha256"]
                metadata[row["dataset"]] = json.loads(row["metadata"])
            self._bundles, self._metadata = bundles, metadata

    def get_bundle(self, dataset):
        if not self._loaded:
            self.load_models()
        self._refresh()
        return self._bundles[dataset.upper()]

    def get_metadata(self, dataset):
        self.get_bundle(dataset)
        return self._metadata[dataset.upper()]

    def get_release_bundle(self, dataset, release_id):
        """Pin replay to immutable artifact even after a champion change or restart."""
        with self._connect() as c:
            row = c.execute("SELECT * FROM releases WHERE id=? AND dataset=?", (release_id,dataset.upper())).fetchone()
            if row is None:
                raise ValueError("Pinned model release unavailable")
            path = self.state_dir / row['artifact']
            if file_sha(path) != row['sha256']:
                raise RuntimeError("Pinned model artifact hash mismatch")
            bundle = joblib.load(path)
            bundle['artifact_sha256'] = row['sha256']
            return bundle

    def list_models(self):
        if not self._loaded:
            self.load_models()
        self._refresh()
        return self._metadata.copy()

    def promote_challenger(self, dataset, new_bundle, metadata, expected_release=None):
        ds = dataset.upper()
        if not self._loaded:
            self.load_models()
        with self._lock, self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            prior = c.execute("SELECT release_id FROM active WHERE dataset=?", (ds,)).fetchone()
            previous = prior[0] if prior else None
            if expected_release is not None and previous != expected_release:
                raise RuntimeError("Champion changed during evaluation; promotion blocked")
            release = self._register(c, ds, new_bundle, metadata, previous)
            c.execute("INSERT OR REPLACE INTO active VALUES (?,?)", (ds, release))
            c.execute("INSERT INTO history(dataset,operation,release_id) VALUES (?,?,?)", (ds,"PROMOTE",release))
        self._refresh()

    def has_rollback(self, dataset):
        if not self._loaded:
            self.load_models()
        with self._connect() as c:
            row = c.execute("SELECT r.previous FROM releases r JOIN active a ON a.release_id=r.id WHERE a.dataset=?", (dataset.upper(),)).fetchone()
            return bool(row and row[0])

    def rollback_champion(self, dataset):
        ds = dataset.upper()
        with self._lock, self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT r.previous FROM releases r JOIN active a ON a.release_id=r.id WHERE a.dataset=?", (ds,)).fetchone()
            if not row or not row[0]:
                raise ValueError("No previous champion version available for rollback on " + ds)
            previous = c.execute("SELECT * FROM releases WHERE id=?", (row[0],)).fetchone()
            if file_sha(self.state_dir / previous["artifact"]) != previous["sha256"]:
                raise RuntimeError("Rollback artifact hash mismatch")
            c.execute("UPDATE active SET release_id=? WHERE dataset=?", (row[0], ds))
            c.execute("INSERT INTO history(dataset,operation,release_id) VALUES (?,?,?)", (ds,"ROLLBACK",row[0]))
        self._refresh()
        meta = self._metadata[ds]
        return dict(status="ROLLED_BACK", dataset=ds, active_model_id=meta["model_id"], model_type=meta["model_type"], metrics=meta["metrics"])


model_registry = ModelRegistry()
