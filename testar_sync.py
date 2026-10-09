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

print('=== DIAGNÓSTICO DE SINCRONIZAÇÃO ===')
print('Config path:', CONFIG_PATH)
print('API URL:', api_url)
print('Token definido:', 'SIM' if token else 'NÃO')
if token:
    print('Token (início):', token[:12])
    print('Token (fim):', token[-12:])
    print('Token comprimento:', len(token))
print()

headers = {}
if token:
    headers['X-Sync-Token'] = token

print('A testar GET /database ...')
try:
    r = requests.get(api_url + '/database', headers=headers, timeout=30)
    print('Status:', r.status_code)
    if r.status_code == 200:
        print('SUCESSO! Token válido. Tamanho dos dados:', len(r.content))
    else:
        try:
            body = r.json()
            print('Erro:', body.get('erro') or body)
        except ValueError:
            print('Erro HTTP', r.status_code)
            print('Resposta:', r.text[:200])
except requests.exceptions.RequestException as e:
    print('Falha de ligação:', e)
