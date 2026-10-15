import os
import subprocess
import pytest
import glob

OUTPUT_PATH = "/app/output/counts.txt"
CLASSES_DIR = "/app/classes"
SRC_DIR = "/app/src"
MAIN_CLASS = "EventAggregator"

@pytest.fixture(scope="module", autouse=True)
def compile_and_clean():
    """Compile Java source and clean output before tests."""
    os.makedirs("/app/output", exist_ok=True)
    if os.path.exists(OUTPUT_PATH):
        os.remove(OUTPUT_PATH)

    proc = subprocess.run(
        ["javac", "-d", CLASSES_DIR, os.path.join(SRC_DIR, "EventAggregator.java")],
        capture_output=True,
        text=True
    )
    assert proc.returncode == 0, f"Compilation failed: {proc.stderr}"
    yield
    if os.path.exists(OUTPUT_PATH):
        os.remove(OUTPUT_PATH)


def parse_counts(path):
    """Parse output file into a dict of type -> count."""
    if not os.path.exists(path):
        return {}
    counts = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("=")
            if len(parts) == 2:
                counts[parts[0].strip()] = int(parts[1].strip())
    return counts


def test_single_threaded_correctness():
    """Verify the aggregator works correctly with a small deterministic input."""
    small_out = "/app/output/small_counts.txt"
    if os.path.exists(small_out):
        os.remove(small_out)

    proc = subprocess.run(
        ["java", "-cp", CLASSES_DIR, MAIN_CLASS, small_out],
        capture_output=True,
        text=True,
        timeout=30.0
    )
    assert proc.returncode == 0, f"Process failed: {proc.stderr}"
    assert os.path.exists(small_out), "Output file was not created."

    counts = parse_counts(small_out)
    total = sum(counts.values())
    assert total == 50000, f"Expected 50000 total events, got {total}. Counts: {counts}"
    for t in ["INFO", "WARN", "ERROR", "DEBUG", "TRACE"]:
        assert t in counts, f"Missing event type: {t}"


def test_multi_run_consistency():
    """Verify that running the aggregator multiple times produces consistent results."""
    results = []
    for i in range(5):
        out = f"/app/output/run_{i}.txt"
        subprocess.run(
            ["java", "-cp", CLASSES_DIR, MAIN_CLASS, out],
            capture_output=True,
            text=True,
            timeout=30.0
        )
        counts = parse_counts(out)
        results.append(counts)

    first = results[0]
    for i, r in enumerate(results[1:], 1):
        assert r == first, f"Run {i} produced different counts: expected {first}, got {r}"


def test_no_exceptions():
    """Verify the application runs without throwing any exceptions or errors."""
    proc = subprocess.run(
        ["java", "-cp", CLASSES_DIR, MAIN_CLASS, "/app/output/noerr.txt"],
        capture_output=True,
        text=True,
        timeout=30.0
    )
    assert proc.returncode == 0, f"Non-zero exit code: {proc.returncode}"
    assert "Exception" not in proc.stderr, f"Exception in stderr: {proc.stderr}"
    assert "Exception" not in proc.stdout, f"Exception in stdout: {proc.stdout}"
    assert "Error" not in proc.stderr, f"Error in stderr: {proc.stderr}"


def test_output_format():
    """Verify the output file has correct format TYPE=COUNT per line."""
    proc = subprocess.run(
        ["java", "-cp", CLASSES_DIR, MAIN_CLASS, "/app/output/fmt_test.txt"],
        capture_output=True,
        text=True,
        timeout=30.0
    )
    assert proc.returncode == 0

    with open("/app/output/fmt_test.txt") as f:
        lines = [l.strip() for l in f if l.strip()]

    assert len(lines) == 5, f"Expected 5 event type lines, got {len(lines)}"
    for line in lines:
        parts = line.split("=")
        assert len(parts) == 2, f"Invalid format: {line}"
        assert parts[0] in ["INFO", "WARN", "ERROR", "DEBUG", "TRACE"], f"Unknown type: {parts[0]}"
        assert parts[1].isdigit(), f"Count is not a number: {parts[1]}"
        assert int(parts[1]) > 0, f"Count must be positive: {parts[1]}"


def test_specific_known_values():
    """Verify all 50,000 events are accounted for exactly (10,000 of each type)."""
    proc = subprocess.run(
        ["java", "-cp", CLASSES_DIR, MAIN_CLASS, "/app/output/known.txt"],
        capture_output=True,
        text=True,
        timeout=30.0
    )
    assert proc.returncode == 0
    counts = parse_counts("/app/output/known.txt")
    total = sum(counts.values())
    assert total == 50000, f"Expected 50000 total, got {total}"

    # With a round-robin pattern (i % 5), exactly 10,000 of each type
    for event_type in ["INFO", "WARN", "ERROR", "DEBUG", "TRACE"]:
        actual = counts.get(event_type, 0)
        assert actual == 10000, (
            f"Wrong count for {event_type}: expected 10000, got {actual}"
        )
