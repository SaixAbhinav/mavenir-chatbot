"""Demo page — the grounded-answer chat. No sidebar, no marketing copy.

Explanations live on the Documentation page, reached via the top-right button.
"""
from __future__ import annotations

import html
import os
import uuid

import requests
import streamlit as st

from nav import docs_page

API = os.environ.get("API_URL", "http://localhost:8000")

REASON_LABEL = {
    "no_relevant_clause": "No relevant clause in the corpus",
    "insufficient": "Retrieved clauses do not contain this",
    "not_answerable_from_standards": "Not answerable from the standards",
    "unverifiable": "Answer could not be verified against the cited text",
}

# (short pill label, full question). Verbatim from the frozen evaluation set so
# each behaves as labelled: one answers with a citation, two decline (one out of
# corpus, one about a live network). A reviewer clicks and sees the difference.
SUGGESTIONS = [
    ("RRC re-establishment",
     "What conditions cause the UE to initiate the RRC connection re-establishment procedure?"),
    ("F1AP information elements",
     "Which information elements does the F1AP UE CONTEXT SETUP REQUEST carry?"),
    ("Cell 4412 dropping calls",
     "Why is cell 4412 dropping calls tonight?"),
]

MARK = (
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="17.5" r="1.9" fill="currentColor" stroke="none"/>'
    '<path d="M8.4 13.9a5 5 0 0 1 7.2 0"/><path d="M5.8 11a9 9 0 0 1 12.4 0"/></svg>'
)

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "history" not in st.session_state:
    st.session_state.history = []
if "pending" not in st.session_state:
    st.session_state.pending = None

# Full-width top bar: brand far left, Learn more boxed on the right.
with st.container(key="topbar"):
    left, right = st.columns([3, 1], vertical_alignment="center")
    left.markdown(
        f'<div class="brand"><span class="brand__mark">{MARK}</span>'
        f'<span class="brand__name">3GPP NOC Copilot</span></div>',
        unsafe_allow_html=True,
    )
    right.page_link(docs_page, label="Learn more  →")


def _ask(text: str) -> None:
    st.session_state.pending = text


def _render_response(body: dict) -> None:
    if body["refused"]:
        reason = REASON_LABEL.get(body["refusal_reason"], "unknown")
        st.markdown(
            f'<div class="reply reply--declined">'
            f'<span class="reply__tag">Declined · {html.escape(reason)}</span>'
            f'<p class="reply__body">{html.escape(body["answer"])}</p></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(body["answer"])
        st.markdown('<div class="sources-label">Sources</div>', unsafe_allow_html=True)
        for citation in body["citations"]:
            st.markdown(
                f'<div class="cite"><span class="cite__id">'
                f'{html.escape(citation["citation"])}</span>'
                f'<blockquote>{html.escape(citation["supporting_quote"])}</blockquote></div>',
                unsafe_allow_html=True,
            )
            with st.expander("Full clause text"):
                st.text(citation["text"])
    # On a refusal the model_id is not reported, so show the gate that fired
    # rather than claiming no model was called (it may have been, at Gate 2).
    tail = f"gate: {body['gate']}" if body["refused"] else (body.get("model_id") or "-")
    st.markdown(f'<p class="meta">{body["latency_ms"]} ms · {html.escape(tail)}</p>',
                unsafe_allow_html=True)


for entry in st.session_state.history:
    with st.chat_message(entry["role"]):
        if entry["role"] == "assistant" and entry.get("body"):
            _render_response(entry["body"])
        else:
            st.markdown(entry["content"])

# Empty state: lift the input up and pin the pills above it, so the two read as
# one centred group in the middle of the screen rather than pinned to the floor.
if not st.session_state.history:
    st.markdown(
        """
        <style>
          [data-testid="stBottom"] { position: fixed; bottom: auto; top: 47%; background: transparent; }
          [data-testid="stBottom"] > div,
          [data-testid="stBottomBlockContainer"] { background: transparent; }
          .st-key-pillbar { bottom: auto; top: calc(47% - 2.4rem); }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="pillbar"):
        columns = st.columns(len(SUGGESTIONS))
        for index, (label, full) in enumerate(SUGGESTIONS):
            columns[index].button(label, key=f"sg_{index}", use_container_width=True,
                                  on_click=_ask, args=(full,))

typed = st.chat_input("Ask about the 5G NR stack, fault supervision or KPIs…")
question = typed or st.session_state.pending
st.session_state.pending = None

if question:
    st.session_state.history.append({"role": "user", "content": question})
    try:
        with st.spinner("Retrieving clauses…"):
            response = requests.post(
                f"{API}/chat",
                json={"question": question, "session_id": st.session_state.session_id},
                timeout=120,
            )
    except Exception as exc:
        st.session_state.history.append(
            {"role": "assistant", "content": f"Could not reach the API: {exc}"})
        st.rerun()

    if response.status_code == 429:
        st.session_state.history.append({"role": "assistant", "content":
            "This demo is receiving a lot of requests right now. Please wait a few seconds and try again."})
    elif response.status_code != 200:
        # The language model is unreachable or rate-limited. Show a clean line,
        # never the provider's raw error payload.
        st.session_state.history.append({"role": "assistant", "content":
            "The language model is temporarily unavailable (it may be rate-limited). Please try again in a moment."})
    else:
        body = response.json()
        st.session_state.history.append(
            {"role": "assistant", "content": body["answer"], "body": body})
    st.rerun()
