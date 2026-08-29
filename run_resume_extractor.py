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

    service = FileManifestService(
        config=settings,
        base_path=args.path,
        extracted_data_folder_name=args.output_folder,
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
        )
        print(f"Status: {doc.status.upper()}")
        print(f"Candidate: {doc.name}")
        print(f"Contact No: {doc.contact_no}")
        print(f"Emails: {doc.email}")
        print(f"Skills: {doc.skills[:6]}...")
        print(f"Experience items: {len(doc.experience)}")
        print(f"Education items: {len(doc.education)}")
        print(f"Images extracted: {len(doc.images)}")
        print(f"Embedding generated: {'Yes (768-dim)' if doc.embedding else 'No'}")
        print(f"Saved JSON: {doc.json_output_path}\n")
        return

    print(f"\n============================================================")
    print(f"  CVForge Resume Extraction & Embedding Pipeline")
    print(f"============================================================")
    print(f"Source Directory:       {service.base_dir}")
    print(f"Destination Directory:  {service.extracted_data_dir}")
    print(f"Embedding Model:        embeddinggemma-onnx-embeddinggemma-300m-v1")
    print(f"============================================================\n")

    summary = service.process_all(
        directory_path=args.path,
        recursive=args.recursive,
        compute_embedding=not args.no_embedding,
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
        print(f"[{badge}] {item.file_name}{name}{imgs}{emb} -> {item.json_file_name}")

    print("\nAll done!")


if __name__ == "__main__":
    main()
