#!/bin/bash
# Verifier entry script for task-java-race-condition
set -uo pipefail

mkdir -p /logs/verifier
echo "0.0" > /logs/verifier/reward.txt

cd /app
python3 -m pytest /tests/test_outputs.py -v --tb=short > /logs/verifier/pytest_output.log 2>&1

if [ $? -eq 0 ]; then
    echo "1.0" > /logs/verifier/reward.txt
else
    echo "0.0" > /logs/verifier/reward.txt
fi
