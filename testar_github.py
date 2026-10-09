import json
import os

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')

config = {}
try:
    with open(CONFIG_PATH, encoding='utf-8') as f:
        data = json.load(f)
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str) and v.strip():
                    config[k] = v.strip()
except (OSError, ValueError):
    pass

api_url = (os.environ.get('EBD_API_URL') or config.get('api_url')
           or 'https://ebd-api-n7xg.onrender.com').rstrip('/')

try:
    r = requests.get(api_url + '/health', timeout=20)
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
except requests.exceptions.RequestException as e:
    print('Falha:', e)
