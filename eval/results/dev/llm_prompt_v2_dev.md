# Comparison: baseline_k10_dev30 → prompt_v2_k10_dev30

- **before** `baseline_k10_dev30`: git `cb97d62`, 2026-10-27T18:10:29+00:00, hybrid k=10, prompt `assess_v1`, `gemini-3.5-flash-lite` (3.5-flash-lite-07-2026)
- **after** `prompt_v2_k10_dev30`: git `6f133d2`, 2026-10-27T18:31:26+00:00, hybrid k=10, prompt `assess_v2`, `gemini-3.5-flash-lite` (3.5-flash-lite-07-2026)
- Config differences: prompt_version: assess_v1 → assess_v2
- Sets compared: dev · 30 cases

## Metrics

| Metric | before | after | Δ |
|---|---|---|---|
| Label accuracy (dev) | 90% | 93% | +3 pp |
| Label + reason accuracy (dev) | 90% | 93% | +3 pp |
| Citation accuracy (conflict cases) (dev) | 89% | 89% | +0 pp |
| Citation accuracy (all with expected art.) (dev) | 92% | 92% | +0 pp |
| Unclear rate (dev) | 23% | 27% | +3 pp |
| Rejected citations + references (dev) | 0 | 0 | |
| compatible↔conflict confusions | 51 | none | |
| likely_compatible where not acceptable | 51 | none | |
| compatible-expected cases answered unclear | none | none | |
| Avg input tokens / call | 2585 | 2689 | +4% |
| Avg output tokens / call | 275 | 273 | -0% |
| Avg total tokens / call | 2860 | 2963 | +4% |

## Improvements (label + reason wrong before, right after)

- **51** Tornar obrigatória a vacinação das crianças — expected [64, 25]: compatible [69/1, 64/3/a] → unclear [69/1, 64/2/b]

## Regressions (label + reason right before, wrong after)

None.
## Other changes (same label + reason verdict; label or citations differ)

| id | label before | label after | cited before | cited after |
|---|---|---|---|---|
| 4 | conflict | conflict | 41/4, 288/c, 41/1 | 41/1, 41/4, 43/2, 43/3 |
| 6 | conflict | conflict | 57/1, 57/2, 57/3 | 57/1, 57/3, 270 |
| 8 | conflict | conflict | 64/2/a, 64/3/a, 64/3/b, 64/4, 165/1/f | 64/2/a, 64/3/a |
| 11 | conflict | conflict | 33/1, 33/3 | 33/1 |
| 36 | conflict | conflict | 34/3, 272/3 | 34/1, 34/3 |
| 38 | conflict | conflict | 53, 59/1 | 53 |
| 39 | conflict | conflict | 62/2, 94/1, 62/1 | 62/1, 62/2, 94/1 |
| 40 | conflict | conflict | 36/1, 13/2 | 13/2, 36/1 |
| 42 | compatible | compatible | 67/2/b, 74/2/b | 67/2/b |
| 43 | compatible | compatible | 97/2/c, 97/1 | 97/2/c, 97/1, 93/1 |
| 45 | compatible | compatible | 104/4, 81/a | 104/4, 66/2/h |
| 46 | unclear | unclear | 9/d, 81/a | – |
| 50 | unclear | unclear | – | 40, 129, 132, 167/6, 223/2, 233, 249, 276, 284, 288 |

## Case 51: Tornar obrigatória a vacinação das crianças

- Expected: [64, 25]; acceptable: ['unclear', 'conflict']
- **before**: compatible [69/1, 64/3/a]
  - summary: A proposta de tornar a vacinação das crianças obrigatória é enquadrada pelo dever do Estado de proteger a saúde pública e garantir a proteção da infância.
  - missing info: –
- **after**: unclear [69/1, 64/2/b]
  - summary: A proposta impõe a obrigatoriedade da vacinação infantil, mas os excertos fornecidos não contêm os direitos fundamentais necessários para avaliar essa restrição.
  - missing info: Faltam artigos relativos aos direitos, liberdades e garantias pessoais (como a integridade física, a liberdade pessoal e a reserva da vida privada) e disposições específicas sobre os limites constitucionais à imposição de tratamentos médicos ou medidas de saúde pública obrigatórias.
