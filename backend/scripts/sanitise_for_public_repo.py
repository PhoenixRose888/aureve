"""Sanitise the exported source for a PUBLIC repository.

Replaces the two real credential literals that appear across the source, tests,
reports and docs with environment-variable references (code) or placeholders
(docs/JSON). Only touches git-tracked files. Run from /app.
"""
import os
import re
import subprocess
import sys

PASSWORD = os.environ.get("SANITISE_PASSWORD", "")
TOKEN = os.environ.get("SANITISE_TOKEN", "")
if not PASSWORD or not TOKEN:
    sys.exit("Set SANITISE_PASSWORD and SANITISE_TOKEN to the literals to strip.")

PW_ENV = 'os.environ.get("REVIEWER_PASSWORD", "")'
TOKEN_ENV = 'os.environ.get("TEST_SESSION_TOKEN", "")'
PW_DOC = "<set via the REVIEWER_PASSWORD environment variable>"
TOKEN_DOC = "<set via the TEST_SESSION_TOKEN environment variable>"

tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
changed, skipped = [], []

for path in tracked:
    try:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        continue
    if PASSWORD not in src and TOKEN not in src:
        continue
    out = src

    if path.endswith(".py"):
        # Collapse "env with the real value as fallback" into env-only first.
        out = re.sub(r'os\.environ\.get\(\s*"REVIEWER_PASSWORD"\s*,\s*"%s"\s*\)' % PASSWORD, PW_ENV, out)
        out = re.sub(r'os\.environ\.get\(\s*"TEST_SESSION_TOKEN"\s*,\s*"%s"\s*\)' % TOKEN, TOKEN_ENV, out)
        # Quoted literals become env reads.
        for quote in ('"', "'"):
            out = out.replace(f"{quote}{PASSWORD}{quote}", PW_ENV)
            out = out.replace(f"{quote}{TOKEN}{quote}", TOKEN_ENV)
        # Any leftovers live in comments/docstrings.
        out = out.replace(PASSWORD, PW_DOC).replace(TOKEN, TOKEN_DOC)
        if PW_ENV in out or TOKEN_ENV in out:
            if not re.search(r"^import os$", out, re.M):
                lines = out.split("\n")
                last_import = max(
                    (i for i, l in enumerate(lines[:60]) if l.startswith(("import ", "from "))),
                    default=-1,
                )
                if last_import >= 0:
                    lines.insert(last_import + 1, "import os")
                else:  # module starts with a docstring only
                    insert_at = 0
                    if lines and lines[0].startswith(('"""', "'''")):
                        quote = lines[0][:3]
                        for i, l in enumerate(lines[1:], 1):
                            if quote in l:
                                insert_at = i + 1
                                break
                    lines.insert(insert_at, "import os")
                out = "\n".join(lines)
    else:
        out = out.replace(PASSWORD, PW_DOC).replace(TOKEN, TOKEN_DOC)

    if out != src:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(out)
        changed.append(path)
    else:
        skipped.append(path)

print(f"sanitised {len(changed)} files")
for p in changed:
    print("  ", p)
if skipped:
    print("UNCHANGED BUT MATCHED (inspect):", skipped)
    sys.exit(1)
