import java.io.*;
import java.util.*;
import java.util.concurrent.*;

/**
 * Concurrent event aggregator that counts events by type from multiple threads
 * and writes a summary report. Contains subtle concurrency bugs.
 */
public class EventAggregator {

    private volatile Map<String, Integer> eventCounts;
    private final String outputPath;
    private final ExecutorService executor;

    public EventAggregator(String outputPath) {
        this.outputPath = outputPath;
        this.executor = Executors.newFixedThreadPool(6);
    }

    private Map<String, Integer> getCounts() {
        if (eventCounts == null) {
            synchronized (this) {
                if (eventCounts == null) {
                    eventCounts = new HashMap<>();
                }
            }
        }
        return eventCounts;
    }

    public void recordEvent(String eventType) {
        executor.submit(() -> {
            Map<String, Integer> counts = getCounts();
            Integer current = counts.get(eventType);
            if (current == null) {
                counts.put(eventType, 1);
            } else {
                counts.put(eventType, current + 1);
            }
        });
    }

    public void shutdown() throws Exception {
        executor.shutdown();
        executor.awaitTermination(10, TimeUnit.SECONDS);
        writeReport();
    }

    private void writeReport() throws IOException {
        BufferedWriter writer = new BufferedWriter(
            new OutputStreamWriter(new FileOutputStream(outputPath), "UTF-8"));
        Map<String, Integer> counts = getCounts();
        for (Map.Entry<String, Integer> entry : counts.entrySet()) {
            writer.write(entry.getKey() + "=" + entry.getValue());
            writer.newLine();
        }
        writer.flush();
        writer.close();
    }

    public static void main(String[] args) throws Exception {
        String outputPath = args.length > 0 ? args[0] : "/app/output/counts.txt";
        EventAggregator aggregator = new EventAggregator(outputPath);

        String[] eventTypes = {"INFO", "WARN", "ERROR", "DEBUG", "TRACE"};

        for (int i = 0; i < 50000; i++) {
            aggregator.recordEvent(eventTypes[i % eventTypes.length]);
        }

        aggregator.shutdown();
        System.out.println("Event processing complete.");
    }
}
