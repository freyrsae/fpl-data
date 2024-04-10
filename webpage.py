import streamlit as st
from fpl import plot_diff_from_mean, player_selections_across_league, fetch_events


league_id_key = "league_id"
st.set_page_config(layout="wide")
try:
    league_id_q = st.query_params[league_id_key]
except Exception:
    league_id_q = None
    pass

league_id = st.text_input(label="League ID", value=league_id_q)
st.markdown("You can find your league ID in the URL on the standings page, e.g. for https://fantasy.premierleague.com/leagues/123456/standings/c then 123456 is the league id")

if league_id:
    st.query_params[league_id_key] = league_id
    st.markdown('## Points throughout the season')
    st.bokeh_chart(plot_diff_from_mean(int(league_id)), use_container_width=True)

    st.markdown('## Gameweek player selection')
    events = fetch_events()
    gw = st.selectbox(label='Gameweek', options=events, index=len(events) - 1, )
    st.dataframe(
        player_selections_across_league(int(league_id), gw).sort_values(by=['# owners'], ascending=False),
        use_container_width=True, hide_index=True, column_order=['name', '# owners', 'points', 'captain', 'vice captain', 'starter', 'bench']
    )
