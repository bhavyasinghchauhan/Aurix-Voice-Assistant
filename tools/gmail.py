"""Gmail integration via the Gmail API (OAuth2).

Requires a credentials.json from Google Cloud Console placed at
config/gmail_credentials.json. On first use, a browser window opens
for the OAuth consent flow; the resulting token is cached at
config/gmail_token.json for subsequent runs.
"""
import asyncio
import base64
import os
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.error_handler import ToolExecutionError
from utils.logger import get_logger

logger = get_logger(__name__)

_CONFIG_DIR = Path(os.path.dirname(os.path.dirname(__file__))) / "config"
CREDENTIALS_PATH = _CONFIG_DIR / "gmail_credentials.json"
TOKEN_PATH = _CONFIG_DIR / "gmail_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

_service_cache = None


def _get_service():
    """Build and cache the Gmail API service. Thread-safe enough for our use."""
    global _service_cache
    if _service_cache is not None:
        return _service_cache

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise ToolExecutionError(
            "Gmail dependencies missing. Run: "
            "pip install google-auth google-auth-oauthlib google-api-python-client"
        )

    if not CREDENTIALS_PATH.exists():
        raise ToolExecutionError(
            f"Gmail credentials not found at {CREDENTIALS_PATH}. "
            "See GMAIL_SETUP.md for instructions."
        )

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        logger.info("Gmail token saved")

    _service_cache = build("gmail", "v1", credentials=creds)
    logger.info("Gmail API service initialized")
    return _service_cache


def _header(msg: dict, name: str) -> str:
    """Extract a header value from a Gmail message payload."""
    for h in msg.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _extract_sender_name(from_header: str) -> str:
    """Pull just the display name from 'Name <email>' format."""
    if "<" in from_header:
        return from_header.split("<")[0].strip().strip('"')
    return from_header.split("@")[0]


# ─── Public tool functions ──────────────────────────────────────────────────

async def check_unread_count() -> dict:
    """Get unread email count with today's count and top senders."""
    loop = asyncio.get_event_loop()

    def _fetch():
        logger.debug("Gmail check_unread_count: getting service...")
        svc = _get_service()
        logger.debug("Gmail service acquired, fetching total unread...")

        total_result = svc.users().messages().list(
            userId="me", q="is:unread", maxResults=1
        ).execute()
        total_unread = total_result.get("resultSizeEstimate", 0)
        logger.debug(f"Gmail total unread: {total_unread}")

        today_str = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        logger.debug(f"Gmail fetching today's unread (after:{today_str})...")
        today_result = svc.users().messages().list(
            userId="me", q=f"is:unread after:{today_str}", maxResults=1
        ).execute()
        new_today = today_result.get("resultSizeEstimate", 0)
        logger.debug(f"Gmail new today: {new_today}")

        top_senders = []
        if total_unread > 0:
            logger.debug("Gmail fetching recent unread for sender extraction...")
            recent = svc.users().messages().list(
                userId="me", q="is:unread", maxResults=5
            ).execute()
            msg_list = recent.get("messages", [])[:5]
            logger.debug(f"Gmail got {len(msg_list)} message refs for sender lookup")
            for msg_ref in msg_list:
                msg = svc.users().messages().get(
                    userId="me", id=msg_ref["id"], format="metadata",
                    metadataHeaders=["From"],
                ).execute()
                from_header = _header(msg, "From")
                sender = _extract_sender_name(from_header)
                logger.debug(f"Gmail sender: {from_header} -> {sender}")
                if sender and sender not in top_senders:
                    top_senders.append(sender)
                if len(top_senders) >= 3:
                    break

        logger.debug(f"Gmail check complete: {total_unread} unread, {new_today} today, senders={top_senders}")
        return total_unread, new_today, top_senders

    try:
        total_unread, new_today, top_senders = await loop.run_in_executor(None, _fetch)
    except ToolExecutionError:
        raise
    except Exception as e:
        logger.error(f"Gmail check_unread_count failed: {e}", exc_info=True)
        raise ToolExecutionError(f"Gmail check failed: {e}") from e

    sender_text = ", ".join(top_senders) if top_senders else "none"
    summary = (
        f"You have {total_unread} unread email{'s' if total_unread != 1 else ''}, "
        f"{new_today} new today. Recent from: {sender_text}."
    )

    logger.info(f"Unread: {total_unread}, today: {new_today}, senders: {sender_text}")
    return {
        "unread_count": total_unread,
        "new_today": new_today,
        "top_senders": top_senders,
        "summary": summary,
        "brief": summary,
    }


async def get_recent_emails(count: int = 5) -> dict:
    """Get summaries of the most recent emails."""
    logger.debug(f"Gmail get_recent_emails called with count={count}")
    loop = asyncio.get_event_loop()

    def _fetch():
        svc = _get_service()
        logger.debug(f"Gmail fetching {count} recent emails...")
        results = svc.users().messages().list(
            userId="me", maxResults=min(count, 20)
        ).execute()
        message_ids = results.get("messages", [])

        emails = []
        for msg_ref in message_ids:
            msg = svc.users().messages().get(
                userId="me", id=msg_ref["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            emails.append({
                "id": msg["id"],
                "from": _header(msg, "From"),
                "subject": _header(msg, "Subject"),
                "date": _header(msg, "Date"),
                "snippet": msg.get("snippet", ""),
                "unread": "UNREAD" in msg.get("labelIds", []),
            })
        return emails

    try:
        emails = await loop.run_in_executor(None, _fetch)
    except ToolExecutionError:
        raise
    except Exception as e:
        logger.error(f"Gmail get_recent_emails failed: {e}", exc_info=True)
        raise ToolExecutionError(f"Gmail fetch failed: {e}") from e

    lines = []
    for e in emails:
        flag = "[NEW] " if e["unread"] else ""
        lines.append(f"{flag}{e['from']}: {e['subject']}")

    summary = "; ".join(lines[:5]) if lines else "No emails found"
    logger.info(f"Fetched {len(emails)} recent emails")

    return {
        "emails": emails,
        "count": len(emails),
        "summary": summary,
    }


async def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email via Gmail."""
    logger.debug(f"Gmail send_email called: to={to}, subject={subject}")
    loop = asyncio.get_event_loop()

    def _send():
        svc = _get_service()
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = svc.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return sent.get("id", "")

    try:
        msg_id = await loop.run_in_executor(None, _send)
    except ToolExecutionError:
        raise
    except Exception as e:
        raise ToolExecutionError(f"Gmail send failed: {e}") from e

    logger.info(f"Email sent to {to} (id={msg_id})")
    return {
        "message_id": msg_id,
        "to": to,
        "subject": subject,
        "summary": f"Email sent to {to}: \"{subject}\"",
    }


async def search_emails(query: str, count: int = 5) -> dict:
    """Search emails by keyword / Gmail search syntax."""
    logger.debug(f"Gmail search_emails called: query='{query}', count={count}")
    loop = asyncio.get_event_loop()

    def _search():
        svc = _get_service()
        results = svc.users().messages().list(
            userId="me", q=query, maxResults=min(count, 20)
        ).execute()
        message_ids = results.get("messages", [])

        emails = []
        for msg_ref in message_ids:
            msg = svc.users().messages().get(
                userId="me", id=msg_ref["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            emails.append({
                "id": msg["id"],
                "from": _header(msg, "From"),
                "subject": _header(msg, "Subject"),
                "date": _header(msg, "Date"),
                "snippet": msg.get("snippet", ""),
            })
        return emails

    try:
        emails = await loop.run_in_executor(None, _search)
    except ToolExecutionError:
        raise
    except Exception as e:
        logger.error(f"Gmail search_emails failed: {e}", exc_info=True)
        raise ToolExecutionError(f"Gmail search failed: {e}") from e

    lines = [f"{e['from']}: {e['subject']}" for e in emails]
    summary = (
        f"Found {len(emails)} email(s) for '{query}': " + "; ".join(lines[:3])
        if emails else f"No emails found for '{query}'"
    )
    logger.info(f"Gmail search '{query}': {len(emails)} results")

    return {
        "query": query,
        "emails": emails,
        "count": len(emails),
        "summary": summary,
    }
