from flask import Flask, jsonify
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

    return jsonify({'upcoming_schedule': schedule})

def convert_date(date_str):
    # Current date
    today = datetime.today()

    # Try parsing with current year first
    try:
        candidate_date = datetime.strptime(date_str + f" {today.year}", "%a, %b %d %Y")
    except ValueError:
        # If weekday is missing, try without it
        candidate_date = datetime.strptime(date_str + f" {today.year}", "%b %d %Y")

    # If the date has already passed this year, use next year
    if candidate_date.date() < today.date():
        candidate_date = candidate_date.replace(year=today.year + 1)

    return candidate_date.strftime("%m/%d/%Y")

def convert_to_utc(date_str, time_str):
    # Combine date and time into one string
    dt_str = f"{date_str} {time_str}"

    # Parse the combined string into a naive datetime object
    local_dt = datetime.strptime(dt_str, "%m/%d/%Y %I:%M %p")

    # Define Eastern Time with daylight saving support
    eastern = pytz.timezone("US/Eastern")

    # Localize the naive datetime to Eastern Time
    localized_dt = eastern.localize(local_dt)

    # Convert to UTC
    utc_dt = localized_dt.astimezone(pytz.utc)

    return utc_dt.strftime("%Y-%m-%d %H:%M:%S %Z")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=10000)
