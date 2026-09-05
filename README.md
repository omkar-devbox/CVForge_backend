# CVForge Backend

Production-ready modular FastAPI backend for CVForge.

## Directory Structure

```
CVForge_backend
│
├── app/
│   ├── main.py                # FastAPI entrypoint, middleware & error handler registration
│   │
│   ├── api/
│   │   ├── router.py          # Combined API Router (/api/v1)
│   │   │
│   │   └── students/          # Students domain
│   │       ├── router.py      # Endpoints (CRUD /students)
│   │       ├── schemas.py     # Student request/response schemas
│   │       └── service.py     # Student business logic & pagination
│   │
│   ├── core/
│   │   ├── config.py          # App settings via pydantic-settings
│   │   ├── database.py        # SQLAlchemy engine, session maker & Base
│   │   └── exceptions.py      # Custom exceptions & global HTTP exception handlers
│   │
│   ├── models/                # SQLAlchemy database models
│   │   └── student.py         # Student entity table
│   │
│   ├── repositories/          # Data Access Object (DAO) pattern
│   │   └── student.py         # Student DB queries
│   │
│   ├── middleware/            # Custom HTTP middleware components
│   │   ├── tenant.py          # Multi-tenant header context (X-Tenant-ID)
│   │   └── logging.py         # Request logging & execution timing
│   │
│   └── utils/                 # Utility helpers
│       ├── response.py        # Standardized API response formatters
│       ├── pagination.py      # Pagination models & metadata helpers
│       └── helpers.py         # Common helper functions
│
├── migrations/                # Alembic database migration scripts
├── tests/                     # Pytest automated test suite
├── .env                       # Local environment variables
├── pyproject.toml             # Project dependencies & build settings
└── README.md                  # Documentation
```

## Quick Start

### 1. Environment & Virtual Environment Setup

Create and activate a Python virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Linux/macOS
# .venv\Scripts\activate   # On Windows
```

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### 2. Install Dependencies

Install packages in editable mode:
```bash
pip install -e .
```

### 3. Run Development Server

Launch Uvicorn development server with auto-reload:
```bash
uvicorn app.main:app --reload --port 8000
```

Access Interactive OpenAPI Docs:
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 4. Running Database Migrations

Generate migration:
```bash
alembic revision --autogenerate -m "Initial schema"
```

Apply migrations:
```bash
alembic upgrade head
```

### 5. Running Resume Extraction & Embedding Pipeline

Extract structured candidate profiles, images, and embeddings from resumes (PDF, DOCX, DOC) using the local offline multi-stage extraction engine.

#### 🚀 Commands to Run All Files

```bash
# Ensure virtual environment is activated:
source .venv/bin/activate

# 1. RUN ALL FILES in default folder (Data for AI/resumes):
python run_resume_extractor.py

# 2. RUN ALL FILES RECURSIVELY (scans all subdirectories & folders):
python run_resume_extractor.py --recursive

# 3. RUN ALL FILES in a specific custom path:
python run_resume_extractor.py --path "/home/omkar/Documents/System Mech/Data for AI/resumes" --recursive

# 4. RUN ALL FILES with custom output destination:
python run_resume_extractor.py --path "/path/to/resumes" --output-folder "Extracted data" --recursive

# 5. RUN ALL FILES with offline Gemma-3-270m LLM text analysis & fixing:
python run_resume_extractor.py --recursive --use-gemma

# 6. RUN ALL FILES in Ultra-Fast Mode (Pure rule-based, skips LLM for 10x faster batching):
python run_resume_extractor.py --recursive --no-gemma

# 7. RUN ALL FILES without computing vector embeddings:
python run_resume_extractor.py --recursive --no-embedding

# 8. RUN ALL FILES directly using virtual environment binary (no activation required):
.venv/bin/python run_resume_extractor.py --recursive

# 9. RUN ALL FILES with verbose real-time debug logging:
python run_resume_extractor.py --recursive --verbose
```

#### 📄 Commands to Run a Single File

```bash
# Process single DOCX file:
python run_resume_extractor.py --file "/home/omkar/Documents/System Mech/Data for AI/resumes/ALOK KUMAR.docx"

# Process single PDF file:
python run_resume_extractor.py --file "/home/omkar/Documents/System Mech/Data for AI/resumes/AkashPatil.pdf"

# Process single legacy DOC file (auto-converted via LibreOffice):
python run_resume_extractor.py --file "/home/omkar/Documents/System Mech/Data for AI/resumes/Goraksha Adhane.doc"
```

#### Gemma-3-270m LLM Usage

The extractor uses **`google/gemma-3-270m`** locally via ONNX Runtime:
- **Location**: `/home/omkar/Documents/System Mech/gemma-3-270m-it-ONNX`
- **Models Included**: `onnx/model_q4.onnx` (~308MB) and `onnx/model_quantized.onnx` (~520MB).
- **Zero Cloud Calls**: 100% private, offline inference with zero OpenAI API calls or keys required.
- **Auto-Fallback**: If the model is not found or inference fails on a corrupted document, the system automatically falls back to the high-precision regex section engine.

```bash
# Explicitly enable Gemma LLM:
python run_resume_extractor.py --use-gemma

# Use custom Gemma model location:
python run_resume_extractor.py --gemma-model "/path/to/custom/gemma-3-270m"

# Disable Gemma LLM (pure rule-based):
python run_resume_extractor.py --no-gemma
```

#### CLI Options Reference
| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--path` | `-p` | `Data for AI/resumes` | Directory path containing resumes to process |
| `--file` | `-f` | `None` | Process a single file instead of full directory |
| `--output-folder` | `-o` | `Extracted data` | Subfolder name for generated JSON and images |
| `--use-gemma` | | `True` | Use offline Gemma-3-270m ONNX model for extraction |
| `--no-gemma` | `--no-llm` | `False` | Disable offline Gemma-3-270m model (use rule-based parser) |
| `--gemma-model` | | `.../gemma-3-270m-it-ONNX` | Path to offline Gemma-3-270m model directory |
| `--no-embedding` | | `False` | Disable vector embedding computation |
| `--recursive` | `-r` | `False` | Scan directory recursively for resumes |
| `--verbose` | `-v` | `False` | Enable verbose debug logs |

#### Extraction Pipeline Stack
- **PDF Text**: PyMuPDF (`fitz` / `pymupdf`) text and embedded image extraction.
- **PDF Tables & Layout**: `pdfplumber` structured table extraction.
- **Scanned PDF OCR**: `OCRService` with PaddleOCR integration for scanned/image documents.
- **Word Documents (`.docx`)**: `python-docx` for paragraphs, tables, and profile images.
- **Legacy Word (`.doc`)**: Headless LibreOffice (`soffice`) `.doc` $\rightarrow$ `.docx` auto-conversion.
- **HTML / Markdown Cleanup**: `BeautifulSoup` & regex noise, entity, and tag stripping.
- **Section Detection**: Regex + custom parser for Summary, Experience, Education, Skills.
- **Local Offline LLM**: `google/gemma-3-270m` ONNX model (100% offline, zero cloud API).
- **Skill Normalization**: `RapidFuzz` deduplication and canonical variant mapping.
- **Date Parsing**: `dateparser` normalization of duration strings to ISO start/end dates.
- **Embeddings**: `embeddinggemma-onnx-embeddinggemma-300m-v1` (768-dimensional vectors).

### 6. Running Tests

Run test suites using pytest:
```bash
# Run new data extraction pipeline tests:
.venv/bin/python -m pytest tests/test_new_data_extractors.py -v

# Run all backend tests:
.venv/bin/python -m pytest -v
```

