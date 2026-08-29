"""Embedding service powered by local embeddinggemma-onnx-embeddinggemma-300m-v1."""

import logging
from pathlib import Path
from typing import List, Optional, Union
import numpy as np

logger = logging.getLogger("cvforge.services.embedding")


class EmbeddingGemmaService:
    """Provides local fast vector embeddings using ONNX runtime and Tokenizers."""

    DEFAULT_MODEL_PATH = Path("/home/omkar/Documents/System Mech/embeddinggemma-onnx-embeddinggemma-300m-v1")

    def __init__(self, model_dir: Optional[Union[str, Path]] = None):
        self.model_dir = Path(model_dir).resolve() if model_dir else self.DEFAULT_MODEL_PATH
        self._session = None
        self._tokenizer = None
        self._is_initialized = False

    def _initialize(self) -> bool:
        """Lazy load ONNX model and tokenizer."""
        if self._is_initialized:
            return True

        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            if not self.model_dir.exists():
                logger.warning(f"Embedding model directory not found at: {self.model_dir}")
                return False

            tokenizer_file = self.model_dir / "tokenizer.json"
            if not tokenizer_file.exists():
                logger.warning(f"Tokenizer not found at: {tokenizer_file}")
                return False

            self._tokenizer = Tokenizer.from_file(str(tokenizer_file))

            # Look for best available ONNX model (quantized preferred for speed/memory)
            onnx_candidates = [
                self.model_dir / "onnx" / "model_quantized.onnx",
                self.model_dir / "onnx" / "model_q4f16.onnx",
                self.model_dir / "onnx" / "model_q4.onnx",
                self.model_dir / "onnx" / "model_fp16.onnx",
                self.model_dir / "onnx" / "model.onnx",
            ]

            selected_model = None
            for cand in onnx_candidates:
                if cand.exists():
                    selected_model = cand
                    break

            if not selected_model:
                logger.warning(f"No valid ONNX model file found in {self.model_dir / 'onnx'}")
                return False

            logger.info(f"Loading ONNX session with: {selected_model.name}")
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            opts.intra_op_num_threads = 4
            self._session = ort.InferenceSession(str(selected_model), sess_options=opts)
            self._is_initialized = True
            return True

        except Exception as exc:
            logger.error(f"Failed to initialize EmbeddingGemmaService: {exc}")
            return False

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate a 768-dimensional normalized embedding vector for the input text."""
        if not text or not text.strip():
            return None

        if not self._initialize():
            return None

        try:
            # Truncate to reasonable context window if very large
            clean_text = text.strip()[:4000]
            enc = self._tokenizer.encode(clean_text)

            input_ids = np.array([enc.ids], dtype=np.int64)
            attention_mask = np.array([enc.attention_mask], dtype=np.int64)

            feeds = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }

            outputs = self._session.run(None, feeds)
            # sentence_embedding is output index 1 if present; fallback to mean pooling
            if len(outputs) > 1 and outputs[1].ndim == 2:
                raw_emb = outputs[1][0]
            else:
                last_hidden = outputs[0][0]  # shape (seq_len, hidden_dim)
                mask = np.expand_dims(attention_mask[0], axis=-1)  # shape (seq_len, 1)
                sum_hidden = np.sum(last_hidden * mask, axis=0)
                sum_mask = np.clip(mask.sum(), a_min=1e-9, a_max=None)
                raw_emb = sum_hidden / sum_mask

            # L2 normalize
            norm = np.linalg.norm(raw_emb)
            if norm > 0:
                normalized = raw_emb / norm
            else:
                normalized = raw_emb

            return [round(float(x), 6) for x in normalized.tolist()]

        except Exception as exc:
            logger.error(f"Failed to generate embedding: {exc}")
            return None
