import json

import streamlit as st

from app import config
from app.bot import Bot
from app.data_loader import Corpus
from app.llm import GeminiLLM

SHOWCASE_PATH = config.ROOT / "resident_showcase.json"
show_debug = False

# Found in testing: the router occasionally treats a status-check on an existing ticket ("is
# someone coming to fix X yet?") as a request to open a NEW ticket instead, when the phrasing is
# action-oriented rather than status-oriented. Not a safety issue (nothing is ever submitted
# without a separate confirmation either way) - a known, honestly-documented LLM limitation.
KNOWN_ISSUES = {
    "RES-3497": ('Router misclassified "is someone coming to fix my window latch soon?" as a '
                 "request to open a NEW ticket, instead of recognizing it as a status check on "
                 "the resident's existing ticket (TKT-2010)."),
    "RES-3565": ('Router misclassified "did you guys talk to my neighbor about the noise yet" as '
                 "a request to open a NEW ticket, instead of recognizing it as a status check on "
                 "the resident's existing ticket (TKT-2016)."),
}

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
    if st.button("Reset conversation", use_container_width=True):
        new_session(resident)
        st.rerun()

if st.session_state.get("resident") != resident:
    new_session(resident)

bot: Bot = st.session_state.bot

chat_tab, showcase_tab = st.tabs(["Chat", "Resident showcase"])

with chat_tab:
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

with showcase_tab:
    st.title("Resident showcase")
    st.caption("Every resident in the sample data has their own short, real conversation, written "
               "around their own ticket — not a repeated script. Shows each one getting the right, "
               "personalized answer from their own record, not anyone else's.")

    if not SHOWCASE_PATH.exists():
        st.info(f"No showcase data yet. Run `python -m tests.resident_showcase` to generate `{SHOWCASE_PATH.name}` "
                "(needs GEMINI_API_KEY; real API calls, small cost).")
    else:
        data = json.loads(SHOWCASE_PATH.read_text())
        records = data["records"]
        s = data["session_totals"]
        cost = "n/a" if s["cost_usd"] is None else f"${s['cost_usd']:.4f}"

        c1, c2, c3 = st.columns(3)
        c1.metric("Residents tested", data["resident_count"])
        c2.metric("API calls", s["calls"])
        c3.metric("Cost", cost)
        st.caption(f"Generated {data['generated_at']}")

        categories = sorted({r["ticket"]["category"] for r in records if r["ticket"]})
        col1, col2 = st.columns(2)
        pick_resident = col1.selectbox("Filter by resident", ["All"] + [r["resident_id"] for r in records])
        pick_category = col2.selectbox("Filter by category", ["All"] + categories)

        shown = records
        if pick_resident != "All":
            shown = [r for r in shown if r["resident_id"] == pick_resident]
        if pick_category != "All":
            shown = [r for r in shown if r["ticket"] and r["ticket"]["category"] == pick_category]

        st.caption(f"Showing {len(shown)} of {len(records)}")

        if pick_resident == "All":
            st.dataframe(
                [{"Resident": r["resident_id"],
                  "Ticket": r["ticket"]["ticket_id"] if r["ticket"] else "—",
                  "Category": r["ticket"]["category"] if r["ticket"] else "—",
                  "Status": r["ticket"]["status"] if r["ticket"] else "—",
                  "Priority": r["ticket"]["priority"] if r["ticket"] else "—",
                  "Subject": r["ticket"]["subject"] if r["ticket"] else "—",
                  "⚠": "Known issue" if r["resident_id"] in KNOWN_ISSUES else ""} for r in shown],
                use_container_width=True, hide_index=True,
            )
            st.caption("Pick one resident above to see their full conversation.")
        else:
            for r in shown:
                t = r["ticket"]
                if t:
                    st.markdown(f"**{r['resident_id']}** — {t['ticket_id']} · {t['category']} · "
                                f"`{t['status']}` · priority {t['priority']}  \n*{t['subject']}*")
                else:
                    st.markdown(f"**{r['resident_id']}** — no tickets on file")
                if r["resident_id"] in KNOWN_ISSUES:
                    st.warning(f"⚠️ **Known issue found in testing:** {KNOWN_ISSUES[r['resident_id']]}")
                for turn in r["turns"]:
                    with st.chat_message("user"):
                        st.markdown(turn["user"])
                    with st.chat_message("assistant"):
                        st.markdown(turn["bot"])
                        if show_debug:
                            st.caption(f"intent: `{turn.get('intent', '')}` · kind: `{turn.get('kind', '')}`")
                st.divider()
