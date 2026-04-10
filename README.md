# PDF Extractor

A generic CLI tool that extracts text, formulas, images, and tables from PDFs into **structured Markdown** with a **content map**. Every artifact (formula image, figure, table) is saved as a separate file and properly referenced in the Markdown — no placeholders like `<!-- image -->` or `<!-- formula-not-decoded -->`.

Built on [Docling](https://github.com/docling-project/docling) (IBM's document understanding toolkit).

---

## Output Structure

For each processed PDF, the tool creates:

```
extracted/<pdf_name>/
├── content.md              # Markdown with proper artifact references
├── content_map.json        # Structured content map (all items with metadata)
└── artifacts/
    ├── formulas/           # formula_1.png, formula_2.png, ...
    ├── images/             # figure_1.png, figure_2.png, ...
    └── tables/             # table_1.csv, table_1.html, ...
```

### Markdown (`content.md`)

- **Formulas** → rendered as images with references: `![formula_1](artifacts/formulas/formula_1.png)`
- **Figures/Diagrams** → `![Figure 1](artifacts/images/figure_1.png)`
- **Tables** → inline markdown table + download links: `[Table 1 CSV](artifacts/tables/table_1.csv)`
- **Section headers, lists, paragraphs** → proper markdown formatting

### Content Map (`content_map.json`)

Ordered list of every content item with:

| Field           | Description                                      |
|-----------------|--------------------------------------------------|
| `index`         | Sequential order in reading flow                 |
| `type`          | Item type (FormulaItem, PictureItem, TableItem, TextItem, etc.) |
| `label`         | Docling-detected label                           |
| `page`          | Page number                                      |
| `bbox`          | Bounding box `{l, t, r, b}` on the page          |
| `text`          | Extracted text content                           |
| `artifact_path` | Relative path to the saved artifact              |
| `html_path`     | Relative path to HTML export (tables only)       |

---

## Prerequisites

- **Python 3.10+** (tested with 3.14)
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager
  ```bash
  # Install uv
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

---

## Setup

No separate environment needed — `uv` handles dependencies automatically using the project's `uv.lock` or by resolving on first run.

**Required dependency:** `docling` (installed automatically by `uv` on first run)

---

## Usage

### Basic

```bash
uv run python extract_pdf.py path/to/document.pdf
```

Output goes to `extracted/<document-name>/`.

### Custom Output Directory

```bash
uv run python extract_pdf.py path/to/document.pdf -o my/output/dir
```

### Examples

```bash
# Extract a single PDF
uv run python extract_pdf.py "raw/GA-solutions/Week1 GA solution.pdf"

# With custom output path
uv run python extract_pdf.py paper.pdf -o extracted/my-paper
```

---

## How It Works

1. **Docling** converts the PDF with OCR, table structure analysis, and image extraction enabled
2. **Artifact extraction** — formula images, figures, and tables are saved to the `artifacts/` folder
   - Formula images are cropped from page renders using bounding box provenance
   - Figures are extracted as high-res PNGs
   - Tables are exported as both CSV and HTML
3. **Markdown builder** — iterates the document body in reading order, replacing generic placeholders (`<!-- image -->`, `<!-- formula-not-decoded -->`) with proper relative path references
4. **Content map** — structured JSON metadata for programmatic access to all content items

---

## Limitations

- **Formula text** — Docling detects formulas but cannot always extract them as LaTeX/MathML text. Formulas are saved as cropped images and embedded as such in the Markdown. For native LaTeX conversion, a custom enrichment model (e.g., LaTeX OCR) would need to be plugged in.
- **OCR accuracy** — depends on the quality of the underlying OCR engine (EasyOCR by default). Scanned/handwritten PDFs may have reduced accuracy.
- **Processing time** — first run downloads Docling's ML models (~100 MB). Subsequent runs are cached.

---

## File Structure

```
pdf-extractor/
├── extract_pdf.py      # Main extraction script
└── README.md           # This file
```
