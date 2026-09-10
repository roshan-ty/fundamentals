# File extraction utilities — unpacks economic/report downloads into usable JSON.
# Supports: zip, xlsx/xls, csv, pdf, docx, and optionally rar (via rarfile+unrar).
# Used primarily for report drops, CFTC report bundles and any supplementary files.
import os
import sys
import io
import json
import csv
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import log, ensure_dir, save_json

RAR_AVAILABLE = False
try:
    import rarfile  # requires external 'unrar' on Unix; bundled on CI via apt
    rarfile.UNRAR_TOOL = "unrar"
    RAR_AVAILABLE = True
except Exception:
    pass

_XLSX = None
_DOCX = None
_PDF = None
try:
    import openpyxl
    _XLSX = True
except Exception:
    _XLSX = False
try:
    import docx
    _DOCX = True
except Exception:
    _DOCX = False
try:
    import pypdf
    _PDF = True
except Exception:
    _PDF = False


def read_zip(path):
    """Return list of {name, content(bytes)} for each member."""
    out = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.endswith("/"):
                continue
            out.append({"name": name, "bytes": z.read(name)})
    return out


def read_rar(path):
    if not RAR_AVAILABLE:
        raise RuntimeError("rarfile unavailable")
    rf = rarfile.RarFile(path)
    out = []
    for name in rf.namelist():
        if name.endswith("/"):
            continue
        out.append({"name": name, "bytes": rf.read(name)})
    return out


def parse_csv_bytes(data):
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    return rows


def parse_xlsx_bytes(data):
    if not _XLSX:
        raise RuntimeError("openpyxl unavailable")
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(h).strip() if h is not None else f"col{i}" for i, h in enumerate(rows[0])]
    return [dict(zip(header, [("" if c is None else c) for c in row])) for row in rows[1:]]


def parse_pdf_bytes(data):
    if not _PDF:
        raise RuntimeError("pypdf unavailable")
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def parse_docx_bytes(data):
    if not _DOCX:
        raise RuntimeError("docx unavailable")
    import docx
    d = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in d.paragraphs)


def extract_report(path, out_dir=None):
    """Extract a report file (any supported format) into structured JSON."""
    name = os.path.basename(path)
    low = name.lower()
    result = {"file": name, "source": path}
    if low.endswith(".zip"):
        parts = []
        for member in read_zip(path):
            sub = extract_bytes(member["name"], member["bytes"])
            parts.append({"member": member["name"], **sub})
        result["type"] = "archive"
        result["members"] = parts
    elif low.endswith((".xlsx", ".xls")):
        result = {"file": name, "type": "table", "rows": parse_xlsx_bytes(open(path, "rb").read())}
    elif low.endswith(".csv"):
        result = {"file": name, "type": "table", "rows": parse_csv_bytes(open(path, "rb").read())}
    elif low.endswith(".pdf"):
        result = {"file": name, "type": "document", "text": parse_pdf_bytes(open(path, "rb").read())}
    elif low.endswith(".docx"):
        result = {"file": name, "type": "document", "text": parse_docx_bytes(open(path, "rb").read())}
    elif low.endswith(".rar"):
        parts = []
        for member in read_rar(path):
            sub = extract_bytes(member["name"], member["bytes"])
            parts.append({"member": member["name"], **sub})
        result = {"file": name, "type": "archive", "members": parts}
    else:
        result = {"file": name, "type": "unsupported"}
    if out_dir:
        ensure_dir(out_dir)
        out_name = os.path.splitext(name)[0] + ".json"
        save_json(os.path.join(out_dir, out_name), result)
        log(f"Extracted {name} -> {out_name}")
    return result


def extract_bytes(member_name, data):
    low = member_name.lower()
    if low.endswith(".csv"):
        return {"type": "table", "rows": parse_csv_bytes(data)}
    if low.endswith(".xlsx") or low.endswith(".xls"):
        return {"type": "table", "rows": parse_xlsx_bytes(data)}
    if low.endswith(".pdf"):
        return {"type": "document", "text": parse_pdf_bytes(data)}
    if low.endswith(".docx"):
        return {"type": "document", "text": parse_docx_bytes(data)}
    return {"type": "binary", "bytes": len(data)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python file_extract.py <path> [out_dir]")
        sys.exit(1)
    target = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(extract_report(target, out_dir), indent=1)[:1500])