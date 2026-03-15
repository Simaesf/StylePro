"""
examples/streamlit_app.py
--------------------------
Minimal Streamlit demo app with StylePro wired in.

Run:
    cd StylePro
    pip install -e ".[streamlit]"
    streamlit run examples/streamlit_app.py

StylePro integration point is at the top of this file.
As each phase completes, more of the overlay will activate.
"""

import streamlit as st

# ---------------------------------------------------------------------------
# StylePro integration — one call at the very top, before any st.* widgets.
# ---------------------------------------------------------------------------
# Phase 4+ will make inject() functional.  Until then this import verifies
# the package installs and imports correctly.
from stylepro import StreamlitStylePro

_sp = StreamlitStylePro.from_config(role="admin")
_sp.inject()
# In your Streamlit app — no sp.inject() needed
# with open("mytheme.css") as f:
#     st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Demo app content — a representative mix of Streamlit components so the
# editor has varied targets to work with.
# ---------------------------------------------------------------------------

st.set_page_config(page_title="StylePro Demo", layout="wide")

st.title("StylePro — Streamlit Demo")
st.caption("A test bed for the StylePro visual style editor.")

col_left, col_right = st.columns([2, 1])

with col_left:
    st.header("Components")

    st.subheader("Buttons")
    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1:
        st.button("Primary Action")
    with col_b2:
        st.button("Secondary Action")
    with col_b3:
        st.button("Danger Action")

    st.subheader("Text inputs")
    name = st.text_input("Name", placeholder="Enter your name")
    bio = st.text_area("Bio", placeholder="Tell us something...")

    st.subheader("Selection")
    framework = st.selectbox("Framework", ["Streamlit", "Dash", "Angular"])
    rating = st.slider("Rating", 1, 10, 7)
    agree = st.checkbox("I agree to the terms")

    st.subheader("Data display")
    import pandas as pd
    import numpy as np

    df = pd.DataFrame(
        np.random.randn(8, 4),
        columns=["Alpha", "Beta", "Gamma", "Delta"],
    )
    st.dataframe(df, use_container_width=True)

with col_right:
    st.header("Metrics")
    st.metric("Visitors", "1,234", "+12%")
    st.metric("Revenue", "$5,678", "-3%")
    st.metric("Uptime", "99.9%", "0%")

    st.header("Chart")
    chart_data = pd.DataFrame(
        np.random.randn(20, 3),
        columns=["A", "B", "C"],
    )
    st.line_chart(chart_data)

    st.header("Info")
    st.info("This is an info message.")
    st.success("This is a success message.")
    st.warning("This is a warning message.")

st.divider()
st.subheader("Form example")
with st.form("contact_form"):
    email = st.text_input("Email")
    message = st.text_area("Message")
    submitted = st.form_submit_button("Send")
    if submitted:
        st.success(f"Message from {email} received.")
