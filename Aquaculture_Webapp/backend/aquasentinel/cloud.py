"""Optional Google Cloud persistence: Firestore for the findings, Cloud Storage for camera frames and report PDFs.

SQLite stays the working store (fast, and it holds the high-volume readings). When FIRESTORE_ENABLED is set,
every write to the finding tables (anomalies, diagnoses, missions, reports, alerts) is copied to Firestore, and a
fresh container with an empty database restores them on start. Cloud Run scales to zero when idle, so without this
the findings would vanish with the container. When GCS_BUCKET is set, camera frames and PDFs are kept there too.

Writes go through one background thread, so the boat loop never waits on the network and writes stay in order.
A failed cloud write is logged and skipped: the dashboard keeps working on SQLite alone.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from . import config

logger = logging.getLogger(__name__)

MIRRORED = ("anomalies", "diagnoses", "missions", "reports", "alerts")


class CloudMirror:
    def __init__(self, firestore_client=None, bucket=None, prefix: str = "aquasentinel"):
        self.db = firestore_client
        self.bucket = bucket
        self.prefix = prefix
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cloud-mirror")

    # ------------------------------------------------------------------ Firestore
    def _col(self, table: str):
        return self.db.collection(f"{self.prefix}_{table}")

    def put(self, table: str, row: dict) -> None:
        """Copy one row (as returned by Store.get). Stored as a JSON string: Firestore rejects nested arrays."""
        if self.db is None or table not in MIRRORED or not row:
            return
        doc = {"id": row["id"], "row": json.dumps(row, default=str, ensure_ascii=False)}
        self._submit(lambda: self._col(table).document(str(row["id"])).set(doc))

    def load(self, table: str) -> list[dict]:
        """All rows of one table, oldest first. Called once at start, before the loop runs."""
        if self.db is None:
            return []
        try:
            rows = [json.loads(d.to_dict()["row"]) for d in self._col(table).stream()]
        except Exception:
            logger.exception("Could not restore %s from Firestore", table)
            return []
        return sorted(rows, key=lambda r: r["id"])

    def clear(self) -> None:
        """Delete every mirrored row (the dashboard's reset)."""
        if self.db is None:
            return

        def wipe():
            for t in MIRRORED:
                for d in self._col(t).stream():
                    d.reference.delete()
        self._submit(wipe)

    # ------------------------------------------------------------------ Cloud Storage
    def put_blob(self, name: str, data: bytes, content_type: str) -> None:
        if self.bucket is None:
            return
        self._submit(lambda: self.bucket.blob(f"{self.prefix}/{name}").upload_from_string(data, content_type=content_type))

    def get_blob(self, name: str) -> bytes | None:
        if self.bucket is None:
            return None
        try:
            blob = self.bucket.blob(f"{self.prefix}/{name}")
            return blob.download_as_bytes() if blob.exists() else None
        except Exception:
            logger.exception("Could not read %s from Cloud Storage", name)
            return None

    # ------------------------------------------------------------------ plumbing
    def _submit(self, fn) -> None:
        def run():
            try:
                fn()
            except Exception:
                logger.exception("Cloud write failed; SQLite still has the data")
        self._pool.submit(run)

    def flush(self) -> None:
        """Wait for queued writes (tests and shutdown)."""
        self._pool.submit(lambda: None).result()


def from_env() -> CloudMirror | None:
    """The mirror described by .env, or None when neither Firestore nor a bucket is configured."""
    if not (config.FIRESTORE_ENABLED or config.GCS_BUCKET):
        return None
    db = bucket = None
    if config.FIRESTORE_ENABLED:
        from google.cloud import firestore
        db = firestore.Client(project=config.GOOGLE_CLOUD_PROJECT or None, database=config.FIRESTORE_DATABASE)
    if config.GCS_BUCKET:
        from google.cloud import storage
        bucket = storage.Client(project=config.GOOGLE_CLOUD_PROJECT or None).bucket(config.GCS_BUCKET)
    logger.info("Cloud persistence: Firestore %s, Cloud Storage %s",
                "on" if db else "off", f"gs://{config.GCS_BUCKET}" if bucket else "off")
    return CloudMirror(db, bucket)
