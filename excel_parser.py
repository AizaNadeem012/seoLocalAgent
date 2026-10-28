import io
import re
import csv
from typing import Dict, Any, List, Tuple, Optional
import openpyxl

URL_REGEX = re.compile(
    r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)',
    re.IGNORECASE
)

DOMAIN_REGEX = re.compile(
    r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[^\s,"\'<>]*)?',
    re.IGNORECASE
)

def clean_val(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()

def is_probable_url(text: str) -> bool:
    t = text.strip()
    if not t or " " in t or len(t) < 4:
        return False
    if t.startswith("http://") or t.startswith("https://"):
        return True
    return bool("." in t and DOMAIN_REGEX.search(t))

def normalize_url(raw: str) -> str:
    u = raw.strip().rstrip("/")
    if not u.startswith("http://") and not u.startswith("https://"):
        u = f"https://{u}"
    return u

def parse_excel_or_csv(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Parses any Excel (.xlsx, .xls) or CSV file.
    Supports structured tables (with headers) and unstructured URL lists.
    Extracts individual targets with per-target backlink/anchor configuration,
    validates URLs, eliminates duplicates, and records invalid rows.
    """
    filename_lower = filename.lower()
    raw_rows: List[List[Any]] = []

    if filename_lower.endswith(".csv"):
        try:
            content = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content = file_bytes.decode("latin-1")

        # Detect dialect / delimiter
        sample = content[:2048]
        delimiter = ","
        if ";" in sample and sample.count(";") > sample.count(","):
            delimiter = ";"
        elif "\t" in sample and sample.count("\t") > sample.count(","):
            delimiter = "\t"

        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        raw_rows = [row for row in reader if any(clean_val(c) for c in row)]

    elif filename_lower.endswith((".xlsx", ".xls")):
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheet = wb.active
        for row in sheet.iter_rows(values_only=True):
            if any(clean_val(c) for c in row):
                raw_rows.append(list(row))
    else:
        raise ValueError("Unsupported format. Please upload an Excel (.xlsx, .xls) or CSV file.")

    if not raw_rows:
        return {
            "targets": [],
            "suggested_profile": {},
            "total_extracted": 0,
            "invalid_rows": [],
            "duplicates_count": 0,
            "filename": filename,
        }

    # Step 1: Detect if Row 0 has recognizable column headers
    header_candidate = [clean_val(c).lower() for c in raw_rows[0]]
    url_col_idx = -1
    name_col_idx = -1
    category_col_idx = -1
    landing_col_idx = -1
    anchor_col_idx = -1
    priority_col_idx = -1
    notes_col_idx = -1
    user_col_idx = -1
    pass_col_idx = -1

    for idx, col_name in enumerate(header_candidate):
        if any(k in col_name for k in ["target landing page", "landing page", "backlink url", "destination", "target link", "target url for backlink"]):
            landing_col_idx = idx
        elif any(k in col_name for k in ["website name", "site name", "portal name", "portal"]) or col_name == "name":
            name_col_idx = idx
        elif any(k in col_name for k in ["website url", "site url", "target url", "domain url", "web url", "url"]) or col_name == "website":
            if url_col_idx == -1:
                url_col_idx = idx
        elif any(k in col_name for k in ["preferred anchor", "anchor text", "anchor", "keyword"]):
            anchor_col_idx = idx
        elif any(k in col_name for k in ["website name", "site name", "name", "portal"]):
            name_col_idx = idx
        elif any(k in col_name for k in ["category", "niche", "industry", "topic"]):
            category_col_idx = idx
        elif any(k in col_name for k in ["priority", "tier"]):
            priority_col_idx = idx
        elif any(k in col_name for k in ["notes", "description", "guidelines", "remarks"]):
            notes_col_idx = idx
        elif any(k in col_name for k in ["username", "user", "login"]):
            user_col_idx = idx
        elif any(k in col_name for k in ["password", "pass", "pwd"]):
            pass_col_idx = idx

    targets = []
    seen_urls = set()
    invalid_rows = []
    duplicates_count = 0
    suggested_profile: Dict[str, str] = {}

    # Case A: Structured table with recognized URL column
    if url_col_idx != -1:
        for row_idx, row in enumerate(raw_rows[1:], start=2):
            if len(row) <= url_col_idx:
                invalid_rows.append({"row": row_idx, "reason": "Empty or truncated row"})
                continue
            
            raw_url = clean_val(row[url_col_idx])
            if not raw_url:
                invalid_rows.append({"row": row_idx, "reason": "URL cell is blank"})
                continue

            if not is_probable_url(raw_url):
                invalid_rows.append({"row": row_idx, "raw_value": raw_url, "reason": "Invalid or unparseable URL format"})
                continue

            normalized_url = normalize_url(raw_url)

            if normalized_url in seen_urls:
                duplicates_count += 1
                continue
            seen_urls.add(normalized_url)

            # Extract metadata
            name = clean_val(row[name_col_idx]) if name_col_idx != -1 and len(row) > name_col_idx else ""
            cat = clean_val(row[category_col_idx]) if category_col_idx != -1 and len(row) > category_col_idx else ""
            landing = clean_val(row[landing_col_idx]) if landing_col_idx != -1 and len(row) > landing_col_idx else ""
            anchor = clean_val(row[anchor_col_idx]) if anchor_col_idx != -1 and len(row) > anchor_col_idx else ""
            priority = clean_val(row[priority_col_idx]) if priority_col_idx != -1 and len(row) > priority_col_idx else "medium"
            notes = clean_val(row[notes_col_idx]) if notes_col_idx != -1 and len(row) > notes_col_idx else ""
            user = clean_val(row[user_col_idx]) if user_col_idx != -1 and len(row) > user_col_idx else None
            pw = clean_val(row[pass_col_idx]) if pass_col_idx != -1 and len(row) > pass_col_idx else None

            # Capture profile suggestion from first valid row
            if landing and not suggested_profile.get("backlink_url"):
                suggested_profile["backlink_url"] = landing
            if anchor and not suggested_profile.get("anchor_text"):
                suggested_profile["anchor_text"] = anchor
            if cat and not suggested_profile.get("niche"):
                suggested_profile["niche"] = cat

            targets.append({
                "website_url": normalized_url,
                "website_name": name or None,
                "category": cat or None,
                "target_backlink_url": landing or None,
                "target_anchor_text": anchor or None,
                "priority": priority.lower() if priority else "medium",
                "notes": notes or None,
                "username": user or None,
                "password": pw or None,
                "status": "Pending Analysis",
                "stage": "QUEUE",
                "workflow": "Pending",
            })

    # Case B: Unstructured list (e.g. pure links, raw paste, or tables without standard headers)
    else:
        for row_idx, row in enumerate(raw_rows, start=1):
            row_has_url = False
            for cell in row:
                val = clean_val(cell)
                if not val:
                    continue

                matches = URL_REGEX.findall(val)
                if not matches and is_probable_url(val):
                    matches = [val]

                for m in matches:
                    row_has_url = True
                    u = normalize_url(m)
                    if u not in seen_urls and "." in u:
                        seen_urls.add(u)
                        targets.append({
                            "website_url": u,
                            "website_name": None,
                            "category": None,
                            "target_backlink_url": None,
                            "target_anchor_text": None,
                            "priority": "medium",
                            "notes": None,
                            "username": None,
                            "password": None,
                            "status": "Pending Analysis",
                            "stage": "QUEUE",
                            "workflow": "Pending",
                        })
                    else:
                        duplicates_count += 1
            if not row_has_url and any(clean_val(c) for c in row):
                invalid_rows.append({"row": row_idx, "reason": "No valid domain or URL found in row"})

    return {
        "targets": targets,
        "suggested_profile": suggested_profile,
        "total_extracted": len(targets),
        "invalid_rows": invalid_rows,
        "duplicates_count": duplicates_count,
        "filename": filename,
    }
