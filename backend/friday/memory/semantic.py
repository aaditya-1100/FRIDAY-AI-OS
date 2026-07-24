import os
import atexit
import hashlib
import math
from typing import List, Dict, Any, Optional
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.http import models
from fastembed import TextEmbedding

_model_instance = None
_client_instance = None


class _Vector(list):
    def tolist(self):
        return list(self)


class _DeterministicEmbeddingFallback:
    """Small offline fallback with the same embed() surface used by fastembed."""
    def embed(self, texts):
        for text in texts:
            buckets = [0.0] * 384
            words = str(text or "").lower().split()
            if not words:
                words = [""]
            for word in words:
                digest = hashlib.sha256(word.encode("utf-8", errors="ignore")).digest()
                idx = int.from_bytes(digest[:2], "big") % len(buckets)
                sign = 1.0 if digest[2] % 2 == 0 else -1.0
                buckets[idx] += sign
            norm = math.sqrt(sum(v * v for v in buckets)) or 1.0
            yield _Vector(v / norm for v in buckets)

import threading

_embedding_ready = threading.Event()
_embedding_lock = threading.Lock()

def get_embedding_model():
    global _model_instance
    if _model_instance is None:
        with _embedding_lock:
            if _model_instance is None:
                if os.getenv("FRIDAY_FORCE_HASH_EMBEDDINGS") == "1":
                    _model_instance = _DeterministicEmbeddingFallback()
                    _embedding_ready.set()
                    return _model_instance
                model_name = "BAAI/bge-small-en-v1.5"
                logger.info(f"[SemanticMemory] Loading embedding model using fastembed: {model_name}")
                try:
                    _model_instance = TextEmbedding(model_name=model_name)
                except Exception as e:
                    logger.warning(f"[SemanticMemory] Failed to load {model_name} via fastembed, trying default: {e}")
                    try:
                        _model_instance = TextEmbedding()
                    except Exception as fallback_error:
                        logger.warning(
                            "[SemanticMemory] fastembed default model unavailable; using deterministic offline fallback: "
                            f"{fallback_error}"
                        )
                        _model_instance = _DeterministicEmbeddingFallback()
                _embedding_ready.set()
                logger.info("[SemanticMemory] Embedding model loaded and ready.")
    return _model_instance

class SemanticMemory:
    def __init__(self, qdrant_path: str = None):
        global _client_instance
        if qdrant_path is None:
            # Explicit FRIDAY_QDRANT_PATH still honoured for backward compat;
            # otherwise resolve through central data-dir config.
            configured_path = os.environ.get("FRIDAY_QDRANT_PATH")
            if configured_path:
                base_path = os.path.abspath(configured_path)
            else:
                from config.paths import get_data_path
                base_path = get_data_path("qdrant")
            worker_id = os.environ.get("PYTEST_XDIST_WORKER")
            if worker_id:
                self.qdrant_path = f"{base_path}_{worker_id}"
            else:
                self.qdrant_path = base_path
        else:
            self.qdrant_path = os.path.abspath(qdrant_path)
        os.makedirs(self.qdrant_path, exist_ok=True)
        
        if _client_instance is None:
            _client_instance = QdrantClient(path=self.qdrant_path)
        self.client = _client_instance
        self._init_collections()

    @property
    def model(self):
        if not _embedding_ready.is_set():
            logger.info("[SemanticMemory] Waiting for embedding model to finish loading in background...")
            _embedding_ready.wait(timeout=60.0)
        return get_embedding_model()

    def _init_collections(self):
        collections = ["friday_semantic", "friday_episodic"]
        for col in collections:
            try:
                exists = False
                try:
                    cols = self.client.get_collections().collections
                    exists = any(c.name == col for c in cols)
                except Exception:
                    exists = self.client.collection_exists(collection_name=col)
                
                if not exists:
                    logger.info(f"[SemanticMemory] Creating Qdrant collection: {col}")
                    self.client.create_collection(
                        collection_name=col,
                        vectors_config=models.VectorParams(
                            size=384,
                            distance=models.Distance.COSINE
                        )
                    )
            except Exception as e:
                logger.error(f"[SemanticMemory] Error checking/creating collection {col}: {e}")

    def add_fact(self, text: str, metadata: Optional[Dict[str, Any]] = None, collection: str = "friday_semantic", app_id: str = "general") -> None:
        try:
            embeddings = list(self.model.embed([text]))
            embedding = embeddings[0].tolist()
            payload = metadata or {}
            payload["text"] = text
            payload["app_id"] = app_id
            
            import uuid
            point_id = str(uuid.uuid4())
            
            self.client.upsert(
                collection_name=collection,
                points=[
                    models.PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload
                    )
                ]
            )
            logger.info(f"[SemanticMemory] Successfully indexed fact in {collection} for app_id {app_id}.")
        except Exception as e:
            logger.error(f"[SemanticMemory] Failed to add fact to Qdrant: {e}", exc_info=True)

    def search(self, query: str, limit: int = 5, collection: str = "friday_semantic", app_id: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            query_vectors = list(self.model.embed([query]))
            query_vector = query_vectors[0].tolist()
            
            query_filter = None
            if app_id:
                query_filter = models.Filter(
                    should=[
                        models.FieldCondition(
                            key="app_id",
                            match=models.MatchValue(value=app_id)
                        ),
                        models.FieldCondition(
                            key="app_id",
                            match=models.MatchValue(value="global")
                        )
                    ]
                )
            
            response = self.client.query_points(
                collection_name=collection,
                query=query_vector,
                query_filter=query_filter,
                limit=limit
            )
            
            hits = []
            for res in response.points:
                hits.append({
                    "id": res.id,
                    "score": res.score,
                    "payload": res.payload
                })
            return hits
        except Exception as e:
            logger.error(f"[SemanticMemory] Qdrant search failed: {e}", exc_info=True)
            return []

    def clear(self, collection: str = "friday_semantic") -> None:
        try:
            cols = self.client.get_collections().collections
            exists = any(c.name == collection for c in cols)
            if exists:
                self.client.delete_collection(collection_name=collection)
            self.client.create_collection(
                collection_name=collection,
                vectors_config=models.VectorParams(
                    size=384,
                    distance=models.Distance.COSINE
                )
            )
            logger.info(f"[SemanticMemory] Cleared Qdrant collection: {collection}")
        except Exception as e:
            logger.error(f"[SemanticMemory] Failed to clear Qdrant collection {collection}: {e}")

def close_qdrant_client(envelope=None):
    global _client_instance
    if _client_instance is not None:
        try:
            _client_instance.close()
        except Exception:
            pass
        finally:
            _client_instance = None

# Subscribe to event bus for clean shutdown
try:
    from friday.core.event_bus import event_bus
    async def _on_shutdown_event(envelope):
        close_qdrant_client()
    event_bus.subscribe("friday.system.shutdown", _on_shutdown_event)
except Exception as e_eb:
    logger.debug(f"[SemanticMemory] Could not subscribe to event bus for shutdown: {e_eb}")

# Register atexit handler
atexit.register(close_qdrant_client)
