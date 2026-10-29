# Experiment: cross-encoder reranking (dev, retrieval only)

- Date: 2026-10-27T17:33:55+00:00 · 24 dev cases · no Gemini calls
- Reranker: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` @ `1427fd652930` (safetensors, no remote code)
- CPU: Intel64 Family 6 Model 170 Stepping 4, GenuineIntel · 22 logical cores · torch threads 16
- RAM (process): start 456 MB · e5 + index 1275 MB · + reranker 2085 MB · **peak 2382 MB**

## Summary

| Config | Hit rate | Mean rank* | MRR | Not found | Latency / query | Added by rerank | Regressions vs A | Improvements vs A |
|---|---|---|---|---|---|---|---|---|
| A) hybrid k=8 | 20/24 (83%) @8 | 5.5 | 0.65 | 0 | 23 ms | 0 ms | – | – |
| B) hybrid k=10 | 22/24 (92%) @10 | 5.5 | 0.65 | 0 | 23 ms | 0 ms | – | 20, 42 |
| C) rerank top 30 -> 8 | 20/24 (83%) @8 | 5.1 | 0.71 | 1 | 1865 ms | 1841 ms | 1, 2 | 20, 42 |
| D) rerank top 50 -> 8 | 20/24 (83%) @8 | 4.3 | 0.71 | 0 | 2746 ms | 2723 ms | 1, 2 | 20, 42 |

*Rank of the first expected article; not found counts as 51. A and B share the same hybrid ranking (top 50; only k differs). C reorders the hybrid top 30 and D the top 50, so they cannot find anything below that.

## Regressions (hit in A, miss in the config)

- **C**, case 1: Reintroduzir a pena de morte — expected [24], rank A=1 → C=12; C top 8: 28, 33_n6, 32_n8, 27_n5, 19_n4, 31, 131, 292
- **C**, case 2: Instituir a prisão perpétua para crimes de terrorismo — expected [30], rank A=6 → C=10; C top 8: 28, 33_n4, 27_n3, 33_n3, 27_n5, 31, 33_n8, 27_n4
- **D**, case 1: Reintroduzir a pena de morte — expected [24], rank A=1 → D=17; D top 8: 28, 62, 33_n6, 32_n8, 27_n5, 19_n4, 19_n8, 278_n5
- **D**, case 2: Instituir a prisão perpétua para crimes de terrorismo — expected [30], rank A=6 → D=13; D top 8: 28, 33_n4, 27_n3, 33_n3, 32_n8, 27_n5, 292, 34

## Per case (rank of the first expected article)

| id | proposal | expected | A | B | C | D |
|---|---|---|---|---|---|---|
| 1 | Reintroduzir a pena de morte | 24 | 1 | 1 | 12 ✘ | 17 ✘ |
| 2 | Instituir a prisão perpétua para crimes de … | 30 | 6 | 6 | 10 ✘ | 13 ✘ |
| 3 | Permitir escutas telefónicas sem autorizaçã… | 34 | 2 | 2 | 1 | 1 |
| 4 | Criar uma religião oficial do Estado | 41 | 4 | 4 | 2 | 2 |
| 5 | Obrigar os jornais a submeter artigos a apr… | 37,38 | 30 ✘ | 30 ✘ | 22 ✘ | 34 ✘ |
| 6 | Proibir greves nos transportes públicos | 57 | 1 | 1 | 1 | 1 |
| 7 | Tornar o ensino básico pago | 74 | 1 | 1 | 1 | 1 |
| 8 | Extinguir o Serviço Nacional de Saúde | 64 | 1 | 1 | 1 | 1 |
| 9 | Reduzir o número de deputados para 150 | 148 | 1 | 1 | 1 | 1 |
| 10 | Permitir que o Presidente da República cump… | 123 | 2 | 2 | 1 | 1 |
| 11 | Expulsar do país cidadãos portugueses conde… | 33 | 1 | 1 | 1 | 1 |
| 12 | Aumentar o investimento público em energias… | 66,81 | 1 | 1 | 1 | 1 |
| 20 | Baixar a idade mínima de voto para os 16 anos | 49 | 9 ✘ | 9 | 2 | 2 |
| 35 | Exigir autorização prévia do Estado para pu… | 37,42 | 44 ✘ | 44 ✘ | >30 ✘ | 13 ✘ |
| 36 | Permitir à polícia entrar em casas durante … | 34 | 1 | 1 | 1 | 1 |
| 37 | Tirar os filhos aos pais sem decisão de um … | 36 | 4 | 4 | 1 | 1 |
| 38 | Permitir despedir trabalhadores por causa d… | 53 | 1 | 1 | 1 | 1 |
| 39 | Confiscar terrenos privados sem pagar nada … | 62 | 1 | 1 | 1 | 1 |
| 40 | Proibir casamentos entre pessoas de naciona… | 36,13 | 1 | 1 | 2 | 2 |
| 41 | Proibir o ensino privado | 43,75 | 2 | 2 | 3 | 3 |
| 42 | Criar uma rede de creches públicas | 67 | 10 ✘ | 10 | 2 | 2 |
| 43 | Apoiar os agricultores contra prejuízos cau… | 93,97 | 1 | 1 | 1 | 1 |
| 44 | Proibir a publicidade enganosa | 60 | 1 | 1 | 1 | 1 |
| 45 | Aumentar o IVA da restauração | 103,104 | 6 | 6 | 2 | 2 |
