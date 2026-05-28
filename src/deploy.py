import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def deploy_site_via_sftp():
    if sys.platform == "win32":
        print("SFTP deploy not supported on Windows")
        return
    build_dir = ROOT / "nullstate-website" / "build"
    if not build_dir.exists():
        print(f"Build directory not found: {build_dir}")
        return
    remote = os.environ.get("NULLSTATE_FTP_REMOTE_DIR", "/nullstate")
    host = os.environ.get("NULLSTATE_FTP_HOST", "server26.shared.spaceship.host")
    user = os.environ.get("NULLSTATE_FTP_USER", "admin@greensol.me")
    pw = os.environ.get("NULLSTATE_FTP_PASSWORD")
    if not pw:
        print("FTP_PASSWORD not set, skipping deploy")
        return
    import ftplib
    ftp = ftplib.FTP(host, user, pw, timeout=60)
    ftp.encoding = "utf-8"
    parts = [p for p in remote.split("/") if p]
    for p in parts:
        try:
            ftp.cwd(p)
        except Exception:
            ftp.mkd(p)
            ftp.cwd(p)
    total = 0
    for root, dirs, files in os.walk(str(build_dir)):
        rel = os.path.relpath(root, str(build_dir))
        target = remote + ("/" + rel.replace(os.sep, "/") if rel != "." else "")
        try:
            ftp.cwd(target)
        except Exception:
            for part in target.split("/"):
                try:
                    ftp.cwd(part)
                except Exception:
                    ftp.mkd(part)
                    ftp.cwd(part)
        for f in files:
            with open(os.path.join(root, f), "rb") as fh:
                ftp.storbinary(f"STOR {f}", fh)
                total += 1
    ftp.quit()
    print(f"Deployed {total} files to {remote}")
