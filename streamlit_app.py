import streamlit as st

from app import config
from app.bot import Bot
from app.data_loader import Corpus
from app.llm import GeminiLLM

st.set_page_config(page_title="Resident Support Assistant", page_icon="🏠", layout="wide")


@st.cache_resource
def get_llm() -> GeminiLLM:
    return GeminiLLM()


def new_session(resident: str) -> None:
    corpus = Corpus.load(config.DATA_DIR, config.RUNTIME_TICKETS)
    st.session_state.corpus = corpus
    st.session_state.bot = Bot(resident, corpus, get_llm())
    st.session_state.resident = resident
    st.session_state.messages = []


corpus0 = Corpus.load(config.DATA_DIR, config.RUNTIME_TICKETS)
residents = sorted(corpus0.known_resident_ids())

with st.sidebar:
    st.header("Session")
    resident = st.selectbox("Signed in as (session identity)", residents,
                            help="The resident is fixed by the session, never by what is typed in chat.")
    show_debug = st.toggle("Show debug info", value=False)
    if st.button("Reset conversation", use_container_width=True):
        new_session(resident)
        st.rerun()
    st.caption(f"Main: `{config.MAIN_MODEL}`  \nRouter: `{config.ROUTER_MODEL}`  \nJudge: {'on' if config.USE_JUDGE else 'off'}")

if st.session_state.get("resident") != resident:
    new_session(resident)

bot: Bot = st.session_state.bot

with st.sidebar:
    st.subheader("Your tickets")
    tickets = bot.corpus.tickets_for(resident)
    if not tickets:
        st.write("No tickets.")
    for t in tickets:
        new = t in bot.corpus.runtime_tickets()
        st.markdown(f"**{t['ticket_id']}**{' 🆕' if new else ''} · {t['category']} · `{t['status']}`  \n{t['subject']}")
    st.subheader("Pending action")
    p = bot.pending
    if not p:
        st.write("None")
    else:
        st.write(f"**{p.type}** ({'awaiting confirmation' if p.awaiting else 'collecting details'})")
        st.json(p.fields)

st.title("🏠 Resident Support Assistant")
st.caption("Ask about rooms, prices, house rules, your tickets, or raise a request.")

if not st.session_state.messages:
    st.session_state.messages.append({"role": "assistant", "content": "Hi! How can I help with your stay today?"})

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if show_debug and m.get("meta"):
            st.caption(m["meta"])

if prompt := st.chat_input("Type your message"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                r = bot.handle(prompt)
                text, meta = r.text, f"intent: `{r.intent}` · kind: `{r.kind}`"
            except Exception as e:
                text, meta = "Sorry, something went wrong. Please try again.", f"error: {e}"
        st.markdown(text)
        if show_debug:
            st.caption(meta)
    st.session_state.messages.append({"role": "assistant", "content": text, "meta": meta})
    st.rerun()
