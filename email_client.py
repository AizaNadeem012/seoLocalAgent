import os
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import make_msgid, formatdate
import re
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import database as db


def clean_app_password(raw_pass: str) -> str:
    """Removes spaces and trims Google App Passwords (e.g. 'abcd efgh ijkl mnop' -> 'abcdefghijklmnop')."""
    if not raw_pass:
        return ""
    return re.sub(r'\s+', '', raw_pass).strip()


class EmailOutreachClient:
    """
    Production-grade Gmail SMTP & IMAP Client.
    Handles real authenticated email dispatch for approved guest post pitches,
    monitors connected inbox for publisher replies, and validates credentials.
    """

    def __init__(self):
        pass

    def get_credentials(self, profile_id: Optional[int] = None) -> Dict[str, Any]:
        if profile_id:
            cfg = db.get_business_profile_by_id(profile_id, mask_passwords=False) or db.get_active_business_profile(mask_passwords=False)
        else:
            cfg = db.get_active_business_profile(mask_passwords=False)
        
        email_address = cfg.get("default_email") or cfg.get("smtp_user") or os.getenv("GMAIL_ADDRESS") or ""
        app_password = cfg.get("smtp_pass") or cfg.get("imap_pass") or os.getenv("GMAIL_APP_PASSWORD") or ""
        app_password = clean_app_password(app_password)

        smtp_host = cfg.get("smtp_host") or os.getenv("SMTP_HOST") or "smtp.gmail.com"
        smtp_port = int(cfg.get("smtp_port") or os.getenv("SMTP_PORT") or 587)
        smtp_user = cfg.get("smtp_user") or email_address
        smtp_pass = clean_app_password(cfg.get("smtp_pass") or app_password)

        imap_host = cfg.get("imap_host") or os.getenv("IMAP_HOST") or "imap.gmail.com"
        imap_port = int(cfg.get("imap_port") or os.getenv("IMAP_PORT") or 993)
        imap_user = cfg.get("imap_user") or email_address
        imap_pass = clean_app_password(cfg.get("imap_pass") or app_password)

        profile_name = cfg.get("name") or "Active Profile"

        return {
            "profile_id": cfg.get("id"),
            "profile_name": profile_name,
            "email_address": email_address,
            "app_password": app_password,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_user": smtp_user,
            "smtp_pass": smtp_pass,
            "imap_host": imap_host,
            "imap_port": imap_port,
            "imap_user": imap_user,
            "imap_pass": imap_pass,
            "sender_email": email_address,
            "is_configured": bool(email_address and smtp_pass),
        }

    def test_connection(self, custom_recipient: Optional[str] = None, profile_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Separately executes and measures:
        1. SMTP Authentication (smtp.gmail.com:587 STARTTLS)
        2. Test Email Delivery (to user's own address or specified recipient)
        3. IMAP Authentication (imap.gmail.com:993 SSL)
        4. Inbox Folder & Message Access
        """
        creds = self.get_credentials(profile_id=profile_id)
        
        results: Dict[str, Any] = {
            "overall_success": False,
            "email_address": creds["email_address"],
            "smtp_host": f"{creds['smtp_host']}:{creds['smtp_port']} (STARTTLS)",
            "imap_host": f"{creds['imap_host']}:{creds['imap_port']} (SSL/TLS)",
            "tests": {
                "smtp_auth": {"success": False, "message": "Not run", "latency_ms": 0},
                "smtp_send": {"success": False, "message": "Not run", "recipient": ""},
                "imap_auth": {"success": False, "message": "Not run", "latency_ms": 0},
                "imap_read": {"success": False, "message": "Not run", "inbox_count": 0, "unread_count": 0},
            },
            "error_summary": None,
        }

        if not creds["email_address"] or not creds["smtp_pass"]:
            results["error_summary"] = "Credentials missing. Please enter your Gmail Address and 16-character Google App Password."
            results["tests"]["smtp_auth"]["message"] = "Missing Gmail address or App Password"
            results["tests"]["imap_auth"]["message"] = "Missing Gmail address or App Password"
            return results

        test_recipient = custom_recipient or creds["email_address"]
        results["tests"]["smtp_send"]["recipient"] = test_recipient

        # ─── 1. Test SMTP Authentication ──────────────────────────────────────
        smtp_server = None
        try:
            t0 = time.time()
            smtp_server = smtplib.SMTP(creds["smtp_host"], creds["smtp_port"], timeout=12)
            smtp_server.ehlo()
            smtp_server.starttls()
            smtp_server.ehlo()
            smtp_server.login(creds["smtp_user"], creds["smtp_pass"])
            t1 = time.time()
            results["tests"]["smtp_auth"] = {
                "success": True,
                "message": f"Successfully authenticated with {creds['smtp_host']}:{creds['smtp_port']} via STARTTLS.",
                "latency_ms": int((t1 - t0) * 1000)
            }
        except smtplib.SMTPAuthenticationError as e:
            results["tests"]["smtp_auth"] = {
                "success": False,
                "message": f"Gmail SMTP Authentication Failed (535): Invalid credentials. Check your 2-Step Verification and 16-character App Password.",
                "details": str(e),
                "latency_ms": 0
            }
            results["error_summary"] = "SMTP Authentication failed. Verify your Gmail address and App Password."
            if smtp_server:
                try: smtp_server.quit()
                except Exception: pass
            return results
        except Exception as e:
            results["tests"]["smtp_auth"] = {
                "success": False,
                "message": f"SMTP Connection error: {str(e)}",
                "details": str(e),
                "latency_ms": 0
            }
            results["error_summary"] = f"SMTP Connection failed: {str(e)}"
            return results

        # ─── 2. Test Sending to Own Address ───────────────────────────────────
        try:
            msg_id = make_msgid(domain="linkforge.autonomous")
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[LinkForge Verification] Real Gmail SMTP Connection Test ({datetime.now().strftime('%H:%M:%S')})"
            msg["From"] = f"LinkForge Automation <{creds['email_address']}>"
            msg["To"] = test_recipient
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = msg_id

            test_body = (
                f"Hello,\n\n"
                f"This is an automated verification email sent by your LinkForge Autonomous Guest Post Engine.\n\n"
                f"Connection Details:\n"
                f"• SMTP Server: {creds['smtp_host']}:{creds['smtp_port']} (STARTTLS)\n"
                f"• Authenticated Account: {creds['email_address']}\n"
                f"• Destination: {test_recipient}\n"
                f"• Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Your Gmail SMTP sending integration is operational and ready for live editorial outreach."
            )
            msg.attach(MIMEText(test_body, "plain", "utf-8"))

            smtp_server.sendmail(creds["email_address"], [test_recipient], msg.as_string())
            smtp_server.quit()
            results["tests"]["smtp_send"] = {
                "success": True,
                "message": f"Test email successfully dispatched to {test_recipient}.",
                "recipient": test_recipient,
                "message_id": msg_id
            }
        except Exception as e:
            results["tests"]["smtp_send"] = {
                "success": False,
                "message": f"Failed to send test email: {str(e)}",
                "recipient": test_recipient
            }
            results["error_summary"] = f"SMTP Send failed: {str(e)}"
        finally:
            if smtp_server:
                try: smtp_server.quit()
                except Exception: pass

        # ─── 3. Test IMAP Authentication ──────────────────────────────────────
        imap_client = None
        try:
            t0 = time.time()
            imap_client = imaplib.IMAP4_SSL(creds["imap_host"], creds["imap_port"], timeout=12)
            imap_client.login(creds["imap_user"], creds["imap_pass"])
            t1 = time.time()
            results["tests"]["imap_auth"] = {
                "success": True,
                "message": f"Successfully authenticated with {creds['imap_host']}:{creds['imap_port']} via SSL/TLS.",
                "latency_ms": int((t1 - t0) * 1000)
            }
        except imaplib.IMAP4.error as e:
            results["tests"]["imap_auth"] = {
                "success": False,
                "message": f"Gmail IMAP Authentication Failed: {str(e)}. Verify that IMAP is enabled in your Gmail Settings -> Forwarding and POP/IMAP.",
                "details": str(e),
                "latency_ms": 0
            }
            results["error_summary"] = "IMAP Authentication failed. Check your App Password and enable IMAP in Gmail Settings."
            return results
        except Exception as e:
            results["tests"]["imap_auth"] = {
                "success": False,
                "message": f"IMAP Connection error: {str(e)}",
                "details": str(e),
                "latency_ms": 0
            }
            results["error_summary"] = f"IMAP Connection error: {str(e)}"
            return results

        # ─── 4. Test IMAP Read & Folder Access ────────────────────────────────
        try:
            status, folder_data = imap_client.select("INBOX", readonly=True)
            if status != "OK":
                raise Exception(f"Unable to select INBOX: {status}")

            total_msgs = int(folder_data[0].decode() if folder_data and folder_data[0] else 0)

            # Check unread count
            status_unread, unread_data = imap_client.search(None, '(UNSEEN)')
            unread_ids = unread_data[0].split() if unread_data and unread_data[0] else []
            unread_count = len(unread_ids)

            results["tests"]["imap_read"] = {
                "success": True,
                "message": f"INBOX access verified. Found {total_msgs} total messages ({unread_count} unread).",
                "inbox_count": total_msgs,
                "unread_count": unread_count,
            }

            imap_client.close()
            imap_client.logout()
        except Exception as e:
            results["tests"]["imap_read"] = {
                "success": False,
                "message": f"Failed to read INBOX status: {str(e)}",
                "inbox_count": 0,
                "unread_count": 0
            }
            results["error_summary"] = f"IMAP Read failed: {str(e)}"
        finally:
            if imap_client:
                try: imap_client.logout()
                except Exception: pass

        # Determine overall status
        all_passed = (
            results["tests"]["smtp_auth"]["success"] and
            results["tests"]["smtp_send"]["success"] and
            results["tests"]["imap_auth"]["success"] and
            results["tests"]["imap_read"]["success"]
        )
        results["overall_success"] = all_passed
        return results

    def send_pitch(
        self, 
        recipient: str, 
        subject: str, 
        body_text: str, 
        target_id: int,
        profile_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Dispatches real approved guest post pitch via Gmail SMTP using the specified profile's credentials.
        Does NOT simulate when real sending is required.
        """
        target = db.get_target_by_id(target_id) or {}
        p_id = profile_id or target.get("business_profile_id")
        creds = self.get_credentials(profile_id=p_id)
        msg_id = make_msgid(domain="linkforge.autonomous")

        if not creds["is_configured"]:
            error_msg = "Real sending aborted: Gmail SMTP credentials are not configured. Go to 'Email Outreach' and enter your Gmail address and App Password."
            db.update_target(target_id, {
                "error_log": error_msg,
                "status": "Needs Approval"
            })
            return {
                "success": False,
                "live": True,
                "error": error_msg,
                "is_simulation": False
            }

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Editorial Outreach <{creds['email_address']}>"
            msg["To"] = recipient
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = msg_id

            part_text = MIMEText(body_text, "plain", "utf-8")
            msg.attach(part_text)

            server = smtplib.SMTP(creds["smtp_host"], creds["smtp_port"], timeout=15)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(creds["smtp_user"], creds["smtp_pass"])
            server.sendmail(creds["email_address"], [recipient], msg.as_string())
            server.quit()

            # Record success in target record
            log_entry = f"Pitch email live dispatched to {recipient} via {creds['smtp_host']}:{creds['smtp_port']}."
            db.update_target(target_id, {
                "email_message_id": msg_id,
                "status": "Awaiting Editorial Reply",
                "stage": "EDITORIAL_WAIT",
                "error_log": log_entry
            })

            return {
                "success": True,
                "live": True,
                "is_simulation": False,
                "message_id": msg_id,
                "recipient": recipient,
                "message": log_entry
            }
        except Exception as e:
            err = f"Gmail SMTP dispatch failed to {recipient}: {str(e)}"
            db.update_target(target_id, {
                "error_log": err,
                "status": "Failed"
            })
            return {
                "success": False,
                "live": True,
                "is_simulation": False,
                "error": err
            }

    def check_inbox_replies(self, profile_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Polls connected Gmail IMAP inbox for unread responses from editors,
        matches them against queued campaigns, and flags editorial approval/fee requests.
        """
        creds = self.get_credentials(profile_id=profile_id)
        if not creds["is_configured"]:
            return {
                "success": False,
                "message": "Gmail IMAP credentials not configured. Configure Gmail address and App Password in Email Settings."
            }

        matched_replies = []
        try:
            mail = imaplib.IMAP4_SSL(creds["imap_host"], creds["imap_port"], timeout=15)
            mail.login(creds["imap_user"], creds["imap_pass"])
            mail.select("INBOX")

            status, messages = mail.search(None, '(UNSEEN)')
            msg_ids = messages[0].split() if messages and messages[0] else []

            targets = db.get_targets()

            for mid in msg_ids[-30:]:  # Check recent 30 unread messages
                status, data = mail.fetch(mid, '(RFC822)')
                for response_part in data:
                    if isinstance(response_part, tuple):
                        raw_msg = email.message_from_bytes(response_part[1])
                        subject = raw_msg["Subject"] or ""
                        sender = raw_msg["From"] or ""
                        
                        body = ""
                        if raw_msg.is_multipart():
                            for part in raw_msg.walk():
                                if part.get_content_type() == "text/plain":
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body = payload.decode("utf-8", errors="ignore")
                                    break
                        else:
                            payload = raw_msg.get_payload(decode=True)
                            if payload:
                                body = payload.decode("utf-8", errors="ignore")

                        # Match with target website domains or message-ID
                        for t in targets:
                            domain_match = re.sub(r'^https?://(www\.)?', '', t['website_url']).split('/')[0].lower()
                            in_reply = (t.get("email_message_id") and t["email_message_id"] in str(raw_msg))
                            matches_domain = domain_match and (domain_match in sender.lower() or domain_match in subject.lower())

                            if in_reply or matches_domain:
                                lower_b = body.lower()
                                if any(ok in lower_b for ok in ["approved", "accepted", "send draft", "looks good", "send article", "happy to review"]):
                                    db.record_editorial_reply(t["id"], body[:600], "Approved by Editor")
                                    matched_replies.append({"target_id": t["id"], "status": "Approved by Editor", "sender": sender, "domain": domain_match})
                                elif any(fee in lower_b for fee in ["fee", "$", "cost", "sponsored", "commercial", "payment"]):
                                    db.record_editorial_reply(t["id"], body[:600], "Needs Approval")
                                    db.update_target(t["id"], {"workflow": "Workflow E (Paid / Review)", "status": "Needs Approval"})
                                    matched_replies.append({"target_id": t["id"], "status": "Paid Offer Detected", "sender": sender, "domain": domain_match})
                                else:
                                    db.record_editorial_reply(t["id"], body[:600], "Awaiting Editorial Reply")
                                    matched_replies.append({"target_id": t["id"], "status": "Reply Received", "sender": sender, "domain": domain_match})
                                break

            mail.close()
            mail.logout()

            return {
                "success": True,
                "matched_count": len(matched_replies),
                "matches": matched_replies,
                "message": f"Scanned unread messages. Found {len(matched_replies)} publisher responses matching active campaigns."
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"IMAP inbox scan error: {str(e)}"
            }


email_outreach_client = EmailOutreachClient()
