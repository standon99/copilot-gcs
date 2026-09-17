"""Reject environment files and this workspace's credential without printing it."""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args()
    key = None
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("OLLAMA_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if len(value) > 16:
                    key = value.encode()
    violations = []
    if args.all:
        candidates = []
        for line in git("rev-list", "--objects", "--all").decode().splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                oid, path = parts
                if git("cat-file", "-t", oid).strip() == b"blob":
                    candidates.append((path, oid))
    else:
        candidates = [
            (name, ":" + name)
            for name in git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
            .decode()
            .split("\0")
            if name
        ]
    for path, ref in candidates:
        base = Path(path).name
        if (base == ".env" or base.startswith(".env.")) and base != ".env.example":
            violations.append(path + " (environment file)")
            continue
        content = git("show", ref)
        if key and key in content:
            violations.append(path + " (local credential detected)")
    if violations:
        print(
            "Secret check rejected Git operation. Remove sensitive content from these paths:",
            file=sys.stderr,
        )
        for path in sorted(set(violations)):
            print(" - " + path, file=sys.stderr)
        return 1
    print("Secret check passed: local credential and private environment files are absent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
