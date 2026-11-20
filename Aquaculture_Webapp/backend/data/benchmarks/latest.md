# Benchmark run 2026-11-20 13:23:28 +0530

Simulator, boat speed x16, re-plan rule: onboard. Gemini model: gemini-3.5-flash-lite. Not field results.

| Metric | Measured | Target |
|---|---|---|
| End-to-end latency (p95, worst scenario) | 13.4 ms | under 10 s |
| Anomaly detection precision | 1.0 | 0.85 or higher |
| Anomaly detection recall | 0.672 | 0.85 or higher |
| Source localisation (median / worst) | 6.0 / 9.5 m | under 25 m |
| Visual inspector label accuracy | 0.975 | 0.80 or higher |
| Readings per hour (at demo speed) | 3366 | 10x manual |

| Scenario | Traced | Source error (m) | Latency p50 / p95 (ms) | Precision | Recall |
|---|---|---|---|---|---|
| sewage | yes | 4.2 | 6.6 / 12.8 | 1.0 | 0.62 |
| farm_runoff | yes | 9.5 | 5.5 / 13.4 | 1.0 | 0.804 |
| industrial | yes | 6.5 | 5.7 / 10.9 | 1.0 | 0.562 |
| algal_bloom | yes | 5.6 | 4.9 / 7.3 | 1.0 | 0.821 |
