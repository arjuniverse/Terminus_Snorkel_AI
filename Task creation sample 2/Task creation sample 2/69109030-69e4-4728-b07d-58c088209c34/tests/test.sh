#!/bin/bash
# Verifier entry point for stratdl-gp.
set -uo pipefail

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

# Always leave a parseable CTRF stub so every exit path produces one; pytest
# overwrites this when it runs.
python3 - <<'PY'
import json, os
os.makedirs("/logs/verifier", exist_ok=True)
with open("/logs/verifier/ctrf.json", "w") as f:
    json.dump({"results": {"tool": {"name": "pytest"},
        "summary": {"tests": 0, "passed": 0, "failed": 0,
                    "pending": 0, "skipped": 0, "other": 0,
                    "start": 0, "stop": 0},
        "tests": []}}, f)
PY

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script." >&2
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

TEST_DIR="${TEST_DIR:-/tests}"

python3 -m pytest --ctrf /logs/verifier/ctrf.json "$TEST_DIR/test_outputs.py" -rA

if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
