import streamlit as st
from fpl import plot_diff_from_mean

st.set_page_config(layout="wide")
try:
    league_id_q = st.query_params["league_id"]
except Exception:
    league_id_q = None
    pass

league_id = st.text_input(label="League ID", value=league_id_q)

if league_id:
    st.bokeh_chart(plot_diff_from_mean(int(league_id)), use_container_width=True)

