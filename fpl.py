import cachetools.func
import requests
from pprint import pprint
from dataclasses import dataclass
from bokeh.plotting import figure
from bokeh.models import HoverTool
from bokeh.palettes import Category20_20
import pandas as pd
from pandas import DataFrame
from bokeh.models import ColumnDataSource

base_url = 'https://fantasy.premierleague.com/api/'
cache_ttl = 60*2
cache_maxsize = 128

@dataclass
class Entry:
    team_id: int
    name: str
    player_name: str
    rank: int

def entry_from_standings(standings) -> Entry:
    return Entry(
        team_id=standings['entry'],
        name=standings['entry_name'],
        player_name=standings["player_name"],
        rank=standings['rank']
    )

@dataclass
class LeagueInfo:
    id: int
    name: str
    entries: list[Entry]

def fetch_league_info(league_id: int) -> LeagueInfo:
    r = requests.get(base_url + f"leagues-classic/{league_id}/standings/").json()
    return LeagueInfo(
        id=r["league"]['id'],
        name=r["league"]["name"],
        entries=[entry_from_standings(e) for e in r['standings']['results']]
    )

@cachetools.func.ttl_cache(maxsize=cache_maxsize, ttl=cache_ttl)
def fetcht_current_gameweek() -> int:
    return min([e['id'] for e in fetch_bootstrap_static()['events'] if e['is_current']])

@cachetools.func.ttl_cache(maxsize=cache_maxsize, ttl=cache_ttl)
def fetch_bootstrap_static():
    r = requests.get(base_url + f"bootstrap-static/").json()
    # pprint(r['events'], indent=2, depth=3, compact=True)
    return r

@cachetools.func.ttl_cache(maxsize=cache_maxsize, ttl=cache_ttl)
def fetch_events() -> list[int]:
    return [e['id'] for e in fetch_bootstrap_static()['events'] if e['finished'] or e['is_current']]

# fpl api returns value as ints, so e.g. 4.5M is returned as 45
def format_value(v: int) -> str:
    return "{:.1f}".format(v/10.0)

@dataclass
class Week:
    event: int
    total_points: int
    points: int
    points_on_bench: int
    bank: str
    value: str

@cachetools.func.ttl_cache(maxsize=cache_maxsize, ttl=cache_ttl)
def fetch_current_season(team_id: int) -> list[Week]:
    r = requests.get(base_url + f"entry/{team_id}/history/").json()
    # pprint(r, indent=2, depth=3, compact=True)
    return [Week(
                event=w['event'],
                total_points=w['total_points'],
                points=w['points'],
                points_on_bench=w['points_on_bench'],
                bank=format_value(w['bank']),
                value=format_value(w['value'])
            ) for w in r['current']]

@cachetools.func.ttl_cache(maxsize=cache_maxsize, ttl=cache_ttl)
def element_names() -> dict[int, str]:
    return {e['id']: e['web_name'] for e in fetch_bootstrap_static()['elements']}

@dataclass
class Pick:
    element: int
    is_captain: bool
    is_vice_captain: bool
    multiplier: int

@cachetools.func.ttl_cache(maxsize=cache_maxsize, ttl=cache_ttl)
def fetch_picks(manager_id: int, event_id: int) -> list[Pick]:
    r = requests.get(base_url + f"entry/{manager_id}/event/{event_id}/picks/").json()
    # pprint(r,  indent=2, depth=3, compact=True)
    return [Pick(
                element=p['element'],
                is_captain=p['is_captain'],
                is_vice_captain=p['is_vice_captain'],
                multiplier=p['multiplier'],
            ) for p in r['picks']]

def prepend_to_events_length(ls: list, n: int, default_value = 0):
    return [default_value] * (n - len(ls)) + ls

@cachetools.func.ttl_cache(maxsize=cache_maxsize, ttl=cache_ttl)
def player_points(event_id: int) -> dict[int, int]:
    r = requests.get(base_url + f"event/{event_id}/live/").json()
    # pprint(r, indent=2, depth=3, compact=True)
    return {e['id']: e['stats']['total_points']for e in r['elements']}

@cachetools.func.ttl_cache(maxsize=cache_maxsize, ttl=cache_ttl)
def player_selections_across_league(league_id: int, gw: int):
    league_info = fetch_league_info(league_id)
    names = {}
    ownership = {}
    points = {}
    player_selections = {}
    captain_selections = {}
    vice_captain_selections = {}
    bench_selections = {}
    for entry in league_info.entries:
        current_picks = fetch_picks(entry.team_id, gw)
        for pick in current_picks:

            if not ownership.get(pick.element):
                ownership[pick.element] = 0
            ownership[pick.element] += 1

            if (not names.get(pick.element)):
                names[pick.element] = element_names()[pick.element]
            if (not points.get(pick.element)):
                points[pick.element] = player_points(gw)[pick.element]

            if pick.is_captain:
                add_to_dict_list(captain_selections, pick.element, entry.name)
            elif pick.is_vice_captain:
                add_to_dict_list(vice_captain_selections, pick.element, entry.name)
            elif pick.multiplier == 1:
                add_to_dict_list(player_selections, pick.element, entry.name)
            elif pick.multiplier == 0:
                add_to_dict_list(bench_selections, pick.element, entry.name)

    df = pd.concat([pd.Series(d) for d in [captain_selections, vice_captain_selections, player_selections, bench_selections, names, points, ownership]], axis=1)
    df.columns = ['captain', 'vice captain', 'starter', 'bench', 'name', 'points', '# owners']
    return df

def add_to_dict_list(d: dict, id: int, name: str):
    if(d.get(id)):
        d[id].append(name)
    else:
        d[id] = [name]

@cachetools.func.ttl_cache(maxsize=cache_maxsize, ttl=cache_ttl)
def plot_diff_from_mean(league_id: int):
    league_info = fetch_league_info(league_id)

    # Sample data for plotting
    x = fetch_events()
    n_events = len(x)

    p = figure(title=league_info.name, x_axis_label='Week', y_axis_label='Total points diff from mean', width=1400,
               height=900)
    total_points_dict = {}

    for entry in league_info.entries:
        season = fetch_current_season(entry.team_id)
        total_points_dict[entry.name] = prepend_to_events_length([w.total_points for w in season], n_events)

    df = DataFrame(total_points_dict)
    df['weekly_mean'] = df.mean(axis=1)

    for entry in league_info.entries:
        season = fetch_current_season(entry.team_id)
        color = Category20_20[entry.rank%20]
        diff_from_mean = df[entry.name] - df['weekly_mean'].round(0)
        p.line(x, diff_from_mean, legend_label=entry.name, line_width=2, color=color)
        source = ColumnDataSource(data=dict(
            x=x,
            y=diff_from_mean,
            total_points=prepend_to_events_length([w.total_points for w in season], n_events),
            weekly_points=prepend_to_events_length([w.points for w in season], n_events),
            points_on_bench=prepend_to_events_length([w.points_on_bench for w in season], n_events),
            value=prepend_to_events_length([w.value for w in season], n_events),
            bank=prepend_to_events_length([w.bank for w in season], n_events)
        ))
        p.circle(x="x", y="y", source=source, size=10, color=color)

    TOOLTIPS = [
        ("Total points", "@total_points"),
        ("Points for Week", "@weekly_points"),
        ("Bench Points", "@points_on_bench"),
        ("Team Value", "@value"),
        ("Bank", "@bank"),
    ]
    hover = HoverTool(tooltips=TOOLTIPS)
    p.add_tools(hover)
    p.legend.location = "top_left"
    return p

if __name__ == '__main__':
    breidholt_league_id = 1138337
    stebbi_league = 134779
    ph_team_id = 3269989
    pprint(fetch_bootstrap_static()['events'], indent=2, depth=3, compact=True)