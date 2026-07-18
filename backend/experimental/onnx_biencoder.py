"""
onnx_biencoder.py — FRIDAY ONNX Bi-Encoder & Embedding Cache Layer
================================================================
Implements local, high-performance CPU sentence embedding generation.
Includes:
  - EmbeddingCache: LRU cache with hit metrics and automatic invalidation
  - ONNXBiEncoder: Standalone sentence tokenizer and ONNX Runtime inference session
"""

import os
import time
import numpy as np
import onnxruntime as ort
from collections import OrderedDict
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

class EmbeddingCache:
    """
    EmbeddingCache: LRU Cache mapping normalized query hashes to their float32 embeddings.
    """
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> np.ndarray | None:
        normalized_key = self._normalize(key)
        if normalized_key in self.cache:
            self.hits += 1
            self.cache.move_to_end(normalized_key)
            return self.cache[normalized_key]
        self.misses += 1
        return None

    def set(self, key: str, value: np.ndarray) -> None:
        normalized_key = self._normalize(key)
        if normalized_key in self.cache:
            self.cache[normalized_key] = value
            self.cache.move_to_end(normalized_key)
        else:
            self.cache[normalized_key] = value
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)

    def invalidate(self) -> None:
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    def get_metrics(self) -> dict:
        total = self.hits + self.misses
        hit_ratio = (self.hits / total) if total > 0 else 0.0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": hit_ratio,
            "cache_size": len(self.cache)
        }

    def _normalize(self, text: str) -> str:
        return " ".join(text.lower().strip().split())


class ONNXBiEncoder:
    """
    ONNXBiEncoder: Standalone sentence transformer inference runner using ONNX Runtime.
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", cache_size: int = 1000):
        self.model_name = model_name
        self.cache = EmbeddingCache(max_size=cache_size)
        self.session = None
        self.tokenizer = None
        self.model_path = None
        self.tokenizer_path = None
        
        # Mappings of huggingface repos to Xenova pre-converted ONNX versions
        self.repos = {
            "all-MiniLM-L6-v2": "Xenova/all-MiniLM-L6-v2",
            "bge-small-en-v1.5": "Xenova/bge-small-en-v1.5",
            "e5-small-v2": "Xenova/e5-small-v2"
        }

    def load(self, local_dir: str = None) -> None:
        """Downloads (if necessary) and loads the ONNX model and tokenizer."""
        repo_id = self.repos.get(self.model_name, f"Xenova/{self.model_name}")
        
        # Download files from HuggingFace Hub (local caching handled automatically by HF)
        print(f"[ONNX_BIENCODER] Loading model '{self.model_name}' from repo '{repo_id}'...")
        try:
            self.model_path = hf_hub_download(repo_id=repo_id, filename="onnx/model.onnx")
            self.tokenizer_path = hf_hub_download(repo_id=repo_id, filename="tokenizer.json")
        except Exception as e:
            print(f"[ONNX_BIENCODER] Failed to download model '{self.model_name}': {e}")
            # Try fallback directory if provided
            if local_dir and os.path.exists(local_dir):
                self.model_path = os.path.join(local_dir, "model.onnx")
                self.tokenizer_path = os.path.join(local_dir, "tokenizer.json")
            else:
                raise e

        # Initialize Tokenizer and ONNX InferenceSession
        self.tokenizer = Tokenizer.from_file(self.tokenizer_path)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        self.tokenizer.enable_truncation(max_length=256)
        
        # CPU-optimized execution provider
        self.session = ort.InferenceSession(
            self.model_path, 
            providers=['CPUExecutionProvider']
        )
        print(f"[ONNX_BIENCODER] Model '{self.model_name}' loaded successfully.")

    def encode(self, text: str) -> np.ndarray:
        """Generates L2-normalized sentence embedding for the query."""
        if not text:
            return np.zeros(384 if "MiniLM" in self.model_name else 384, dtype=np.float32)
            
        # Check LRU cache first
        cached = self.cache.get(text)
        if cached is not None:
            return cached

        if not self.session or not self.tokenizer:
            raise RuntimeError("Model is not loaded. Call load() first.")

        # Tokenize sentence
        encoding = self.tokenizer.encode(text)
        
        # Extract inputs expected by the ONNX model
        input_ids = np.array([encoding.ids], dtype=np.int64)
        attention_mask = np.array([encoding.attention_mask], dtype=np.int64)
        
        inputs = {
            "input_ids": input_ids,
            "attention_mask": attention_mask
        }
        
        # Check if model expects token_type_ids
        expected_inputs = [node.name for node in self.session.get_inputs()]
        if "token_type_ids" in expected_inputs:
            inputs["token_type_ids"] = np.array([encoding.type_ids], dtype=np.int64)

        # Run ONNX Runtime Inference
        outputs = self.session.run(None, inputs)
        
        # outputs[0] is token_embeddings of shape [batch_size, seq_len, hidden_dim]
        token_embeddings = outputs[0]
        
        # Perform Mean Pooling over the token embeddings using the attention mask
        input_mask_expanded = np.expand_dims(attention_mask, axis=-1)
        sum_embeddings = np.sum(token_embeddings * input_mask_expanded, axis=1)
        sum_mask = np.clip(np.sum(input_mask_expanded, axis=1), a_min=1e-9, a_max=None)
        mean_pooled = sum_embeddings / sum_mask
        
        # Extract single batch embedding
        embedding = mean_pooled[0].astype(np.float32)
        
        # Perform L2 Normalization
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        # Save to LRU cache
        self.cache.set(text, embedding)
        
        return embedding
