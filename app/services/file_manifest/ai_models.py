"""AI, machine learning, OCR, and local LLM services for resume extraction.

Consolidates:
- EmbeddingGemmaService: Local ONNX embedding inference (Gemma-300m embeddings)
- OCRService: PaddleOCR optical character recognition engine with graceful fallback
- GemmaExtractor: Local offline LLM candidate extraction via Gemma-3-270m ONNX
"""

import io
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union
import numpy as np
from PIL import Image

logger = logging.getLogger("cvforge.services.ai_models")


# =============================================================================
# 1. OCR Service (PaddleOCR)
# =============================================================================

class OCRService:
    """Provides optical character recognition for scanned document pages."""

    _paddle_instance = None
    _paddle_failed = False

    @classmethod
    def _get_paddleocr(cls):
        if cls._paddle_failed:
            return None
        if cls._paddle_instance is None:
            try:
                from paddleocr import PaddleOCR  # type: ignore[import-not-found,import-untyped]
                # Initialize PaddleOCR with English, angle classification enabled
                cls._paddle_instance = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
                logger.info("PaddleOCR engine initialized successfully")
            except Exception as exc:
                cls._paddle_failed = True
                logger.warning(f"PaddleOCR is not available or failed to initialize: {exc}")
                return None
        return cls._paddle_instance

    @classmethod
    def ocr_image(cls, image_input: Union[bytes, Path, str, Image.Image]) -> str:
        """Performs OCR on an image (bytes, path, or PIL Image) and returns recognized text."""
        ocr = cls._get_paddleocr()
        if ocr is None:
            logger.debug("OCR skipped: No active OCR engine available.")
            return ""

        try:
            if isinstance(image_input, (bytes, bytearray)):
                pil_img = Image.open(io.BytesIO(image_input)).convert("RGB")
                img_array = np.array(pil_img)
            elif isinstance(image_input, Image.Image):
                img_array = np.array(image_input.convert("RGB"))
            elif isinstance(image_input, (str, Path)):
                pil_img = Image.open(str(image_input)).convert("RGB")
                img_array = np.array(pil_img)
            else:
                return ""

            result = ocr.ocr(img_array, cls=True)
            text_lines: List[str] = []
            if result and len(result) > 0:
                for line in result:
                    if not line:
                        continue
                    for word_info in line:
                        if word_info and len(word_info) >= 2 and word_info[1]:
                            text = word_info[1][0]
                            if text:
                                text_lines.append(text)

            return "\n".join(text_lines)

        except Exception as exc:
            logger.warning(f"Error during OCR execution: {exc}")
            return ""


# =============================================================================
# 2. Embedding Service (EmbeddingGemma ONNX)
# =============================================================================

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


# =============================================================================
# 3. Gemma-3-270m Offline Extractor (ONNX)
# =============================================================================

class GemmaExtractor:
    """Provides local offline structured candidate extraction via Gemma-3-270m ONNX."""

    DEFAULT_MODEL_DIR = Path("/home/omkar/Documents/System Mech/gemma-3-270m-it-ONNX")

    def __init__(self, model_dir: Optional[Union[str, Path]] = None):
        self.model_dir = Path(model_dir).resolve() if model_dir else self.DEFAULT_MODEL_DIR
        self._session = None
        self._tokenizer = None
        self._is_initialized = False

    def is_available(self) -> bool:
        """Returns True if the offline model directory exists and has model weights."""
        if not self.model_dir.exists():
            return False
        has_tokenizer = (self.model_dir / "tokenizer.json").exists()
        has_onnx = any(self.model_dir.glob("onnx/*.onnx")) or any(self.model_dir.glob("*.onnx"))
        return has_tokenizer and has_onnx

    def _initialize(self) -> bool:
        """Lazy load ONNX runtime session and Tokenizer."""
        if self._is_initialized:
            return True

        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            if not self.is_available():
                logger.debug(f"Gemma-3-270m model not found at {self.model_dir}")
                return False

            tokenizer_path = self.model_dir / "tokenizer.json"
            self._tokenizer = Tokenizer.from_file(str(tokenizer_path))

            # Select quantized model for low memory & fast CPU/GPU inference
            candidate_models = [
                self.model_dir / "onnx" / "model_q4.onnx",
                self.model_dir / "onnx" / "model_quantized.onnx",
                self.model_dir / "onnx" / "model_fp16.onnx",
                self.model_dir / "onnx" / "model.onnx",
                self.model_dir / "model_quantized.onnx",
                self.model_dir / "model.onnx",
            ]

            model_file = None
            for cand in candidate_models:
                if cand.exists():
                    model_file = cand
                    break

            if not model_file:
                logger.warning(f"No valid ONNX model file found in {self.model_dir}")
                return False

            # Configure session options
            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = 4
            sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            providers = ["CPUExecutionProvider"]
            if "CUDAExecutionProvider" in ort.get_available_providers():
                providers.insert(0, "CUDAExecutionProvider")

            self._session = ort.InferenceSession(
                str(model_file), sess_options=sess_opts, providers=providers
            )
            self._num_layers = 18  # Gemma-3-270m architecture layers
            self._head_dim = 256
            self._is_initialized = True
            logger.info(f"Loaded offline Gemma-3-270m ONNX model from {model_file.name}")
            return True

        except Exception as exc:
            logger.warning(f"Failed to initialize offline Gemma-3-270m: {exc}")
            return False

    def unload(self):
        """Unloads ONNX session and tokenizer to free system memory."""
        import gc
        if self._session is not None:
            del self._session
            self._session = None
        if self._tokenizer is not None:
            del self._tokenizer
            self._tokenizer = None
        self._is_initialized = False
        gc.collect()

    def clear_session(self):
        """Clears previous prompt context, message history, and KV-cache while keeping
        the ONNX model session in memory.
        """
        import gc
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        gc.collect()
        logger.debug("Cleared Gemma context, previous messages, and KV cache; fresh session ready.")

    def generate(self, prompt: str, max_new_tokens: int = 256) -> str:
        """Runs local inference with KV-cache acceleration on Gemma-3-270m ONNX.

        Generates up to max_new_tokens tokens (~90 tokens/sec on CPU).
        """
        if not self._initialize():
            return ""

        feed = None
        step_feed = None
        outs = None
        try:
            encoded = self._tokenizer.encode(prompt)
            prompt_tokens = encoded.ids
            seq_len = len(prompt_tokens)

            input_ids = np.array([prompt_tokens], dtype=np.int64)
            attention_mask = np.ones((1, seq_len), dtype=np.int64)

            # Initialize empty past_key_values for step 0
            feed = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }
            for i in range(self._num_layers):
                feed[f"past_key_values.{i}.key"] = np.zeros((1, 1, 0, self._head_dim), dtype=np.float32)
                feed[f"past_key_values.{i}.value"] = np.zeros((1, 1, 0, self._head_dim), dtype=np.float32)

            outs = self._session.run(None, feed)
            logits = outs[0]
            next_token = int(np.argmax(logits[0, -1, :]))
            generated_tokens = [next_token]

            eos_id = self._tokenizer.token_to_id("<end_of_turn>") or 1

            for _ in range(max_new_tokens - 1):
                if next_token == eos_id:
                    break

                total_len = seq_len + len(generated_tokens)
                step_feed = {
                    "input_ids": np.array([[next_token]], dtype=np.int64),
                    "attention_mask": np.ones((1, total_len), dtype=np.int64),
                }
                for i in range(self._num_layers):
                    step_feed[f"past_key_values.{i}.key"] = outs[1 + 2 * i]
                    step_feed[f"past_key_values.{i}.value"] = outs[2 + 2 * i]

                outs = self._session.run(None, step_feed)
                logits = outs[0]
                next_token = int(np.argmax(logits[0, -1, :]))
                generated_tokens.append(next_token)

            return self._tokenizer.decode(generated_tokens).strip()

        except Exception as exc:
            logger.debug(f"Gemma-3-270m generation error: {exc}")
            return ""
        finally:
            import gc
            del feed, step_feed, outs
            gc.collect()

    @staticmethod
    def _repair_json(s: str) -> Optional[Dict[str, Any]]:
        """Repairs incomplete or truncated JSON strings by balancing brackets and braces."""
        if not s:
            return None
        idx = s.find("{")
        if idx == -1:
            return None
        s = s[idx:].strip()

        try:
            return json.loads(s)
        except Exception:
            pass

        in_str = False
        escape = False
        open_brackets = []
        clean_chars = []
        for ch in s:
            if escape:
                escape = False
                clean_chars.append(ch)
                continue
            if ch == "\\":
                escape = True
                clean_chars.append(ch)
                continue
            if ch == '"':
                in_str = not in_str
                clean_chars.append(ch)
                continue
            if not in_str:
                if ch in "{[":
                    open_brackets.append(ch)
                elif ch == "}":
                    if open_brackets and open_brackets[-1] == "{":
                        open_brackets.pop()
                elif ch == "]":
                    if open_brackets and open_brackets[-1] == "[":
                        open_brackets.pop()
            clean_chars.append(ch)

        fixed = "".join(clean_chars)
        if in_str:
            fixed += '"'
        for b in reversed(open_brackets):
            if b == "{":
                fixed += "}"
            elif b == "[":
                fixed += "]"

        fixed = re.sub(r",\s*([\]}])", r"\1", fixed)
        try:
            parsed = json.loads(fixed)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        return None

    def extract_profile(self, resume_text: str) -> Optional[Dict[str, Any]]:
        """Runs Gemma-3-270m to parse key profile entities from resume text."""
        if not resume_text:
            return None

        prompt = (
            f"<start_of_turn>user\n"
            f"Extract the candidate name, role, skills, and summary from this resume:\n"
            f"{resume_text[:1200]}\n"
            f"Format:\n"
            f'{{"name": "...", "role": "...", "skills": [...], "company": "...", "education": [...]}}\n'
            f"<end_of_turn>\n<start_of_turn>model\n```json\n"
        )

        output = self.generate(prompt, max_new_tokens=220)
        if not output:
            return None

        repaired = self._repair_json(output)
        if repaired:
            return repaired

        json_match = re.search(r"\{.*?\}", output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except Exception:
                pass

        return None

    def fix_and_analyze_experience(self, exp_chunk: str) -> Optional[Dict[str, Any]]:
        """Uses Gemma-3-270m to analyze a work experience section, separating role, company,

        and location accurately.
        """
        if not exp_chunk or len(exp_chunk.split()) < 3:
            return None

        prompt = (
            f"<start_of_turn>user\n"
            f"Extract job title, company name, and location from this header:\n"
            f"{exp_chunk.strip()}\n"
            f'Format: {{"role": "...", "company": "...", "location": "..."}}\n'
            f"<end_of_turn>\n<start_of_turn>model\n```json\n"
        )

        output = self.generate(prompt, max_new_tokens=80)
        repaired = self._repair_json(output)
        if repaired and isinstance(repaired, dict):
            return repaired

        json_match = re.search(r"\{.*?\}", output, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return None

    def generate_summary(self, profile_snippet: str) -> Optional[str]:
        """Uses Gemma-3-270m to generate a concise, professional 2-sentence executive summary."""
        if not profile_snippet or len(profile_snippet.split()) < 5:
            return None

        prompt = (
            f"<start_of_turn>user\n"
            f"Write a concise 2-sentence professional executive summary for this candidate profile:\n"
            f"{profile_snippet.strip()}\n"
            f"<end_of_turn>\n<start_of_turn>model\n"
        )
        out = self.generate(prompt, max_new_tokens=90)
        if out:
            cleaned = " ".join(out.split())
            sentences = [s.strip() for s in cleaned.split(".") if s.strip()]
            if sentences:
                return ". ".join(sentences[:2]) + "."
        return None

    def refine_name(self, header_text: str) -> Optional[str]:
        """Uses Gemma-3-270m ONNX to isolate the candidate's actual personal name from header lines."""
        if not header_text or len(header_text.split()) < 2:
            return None

        prompt = (
            f"<start_of_turn>user\n"
            f"What is the full personal candidate name in this resume header?\n"
            f"{header_text.strip()}\n"
            f"Respond with only the candidate name.\n"
            f"<end_of_turn>\n<start_of_turn>model\n"
        )
        out = self.generate(prompt, max_new_tokens=15)
        if not out:
            return None
        cleaned = re.sub(r"[^\w\s]", "", out.split("\n")[0]).strip()
        if 2 <= len(cleaned.split()) <= 4:
            return cleaned.title()
        return None

    def refine_experience_header(self, exp_chunk: str) -> Optional[Dict[str, Any]]:
        """Alias to fix_and_analyze_experience."""
        return self.fix_and_analyze_experience(exp_chunk)

    def extract_candidate_insights(self, resume_text: str) -> Dict[str, Optional[str]]:
        """Uses Gemma-3-270m ONNX to extract candidate location, total experience, notice period, current CTC, and expected CTC."""
        result: Dict[str, Optional[str]] = {
            "location": None,
            "total_experience": None,
            "notice_period": None,
            "current_ctc": None,
            "expected_ctc": None,
        }
        if not resume_text:
            return result

        lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
        relevant_lines = []
        for line in lines:
            line_l = line.lower()
            if any(k in line_l for k in ["ctc", "notice", "location", "relocate", "experience", "salary", "lpa", "joiner", "per annum"]):
                relevant_lines.append(line)

        snippet_parts = lines[:15] + relevant_lines[:25]
        seen = set()
        dedup_lines = []
        for l in snippet_parts:
            if l not in seen:
                seen.add(l)
                dedup_lines.append(l)
        context_text = "\n".join(dedup_lines)[:1800]

        prompt = (
            f"<start_of_turn>user\n"
            f"Extract candidate details from the following resume text:\n"
            f"{context_text}\n\n"
            f"Fields to extract:\n"
            f"- location: City or current candidate location\n"
            f"- total_experience: Total years of experience (e.g. '5 years')\n"
            f"- notice_period: Notice period (e.g. 'Immediate', '15 days', '30 days')\n"
            f"- current_ctc: Current CTC or present salary (e.g. '10 LPA', '1000000')\n"
            f"- expected_ctc: Expected CTC or salary (e.g. '13 LPA', '1300000')\n"
            f"Format as valid JSON:\n"
            f'{{"location": "...", "total_experience": "...", "notice_period": "...", "current_ctc": "...", "expected_ctc": "..."}}\n'
            f"<end_of_turn>\n<start_of_turn>model\n```json\n"
        )

        output = self.generate(prompt, max_new_tokens=140)
        data = self._repair_json(output)
        if not data:
            match = re.search(r"\{.*?\}", output, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:
                    pass

        if isinstance(data, dict):
            for k in result:
                v = data.get(k)
                if v and isinstance(v, str):
                    clean_v = v.strip()
                    # Filter out placeholders or echoed prompt descriptions
                    if not clean_v.lower().startswith(("candidate", "total years", "city or", "notice period", "current ctc", "expected ctc")):
                        result[k] = clean_v
        return result



__all__ = [
    "OCRService",
    "EmbeddingGemmaService",
    "GemmaExtractor",
]
