"""Command-line interface (CLI) for running the File Manifest Service."""

import argparse
import json
import logging
import sys
from pathlib import Path

from app.core.config import settings
from app.services.file_manifest.service import FileManifestService


def setup_cli_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(
        description="CVForge File Manifest & Document Extraction Service CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--path",
        "-p",
        type=str,
        default=None,
        help="Path to documents folder (defaults to FilePath from .env)",
    )
    parser.add_argument(
        "--output-folder",
        "-o",
        type=str,
        default=None,
        help="Subfolder name for extracted JSON files (defaults to 'Extracted data')",
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        default=None,
        help="Process a single document file instead of the whole directory",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Recursively scan subdirectories for documents",
    )
    parser.add_argument(
        "--status",
        "-s",
        action="store_true",
        help="Check document discovery and extraction status only",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose debug logging",
    )

    args = parser.parse_args()
    setup_cli_logging(args.verbose)

    service = FileManifestService(
        config=settings,
        base_path=args.path,
        extracted_data_folder_name=args.output_folder,
    )

    if args.status:
        status_info = service.get_manifest_status(args.path)
        print(json.dumps(status_info, indent=2))
        return

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: File '{file_path}' does not exist.", file=sys.stderr)
            sys.exit(1)
        result = service.process_file(file_path)
        print(
            f"Extraction complete for '{result.file_name}'. Status: {result.status}"
        )
        if result.json_output_path:
            print(f"Saved to: {result.json_output_path}")
        return

    # Process all files in directory
    print(f"Scanning directory: {service.base_dir}")
    print(f"Destination folder: {service.extracted_data_dir}")
    summary = service.process_all(
        directory_path=args.path,
        recursive=args.recursive,
    )

    print("\n" + "=" * 60)
    print("FILE MANIFEST EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"Total documents found: {summary.total_files_found}")
    print(f"Successfully processed: {summary.total_success}")
    print(f"Failed: {summary.total_failed}")
    print(f"Extracted folder: {summary.extracted_data_directory}")
    print("=" * 60)

    for item in summary.files:
        status_badge = "✓ OK" if item.status == "success" else "✗ ERR"
        name_info = f"({item.candidate_name})" if item.candidate_name else ""
        print(f"[{status_badge}] {item.file_name} {name_info} -> {item.json_file_name}")


if __name__ == "__main__":
    main()
