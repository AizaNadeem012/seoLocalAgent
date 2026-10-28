import unittest
import os
import io
import json
import sqlite3
from unittest.mock import MagicMock, patch

import database as db
from excel_parser import parse_excel_or_csv, is_probable_url, normalize_url
from website_analyzer import analyze_guidelines_text, extract_word_count_limits
from content_generator import smart_content_generator
from email_client import email_outreach_client, clean_app_password


class TestSmartGuestPostingSystem(unittest.TestCase):

    def setUp(self):
        db.init_db()

    # ─── 1. Excel & CSV Import Validation ──────────────────────────────────
    def test_excel_url_helpers(self):
        self.assertTrue(is_probable_url("https://fashionunited.com"))
        self.assertTrue(is_probable_url("websolindia.com/write-for-us/"))
        self.assertFalse(is_probable_url("Not A Valid URL"))
        self.assertFalse(is_probable_url(""))

        self.assertEqual(normalize_url("websolindia.com/write-for-us/"), "https://websolindia.com/write-for-us")
        self.assertEqual(normalize_url("https://fashionunited.com/"), "https://fashionunited.com")

    def test_csv_parser_structured_columns(self):
        csv_data = (
            "Website URL,Website Name,Category,Target Landing Page,Preferred Anchor Text,Priority,Notes\n"
            "https://target-alpha.com,Alpha Blog,Fashion,https://www.afimahclothingstore.com/mens,bespoke tailoring,high,Top tier\n"
            "https://target-beta.com,Beta Tech,Technology,https://www.afimahclothingstore.com/about,sustainable luxury,medium,Standard\n"
            "https://target-alpha.com,Alpha Duplicate,Fashion,,,,Duplicate row\n"
            "invalid-row-without-domain,,,,,,Invalid\n"
        ).encode("utf-8")

        res = parse_excel_or_csv(csv_data, "targets.csv")
        self.assertEqual(len(res["targets"]), 2)
        self.assertEqual(res["duplicates_count"], 1)
        self.assertEqual(len(res["invalid_rows"]), 1)

        t1 = res["targets"][0]
        self.assertEqual(t1["website_url"], "https://target-alpha.com")
        self.assertEqual(t1["website_name"], "Alpha Blog")
        self.assertEqual(t1["category"], "Fashion")
        self.assertEqual(t1["target_backlink_url"], "https://www.afimahclothingstore.com/mens")
        self.assertEqual(t1["target_anchor_text"], "bespoke tailoring")
        self.assertEqual(t1["priority"], "high")

    # ─── 2. Website Reconnaissance & Guidelines Analysis ────────────────────
    def test_extract_word_count_limits(self):
        text1 = "Submissions must be between 800 to 1500 words in length."
        min_w, max_w = extract_word_count_limits(text1)
        self.assertEqual(min_w, 800)
        self.assertEqual(max_w, 1500)

        text2 = "We require a minimum of 1000 words per article."
        min_w2, _ = extract_word_count_limits(text2)
        self.assertEqual(min_w2, 1000)

    def test_analyze_guidelines_text_free_vs_paid(self):
        free_guidelines = (
            "Welcome to our blog! We accept free guest posts on digital marketing. "
            "We do not charge any fee for publishing high quality articles. "
            "Dofollow backlinks are permitted in the content."
        )
        res_free = analyze_guidelines_text(free_guidelines)
        self.assertEqual(res_free["pricing_type"], "free")
        self.assertIn("do-follow", res_free["backlink_policy"].lower())

        paid_guidelines = (
            "We accept sponsored content. Our editorial publishing fee is $150 per post via PayPal. "
            "All commercial links must be pre-approved."
        )
        res_paid = analyze_guidelines_text(paid_guidelines)
        self.assertEqual(res_paid["pricing_type"], "paid")
        self.assertTrue(len(res_paid["evidence_snippets"]) > 0)

    def test_analyze_guidelines_ai_policy(self):
        ai_prohibited = (
            "Strict human-only publication. No AI content is allowed. "
            "ChatGPT content will be rejected immediately upon submission."
        )
        res_ai = analyze_guidelines_text(ai_prohibited)
        self.assertEqual(res_ai["ai_policy"], "disallowed")

    # ─── 3. Smart Content & Pitch Generation ────────────────────────────────
    def test_content_generator_article(self):
        target = {
            "category": "Menswear & Tailoring",
            "website_name": "Modern Sartorialist",
            "target_backlink_url": "https://www.afimahclothingstore.com/bespoke",
            "target_anchor_text": "handcrafted bespoke suits"
        }
        config = {
            "niche": "Fashion",
            "backlink_url": "https://www.afimahclothingstore.com",
            "anchor_text": "sustainable luxury apparel"
        }
        report = {
            "niche_detected": "Menswear & Tailoring",
            "website_title": "Modern Sartorialist",
            "word_count_min": 800,
            "word_count_max": 1500
        }

        art = smart_content_generator.generate_article(target, config, report)
        self.assertIn("handcrafted bespoke suits", art["body"])
        self.assertIn("https://www.afimahclothingstore.com/bespoke", art["body"])
        self.assertGreater(art["word_count"], 500)
        self.assertTrue(art["has_anchor"])
        self.assertTrue(art["has_link"])

    def test_content_generator_pitch(self):
        target = {
            "category": "Sustainable Fashion",
            "website_name": "EcoStyle Magazine"
        }
        config = {
            "default_email": "editor@afimahclothingstore.com"
        }
        report = {
            "contact_email": "submissions@ecostylemag.com"
        }
        pitch = smart_content_generator.generate_pitch(target, config, report)
        self.assertIn("EcoStyle", pitch["subject"])
        self.assertEqual(pitch["recipient"], "submissions@ecostylemag.com")
        self.assertIn("Proposed Article Titles", pitch["body"])

    # ─── 4. Database Lifecycle & Approvals Queue ────────────────────────────
    def test_target_lifecycle_and_approval(self):
        unique_url = f"https://test-lifecycle-{os.urandom(4).hex()}.com"
        target = db.add_target({
            "website_url": unique_url,
            "website_name": "Lifecycle Test Site",
            "category": "Testing"
        })
        self.assertIsNotNone(target)
        tid = target["id"]

        # Update analysis report
        mock_report = {
            "niche_detected": "Testing",
            "pricing_type": "paid",
            "pricing_details": "Admin fee $50 requested",
            "recommended_workflow": "Workflow E (Paid / Review)",
            "confidence_score": 0.85
        }
        db.update_target(tid, {
            "analysis_report": mock_report,
            "workflow": "Workflow E (Paid / Review)",
            "status": "Needs Approval"
        })

        t_after = db.get_target_by_id(tid)
        self.assertEqual(t_after["status"], "Needs Approval")
        self.assertEqual(t_after["workflow"], "Workflow E (Paid / Review)")
        self.assertIsNotNone(t_after["analysis_report_parsed"])

        # Check approval queue
        queue = db.get_approval_queue()
        queue_ids = [item["id"] for item in queue]
        self.assertIn(tid, queue_ids)

        # Client Approves
        db.approve_target(tid, "Client authorized $50 admin fee")
        t_approved = db.get_target_by_id(tid)
        self.assertEqual(t_approved["approval_status"], "Approved")
        self.assertEqual(t_approved["status"], "Ready to Submit")
        self.assertEqual(t_approved["stage"], "APPROVED")

        # Editorial Reply
        db.record_editorial_reply(tid, "Your article has been reviewed and approved for publication!")
        t_replied = db.get_target_by_id(tid)
        self.assertEqual(t_replied["status"], "Approved by Editor")
        self.assertEqual(t_replied["workflow"], "Workflow D (Approved by Editor)")

        # Cleanup
        db.delete_target(tid)

    # ─── 5. Real Gmail Settings & Password Cleaner ──────────────────────────
    def test_clean_app_password(self):
        raw = " abcd efgh ijkl mnop "
        cleaned = clean_app_password(raw)
        self.assertEqual(cleaned, "abcdefghijklmnop")
        self.assertEqual(clean_app_password(""), "")
        self.assertEqual(clean_app_password(None), "")

    def test_email_missing_credentials_fails_real(self):
        """Verifies that unconfigured real outreach does NOT simulate success."""
        with patch.object(email_outreach_client, 'get_credentials') as mock_creds:
            mock_creds.return_value = {
                "email_address": "",
                "app_password": "",
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_user": "",
                "smtp_pass": "",
                "imap_host": "imap.gmail.com",
                "imap_port": 993,
                "imap_user": "",
                "imap_pass": "",
                "is_configured": False,
            }

            # Test connection diagnostic
            diag = email_outreach_client.test_connection("test@gmail.com")
            self.assertFalse(diag["overall_success"])
            self.assertIn("Credentials missing", diag["error_summary"])

            # Test pitch sending
            unique_url = f"https://email-test-{os.urandom(4).hex()}.com"
            t = db.add_target({"website_url": unique_url})
            res = email_outreach_client.send_pitch("editor@domain.com", "Pitch", "Body", t["id"])
            self.assertFalse(res["success"])
            self.assertFalse(res["is_simulation"])
            self.assertIn("Real sending aborted", res["error"])
            db.delete_target(t["id"])

    def test_email_test_connection_mocked_success(self):
        """Verifies all 4 separate diagnostic steps (SMTP auth, SMTP send, IMAP auth, IMAP read)."""
        mock_creds = {
            "email_address": "verified@gmail.com",
            "app_password": "abcdefghijklmnop",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_user": "verified@gmail.com",
            "smtp_pass": "abcdefghijklmnop",
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "imap_user": "verified@gmail.com",
            "imap_pass": "abcdefghijklmnop",
            "is_configured": True,
        }

        with patch.object(email_outreach_client, 'get_credentials', return_value=mock_creds), \
             patch('smtplib.SMTP') as mock_smtp_cls, \
             patch('imaplib.IMAP4_SSL') as mock_imap_cls:

            # Mock SMTP
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value = mock_smtp

            # Mock IMAP
            mock_imap = MagicMock()
            mock_imap.select.return_value = ("OK", [b"42"])
            mock_imap.search.return_value = ("OK", [b"1 2 3"])
            mock_imap_cls.return_value = mock_imap

            res = email_outreach_client.test_connection("verified@gmail.com")

            self.assertTrue(res["overall_success"])
            self.assertTrue(res["tests"]["smtp_auth"]["success"])
            self.assertTrue(res["tests"]["smtp_send"]["success"])
            self.assertTrue(res["tests"]["imap_auth"]["success"])
            self.assertTrue(res["tests"]["imap_read"]["success"])
            self.assertEqual(res["tests"]["imap_read"]["inbox_count"], 42)
            self.assertEqual(res["tests"]["imap_read"]["unread_count"], 3)


if __name__ == "__main__":
    unittest.main()
