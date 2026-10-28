import sqlite3

conn = sqlite3.connect('linkforge.db')
c = conn.cursor()

bad_patterns = ['contact-forms', 'contact-index', 'confirm', 'thank-you', 'thank_you', 'success', 'sent', '/index/']

c.execute('SELECT id, website_url, live_post_url FROM targets WHERE live_post_url IS NOT NULL')
rows = c.fetchall()
fixed = []

for row in rows:
    tid, site, url = row
    if url and any(p in url.lower() for p in bad_patterns):
        note = " [Auto-corrected: form confirmation redirect page removed from live_post_url - article pending editorial review]"
        c.execute(
            "UPDATE targets SET live_post_url = NULL, status = 'Pending Editorial Review', error_log = COALESCE(error_log,'') || ? WHERE id = ?",
            (note, tid)
        )
        fixed.append((tid, site, url))

conn.commit()
conn.close()

print(f"Fixed {len(fixed)} bad live_post_url entries:")
for f in fixed:
    print(f"  ID={f[0]} | site={f[1]}")
    print(f"    bad_url was: {f[2]}")
