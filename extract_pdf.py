"""
Generic PDF Extractor — extracts text, formulas, images, and tables from PDFs.

Output structure per PDF:
    extracted/<pdf_name>/
    ├── content.md              # Markdown with proper artifact references
    ├── content_map.json        # Structured content map (all items with metadata)
    └── artifacts/
        ├── images/             # figure_1.png, figure_2.png, ...
        ├── formulas/           # formula_1.png, formula_2.png, ...
        └── tables/             # table_1.csv, table_1.html, ...

Usage:
    python extract_pdf.py path/to/file.pdf
    python extract_pdf.py path/to/file.pdf --output-dir custom/output/
"""

import sys
import os
import json
import argparse
from pathlib import Path

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
from docling_core.types.doc import (
    DocItemLabel,
    PictureItem,
    TableItem,
    FormulaItem,
    TextItem,
    SectionHeaderItem,
    ListItem,
    GroupItem,
    GroupLabel,
)


def setup_converter() -> DocumentConverter:
    """Create a DocumentConverter with OCR, table structure, and image extraction enabled."""
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_table_structure = True
    pipeline_options.do_ocr = True
    pipeline_options.images_scale = 2.0
    pipeline_options.generate_page_images = True      # needed for FormulaItem.get_image()
    pipeline_options.generate_picture_images = True    # needed for PictureItem.get_image()

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )


def extract_artifacts(doc, artifacts_dir: Path) -> dict:
    """
    Extract all images (formulas + figures) and tables to the artifacts directory.
    Returns counters and a mapping from item self_ref → artifact relative path.
    """
    formulas_dir = artifacts_dir / "formulas"
    images_dir = artifacts_dir / "images"
    tables_dir = artifacts_dir / "tables"

    formulas_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    ref_to_path = {}
    counters = {"formulas": 0, "figures": 0, "tables": 0}

    formula_idx = 0
    figure_idx = 0
    table_idx = 0

    for item, _level in doc.iterate_items(with_groups=False):
        if isinstance(item, FormulaItem):
            formula_idx += 1
            img = item.get_image(doc)
            if img:
                fname = f"formula_{formula_idx}.png"
                fpath = formulas_dir / fname
                img.save(str(fpath), "PNG")
                rel_path = f"artifacts/formulas/{fname}"
                ref_to_path[item.self_ref] = rel_path
                counters["formulas"] += 1
                print(f"  Extracted: {rel_path}")

        elif isinstance(item, PictureItem):
            figure_idx += 1
            img = item.get_image(doc)
            if img:
                fname = f"figure_{figure_idx}.png"
                fpath = images_dir / fname
                img.save(str(fpath), "PNG")
                rel_path = f"artifacts/images/{fname}"
                ref_to_path[item.self_ref] = rel_path
                counters["figures"] += 1
                print(f"  Extracted: {rel_path}")

        elif isinstance(item, TableItem):
            table_idx += 1
            # CSV
            df = item.export_to_dataframe(doc=doc)
            csv_fname = f"table_{table_idx}.csv"
            csv_path = tables_dir / csv_fname
            df.to_csv(str(csv_path), index=False)
            counters["tables"] += 1
            print(f"  Extracted: artifacts/tables/{csv_fname}")

            # HTML
            html_fname = f"table_{table_idx}.html"
            html_path = tables_dir / html_fname
            html_content = item.export_to_html(doc=doc)
            with open(html_path, "w") as f:
                f.write(html_content)

            ref_to_path[item.self_ref] = {
                "csv": f"artifacts/tables/{csv_fname}",
                "html": f"artifacts/tables/{html_fname}",
            }

    return ref_to_path, counters


def get_caption_text(item) -> str:
    """Extract caption text from a PictureItem."""
    if hasattr(item, "captions") and item.captions:
        parts = []
        for cap in item.captions:
            if hasattr(cap, "text") and cap.text:
                parts.append(cap.text)
        return " ".join(parts)
    return ""


def build_markdown_and_content_map(doc, ref_to_path: dict, counters: dict) -> tuple[str, list[dict]]:
    """
    Build markdown by iterating items in reading order, and simultaneously
    build a structured content map.
    """
    md_lines = []
    content_map = []

    # Counters for naming artifacts
    formula_idx = 0
    figure_idx = 0
    table_idx = 0

    for item, level in doc.iterate_items(with_groups=False):
        entry = {
            "index": len(content_map),
            "type": type(item).__name__,
            "label": str(item.label) if hasattr(item, "label") else None,
            "page": None,
            "bbox": None,
            "text": None,
            "artifact_path": None,
        }

        # Extract page and bbox from provenance
        if hasattr(item, "prov") and item.prov:
            prov = item.prov[0]
            entry["page"] = getattr(prov, "page_no", None)
            if hasattr(prov, "bbox") and prov.bbox:
                bbox = prov.bbox
                entry["bbox"] = {
                    "l": round(bbox.l, 2),
                    "t": round(bbox.t, 2),
                    "r": round(bbox.r, 2),
                    "b": round(bbox.b, 2),
                }

        rendered = ""

        # --- FORMULAS ---
        if isinstance(item, FormulaItem):
            formula_idx += 1
            text = item.text or ""
            entry["text"] = text
            path_info = ref_to_path.get(item.self_ref)
            if path_info:
                entry["artifact_path"] = path_info
                if text:
                    rendered = f"\n$$\n{text}\n$$\n> ![formula_{formula_idx}]({path_info})\n"
                else:
                    rendered = f"\n![formula_{formula_idx}]({path_info})\n"

        # --- PICTURES ---
        elif isinstance(item, PictureItem):
            figure_idx += 1
            caption = get_caption_text(item)
            label = caption if caption else f"Figure {figure_idx}"
            entry["text"] = label
            path_info = ref_to_path.get(item.self_ref)
            if path_info:
                entry["artifact_path"] = path_info
                rendered = f"\n![{label}]({path_info})\n"

        # --- TABLES ---
        elif isinstance(item, TableItem):
            table_idx += 1
            entry["table_index"] = table_idx
            path_info = ref_to_path.get(item.self_ref)
            if path_info:
                entry["artifact_path"] = path_info["csv"]
                entry["html_path"] = path_info["html"]
                # Try inline markdown table
                try:
                    md_table = item.export_to_markdown(doc=doc)
                    rendered = f"\n{md_table}\n\n> 📊 [Table {table_idx} CSV]({path_info['csv']}) | [Table {table_idx} HTML]({path_info['html']})\n"
                except Exception:
                    rendered = f"\n> 📊 [Table {table_idx} CSV]({path_info['csv']}) | [Table {table_idx} HTML]({path_info['html']})\n"

        # --- SECTION HEADERS ---
        elif isinstance(item, SectionHeaderItem):
            lvl = getattr(item, "level", 1)
            prefix = "#" * min(lvl + 1, 6)
            entry["text"] = item.text
            entry["level"] = lvl
            rendered = f"\n{prefix} {item.text}\n"

        # --- LIST ITEMS ---
        elif isinstance(item, ListItem):
            entry["text"] = item.text
            enumerated = getattr(item, "enumerated", False)
            if enumerated:
                rendered = f"1. {item.text}"
            else:
                rendered = f"- {item.text}"

        # --- TEXT ITEMS ---
        elif isinstance(item, TextItem):
            text = item.text or ""
            entry["text"] = text
            label = item.label if hasattr(item, "label") else None

            if label == DocItemLabel.TITLE:
                rendered = f"# {text}\n"
            elif label == DocItemLabel.SECTION_HEADER:
                rendered = f"\n## {text}\n"
            elif label == DocItemLabel.PARAGRAPH:
                rendered = text
            elif label == DocItemLabel.FORMULA:
                # Should be caught by FormulaItem above, but fallback
                formula_idx += 1
                path_info = ref_to_path.get(getattr(item, "self_ref", None))
                if text:
                    rendered = f"\n$$\n{text}\n$$\n"
                elif path_info:
                    rendered = f"\n![formula_{formula_idx}]({path_info})\n"
            else:
                rendered = text

        if rendered:
            md_lines.append(rendered)

        content_map.append(entry)

    # Add page break markers between pages
    md_content = "\n".join(md_lines)

    return md_content, content_map


def extract_pdf(pdf_path: str, output_dir: str):
    """Main extraction function."""
    print(f"Processing: {pdf_path}")
    print(f"Output directory: {output_dir}")

    # Setup converter
    converter = setup_converter()

    # Convert
    result = converter.convert(pdf_path)
    doc = result.document

    # Create output dirs
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    artifacts_dir = output_path / "artifacts"

    # Extract artifacts
    print("\nExtracting artifacts...")
    ref_to_path, counters = extract_artifacts(doc, artifacts_dir)

    # Build markdown and content map
    print("\nBuilding markdown with artifact references...")
    md_content, content_map = build_markdown_and_content_map(doc, ref_to_path, counters)

    # Save markdown
    md_path = output_path / "content.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Save content map
    map_path = output_path / "content_map.json"
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(content_map, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Extraction complete!")
    print(f"{'='*60}")
    print(f"  Markdown:      {md_path}")
    print(f"  Content map:   {map_path}")
    print(f"  Formulas:      {counters['formulas']} extracted")
    print(f"  Figures:       {counters['figures']} extracted")
    print(f"  Tables:        {counters['tables']} extracted")
    print(f"  Total items:   {len(content_map)}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract text, formulas, images, and tables from PDFs to Markdown."
    )
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="Output directory (default: extracted/<pdf_name>)"
    )
    args = parser.parse_args()

    # Determine output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        pdf_name = Path(args.pdf_path).stem
        safe_name = pdf_name.replace(" ", "-").lower()
        output_dir = f"extracted/{safe_name}"

    extract_pdf(args.pdf_path, output_dir)


if __name__ == "__main__":
    main()
