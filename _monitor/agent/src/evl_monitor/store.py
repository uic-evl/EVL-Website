"""SQLite history store: tiered rollups with fixed row budgets.

Only the open 10 s bucket lives in memory (see engine.py). Every coarser tier is
computed from stored rows of the next finer tier, inside the same transaction that
writes the finer rows, so a restart loses at most that one open bucket.
"""

from __future__ import annotations

import logging
import math
import os
import sqlite3
import threading
from dataclasses import dataclass

from . import registry
from .tiers import Tier, signature

log = logging.getLogger(__name__)

SCHEMA_VERSION = "1"

DDL = """
CREATE TABLE IF NOT EXISTS series(id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS pts(
  tier INTEGER NOT NULL, sid INTEGER NOT NULL, t INTEGER NOT NULL,
  n INTEGER NOT NULL, mean REAL NOT NULL, mx REAL NOT NULL, mn REAL NOT NULL,
  PRIMARY KEY(tier, sid, t)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS usage(
  day INTEGER NOT NULL, user TEXT NOT NULL, container TEXT NOT NULL,
  gpu_s REAL NOT NULL, mem_gib_s REAL NOT NULL,
  PRIMARY KEY(day, user, container)
) WITHOUT ROWID;
"""

DAY = 86400
USAGE_DAYS = 400
USAGE_ROWS_PER_DAY = 500


@dataclass
class Acc:
    """Running aggregate of one series inside one bucket."""

    n: int = 0
    total: float = 0.0
    mx: float = -math.inf
    mn: float = math.inf

    def add(self, v: float) -> None:
        self.n += 1
        self.total += v
        if v > self.mx:
            self.mx = v
        if v < self.mn:
            self.mn = v


class Store:
    def __init__(self, path: str, tiers: tuple[Tier, ...]):
        self.path = path
        self.tiers = tiers
        self._lock = threading.Lock()
        self._sids: dict[str, int] = {}
        self.db = self._open()

    # setup ---------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA journal_size_limit=4194304")
        db.execute("PRAGMA temp_store=MEMORY")
        return db

    def _open(self) -> sqlite3.Connection:
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        db = None
        try:
            db = self._connect()
            ok = db.execute("PRAGMA quick_check").fetchone()[0]
            if ok != "ok":
                raise sqlite3.DatabaseError(ok)
        except sqlite3.DatabaseError as exc:
            if db is not None:
                db.close()
            if self.path == ":memory:":
                raise
            log.warning("history database is corrupt (%s); keeping one copy and starting fresh", exc)
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(self.path + suffix):
                    os.replace(self.path + suffix, self.path + ".corrupt" + suffix)
            db = self._connect()
        db.executescript(DDL)
        self.db = db
        self._check_meta()
        self._sids = {k: i for i, k in db.execute("SELECT id, key FROM series")}
        return db

    def _check_meta(self) -> None:
        meta = dict(self.db.execute("SELECT k, v FROM meta"))
        if meta.get("schema", SCHEMA_VERSION) != SCHEMA_VERSION:
            log.warning("history schema changed; starting fresh")
            self.db.executescript("DELETE FROM pts; DELETE FROM series; DELETE FROM meta;")
            meta = {}
        old = meta.get("tiers", "").split(",") if meta.get("tiers") else []
        new = signature(self.tiers).split(",")
        for k, step in enumerate(new):
            if k < len(old) and old[k] != step:
                log.warning("tier %s step changed; dropping its rows", self.tiers[k].range)
                self.db.execute("DELETE FROM pts WHERE tier >= ?", (k,))
                self.db.execute("DELETE FROM meta WHERE k LIKE 'next_%'")
                break
        self._set_meta("schema", SCHEMA_VERSION)
        self._set_meta("tiers", signature(self.tiers))

    def _set_meta(self, k: str, v: object) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES(?, ?)", (k, str(v)))

    def _meta_int(self, k: str) -> int | None:
        row = self.db.execute("SELECT v FROM meta WHERE k = ?", (k,)).fetchone()
        return int(row[0]) if row else None

    def close(self) -> None:
        with self._lock:
            try:
                self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                self.db.close()

    # series ids ------------------------------------------------------------

    def _sid(self, key: str) -> int | None:
        sid = self._sids.get(key)
        if sid is not None:
            return sid
        if not registry.is_valid_key(key) or len(self._sids) >= registry.MAX_SERIES:
            return None
        cur = self.db.execute("INSERT OR IGNORE INTO series(key) VALUES(?)", (key,))
        if cur.rowcount:
            sid = cur.lastrowid
        else:
            sid = self.db.execute("SELECT id FROM series WHERE key = ?", (key,)).fetchone()[0]
        self._sids[key] = sid
        return sid

    # writes ----------------------------------------------------------------

    def last_bucket(self) -> int | None:
        """Start of the newest stored finest bucket."""
        return self._meta_int("last_a")

    def commit_bucket(self, t: int, accs: dict[str, Acc], fine_end: int) -> set[int]:
        """Store one closed finest bucket, roll up every tier through `fine_end`, prune.

        Returns the tier indexes whose closed-bucket window moved.
        """
        with self._lock:
            self.db.execute("BEGIN")
            try:
                rows = []
                for key, a in accs.items():
                    if a.n == 0:
                        continue
                    sid = self._sid(key)
                    if sid is None:
                        continue
                    rows.append((0, sid, t, a.n, a.total / a.n, a.mx, a.mn))
                self.db.executemany(
                    "INSERT OR REPLACE INTO pts(tier, sid, t, n, mean, mx, mn) VALUES(?,?,?,?,?,?,?)",
                    rows,
                )
                self._set_meta("last_a", t)
                changed = self._cascade(fine_end)
                self._prune(fine_end)
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        return changed

    def catch_up(self, fine_end: int) -> set[int]:
        """Roll up whatever finer rows a previous run left behind, then prune."""
        with self._lock:
            self.db.execute("BEGIN")
            try:
                changed = self._cascade(fine_end)
                self._prune(fine_end)
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        return changed

    def _cascade(self, fine_end: int) -> set[int]:
        changed = {0}
        for tier in self.tiers[1:]:
            k, step = tier.index, tier.step
            hi = (fine_end // step) * step  # windows starting below hi are closed
            lo = self._meta_int(f"next_{k}")
            if lo is None:
                row = self.db.execute(
                    "SELECT MIN(t) FROM pts WHERE tier = ?", (k - 1,)
                ).fetchone()
                if row[0] is None:
                    continue
                lo = (row[0] // step) * step
            if hi <= lo:
                continue
            cur = self.db.execute(
                """
                INSERT OR REPLACE INTO pts(tier, sid, t, n, mean, mx, mn)
                SELECT ?, sid, (t / ?) * ?, SUM(n), SUM(mean * n) / SUM(n), MAX(mx), MIN(mn)
                FROM pts WHERE tier = ? AND t >= ? AND t < ?
                GROUP BY sid, (t / ?) * ?
                """,
                (k, step, step, k - 1, lo, hi, step, step),
            )
            self._set_meta(f"next_{k}", hi)
            if cur.rowcount:
                changed.add(k)
        return changed

    def _prune(self, fine_end: int) -> None:
        for tier in self.tiers:
            cutoff = (fine_end // tier.step) * tier.step - tier.keep * tier.step
            self.db.execute("DELETE FROM pts WHERE tier = ? AND t < ?", (tier.index, cutoff))

    def load_rows(self, rows: list[tuple], fine_end: int, last_a: int) -> None:
        """Bulk insert (tier, key, t, n, mean, mx, mn) rows; used by the fake backfill."""
        with self._lock:
            self.db.execute("BEGIN")
            try:
                out = []
                for tier, key, t, n, mean, mx, mn in rows:
                    sid = self._sid(key)
                    if sid is not None:
                        out.append((tier, sid, t, n, mean, mx, mn))
                self.db.executemany(
                    "INSERT OR REPLACE INTO pts(tier, sid, t, n, mean, mx, mn) VALUES(?,?,?,?,?,?,?)", out)
                for tier in self.tiers[1:]:
                    self._set_meta(f"next_{tier.index}", (fine_end // tier.step) * tier.step)
                self._set_meta("last_a", last_a)
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def checkpoint(self) -> None:
        with self._lock:
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # reads -----------------------------------------------------------------

    def window(self, tier: Tier, end: int, n: int) -> tuple[int, dict[str, tuple[list, list, list]]]:
        """Return (start, {key: (means, maxes, mins)}) for the n closed buckets before `end`."""
        hi = (end // tier.step) * tier.step
        start = hi - n * tier.step
        keys = {i: k for k, i in self._sids.items()}
        out: dict[str, tuple[list, list, list]] = {}
        with self._lock:
            cur = self.db.execute(
                "SELECT sid, t, mean, mx, mn FROM pts WHERE tier = ? AND t >= ? AND t < ?",
                (tier.index, start, hi),
            )
            for sid, t, mean, mx, mn in cur:
                key = keys.get(sid)
                if key is None:
                    continue
                if key not in out:
                    out[key] = ([None] * n, [None] * n, [None] * n)
                i = (t - start) // tier.step
                out[key][0][i] = mean
                out[key][1][i] = mx
                out[key][2][i] = mn
        return start, out

    # per-user GPU usage ------------------------------------------------------

    def add_usage(self, rows: dict[tuple[int, str, str], tuple[float, float]], now: float) -> None:
        """Add GPU-seconds and GPU-memory-GiB-seconds to (day, user, container) rows."""
        if not rows:
            return
        with self._lock:
            self.db.execute("BEGIN")
            try:
                counts = dict(self.db.execute(
                    "SELECT day, COUNT(*) FROM usage WHERE day >= ? GROUP BY day",
                    (min(k[0] for k in rows),)))
                for (day, user, container), (gpu_s, mem_s) in rows.items():
                    exists = self.db.execute(
                        "SELECT 1 FROM usage WHERE day = ? AND user = ? AND container = ?",
                        (day, user, container)).fetchone()
                    if not exists:
                        if counts.get(day, 0) >= USAGE_ROWS_PER_DAY:
                            continue
                        counts[day] = counts.get(day, 0) + 1
                    self.db.execute(
                        """INSERT INTO usage(day, user, container, gpu_s, mem_gib_s) VALUES(?,?,?,?,?)
                           ON CONFLICT(day, user, container) DO UPDATE SET
                           gpu_s = gpu_s + excluded.gpu_s, mem_gib_s = mem_gib_s + excluded.mem_gib_s""",
                        (day, user, container, gpu_s, mem_s))
                cutoff = (int(now) // DAY) * DAY - USAGE_DAYS * DAY
                self.db.execute("DELETE FROM usage WHERE day < ?", (cutoff,))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def daily_rows(self, tier: Tier, since: int) -> list[tuple[str, int, int, float]]:
        """(key, t, n, mean) of the series daily.json summarizes, from `tier`, since `since`."""
        with self._lock:
            return self.db.execute(
                """SELECT s.key, p.t, p.n, p.mean FROM pts p JOIN series s ON s.id = p.sid
                   WHERE p.tier = ? AND p.t >= ? AND (
                     s.key IN ('host.cpu_pct', 'host.mem_pct', 'host.load1')
                     OR s.key GLOB 'gpu.*.util_pct' OR s.key GLOB 'gpu.*.mem_pct')""",
                (tier.index, since)).fetchall()

    def usage(self) -> list[tuple[int, str, str, float, float]]:
        with self._lock:
            return self.db.execute(
                "SELECT day, user, container, gpu_s, mem_gib_s FROM usage ORDER BY day, gpu_s DESC"
            ).fetchall()

    def stats(self) -> dict:
        with self._lock:
            per_tier = dict(self.db.execute("SELECT tier, COUNT(*) FROM pts GROUP BY tier"))
            series = self.db.execute("SELECT COUNT(*) FROM series").fetchone()[0]
            usage_rows = self.db.execute("SELECT COUNT(*) FROM usage").fetchone()[0]
            page_count = self.db.execute("PRAGMA page_count").fetchone()[0]
            freelist = self.db.execute("PRAGMA freelist_count").fetchone()[0]
            page_size = self.db.execute("PRAGMA page_size").fetchone()[0]
        sizes = {}
        for suffix in ("", "-wal"):
            p = self.path + suffix
            sizes["db" if not suffix else "wal"] = os.path.getsize(p) if os.path.exists(p) else 0
        return {
            "rows": {self.tiers[t].range: c for t, c in sorted(per_tier.items())},
            "series": series,
            "usage_rows": usage_rows,
            "page_count": page_count,
            "freelist": freelist,
            "page_size": page_size,
            "db_bytes": sizes["db"],
            "wal_bytes": sizes["wal"],
        }
