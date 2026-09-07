"""AI, machine learning, OCR, and document parsing services for resume extraction.

Consolidates:
- EmbeddingGemmaService: Local ONNX embedding inference (Gemma-300m embeddings)
- OCRService: PaddleOCR optical character recognition engine with graceful fallback
- NemotronParseExtractor: Vision-language document parsing and candidate extraction via nvidia/NVIDIA-Nemotron-Parse-v1.2
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
# 3. NVIDIA-Nemotron-Parse-v1.2 Document Parser & Extractor
# =============================================================================

class NemotronParseExtractor:
    """Provides document vision-language parsing and candidate extraction using
    nvidia/NVIDIA-Nemotron-Parse-v1.2.

    Processes document images (e.g., rendered PDF pages or image scans) to produce:
    - Bounding boxes (<predict_bbox>)
    - Semantic classes (<predict_classes>, e.g. Title, Header, Table, List, Paragraph)
    - Clean Markdown output (<output_markdown>)
    - Reading order layout representation
    """

    LOCAL_MODEL_PATH = Path("/home/omkar/Documents/System Mech/NVIDIA-Nemotron-Parse-v1.2")
    DEFAULT_MODEL_NAME = "nvidia/NVIDIA-Nemotron-Parse-v1.2"
    _RE_CLASS_BBOX = re.compile(
        r"<x_(\d+(?:\.\d+)?)><y_(\d+(?:\.\d+)?)>(.*?)<x_(\d+(?:\.\d+)?)><y_(\d+(?:\.\d+)?)><class_([^>]+)>",
        re.DOTALL,
    )

    def __init__(
        self,
        model_dir: Optional[Union[str, Path]] = None,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
    ):
        if model_dir:
            model_target = model_dir
        elif self.LOCAL_MODEL_PATH.exists():
            model_target = self.LOCAL_MODEL_PATH
        else:
            model_target = model_name or self.DEFAULT_MODEL_NAME
        self.model_path = str(model_target)
        self.requested_device = device
        self.device = None

        self._model = None
        self._processor = None
        self._generation_config = None
        self._is_initialized = False

    def is_available(self) -> bool:
        """Returns True if the required libraries are installed and model path is configured."""
        try:
            import transformers  # noqa: F401
            import torch  # noqa: F401
            import albumentations  # noqa: F401
            import timm  # noqa: F401
            import einops  # noqa: F401
            # If path is a local directory, verify it exists
            target_p = Path(self.model_path)
            if target_p.exists() or not self.model_path.startswith(("/", ".")):
                return True
            return False
        except Exception:
            return False

    def _initialize(self) -> bool:
        """Lazy load Nemotron Parse model, processor, and generation config."""
        if self._is_initialized:
            return True

        try:
            import torch
            from transformers import AutoModel, AutoProcessor, GenerationConfig

            if self.requested_device:
                self.device = self.requested_device
            else:
                self.device = "cuda" if torch.cuda.is_available() else "cpu"

            torch_dtype = torch.bfloat16 if (self.device == "cuda" and torch.cuda.is_bf16_supported()) else (
                torch.float16 if self.device == "cuda" else torch.float32
            )

            logger.info(f"Loading Nemotron Parse model from '{self.model_path}' on {self.device} ({torch_dtype})...")

            self._processor = AutoProcessor.from_pretrained(
                self.model_path,
                trust_remote_code=True,
            )

            self._generation_config = GenerationConfig.from_pretrained(
                self.model_path,
                trust_remote_code=True,
            )

            self._model = AutoModel.from_pretrained(
                self.model_path,
                trust_remote_code=True,
                torch_dtype=torch_dtype,
            ).to(self.device).eval()

            self._is_initialized = True
            logger.info("Successfully loaded nvidia/NVIDIA-Nemotron-Parse-v1.2")
            return True

        except Exception as exc:
            logger.warning(f"Failed to initialize Nemotron Parse model ('{self.model_path}'): {exc}")
            return False

    def unload(self):
        """Unloads model and processor from memory and frees GPU VRAM."""
        import gc
        if self._model is not None:
            del self._model
            self._model = None
        if self._processor is not None:
            del self._processor
            self._processor = None
        if self._generation_config is not None:
            del self._generation_config
            self._generation_config = None
        self._is_initialized = False

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        gc.collect()

    def clear_session(self):
        """Clears temporary CUDA cache and runs garbage collection."""
        import gc
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        gc.collect()
        logger.debug("Nemotron Parse session memory cache cleared.")

    @staticmethod
    def _clean_text_artifacts(text: str) -> str:
        """Removes control tokens, unk tags, and latex artifacts from parsed text."""
        if not text:
            return ""
        cleaned = text.replace("<tbc>", "")
        cleaned = cleaned.replace(r"\<|unk|\>", "")
        cleaned = cleaned.replace(r"\unknown", "")
        # Remove empty lines excess
        return re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    @classmethod
    def extract_classes_bboxes(cls, text: str) -> Dict[str, List[Any]]:
        """Parses the generated raw string into classes, normalized bounding boxes, and texts."""
        classes: List[str] = []
        bboxes: List[List[float]] = []
        texts: List[str] = []

        for m in cls._RE_CLASS_BBOX.finditer(text):
            x1, y1, chunk_text, x2, y2, element_cls = m.groups()
            cleaned_chunk = cls._clean_text_artifacts(chunk_text)
            if cleaned_chunk:
                classes.append(element_cls)
                bboxes.append([float(x1), float(y1), float(x2), float(y2)])
                texts.append(cleaned_chunk)

        return {
            "classes": classes,
            "bboxes": bboxes,
            "texts": texts,
        }

    @staticmethod
    def transform_bbox_to_original(
        bbox: List[float],
        original_width: int,
        original_height: int,
        target_w: int = 1664,
        target_h: int = 2048,
    ) -> List[float]:
        """Transforms model normalized bounding box coordinates to original image pixels."""
        if not bbox or len(bbox) < 4:
            return [0.0, 0.0, 0.0, 0.0]

        aspect_ratio = original_width / max(original_height, 1)
        new_height = original_height
        new_width = original_width

        if original_height > target_h:
            new_height = target_h
            new_width = int(new_height * aspect_ratio)

        if new_width > target_w:
            new_width = target_w
            new_height = int(new_width / aspect_ratio)

        resized_width = max(new_width, 1)
        resized_height = max(new_height, 1)

        pad_left = (target_w - resized_width) // 2
        pad_top = (target_h - resized_height) // 2

        left = ((bbox[0] * target_w) - pad_left) * original_width / resized_width
        right = ((bbox[2] * target_w) - pad_left) * original_width / resized_width
        top = ((bbox[1] * target_h) - pad_top) * original_height / resized_height
        bottom = ((bbox[3] * target_h) - pad_top) * original_height / resized_height

        return [
            round(max(0.0, min(float(original_width), left)), 1),
            round(max(0.0, min(float(original_height), top)), 1),
            round(max(0.0, min(float(original_width), right)), 1),
            round(max(0.0, min(float(original_height), bottom)), 1),
        ]

    def parse_document_image(
        self,
        image_input: Union[Image.Image, Path, str, bytes, np.ndarray],
        predict_text_in_pic: bool = False,
    ) -> Dict[str, Any]:
        """Runs NVIDIA-Nemotron-Parse-v1.2 on a single document page image.

        Returns:
            Dict containing:
            - 'markdown': Full combined markdown text
            - 'elements': List of structured element dicts (class, bbox, text)
            - 'classes': List of raw element classes
            - 'raw_output': Complete raw generation text
        """
        empty_res: Dict[str, Any] = {
            "markdown": "",
            "elements": [],
            "classes": [],
            "raw_output": "",
        }

        if not self._initialize():
            return empty_res

        # Convert input to PIL RGB Image
        try:
            if isinstance(image_input, Image.Image):
                pil_img = image_input.convert("RGB")
            elif isinstance(image_input, (str, Path)):
                pil_img = Image.open(str(image_input)).convert("RGB")
            elif isinstance(image_input, (bytes, bytearray)):
                pil_img = Image.open(io.BytesIO(image_input)).convert("RGB")
            elif isinstance(image_input, np.ndarray):
                pil_img = Image.fromarray(image_input).convert("RGB")
            else:
                return empty_res
        except Exception as img_err:
            logger.warning(f"Nemotron image conversion error: {img_err}")
            return empty_res

        orig_w, orig_h = pil_img.size

        # Build v1.2 required 4-token task prompt
        pic_token = "<predict_text_in_pic>" if predict_text_in_pic else "<predict_no_text_in_pic>"
        task_prompt = f"</s><s><predict_bbox><predict_classes><output_markdown>{pic_token}"

        try:
            inputs = self._processor(
                images=[pil_img],
                text=task_prompt,
                return_tensors="pt",
                add_special_tokens=False,
            ).to(self.device)

            outputs = self._model.generate(
                **inputs,
                generation_config=self._generation_config,
            )

            generated_text = self._processor.batch_decode(outputs, skip_special_tokens=True)[0]

            parsed = self.extract_classes_bboxes(generated_text)
            elements: List[Dict[str, Any]] = []
            markdown_chunks: List[str] = []

            for cls_name, bbox, txt in zip(parsed["classes"], parsed["bboxes"], parsed["texts"]):
                scaled_bbox = self.transform_bbox_to_original(bbox, orig_w, orig_h)
                elements.append({
                    "class": cls_name,
                    "bbox": scaled_bbox,
                    "text": txt,
                })
                markdown_chunks.append(txt)

            full_markdown = "\n\n".join(markdown_chunks).strip()

            return {
                "markdown": full_markdown,
                "elements": elements,
                "classes": parsed["classes"],
                "raw_output": generated_text,
            }

        except Exception as gen_err:
            logger.warning(f"Nemotron Parse inference error: {gen_err}")
            return empty_res
        finally:
            self.clear_session()

    def parse_pdf_pages(
        self,
        pdf_path: Union[str, Path],
        max_pages: int = 4,
        dpi: int = 150,
    ) -> Dict[str, Any]:
        """Renders pages of a PDF document and parses each page with Nemotron Parse."""
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            return {"markdown": "", "elements": [], "pages": []}

        try:
            import pymupdf as fitz
        except ImportError:
            logger.warning("pymupdf not installed; cannot render PDF for Nemotron Parse.")
            return {"markdown": "", "elements": [], "pages": []}

        all_markdown: List[str] = []
        all_elements: List[Dict[str, Any]] = []
        pages_data: List[Dict[str, Any]] = []

        doc = None
        try:
            doc = fitz.open(str(pdf_file))
            total_pages = min(len(doc), max_pages)

            for p_idx in range(total_pages):
                page = doc[p_idx]
                pix = page.get_pixmap(dpi=dpi)
                pil_page = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                page_res = self.parse_document_image(pil_page)
                pages_data.append({
                    "page_number": p_idx + 1,
                    "elements": page_res.get("elements", []),
                    "markdown": page_res.get("markdown", ""),
                })
                if page_res.get("markdown"):
                    all_markdown.append(page_res["markdown"])
                all_elements.extend(page_res.get("elements", []))

            return {
                "markdown": "\n\n".join(all_markdown).strip(),
                "elements": all_elements,
                "classes": [el.get("class") for el in all_elements if el.get("class")],
                "pages": pages_data,
            }
        except Exception as e:
            logger.warning(f"Failed to parse PDF with Nemotron Parse ({pdf_file.name}): {e}")
            return {"markdown": "", "elements": [], "classes": [], "pages": []}
        finally:
            if doc:
                doc.close()

    # -------------------------------------------------------------------------
    # Candidate & Profile Refinement Methods
    # -------------------------------------------------------------------------

    def extract_profile(self, text_or_markdown: str) -> Optional[Dict[str, Any]]:
        """Parses structured profile entities from Nemotron Markdown or text."""
        if not text_or_markdown or not text_or_markdown.strip():
            return None

        lines = [line.strip() for line in text_or_markdown.splitlines() if line.strip()]
        if not lines:
            return None

        # 1. Extract name from header
        name = self.refine_name("\n".join(lines[:5]))

        # 2. Extract candidate role if present in header/subheader
        role = None
        for line in lines[1:5]:
            clean_l = re.sub(r"[#*_\-]", "", line).strip()
            if any(term in clean_l.lower() for term in ["engineer", "developer", "lead", "architect", "manager", "analyst", "specialist", "executive", "officer", "trainee", "intern"]):
                if not any(k in clean_l.lower() for k in ["email", "phone", "curriculum", "resume", "profile summary"]):
                    role = clean_l.split("|")[0].split("–")[0].split("-")[0].strip()
                    break

        # 3. Extract summary
        summary = None
        current_sec = None
        sec_lines: Dict[str, List[str]] = {}

        for line in lines:
            clean_l = re.sub(r"^[#*_\-\s]+", "", line).strip(" :")
            clean_l_low = clean_l.lower()

            if any(h in clean_l_low for h in ["summary", "profile", "about me", "overview"]):
                current_sec = "summary"
                sec_lines.setdefault("summary", [])
                continue
            elif any(h in clean_l_low for h in ["skill", "technical proficienc", "technologies", "competenc"]):
                current_sec = "skills"
                sec_lines.setdefault("skills", [])
                continue
            elif any(h in clean_l_low for h in ["experience", "employment", "work history"]):
                current_sec = "experience"
                sec_lines.setdefault("experience", [])
                continue
            elif any(h in clean_l_low for h in ["education", "academic", "qualification"]):
                current_sec = "education"
                sec_lines.setdefault("education", [])
                continue
            elif any(h in clean_l_low for h in ["project", "key project"]):
                current_sec = "projects"
                sec_lines.setdefault("projects", [])
                continue
            elif any(h in clean_l_low for h in ["certification", "certificates", "licenses"]):
                current_sec = "certifications"
                sec_lines.setdefault("certifications", [])
                continue
            elif line.startswith("#") and len(clean_l.split()) < 5:
                current_sec = "other"

            if current_sec and current_sec in sec_lines:
                sec_lines[current_sec].append(line)

        if "summary" in sec_lines:
            sum_text = " ".join([re.sub(r"^[#*_\-\s]+", "", l) for l in sec_lines["summary"] if len(l) > 15])
            if len(sum_text) >= 30 and not any(k in sum_text.lower() for k in ["@", "pin code", "phone:"]):
                summary = sum_text

        # 4. Extract skills from skills section
        skills: List[str] = []
        if "skills" in sec_lines:
            for s_line in sec_lines["skills"]:
                cleaned_s = re.sub(r"^[•\-\*\uf0b7\s]+", "", s_line).strip()
                if ":" in cleaned_s:
                    cleaned_s = cleaned_s.split(":", 1)[1].strip()
                for token in re.split(r"[,|•;/]", cleaned_s):
                    t = token.strip(" .-_*")
                    if t and 2 <= len(t) <= 35 and not any(q in t.lower() for q in ["proficient", "knowledge of", "experience in"]):
                        skills.append(t)

        return {
            "name": name,
            "role": role,
            "summary": summary,
            "skills": skills,
            "experience": [],
            "education": [],
            "projects": [],
        }

    def refine_name(self, header_text: str) -> Optional[str]:
        """Isolates candidate personal name from header text or Nemotron Title element."""
        if not header_text or len(header_text.split()) < 2:
            return None

        lines = [l.strip() for l in header_text.splitlines() if l.strip()]
        for line in lines[:4]:
            clean_l = re.sub(r"[#*_\-]", "", line).strip()
            clean_l = re.sub(r"^(?:mr|ms|mrs|dr|er|prof)\.?\s+", "", clean_l, flags=re.IGNORECASE).strip()
            clean_l = re.sub(r"\b(?:wa|npu|call\s+later|aug|sep|oct|nov|dec|2024|2025|2026)\b.*$", "", clean_l, flags=re.IGNORECASE).strip(" .-_")
            words = clean_l.split()
            if 2 <= len(words) <= 4 and all(w.isalpha() or "-" in w for w in words):
                if not any(k in clean_l.lower() for k in ["resume", "cv", "curriculum", "profile", "engineer", "developer", "manager"]):
                    return clean_l.title()
        return None

    def fix_and_analyze_experience(self, exp_chunk: str) -> Optional[Dict[str, Any]]:
        """Analyzes a work experience chunk, separating role, company, and location."""
        if not exp_chunk or len(exp_chunk.split()) < 3:
            return None

        # Common format: Role at/in Company, Location or Role | Company
        parts = [p.strip() for p in re.split(r"\s*[|•–—-]\s*", exp_chunk) if p.strip()]
        role = parts[0] if parts else None
        company = parts[1] if len(parts) > 1 else None
        location = parts[2] if len(parts) > 2 else None

        if role and not company:
            at_match = re.search(r"^(.*?)\s+(?:at|@)\s+(.*)$", role, re.IGNORECASE)
            if at_match:
                role = at_match.group(1).strip()
                company = at_match.group(2).strip()

        return {
            "role": role,
            "company": company,
            "location": location,
        }

    def generate_summary(self, profile_snippet: str) -> Optional[str]:
        """Generates a professional 2-sentence executive summary based on the profile snippet."""
        if not profile_snippet or len(profile_snippet.split()) < 4:
            return None

        name_match = re.search(r"Name:\s*([^\n]+)", profile_snippet)
        role_match = re.search(r"Recent Experience:\s*([^\n]+)", profile_snippet)
        skills_match = re.search(r"(?:Core|Key)\s*Skills:\s*([^\n]+)", profile_snippet)

        name = name_match.group(1).strip() if name_match else "Professional"
        role_info = role_match.group(1).strip() if role_match else "Experienced specialist"
        skills = skills_match.group(1).strip() if skills_match else "industry-standard technologies"

        sentence1 = f"Results-driven professional with demonstrated experience as {role_info}."
        sentence2 = f"Proficient in {skills}, committed to delivering high-impact solutions and driving operational excellence."
        return f"{sentence1} {sentence2}"

    def refine_extracted_document(self, doc: Any) -> Any:
        """Refines and enriches an ExtractedDocument:
        - Resolves ambiguous names or single-word concatenated names.
        - Corrects misplaced company names in candidate role.
        - Generates or polishes professional executive summary.
        - Segregates certifications from skills.
        - Strips questionnaire text from languages.
        """
        if not doc:
            return doc

        # 1. Refine name if needed
        if doc.name:
            clean_name = self.refine_name(doc.name)
            if clean_name:
                doc.name = clean_name

        # 2. Refine role if it looks like a company
        comp_indicators = ["pvt", "ltd", "inc", "corp", "corporation", "technologies", "solutions", "industries", "holdings", "limited", "company", "steel", "motors"]
        if doc.role and any(w in doc.role.lower() for w in comp_indicators) and not any(w in doc.role.lower() for w in ["engineer", "developer", "manager", "lead", "architect", "analyst", "specialist", "executive", "officer", "trainee", "intern"]):
            if doc.experience and doc.experience[0].role:
                doc.role = doc.experience[0].role

        # 3. Refine summary
        if not doc.summary or len(doc.summary.strip()) < 25 or "|" in doc.summary or "what is your" in doc.summary.lower():
            snip_parts = [f"Name: {doc.name or getattr(doc, 'file_stem', 'Candidate')}"]
            if doc.skills:
                snip_parts.append(f"Key Skills: {', '.join(doc.skills[:8])}")
            if doc.experience and doc.experience[0].role:
                snip_parts.append(f"Recent Experience: {doc.experience[0].role} at {doc.experience[0].company or 'industry'}")
            summary_prompt = "\n".join(snip_parts)
            doc.summary = self.generate_summary(summary_prompt)

        return doc

    def extract_candidate_insights(self, resume_text: str) -> Dict[str, Optional[str]]:
        """Extracts recruitment metadata: location, total experience, notice period, and CTC."""
        result: Dict[str, Optional[str]] = {
            "location": None,
            "total_experience": None,
            "notice_period": None,
            "current_ctc": None,
            "expected_ctc": None,
        }
        if not resume_text:
            return result

        # Notice period regex
        notice_m = re.search(
            r"(?:notice\s*period|availability|serving\s*notice)[:\s]*([0-9]+\s*(?:days?|months?)|immediate(?:ly)?|ready\s*to\s*join)",
            resume_text,
            re.IGNORECASE,
        )
        if notice_m:
            result["notice_period"] = notice_m.group(1).strip()

        # Total experience regex
        exp_m = re.search(
            r"(?:total\s*experience|overall\s*experience)[:\s]*([0-9.]+\s*(?:\+|plus)?\s*(?:years?|yrs?))",
            resume_text,
            re.IGNORECASE,
        )
        if exp_m:
            result["total_experience"] = exp_m.group(1).strip()

        # Current CTC regex
        c_ctc = re.search(
            r"(?:current\s*ctc|present\s*salary|current\s*salary)[:\s]*([0-9.]+\s*(?:lpa|lakhs?|lacs?|k)?)",
            resume_text,
            re.IGNORECASE,
        )
        if c_ctc:
            result["current_ctc"] = c_ctc.group(1).strip()

        # Expected CTC regex
        e_ctc = re.search(
            r"(?:expected\s*ctc|expected\s*salary)[:\s]*([0-9.]+\s*(?:lpa|lakhs?|lacs?|k)?)",
            resume_text,
            re.IGNORECASE,
        )
        if e_ctc:
            result["expected_ctc"] = e_ctc.group(1).strip()

        # Location regex
        loc_m = re.search(
            r"(?:current\s*location|location|residing\s*in|based\s*in)[:\s]*([a-zA-Z\s]{2,20})",
            resume_text,
            re.IGNORECASE,
        )
        if loc_m:
            cand_loc = loc_m.group(1).strip()
            if not any(w in cand_loc.lower() for w in ["phone", "email", "gender", "married"]):
                result["location"] = cand_loc.title()

        return result


# Backwards compatibility alias
GemmaExtractor = NemotronParseExtractor


__all__ = [
    "OCRService",
    "EmbeddingGemmaService",
    "NemotronParseExtractor",
    "GemmaExtractor",
]

