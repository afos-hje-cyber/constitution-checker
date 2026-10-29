# Comparison: baseline_v1_dev24 (k=8) vs baseline_v1_dev24_k10 (k=10)

- `baseline_v1_dev24`: git `7b073fa`, 2026-10-27T16:20:35+00:00, hybrid k=8, prompt `assess_v1`, `gemini-3.5-flash-lite` (3.5-flash-lite-07-2026), API calls 11
- `baseline_v1_dev24_k10`: git `74e847a`, 2026-10-27T17:48:05+00:00, hybrid k=10, prompt `assess_v1`, `gemini-3.5-flash-lite` (3.5-flash-lite-07-2026), API calls 28
- Sets compared: dev · 24 cases

## Metrics

| Metric | k=8 | k=10 | Δ |
|---|---|---|---|
| Label accuracy (dev) | 88% | 92% | +4 pp |
| Label + reason accuracy (dev) | 83% | 92% | +8 pp |
| Citation accuracy (conflict cases) (dev) | 83% | 89% | +6 pp |
| Citation accuracy (all with expected art.) (dev) | 83% | 92% | +8 pp |
| Unclear rate (dev) | 12% | 8% | -4 pp |
| Retrieval hit @k (dev) | 83% @8 | 92% @10 | |
| Rejected citations + references (dev) | 0 | 0 | |
| compatible↔conflict confusions | none | none | |
| Avg input tokens / call | 2145 | 2542 | +19% |
| Avg output tokens / call | 276 | 289 | +5% |
| Avg total tokens / call | 2421 | 2832 | +17% |

## Improvements (label + reason wrong at k=8, right at k=10)

- **20** Baixar a idade mínima de voto para os 16 anos — expected [49], rank 9: unclear [122, 113/1] → conflict [49/1]
- **42** Criar uma rede de creches públicas — expected [67], rank 10: compatible [74/2/b, 75/1] → compatible [67/2/b, 74/2/b]

## Regressions (label + reason right at k=8, wrong at k=10)

None.

## Other changes (same label + reason verdict; label or citations differ)

| id | label k=8 | label k=10 | cited k=8 | cited k=10 |
|---|---|---|---|---|
| 1 | conflict | conflict | 24/2, 24/1 | 24, 24/1, 24/2 |
| 4 | conflict | conflict | 41/4, 43/3 | 41/4, 288/c, 41/1 |
| 5 | unclear | unclear | 168/6/a | – |
| 8 | conflict | conflict | 64/2/a, 64/3/a | 64/2/a, 64/3/a, 64/3/b, 64/4, 165/1/f |
| 11 | conflict | conflict | 33/1 | 33/1, 33/3 |
| 12 | compatible | compatible | 81/m, 81/a | 81/m, 66/2/d |
| 36 | conflict | conflict | 34/3 | 34/3, 272/3 |
| 38 | conflict | conflict | 53 | 53, 59/1 |
| 39 | conflict | conflict | 62/1, 62/2, 94/1 | 62/2, 94/1, 62/1 |
| 43 | compatible | compatible | 97/2/c, 93/1/b | 97/2/c, 97/1 |
| 45 | compatible | compatible | 104/4, 81/b | 104/4, 81/a |
