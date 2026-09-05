-- ============================================================
-- CVFORGE
-- DOCUMENT EXTRACTION SYSTEM
-- PostgreSQL Schema
--
-- TOTAL TABLES: 8
-- ============================================================


-- ============================================================
-- 0. CREATE DATABASE
-- ============================================================
-- Run separately if required:
--
-- CREATE DATABASE cvforge;
--
-- Then connect to cvforge.


-- ============================================================
-- 1. CREATE POSTGRESQL SCHEMAS
-- ============================================================

CREATE SCHEMA IF NOT EXISTS project;
CREATE SCHEMA IF NOT EXISTS document;
CREATE SCHEMA IF NOT EXISTS structure;
CREATE SCHEMA IF NOT EXISTS extraction;


-- ============================================================
-- 2. UPDATED_AT FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- ============================================================
-- PROJECT
-- ============================================================
-- ============================================================


-- ============================================================
-- 3. PROJECTS
-- ============================================================

CREATE TABLE project.projects (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    name VARCHAR(255) NOT NULL,

    description TEXT,

    -- cv, invoice, legal, form, resume, custom
    project_type VARCHAR(100) NOT NULL,

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Ownership
    user_id BIGINT,

    -- Audit
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Soft Delete
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by BIGINT,
    deleted_at TIMESTAMPTZ
);


-- ============================================================
-- 4. FIELD DEFINITIONS
-- ============================================================

CREATE TABLE project.field_definitions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Project Reference
    project_id BIGINT NOT NULL
        REFERENCES project.projects(id)
        ON DELETE CASCADE,

    -- Ownership
    user_id BIGINT,

    -- Field Information
    field_name VARCHAR(500) NOT NULL,

    -- string / number / boolean / date / array / object
    field_type VARCHAR(50) NOT NULL
        CHECK (
            field_type IN (
                'string',
                'number',
                'boolean',
                'date',
                'array',
                'object'
            )
        ),

    description TEXT,

    -- Field Configuration
    is_required BOOLEAN NOT NULL DEFAULT FALSE,

    -- Instructions for Extraction Engine / LLM
    extraction_prompt TEXT,

    -- Validation Rules
    validation_rules JSONB NOT NULL DEFAULT '{}'::JSONB,

    -- Display / Extraction Order
    display_order INT NOT NULL DEFAULT 0,

    -- Audit
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Soft Delete
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by BIGINT,
    deleted_at TIMESTAMPTZ
);


-- ============================================================
-- PROJECT INDEXES
-- ============================================================

CREATE INDEX idx_projects_user_id
ON project.projects(user_id);

CREATE INDEX idx_projects_active
ON project.projects(user_id)
WHERE is_deleted = FALSE
  AND is_active = TRUE;

CREATE INDEX idx_field_definitions_project_id
ON project.field_definitions(project_id);


-- Same field name cannot repeat in active project
CREATE UNIQUE INDEX uq_field_definitions_project_name
ON project.field_definitions(project_id, field_name)
WHERE is_deleted = FALSE;


-- ============================================================
-- PROJECT TRIGGERS
-- ============================================================

CREATE TRIGGER trg_projects_updated_at
BEFORE UPDATE ON project.projects
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


CREATE TRIGGER trg_field_definitions_updated_at
BEFORE UPDATE ON project.field_definitions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- ============================================================
-- DOCUMENT
-- ============================================================
-- ============================================================


-- ============================================================
-- 5. DOCUMENTS
-- ============================================================

CREATE TABLE document.documents (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Project Reference
    project_id BIGINT NOT NULL
        REFERENCES project.projects(id)
        ON DELETE CASCADE,

    -- File Information
    file_name VARCHAR(500) NOT NULL,

    file_url TEXT NOT NULL,

    mime_type VARCHAR(100),

    file_size BIGINT
        CHECK (
            file_size IS NULL
            OR file_size >= 0
        ),

    document_hash VARCHAR(128),

    -- Processing Status
    status VARCHAR(30) NOT NULL DEFAULT 'uploaded'
        CHECK (
            status IN (
                'uploaded',
                'processing',
                'processed',
                'failed'
            )
        ),

    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,

    -- Audit
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Soft Delete
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by BIGINT,
    deleted_at TIMESTAMPTZ
);


-- ============================================================
-- 6. DOCUMENT VERSIONS
-- ============================================================

CREATE TABLE document.document_versions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Document Reference
    document_id BIGINT NOT NULL
        REFERENCES document.documents(id)
        ON DELETE CASCADE,

    -- Version Information
    version_number INT NOT NULL
        CHECK (version_number > 0),

    file_url TEXT,

    document_hash VARCHAR(128),

    -- Audit
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Soft Delete
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by BIGINT,
    deleted_at TIMESTAMPTZ
);


-- ============================================================
-- 7. DOCUMENT PAGES
-- ============================================================

CREATE TABLE document.document_pages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Document Reference
    document_id BIGINT NOT NULL
        REFERENCES document.documents(id)
        ON DELETE CASCADE,

    page_number INT NOT NULL
        CHECK (page_number > 0),

    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,

    -- Audit
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Soft Delete
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by BIGINT,
    deleted_at TIMESTAMPTZ
);


-- ============================================================
-- DOCUMENT INDEXES
-- ============================================================

CREATE INDEX idx_documents_project_id
ON document.documents(project_id);

CREATE INDEX idx_documents_status
ON document.documents(status);

CREATE INDEX idx_documents_hash
ON document.documents(document_hash);

CREATE INDEX idx_document_versions_document_id
ON document.document_versions(document_id);

CREATE INDEX idx_document_pages_document_id
ON document.document_pages(document_id);


-- ============================================================
-- DOCUMENT UNIQUE INDEXES
-- ============================================================

CREATE UNIQUE INDEX uq_document_versions
ON document.document_versions(document_id, version_number)
WHERE is_deleted = FALSE;


CREATE UNIQUE INDEX uq_document_pages
ON document.document_pages(document_id, page_number)
WHERE is_deleted = FALSE;


-- ============================================================
-- DOCUMENT TRIGGERS
-- ============================================================

CREATE TRIGGER trg_documents_updated_at
BEFORE UPDATE ON document.documents
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


CREATE TRIGGER trg_document_versions_updated_at
BEFORE UPDATE ON document.document_versions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


CREATE TRIGGER trg_document_pages_updated_at
BEFORE UPDATE ON document.document_pages
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- ============================================================
-- STRUCTURE
-- ============================================================
-- ============================================================


-- ============================================================
-- 8. BLOCKS
-- ============================================================

CREATE TABLE structure.blocks (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Page Reference
    page_id BIGINT NOT NULL
        REFERENCES document.document_pages(id)
        ON DELETE CASCADE,

    -- Entire Page Layout / Blocks / Layers stored in metadata JSONB
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,

    -- Audit
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Soft Delete
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by BIGINT,
    deleted_at TIMESTAMPTZ
);


-- ============================================================
-- STRUCTURE INDEXES
-- ============================================================

CREATE INDEX idx_blocks_page_id
ON structure.blocks(page_id);


-- ============================================================
-- STRUCTURE TRIGGER
-- ============================================================

CREATE TRIGGER trg_blocks_updated_at
BEFORE UPDATE ON structure.blocks
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- ============================================================
-- EXTRACTION
-- ============================================================
-- ============================================================


-- ============================================================
-- 9. EXTRACTIONS
-- ============================================================

CREATE TABLE extraction.extractions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Document Reference
    document_id BIGINT NOT NULL
        REFERENCES document.documents(id)
        ON DELETE CASCADE,

    -- Extractor Information
    extractor_name VARCHAR(255),

    extractor_version VARCHAR(100),

    -- ocr / llm / rule_based / hybrid / custom
    extraction_type VARCHAR(100),

    -- Processing Status
    status VARCHAR(30) NOT NULL DEFAULT 'processing'
        CHECK (
            status IN (
                'processing',
                'completed',
                'failed',
                'review_required'
            )
        ),

    -- Processing Information
    processing_time_ms BIGINT
        CHECK (
            processing_time_ms IS NULL
            OR processing_time_ms >= 0
        ),

    -- Overall Confidence: 0 - 100
    overall_confidence NUMERIC(5,2)
        CHECK (
            overall_confidence IS NULL
            OR (
                overall_confidence >= 0
                AND overall_confidence <= 100
            )
        ),

    error_message TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,

    -- Audit
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Soft Delete
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by BIGINT,
    deleted_at TIMESTAMPTZ
);


-- ============================================================
-- 10. EXTRACTION DATA
-- ============================================================

CREATE TABLE extraction.extraction_data (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Extraction Reference
    extraction_id BIGINT NOT NULL
        REFERENCES extraction.extractions(id)
        ON DELETE CASCADE,

    -- Field Definition Reference
    field_definition_id BIGINT NOT NULL
        REFERENCES project.field_definitions(id)
        ON DELETE RESTRICT,

    -- Extracted Value
    value JSONB,

    -- Extraction Confidence: 0 - 100
    confidence NUMERIC(5,2)
        CHECK (
            confidence IS NULL
            OR (
                confidence >= 0
                AND confidence <= 100
            )
        ),

    -- Source Block
    source_block_id BIGINT
        REFERENCES structure.blocks(id)
        ON DELETE SET NULL,

    -- Original source text
    source_text TEXT,

    -- Audit
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Soft Delete
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by BIGINT,
    deleted_at TIMESTAMPTZ
);


-- ============================================================
-- 11. CANDIDATE PROFILES (Domain & Core Summary)
-- ============================================================

CREATE TABLE extraction.candidate_profiles (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Document & Extraction References
    document_id BIGINT NOT NULL
        REFERENCES document.documents(id)
        ON DELETE CASCADE,

    extraction_id BIGINT NOT NULL
        REFERENCES extraction.extractions(id)
        ON DELETE CASCADE,

    -- Candidate Core Information
    name VARCHAR(255),
    email VARCHAR(255),
    contact_no VARCHAR(100),
    role VARCHAR(255),
    skills TEXT,
    experience TEXT,
    education TEXT,

    -- Candidate Status & Recruitment Insights
    status VARCHAR(100) DEFAULT 'Active',
    source VARCHAR(255),
    location VARCHAR(255),
    total_experience VARCHAR(100),
    notice_period VARCHAR(100),
    current_ctc VARCHAR(100),
    expected_ctc VARCHAR(100),
    note TEXT,

    -- Overall Domain Profile (e.g. Mechanical, Software, Civil, Electrical, etc.)
    overall_profile VARCHAR(100),

    -- Audit
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Soft Delete
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by BIGINT,
    deleted_at TIMESTAMPTZ
);


-- ============================================================
-- EXTRACTION INDEXES
-- ============================================================

CREATE INDEX idx_extractions_document_id
ON extraction.extractions(document_id);

CREATE INDEX idx_extractions_status
ON extraction.extractions(status);

CREATE INDEX idx_extraction_data_extraction_id
ON extraction.extraction_data(extraction_id);

CREATE INDEX idx_extraction_data_field_definition_id
ON extraction.extraction_data(field_definition_id);

CREATE INDEX idx_extraction_data_source_block_id
ON extraction.extraction_data(source_block_id);

CREATE INDEX idx_candidate_profiles_document_id
ON extraction.candidate_profiles(document_id);

CREATE INDEX idx_candidate_profiles_extraction_id
ON extraction.candidate_profiles(extraction_id);

CREATE INDEX idx_candidate_profiles_overall_profile
ON extraction.candidate_profiles(overall_profile);


-- ============================================================
-- EXTRACTION UNIQUE INDEXES
-- ============================================================

CREATE UNIQUE INDEX uq_extraction_data_field
ON extraction.extraction_data(
    extraction_id,
    field_definition_id
)
WHERE is_deleted = FALSE;

CREATE UNIQUE INDEX uq_candidate_profiles_extraction
ON extraction.candidate_profiles(extraction_id)
WHERE is_deleted = FALSE;


-- ============================================================
-- EXTRACTION TRIGGERS
-- ============================================================

CREATE TRIGGER trg_extractions_updated_at
BEFORE UPDATE ON extraction.extractions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


CREATE TRIGGER trg_extraction_data_updated_at
BEFORE UPDATE ON extraction.extraction_data
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


CREATE TRIGGER trg_candidate_profiles_updated_at
BEFORE UPDATE ON extraction.candidate_profiles
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- ============================================================
-- FINAL RELATIONSHIP
-- ============================================================
-- ============================================================

/*

PROJECT
  |
  +-- projects
  |
  +-- field_definitions
          |
          | field_definition_id
          |
          v
DOCUMENT
  |
  +-- documents
  |      |
  |      +-- document_versions
  |
  +-- document_pages
          |
          v
       blocks
          |
          | source_block_id
          |
          v
EXTRACTION
  |
  +-- extractions
          |
          v
      extraction_data
          |
          +-- field_definition_id
          |
          +-- source_block_id


MAIN FLOW:

projects
    |
    +---- documents
              |
              +---- document_pages
                        |
                        +---- blocks
              |
              +---- document_versions
              |
              +---- extractions
                        |
                        +---- extraction_data
                                  |
                                  +---- field_definitions


CV EXAMPLE:

Project
  |
  +-- CV Extraction
       |
       +-- Field Definitions
       |     |
       |     +-- full_name
       |     +-- email
       |     +-- phone
       |     +-- skills
       |     +-- experience
       |
       +-- Document
             |
             +-- Pages
             |    |
             |    +-- Page 1
             |         |
             |         +-- Blocks
             |              +-- Name
             |              +-- Email
             |              +-- Skills
             |
             +-- Extraction
                  |
                  +-- Extraction Data
                       |
                       +-- full_name -> "Omkar"
                       |       |
                       |       +-- field_definition_id
                       |       +-- source_block_id
                       |
                       +-- email -> "omkar@gmail.com"
                       |       |
                       |       +-- field_definition_id
                       |       +-- source_block_id
                       |
                       +-- skills -> ["Python","SQL"]
                               |
                               +-- field_definition_id
                               +-- source_block_id

*/