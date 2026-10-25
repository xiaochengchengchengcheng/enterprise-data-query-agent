# -*- coding: utf-8 -*-
"""Thread-safe in-memory conversation and analysis task storage."""

import copy
import threading
import time
from typing import Any, Dict, List, Optional


class ConversationStore:
    def __init__(self, max_turns: int = 12, ttl_seconds: int = 86400):
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [
            key for key, value in self._sessions.items()
            if now - value.get('updated_at', now) > self.ttl_seconds
        ]
        for key in expired:
            self._sessions.pop(key, None)

    def append(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            self._purge_expired()
            session = self._sessions.setdefault(
                session_id,
                {'messages': [], 'updated_at': time.time()},
            )
            session['messages'].append({
                'role': role,
                'content': content,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            })
            session['messages'] = session['messages'][-self.max_turns * 2:]
            session['updated_at'] = time.time()

    def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        with self._lock:
            self._purge_expired()
            session = self._sessions.get(session_id, {})
            return copy.deepcopy(session.get('messages', []))


class AnalysisTaskStore:
    def __init__(self, ttl_seconds: int = 86400):
        self.ttl_seconds = ttl_seconds
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [
            key for key, value in self._tasks.items()
            if now - value.get('_updated_at', now) > self.ttl_seconds
        ]
        for key in expired:
            self._tasks.pop(key, None)

    def put(self, task_id: str, task: Dict[str, Any]) -> None:
        with self._lock:
            self._purge_expired()
            value = copy.deepcopy(task)
            value['_updated_at'] = time.time()
            self._tasks[task_id] = value

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._purge_expired()
            task = self._tasks.get(task_id)
            return copy.deepcopy(task) if task else None

    def update(self, task_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._purge_expired()
            if task_id not in self._tasks:
                raise KeyError(task_id)
            self._tasks[task_id].update(copy.deepcopy(changes))
            self._tasks[task_id]['_updated_at'] = time.time()
            return copy.deepcopy(self._tasks[task_id])


conversation_store = ConversationStore()
analysis_task_store = AnalysisTaskStore()
