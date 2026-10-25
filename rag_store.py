# -*- coding: utf-8 -*-
"""Persistent SQLite vector store for business metadata and terminology."""

import json
import math
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from model_registry import ModelRegistry, model_registry


class SQLiteVectorStore:
    def __init__(
        self,
        db_path: Optional[str] = None,
        registry: Optional[ModelRegistry] = None,
    ):
        self.db_path = db_path or os.environ.get('RAG_DB_PATH', './data/rag.sqlite3')
        self.registry = registry or model_registry
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                '''CREATE TABLE IF NOT EXISTS rag_documents (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )'''
            )
            connection.execute(
                'CREATE INDEX IF NOT EXISTS idx_rag_namespace ON rag_documents(namespace)'
            )

    def upsert(
        self,
        documents: List[Dict[str, Any]],
        namespace: str = 'business',
        embedding_model: Optional[str] = None,
    ) -> int:
        if not documents:
            return 0
        model_name = embedding_model or self.registry.default_embedding_name()
        contents = [str(item.get('content', '')).strip() for item in documents]
        if any(not item for item in contents):
            raise ValueError('RAG 文档 content 不能为空')
        vectors = self.registry.embed(contents, model_name)
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        with self._lock, self._connect() as connection:
            for index, document in enumerate(documents):
                document_id = str(document.get('id') or uuid.uuid4())
                connection.execute(
                    '''INSERT INTO rag_documents
                       (id, namespace, content, metadata_json, embedding_json, embedding_model, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                         namespace=excluded.namespace,
                         content=excluded.content,
                         metadata_json=excluded.metadata_json,
                         embedding_json=excluded.embedding_json,
                         embedding_model=excluded.embedding_model,
                         updated_at=excluded.updated_at''',
                    (
                        document_id,
                        namespace,
                        contents[index],
                        json.dumps(document.get('metadata', {}), ensure_ascii=False),
                        json.dumps(vectors[index]),
                        model_name,
                        now,
                    ),
                )
        return len(documents)

    def search(
        self,
        query: str,
        top_k: int = 5,
        namespace: str = 'business',
        embedding_model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not query.strip():
            return []
        model_name = embedding_model or self.registry.default_embedding_name()
        query_vector = self.registry.embed([query], model_name)[0]
        with self._connect() as connection:
            rows = connection.execute(
                '''SELECT id, content, metadata_json, embedding_json, embedding_model
                   FROM rag_documents WHERE namespace = ? AND embedding_model = ?''',
                (namespace, model_name),
            ).fetchall()
        results = []
        for row in rows:
            vector = json.loads(row['embedding_json'])
            score = self._cosine(query_vector, vector)
            results.append({
                'id': row['id'],
                'content': row['content'],
                'metadata': json.loads(row['metadata_json']),
                'score': round(score, 6),
            })
        results.sort(key=lambda item: item['score'], reverse=True)
        return results[:max(1, min(int(top_k), 20))]

    def count(self, namespace: Optional[str] = None) -> int:
        with self._connect() as connection:
            if namespace:
                row = connection.execute(
                    'SELECT COUNT(*) AS count FROM rag_documents WHERE namespace = ?',
                    (namespace,),
                ).fetchone()
            else:
                row = connection.execute('SELECT COUNT(*) AS count FROM rag_documents').fetchone()
        return int(row['count'])

    @staticmethod
    def _cosine(left: List[float], right: List[float]) -> float:
        if len(left) != len(right):
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(item * item for item in left))
        right_norm = math.sqrt(sum(item * item for item in right))
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)


rag_store = SQLiteVectorStore()
