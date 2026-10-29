# Evaluation notes

Results files live in `eval/results/`: the frozen baseline (`baseline_v1`) and
the final test run (`final_test`) at the top level, dev runs and comparisons in
`dev/`, side experiments, smoke tests and legacy retrieval runs in
`experiments/`. Compare LLM runs with `eval/compare_llm_runs.py` (e.g.
`dev/baseline_k10_dev30 dev/prompt_v2_k10_dev30`); legacy retrieval runs with
`eval/legacy/compare_runs.py`.

Commit hashes inside eval/results and eval/freezes.json refer to the
development history, which is not published; freeze timestamps are kept.

## 2026-10-25 — Hierarchy in the chunk prefix (v2_hierarchy): negative result

**Change.** The chunk prefix gained the two most specific hierarchy levels:
`Artigo 123.º, n.º 1 — Presidente da República › Estatuto e eleição › Reelegibilidade: ...`
instead of `Artigo 123.º, n.º 1 — Reelegibilidade: ...` (v1_basic).

**Result** (12 cases, e5-small, scored on the current cases):

| Strategy  | k | v1_basic_prefix | v2_hierarchy_prefix |
|-----------|---|-----------------|---------------------|
| article   | 5 | 10/12           | 10/12               |
| article   | 8 | 11/12           | 11/12               |
| paragraph | 5 | 9/12            | 8/12                |
| paragraph | 8 | 9/12            | 8/12                |
| hybrid    | 5 | 10/12           | 9/12                |
| hybrid    | 8 | 11/12           | 11/12               |

Ranks got worse in several cases (e.g. case 2 paragraph 4 → 19, case 12
1 → 3/4). The only gain was the targeted one: case 10 paragraph 53 → 11, still
a miss.

**Likely cause.** The hierarchy adds the same long text to many chunks (24
articles share "Direitos, liberdades e garantias › Direitos, liberdades e
garantias pessoais"). Shared prefixes make chunks more alike and dilute the
distinctive content, especially in short paragraphs. Top-8 scores stayed packed
in 0.85–0.89.

**Decision.** Keep v1_basic as the default; v2_hierarchy stays selectable in
`chunking.py` (`prefix_version`) only to reproduce this result.

**Reproducibility.** Indexes rebuilt with v1_basic (run `v1_rebuild`): every
hit rate and per-case rank identical to `v1_basic_prefix`; vectors
bit-identical to the original build; top-20 lists identical.

## Known failures

- Case 5 (prior approval of newspaper articles by the Government → Art. 37.º/38.º):
  missed by every strategy (rank 20–33 in v1). Vocabulary gap: the article says
  "censura", the proposal says "aprovação prévia do Governo". To be tested with
  query rewriting.

## 2026-10-27 — Baseline v1 (frozen)

Config: hybrid, k=8, prefix `v1_basic`, multilingual-e5-small; LLM
`gemini-3.5-flash-lite` (version `3.5-flash-lite-07-2026`), temperature 0,
prompt `assess_v1`. Answer key `eval/cases.json` (34 cases: 13 dev, 21 test),
frozen 2026-10-27T15:50:26Z. Report: `eval/results/baseline_v1.md`
(generated at the label+reason metric commit, 0 API calls, all answers from cache).

| Metric | dev | test |
|---|---|---|
| Cases | 13 | 21 |
| Retrieval hit @5 | 77% | 83% |
| Retrieval hit @8 | 85% | 83% |
| Retrieval hit @10 | 92% | 83% |
| Retrieval hit @12 | 92% | 83% |
| Label accuracy | 85% | 95% |
| Label + reason accuracy | 85% | 81% |
| Citation accuracy (conflict cases) | 83% (n=12) | 88% (n=8) |
| Citation accuracy (all with expected art.) | 85% | 83% |
| Unclear rate | 15% | 33% |
| Rejected citations + references | 0 | 0 |

Label + reason failures: dev 5, 20; test 17, 27, 29, 30.

**Contamination.** Test cases 13, 15, 22, 28, 30 and 33 were run before the
answer key was frozen on 2026-10-27 (33 in the smoke tests on 2026-10-25; the
others in the app on 2026-10-26). No design decisions were based on them.

**Art. 288.º is a hub chunk.** "Limites materiais da revisão" lists many
constitutional principles, so it is close to many unrelated queries: it is in
the hybrid top 8 in 7 of 34 cases (5, 12, 16, 17, 19, 33, 34) and was cited in
cases 17 and 34, although it limits constitutional revision, not ordinary laws.

**Known test failure: case 30** ("Criar regiões administrativas no
continente"): labelled `potential_conflict`, acceptable labels are
`likely_compatible` / `unclear` (the model reasoned correctly about the
referendum requirement). It must NOT be tuned on: any fix has to be motivated
by dev cases or general rules, and case 30 is only re-checked at the end.

## 2026-10-27 — Dev set expanded to 24 cases (baseline v1, dev only)

Eleven dev cases (35-45) were added and frozen as batch 2 in
`eval/freezes.json` (2026-10-27T16:16:02Z), written and checked against
`articles.json` **before any experiment**; the test set is unchanged and was
not run. Run `baseline_v1_dev24` (`eval/results/dev/baseline_v1_dev24.md`,
same config as baseline v1, 11 new API calls):

| Metric (dev, 24 cases) | Value |
|---|---|
| Retrieval hit @5 / @8 / @10 / @12 | 75% / 83% / 92% / 92% |
| Label accuracy | 88% |
| Label + reason accuracy | 83% |
| Citation accuracy (conflict cases, n=18) | 83% |
| Unclear rate | 12% |
| Rejected citations + references | 0 |

Dev failures: 5, 20, 35 (wrong label, retrieval miss) and 42 (right label,
expected Art. 67.º at rank 10, not cited). Cases 5 and 35 share the same
pattern: "prior approval" wording without the word "censura" never retrieves
Art. 37.º. Cases 20 and 42 are at rank 9-10, just outside k=8.

## 2026-10-27 — Reranker experiment: decision rule (written before running)

Candidate: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` at revision
`1427fd652930e4ba29e8149678df786c240d8825` (safetensors only, no remote code).
Configs on the 24 dev cases, retrieval only: A) hybrid k=8, B) hybrid k=10,
C) rerank top 30 -> 8, D) rerank top 50 -> 8.

Decision rule: "Adopt reranking only if it beats hybrid k=10 on dev hit rate,
has zero regressions vs baseline, adds < 1 s per query on CPU, and fits
deploy RAM. Otherwise adopt k=10 (if it has no regressions) and record
reranking as a negative result."

## 2026-10-27 — Reranker experiment: result (negative)

`eval/results/experiments/exp_rerank.md` (24 dev cases, retrieval only, no Gemini calls,
test set not loaded). Reranker `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`
@ `1427fd65`, safetensors only (6 files fetched, no .bin/.py, no repo code run).

| Config | Hit rate | MRR | Latency / query (CPU) | Regressions vs A |
|---|---|---|---|---|
| A) hybrid k=8 | 20/24 (83%) @8 | 0.65 | 23 ms | – |
| B) hybrid k=10 | 22/24 (92%) @10 | 0.65 | 23 ms | – |
| C) rerank top 30 -> 8 | 20/24 (83%) @8 | 0.71 | 1865 ms | 1, 2 |
| D) rerank top 50 -> 8 | 20/24 (83%) @8 | 0.71 | 2746 ms | 1, 2 |

Peak process RAM: 1.28 GB with e5 + index, 2.38 GB with e5 + reranker.

Against the decision rule recorded before the run, reranking fails every
condition: it does not beat k=10 (83% vs 92%), it regresses cases 1 and 2
(Art. 24.º drops from rank 1 to 12/17; Art. 30.º from 6 to 10/13), it adds
1.8-2.7 s per query, and it adds ~0.8 GB of RAM. MRR improves (0.65 -> 0.71)
and it fixes 20 and 42, but the reranker (trained on translated web search,
not legal text) promotes generic criminal-procedure articles (28, 27, 33).
**Decision: reranking recorded as a negative result; stage stays in the code,
off by default (`RERANK_ENABLED`).** Per the rule, k=10 is adopted (no
regressions on dev); changing the app default is a separate step, because it
changes every LLM prompt and needs a new LLM evaluation run.

Side observation: in config D, case 35 (prior authorisation to publish books)
rose from rank 44 to 13. This supports trying query rewriting for the
censorship cases; not pursued now.

## 2026-10-27 — k=10 with the LLM on dev: decision rule (written before running)

"Adopt k=10 as the app default only if, on dev: label + reason accuracy >=
baseline_v1_dev24 (83%); no compatible<->conflict confusion; and every case
that was correct at k=8 and wrong at k=10 is listed and reviewed. Otherwise
keep k=8."

## 2026-10-27 — k=10 with the LLM on dev: result (adopted)

Run `baseline_v1_dev24_k10` (24 dev cases, test set not run),
compared with `baseline_v1_dev24` in `eval/results/dev/llm_k10_dev.md`:

| Metric (dev) | k=8 | k=10 |
|---|---|---|
| Label accuracy | 88% | 92% |
| Label + reason accuracy | 83% | 92% |
| Citation accuracy (conflict cases) | 83% | 89% |
| Unclear rate | 12% | 8% |
| compatible<->conflict confusions | none | none |
| Avg input tokens / call | 2145 | 2542 (+19%) |

Improvements: 20 (now cites 49/1, label conflict) and 42 (now cites 67/2/b).
Regressions (right at k=8, wrong at k=10): none, so there was nothing to
review. Against the rule recorded before the run, all three conditions pass:
**k=10 adopted as the default** (`config.RETRIEVAL_K`; `retrieve()` now takes
its defaults from config). Remaining dev failures: 5 and 35 (censorship
wording, retrieval). The test set is still evaluated only at k=8
(`baseline_v1`); it will be re-run once, at the end.

Notes: the run used 28 API calls for 24 cases; the 4 extra were retries whose
cause (429/5xx vs invalid JSON) was not recorded. run_eval now records
per-case `attempts` and the client's `transport_retries` / `output_retries`.
At k=10 case 4 additionally cites Art. 288.º (hub chunk), without changing
its verdict.

## 2026-10-27 — Feasibility: retrieval with the LLM's missing_information (dev)

`eval/results/experiments/exp_missing_info_retrieval.md` (retrieval only, 0 Gemini calls;
missing_information taken from the k=8 answers in baseline_v1_dev24). Rank of
the expected articles in the hybrid top 30:

| case | expected | proposal | missing_info alone | proposal + missing_info |
|---|---|---|---|---|
| 5 | 37, 38 | >30, 30 | 6, 8 | 5, 10 |
| 20 | 49 | 9 | >30 | >30 |
| 35 | 37, 42 | >30, >30 | 4, >30 | 3, >30 |

The model's own description of what is missing ("proibição de censura")
recovers Art. 37.º for both censorship cases, which plain retrieval never
finds. But it is not a safe replacement for the query: for case 20 Art. 49.º
falls from rank 9 to >30, and every missing_info query pulls in hub chunks
(288, 27.º n.º 3, 223.º n.º 2) because of generic words such as "excertos
constitucionais" and "direitos, liberdades e garantias". If pursued, a second
retrieval pass should ADD chunks to the first-pass results (never replace
them) and ask the model for short legal keywords rather than a sentence.
Only 3 cases: a feasibility signal, not an evaluation. No decision taken.

## 2026-10-27 — Dev batch 3 ("unclear" cases) at k=10: dev30

Six dev cases (46-51) where "unclear" is the right answer were added and
frozen as batch 3 (`eval/freezes.json`, 2026-10-27T18:09:12Z) before any
second-pass feature. Run `baseline_k10_dev30` (`eval/results/dev/baseline_k10_dev30.md`,
k=10, 6 new API calls, no retries, test set not run):

| Metric (dev, 30 cases) | Value |
|---|---|
| Retrieval hit @10 | 92% |
| Label accuracy | 90% |
| Label + reason accuracy | 90% |
| Citation accuracy (conflict cases, n=18) | 89% |
| Unclear rate | 23% |
| Rejected citations + references | 0 |

Cases 46-50 (vague, off-topic question, poem request, "always answer
compatible" instruction, summer-time change): all `unclear`, correctly.

**Case 51 (compulsory child vaccination) failed in the most harmful way:**
`likely_compatible`, citing 69/1 and 64/3/a. Cause is retrieval, not
reasoning: the conflict-side article Art. 25.º (physical integrity) ranks
31 and Art. 18.º ranks 113, so the model only saw the supporting side
(Art. 69.º at rank 1, Art. 64.º at 7) and had no reason to flag anything.
This is a new failure type: one-sided evidence leading to a confident
"compatible". It is a dev case, so it may guide later work; it argues for
retrieving the rights a proposal restricts, not only the topic it is about.

## 2026-10-27 — Prompt assess_v2 (one-sided evidence): decision rule (written before running)

assess_v2 = assess_v1 + rule 8: before answering likely_compatible, check
whether the proposal imposes obligations, prohibitions or restrictions on
persons or entities; if the affected rights (DLG or economic, social and
cultural rights) are not in the excerpts, answer unclear and name them in
missing_information. Run on dev at k=10, compared with baseline_k10_dev30.

Decision rule: "Adopt assess_v2 only if, on dev: label + reason accuracy
>= 90% (k=10 baseline); zero likely_compatible answers on cases where it is
not acceptable; no compatible<->conflict confusion; at most 1 of the 5
compatible-expected cases (12, 42-45) turns unclear; every regression
listed and reviewed."

## 2026-10-27 — Prompt assess_v2 on dev: result (adopted)

Run `prompt_v2_k10_dev30` (k=10, 30 dev cases, test set not run), compared
with `baseline_k10_dev30` in `eval/results/dev/llm_prompt_v2_dev.md`. The first
attempt stopped at case 45 on a dropped connection (httpx.RemoteProtocolError,
not classified as retryable); fixed (dropped connections are now retried) and resumed from the cache.
API calls: 24 (first attempt) + 7 (resume) = 31.

| Metric (dev, 30) | assess_v1 | assess_v2 |
|---|---|---|
| Label accuracy | 90% | 93% |
| Label + reason accuracy | 90% | 93% |
| Citation accuracy (conflict cases) | 89% | 89% |
| Unclear rate | 23% | 27% |
| likely_compatible where not acceptable | 51 | none |
| compatible<->conflict confusions | 51 | none |
| compatible-expected (12, 42-45) answered unclear | none | none |
| Avg input tokens / call | 2585 | 2689 (+4%) |

Improvement: 51 (compulsory vaccination) compatible -> unclear; missing info
names physical integrity, personal liberty and privacy. Regressions: none.
All five conditions of the rule pass: **assess_v2 adopted as the default
prompt** (`config.PROMPT_VERSION`). Remaining dev failures: 5 and 35
(censorship wording, retrieval).

Follow-up (validation, not prompt): in case 50 the v2 reasoning lists all 10
retrieved articles to say none applies, and the auto-add rule turned each
mention into a citation ("referido no raciocínio"), so an `unclear` answer
shows 10 irrelevant citations. Auto-adding should probably be limited to
non-unclear labels or to articles the text relies on.

## 2026-10-27 — Folder reorganisation (path map)

The folder-reorganisation commit grouped the code by pipeline stage (`git mv`).
Entries above this one use the old paths; this is the map:

| Old path | New path |
|---|---|
| `app.py` | `app/streamlit_app.py` |
| `src/config.py`, `src/usage.py` | `src/common/config.py`, `src/common/usage.py` |
| `MODEL`, `load_model` in `src/build_index.py` | `src/common/embeddings.py` |
| `src/parse_constitution.py`, `src/chunking.py`, `src/build_index.py` | `src/ingest/…` (run via `scripts/parse_constitution.py`, `scripts/build_index.py`) |
| `src/retrieve.py`, `rerank.py`, `assess.py`, `validation.py`, `llm.py` | `src/rag/…` |
| `src/prompts/` | `src/rag/prompts/` |
| `scripts/run_eval.py`, `compare_llm_runs.py`, `assess_smoke.py` | `eval/…` |
| `scripts/token_stats.py` | `eval/experiments/token_stats.py` |
| `scripts/retrieval_test.py`, `compare_runs.py`, `eval/retrieval_cases.json` | `eval/legacy/…` |
| `tests/test_*.py` | `tests/common/`, `tests/rag/`, `tests/eval/` (run with `-s tests -t .`) |
| `eval/results/*` (later move, 2026-10-29) | dev runs → `eval/results/dev/`; `exp_*`, `retrieval_*`, `assess_smoke_*` → `eval/results/experiments/`; `baseline_v1`, `final_test` stay; `eval/ideas.md` folded into "Future work" below and deleted |

Unchanged: `data/`, `eval/cases.json`, `eval/freezes.json`, `eval/results/`,
`scripts/ask.py`, `scripts/inspect_pdf.py`. Verified before committing: 47
tests pass; a cache-only dev run (k=10, assess_v2) reproduced
`prompt_v2_k10_dev30` exactly with 0 API calls (30/30 cached); the app and
ask.py found the Gemini key from `.env`; `articles.json` and the index vectors
rebuilt byte-identical (only `built_at` in the metadata differed; the
committed index files were restored).

## 2026-10-28 — Final test run (pre-registered)

Written and committed before running. The test set is run once.

**Config** (code as of the commit before this entry; the run itself happens at the commit that adds
this entry, which changes only this file):

| Setting | Value | Source |
|---|---|---|
| Retrieval | hybrid | `config.RETRIEVAL_STRATEGY` |
| k | 10 | `config.RETRIEVAL_K` (run_eval `--k` default) |
| Chunk prefix | `v1_basic` | `data/processed/index_hybrid_e5small.meta.json` |
| Embeddings | `intfloat/multilingual-e5-small` @ `614241f6…` | `src/common/embeddings.py`, checked against the index metadata |
| LLM | `gemini-3.5-flash-lite`, version `3.5-flash-lite-07-2026` | `config.MODEL`, `config.MODEL_VERSION` |
| Temperature | 0 | `config.TEMPERATURE` |
| Prompt | `assess_v2` | `config.PROMPT_VERSION` (run_eval `--prompt` default) |
| Reranker | off | `config.RERANK_ENABLED` (env `RERANK_ENABLED` not set) |

Answer key: the 21 test cases (13-19, 21-34) of `eval/cases.json`, frozen in
batch 1 at 2026-10-27T15:50:26Z (the answer-key freeze commit); identical to
that version today. No test case has a cached answer under `assess_v2` (all 21 need an API
call); the only earlier test answers are `assess_v1` at k=8.

Command:
`.venv\Scripts\python eval\run_eval.py --run-name final_test --set test --max-api-calls 30`

**Metrics to report:** label accuracy and label + reason accuracy, next to the
baseline test run (`baseline_v1`: k=8, `assess_v1`: 95% / 81%). The two runs
differ in both k and prompt, so the comparison shows the combined effect.

**Reporting rules:**
- Every test case whose result changed vs baseline (label, label_ok or
  label_and_reason_ok) is listed, improvements and regressions alike.
- The 6 cases seen before the key was frozen (13, 15, 22, 28, 30, 33) are
  disclosed. (The report's automatic
  "answers before freeze" flag will not catch them: the new answers are
  produced after the freeze.) Case 30 is the known test failure.
- No prompt, retrieval or config change will be made based on these results.
  Only a crash or technical bug may be fixed; any such fix and any re-run of
  the affected cases will be disclosed here.

### Results

Run `final_test` (at the pre-registration commit, clean tree), run once as registered, no
crash, no re-run. Report: `eval/results/final_test.md`. API calls: 21
(0 cache hits, 0 transport retries, 0 output retries).

| Metric (test, 21) | baseline_v1 (k=8, assess_v1) | final_test (k=10, assess_v2) |
|---|---|---|
| Label accuracy | 95% (20/21) | 86% (18/21) |
| Label + reason accuracy | 81% (17/21) | 81% (17/21) |
| Retrieval hit @10 | 83% | 83% |
| Unclear rate | 33% | 29% |

Cases whose result changed vs baseline (label, label_ok or label + reason):
- 17 (ban unions in the public service; expects Art. 55.º): conflict -> unclear.
  **Regression** (label now wrong; label + reason was already wrong). Art. 55.º
  is at rank 14, outside the top 10; the model called the proposal too vague.
- 27 (compulsory voting; acceptable compatible/unclear; expects Art. 49.º):
  unclear -> conflict. **Regression** (label now wrong; label + reason was
  already wrong). Art. 49.º is not in the top 30; it cited Arts. 113.º, 121.º.
- 28 (raise university fees; acceptable conflict/unclear): unclear -> conflict,
  citing Arts. 74.º, 76.º. Correct both times; no metric change.

No improvements. Citation-only changes (label and scores unchanged): 22, 23,
26, 29, 31, 32, 34.

Cases still wrong (label + reason):
- 17: see above.
- 27: see above.
- 29 (remove nationality for serious crimes; expects Art. 26.º/30.º): label
  unclear is acceptable, but no expected article cited; Arts. 26.º/30.º at
  rank 30, and the model named the missing nationality rules. Also wrong at
  baseline.
- 30 (create administrative regions; acceptable compatible/unclear): conflict,
  citing Arts. 236.º, 255.º, 256.º (referendum requirement). Known test
  failure; unchanged from baseline.

Compatible <-> conflict: no confusion on single-label cases (5/5
compatible-expected answered compatible; 0 of 8 conflict-expected answered
compatible). On cases where compatible is acceptable but conflict is not, 27
and 30 were answered conflict. False likely_compatible: none.

Pre-freeze cases (seen before the key was frozen):
- 13: conflict, correct (cites 45.º) — unchanged.
- 15: conflict, correct (cites 209.º) — unchanged.
- 22: compatible, correct (cites 65.º, 70.º, plus 9.º) — unchanged.
- 28: conflict, correct — changed from unclear (both acceptable).
- 30: conflict, wrong — unchanged (known failure).
- 33: unclear, correct (off-topic) — unchanged.

## Future work (not built)

Candidate experiments, each to be pre-registered and run on dev only (the test
set is closed):

- **Query rewriting.** Rewrite the proposal into constitutional vocabulary
  before retrieval (e.g. "aprovação prévia do Governo" → "censura, liberdade
  de imprensa"). Target: the censorship cases (dev 5, 35), where Art. 37.º is
  never retrieved. A related second-pass search on the model's
  missing_information was checked in
  `eval/results/experiments/exp_missing_info_retrieval.md`.
- **Institution name in the chunk prefix (v3).** Add only the título name, and
  only when it is an institution (Presidente da República, Assembleia da
  República, Governo, Tribunais, Tribunal Constitucional, Regiões autónomas,
  Poder local), e.g. `Artigo 123.º, n.º 1 — Presidente da República ›
  Reelegibilidade: ...`. Why: v2_hierarchy helped exactly where a paragraph
  never names the body it regulates (Art. 123.º n.º 1 says "terceiro mandato"
  but not "Presidente"; case 10 paragraph rank 53 → 11), but hurt elsewhere
  because long generic levels are shared by many chunks. Institution names are
  short and discriminative. Watch: Art. 133.º was exactly 512 tokens under v2;
  check the alínea split still keeps every paragraph/hybrid chunk ≤ 512.
