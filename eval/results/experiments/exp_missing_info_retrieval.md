# Experiment: retrieval with the LLM's missing_information (dev, retrieval only)

- Date: 2026-10-27T18:00:36+00:00 · source: `baseline_v1_dev24.json` (k=8 answers) · hybrid top 30 · 0 Gemini calls

Rank of each expected article (first chunk of that article) in the hybrid top 30.

| case | expected | (0) proposal | (a) missing_info | (b) proposal + missing_info |
|---|---|---|---|---|
| 5 | 37, 38 | 37: >30, 38: 30 | 37: 6, 38: 8 | 37: 5, 38: 10 |
| 20 | 49 | 49: 9 | 49: >30 | 49: >30 |
| 35 | 37, 42 | 37: >30, 42: >30 | 37: 4, 42: >30 | 37: 3, 42: >30 |

## Queries and top 5

### 5: Obrigar os jornais a submeter artigos a aprovação prévia do Governo
- missing_information: Faltam excertos da Constituição relativos aos direitos, liberdades e garantias fundamentais, em particular os artigos que consagram a liberdade de imprensa, a liberdade de expressão e a proibição de censura prévia.
- (0) top 5: 134, 197_n1, 192, 119_n1, 169_n1
- (a) top 5: 288, 27_n3, 16, 9, 18
- (b) top 5: 288, 223_n2, 134, 27_n3, 37

### 20: Baixar a idade mínima de voto para os 16 anos
- missing_information: Faltam excertos constitucionais que definam a capacidade eleitoral ativa (quem pode votar) e a idade mínima para o exercício do direito de voto.
- (0) top 5: 126, 122, 152, 148, 113
- (a) top 5: 223_n2, 288, 27_n3, 59_n2, 55_n6
- (b) top 5: 223_n2, 288, 27_n3, 59_n2, 67

### 35: Exigir autorização prévia do Estado para publicar livros
- missing_information: Faltam excertos constitucionais que regulem a liberdade de expressão, a liberdade de imprensa e a proibição da censura, bem como mais pormenores sobre o âmbito e a aplicação prática da medida proposta.
- (0) top 5: 73, 165_n3, 165_n4, 227_n2, 74
- (a) top 5: 288, 27_n3, 223_n2, 37, 119_n1
- (b) top 5: 288, 27_n3, 37, 223_n2, 119_n1
