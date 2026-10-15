#!/bin/bash

# Run pytest inside the container against the agent's changes
python -m pytest /tests/test_outputs.py
rc=$?

# Harbor reads this reward file to calculate agent benchmarking scores
if [ "$rc" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi