# Evaluation report: baseline_v1_dev24

- Date: 2026-10-27T16:20:35+00:00 · git `7b073fa`
- Retrieval: hybrid, k=8, prefix `v1_basic`, embeddings `intfloat/multilingual-e5-small`
- LLM: `gemini-3.5-flash-lite` (version `3.5-flash-lite-07-2026`), temperature 0, prompt `assess_v1`
- API calls in this invocation: 11 (cache hits: 13)
- Answers first produced by the API on: 2026-10-25 (3), 2026-10-26 (1), 2026-10-27 (20)
- Answer key frozen (eval/freezes.json): batch 1 at 2026-10-27T15:50:26Z (34 cases); batch 2 at 2026-10-27T16:16:02Z (11 cases)
- ⚠ Answers produced before their case was frozen (seen before the key was fixed): cases 1, 6, 12, 20
- Sets in this run: dev

## Metrics

| Metric | dev |
|---|---|
| Cases | 24 |
| Retrieval hit @5 | 75% |
| Retrieval hit @8 | 83% |
| Retrieval hit @10 | 92% |
| Retrieval hit @12 | 92% |
| Label accuracy | 88% |
| Label + reason accuracy | 83% |
| Citation accuracy (conflict cases) | 83% (n=18) |
| Citation accuracy (all with expected art.) | 83% |
| Unclear rate | 12% |
| Rejected citations + references | 0 |
| API calls (this invocation) | 11 |

Confusion (rows = expected, columns = given; hits = label in acceptable_labels):

| set | expected | compatible | conflict | unclear | hits |
|---|---|---|---|---|---|
| dev | compatible | 4 | 0 | 0 | 4/4 |
| dev | conflict | 0 | 15 | 3 | 15/18 |
| dev | borderline | 1 | 1 | 0 | 2/2 |

## Cases

Rank = first expected article in hybrid top 30 (– = none expected, >30 = miss). Cited: article/n.º/alínea.

| id | set | proposal | exp. art. | rank | label | ok | cited |
|---|---|---|---|---|---|---|---|
| 1 | dev | Reintroduzir a pena de morte | 24 | 1 | conflict | ✔ | 24/2, 24/1 |
| 2 | dev | Instituir a prisão perpétua para crimes de terro… | 30 | 6 | conflict | ✔ | 30/1 |
| 3 | dev | Permitir escutas telefónicas sem autorização de … | 34 | 2 | conflict | ✔ | 34/1, 34/4 |
| 4 | dev | Criar uma religião oficial do Estado | 41 | 4 | conflict | ✔ | 41/4, 43/3 |
| 5 | dev | Obrigar os jornais a submeter artigos a aprovaçã… | 37,38 | 30 | unclear | ✘ (no exp. cit.) | 168/6/a |
| 6 | dev | Proibir greves nos transportes públicos | 57 | 1 | conflict | ✔ | 57/1, 57/2, 57/3 |
| 7 | dev | Tornar o ensino básico pago | 74 | 1 | conflict | ✔ | 74/2/a |
| 8 | dev | Extinguir o Serviço Nacional de Saúde | 64 | 1 | conflict | ✔ | 64/2/a, 64/3/a |
| 9 | dev | Reduzir o número de deputados para 150 | 148 | 1 | conflict | ✔ | 148 |
| 10 | dev | Permitir que o Presidente da República cumpra tr… | 123 | 2 | conflict | ✔ | 123/1 |
| 11 | dev | Expulsar do país cidadãos portugueses condenados… | 33 | 1 | conflict | ✔ | 33/1 |
| 12 | dev | Aumentar o investimento público em energias reno… | 66,81 | 1 | compatible | ✔ | 81/m, 81/a |
| 20 | dev | Baixar a idade mínima de voto para os 16 anos | 49 | 9 | unclear | ✘ (no exp. cit.) | 122, 113/1 |
| 35 | dev | Exigir autorização prévia do Estado para publica… | 37,42 | >30 | unclear | ✘ (no exp. cit.) | – |
| 36 | dev | Permitir à polícia entrar em casas durante a noi… | 34 | 1 | conflict | ✔ | 34/3 |
| 37 | dev | Tirar os filhos aos pais sem decisão de um tribu… | 36 | 4 | conflict | ✔ | 36/6 |
| 38 | dev | Permitir despedir trabalhadores por causa das su… | 53 | 1 | conflict | ✔ | 53 |
| 39 | dev | Confiscar terrenos privados sem pagar nada aos d… | 62 | 1 | conflict | ✔ | 62/1, 62/2, 94/1 |
| 40 | dev | Proibir casamentos entre pessoas de nacionalidad… | 36,13 | 1 | conflict | ✔ | 36/1, 13/2 |
| 41 | dev | Proibir o ensino privado | 43,75 | 2 | conflict | ✔ | 43/4, 75/2 |
| 42 | dev | Criar uma rede de creches públicas | 67 | 10 | compatible | ✔ (no exp. cit.) | 74/2/b, 75/1 |
| 43 | dev | Apoiar os agricultores contra prejuízos causados… | 93,97 | 1 | compatible | ✔ | 97/2/c, 93/1/b |
| 44 | dev | Proibir a publicidade enganosa | 60 | 1 | compatible | ✔ | 60/1, 60/2 |
| 45 | dev | Aumentar o IVA da restauração | 103,104 | 6 | compatible | ✔ | 104/4, 81/b |

## Failures

Wrong label, expected article not cited, or retrieval miss @8.

### 5 (dev): Obrigar os jornais a submeter artigos a aprovação prévia do Governo
- Why: label unclear not in ['conflict']; expected article not cited; retrieval miss @8 (rank 30). Expected art.: 37, 38
- Top 8: 134 (0.878), 197_n1 (0.872), 192 (0.869), 119_n1 (0.868), 169_n1 (0.864), 161 (0.864), 288 (0.863), 168_n6 (0.861)
- Summary: A proposta é demasiado vaga ou omissa quanto aos aspetos essenciais da liberdade de imprensa e regulação, não sendo possível avaliá-la com segurança com base apenas nos excertos constitucionais fornecidos.
- Missing info: Faltam excertos da Constituição relativos aos direitos, liberdades e garantias fundamentais, em particular os artigos que consagram a liberdade de imprensa, a liberdade de expressão e a proibição de censura prévia.

### 20 (dev): Baixar a idade mínima de voto para os 16 anos
- Why: label unclear not in ['conflict']; expected article not cited; retrieval miss @8 (rank 9). Expected art.: 49
- Top 8: 126 (0.877), 122 (0.875), 152 (0.870), 148 (0.868), 113 (0.865), 128 (0.864), 167_n6 (0.861), 171 (0.861)
- Summary: A proposta é pouco clara e os excertos fornecidos não contêm informação suficiente para a avaliar.
- Missing info: Faltam excertos constitucionais que definam a capacidade eleitoral ativa (quem pode votar) e a idade mínima para o exercício do direito de voto.

### 35 (dev): Exigir autorização prévia do Estado para publicar livros
- Why: label unclear not in ['conflict']; expected article not cited; retrieval miss @8 (rank >30). Expected art.: 37, 42
- Top 8: 73 (0.853), 165_n3 (0.852), 165_n4 (0.852), 227_n2 (0.851), 74 (0.851), 112_n2 (0.851), 233 (0.851), 278_n4 (0.850)
- Summary: A proposta é demasiado vaga e não fornece pormenores suficientes para uma avaliação segura à luz dos excertos disponibilizados.
- Missing info: Faltam excertos constitucionais que regulem a liberdade de expressão, a liberdade de imprensa e a proibição da censura, bem como mais pormenores sobre o âmbito e a aplicação prática da medida proposta.

### 42 (dev): Criar uma rede de creches públicas
- Why: expected article not cited; retrieval miss @8 (rank 10). Expected art.: 67
- Top 8: 75 (0.866), 43 (0.851), 144 (0.851), 74 (0.850), 255 (0.848), 257 (0.846), 247 (0.846), 267 (0.846)
- Summary: A proposta de criar uma rede de creches públicas é compatível com os princípios constitucionais de garantia do ensino e da educação pré-escolar pelo Estado.
