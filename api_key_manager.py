# -*- coding: utf-8 -*-
"""SQLite-backed API key lifecycle and scope management."""

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple


class APIKeyManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get('API_KEY_DB_PATH', './data/api_keys.sqlite3')
        directory = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(directory, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                '''CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    prefix TEXT NOT NULL UNIQUE,
                    salt TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    scopes TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at INTEGER,
                    revoked_at TEXT,
                    last_used_at TEXT
                )'''
            )

    @staticmethod
    def _digest(token: str, salt: bytes) -> str:
        value = hashlib.pbkdf2_hmac('sha256', token.encode('utf-8'), salt, 200000)
        return value.hex()

    def create_key(
        self,
        name: str,
        scopes: List[str],
        expires_in_days: Optional[int] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        token = 'eda_' + secrets.token_urlsafe(32)
        prefix = token[:12]
        salt = secrets.token_bytes(16)
        key_id = str(uuid.uuid4())
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        expires_at = None
        if expires_in_days:
            expires_at = int(time.time()) + int(expires_in_days) * 86400
        normalized_scopes = sorted(set(scopes or ['analysis']))
        with self._lock, self._connect() as connection:
            connection.execute(
                '''INSERT INTO api_keys
                   (id, name, prefix, salt, key_hash, scopes, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    key_id,
                    name,
                    prefix,
                    salt.hex(),
                    self._digest(token, salt),
                    ','.join(normalized_scopes),
                    now,
                    expires_at,
                ),
            )
        return token, {
            'id': key_id,
            'name': name,
            'prefix': prefix,
            'scopes': normalized_scopes,
            'created_at': now,
            'expires_at': expires_at,
        }

    def verify(self, token: str, required_scope: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        bootstrap = os.environ.get('ADMIN_API_KEY', '')
        if bootstrap and hmac.compare_digest(token, bootstrap):
            return {'id': 'bootstrap', 'name': 'bootstrap-admin', 'scopes': ['*', 'admin']}
        prefix = token[:12]
        with self._lock, self._connect() as connection:
            row = connection.execute(
                'SELECT * FROM api_keys WHERE prefix = ?', (prefix,)
            ).fetchone()
            if not row or row['revoked_at']:
                return None
            if row['expires_at'] and int(row['expires_at']) < int(time.time()):
                return None
            expected = self._digest(token, bytes.fromhex(row['salt']))
            if not hmac.compare_digest(expected, row['key_hash']):
                return None
            scopes = [item for item in row['scopes'].split(',') if item]
            if required_scope and required_scope not in scopes and '*' not in scopes and 'admin' not in scopes:
                return None
            connection.execute(
                'UPDATE api_keys SET last_used_at = ? WHERE id = ?',
                (time.strftime('%Y-%m-%d %H:%M:%S'), row['id']),
            )
            return {'id': row['id'], 'name': row['name'], 'scopes': scopes}

    def list_keys(self) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                '''SELECT id, name, prefix, scopes, created_at, expires_at,
                          revoked_at, last_used_at FROM api_keys ORDER BY created_at DESC'''
            ).fetchall()
        return [
            {
                **dict(row),
                'scopes': [item for item in row['scopes'].split(',') if item],
            }
            for row in rows
        ]

    def revoke(self, key_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                'UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL',
                (time.strftime('%Y-%m-%d %H:%M:%S'), key_id),
            )
            return cursor.rowcount > 0


api_key_manager = APIKeyManager()
