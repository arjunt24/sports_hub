# https://dashboard.render.com/web/srv-d3sq1lhr0fns738mcp9g

from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

app = Flask(__name__)

@app.route('/lakers-schedule', methods=['GET'])
def get_lakers_schedule():
    url = 'https://www.espn.com/nba/team/schedule/_/name/lal/los-angeles-lakers'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return jsonify({'error': 'Failed to fetch schedule'}), response.status_code

    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('tbody', class_='Table__TBODY')

    schedule = []
    cols = None
    header_row_0_found = False
    for row in table.find_all('tr'):
        if cols is None: 
            if 'Table_Headers' in row.find('td')['class']:
                if not header_row_0_found:
                    header_row_0_found = True
                else:
                    cols = [header.text.strip() for header in row.find_all('td')]
            continue

        game_cells = row.find_all('td')
        game_data = {cols[i]: cell for i, cell in enumerate([col.text.strip() for col in game_cells])}

        tv_cell = game_cells[cols.index('TV')]
        if tv_cell.text == '':
            for figure in tv_cell.find_all('figure'):
                network = [cls for cls in figure['class'] if cls.startswith('network-')]
                game_data['TV'] += network[0].replace('network-', '').upper()
        if 'ABC' in game_data['TV']:
            game_data['TV'] = 'ABC '
        elif 'ESPN' in game_data['TV']:
            game_data['TV'] = 'ESPN '
        elif 'NBC' in game_data['TV']:
            game_data['TV'] = 'NBC '
        elif 'Peacock' in game_data['TV']:
            game_data['TV'] = 'Peacock'
        elif game_data['TV'] in ['Prime Video', 'NBA TV']:
            pass
        else:
            game_data['TV'] = 'League Pass'

        game_data['DATE'] = convert_date(game_data['DATE'])

        game_data['DATETIME'] = convert_to_utc(game_data['DATE'], game_data['TIME'])

        game_data['IS_HOME'] = not game_data['OPPONENT'].startswith('@')
        game_data['OPPONENT'] = " ".join(game_data['OPPONENT'].split(' ')[1:])

        game_data.pop('DATE')
        game_data.pop('TIME')
        game_data.pop('tickets')

        schedule.append(game_data)

    resp = {'upcoming_schedule': schedule}

    if request.args.get('nbapiformat') == 'true':
        return jsonify(convert_to_nba_api_format(resp))
    
    return jsonify(resp)

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

def convert_to_nba_api_format(original_json):
    def parse_datetime(dt_str):
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S %Z")
        gdte = dt.strftime("%Y-%m-%d")
        utctm = dt.strftime("%H:%M")
        etm = dt.strftime("%Y-%m-%dT%H:%M:%S")
        return gdte, utctm, etm

    games = []
    for i, game in enumerate(original_json.get("upcoming_schedule", [])):
        dt_str = game.get("DATETIME", "")
        gdte, utctm, etm = parse_datetime(dt_str) if dt_str else ("", "", "")
        
        opponent = game.get("OPPONENT", "")
        is_home = game.get("IS_HOME", False)
        tv = game.get("TV", "")

        gid = f"00125000{i+1:02d}"
        gcode = f"{gdte.replace('-', '')}/{'LAL' + opponent[:3].upper()}" if gdte and opponent else ""

        home_team = NBA_TEAMS["Los Angeles"]
        away_team = NBA_TEAMS.get(opponent, {"tid": "", "ta": "", "tn": "", "tc": opponent})

        h_team = home_team if is_home else away_team
        v_team = away_team if is_home else home_team

        game_obj = {
            "gid": gid,
            "gcode": gcode,
            "seri": "",
            "is": int(is_home),
            "gdte": gdte,
            "htm": etm,
            "vtm": etm,
            "etm": etm,
            "an": "",
            "ac": "",
            "as": "",
            "st": "",
            "stt": "",
            "bd": {
                "b": []
            },
            "v": {
                "tid": v_team["tid"],
                "re": "",
                "ta": v_team["ta"],
                "tn": v_team["tn"],
                "tc": v_team["tc"],
                "s": ""
            },
            "h": {
                "tid": h_team["tid"],
                "re": "",
                "ta": h_team["ta"],
                "tn": h_team["tn"],
                "tc": h_team["tc"],
                "s": ""
            },
            "gdtutc": gdte,
            "utctm": utctm,
            "ppdst": ""
        }
        games.append(game_obj)

    return {
        "gscd": {
            "tid": NBA_TEAMS["Los Angeles"]["tid"],
            "g": games,
            "ta": NBA_TEAMS["Los Angeles"]["ta"],
            "tn": NBA_TEAMS["Los Angeles"]["tn"],
            "tc": NBA_TEAMS["Los Angeles"]["tc"]
        }
    }
    
NBA_TEAMS = {
    "Atlanta":      {"tid": 1610612737, "ta": "ATL", "tn": "Hawks", "tc": "Atlanta"},
    "Boston":       {"tid": 1610612738, "ta": "BOS", "tn": "Celtics", "tc": "Boston"},
    "Brooklyn":     {"tid": 1610612751, "ta": "BKN", "tn": "Nets", "tc": "Brooklyn"},
    "Charlotte":    {"tid": 1610612766, "ta": "CHA", "tn": "Hornets", "tc": "Charlotte"},
    "Chicago":      {"tid": 1610612741, "ta": "CHI", "tn": "Bulls", "tc": "Chicago"},
    "Cleveland":    {"tid": 1610612739, "ta": "CLE", "tn": "Cavaliers", "tc": "Cleveland"},
    "Dallas":       {"tid": 1610612742, "ta": "DAL", "tn": "Mavericks", "tc": "Dallas"},
    "Denver":       {"tid": 1610612743, "ta": "DEN", "tn": "Nuggets", "tc": "Denver"},
    "Detroit":      {"tid": 1610612765, "ta": "DET", "tn": "Pistons", "tc": "Detroit"},
    "Golden State": {"tid": 1610612744, "ta": "GSW", "tn": "Warriors", "tc": "Golden State"},
    "Houston":      {"tid": 1610612745, "ta": "HOU", "tn": "Rockets", "tc": "Houston"},
    "Indiana":      {"tid": 1610612754, "ta": "IND", "tn": "Pacers", "tc": "Indiana"},
    "LA":  {"tid": 1610612746, "ta": "LAC", "tn": "Clippers", "tc": "LA"},
    "Los Angeles":  {"tid": 1610612747, "ta": "LAL", "tn": "Lakers", "tc": "Los Angeles"},
    "Memphis":      {"tid": 1610612763, "ta": "MEM", "tn": "Grizzlies", "tc": "Memphis"},
    "Miami":        {"tid": 1610612748, "ta": "MIA", "tn": "Heat", "tc": "Miami"},
    "Milwaukee":    {"tid": 1610612749, "ta": "MIL", "tn": "Bucks", "tc": "Milwaukee"},
    "Minnesota":    {"tid": 1610612750, "ta": "MIN", "tn": "Timberwolves", "tc": "Minnesota"},
    "New Orleans":  {"tid": 1610612740, "ta": "NOP", "tn": "Pelicans", "tc": "New Orleans"},
    "New York":     {"tid": 1610612752, "ta": "NYK", "tn": "Knicks", "tc": "New York"},
    "Oklahoma City":{"tid": 1610612760, "ta": "OKC", "tn": "Thunder", "tc": "Oklahoma City"},
    "Orlando":      {"tid": 1610612753, "ta": "ORL", "tn": "Magic", "tc": "Orlando"},
    "Philadelphia": {"tid": 1610612755, "ta": "PHI", "tn": "76ers", "tc": "Philadelphia"},
    "Phoenix":      {"tid": 1610612756, "ta": "PHX", "tn": "Suns", "tc": "Phoenix"},
    "Portland":     {"tid": 1610612757, "ta": "POR", "tn": "Trail Blazers", "tc": "Portland"},
    "Sacramento":   {"tid": 1610612758, "ta": "SAC", "tn": "Kings", "tc": "Sacramento"},
    "San Antonio":  {"tid": 1610612759, "ta": "SAS", "tn": "Spurs", "tc": "San Antonio"},
    "Toronto":      {"tid": 1610612761, "ta": "TOR", "tn": "Raptors", "tc": "Toronto"},
    "Utah":         {"tid": 1610612762, "ta": "UTA", "tn": "Jazz", "tc": "Utah"},
    "Washington":   {"tid": 1610612764, "ta": "WAS", "tn": "Wizards", "tc": "Washington"}
}


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=10000)
