"""NullState Mail Archive — download and index existing Zoho emails via IMAP.
Parallel load: copies emails into NullState ecosystem without touching originals.
"""

import os
import json
import imaplib
import email
import email.utils
import sqlite3
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from email.header import decode_header

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("nullstate-mail-archive")

DB_PATH = os.environ.get("NULLSTATE_DB_PATH", "src/core/nullstate.db")
ARCHIVE_DIR = Path(os.environ.get("NULLSTATE_MAIL_ARCHIVE", "data/mail_archive"))

ZOHO_IMAP_HOST = "imap.zoho.com"
ZOHO_IMAP_PORT = 993


def init_archive_db(conn=None):
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS mail_archive (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_id TEXT UNIQUE,
        folder TEXT DEFAULT 'INBOX',
        from_addr TEXT,
        to_addr TEXT,
        subject TEXT,
        date TEXT,
        body_plain TEXT,
        body_html TEXT,
        has_attachments INTEGER DEFAULT 0,
        archive_hash TEXT,
        archived_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS mail_archive_folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        total INTEGER DEFAULT 0,
        archived INTEGER DEFAULT 0,
        last_sync TEXT
    )""")
    conn.commit()
    return conn


def decode_mime_header(header_value):
    if not header_value:
        return ""
    parts = decode_header(header_value)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(charset or "utf-8", errors="replace"))
            except LookupError:
                result.append(part.decode("utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def extract_body(msg):
    body_plain = ""
    body_html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not body_plain:
                try:
                    body_plain = part.get_payload(decode=True).decode("utf-8", errors="replace")
                except:
                    pass
            elif ct == "text/html" and not body_html:
                try:
                    body_html = part.get_payload(decode=True).decode("utf-8", errors="replace")
                except:
                    pass
    else:
        ct = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            try:
                decoded = payload.decode("utf-8", errors="replace")
                if ct == "text/html":
                    body_html = decoded
                else:
                    body_plain = decoded
            except:
                pass
    return body_plain, body_html


def archive_email(msg, folder="INBOX", conn=None):
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
    
    msg_id = msg.get("Message-ID", "") or hashlib.sha256(str(msg).encode()).hexdigest()
    from_addr = decode_mime_header(msg.get("From", ""))
    to_addr = decode_mime_header(msg.get("To", ""))
    subject = decode_mime_header(msg.get("Subject", ""))
    date_str = msg.get("Date", "")
    body_plain, body_html = extract_body(msg)
    has_attachments = 1 if msg.is_multipart() and any(
        p.get_content_maintype() != "text" for p in msg.walk()
    ) else 0
    archive_hash = hashlib.sha256(f"{msg_id}:{from_addr}:{subject}:{date_str}".encode()).hexdigest()
    
    try:
        conn.execute(
            """INSERT OR IGNORE INTO mail_archive
               (msg_id, folder, from_addr, to_addr, subject, date,
                body_plain, body_html, has_attachments, archive_hash, archived_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (msg_id, folder, from_addr, to_addr, subject, date_str,
             body_plain[:100000] if body_plain else "",
             body_html[:500000] if body_html else "",
             has_attachments, archive_hash,
             datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        return True
    except Exception as e:
        log.error(f"Failed to archive msg {msg_id}: {e}")
        return False


class ZohoMailArchiver:
    """Download emails from Zoho via IMAP and archive into NullState."""
    
    def __init__(self, email_addr, password):
        self.email = email_addr
        self.password = password
        self.imap = None
        self.conn = None
    
    def connect(self):
        ctx = imaplib.IMAP4_SSL(ZOHO_IMAP_HOST, ZOHO_IMAP_PORT)
        ctx.login(self.email, self.password)
        self.imap = ctx
        log.info(f"Connected to Zoho IMAP as {self.email}")
        return True
    
    def list_folders(self):
        result, data = self.imap.list()
        folders = []
        for item in data:
            decoded = item.decode()
            parts = decoded.split(' "/" ')
            if len(parts) > 1:
                folders.append(parts[-1].strip('"'))
        return folders
    
    def archive_folder(self, folder="INBOX", batch_size=100):
        if not self.imap:
            raise RuntimeError("Not connected")
        
        self.imap.select(folder, readonly=True)
        result, data = self.imap.search(None, "ALL")
        if result != "OK":
            log.warning(f"No messages in {folder}")
            return 0
        
        msg_ids = data[0].split()
        total = len(msg_ids)
        log.info(f"Archiving {total} messages from {folder}")
        
        self.conn = init_archive_db()
        archived = 0
        
        for i in range(0, total, batch_size):
            batch = msg_ids[i:i+batch_size]
            for mid in batch:
                result, msg_data = self.imap.fetch(mid, "(RFC822)")
                if result != "OK":
                    continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                if archive_email(msg, folder, self.conn):
                    archived += 1
            
            if (i + batch_size) % 500 == 0 or i + batch_size >= total:
                log.info(f"  Archived {archived}/{total} from {folder}")
        
        # Update folder stats
        self.conn.execute(
            "INSERT OR REPLACE INTO mail_archive_folders (name, total, archived, last_sync) VALUES (?,?,?,?)",
            (folder, total, archived, datetime.now(timezone.utc).isoformat())
        )
        self.conn.commit()
        
        log.info(f"Done: {archived}/{total} archived from {folder}")
        return archived
    
    def archive_all(self):
        folders = self.list_folders()
        log.info(f"Found folders: {folders}")
        total = 0
        for folder in folders:
            total += self.archive_folder(folder)
        return total
    
    def disconnect(self):
        if self.imap:
            self.imap.logout()


def get_archive_stats(conn=None):
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT COUNT(*) FROM mail_archive").fetchone()
    total = rows[0] if rows else 0
    folders = conn.execute("SELECT name, total, archived, last_sync FROM mail_archive_folders").fetchall()
    return {
        "total_archived": total,
        "folders": [{"name": f[0], "total": f[1], "archived": f[2], "last_sync": f[3]} for f in folders]
    }


def build_search_index(conn=None):
    """Build a searchable index from archived emails."""
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS mail_archive_fts USING fts5(
            subject, from_addr, to_addr, body_plain, content=mail_archive, content_rowid=id
        )
    """)
    conn.execute("""
        INSERT OR IGNORE INTO mail_archive_fts(rowid, subject, from_addr, to_addr, body_plain)
        SELECT id, subject, from_addr, to_addr, body_plain FROM mail_archive
        WHERE id NOT IN (SELECT rowid FROM mail_archive_fts)
    """)
    conn.commit()


def search_archive(query, limit=50, conn=None):
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT id, subject, from_addr, to_addr, date, archive_hash FROM mail_archive_fts "
            "WHERE mail_archive_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit)
        ).fetchall()
        return [{"id": r[0], "subject": r[1], "from": r[2], "to": r[3], "date": r[4], "hash": r[5]} for r in rows]
    except Exception as e:
        log.error(f"Search failed: {e}")
        return []


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NullState Mail Archive")
    parser.add_argument("email", help="Zoho email to archive")
    parser.add_argument("--password", help="Zoho password (or set ZOHO_IMAP_PASSWORD env)")
    parser.add_argument("--folder", default="INBOX", help="Folder to archive (default: INBOX, use 'ALL' for all)")
    parser.add_argument("--stats", action="store_true", help="Show archive stats")
    parser.add_argument("--search", help="Search archived emails")
    args = parser.parse_args()
    
    if args.stats:
        stats = get_archive_stats()
        print(json.dumps(stats, indent=2))
    elif args.search:
        results = search_archive(args.search)
        for r in results:
            print(f"  [{r['id']}] {r['date']} | {r['from']} -> {r['to']} | {r['subject'][:80]}")
        print(f"\n  {len(results)} results")
    else:
        password = args.password or os.environ.get("ZOHO_IMAP_PASSWORD", "")
        if not password:
            print("ERROR: Password required. Set --password or ZOHO_IMAP_PASSWORD env var.")
            exit(1)
        archiver = ZohoMailArchiver(args.email, password)
        archiver.connect()
        total = archiver.archive_all() if args.folder == "ALL" else archiver.archive_folder(args.folder)
        archiver.disconnect()
        build_search_index()
        print(f"\nDone. {total} emails archived.")
        print(f"Run with --stats to see archive status.")
