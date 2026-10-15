#!/bin/bash
# Oracle solve script. Drops the reference stratdl.pl into /app/src/ and runs the
# wrapper once on a bundled example so the verifier can confirm the wrapper
# produces a fresh output file.
set -euo pipefail

cp /oracle/oracle.pl /app/src/stratdl.pl 2>/dev/null \
    || cp "$(dirname "$0")/oracle.pl" /app/src/stratdl.pl

chmod +x /app/stratdl

/app/stratdl /app/examples/reach.dl /app/out.txt || true
echo "[solve] /app/out.txt:"
cat /app/out.txt
