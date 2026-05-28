"""NullState Security Sandbox — Proprietary Information Control System.
Ensures clear separation between public/open-source and proprietary internal assets.
Control points, triggers, and gates for what goes where.

Equity system: proprietary knowledge stays in the walled garden and grows the business value.
"""

import os
import json
import fnmatch
import logging
import pathlib
from datetime import datetime
from typing import List, Set, Dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SANDBOX] %(message)s")
log = logging.getLogger("nullstate-sandbox")

PROJECT_ROOT = "/home/Nullstate-linux-vm"

# ─── Classification Rules ──────────────────────────────────────────

# PUBLIC = safe for open-source, GitHub, HF
# INTERNAL = proprietary, never commit, never share
# RESTRICTED = credentials, keys, access-controlled

CLASSIFIED_PATHS = {
    # ── PUBLIC (open-source safe) ──
    "public": {
        "globs": [
            "src/nullstate/network/*.py",
            "src/nullstate/api/*.py",
            "src/nullstate/mail/*.py",
            "src/nullstate/cli.py",
            "src/nullstate/__init__.py",
            "pyproject.toml",
            "README.md",
            "LICENSE",
            "nullstate-website/src/**/*",
            "nullstate-website/docs/**/*",
            "nullstate-website/static/**/*",
            "nullstate-website/docusaurus.config.ts",
            "nullstate-website/sidebars.ts",
            "examples/**/*",
            "docs/**/*.md",
        ],
        "gitignore_rules": [
            "# NullState Public Repository - Safe for open-source",
        ]
    },
    
    # ── INTERNAL (proprietary, never in public repos) ──
    "internal": {
        "globs": [
            "src/nullstate/hod/**/*.py",
            "src/nullstate/training/**/*.py",
            "src/training/**/*",
            "src/worker/**/*.py",
            "src/core/**/*.py",
            "src/wallet/**/*",
            "src/agents/**/*.py",
            "src/nullstate/database.py",
            "credentials/**/*",
            "backups/**/*",
            "logs/**/*",
            "deployments/**/*",
        ],
        "gitignore_rules": [
            "# ---- NullState Proprietary - DO NOT COMMIT TO PUBLIC ----",
            "# HOD autonomous engine - core business logic",
            "src/nullstate/hod/",
            "# Training pipeline - proprietary dataset generation",
            "src/nullstate/training/",
            "src/training/synthetic/",
            "src/training/nullstate_training_*.jsonl",
            "# Worker systems - internal automation",
            "src/worker/",
            "# Core infrastructure - database, store",
            "src/core/",
            "src/core/*.db*",
            "src/core/*.db",
            "*.db",
            "*.db-shm",
            "*.db-wal",
            "# Wallet and credentials - NEVER COMMIT",
            "src/wallet/",
            "credentials/",
            "**/.env",
            "**/.env.*",
            "# Backups, logs, internal artifacts",
            "backups/",
            "logs/",
            "deployments/",
            "usage.json",
        ]
    },
    
    # ── RESTRICTED (keys, secrets — chmod 600, air-gapped) ──
    "restricted": {
        "globs": [
            "credentials/**/*",
            "src/wallet/.env",
            "**/.env",
            "**/*.pem",
            "**/*.key",
            "**/service_account*.json",
        ],
        "permissions": "600",
        "gitignore_rules": [
            "# ---- NULLSTATE RESTRICTED - NEVER COMMIT OR SHARE ----",
            "credentials/",
            "src/wallet/.env",
            ".env",
            "*.pem",
            "*.key",
        ]
    }
}

# Sensitive patterns that trigger alerts in code
SENSITIVE_PATTERNS = [
    "NULLSTATE_WALLET_PRIVATE_KEY",
    "NULLSTATE_SOLANA_PRIVATE_KEY",
    "NULLSTATE_HF_TOKEN",
    "NULLSTATE_GOOGLE_API_KEY",
    "AIzaSy",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN EC PRIVATE KEY",
    "ghp_",
    "gho_",
    "github_pat_",
    "hf_",
]


def _matches_glob(relpath: str, pattern: str) -> bool:
    """Match file path against glob pattern, supporting ** for recursive matching."""
    if "**" in pattern:
        # Handle ** by splitting and matching each part
        parts = pattern.split("/**/")
        if len(parts) == 2:
            prefix, suffix = parts
            # Walk the file's path components
            path_parts = relpath.split("/")
            for i in range(len(path_parts)):
                candidate = "/".join([prefix] + path_parts[i:] if prefix else path_parts[i:])
                if fnmatch.fnmatch(candidate, suffix):
                    return True
                if not prefix:
                    break
            return False
    return fnmatch.fnmatch(relpath, pattern) or fnmatch.fnmatch(os.path.basename(relpath), pattern)


def classify_file(filepath: str) -> str:
    """Classify a file as public, internal, or restricted."""
    relpath = os.path.relpath(filepath, PROJECT_ROOT)
    
    # Check restricted first (highest priority)
    for pattern in CLASSIFIED_PATHS["restricted"]["globs"]:
        if _matches_glob(relpath, pattern):
            return "restricted"
    
    # Check internal
    for pattern in CLASSIFIED_PATHS["internal"]["globs"]:
        if _matches_glob(relpath, pattern):
            return "internal"
    
    # Check public
    for pattern in CLASSIFIED_PATHS["public"]["globs"]:
        if _matches_glob(relpath, pattern):
            return "public"
    
    # Default: internal (conservative - new files are proprietary by default)
    return "internal"


def scan_for_sensitive_leaks() -> List[Dict]:
    """Scan the codebase for sensitive patterns that shouldn't be in public files."""
    leaks = []
    
    # Only scan files classified as public (where leaks would matter)
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Skip hidden dirs, node_modules, etc.
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '.local', '.cache', '.npm', '.vscode-server', '.ollama', '.git', '.opencode']]
        
        for fname in files:
            fpath = os.path.join(root, fname)
            if classify_file(fpath) != "public":
                continue
            
            # Check file for sensitive patterns
            relpath = os.path.relpath(fpath, PROJECT_ROOT)
            try:
                with open(fpath, 'rb') as f:
                    content = f.read()
                
                for pattern in SENSITIVE_PATTERNS:
                    if pattern.encode() in content:
                        leaks.append({
                            "file": relpath,
                            "pattern": pattern,
                            "severity": "CRITICAL" if "PRIVATE" in pattern or "SECRET" in pattern else "HIGH",
                            "action": "Remove immediately - this will be in public repo"
                        })
            except (IOError, OSError):
                pass
    
    return leaks


def generate_gitignore() -> str:
    """Generate comprehensive .gitignore with proper classifications."""
    lines = [
        "# NullState .gitignore",
        "# Auto-generated by Security Sandbox",
        f"# Generated: {datetime.now().isoformat()}",
        "",
        "# ---- INTERNAL: Proprietary - DO NOT COMMIT TO PUBLIC ----",
    ]
    
    for rule in CLASSIFIED_PATHS["internal"]["gitignore_rules"]:
        if rule.startswith("#"):
            lines.append(rule)
        else:
            lines.append(rule)
    
    lines.extend([
        "",
        "# ---- RESTRICTED: Secrets - NEVER COMMIT ----",
    ])
    
    for rule in CLASSIFIED_PATHS["restricted"]["gitignore_rules"]:
        if rule.startswith("#"):
            lines.append(rule)
        else:
            lines.append(rule)
    
    lines.extend([
        "",
        "# ---- Standard ignores ----",
        "__pycache__/",
        "*.pyc",
        "*.pyo",
        "*.egg-info/",
        ".DS_Store",
        "Thumbs.db",
        "",
        "# ---- Build outputs ----",
        "nullstate-website/build/",
        ".docusaurus/",
        ".cache/",
    ])
    
    return "\n".join(lines)


def enforce_permissions():
    """Ensure restricted files have correct permissions (chmod 600)."""
    restricted_globs = CLASSIFIED_PATHS["restricted"]["globs"]
    
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '.local', '.npm', '.ollama']]
        
        for fname in files:
            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, PROJECT_ROOT)
            
            for pattern in restricted_globs:
                if _matches_glob(relpath, pattern):
                    try:
                        os.chmod(fpath, 0o600)
                        log.info(f"Secured: {relpath} (chmod 600)")
                    except Exception as e:
                        log.warning(f"Could not secure {relpath}: {e}")
                    break


def validate_public_repo() -> Dict:
    """Validate that public-facing paths contain no proprietary content."""
    results = {
        "pass": True,
        "checks": [],
        "leaks": [],
        "warnings": []
    }
    
    # Check git tracking — ensure internal paths are gitignored
    try:
        import subprocess
        gitignored = subprocess.run(
            ["git", "check-ignore"] + CLASSIFIED_PATHS["internal"]["globs"] + CLASSIFIED_PATHS["restricted"]["globs"],
            capture_output=True, text=True, timeout=10
        )
        # Files that would be tracked but shouldn't be
        results["checks"].append({
            "check": "Git ignore internal paths",
            "status": "PASS" if gitignored.returncode == 0 else "WARN"
        })
    except Exception as e:
        results["warnings"].append(f"Git check failed: {e}")
    
    # Scan for sensitive leaks in public files
    leaks = scan_for_sensitive_leaks()
    results["leaks"] = leaks
    if leaks:
        results["pass"] = False
        for leak in leaks:
            results["checks"].append({
                "check": f"Sensitive leak in {leak['file']}",
                "status": "FAIL",
                "severity": leak["severity"],
                "action": leak["action"]
            })
    
    # Check restricted file permissions
    permission_issues = []
    restricted_globs = CLASSIFIED_PATHS["restricted"]["globs"]
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules']]
        for fname in files:
            fpath = os.path.join(root, fname)
            for pattern in restricted_globs:
                relpath = os.path.relpath(fpath, PROJECT_ROOT)
                if _matches_glob(relpath, pattern):
                    try:
                        perms = oct(os.stat(fpath).st_mode)[-3:]
                        if perms != "600":
                            permission_issues.append(f"{relpath} (mode: {perms})")
                    except:
                        pass
    
    if permission_issues:
        results["warnings"].append(f"Permission issues: {permission_issues}")
        results["checks"].append({
            "check": "Restricted file permissions",
            "status": "WARN",
            "details": permission_issues
        })
    
    return results


def main():
    """Run security sandbox validation."""
    import argparse
    parser = argparse.ArgumentParser(description="NullState Security Sandbox")
    parser.add_argument("--fix-permissions", action="store_true", help="Fix file permissions")
    parser.add_argument("--generate-gitignore", action="store_true", help="Generate .gitignore")
    parser.add_argument("--scan-leaks", action="store_true", help="Scan for sensitive leaks")
    parser.add_argument("--validate", action="store_true", help="Full validation")
    args = parser.parse_args()
    
    if args.fix_permissions:
        print("Enforcing restricted file permissions...")
        enforce_permissions()
        print("Done")
    
    if args.generate_gitignore:
        gitignore = generate_gitignore()
        with open(os.path.join(PROJECT_ROOT, ".gitignore"), "w") as f:
            f.write(gitignore)
        print(f"Generated .gitignore ({len(gitignore)} chars)")
    
    if args.scan_leaks:
        print("Scanning for sensitive leaks in public files...")
        leaks = scan_for_sensitive_leaks()
        if leaks:
            print(f"FOUND {len(leaks)} LEAKS:")
            for l in leaks:
                print(f"  [{l['severity']}] {l['file']}: {l['pattern']}")
                print(f"    Action: {l['action']}")
        else:
            print("No leaks found - clear")
    
    if args.validate:
        results = validate_public_repo()
        print(f"\nSecurity Validation: {'PASS' if results['pass'] else 'FAIL'}")
        for check in results["checks"]:
            status_sym = "✓" if check["status"] == "PASS" else "⚠" if check["status"] == "WARN" else "✗"
            print(f"  {status_sym} {check['check']}: {check['status']}")
        if results["leaks"]:
            print(f"\n  CRITICAL: {len(results['leaks'])} sensitive leaks detected!")
        if results["warnings"]:
            for w in results["warnings"]:
                print(f"  ⚠ {w}")


if __name__ == "__main__":
    main()
