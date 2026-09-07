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

# 5. RUN ALL FILES with NVIDIA-Nemotron-Parse-v1.2 document parsing & candidate extraction:
python run_resume_extractor.py --recursive --use-nemotron

# 6. RUN ALL FILES in Ultra-Fast Mode (Pure rule-based, skips model for 10x faster batching):
python run_resume_extractor.py --recursive --no-nemotron

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

#### NVIDIA-Nemotron-Parse-v1.2 Usage

The extractor uses **`nvidia/NVIDIA-Nemotron-Parse-v1.2`** for vision-language document parsing and candidate extraction:
- **Location**: `/home/omkar/Documents/System Mech/NVIDIA-Nemotron-Parse-v1.2` (or HuggingFace Hub `nvidia/NVIDIA-Nemotron-Parse-v1.2`)
- **Features**: Visual layout detection, normalized bounding boxes (`<predict_bbox>`), semantic classes (`<predict_classes>`), reading-order Markdown (`<output_markdown>`).
- **Zero Cloud Calls**: Runs locally on CUDA or CPU with zero OpenAI API calls or keys required.
- **Auto-Fallback**: If the model is not found or inference fails on a corrupted document, the system automatically falls back to the high-precision regex section engine.

```bash
# Explicitly enable Nemotron model:
python run_resume_extractor.py --use-nemotron

# Use custom model location:
python run_resume_extractor.py --nemotron-model "/path/to/custom/NVIDIA-Nemotron-Parse-v1.2"

# Disable model (pure rule-based):
python run_resume_extractor.py --no-nemotron
```

#### CLI Options Reference
| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--path` | `-p` | `Data for AI/resumes` | Directory path containing resumes to process |
| `--file` | `-f` | `None` | Process a single file instead of full directory |
| `--output-folder` | `-o` | `Extracted data` | Subfolder name for generated JSON and images |
| `--use-nemotron` | `--use-gemma` | `True` | Use nvidia/NVIDIA-Nemotron-Parse-v1.2 for parsing |
| `--no-nemotron` | `--no-llm` | `False` | Disable Nemotron model (use pure rule-based parser) |
| `--nemotron-model` | `--gemma-model` | `.../NVIDIA-Nemotron-Parse-v1.2` | Path or HuggingFace ID for model |
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
- **Vision-Language Document Parser**: `nvidia/NVIDIA-Nemotron-Parse-v1.2` document model.
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

