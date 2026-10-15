# Fix Race Condition in Thread-Safe Event Counter

The event aggregator at `/app/src/EventAggregator.java` processes 50,000 events from multiple concurrent threads and writes a summary report to `/app/output/counts.txt`. Under concurrent load, the aggregator produces incorrect results.

### Problems to Fix:
1. **Incorrect event counts**: When multiple threads record events simultaneously, some event counts are lost or incorrect. The final report does not match the expected totals.
2. **Thread-safety violation**: The shared map used for counting events is not properly protected against concurrent modifications, which can cause data corruption or exceptions under load.

### Constraints:
- The application must compile with `javac -d /app/classes src/EventAggregator.java` and run via `java -cp /app/classes EventAggregator <output_path>`.
- The output file must contain one line per event type in the format `TYPE=COUNT` (e.g., `INFO=12034`).
- All 50,000 events must be accounted for in the final report (sum of all counts must equal 50,000).
- The application must complete without throwing any exceptions.

### Deliverables:
- Fix the concurrency bugs in `/app/src/EventAggregator.java`.
- Ensure the output file `/app/output/counts.txt` is correct under concurrent execution.
- The entry point signature must remain unchanged.
