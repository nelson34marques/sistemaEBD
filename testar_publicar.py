import base64
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
except (OSError, ValueError) as e:
    print('ERRO a ler config.json:', e)

api_url = (os.environ.get('EBD_API_URL') or config.get('api_url')
           or 'https://ebd-api-n7xg.onrender.com').rstrip('/')
token = os.environ.get('EBD_SYNC_TOKEN') or config.get('sync_token', '')

print('=== TESTE DE PUBLICAÇÃO (POST /sync) ===')
print('API URL:', api_url)
print('Token definido:', 'SIM' if token else 'NÃO')

headers = {'X-Sync-Token': token} if token else {}

print('A testar POST /sync ...')
payload = {'database': base64.b64encode(b'SQLite format 3\x00' + b'\x00' * 100).decode('ascii')}
try:
    r = requests.post(api_url + '/sync', json=payload, headers=headers, timeout=60)
    print('Status:', r.status_code)
    try:
        body = r.json()
        print('Resposta:', json.dumps(body, indent=2, ensure_ascii=False))
    except ValueError:
        print('Resposta (texto):', r.text[:500])
except requests.exceptions.RequestException as e:
    print('Falha de ligação:', e)
