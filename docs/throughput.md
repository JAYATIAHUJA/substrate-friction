# Measured ingest throughput

`UNWIND $rows` batches over the client transport, against local object storage.

| Batch size | Seconds | Edges/sec |
|---|---|---|
| 250 | 0.634 | 15783.7 |
| 500 | 0.449 | 22249.5 |
| 1000 | 1.03 | 9712.1 |

**Best: 22249.5 edges/sec at batch size 500.**

Roughly 65,000 edges per repository; three repositories is under 200,000 edges. At the measured rate this loads in minutes, which is the point of choosing a project whose graph is small: the engine's write path is serialized and adding writers does not help.
