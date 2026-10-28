# LinkForge — Real Autonomous SEO Guest Post & Backlink Dashboard

A real, production-ready, full-stack application for automated guest posting and live backlink verification.

---

## What Makes This Real (No Demo Data)

1. **Universal Excel & Spreadsheet Parser (`excel_parser.py`)**:
   - Parses structured spreadsheets (e.g. `rankwave_target_websites_template.xlsx`) with columns for `Website URL`, `Target Landing Page`, `Preferred Anchor`, `Category`, `Notes`, `Priority`.
   - Parses unstructured link lists (e.g. `nandla .xlsx`) with 200+ raw website links and forum URLs.
   - Automatically detects destination landing pages and anchor keywords to auto-configure your business profile.

2. **Real Playwright Browser Automation Core (`automation.py`)**:
   - Launches real Chromium instances with `--disable-blink-features=AutomationControlled` and `playwright-stealth`.
   - Real anti-bot evasion: humanized typing delay (`random.randint(35, 120) ms`), realistic navigation.
   - Real page analysis: detects HTTP status codes, extracts real page titles, scans for guest post submission links (`write for us`, `contribute`, `guest post`, `register`, `new topic`).
   - Generates unique brand credentials (`brand_dev_XXXX`) and writes them directly to the database.
   - Mitigates Cloudflare & CAPTCHAs gracefully (`Failed - Captcha` / `Manual Required`) without breaking execution threads.
   - Real Live Backlink Verification: verifies destination URLs and anchor text on live posts.

3. **Ultra-Clean, High-Performance Dashboard (`static/index.html`)**:
   - Dark-mode SaaS UI with live KPI stats cards.
   - Drag-and-drop Excel upload with instant validation.
   - Filterable, searchable data grid with credential reveal toggles and live post hyperlinks.
   - Real-time live execution logs stream (SSE).
   - Manual override modal.

---

## Quickstart

### Start the Server
```bash
run.bat
```
*(Or inside PowerShell: `python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload`)*

Dashboard will open at:
**http://localhost:8000**
