"""NullState CLI — unified entry point for all NullState operations."""

import sys
import os
import argparse

def main():
    parser = argparse.ArgumentParser(description="NullState — Agent Payment Infrastructure")
    parser.add_argument("--version", action="version", version="NullState 0.2.0")

    sub = parser.add_subparsers(dest="command")

    # Status
    _p_status = sub.add_parser("status", help="Check gateway health")

    # Serve model API
    p_serve = sub.add_parser("serve", help="Start model inference API")
    p_serve.add_argument("--port", type=int, default=8082)
    p_serve.add_argument("--host", default="0.0.0.0")

    # Train / generate synthetic data
    p_synth = sub.add_parser("synth", help="Generate synthetic training data")
    p_synth.add_argument("--count", type=int, default=500)
    p_synth.add_argument("--domain", default="all")
    p_synth.add_argument("--workers", type=int, default=8)

    # Email server
    p_email = sub.add_parser("email", help="Start NullState email server")
    p_email.add_argument("--smtp-port", type=int, default=2525)
    p_email.add_argument("--api-port", type=int, default=8083)

    p_email_create = sub.add_parser("email-create", help="Create mail account")
    p_email_create.add_argument("email")
    p_email_create.add_argument("--name", default="")
    p_email_create.add_argument("--forward", default="")
    p_email_create.add_argument("--catch-all", action="store_true")

    _p_email_list = sub.add_parser("email-list", help="List mail accounts")

    p_email_send = sub.add_parser("email-send", help="Send an email")
    p_email_send.add_argument("--to", required=True)
    p_email_send.add_argument("--subject", default="NullState Notification")
    p_email_send.add_argument("--body", default="")

    p_email_archive = sub.add_parser("email-archive", help="Email archive tasks")
    p_email_archive.add_argument("--stats", action="store_true", help="Show archive stats")
    p_email_archive.add_argument("--search", help="Search archived emails")

    # Dataset
    sub.add_parser("dataset", help="Build training dataset from production data")

    # KYA
    sub.add_parser("kya", help="Get KYA authentication token")

    args = parser.parse_args()

    if args.command == "serve":
        from nullstate.api.model_api import main as serve_main
        os.environ["MODEL_API_PORT"] = str(args.port)
        os.environ["MODEL_API_HOST"] = args.host
        serve_main()
    elif args.command == "synth":
        from nullstate.training.synthesize_dataset import main as synth_main
        sys.argv = ["nullstate-synth", "--count", str(args.count), "--domain", args.domain, "--workers", str(args.workers)]
        synth_main()
    elif args.command == "email":
        from nullstate.mail.server import main as email_main
        sys.argv = ["nullstate-email", "serve",
                     "--smtp-port", str(args.smtp_port),
                     "--api-port", str(args.api_port)]
        email_main()
    elif args.command == "email-create":
        from nullstate.mail.server import cmd_create_account
        cmd_create_account(args)
    elif args.command == "email-list":
        from nullstate.mail.server import cmd_list_accounts
        cmd_list_accounts(args)
    elif args.command == "email-send":
        from nullstate.mail.server import cmd_send
        cmd_send(args)
    elif args.command == "email-archive":
        if args.stats:
            from nullstate.mail.archive import get_archive_stats
            import json
            print(json.dumps(get_archive_stats(), indent=2))
        elif args.search:
            from nullstate.mail.archive import search_archive
            results = search_archive(args.search)
            for r in results:
                print(f"  [{r['id']}] {r['date']} | {r['from']} -> {r['to']} | {r['subject'][:80]}")
            print(f"\n  {len(results)} results")
        else:
            print("Use --stats or --search <query>")
    elif args.command == "dataset":
        from nullstate.training.expand_dataset import build as dataset_build
        dataset_build()
    elif args.command == "kya":
        import requests
        r = requests.get("https://localhost:8080/kya/challenge", verify=False)
        print(r.json())
    elif args.command == "status":
        import requests
        try:
            r = requests.get("https://localhost:8080/health", verify=False, timeout=5)
            print(f"Gateway: {r.json()}")
        except Exception as e:
            print(f"Gateway not reachable: {e}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
