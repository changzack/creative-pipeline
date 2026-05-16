#!/usr/bin/env python3
"""
Sync local prompt files to Langfuse Prompt Management.

Reads pipeline/prompts/*.txt and pushes each as a new version of the same
prompt name in Langfuse, with label 'production'. Safe to re-run — Langfuse
creates a new version each time, with the old versions preserved.

Usage:
    cd ~/.openclaw/workspace/pipeline
    source .venv/bin/activate
    python scripts/sync-prompts.py [--dry-run] [--label production]

Environment:
    LANGFUSE_HOST           (default: http://localhost:3000)
    LANGFUSE_PUBLIC_KEY     (no default — must be set)
    LANGFUSE_SECRET_KEY     (default: sk-lf-…2026)
"""
import argparse
import os
import sys
from pathlib import Path

# Add parent dir to path so we can import langfuse_tracing's defaults
THIS_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = THIS_DIR.parent
PROMPTS_DIR = PIPELINE_DIR / "prompts"
sys.path.insert(0, str(PIPELINE_DIR))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="production", help="Langfuse label to attach (default: production)")
    ap.add_argument("--dry-run", action="store_true", help="Print what would be pushed, don't push")
    ap.add_argument("--only", default=None, help="Only sync this prompt name")
    args = ap.parse_args()

    try:
        from langfuse import Langfuse
    except ImportError:
        print("❌ langfuse SDK not installed in this env")
        return 1

    host = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "")

    print(f"→ Langfuse host: {host}")
    print(f"→ Label: {args.label}")
    print(f"→ Prompts dir: {PROMPTS_DIR}")
    print()

    if not PROMPTS_DIR.exists():
        print(f"❌ Prompts dir not found: {PROMPTS_DIR}")
        return 1

    client = Langfuse(public_key=pk, secret_key=sk, host=host)

    files = sorted(PROMPTS_DIR.glob("*.txt"))
    if not files:
        print("⚠️  No .txt prompt files found")
        return 0

    pushed = 0
    skipped = 0
    failed = 0
    for f in files:
        name = f.stem
        if args.only and name != args.only:
            continue

        content = f.read_text()
        size_kb = len(content) / 1024
        # Detect template variables (Langfuse uses {{var}} syntax)
        var_count = content.count("{{")

        print(f"📜 {name}  ({size_kb:.2f}KB, {var_count} template vars)")

        if args.dry_run:
            print(f"   [dry-run] would push to Langfuse with label '{args.label}'")
            skipped += 1
            continue

        try:
            client.create_prompt(
                name=name,
                prompt=content,
                labels=[args.label],
                config={
                    "source": "pipeline/prompts/" + f.name,
                    "synced_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
                },
            )
            print(f"   ✅ pushed (label={args.label})")
            pushed += 1
        except Exception as e:
            print(f"   ❌ failed: {e}")
            failed += 1

    client.flush()
    print()
    print(f"Done — pushed {pushed}, skipped {skipped}, failed {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
