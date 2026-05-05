# Evaluation Dataset Layout

Use simple names plus version numbers:

- `main/ui_main_v2.json`: main day-to-day benchmark
- `diagnostics/ui_refusal_v1.json`: refusal and out-of-scope diagnostic split
- `seeds/ui_seed_v1.json`: lighter seed benchmark for smoke checks
- `archive/snapshot_chunk_seed_v0.json`: older synthetic snapshot-chunk seed kept only for reference

Naming rule:

- `ui_main_vN`: main benchmark promoted for regular comparisons
- `ui_refusal_vN`: refusal-focused diagnostic benchmark
- `ui_seed_vN`: lighter seed benchmark
- `snapshot_chunk_seed_vN`: archive material from earlier synthetic generation passes
