"""Shared page registry, imported by both app.py and the pages so st.page_link
targets the same st.Page object st.navigation registered."""
from __future__ import annotations

import streamlit as st

# The default page serves at "/"; only the non-default page needs a url_path.
demo_page = st.Page("views/demo.py", title="Demo", default=True)
docs_page = st.Page("views/documentation.py", title="Documentation", url_path="docs")
