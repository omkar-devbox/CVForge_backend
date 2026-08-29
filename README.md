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

Extract structured candidate profiles, images, and embeddings from resumes:
```bash
# Process all resumes in Data for AI/resumes
python run_resume_extractor.py

# Process a single resume file
python run_resume_extractor.py --file "../Data for AI/resumes/ALOK KUMAR.docx"
```

Features:
- **Candidate Profiling**: Name, Contact No, Email, Links (`github`, `linkedin`, `portfolio`), Skills, Education, Experience.
- **Image Saving**: Extracts profile pictures/media into `Extracted data/images/<candidate_name>/`.
- **Embeddings**: Computes 768-dimensional normalized dense vectors using `embeddinggemma-onnx-embeddinggemma-300m-v1`.

### 6. Running Tests

Run full test suite with pytest:
```bash
pytest -v
```
