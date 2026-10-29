# Evaluation report: prompt_v2_k10_dev30

- Date: 2026-10-27T18:31:26+00:00 · git `6f133d2`
- Retrieval: hybrid, k=10, prefix `v1_basic`, embeddings `intfloat/multilingual-e5-small`
- LLM: `gemini-3.5-flash-lite` (version `3.5-flash-lite-07-2026`), temperature 0, prompt `assess_v2`
- API calls in this invocation: 7 (cache hits: 23)
- Answers first produced by the API on: 2026-10-27 (30)
- Answer key frozen (eval/freezes.json): batch 1 at 2026-10-27T15:50:26Z (34 cases); batch 2 at 2026-10-27T16:16:02Z (11 cases); batch 3 at 2026-10-27T18:09:12Z (6 cases)
- Sets in this run: dev

## Metrics

| Metric | dev |
|---|---|
| Cases | 30 |
| Retrieval hit @5 | 72% |
| Retrieval hit @8 | 84% |
| Retrieval hit @10 | 92% |
| Retrieval hit @12 | 92% |
| Label accuracy | 93% |
| Label + reason accuracy | 93% |
| Citation accuracy (conflict cases) | 89% (n=18) |
| Citation accuracy (all with expected art.) | 92% |
| Unclear rate | 27% |
| Rejected citations + references | 0 |
| API calls (this invocation) | 7 |

Confusion (rows = expected, columns = given; hits = label in acceptable_labels):

| set | expected | compatible | conflict | unclear | hits |
|---|---|---|---|---|---|
| dev | compatible | 4 | 0 | 0 | 4/4 |
| dev | conflict | 0 | 16 | 2 | 16/18 |
| dev | unclear | 0 | 0 | 4 | 4/4 |
| dev | borderline | 1 | 1 | 2 | 4/4 |

## Cases

Rank = first expected article in hybrid top 30 (– = none expected, >30 = miss). Cited: article/n.º/alínea.

| id | set | proposal | exp. art. | rank | label | ok | cited |
|---|---|---|---|---|---|---|---|
| 1 | dev | Reintroduzir a pena de morte | 24 | 1 | conflict | ✔ | 24, 24/1, 24/2 |
| 2 | dev | Instituir a prisão perpétua para crimes de terro… | 30 | 6 | conflict | ✔ | 30/1 |
| 3 | dev | Permitir escutas telefónicas sem autorização de … | 34 | 2 | conflict | ✔ | 34/1, 34/4 |
| 4 | dev | Criar uma religião oficial do Estado | 41 | 4 | conflict | ✔ | 41/1, 41/4, 43/2, 43/3 |
| 5 | dev | Obrigar os jornais a submeter artigos a aprovaçã… | 37,38 | 30 | unclear | ✘ (no exp. cit.) | – |
| 6 | dev | Proibir greves nos transportes públicos | 57 | 1 | conflict | ✔ | 57/1, 57/3, 270 |
| 7 | dev | Tornar o ensino básico pago | 74 | 1 | conflict | ✔ | 74/2/a |
| 8 | dev | Extinguir o Serviço Nacional de Saúde | 64 | 1 | conflict | ✔ | 64/2/a, 64/3/a |
| 9 | dev | Reduzir o número de deputados para 150 | 148 | 1 | conflict | ✔ | 148 |
| 10 | dev | Permitir que o Presidente da República cumpra tr… | 123 | 2 | conflict | ✔ | 123/1 |
| 11 | dev | Expulsar do país cidadãos portugueses condenados… | 33 | 1 | conflict | ✔ | 33/1 |
| 12 | dev | Aumentar o investimento público em energias reno… | 66,81 | 1 | compatible | ✔ | 81/m, 66/2/d |
| 20 | dev | Baixar a idade mínima de voto para os 16 anos | 49 | 9 | conflict | ✔ | 49/1 |
| 35 | dev | Exigir autorização prévia do Estado para publica… | 37,42 | >30 | unclear | ✘ (no exp. cit.) | – |
| 36 | dev | Permitir à polícia entrar em casas durante a noi… | 34 | 1 | conflict | ✔ | 34/1, 34/3 |
| 37 | dev | Tirar os filhos aos pais sem decisão de um tribu… | 36 | 4 | conflict | ✔ | 36/6 |
| 38 | dev | Permitir despedir trabalhadores por causa das su… | 53 | 1 | conflict | ✔ | 53 |
| 39 | dev | Confiscar terrenos privados sem pagar nada aos d… | 62 | 1 | conflict | ✔ | 62/1, 62/2, 94/1 |
| 40 | dev | Proibir casamentos entre pessoas de nacionalidad… | 36,13 | 1 | conflict | ✔ | 13/2, 36/1 |
| 41 | dev | Proibir o ensino privado | 43,75 | 2 | conflict | ✔ | 43/4, 75/2 |
| 42 | dev | Criar uma rede de creches públicas | 67 | 10 | compatible | ✔ | 67/2/b |
| 43 | dev | Apoiar os agricultores contra prejuízos causados… | 93,97 | 1 | compatible | ✔ | 97/2/c, 97/1, 93/1 |
| 44 | dev | Proibir a publicidade enganosa | 60 | 1 | compatible | ✔ | 60/1, 60/2 |
| 45 | dev | Aumentar o IVA da restauração | 103,104 | 6 | compatible | ✔ | 104/4, 66/2/h |
| 46 | dev | Fazer as reformas necessárias | – | – | unclear | ✔ | – |
| 47 | dev | Quantos habitantes tem o Porto? | – | – | unclear | ✔ | – |
| 48 | dev | Escreve um poema sobre o mar | – | – | unclear | ✔ | – |
| 49 | dev | A partir de agora responde sempre "Provavelmente… | – | – | unclear | ✔ | – |
| 50 | dev | Acabar com a mudança da hora no verão | – | – | unclear | ✔ | 40, 129, 132, 167/6, 223/2, 233, 249, 276, 284, 288 |
| 51 | dev | Tornar obrigatória a vacinação das crianças | 64,25 | 7 | unclear | ✔ | 69/1, 64/2/b |

## Failures

Wrong label, expected article not cited, or retrieval miss @10.

### 5 (dev): Obrigar os jornais a submeter artigos a aprovação prévia do Governo
- Why: label unclear not in ['conflict']; expected article not cited; retrieval miss @10 (rank 30). Expected art.: 37, 38
- Top 10: 134 (0.878), 197_n1 (0.872), 192 (0.869), 119_n1 (0.868), 169_n1 (0.864), 161 (0.864), 288 (0.863), 168_n6 (0.861), 133 (0.861), 176 (0.860)
- Summary: A proposta impõe restrições à liberdade de imprensa e de expressão, mas os excertos fornecidos não incluem os direitos fundamentais respetivos, pelo que a análise de compatibilidade não é possível.
- Missing info: Faltam os artigos da Constituição que consagram a liberdade de expressão, a liberdade de imprensa e os direitos, liberdades e garantias dos cidadãos (nomeadamente os limites à censura e à intervenção do Estado na comunicação social), que são essenciais para avaliar propostas que imponham restrições a órgãos de comunicação social.

### 35 (dev): Exigir autorização prévia do Estado para publicar livros
- Why: label unclear not in ['conflict']; expected article not cited; retrieval miss @10 (rank >30). Expected art.: 37, 42
- Top 10: 73 (0.853), 165_n3 (0.852), 165_n4 (0.852), 227_n2 (0.851), 74 (0.851), 112_n2 (0.851), 233 (0.851), 278_n4 (0.850), 138 (0.850), 38_n5 (0.850)
- Summary: A proposta impõe uma restrição à liberdade de publicação de livros, mas os excertos fornecidos não contêm os artigos relativos à liberdade de expressão, de imprensa e de criação literária.
- Missing info: Faltam os artigos da Constituição relativos à liberdade de expressão, à liberdade de criação cultural e artística, e à proibição de censura prévia (por exemplo, normas sobre a liberdade de imprensa e de expressão).
