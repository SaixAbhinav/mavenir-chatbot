"""Entry point / router. Two pages, no sidebar:

  - Demo          the grounded-answer chat (this is the product)
  - Documentation what the system is and how it decides to answer or decline

Shared pastel styling is injected here so it applies to both pages.
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="3GPP NOC Chatbot", page_icon="📡", layout="centered")

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap');

      /* Dark-only. The palette's darkest colour (#41444b) is the base; the beige
         (#cabfab) is the accent so it reads against it. */
      /* Dark-only. A darker base so it reads as dark; #41444b is the elevated
         surface (cards, input, header), #52575d lifts one step more. */
      :root {
        --bg:        #2b2d33;
        --surface:   #41444b;
        --text:      #dfd8c8;
        --muted:     #cabfab;
        --line:      #5a5e66;

        --accent:      #cabfab;
        --accent-soft: #52575d;
        --accent-ink:  #dfd8c8;

        --refuse:      #cabfab;
        --refuse-soft: #cabfab;
        --refuse-ink:  #41444b;

        --r-card: 16px;
        --r-ctrl: 12px;
        --shadow: 0 10px 34px -14px rgba(0, 0, 0, .5);
      }

      /* No sidebar, and hide Streamlit's dev header (Deploy / menu) so it does
         not collide with our own top bar. */
      [data-testid="stSidebar"], [data-testid="stSidebarNav"],
      [data-testid="stSidebarCollapsedControl"], [data-testid="stHeader"] { display: none !important; }

      .stApp { background: var(--bg); }
      .block-container { max-width: 780px; padding-top: 4.6rem; }
      html, body, [class*="css"], .stMarkdown, p, li, label { font-family: 'Outfit', system-ui, sans-serif; }
      h1, h2, h3, h4 { font-family: 'Outfit', system-ui, sans-serif !important; }

      .brand { display: flex; align-items: center; gap: .55rem; }
      .brand__mark { color: var(--accent); display: inline-flex; }
      .brand__name { font-size: 1.3rem; font-weight: 700; letter-spacing: -.02em; color: var(--text); }

      /* Sticky full-width top bar (st.container(key="topbar")) */
      .st-key-topbar { position: fixed; top: 0; left: 50%; transform: translateX(-50%);
        width: 100vw; box-sizing: border-box; padding: .55rem 2.5rem; z-index: 100;
        background: var(--bg); border-bottom: 1px solid var(--line); }
      .st-key-topbar [data-testid="stHorizontalBlock"] { align-items: center; }

      /* Learn more / Back links as a boxed button, right-aligned */
      [data-testid="stPageLink"] { display: flex; justify-content: flex-end; }
      [data-testid="stPageLink"] a {
        color: var(--accent-ink) !important; font-weight: 600; font-family: 'Outfit', sans-serif;
        border-radius: var(--r-card); border: 1px solid var(--accent); background: var(--accent-soft);
        padding: .4rem .9rem; box-shadow: var(--shadow); transition: transform .18s ease; }
      [data-testid="stPageLink"] a:hover { transform: translateY(-1px); }
      [data-testid="stPageLink"] p { font-size: .9rem; }

      /* Pills pinned just above the docked chat input (st.container(key="pillbar")) */
      .st-key-pillbar { position: fixed; left: 50%; transform: translateX(-50%);
        bottom: 7.4rem; width: min(700px, 92vw); z-index: 40; }
      .st-key-pillbar [data-testid="stHorizontalBlock"] { gap: .5rem; }

      .suggest-label { font-size: .78rem; font-weight: 600; color: var(--muted);
        text-align: center; margin: .2rem 0 .5rem; }

      /* Example suggestions as compact pills (descendant selector so it also
         wins when Streamlit nests the button under a tooltip wrapper). */
      .stButton button {
        width: 100%; white-space: normal; line-height: 1.25;
        background: var(--accent-soft); color: var(--accent-ink);
        border: 1px solid var(--line); border-radius: 999px;
        padding: .5rem .9rem; font-family: 'Outfit', sans-serif; font-size: .85rem; font-weight: 600;
        transition: transform .18s ease, border-color .18s ease; }
      .stButton button:hover { border-color: var(--accent); transform: translateY(-2px); }
      .stButton button:active { transform: translateY(0); }

      [data-testid="stChatMessage"] {
        background: transparent; border: 0; box-shadow: none; padding: .2rem .3rem; }

      .reply--declined .reply__tag { display: inline-flex; align-items: center;
        font-size: .74rem; font-weight: 700; padding: .28rem .6rem; border-radius: 999px;
        margin-bottom: .5rem; background: var(--refuse-soft); color: var(--refuse-ink);
        border: 1px solid var(--refuse); }
      .reply--declined .reply__body { color: var(--text); margin: 0; line-height: 1.55; }

      .sources-label { font-size: .78rem; font-weight: 700; color: var(--muted);
        text-transform: uppercase; letter-spacing: .06em; margin: .3rem 0 .5rem; }
      .cite { border: 1px solid var(--line); border-left: 3px solid var(--accent);
        border-radius: var(--r-ctrl); padding: .6rem .8rem; margin-bottom: .5rem; background: var(--surface); }
      .cite__id { font-family: ui-monospace, 'SFMono-Regular', monospace; font-size: .8rem;
        color: var(--accent-ink); font-weight: 600; }
      .cite blockquote { margin: .35rem 0 0; padding: 0; border: 0; color: var(--text);
        font-size: .92rem; line-height: 1.5; opacity: .92; }
      .meta { color: var(--muted); font-size: .78rem; margin-top: .3rem; }

      /* Tint the chat input to the palette. Background only (no border/radius) to
         avoid the outline misalignment that custom borders caused here. */
      [data-testid="stChatInput"],
      [data-testid="stChatInput"] > div { background: var(--surface) !important; }
      [data-testid="stChatInput"] textarea { color: var(--text) !important; }

      /* Documentation page */
      .doc h2 { font-size: 1.25rem; font-weight: 700; color: var(--text); margin: 1.4rem 0 .4rem; }
      .doc p, .doc li { color: var(--text); line-height: 1.6; }
      .doc .lead { color: var(--muted); font-size: 1.05rem; line-height: 1.55; }
      .stat-row { display: flex; flex-wrap: wrap; gap: .5rem; margin: .6rem 0; }
      .stat { border: 1px solid var(--line); border-radius: var(--r-ctrl); background: var(--surface);
        padding: .5rem .8rem; box-shadow: var(--shadow); }
      .stat b { display: block; font-size: 1.2rem; color: var(--accent-ink); font-weight: 700; }
      .stat span { font-size: .78rem; color: var(--muted); }

      @media (prefers-reduced-motion: reduce) {
        .stButton > button { transition: none; }
        .stButton > button:hover { transform: none; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)

from nav import demo_page, docs_page  # noqa: E402  (must follow set_page_config)

st.navigation([demo_page, docs_page], position="hidden").run()
