from flask import Flask, jsonify
import requests
from bs4 import BeautifulSoup

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
    data = soup.find('tbody', class_='Table__TBODY')

    schedule = []
    for row in data.find_all('tr'):
        columns = row.find_all('td')
        schedule.append([col.text.strip() for col in columns])

    return jsonify({'schedule': schedule})

if __name__ == '__main__':
    app.run(debug=True, port=10000)

