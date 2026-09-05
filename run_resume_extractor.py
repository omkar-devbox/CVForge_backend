#!/usr/bin/env python3
"""Runner script for Resume Extraction, Image Saving, and Embedding Generation."""

import argparse
import json
import logging
from pathlib import Path
import sys

# Add project root to sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.services.file_manifest.service import FileManifestService


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Suppress verbose 3rd party parser noise (e.g. pdfminer FontBBox warnings) unless verbose
    noisy_loggers = [
        "pdfminer",
        "pdfminer.pdffont",
        "pdfminer.pdfinterp",
        "pdfminer.pdfpage",
        "pdfminer.pdfdocument",
        "pdfminer.cmapdb",
        "pdfminer.converter",
        "pdfplumber",
        "PIL",
        "urllib3",
        "transformers",
    ]
    for noisy in noisy_loggers:
        nl = logging.getLogger(noisy)
        nl.setLevel(logging.ERROR if not verbose else logging.INFO)
        nl.propagate = False



def main():
    parser = argparse.ArgumentParser(
        description="Extract structured candidate profiles, images, and embeddings from resumes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--path",
        "-p",
        type=str,
        default="/home/omkar/Documents/System Mech/Data for AI/resumes",
        help="Path to folder containing resumes (PDF, DOCX, DOC)",
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        default=None,
        help="Path to a single resume file to process",
    )
    parser.add_argument(
        "--output-folder",
        "-o",
        type=str,
        default="Extracted data",
        help="Subfolder name for extracted JSON files and images",
    )
    parser.add_argument(
        "--no-embedding",
        action="store_true",
        help="Disable EmbeddingGemma vector computation",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Disable persisting extracted data into PostgreSQL database (cvforge_dev)",
    )

    parser.add_argument(
        "--use-gemma",
        dest="use_gemma",
        action="store_true",
        default=True,
        help="Use offline google/gemma-3-270m ONNX model for candidate extraction (default: True)",
    )
    parser.add_argument(
        "--no-gemma",
        "--no-llm",
        dest="no_gemma",
        action="store_true",
        help="Disable offline Gemma-3-270m model and use pure rule-based extractor",
    )
    parser.add_argument(
        "--gemma-model",
        type=str,
        default="/home/omkar/Documents/System Mech/gemma-3-270m-it-ONNX",
        help="Path to local directory with google/gemma-3-270m ONNX model files",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Scan directory recursively",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose debug logs",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    enable_llm = False if args.no_gemma else args.use_gemma

    service = FileManifestService(
        config=settings,
        base_path=args.path,
        extracted_data_folder_name=args.output_folder,
        enable_llm=enable_llm,
        gemma_model_dir=args.gemma_model,
        save_to_db=not args.no_db,
    )

    if args.file:
        file_path = Path(args.file).resolve()
        if not file_path.exists():
            print(f"Error: File '{file_path}' does not exist.", file=sys.stderr)
            sys.exit(1)

        print(f"\nProcessing single file: {file_path.name}")
        doc = service.process_file(
            file_path,
            save_json=True,
            compute_embedding=not args.no_embedding,
            save_to_db=not args.no_db,
        )
        print(f"Status: {doc.status.upper()}")
        print(f"Candidate: {doc.name}")
        print(f"Role: {doc.role}")
        print(f"Contact No: {doc.contact_no}")
        print(f"Emails: {doc.email}")
        if doc.summary:
            print(f"Summary: {doc.summary[:80]}...")
        print(f"Skills: {doc.skills[:8]}...")
        print(f"Experience items: {len(doc.experience)}")
        print(f"Education items: {len(doc.education)}")
        print(f"Projects items: {len(doc.projects)}")
        print(f"Certifications: {len(doc.certifications)}")
        print(f"Tools: {doc.tools}")
        if doc.ats_score:
            score_val = getattr(doc.ats_score, "overall_score", None) or (doc.ats_score.get("overall_score") if isinstance(doc.ats_score, dict) else None)
            grade_val = getattr(doc.ats_score, "grade", None) or (doc.ats_score.get("grade") if isinstance(doc.ats_score, dict) else None)
            print(f"ATS Score: {score_val}/100 [{grade_val}]")
        print(f"Images extracted: {len(doc.images)}")
        print(f"Embedding generated: {'Yes (768-dim)' if doc.embedding else 'No'}")
        print(f"Database sync: {'cvforge_dev (saved/updated)' if not args.no_db else 'Disabled'}")
        print(f"Saved JSON: {doc.json_output_path}\n")
        return

    llm_info = (
        "google/gemma-3-270m (ONNX)"
        if (service.enable_llm and Path(args.gemma_model).exists())
        else "Disabled (Rule-based)"
    )

    print(f"\n============================================================")
    print(f"  CVForge Resume Extraction & Embedding Pipeline")
    print(f"============================================================")
    print(f"Source Directory:       {service.base_dir}")
    print(f"Destination Directory:  {service.extracted_data_dir}")
    print(f"Database Target:        {'cvforge_dev (PostgreSQL)' if not args.no_db else 'Disabled'}")
    print(f"LLM Model:              {llm_info}")
    print(f"Embedding Model:        embeddinggemma-onnx-embeddinggemma-300m-v1")
    print(f"============================================================\n")

    summary = service.process_all(
        directory_path=args.path,
        recursive=args.recursive,
        compute_embedding=not args.no_embedding,
        save_to_db=not args.no_db,
    )

    print("\n" + "=" * 60)
    print("EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"Total documents found:   {summary.total_files_found}")
    print(f"Successfully processed:  {summary.total_success}")
    print(f"Failed:                  {summary.total_failed}")
    print(f"Output directory:        {summary.extracted_data_directory}")
    print("=" * 60)

    for item in summary.files:
        badge = "✓" if item.status == "success" else "✗"
        emb = " [768-emb]" if item.has_embedding else ""
        imgs = f" [{item.images_count} img]" if item.images_count > 0 else ""
        name = f" ({item.candidate_name})" if item.candidate_name else ""
        role = f" [{item.role}]" if getattr(item, "role", None) else ""
        print(f"[{badge}] {item.file_name}{name}{role}{imgs}{emb} -> {item.json_file_name}")

    print("\nAll done!")


if __name__ == "__main__":
    main()

