# https://dashboard.render.com/web/srv-d3sq1lhr0fns738mcp9g

import re
from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import copy

app = Flask(__name__)

@app.route('/nba/schedule/<team_acronym>', methods=['GET'])
def get_nba_team_schedule(team_acronym):
    nba_teams_data = fetch_standings_data(NBA_TEAMS_DATA)
    my_team_data = [team for team in nba_teams_data if team.get("espn-acronym") == team_acronym.upper()][0]
    schedule = fetch_team_schedule_data(nba_teams_data, my_team_data)
    resp = {'upcoming_schedule': schedule}

    if request.args.get('nbapiformat') == 'true':
        resp = convert_to_nba_api_format(resp, nba_teams_data, my_team_data)

    return jsonify(resp)

def fetch_standings_data(nba_teams_data):
    soup = fetch_soup(f'https://www.espn.com/nba/standings/_/group/conference')
    if not soup:
        return jsonify({'error': f'Failed to parse standings: {url}'}), 500
    tables = soup.find_all('tbody', class_='Table__TBODY')

    def matches_letters_prefix(text, target, length=3):
        return re.sub(r'[^a-zA-Z]', '', text)[:length].lower() == target.lower()

    for i, table in enumerate(tables):
        conf = 'W' if i > 1 else 'E'
        for conf_rank, row in enumerate(table.find_all('tr')):
            if i % 2 == 0:
                team_data = [team for team in nba_teams_data if matches_letters_prefix(row.text, team.get("espn-acronym"), 2) or matches_letters_prefix(row.text, team.get("espn-acronym"), 3)][0]
                team_data['conf'] = conf
                team_data['conf_rank'] = conf_rank + 1
            else:
                team_data = [team for team in nba_teams_data if team.get("conf") == conf and team.get("conf_rank") == conf_rank + 1][0]
                win_cell, loss_cell = row.find_all('td')[:2]
                team_data['record-wins'] = win_cell.text
                team_data['record-losses'] = loss_cell.text

    return nba_teams_data

def fetch_team_schedule_data(nba_teams_data, my_team_data):
    soup = fetch_soup(f'https://www.espn.com/nba/team/schedule/_/name/{my_team_data.get("acronym")}/{my_team_data.get("url-name")}')
    if not soup:
        return jsonify({'error': f'Failed to parse schedule: {url}'}), 500
    table = soup.find('tbody', class_='Table__TBODY')

    schedule_data = []
    col_names = None
    pre_header_row_found = False
    for row in table.find_all('tr'):
        if col_names is None: 
            if 'Table_Headers' in row.find('td')['class']:
                if not pre_header_row_found:
                    pre_header_row_found = True
                else:
                    col_names = [header.text.strip() for header in row.find_all('td')]
            continue

        schedule_data.append(format_game_data(nba_teams_data, my_team_data, col_names, row.find_all('td')))

    return schedule_data

def fetch_soup(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return None

    return BeautifulSoup(response.text, 'html.parser')

def format_game_data(nba_teams_data, my_team_data, col_names, game_cells):
    game_data = {col_names[i]: cell for i, cell in enumerate([col.text.strip() for col in game_cells])}

    game_data['datetime_utc'] = convert_to_utc(convert_date(game_data['DATE']), game_data['TIME'])

    tv_cell = game_cells[col_names.index('TV')]
    if tv_cell.text == '':
        for figure in tv_cell.find_all('figure'):
            network = [cls for cls in figure['class'] if cls.startswith('network-')]
            game_data['TV'] += network[0].replace('network-', '').upper()
    if 'ABC' in game_data['TV']:
        game_data['channel'] = 'ABC'
    elif 'ESPN' in game_data['TV']:
        game_data['channel'] = 'ESPN'
    elif 'NBC' in game_data['TV']:
        game_data['channel'] = 'NBC'
    elif 'Peacock' in game_data['TV']:
        game_data['channel'] = 'Peacock'
    elif game_data['TV'] in ['Prime Video', 'NBA TV']:
        game_data['channel'] = game_data['TV']
    else:
        game_data['channel'] = 'League Pass'

    game_data['my_team'] = copy.deepcopy(my_team_data)
    game_data['my_team']['is_home'] = not game_data['OPPONENT'].startswith('@')

    opponent_tc = " ".join(game_data['OPPONENT'].split(' ')[1:])
    opp_team_data = [team for team in nba_teams_data if team.get("city") == opponent_tc][0]
    game_data['opp_team'] = copy.deepcopy(opp_team_data)
    game_data['opp_team']['is_home'] = not game_data['my_team']['is_home']

    game_data.pop('OPPONENT')
    game_data.pop('TV')
    game_data.pop('DATE')
    game_data.pop('TIME')
    game_data.pop('tickets')

    return game_data

def convert_date(date_str):
    today = datetime.today()

    try:
        candidate_date = datetime.strptime(date_str + f" {today.year}", "%a, %b %d %Y")
    except ValueError:
        candidate_date = datetime.strptime(date_str + f" {today.year}", "%b %d %Y")

    if candidate_date.date() < today.date():
        candidate_date = candidate_date.replace(year=today.year + 1)

    return candidate_date.strftime("%m/%d/%Y")

def convert_to_utc(date_str, time_str):
    dt_str = f"{date_str} {time_str}"
    local_dt = datetime.strptime(dt_str, "%m/%d/%Y %I:%M %p")
    eastern = pytz.timezone("US/Eastern")
    localized_dt = eastern.localize(local_dt)
    utc_dt = localized_dt.astimezone(pytz.utc)

    return utc_dt.strftime("%Y-%m-%d %H:%M:%S %Z")

def convert_to_nba_api_format(original_json, nba_teams_data, my_team_data):
    def parse_datetime(dt_str):
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S %Z")
        gdte = dt.strftime("%Y-%m-%d")
        utctm = dt.strftime("%H:%M")
        etm = dt.strftime("%Y-%m-%dT%H:%M:%S")
        return gdte, utctm, etm

    games = []
    for game in original_json.get("upcoming_schedule", []):
        dt_str = game["datetime_utc"]
        gdte, utctm, etm = parse_datetime(dt_str) if dt_str else ("", "", "")

        opponent = game["opp_team"]['city']
        is_home = game["my_team"]['is_home']
        tv = game["channel"]

        my_team_game_data = [team for team in nba_teams_data if team.get("city") == my_team_data.get("city")][0]
        opp_team_game_data = [team for team in nba_teams_data if team.get("city") == opponent][0]

        game_obj = {
            "gdtutc": gdte,
            "utctm": utctm,
            "bd": {
                "b": [{"disp": tv}]
            },
            "v" if is_home else "h": {
                "re": f"{opp_team_game_data['record-wins']}-{opp_team_game_data['record-losses']}",
                "ta": opp_team_game_data["acronym"],
                "tn": opp_team_game_data["nickname"],
                "tc": opp_team_game_data["city"],
            },
            "h" if is_home else "v": {
                "re": f"{my_team_game_data['record-wins']}-{my_team_game_data['record-losses']}",
                "ta": my_team_game_data["acronym"],
                "tn": my_team_game_data["nickname"],
                "tc": my_team_game_data["city"],
            }
        }
        games.append(game_obj)

    return {
        "gscd": {
            "g": games,
            "ta": my_team_data["acronym"],
            "tn": my_team_data["nickname"],
            "tc": my_team_data["city"]
        }
    }
    
NBA_TEAMS_DATA = [
    {"name": "Atlanta Hawks", "acronym": "ATL", "espn-acronym": "ATL", "nickname": "Hawks", "city": "Atlanta", "url-name": "atlanta-hawks", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/atl.png"},
    {"name": "Boston Celtics", "acronym": "BOS", "espn-acronym": "BOS", "nickname": "Celtics", "city": "Boston", "url-name": "boston-celtics", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png"},
    {"name": "Brooklyn Nets", "acronym": "BKN", "espn-acronym": "BKN", "nickname": "Nets", "city": "Brooklyn", "url-name": "brooklyn-nets", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/bkn.png"},
    {"name": "Charlotte Hornets", "acronym": "CHA", "espn-acronym": "CHA", "nickname": "Hornets", "city": "Charlotte", "url-name": "charlotte-hornets", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/cha.png"},
    {"name": "Chicago Bulls", "acronym": "CHI", "espn-acronym": "CHI", "nickname": "Bulls", "city": "Chicago", "url-name": "chicago-bulls", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/chi.png"},
    {"name": "Cleveland Cavaliers", "acronym": "CLE", "espn-acronym": "CLE", "nickname": "Cavaliers", "city": "Cleveland", "url-name": "cleveland-cavaliers", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/cle.png"},
    {"name": "Dallas Mavericks", "acronym": "DAL", "espn-acronym": "DAL", "nickname": "Mavericks", "city": "Dallas", "url-name": "dallas-mavericks", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/dal.png"},
    {"name": "Denver Nuggets", "acronym": "DEN", "espn-acronym": "DEN", "nickname": "Nuggets", "city": "Denver", "url-name": "denver-nuggets", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/den.png"},
    {"name": "Detroit Pistons", "acronym": "DET", "espn-acronym": "DET", "nickname": "Pistons", "city": "Detroit", "url-name": "detroit-pistons", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/det.png"},
    {"name": "Golden State Warriors", "acronym": "GSW", "espn-acronym": "GS", "nickname": "Warriors", "city": "Golden State", "url-name": "golden-state-warriors", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/gs.png"},
    {"name": "Houston Rockets", "acronym": "HOU", "espn-acronym": "HOU", "nickname": "Rockets", "city": "Houston", "url-name": "houston-rockets", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/hou.png"},
    {"name": "Indiana Pacers", "acronym": "IND", "espn-acronym": "IND", "nickname": "Pacers", "city": "Indiana", "url-name": "indiana-pacers", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/ind.png"},
    {"name": "LA Clippers", "acronym": "LAC", "espn-acronym": "LAC", "nickname": "Clippers", "city": "LA", "url-name": "la-clippers", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/lac.png"},
    {"name": "Los Angeles Lakers", "acronym": "LAL", "espn-acronym": "LAL", "nickname": "Lakers", "city": "Los Angeles", "url-name": "los-angeles-lakers", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/lal.png"},
    {"name": "Memphis Grizzlies", "acronym": "MEM", "espn-acronym": "MEM", "nickname": "Grizzlies", "city": "Memphis", "url-name": "memphis-grizzlies", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/mem.png"},
    {"name": "Miami Heat", "acronym": "MIA", "espn-acronym": "MIA", "nickname": "Heat", "city": "Miami", "url-name": "miami-heat", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/mia.png"},
    {"name": "Milwaukee Bucks", "acronym": "MIL", "espn-acronym": "MIL", "nickname": "Bucks", "city": "Milwaukee", "url-name": "milwaukee-bucks", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/mil.png"},
    {"name": "Minnesota Timberwolves", "acronym": "MIN", "espn-acronym": "MIN", "nickname": "Timberwolves", "city": "Minnesota", "url-name": "minnesota-timberwolves", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/min.png"},
    {"name": "New Orleans Pelicans", "acronym": "NOP", "espn-acronym": "NO", "nickname": "Pelicans", "city": "New Orleans", "url-name": "new-orleans-pelicans", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/nop.png"},
    {"name": "New York Knicks", "acronym": "NYK", "espn-acronym": "NY", "nickname": "Knicks", "city": "New York", "url-name": "new-york-knicks", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/nyk.png"},
    {"name": "Oklahoma City Thunder", "acronym": "OKC", "espn-acronym": "OKC", "nickname": "Thunder", "city": "Oklahoma City", "url-name": "oklahoma-city-thunder", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/okc.png"},
    {"name": "Orlando Magic", "acronym": "ORL", "espn-acronym": "ORL", "nickname": "Magic", "city": "Orlando", "url-name": "orlando-magic", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/orl.png"},
    {"name": "Philadelphia 76ers", "acronym": "PHI", "espn-acronym": "PHI", "nickname": "76ers", "city": "Philadelphia", "url-name": "philadelphia-76ers", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/phi.png"},
    {"name": "Phoenix Suns", "acronym": "PHX", "espn-acronym": "PHX", "nickname": "Suns", "city": "Phoenix", "url-name": "phoenix-suns", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/phx.png"},
    {"name": "Portland Trail Blazers", "acronym": "POR", "espn-acronym": "POR", "nickname": "Trail Blazers", "city": "Portland", "url-name": "portland-trail-blazers", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/por.png"},
    {"name": "Sacramento Kings", "acronym": "SAC", "espn-acronym": "SAC", "nickname": "Kings", "city": "Sacramento", "url-name": "sacramento-kings", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/sac.png"},
    {"name": "San Antonio Spurs", "acronym": "SAS", "espn-acronym": "SAS", "nickname": "Spurs", "city": "San Antonio", "url-name": "san-antonio-spurs", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/sas.png"},
    {"name": "Toronto Raptors", "acronym": "TOR", "espn-acronym": "TOR", "nickname": "Raptors", "city": "Toronto", "url-name": "toronto-raptors", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/tor.png"},
    {"name": "Utah Jazz", "acronym": "UTA", "espn-acronym": "UTA", "nickname": "Jazz", "city": "Utah", "url-name": "utah-jazz", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/uta.png"},
    {"name": "Washington Wizards", "acronym": "WAS", "espn-acronym": "WSH", "nickname": "Wizards", "city": "Washington", "url-name": "washington-wizards", "logo-url": "https://a.espncdn.com/i/teamlogos/nba/500/was.png"}
]

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=10000)
