from __future__ import annotations

import argparse
import re
from pathlib import Path


def remove_front_matter(markdown_text: str) -> str:
    """Remove YAML front matter if present at the top of the file.

    Front matter is delimited by leading '---' blocks.
    """
    # Matches starting '---' up to the next '---' at line start
    front_matter_pattern = r"^---\n[\s\S]*?\n---\n"
    return re.sub(front_matter_pattern, "", markdown_text, count=1, flags=re.MULTILINE)


def markdown_to_html(markdown_text: str) -> str:
    """Convert Markdown to basic HTML.

    We avoid heavyweight toolchains; use Python's markdown package if available,
    fallback to a minimal converter for headings and paragraphs.
    """
    try:
        import markdown  # type: ignore

        return markdown.markdown(
            markdown_text,
            extensions=[
                "extra",
                "sane_lists",
                "tables",
                "toc",
                "codehilite",
            ],
            output_format="html5",
        )
    except Exception:
        # Minimal fallback: very naive conversions for local preview only
        html = []
        for line in markdown_text.splitlines():
            if line.startswith("# "):
                html.append(f"<h1>{line[2:].strip()}</h1>")
            elif line.startswith("## "):
                html.append(f"<h2>{line[3:].strip()}</h2>")
            elif line.startswith("### "):
                html.append(f"<h3>{line[4:].strip()}</h3>")
            elif line.strip():
                html.append(f"<p>{line}</p>")
        return "\n".join(html)


def html_to_pdf(html: str, out_file: Path) -> None:
    """Render HTML to PDF using xhtml2pdf if available.

    If not installed, raise a clear error with instructions.
    """
    try:
        import io

        from xhtml2pdf import pisa  # type: ignore

        with out_file.open("wb") as pdf_file:
            result = pisa.CreatePDF(io.StringIO(html), dest=pdf_file)
        if result.err:
            raise RuntimeError(f"xhtml2pdf failed to render {out_file.name}")
    except ModuleNotFoundError as exc:
        raise SystemExit("xhtml2pdf is required. Install with: uv add xhtml2pdf") from exc


def build_document(md_path: Path, out_dir: Path) -> Path:
    text = md_path.read_text(encoding="utf-8")
    content = remove_front_matter(text)
    html_body = markdown_to_html(content)

    html = f"""
<!doctype html>
<html lang=\"pt-BR\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{md_path.stem}</title>
    <style>
      body {{ font-family: Arial, Helvetica, sans-serif; font-size: 12pt; line-height: 1.45; }}
      h1, h2, h3 {{ color: #111; margin-top: 1.2em; }}
      table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
      th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
      code {{ background: #f6f8fa; padding: 2px 4px; border-radius: 3px; }}
      blockquote {{ border-left: 4px solid #ddd; margin: 0.8em 0; padding: 0.2em 0.8em; color: #555; }}
    </style>
  </head>
  <body>
    {html_body}
  </body>
</html>
"""

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{md_path.stem}.pdf"
    html_to_pdf(html, out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build PDFs from Markdown documents.")
    parser.add_argument(
        "--src-dir",
        type=Path,
        default=Path(__file__).parent,
        help="Directory containing Markdown files.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).parent / "pdfs",
        help="Output directory for generated PDFs.",
    )
    args = parser.parse_args()

    md_files = sorted(p for p in args.src_dir.glob("*.md") if p.name.lower() != "readme.md")
    if not md_files:
        raise SystemExit(f"No Markdown files found in {args.src_dir}")

    for md in md_files:
        out = build_document(md, args.out_dir)
        print(f"Built: {out}")


if __name__ == "__main__":
    main()
