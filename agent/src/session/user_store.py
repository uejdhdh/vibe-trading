"""Simple file-backed user store for multi-user session isolation."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from pathlib import Path


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


class UserStore:
    """File-backed user registry with password hashing and token management."""

    def __init__(self, base_dir: Path) -> None:
        self._dir = base_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._users_path = self._dir / "users.json"
        self._tokens_path = self._dir / "tokens.json"
        self._secret_path = self._dir / ".secret"
        self._users: dict[str, dict] = self._load_json(self._users_path)
        self._tokens: dict[str, str] = self._load_json(self._tokens_path)
        self._secret = self._load_or_create_secret()

    @property
    def secret(self) -> str:
        return self._secret

    # ---- Users ----

    def register(self, username: str, password: str) -> tuple[str, str]:
        """Register a new user. Returns (user_id, token). Raises on failure."""
        username = username.strip().lower()
        if not username:
            raise ValueError("用户名不能为空")
        if len(username) < 2:
            raise ValueError("用户名至少2个字符")
        if len(password) < 4:
            raise ValueError("密码至少4个字符")
        if username in self._users:
            raise ValueError("用户名已被占用")
        user_id = uuid.uuid4().hex[:16]
        salt = secrets.token_hex(8)
        self._users[username] = {
            "user_id": user_id,
            "password_hash": _hash_password(password, salt),
            "salt": salt,
            "created_at": self._now(),
        }
        self._save_users()
        token = self._make_token(user_id)
        return user_id, token

    def login(self, username: str, password: str) -> str | None:
        """Login and return a token, or None."""
        username = username.strip().lower()
        entry = self._users.get(username)
        if not entry:
            return None
        expected = _hash_password(password, entry["salt"])
        if not secrets.compare_digest(expected, entry["password_hash"]):
            return None
        return self._make_token(entry["user_id"])

    def user_id_from_token(self, token: str) -> str | None:
        """Validate token and return user_id, or None."""
        if not token:
            return None
        cached = self._tokens.get(token)
        if cached:
            return cached
        try:
            payload = token.split(".")[0]
            user_id, sig = payload.split(":", 1)
            expected = self._sign(user_id)
            if secrets.compare_digest(sig, expected):
                self._tokens[token] = user_id
                self._save_tokens()
                return user_id
        except (ValueError, IndexError):
            pass
        return None

    def user_count(self) -> int:
        return len(self._users)

    # ---- Helpers ----

    def _make_token(self, user_id: str) -> str:
        sig = self._sign(user_id)
        token = f"{user_id}:{sig}.{secrets.token_hex(8)}"
        self._tokens[token] = user_id
        self._save_tokens()
        return token

    def _sign(self, user_id: str) -> str:
        return hashlib.sha256(f"{user_id}:{self._secret}".encode()).hexdigest()[:32]

    def _load_or_create_secret(self) -> str:
        if self._secret_path.exists():
            return self._secret_path.read_text().strip()
        s = secrets.token_hex(32)
        self._secret_path.write_text(s)
        return s

    @staticmethod
    def _now() -> str:
        from datetime import datetime
        return datetime.now().isoformat()

    @staticmethod
    def _load_json(path: Path) -> dict:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_json(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _save_users(self) -> None:
        self._save_json(self._users_path, self._users)

    def _save_tokens(self) -> None:
        self._save_json(self._tokens_path, self._tokens)
