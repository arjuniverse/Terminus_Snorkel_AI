import java.io.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class EventAggregator {

    private final ConcurrentHashMap<String, AtomicInteger> eventCounts;
    private final String outputPath;
    private final ExecutorService executor;

    public EventAggregator(String outputPath) {
        this.outputPath = outputPath;
        this.eventCounts = new ConcurrentHashMap<>();
        this.executor = Executors.newFixedThreadPool(6);
    }

    public void recordEvent(String eventType) {
        executor.submit(() -> {
            eventCounts.computeIfAbsent(eventType, k -> new AtomicInteger(0))
                       .incrementAndGet();
        });
    }

    public void shutdown() throws Exception {
        executor.shutdown();
        boolean finished = executor.awaitTermination(15, TimeUnit.SECONDS);
        if (!finished) {
            executor.shutdownNow();
        }
        writeReport();
    }

    private void writeReport() throws IOException {
        BufferedWriter writer = new BufferedWriter(
            new OutputStreamWriter(new FileOutputStream(outputPath), "UTF-8"));
        List<String> keys = new ArrayList<>(eventCounts.keySet());
        Collections.sort(keys);
        for (String key : keys) {
            writer.write(key + "=" + eventCounts.get(key).get());
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
