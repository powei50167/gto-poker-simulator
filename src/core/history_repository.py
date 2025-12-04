import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional


class HistoryRepository:
    """負責將牌局歷史保存到 SQLite，並提供查詢功能。"""

    def __init__(self, db_path: str | Path = Path("data/game_history.db")):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hand_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    state_json TEXT NOT NULL
                )
                """
            )

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def save_hand(self, state: Dict[str, Any]) -> int:
        """儲存牌局並返回對應的紀錄 ID。"""

        payload = json.dumps(state, ensure_ascii=False)
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO hand_history (created_at, state_json) VALUES (datetime('now'), ?)",
                (payload,),
            )
            return int(cursor.lastrowid)

    def list_hands(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, state_json
                FROM hand_history
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_hand(self, hand_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, created_at, state_json FROM hand_history WHERE id = ?",
                (hand_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def _row_to_record(self, row: sqlite3.Row | None) -> Dict[str, Any]:
        if not row:
            return {}
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "state": json.loads(row["state_json"]),
        }
