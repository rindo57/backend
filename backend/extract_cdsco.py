import pdfplumber
import csv
from pathlib import Path
import sys
import re


def _resolve_pdf_path(pdf_path):
    candidate = Path(pdf_path)
    if candidate.is_file():
        return candidate

    backend_candidate = Path(__file__).resolve().parent / candidate
    if backend_candidate.is_file():
        return backend_candidate

    return None


def _get_backend_pdfs():
    backend_dir = Path(__file__).resolve().parent
    return sorted(backend_dir.glob("*.pdf"))


def _normalize_row(row):
    """Return stable columns: drug_name, batch_number, manufacturer, reason."""
    cleaned = [cell.strip() if isinstance(cell, str) else cell for cell in row if cell is not None]
    cleaned = [cell for cell in cleaned if cell != ""]

    # Some CDSCO tables contain an extra leading Sr. No. column (e.g. "1.")
    # which shifts all data by one position. Drop it when present.
    if cleaned and re.fullmatch(r"\d+\.?", str(cleaned[0]).strip()):
        cleaned = cleaned[1:]

    if not cleaned:
        return ["", "", "", ""]

    drug_name = cleaned[0] if len(cleaned) > 0 else ""
    batch_number = cleaned[1] if len(cleaned) > 1 else ""
    manufacturer = cleaned[2] if len(cleaned) > 2 else ""

    # Keep any trailing cells in reason to avoid losing data from merged table cells.
    reason = " ".join(str(cell) for cell in cleaned[3:]).strip() if len(cleaned) > 3 else ""
    return [drug_name, batch_number, manufacturer, reason]


def extract_from_pdfs(pdf_paths, output_csv):
    output_path = Path(output_csv)
    if not output_path.is_absolute():
        output_path = Path(__file__).resolve().parent / output_path

    total_rows = 0
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['source_pdf', 'page_number', 'drug_name', 'batch_number', 'manufacturer', 'reason'])

        for pdf_path in pdf_paths:
            with pdfplumber.open(pdf_path) as pdf:
                for page_index, page in enumerate(pdf.pages, start=1):
                    tables = page.extract_tables() or []
                    for table in tables:
                        if not table:
                            continue
                        for row in table[1:]:  # skip header row
                            if not row:
                                continue
                            normalized = _normalize_row(row)
                            if any(normalized):
                                writer.writerow([pdf_path.name, page_index, *normalized])
                                total_rows += 1

    return output_path, total_rows


def extract_from_pdf(pdf_path, output_csv):
    resolved_pdf = _resolve_pdf_path(pdf_path)
    if resolved_pdf is None:
        raise FileNotFoundError(
            f"PDF not found: '{pdf_path}'. Place the file in backend or pass absolute path."
        )

    output_path, total_rows = extract_from_pdfs([resolved_pdf], output_csv)
    return [resolved_pdf], output_path, total_rows


def extract_from_all_pdfs(output_csv):
    pdfs = _get_backend_pdfs()
    if not pdfs:
        raise FileNotFoundError("No PDF files found in backend folder.")

    output_path, total_rows = extract_from_pdfs(pdfs, output_csv)
    return pdfs, output_path, total_rows

if __name__ == "__main__":
    # Usage:
    # python extract_cdsco.py                  -> process all backend PDFs
    # python extract_cdsco.py all out.csv      -> process all backend PDFs to out.csv
    # python extract_cdsco.py input.pdf out.csv -> process a single PDF
    arg1 = sys.argv[1] if len(sys.argv) > 1 else "all"
    output_csv = sys.argv[2] if len(sys.argv) > 2 else "cdsco_clean.csv"

    try:
        if arg1.lower() == "all":
            used_pdfs, saved_csv, total_rows = extract_from_all_pdfs(output_csv)
            print(f"Done! Processed {len(used_pdfs)} PDFs | Rows: {total_rows} | Output: {saved_csv}")
        else:
            used_pdfs, saved_csv, total_rows = extract_from_pdf(arg1, output_csv)
            print(f"Done! Processed {len(used_pdfs)} PDF ({used_pdfs[0].name}) | Rows: {total_rows} | Output: {saved_csv}")
    except FileNotFoundError as error:
        print(error)
