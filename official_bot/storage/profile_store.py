"""SQLite-backed stable-ID opponent profiles."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS opponent_profiles (
    opponent_id TEXT PRIMARY KEY,
    name TEXT,
    games INTEGER NOT NULL DEFAULT 0,
    attack_ema REAL NOT NULL DEFAULT 50,
    attack_peak REAL NOT NULL DEFAULT 50,
    attack_samples INTEGER NOT NULL DEFAULT 0,
    contacts INTEGER NOT NULL DEFAULT 0,
    last_seen_at TEXT NOT NULL
)
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProfileStore:
    def __init__(self, path):
        self.path = Path(path)

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=3)
        connection.row_factory = sqlite3.Row
        connection.execute(SCHEMA)
        return connection

    def load_many(self, opponent_ids):
        identifiers = sorted({str(value) for value in opponent_ids if value is not None})
        if not identifiers or not self.path.exists():
            return {}
        placeholders = ",".join("?" for _ in identifiers)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM opponent_profiles WHERE opponent_id IN ({placeholders})",
                identifiers,
            ).fetchall()
        return {row["opponent_id"]: dict(row) for row in rows}

    def save_many(self, profiles):
        profiles = list(profiles)
        if not profiles:
            return
        with self._connect() as connection:
            for profile in profiles:
                connection.execute(
                    """
                    INSERT INTO opponent_profiles (
                        opponent_id, name, games, attack_ema, attack_peak,
                        attack_samples, contacts, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(opponent_id) DO UPDATE SET
                        name=excluded.name,
                        games=excluded.games,
                        attack_ema=excluded.attack_ema,
                        attack_peak=excluded.attack_peak,
                        attack_samples=excluded.attack_samples,
                        contacts=excluded.contacts,
                        last_seen_at=excluded.last_seen_at
                    """,
                    (
                        str(profile["opponent_id"]),
                        profile.get("name"),
                        int(profile.get("games") or 0),
                        float(profile.get("attack_ema") or 50),
                        float(profile.get("attack_peak") or 50),
                        int(profile.get("attack_samples") or 0),
                        int(profile.get("contacts") or 0),
                        profile.get("last_seen_at") or _now(),
                    ),
                )

    def count(self):
        if not self.path.exists():
            return 0
        with self._connect() as connection:
            return int(connection.execute(
                "SELECT COUNT(*) FROM opponent_profiles").fetchone()[0])
