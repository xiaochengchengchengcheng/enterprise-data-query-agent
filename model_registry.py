# -*- coding: utf-8 -*-
"""Runtime registry for OpenAI-compatible chat and embedding models."""

import hashlib
import json
import math
import os
import re
import threading
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import requests

from llm_gateway import LLMGateway
from security_middleware import mask_sensitive_text


@dataclass
class ModelSpec:
    name: str
    kind: str
    model: str
    api_base: str = ''
    api_key_env: str = ''
    dimensions: int = 256

    def public_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value.pop('api_key_env', None)
        value['configured'] = self.kind == 'embedding-local' or bool(
            self.api_base and self.api_key_env and os.environ.get(self.api_key_env)
        )
        return value


class ModelRegistry:
    def __init__(self):
        self._models: Dict[str, ModelSpec] = {}
        self._lock = threading.RLock()
        self._load_defaults()
        self._load_json_config()

    def _load_defaults(self) -> None:
        self.register(ModelSpec(
            name='default-chat',
            kind='chat',
            model=os.environ.get('LLM_MODEL_NAME', 'deepseek-chat'),
            api_base=os.environ.get('LLM_API_BASE', ''),
            api_key_env='LLM_API_KEY',
        ))
        embedding_base = os.environ.get('EMBEDDING_API_BASE', '')
        embedding_model = os.environ.get('EMBEDDING_MODEL_NAME', '')
        if embedding_base and embedding_model:
            self.register(ModelSpec(
                name='default-embedding',
                kind='embedding',
                model=embedding_model,
                api_base=embedding_base,
                api_key_env='EMBEDDING_API_KEY',
                dimensions=int(os.environ.get('EMBEDDING_DIMENSIONS', '1024')),
            ))
        self.register(ModelSpec(
            name='local-hashing',
            kind='embedding-local',
            model='character-ngram-hashing',
            dimensions=int(os.environ.get('LOCAL_EMBEDDING_DIMENSIONS', '256')),
        ))

    def _load_json_config(self) -> None:
        raw = os.environ.get('MODEL_REGISTRY_JSON', '').strip()
        if not raw:
            return
        try:
            items = json.loads(raw)
            for item in items:
                self.register(ModelSpec(**item))
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError('MODEL_REGISTRY_JSON 配置无效: %s' % exc)

    def register(self, spec: ModelSpec) -> None:
        if spec.kind not in ('chat', 'embedding', 'embedding-local'):
            raise ValueError('不支持的模型类型: %s' % spec.kind)
        with self._lock:
            self._models[spec.name] = spec

    def list_models(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [spec.public_dict() for spec in self._models.values()]

    def get(self, name: Optional[str], kind: str) -> ModelSpec:
        target = name or ('default-chat' if kind == 'chat' else self.default_embedding_name())
        with self._lock:
            spec = self._models.get(target)
        if not spec or (kind == 'embedding' and spec.kind not in ('embedding', 'embedding-local')) or (kind == 'chat' and spec.kind != 'chat'):
            raise KeyError('未注册的%s模型: %s' % (kind, target))
        return spec

    def default_embedding_name(self) -> str:
        with self._lock:
            return 'default-embedding' if 'default-embedding' in self._models else 'local-hashing'

    def get_chat_gateway(self, name: Optional[str] = None) -> LLMGateway:
        spec = self.get(name, 'chat')
        api_key = os.environ.get(spec.api_key_env, '')
        return LLMGateway(
            api_base=spec.api_base,
            api_key=api_key,
            model_name=spec.model,
        )

    def embed(self, texts: List[str], name: Optional[str] = None) -> List[List[float]]:
        spec = self.get(name, 'embedding')
        if spec.kind == 'embedding-local':
            return [self._hash_embedding(text, spec.dimensions) for text in texts]

        url = spec.api_base.rstrip('/') + '/embeddings'
        api_key = os.environ.get(spec.api_key_env, '')
        if not api_key:
            raise ValueError('%s 未配置' % spec.api_key_env)
        safe_texts = [mask_sensitive_text(text) for text in texts]
        response = requests.post(
            url,
            headers={
                'Authorization': 'Bearer ' + api_key,
                'Content-Type': 'application/json',
            },
            json={'model': spec.model, 'input': safe_texts},
            timeout=int(os.environ.get('EMBEDDING_REQUEST_TIMEOUT', '60')),
        )
        response.raise_for_status()
        data = sorted(response.json().get('data', []), key=lambda item: item.get('index', 0))
        if len(data) != len(texts):
            raise ValueError('Embedding API 返回数量不匹配')
        return [item['embedding'] for item in data]

    @staticmethod
    def _hash_embedding(text: str, dimensions: int) -> List[float]:
        value = re.sub(r'\s+', ' ', text.lower()).strip()
        tokens = list(value)
        tokens.extend(value[index:index + 2] for index in range(max(0, len(value) - 1)))
        vector = [0.0] * dimensions
        for token in tokens:
            digest = hashlib.sha256(token.encode('utf-8')).digest()
            index = int.from_bytes(digest[:4], 'big') % dimensions
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(item * item for item in vector)) or 1.0
        return [item / norm for item in vector]


model_registry = ModelRegistry()
