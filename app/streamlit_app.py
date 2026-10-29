"""Streamlit app: compare a policy proposal with the Portuguese Constitution.

Run:  .venv\\Scripts\\python -m streamlit run app/streamlit_app.py --server.address localhost

Everything the user sees is in European Portuguese. Heavy resources (embedding
model, index, LLM client) are loaded once per server process.
"""

import os
import re
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st  # noqa: E402

# Names read from the environment by src/ (the key by rag/llm.py, the caps by
# common/config.py). Must run before `config` is imported.
SECRET_NAMES = ("GEMINI_API_KEY", "DAILY_CAP", "SESSION_CAP")


def secrets_to_env():
    """Streamlit Cloud: copy secrets into environment variables.

    Locally there is usually no .streamlit/secrets.toml, so nothing is copied
    and the key comes from .env (load_dotenv never overrides a value already set).
    """
    try:
        secrets = {name: st.secrets[name] for name in SECRET_NAMES if name in st.secrets}
    except FileNotFoundError:   # no secrets file at all (StreamlitSecretNotFoundError)
        return
    for name, value in secrets.items():
        os.environ.setdefault(name, str(value))


secrets_to_env()

from common import config  # noqa: E402
from rag.assess import assess, chunk_block, get_client  # noqa: E402
from common.embeddings import MODEL as EMBEDDING_MODEL  # noqa: E402
from ingest.chunking import label, load_articles  # noqa: E402
from rag.llm import (LLMOutputError, LLMUnavailableError, MissingAPIKeyError,  # noqa: E402
                     ModelStatus)
from rag.rerank import RerankerMismatchError, load_reranker  # noqa: E402
from rag.retrieve import IndexMismatchError, load_index, retrieve  # noqa: E402
from common.usage import UsageLimitError, default_daily_counter, make_guard  # noqa: E402

DISCLAIMER = ("Ferramenta educativa. Não constitui aconselhamento jurídico. Só o Tribunal "
              "Constitucional pode declarar a inconstitucionalidade de uma norma.")

EXAMPLES = [
    "Reintroduzir a pena de morte",
    "Proibir greves nos transportes públicos",
    "Aumentar o investimento público em energias renováveis",
]

# Neutral colours on purpose: no green "approved" signal.
BADGE_COLOURS = {
    "likely_compatible": "#1d4ed8",    # blue
    "potential_conflict": "#b45309",   # amber
    "unclear": "#4b5563",              # grey
}

FALLBACK_MESSAGE = ("A análise automática está temporariamente indisponível. "
                    "Eis os artigos mais relevantes:")
FALLBACK_REASONS = {
    "session": "Atingiu o limite de análises novas nesta sessão ({cap}).",
    "daily": ("Foi atingido o limite diário de análises da aplicação. O limite renova-se "
              "à meia-noite da costa oeste dos EUA (por volta das 8h00 em Portugal continental)."),
    "unavailable": "O serviço de IA não respondeu. Tente novamente dentro de alguns minutos.",
    "version": "A versão do modelo mudou; por agora são mostrados apenas os artigos mais relevantes.",
    "no_key": ("A chave da API não está configurada; são mostrados apenas os artigos mais "
               "relevantes."),
}

# Model status -> fallback reason, for the statuses where the LLM is not used at all.
LLM_OFF = {"mismatch": "version", "no_key": "no_key"}


# ------------------------------------------------------------------ helpers

def safe(text):
    """Show model/user text literally: escape Markdown, LaTeX ($) and HTML."""
    text = re.sub(r"([\\`*_\[\]<>#|~$])", r"\\\1", text)
    return text.replace("\n", "  \n")


def cite_header(article_number, n=None, alinea=None, title=None):
    text = f"Artigo {article_number}.º"
    if n:
        text += f", n.º {n}"
    if alinea:
        text += f", alínea {alinea})"
    return f"{text} — {title}" if title else text


def article_markdown(article, cited_n=None):
    """Full article text from articles.json; the cited n.º is marked with ▶."""
    lines = []
    for p in article["paragraphs"]:
        body = safe(p["text"])
        if p["n"] is None:
            lines.append(body)
        else:
            mark = "▶ " if p["n"] == cited_n else ""
            lines.append(f"{mark}**{p['n']}.** {body}")
    return "\n\n".join(lines)


def badge(label_code):
    colour = BADGE_COLOURS[label_code]
    name = config.LABELS[label_code]
    return (f'<span style="background:{colour};color:#fff;padding:0.3rem 0.8rem;'
            f'border-radius:1rem;font-weight:600;">{name}</span>')


# ---------------------------------------------------------------- resources

@st.cache_resource(show_spinner="A carregar o modelo e o índice…")
def load_resources():
    """Load once per process and run the startup checks.

    Raises IndexMismatchError if a check fails (not cached, so the next page
    load tries again). "model_status" gives "ok", "unreachable", "mismatch"
    or "no_key"; an "unreachable" result is checked again later (ModelStatus).
    """
    meta = load_index(config.RETRIEVAL_STRATEGY)[2]     # also loads the embedding model
    if config.RERANK_ENABLED:                            # optional stage, off by default
        load_reranker()                                  # refuses a mismatched revision
    try:
        check = get_client().verify_model               # models.get: no generation quota used
    except MissingAPIKeyError:                          # no .env / no secret: retrieval only
        check = lambda: "no_key"                        # noqa: E731
    return {
        "prefix_version": meta["prefix_version"],
        "model_status": ModelStatus(check),
        "articles": {a["number"]: a for a in load_articles() if a["number"] is not None},
        "daily": default_daily_counter(),
    }


def run_analysis(proposal, res):
    """Assess the proposal, or fall back to retrieval only. Returns a dict for display."""
    status = res["model_status"].get()
    if status in LLM_OFF:   # model changed since the evaluation, or no key: no LLM answers
        hits = retrieve(proposal, config.RETRIEVAL_STRATEGY, config.RETRIEVAL_K)
        return {"kind": "fallback", "reason": LLM_OFF[status], "proposal": proposal, "hits": hits}
    guard = make_guard(res["daily"], st.session_state, config.SESSION_CAP)   # one per question
    try:
        with st.spinner("A analisar a proposta…"):
            return {"kind": "assessment", "out": assess(proposal, before_api_call=guard)}
    except UsageLimitError as error:
        reason = error.kind
    except (LLMUnavailableError, LLMOutputError):
        reason = "unavailable"
    hits = retrieve(proposal, config.RETRIEVAL_STRATEGY, config.RETRIEVAL_K)
    return {"kind": "fallback", "reason": reason, "proposal": proposal, "hits": hits}


# ------------------------------------------------------------------ display

def show_sidebar(res):
    with st.sidebar:
        st.header("Como funciona")
        st.markdown(
            "1. **Pesquisa:** a proposta é comparada com os 296 artigos da Constituição "
            f"(7.ª revisão, 2005) e são escolhidos os {config.RETRIEVAL_K} excertos mais próximos.\n"
            "2. **Análise:** um modelo de linguagem avalia a proposta usando apenas esses excertos.\n"
            "3. **Validação no código:** cada citação é confirmada contra os excertos recuperados; "
            "se não estiver lá, é rejeitada e a etiqueta pode passar a «Incerto».\n"
            "4. **Resultado:** uma de três etiquetas, sempre com os artigos citados.")
        st.header("Limitações")
        st.markdown(
            "- A pesquisa pode não encontrar todos os artigos relevantes.\n"
            "- Não considera a jurisprudência do Tribunal Constitucional nem outra legislação.\n"
            "- O modelo pode errar: confirme sempre no texto dos artigos citados.")
        st.header("Privacidade")
        st.markdown("O texto é enviado para a API Google Gemini. Não introduza dados pessoais.")
        st.header("Modelo")
        st.markdown(f"- Linguagem: `{config.MODEL}` (versão `{config.MODEL_VERSION}`)\n"
                    f"- Pesquisa: `{EMBEDDING_MODEL['name']}`\n"
                    f"- Instruções: `{config.PROMPT_VERSION}`")


def show_hit_list(hits, res):
    for i, h in enumerate(hits, start=1):
        header, body = chunk_block(h, res["prefix_version"]).split("\n", 1)
        with st.expander(f"{i}. {header.strip('[]')}  ·  semelhança {h['score']:.3f}"):
            st.markdown(safe(body))


def show_fallback(result, res):
    st.warning(FALLBACK_MESSAGE)
    st.caption(FALLBACK_REASONS[result["reason"]].format(cap=config.SESSION_CAP))
    show_hit_list(result["hits"], res)


def show_assessment(out, res):
    r = out["result"]
    st.markdown(badge(r["label"]), unsafe_allow_html=True)   # fixed HTML, no user text
    st.markdown(f"#### Resumo\n{safe(r['summary'])}")
    st.markdown(f"#### Raciocínio\n{safe(r['reasoning'])}")
    if r["missing_information"]:
        st.markdown(f"#### Informação em falta\n{safe(r['missing_information'])}")

    # On "unclear" the list holds the articles the model weighed (validation
    # auto-adds every article named in the reasoning), not supporting citations.
    is_unclear = r["label"] == "unclear"
    st.markdown("#### Artigos analisados" if is_unclear else "#### Artigos citados")
    if not r["citations"]:
        st.caption("Nenhum artigo analisado." if is_unclear else "Nenhum artigo citado.")
    for c in r["citations"]:
        article = res["articles"].get(c["article"])
        title = article["title"] if article else None
        st.markdown(f"**{cite_header(c['article'], c.get('n'), c.get('alinea'), title)}**  \n"
                    f"{safe(c['explanation'])}")
        if article:
            with st.expander(f"Ver o texto do artigo {c['article']}.º"):
                st.markdown(article_markdown(article, c.get("n")))

    with st.expander(f"Artigos consultados ({len(out['retrieved'])})"):
        for i, h in enumerate(out["retrieved"], start=1):
            alineas = tuple(h["alineas"].split("-")) if h["alineas"] else None
            name = label({"number": h["article"]}, h["paragraph"], alineas)
            st.markdown(f"{i}. {name} — {safe(h['title'])} · semelhança `{h['score']:.3f}`")

    with st.expander("Detalhes técnicos"):
        u = out["usage"]
        st.markdown(
            f"- Modelo: `{out['model']}` (versão `{out['model_version']}`; "
            f"a API indicou `{out['response_model_version']}`)\n"
            f"- Instruções: `{out['prompt_version']}` · pesquisa: `{out['retrieval']['strategy']}`, "
            f"k={out['retrieval']['k']}, prefixo `{out['retrieval']['prefix_version']}`\n"
            f"- Tokens: entrada {u['input_tokens']}, saída {u['output_tokens']}, "
            f"total {u['total_tokens']}\n"
            f"- Resposta em cache: {'sim (sem pedido à API)' if out['cached'] else 'não'} · "
            f"tentativas: {out['attempts']} · tempo: {out['seconds']} s")
        st.markdown("**Notas de validação**")
        st.json(out["validation_notes"])
        st.markdown("**Citações rejeitadas**")
        st.json(out["rejected_citations"])
        st.markdown("**Referências rejeitadas**")
        st.json(out["rejected_references"])


# --------------------------------------------------------------------- page

def fill_example(text):
    st.session_state["proposal"] = text


def main():
    st.set_page_config(page_title="Comparador Constitucional", page_icon="⚖️", layout="centered")
    st.session_state.setdefault("new_analyses", 0)
    st.session_state.setdefault("proposal", "")

    try:
        res = load_resources()
    except (IndexMismatchError, RerankerMismatchError, FileNotFoundError) as error:
        st.title("Comparador Constitucional")
        st.error("A aplicação não pode arrancar: a verificação de configuração falhou.\n\n"
                 f"`{type(error).__name__}`: {error}")
        st.stop()

    show_sidebar(res)
    st.title("Comparador Constitucional")
    st.markdown("Compare uma proposta de política pública com a Constituição da República "
                "Portuguesa e veja que artigos podem estar em causa.")
    status = res["model_status"].get()
    if status == "unreachable":
        st.warning("Não foi possível contactar o serviço de IA. A análise automática pode "
                   "falhar; nesse caso são mostrados apenas os artigos mais relevantes.")
    elif status in LLM_OFF:
        st.warning(FALLBACK_REASONS[LLM_OFF[status]])

    st.markdown("**Exemplos:**")
    cols = st.columns(len(EXAMPLES))
    for col, text in zip(cols, EXAMPLES):
        col.button(text, on_click=fill_example, args=(text,), use_container_width=True)

    st.text_area("Proposta", key="proposal", max_chars=config.MAX_PROPOSAL_CHARS, height=120,
                 placeholder="Escreva aqui a proposta, por exemplo: «Proibir greves nos "
                             "transportes públicos».")
    left = config.SESSION_CAP - st.session_state["new_analyses"]
    st.caption(f"Análises novas disponíveis nesta sessão: {left} de {config.SESSION_CAP}. "
               "Propostas já analisadas antes não contam para o limite.")
    clicked = st.button("Analisar", type="primary")

    st.info(DISCLAIMER)

    if clicked:
        proposal = st.session_state["proposal"].strip()
        if not proposal:
            st.warning("Escreva uma proposta antes de carregar em «Analisar».")
        else:
            st.session_state["last"] = run_analysis(proposal, res)
            st.rerun()   # redraw so the usage counter above reflects this analysis

    result = st.session_state.get("last")
    if result:
        if result["kind"] == "assessment":
            st.markdown(f"**Proposta analisada:** {safe(result['out']['proposal'])}")
            show_assessment(result["out"], res)
        else:
            st.markdown(f"**Proposta:** {safe(result['proposal'])}")
            show_fallback(result, res)


main()
