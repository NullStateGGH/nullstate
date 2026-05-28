"""NullState Mail Server — Full-scale email service.
Multi-provider outbound relay, account management, REST API, webhook processing.
Entry point: python3 -m nullstate.mail.server or nullstate email
"""

import os
import json
import sqlite3
import asyncio
import smtplib
import logging
import argparse
import importlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, asdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("nullstate-mail")

DB_PATH = os.environ.get("NULLSTATE_DB_PATH", "src/core/nullstate.db")
SMTP_PORT = int(os.environ.get("NULLSTATE_SMTP_PORT", "2525"))
HTTP_PORT = int(os.environ.get("NULLSTATE_MAIL_HTTP_PORT", "8083"))

DEFAULT_DOMAIN = os.environ.get("NULLSTATE_MAIL_DOMAIN", "greensol.me")
DEFAULT_FROM = os.environ.get("NULLSTATE_MAIL_FROM", "ceo@greensol.me")

RELAY_HOST = os.environ.get("NULLSTATE_MAIL_RELAY_HOST", "")
RELAY_PORT = int(os.environ.get("NULLSTATE_MAIL_RELAY_PORT", "587"))
RELAY_USER = os.environ.get("NULLSTATE_MAIL_RELAY_USER", "")
RELAY_PASS = os.environ.get("NULLSTATE_MAIL_RELAY_PASS", "")

# ─── Data Models ─────────────────────────────────────────────────────

@dataclass
class MailAccount:
    email: str
    name: str = ""
    forward_to: str = ""
    catch_all: bool = False
    active: bool = True
    created_at: str = ""
    last_used: str = ""

@dataclass
class OutboundMessage:
    id: int = 0
    from_addr: str = ""
    to_addr: str = ""
    subject: str = ""
    body: str = ""
    html_body: str = ""
    status: str = "pending"
    attempts: int = 0
    error: str = ""
    created_at: str = ""
    sent_at: str = ""

# ─── Database ─────────────────────────────────────────────────────────

def migrate_schema(conn):
    """Migrate old schema to new one if needed."""
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

    if "mail_queue" in tables and "mail_accounts" not in tables:
        conn.execute("DROP TABLE IF EXISTS mail_queue")

    if "mail_accounts" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(mail_accounts)").fetchall()]
        old_cols = {"agent_id", "kya_token", "last_login"}
        if old_cols.issubset(set(cols)):
            conn.execute("DROP TABLE mail_accounts")

    if "mail_queue" in tables:
        conn.execute("DROP TABLE IF EXISTS mail_queue")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    migrate_schema(conn)

    conn.execute("""CREATE TABLE IF NOT EXISTS mail_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        name TEXT DEFAULT '',
        forward_to TEXT DEFAULT '',
        catch_all INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        created_at TEXT,
        last_used TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS outbound_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_addr TEXT,
        to_addr TEXT,
        subject TEXT,
        body TEXT,
        html_body TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        attempts INTEGER DEFAULT 0,
        error TEXT DEFAULT '',
        created_at TEXT,
        sent_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS relay_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        host TEXT NOT NULL,
        port INTEGER DEFAULT 587,
        username TEXT DEFAULT '',
        password TEXT DEFAULT '',
        use_tls INTEGER DEFAULT 1,
        active INTEGER DEFAULT 1,
        label TEXT DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS mail_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        subject_template TEXT,
        body_template TEXT,
        html_template TEXT DEFAULT '',
        created_at TEXT
    )""")
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

# ─── Account Management ──────────────────────────────────────────────

class AccountManager:
    def __init__(self, db=None):
        self.db = db or init_db()

    def create_account(self, email: str, name: str = "", forward_to: str = "", catch_all: bool = False) -> MailAccount:
        now = datetime.now(timezone.utc).isoformat()
        try:
            self.db.execute(
                "INSERT INTO mail_accounts (email, name, forward_to, catch_all, created_at) VALUES (?,?,?,?,?)",
                (email, name, forward_to, 1 if catch_all else 0, now)
            )
            self.db.commit()
            log.info(f"Created mail account: {email}")
            return MailAccount(email=email, name=name, forward_to=forward_to, catch_all=catch_all, created_at=now)
        except sqlite3.IntegrityError:
            log.warning(f"Account already exists: {email}")
            return self.get_account(email)

    def get_account(self, email: str) -> Optional[MailAccount]:
        row = self.db.execute("SELECT * FROM mail_accounts WHERE email = ?", (email,)).fetchone()
        if row:
            return MailAccount(
                email=row[1], name=row[2] or "", forward_to=row[3] or "",
                catch_all=bool(row[4]), active=bool(row[5]),
                created_at=row[6] or "", last_used=row[7] or ""
            )
        return None

    def list_accounts(self, active_only: bool = True) -> list[MailAccount]:
        query = "SELECT * FROM mail_accounts"
        if active_only:
            query += " WHERE active = 1"
        rows = self.db.execute(query).fetchall()
        return [MailAccount(
            email=r[1], name=r[2] or "", forward_to=r[3] or "",
            catch_all=bool(r[4]), active=bool(r[5]),
            created_at=r[6] or "", last_used=r[7] or ""
        ) for r in rows]

    def delete_account(self, email: str) -> bool:
        self.db.execute("DELETE FROM mail_accounts WHERE email = ?", (email,))
        self.db.commit()
        return self.db.total_changes > 0

    def route_inbound(self, to_addr: str) -> Optional[str]:
        """Route inbound email to the correct delivery address."""
        acct = self.get_account(to_addr)
        if acct and acct.active:
            return acct.forward_to or acct.email

        # Check catch-all
        domain = to_addr.split("@")[-1] if "@" in to_addr else ""
        catch = self.db.execute(
            "SELECT forward_to, email FROM mail_accounts WHERE catch_all = 1 AND email LIKE ?",
            (f"%@{domain}",)
        ).fetchone()
        if catch:
            return catch[0] or catch[1]
        return None

# ─── Outbound Sender ─────────────────────────────────────────────────

class OutboundSender:
    def __init__(self, db=None):
        self.db = db or init_db()

    def queue(self, from_addr: str, to_addr: str, subject: str,
              body: str = "", html_body: str = "") -> int:
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "INSERT INTO outbound_queue (from_addr, to_addr, subject, body, html_body, created_at) VALUES (?,?,?,?,?,?)",
            (from_addr, to_addr, subject, body, html_body, now)
        )
        self.db.commit()
        msg_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]
        log.info(f"Queued outbound #{msg_id}: {subject} -> {to_addr}")
        return msg_id

    def send_message(self, msg: OutboundMessage) -> bool:
        """Send a single queued message via configured relay."""
        if not RELAY_HOST:
            log.warning("No SMTP relay configured, using local sendmail fallback")
            return self._send_local(msg)

        # Use relay user as envelope from (required by most relays)
        envelope_from = RELAY_USER if RELAY_USER else msg.from_addr

        try:
            server = smtplib.SMTP(RELAY_HOST, RELAY_PORT, timeout=30)
            server.ehlo()
            if RELAY_PORT == 587:
                server.starttls()
                server.ehlo()
            if RELAY_USER and RELAY_PASS:
                server.login(RELAY_USER, RELAY_PASS)

            if msg.html_body:
                mime = MIMEMultipart("alternative")
                mime.attach(MIMEText(msg.body, "plain", "utf-8"))
                mime.attach(MIMEText(msg.html_body, "html", "utf-8"))
            else:
                mime = MIMEText(msg.body, "plain", "utf-8")

            mime["Subject"] = msg.subject
            mime["From"] = msg.from_addr
            mime["To"] = msg.to_addr
            mime["Message-ID"] = f"<nullstate-{msg.id}-{datetime.now().timestamp()}@nullstate.io>"

            server.sendmail(envelope_from, [msg.to_addr], mime.as_string())
            server.quit()
            return True
        except Exception as e:
            log.error(f"SMTP relay failed for #{msg.id}: {e}")
            return False

    def _send_local(self, msg: OutboundMessage) -> bool:
        """Fallback: use local sendmail."""
        try:
            import subprocess
            pipe = subprocess.Popen(["/usr/sbin/sendmail", "-t", msg.to_addr],
                                    stdin=subprocess.PIPE)
            content = f"From: {msg.from_addr}\nTo: {msg.to_addr}\nSubject: {msg.subject}\n\n{msg.body}"
            pipe.communicate(content.encode())
            return pipe.returncode == 0
        except Exception as e:
            log.error(f"Local sendmail failed for #{msg.id}: {e}")
            return False

    def process_queue(self, batch_size: int = 10) -> tuple[int, int]:
        """Process pending outbound messages. Returns (sent, failed)."""
        rows = self.db.execute(
            "SELECT * FROM outbound_queue WHERE status = 'pending' AND attempts < 5 ORDER BY id LIMIT ?",
            (batch_size,)
        ).fetchall()

        sent = 0
        failed = 0
        for row in rows:
            msg = OutboundMessage(
                id=row[0], from_addr=row[1], to_addr=row[2],
                subject=row[3], body=row[4], html_body=row[5] or "",
                status=row[6], attempts=row[7], error=row[8] or "",
                created_at=row[9] or ""
            )
            success = self.send_message(msg)
            now = datetime.now(timezone.utc).isoformat()
            if success:
                self.db.execute(
                    "UPDATE outbound_queue SET status = 'sent', sent_at = ? WHERE id = ?",
                    (now, msg.id)
                )
                sent += 1
            else:
                self.db.execute(
                    "UPDATE outbound_queue SET attempts = attempts + 1, error = ? WHERE id = ?",
                    ("Delivery failed, will retry" if msg.attempts < 4 else "Permanent failure", msg.id)
                )
                if msg.attempts >= 4:
                    self.db.execute(
                        "UPDATE outbound_queue SET status = 'failed' WHERE id = ?",
                        (msg.id,)
                    )
                failed += 1
            self.db.commit()

        return sent, failed

# ─── SMTP Receiver ───────────────────────────────────────────────────

class NullStateSMTPServer:
    def __init__(self, host="0.0.0.0", port=2525):
        self.host = host
        self.port = port
        self.server = None
        self.accounts = AccountManager()
        self.sender = OutboundSender()

    async def handle_client(self, reader, writer):
        _peername = writer.get_extra_info('peername')

        def send(msg):
            writer.write(f"{msg}\r\n".encode())

        send("220 NullState Mail Service Ready")

        data = await reader.readuntil(b"\r\n")
        line = data.decode().strip()

        if not (line.startswith("EHLO") or line.startswith("HELO")):
            send("500 Command not recognized")
            writer.close()
            return

        send("250 Hello, pleased to meet you")

        data = await reader.readuntil(b"\r\n")
        from_addr = data.decode().strip().replace("MAIL FROM:<", "").replace(">", "")
        send(f"250 {from_addr}... Sender OK")

        data = await reader.readuntil(b"\r\n")
        to_addr = data.decode().strip().replace("RCPT TO:<", "").replace(">", "")

        # Route to internal account or forward
        delivery_addr = self.accounts.route_inbound(to_addr)
        if delivery_addr:
            send(f"250 {to_addr}... Recipient OK")
        else:
            send(f"550 {to_addr}... No such user here")
            writer.close()
            return

        data = await reader.readuntil(b"\r\n")
        send("354 Enter mail, end with \".\" on a line by itself")

        body_lines = []
        while True:
            data = await reader.readuntil(b"\r\n")
            line = data.decode().strip()
            if line == ".":
                break
            body_lines.append(line)

        body = "\n".join(body_lines)

        # Queue for delivery
        self.sender.queue(from_addr, delivery_addr, "NullState Mail Forward", body)

        send("250 Message accepted for delivery")

        try:
            await reader.readuntil(b"\r\n")
        except Exception:
            pass
        send("221 NullState Mail Service closing connection")
        writer.close()

    async def start(self):
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        addr = self.server.sockets[0].getsockname()
        log.info(f"SMTP receiver on {addr[0]}:{addr[1]}")
        async with self.server:
            await self.server.serve_forever()

    def stop(self):
        if self.server:
            self.server.close()

# ─── REST API ─────────────────────────────────────────────────────────

class MailAPI:
    def __init__(self, host="0.0.0.0", port=8083):
        self.host = host
        self.port = port
        self.accounts = AccountManager()
        self.sender = OutboundSender()

    async def handle_request(self, reader, writer):
        request = await reader.readuntil(b"\r\n\r\n")
        lines = request.decode().split("\r\n")
        first = lines[0].split()
        if len(first) < 2:
            writer.close()
            return

        method = first[0]
        path = first[1]

        # Read body if present
        body = ""
        content_length = 0
        for line in lines[1:]:
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":")[1].strip())

        if content_length > 0:
            body = (await reader.readexactly(content_length)).decode()

        response = self._route(method, path, body)
        status_map = {"ok": "200 OK", "error": "400 Bad Request", "not_found": "404 Not Found"}

        resp_body = json.dumps(response)
        writer.write(f"HTTP/1.1 {status_map.get(response.get('status', 'ok'), '200 OK')}\r\n".encode())
        writer.write(b"Content-Type: application/json\r\n")
        writer.write(f"Content-Length: {len(resp_body)}\r\n".encode())
        writer.write(b"Connection: close\r\n\r\n")
        writer.write(resp_body.encode())
        writer.close()

    def _route(self, method, path, body):
        data = json.loads(body) if body else {}

        if path == "/health":
            return {"status": "ok", "service": "nullstate-mail"}

        elif path == "/api/accounts" and method == "GET":
            accounts = self.accounts.list_accounts()
            return {"status": "ok", "accounts": [asdict(a) for a in accounts]}

        elif path == "/api/accounts" and method == "POST":
            acct = self.accounts.create_account(
                email=data.get("email", ""),
                name=data.get("name", ""),
                forward_to=data.get("forward_to", ""),
                catch_all=data.get("catch_all", False)
            )
            return {"status": "ok", "account": asdict(acct)}

        elif path.startswith("/api/accounts/") and method == "DELETE":
            email = path.replace("/api/accounts/", "")
            self.accounts.delete_account(email)
            return {"status": "ok", "deleted": email}

        elif path == "/api/send" and method == "POST":
            msg_id = self.sender.queue(
                from_addr=data.get("from", DEFAULT_FROM),
                to_addr=data.get("to", ""),
                subject=data.get("subject", ""),
                body=data.get("body", ""),
                html_body=data.get("html", "")
            )
            return {"status": "ok", "queued": msg_id}

        elif path == "/api/queue/process" and method == "POST":
            sent, failed = self.sender.process_queue()
            return {"status": "ok", "sent": sent, "failed": failed}

        elif path == "/api/queue" and method == "GET":
            rows = self.sender.db.execute(
                "SELECT * FROM outbound_queue ORDER BY id DESC LIMIT 50"
            ).fetchall()
            msgs = [{
                "id": r[0], "from": r[1], "to": r[2], "subject": r[3],
                "status": r[6], "attempts": r[7], "error": r[8],
                "created_at": r[9], "sent_at": r[10]
            } for r in rows]
            return {"status": "ok", "messages": msgs}

        elif path == "/api/archive/stats" and method == "GET":
            conn = init_db()
            row = conn.execute("SELECT COUNT(*) FROM mail_archive").fetchone()
            folders = conn.execute(
                "SELECT name, total, archived, last_sync FROM mail_archive_folders"
            ).fetchall()
            return {"status": "ok", "total_archived": row[0] if row else 0,
                    "folders": [{"name": f[0], "total": f[1], "archived": f[2], "last_sync": f[3]} for f in folders]}

        elif path == "/api/archive/search" and method == "POST":
            query = data.get("query", "")
            if not query:
                return {"status": "error", "message": "Missing query"}
            conn = init_db()
            try:
                rows = conn.execute(
                    "SELECT id, subject, from_addr, to_addr, date, archive_hash FROM mail_archive "
                    "WHERE subject LIKE ? OR from_addr LIKE ? OR to_addr LIKE ? OR body_plain LIKE ? "
                    "ORDER BY date DESC LIMIT 50",
                    (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%")
                ).fetchall()
                return {"status": "ok", "results": [
                    {"id": r[0], "subject": r[1], "from": r[2], "to": r[3], "date": r[4], "hash": r[5]}
                    for r in rows
                ]}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        return {"status": "not_found"}

    async def start(self):
        server = await asyncio.start_server(self.handle_request, self.host, self.port)
        log.info(f"Mail API on {self.host}:{self.port}")
        async with server:
            await server.serve_forever()

# ─── CLI Commands ─────────────────────────────────────────────────────

def cmd_create_account(args):
    db = init_db()
    mgr = AccountManager(db)
    acct = mgr.create_account(args.email, args.name, args.forward, args.catch_all)
    print(f"Created: {acct.email}")

def cmd_list_accounts(args):
    db = init_db()
    mgr = AccountManager(db)
    for a in mgr.list_accounts():
        print(f"  {a.email:35s} {'catch-all' if a.catch_all else 'forward: ' + a.forward_to if a.forward_to else 'local'}")

def cmd_send(args):
    db = init_db()
    sender = OutboundSender(db)
    msg_id = sender.queue(args.from_addr, args.to, args.subject, args.body)
    print(f"Queued message #{msg_id}")
    if args.send_now:
        sent, failed = sender.process_queue()
        print(f"Processed: {sent} sent, {failed} failed")

def cmd_process(args):
    db = init_db()
    sender = OutboundSender(db)
    sent, failed = sender.process_queue()
    print(f"Processed: {sent} sent, {failed} failed")

def cmd_serve(args):
    """Start all mail server services."""
    init_db()

    async def run_all():
        smtp = NullStateSMTPServer(port=args.smtp_port or SMTP_PORT)
        api = MailAPI(port=args.api_port or HTTP_PORT)

        await asyncio.gather(
            smtp.start(),
            api.start()
        )

    print("NullState Mail Server v3")
    print(f"  SMTP receiver : 0.0.0.0:{args.smtp_port or SMTP_PORT}")
    print(f"  API          : 0.0.0.0:{args.api_port or HTTP_PORT}")
    print(f"  Relay        : {RELAY_HOST or 'local sendmail'}")
    print(f"  Domain       : {DEFAULT_DOMAIN}")
    print(f"  DB           : {DB_PATH}")

    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        print("\nNullState Mail Server stopped")

# ─── Entry Point ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NullState Mail Server")
    sub = parser.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="Start all services")
    p_serve.add_argument("--smtp-port", type=int, default=2525)
    p_serve.add_argument("--api-port", type=int, default=8083)

    p_create = sub.add_parser("create", help="Create mail account")
    p_create.add_argument("email")
    p_create.add_argument("--name", default="")
    p_create.add_argument("--forward", default="")
    p_create.add_argument("--catch-all", action="store_true")

    _p_list = sub.add_parser("list", help="List mail accounts")

    p_send = sub.add_parser("send", help="Send an email")
    p_send.add_argument("--from", dest="from_addr", default=DEFAULT_FROM)
    p_send.add_argument("--to", required=True)
    p_send.add_argument("--subject", default="NullState Notification")
    p_send.add_argument("--body", default="")
    p_send.add_argument("--send-now", action="store_true", help="Process immediately")

    _p_process = sub.add_parser("process", help="Process outbound queue")

    p_archive = sub.add_parser("archive", help="Manage email archive")
    p_archive.add_argument("--stats", action="store_true", help="Show archive stats")
    p_archive.add_argument("--search", help="Search archived emails")
    p_archive.add_argument("--zoho-user", help="Zoho email to archive (requires --zoho-pass)")
    p_archive.add_argument("--zoho-pass", help="Zoho password")

    args = parser.parse_args()

    if args.command == "create":
        cmd_create_account(args)
    elif args.command == "list":
        cmd_list_accounts(args)
    elif args.command == "send":
        cmd_send(args)
    elif args.command == "process":
        cmd_process(args)
    elif args.command == "archive":
        if args.stats:
            from .archive import get_archive_stats
            import json
            print(json.dumps(get_archive_stats(), indent=2))
        elif args.search:
            from .archive import search_archive
            results = search_archive(args.search)
            for r in results:
                print(f"  [{r['id']}] {r['date']} | {r['from']} -> {r['to']} | {r['subject'][:80]}")
            print(f"\n  {len(results)} results")
        elif args.zoho_user and args.zoho_pass:
            from .archive import ZohoMailArchiver, build_search_index
            archiver = ZohoMailArchiver(args.zoho_user, args.zoho_pass)
            archiver.connect()
            total = archiver.archive_all()
            archiver.disconnect()
            build_search_index()
            print(f"Archived {total} emails from {args.zoho_user}")
        else:
            print("Use --stats, --search, or --zoho-user + --zoho-pass")
    else:
        cmd_serve(args)

if __name__ == "__main__":
    main()
