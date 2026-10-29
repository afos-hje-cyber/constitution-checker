# Constitution Checker

A retrieval-augmented (RAG) app that compares a policy proposal with the
Constitution of the Portuguese Republic (7th revision, 2005) and points to the
articles that may be in tension with it. The interface and answers are in
European Portuguese.

> **Ferramenta educativa. Não constitui aconselhamento jurídico.**
> Só o Tribunal Constitucional pode declarar a inconstitucionalidade de uma norma.

## What it does

1. **Retrieval:** the proposal is embedded with `intfloat/multilingual-e5-small`
   and compared (exact cosine similarity) with the Constitution split into
   chunks (whole articles up to 200 words, longer ones by numbered paragraph);
   the 10 closest chunks are kept.
2. **Assessment:** an LLM (Gemini, free tier) is given only those chunks and is
   instructed to rely on them alone. Its output is always one of three labels —
   *Provavelmente compatível*, *Potencial conflito*, *Incerto / requer análise
   jurídica* — with a summary, its reasoning and the articles it cites. The
   prompt forbids a "constitutional / unconstitutional" verdict; the code flags
   such wording as a warning.
3. **Validation in code:** a cited article (or n.º) that was not among the
   retrieved chunks is rejected; if the text refers to an article that was not
   retrieved, or a label other than "Incerto" has no valid citation, the label
   is changed to "Incerto".
4. **Off-topic input and instructions:** the proposal is passed to the model as
   data, and the prompt tells it to ignore instructions inside it and to answer
   "Incerto" when the text is not a policy proposal. This is a prompt rule, not
   a guarantee; the evaluation has one off-topic and one prompt-injection test
   case, and both were answered "Incerto".
5. **Fallback:** if the LLM is unavailable, a usage cap is reached or no API
   key is configured, the app still shows the most relevant articles
   (retrieval only).

Architecture and module details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run it locally

Requires Python 3.11 and a free Gemini API key from Google AI Studio.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
echo GEMINI_API_KEY=your-key-here > .env
python -m streamlit run app/streamlit_app.py
```

The index and parsed articles are in `data/processed/`, so no rebuild is
needed. The embedding model (~470 MB on disk) is downloaded on first start.
Unit tests: `python -m unittest discover -s tests -t . -v`.

## Evaluation

The answer key (`eval/cases.json`) was frozen before the experiments: 30
development cases used for every design decision, and 21 test cases kept
aside. The final configuration (hybrid chunks, k=10, prompt `assess_v2`) was
pre-registered in `eval/NOTES.md` and run once on the test set: **label
accuracy 86% (18/21)** and **label + reason accuracy 81% (17/21)**, where
"reason" means at least one expected article is cited. The earlier baseline
(k=8, prompt `assess_v1`) scored 95% / 81% on the same test set, so the gains
seen on the development set did not carry over. There were **no false
"likely compatible" answers**. Three of the four remaining errors come from
the relevant article not being retrieved. Every run, decision rule and
regression is logged in [eval/NOTES.md](eval/NOTES.md).

## Known limitations

- When the relevant article is not retrieved, the model can miss the conflict
  or over-flag one based on the wrong articles (test case 27).
- Censorship described without the word "censura" (e.g. "prior approval of
  newspaper articles by the Government") does not retrieve Art. 37.º.
- On "unclear" answers, every article named in the reasoning is added to the
  citation list, so the list mixes supporting citations with articles merely
  considered (the app labels it "Artigos analisados").
- Improvements measured on the development set did not transfer to the test set.
- The evaluation sets are small (30 dev, 21 test cases), and the answer key
  was not reviewed by a lawyer.
- Only the text of the Constitution is used: no case law of the Tribunal
  Constitucional and no other legislation.
- Free-tier Gemini has a daily request limit (the app caps itself and falls
  back to retrieval only), and the model version may change: the app checks
  the version at startup and, if it differs from the evaluated one, shows only
  the most relevant articles (no LLM answers).

## How it was built

I built this project to learn how RAG apps work and how to develop with AI
tools. Built with AI assistance (Claude Code). I made the design decisions, ran and
reviewed the evaluation, and reviewed the code.
