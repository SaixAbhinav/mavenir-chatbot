"""Shared page registry.

Defined once and imported by both the router (app.py) and the pages, so that
st.page_link targets the same st.Page object st.navigation registered — passing
a bare file-path string instead produces a mismatched href that does not route.
"""
from __future__ import annotations

import streamlit as st

# The default page is served at "/" only; giving it a url_path makes that path
# a 404. Only the non-default page needs an explicit url_path.
demo_page = st.Page("views/demo.py", title="Demo", default=True)
docs_page = st.Page("views/documentation.py", title="Documentation", url_path="docs")
