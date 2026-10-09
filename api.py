import base64
import hashlib
import hmac
import os
import sqlite3
import tempfile
from datetime import datetime
from functools import wraps
from urllib.parse import quote

import requests as http_requests
from flask import Flask, jsonify, request, g
from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

import database as db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DATABASE_PATH') or os.path.join(BASE_DIR, 'database.sqlite')
db.DB_PATH = DB_PATH

try:
    # Garante o esquema actual (colunas novas como members.photo) antes de servir.
    db.init_db()
except Exception:
    pass

FIREBASE_PROJECT_ID = (os.environ.get('FIREBASE_PROJECT_ID') or '').strip()

SYNC_TOKEN = (os.environ.get('SYNC_TOKEN') or '').strip()
GITHUB_TOKEN = (os.environ.get('GITHUB_TOKEN') or '').strip()
GITHUB_REPO = (os.environ.get('GITHUB_REPO') or '').strip()
GITHUB_PATH = (os.environ.get('GITHUB_PATH') or 'database.sqlite').strip()
GITHUB_BRANCH = (os.environ.get('GITHUB_BRANCH') or 'main').strip()
GITHUB_COMMIT_MESSAGE = (
    os.environ.get('GITHUB_COMMIT_MESSAGE')
    or 'Actualizar base de dados pelo app Secretaria EBD'
).strip()



def _csv_env(name):
    return [v.strip() for v in (os.environ.get(name) or '').split(',') if v.strip()]


ALLOWED_ORIGINS = _csv_env('API_ALLOWED_ORIGINS')
ALLOWED_EMAILS = {v.lower() for v in _csv_env('API_ALLOWED_EMAILS')}
RATE_LIMIT = os.environ.get('API_RATE_LIMIT', '120 per minute')
REQUIRE_AUTH = (os.environ.get('API_REQUIRE_AUTH', 'true') or 'true').strip().lower() not in ('0', 'false', 'nao', 'no', 'off')

app = Flask(__name__)
app.json.ensure_ascii = False
app.json.sort_keys = False


def connect():
    uri = 'file:{}?mode=ro'.format(quote(DB_PATH))
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only = ON')
    return conn


def query(sql, args=()):
    conn = connect()
    try:
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def calculate_age(birth_date_str):
    if not birth_date_str:
        return None
    try:
        birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d')
        today = datetime.today()
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    except (ValueError, TypeError):
        return None


def staff_by_class():
    staff = query('''
        SELECT s.class_id, s.name, s.role, s.phone FROM staff s
        WHERE s.deleted_at IS NULL
    ''')
    by_class = {}
    for s in staff:
        by_class.setdefault(s['class_id'], []).append(s)
    return by_class


def session_stats():
    stats = query('''
        SELECT
            a.session_id,
            COUNT(a.id) AS total,
            SUM(CASE WHEN a.is_present = 1 THEN 1 ELSE 0 END) AS presentes
        FROM attendances a
        GROUP BY a.session_id
    ''')
    return {s['session_id']: s for s in stats}


def verify_firebase_token(token):
    google_request = google_requests.Request()
    return google_id_token.verify_firebase_token(
        token, google_request, audience=FIREBASE_PROJECT_ID
    )


def authenticate():
    """Valida a sessão do Firebase. Devolve None (ok) ou (resposta, estado)."""
    if not FIREBASE_PROJECT_ID:
        return jsonify({
            'erro': 'API nao configurada',
            'detalhe': 'FIREBASE_PROJECT_ID nao definido no servidor'
        }), 503

    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return jsonify({'erro': 'Token ausente'}), 401

    token = header[7:].strip()
    if not token:
        return jsonify({'erro': 'Token ausente'}), 401

    try:
        claims = verify_firebase_token(token)
    except TransportError:
        return jsonify({'erro': 'Nao foi possivel validar a sessao. Tente novamente.'}), 503
    except GoogleAuthError:
        return jsonify({'erro': 'Token invalido'}), 401
    except Exception:
        return jsonify({'erro': 'Token invalido ou expirado'}), 401

    email = (claims.get('email') or '').lower()
    if ALLOWED_EMAILS and email not in ALLOWED_EMAILS:
        return jsonify({'erro': 'Sem permissao'}), 403

    g.user = claims
    g.user_email = email
    g.user_uid = claims.get('sub')
    return None


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not REQUIRE_AUTH:
            return fn(*args, **kwargs)
        erro = authenticate()
        if erro:
            return erro
        return fn(*args, **kwargs)
    return wrapper


def require_write(fn):
    """Exige sessão de administrador para escrever, mesmo com API_REQUIRE_AUTH = false."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        erro = authenticate()
        if erro:
            return erro
        return fn(*args, **kwargs)
    return wrapper


def rate_limit_key():
    return g.user_uid if getattr(g, 'user_uid', None) else request.remote_addr


def client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr


buckets = {}


@app.before_request
def handle_preflight():
    if request.method == 'OPTIONS':
        return ('', 204)


@app.before_request
def enforce_rate_limit():

    allowed = None
    raw_limit = RATE_LIMIT.split()
    if raw_limit:
        try:
            allowed = int(raw_limit[0])
        except (ValueError, IndexError):
            allowed = 120

    if not allowed:
        return None

    key = client_ip()
    now = datetime.now().timestamp()
    window = 60.0

    hits = [t for t in buckets.get(key, []) if now - t < window]
    if len(hits) >= allowed:
        return jsonify({'erro': 'Muitas requisicoes. Tente de novo em instantes.'}), 429
    hits.append(now)
    buckets[key] = hits

    if len(buckets) > 5000:
        for stale in [k for k, v in buckets.items() if not v or now - v[-1] > window]:
            buckets.pop(stale, None)

    response = None
    return response


@app.after_request
def add_cors(response):
    origin = request.headers.get('Origin')
    if origin and ALLOWED_ORIGINS and origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Vary'] = 'Origin'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Max-Age'] = 86400
    elif 'Access-Control-Allow-Origin' in response.headers:
        del response.headers['Access-Control-Allow-Origin']

    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.errorhandler(401)
def handler_401(error):
    return jsonify({'erro': 'Nao autorizado'}), 401


@app.errorhandler(403)
def handler_403(error):
    return jsonify({'erro': 'Sem permissao'}), 403


@app.errorhandler(429)
def handler_429(error):
    return jsonify({'erro': 'Muitas requisicoes'}), 429


@app.route('/health', methods=['GET'])
def health():
    try:
        pendentes = db.pending_changes()
    except Exception:
        pendentes = None
    return jsonify({
        'status': 'ok',
        'auth_configurado': bool(FIREBASE_PROJECT_ID),
        'origens_permitidas': len(ALLOWED_ORIGINS),
        'emails_permitidos': len(API_ALLOWED_EMAILS) > 0,
        'sync_configurado': bool(SYNC_TOKEN and GITHUB_TOKEN and GITHUB_REPO),
        'github_token_definido': bool(GITHUB_TOKEN),
        'github_repo_definido': bool(GITHUB_REPO),
        'pendentes_publicar': pendentes,
    })


@app.route('/', methods=['GET', 'OPTIONS'])
@require_auth
def home():
    if request.method == 'OPTIONS':
        return ('', 204)
    return jsonify({
        'nome': 'API EBD - leitura',
        'autenticado': True,
        'usuario': getattr(g, 'user_email', None),
        'endpoints': [
            '/stats',
            '/classes',
            '/classes/<id>',
            '/classes/<id>/staff',
            '/classes/<id>/members',
            '/classes/<id>/sessions',
            '/sessions',
            '/sessions/<id>',
            '/members',
        ]
    })


@app.route('/stats', methods=['GET', 'OPTIONS'])
@require_auth
def stats():
    if request.method == 'OPTIONS':
        return ('', 204)
    classes = query('SELECT COUNT(*) AS n FROM classes WHERE deleted_at IS NULL')[0]['n']
    members = query('SELECT COUNT(*) AS n FROM members WHERE deleted_at IS NULL')[0]['n']
    sessions = query('SELECT COUNT(*) AS n FROM class_sessions')[0]['n']
    visitors = query('SELECT COUNT(*) AS n FROM visitors WHERE deleted_at IS NULL')[0]['n']
    presentes = query('''
        SELECT COUNT(*) AS n FROM attendances a
        JOIN members m ON m.id = a.member_id
        WHERE a.is_present = 1 AND m.deleted_at IS NULL
    ''')[0]['n']
    por_turma = []
    for c in query('SELECT id, name FROM classes WHERE deleted_at IS NULL ORDER BY age_min'):
        c['alunos'] = query(
            'SELECT COUNT(*) AS n FROM members WHERE class_id = ? AND deleted_at IS NULL',
            (c['id'],)
        )[0]['n']
        por_turma.append(c)
    return jsonify({
        'turmas': classes,
        'alunos': members,
        'aulas_registadas': sessions,
        'visitantes_ativos': visitors,
        'presencas_confirmadas': presentes,
        'alunos_por_turma': por_turma,
    })


@app.route('/classes', methods=['GET', 'OPTIONS'])
@require_auth
def classes():
    if request.method == 'OPTIONS':
        return ('', 204)
    staff = staff_by_class()
    result = []
    for c in query('''
        SELECT c.*,
            (SELECT COUNT(*) FROM members m
             WHERE m.class_id = c.id AND m.deleted_at IS NULL) AS alunos
        FROM classes c
        WHERE c.deleted_at IS NULL
        ORDER BY c.age_min
    '''):
        equipa = {}
        for s in staff.get(c['id'], []):
            equipa.setdefault(s['role'], []).append({'nome': s['name'], 'telefone': s['phone']})
        c['equipa'] = equipa
        result.append(c)
    return jsonify(result)


@app.route('/classes/<class_id>', methods=['GET', 'OPTIONS'])
@require_auth
def class_detail(class_id):
    if request.method == 'OPTIONS':
        return ('', 204)
    rows = query('''
        SELECT c.*,
            (SELECT COUNT(*) FROM members m
             WHERE m.class_id = c.id AND m.deleted_at IS NULL) AS alunos
        FROM classes c
        WHERE c.id = ? AND c.deleted_at IS NULL
    ''', (class_id,))
    if not rows:
        return jsonify({'erro': 'Turma não encontrada'}), 404
    c = rows[0]
    equipa = {}
    for s in query('''
        SELECT s.name, s.role, s.phone FROM staff s
        WHERE s.class_id = ? AND s.deleted_at IS NULL
    ''', (class_id,)):
        equipa.setdefault(s['role'], []).append({'nome': s['name'], 'telefone': s['phone']})
    c['equipa'] = equipa
    return jsonify(c)


@app.route('/classes/<class_id>/staff', methods=['GET', 'OPTIONS'])
@require_auth
def class_staff(class_id):
    if request.method == 'OPTIONS':
        return ('', 204)
    return jsonify(query('''
        SELECT s.name, s.role, s.phone, s.class_id FROM staff s
        JOIN classes c ON c.id = s.class_id
        WHERE s.class_id = ? AND s.deleted_at IS NULL AND c.deleted_at IS NULL
        ORDER BY s.role
    ''', (class_id,)))


@app.route('/classes/<class_id>/members', methods=['GET', 'OPTIONS'])
@require_auth
def class_members(class_id):
    if request.method == 'OPTIONS':
        return ('', 204)
    members = query('''
        SELECT m.id, m.name, m.birth_date, m.role, m.class_id
        FROM members m
        WHERE m.class_id = ? AND m.deleted_at IS NULL
        ORDER BY m.name
    ''', (class_id,))
    for m in members:
        m['idade'] = calculate_age(m['birth_date'])
    return jsonify(members)


@app.route('/classes/<class_id>/sessions', methods=['GET', 'OPTIONS'])
@require_auth
def class_sessions(class_id):
    if request.method == 'OPTIONS':
        return ('', 204)
    stats = session_stats()
    sessions = query('''
        SELECT cs.id, cs.class_id, cs.date, cs.visitors_count
        FROM class_sessions cs
        WHERE cs.class_id = ?
        ORDER BY cs.date DESC
    ''', (class_id,))
    for s in sessions:
        st = stats.get(s['id'], {})
        s['presencas'] = st.get('presentes', 0) or 0
        s['matriculados'] = st.get('total', 0) or 0
    return jsonify(sessions)


@app.route('/sessions', methods=['GET', 'OPTIONS'])
@require_auth
def sessions():
    if request.method == 'OPTIONS':
        return ('', 204)
    sql = '''
        SELECT cs.id, cs.class_id, c.name AS turma, cs.date, cs.visitors_count
        FROM class_sessions cs
        JOIN classes c ON c.id = cs.class_id AND c.deleted_at IS NULL
    '''
    args = []
    where = []
    class_id = request.args.get('class_id')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    if class_id:
        where.append('cs.class_id = ?')
        args.append(class_id)
    if date_from:
        where.append('cs.date >= ?')
        args.append(date_from)
    if date_to:
        where.append('cs.date <= ?')
        args.append(date_to)
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY cs.date DESC, cs.class_id'
    sessions = query(sql, args)
    stats = session_stats()
    for s in sessions:
        st = stats.get(s['id'], {})
        s['presencas'] = st.get('presentes', 0) or 0
        s['matriculados'] = st.get('total', 0) or 0
    return jsonify(sessions)


@app.route('/sessions/<session_id>', methods=['GET', 'OPTIONS'])
@require_auth
def session_detail(session_id):
    if request.method == 'OPTIONS':
        return ('', 204)
    rows = query('''
        SELECT cs.*, c.name AS turma
        FROM class_sessions cs
        JOIN classes c ON c.id = cs.class_id AND c.deleted_at IS NULL
        WHERE cs.id = ?
    ''', (session_id,))
    if not rows:
        return jsonify({'erro': 'Aula não encontrada'}), 404
    session = rows[0]

    members = query('''
        SELECT m.id, m.name, m.birth_date
        FROM members m
        WHERE m.class_id = ? AND m.deleted_at IS NULL
        ORDER BY m.name
    ''', (session['class_id'],))
    for m in members:
        m['idade'] = calculate_age(m['birth_date'])
        m['presente'] = False

    for a in query('''
        SELECT member_id, is_present FROM attendances WHERE session_id = ?
    ''', (session_id,)):
        for m in members:
            if m['id'] == a['member_id']:
                m['presente'] = bool(a['is_present'])

    session['alunos'] = members
    session['visitantes'] = query('''
        SELECT id, name FROM visitors
        WHERE session_id = ? AND deleted_at IS NULL
        ORDER BY created_at
    ''', (session_id,))
    return jsonify(session)


@app.route('/members', methods=['GET', 'OPTIONS'])
@require_auth
def members():
    if request.method == 'OPTIONS':
        return ('', 204)
    result = query('''
        SELECT m.id, m.name, m.birth_date, m.role, m.class_id, c.name AS turma,
               CASE WHEN m.photo IS NULL THEN 0 ELSE 1 END AS has_photo
        FROM members m
        LEFT JOIN classes c ON c.id = m.class_id
        WHERE m.deleted_at IS NULL
        ORDER BY c.age_min, m.name
    ''')
    class_id = request.args.get('class_id')
    if class_id:
        result = [m for m in result if m['class_id'] == class_id]
    for m in result:
        m['idade'] = calculate_age(m['birth_date'])
    return jsonify(result)


@app.route('/members/photos', methods=['GET', 'OPTIONS'])
@require_auth
def members_photos():
    if request.method == 'OPTIONS':
        return ('', 204)
    rows = query('SELECT id, photo FROM members WHERE deleted_at IS NULL AND photo IS NOT NULL')
    return jsonify({r['id']: r['photo'] for r in rows})


@app.route('/visitors', methods=['GET', 'OPTIONS'])
@require_auth
def visitors():
    if request.method == 'OPTIONS':
        return ('', 204)
    rows = query('''
        SELECT v.id, v.name, v.session_id, v.created_at,
               cs.date, cs.class_id, c.name AS turma
        FROM visitors v
        JOIN class_sessions cs ON cs.id = v.session_id
        LEFT JOIN classes c ON c.id = cs.class_id
        WHERE v.deleted_at IS NULL
        ORDER BY cs.date DESC, v.created_at
    ''')
    return jsonify([{
        'id': r['id'],
        'name': r['name'],
        'date': r['date'],
        'classId': r['class_id'],
        'className': r['turma'] or 'Visitante',
        'sessionId': r['session_id'],
        'createdAt': r['created_at'],
    } for r in rows])


@app.route('/attendance', methods=['GET', 'OPTIONS'])
@require_auth
def attendance():
    if request.method == 'OPTIONS':
        return ('', 204)
    rows = query('''
        SELECT a.session_id, a.member_id, a.is_present
        FROM attendances a
        JOIN members m ON m.id = a.member_id AND m.deleted_at IS NULL
        JOIN class_sessions cs ON cs.id = a.session_id
        JOIN classes c ON c.id = cs.class_id AND c.deleted_at IS NULL
    ''')
    by_session = {}
    for r in rows:
        by_session.setdefault(r['session_id'], []).append({
            'memberId': r['member_id'],
            'status': 'Presente' if r['is_present'] else 'Ausente',
        })
    if not by_session:
        return jsonify([])
    sessions = query('''
        SELECT cs.id, cs.class_id, cs.date, c.name AS turma
        FROM class_sessions cs
        JOIN classes c ON c.id = cs.class_id AND c.deleted_at IS NULL
        WHERE cs.id IN ({})
        ORDER BY cs.date DESC
    '''.format(','.join('?' for _ in by_session)), tuple(by_session))
    return jsonify([{
        'id': s['id'],
        'classId': s['class_id'],
        'sessionDate': s['date'],
        'className': s['turma'],
        'attendance': by_session[s['id']],
    } for s in sessions])


def _publicar_local(mensagem):
    """Publica a base local no GitHub. Devolve o estado da publicação."""
    if not (GITHUB_TOKEN and GITHUB_REPO):
        return {'publicado': False,
                'motivo': 'Publicação não configurada no servidor (faltam GITHUB_TOKEN/GITHUB_REPO).'}
    try:
        commit, sha = publish_to_github(db.backup_to_bytes(), mensagem)
    except http_requests.RequestException:
        return {'publicado': False,
                'motivo': 'Sem ligação ao GitHub. Os dados ficam guardados e serão publicados na próxima gravação.'}
    except RuntimeError as exc:
        return {'publicado': False, 'motivo': str(exc)}
    db.mark_all_synced()
    return {'publicado': True, 'commit': commit, 'sha': sha}


def _data_valida(valor):
    try:
        datetime.strptime(valor, '%Y-%m-%d')
        return True
    except (ValueError, TypeError):
        return False


def _turma_existe(class_id):
    return bool(query('SELECT id FROM classes WHERE id = ? AND deleted_at IS NULL', (class_id,)))


@app.route('/members', methods=['POST', 'OPTIONS'])
@require_write
def criar_membro():
    if request.method == 'OPTIONS':
        return ('', 204)
    data = request.get_json(silent=True) or {}
    nome = str(data.get('name') or '').strip()
    if not 2 <= len(nome) <= 120:
        return jsonify({'erro': 'Indique o nome do aluno (2 a 120 caracteres).'}), 400
    nascimento = str(data.get('birth_date') or '').strip()
    if nascimento and not _data_valida(nascimento):
        return jsonify({'erro': 'Data de nascimento inválida (use AAAA-MM-DD).'}), 400
    papel = str(data.get('role') or 'Aluno').strip() or 'Aluno'
    if len(papel) > 40:
        return jsonify({'erro': 'Função demasiado longa.'}), 400

    member_id, turma = db.add_member(nome, nascimento, papel)
    publicacao = _publicar_local('Registar aluno pelo site: {0}'.format(nome))
    return jsonify({
        'id': member_id,
        'name': nome,
        'birth_date': nascimento,
        'role': papel,
        'class_id': turma['id'] if turma else None,
        'turma': turma['name'] if turma else None,
        'idade': calculate_age(nascimento),
        'has_photo': 0,
        'publicacao': publicacao,
    }), 201


@app.route('/members/<member_id>/photo', methods=['GET', 'POST', 'OPTIONS'])
def foto_do_membro(member_id):
    if request.method == 'OPTIONS':
        return ('', 204)
    if request.method == 'GET':
        erro = authenticate() if REQUIRE_AUTH else None
        if erro:
            return erro
        foto = db.get_member_photo(member_id)
        if not foto:
            return jsonify({'erro': 'Este aluno ainda não tem foto.'}), 404
        return jsonify({'photo': foto, 'id': member_id})

    erro = authenticate()
    if erro:
        return erro
    data = request.get_json(silent=True) or {}
    foto = str(data.get('photo') or '')
    if not foto.startswith('data:image/') or ';base64,' not in foto:
        return jsonify({'erro': 'Formato de foto inválido.'}), 400
    if len(foto) > 900000:
        return jsonify({'erro': 'Foto demasiado grande (máximo 600 KB após redução).'}), 400
    if not db.set_member_photo(member_id, foto):
        return jsonify({'erro': 'Aluno não encontrado.'}), 404
    publicacao = _publicar_local('Foto de aluno')
    return jsonify({'ok': True, 'id': member_id, 'publicacao': publicacao}), 201


@app.route('/visitors', methods=['POST', 'OPTIONS'])
@require_write
def criar_visitante():
    if request.method == 'OPTIONS':
        return ('', 204)
    data = request.get_json(silent=True) or {}
    nome = str(data.get('name') or '').strip()
    if not 2 <= len(nome) <= 120:
        return jsonify({'erro': 'Indique o nome do visitante (2 a 120 caracteres).'}), 400
    class_id = str(data.get('classId') or '').strip()
    if not class_id or not _turma_existe(class_id):
        return jsonify({'erro': 'Escolha uma turma válida.'}), 400
    data_sessao = str(data.get('date') or '').strip()
    if not _data_valida(data_sessao):
        return jsonify({'erro': 'Data da sessão inválida (use AAAA-MM-DD).'}), 400

    sessao = db.get_or_create_session(class_id, data_sessao)
    visitor_id = db.add_visitor(sessao['id'], nome)
    publicacao = _publicar_local('Registar visitante pelo site: {0}'.format(nome))
    return jsonify({
        'id': visitor_id,
        'name': nome,
        'date': data_sessao,
        'classId': class_id,
        'sessionId': sessao['id'],
        'publicacao': publicacao,
    }), 201


@app.route('/attendance', methods=['POST', 'OPTIONS'])
@require_write
def registar_presencas():
    if request.method == 'OPTIONS':
        return ('', 204)
    data = request.get_json(silent=True) or {}
    class_id = str(data.get('classId') or '').strip()
    if not class_id or not _turma_existe(class_id):
        return jsonify({'erro': 'Escolha uma turma válida.'}), 400
    data_sessao = str(data.get('date') or '').strip()
    if not _data_valida(data_sessao):
        return jsonify({'erro': 'Data da sessão inválida (use AAAA-MM-DD).'}), 400
    lista = data.get('attendance')
    if not isinstance(lista, list) or not lista:
        return jsonify({'erro': 'Indique a lista de alunos e o respectivo estado.'}), 400

    presencas = {}
    for item in lista:
        member_id = str((item or {}).get('memberId') or '').strip()
        if not member_id:
            continue
        presencas[member_id] = str((item or {}).get('status') or '') == 'Presente'
    if not presencas:
        return jsonify({'erro': 'Lista de presenças inválida.'}), 400

    existentes = {
        r['id'] for r in query(
            'SELECT id FROM members WHERE deleted_at IS NULL AND id IN ({0})'.format(
                ','.join('?' for _ in presencas)
            ),
            tuple(presencas)
        )
    }
    if len(existentes) != len(presencas):
        return jsonify({'erro': 'A lista de presenças tem alunos que já não existem. Atualize a página.'}), 400

    sessao = db.get_or_create_session(class_id, data_sessao)
    db.save_attendance(sessao['id'], presencas)
    publicacao = _publicar_local('Registar presenças pelo site em {0}'.format(data_sessao))
    return jsonify({
        'sessionId': sessao['id'],
        'registados': len(presencas),
        'publicacao': publicacao,
    }), 201


def git_blob_sha(data):
    return hashlib.sha1(b'blob %d\0%s' % (len(data), data)).hexdigest()


def validate_database(raw):
    """Confirma que os dados recebidos são mesmo uma base SQLite íntegra."""
    if not raw.startswith(b'SQLite format 3\x00'):
        return 'O ficheiro enviado não é uma base de dados SQLite.'
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
    try:
        tmp.write(raw)
        tmp.close()
        conn = sqlite3.connect(tmp.name)
        try:
            result = conn.execute('PRAGMA integrity_check').fetchone()[0]
            tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            conn.close()
        if result != 'ok':
            return 'A base de dados enviada está corrompida ({0}).'.format(result)
        missing = {'classes', 'members', 'class_sessions', 'attendances', 'staff', 'visitors'} - tables
        if missing:
            return 'A base de dados enviada não tem as tabelas esperadas: {0}.'.format(
                ', '.join(sorted(missing))
            )
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    return None


def publish_to_github(raw, message):
    """Grava a base de dados no repositório GitHub. Devolve (commit, sha)."""
    api_root = 'https://api.github.com'
    headers = {
        'Authorization': 'Bearer {0}'.format(GITHUB_TOKEN),
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'ebd-api-sync',
    }
    url = '{0}/repos/{1}/contents/{2}'.format(api_root, GITHUB_REPO, GITHUB_PATH)
    params = {'ref': GITHUB_BRANCH}

    current_sha = None
    response = http_requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code == 200:
        current_sha = response.json().get('sha')
    elif response.status_code != 404:
        raise RuntimeError(
            'Não foi possível ler o repositório GitHub ({0}).'.format(response.status_code)
        )

    new_sha = git_blob_sha(raw)
    if current_sha and current_sha == new_sha:
        return None, new_sha

    payload = {'message': message, 'content': base64.b64encode(raw).decode('ascii'),
               'branch': GITHUB_BRANCH}
    if current_sha:
        payload['sha'] = current_sha

    response = http_requests.put(url, headers=headers, json=payload, timeout=60)
    if response.status_code not in (200, 201):
        try:
            detalhe = response.json().get('message', '')
        except ValueError:
            detalhe = response.text[:200]
        raise RuntimeError(
            'GitHub recusou a gravação ({0}): {1}'.format(response.status_code, detalhe)
        )
    data = response.json()
    commit = (data.get('commit') or {}).get('sha')
    return commit, (data.get('content') or {}).get('sha') or new_sha


def baixar_bd_publicada():
    """Descarrega a base de dados publicada no GitHub. Devolve bytes ou None."""
    if not (GITHUB_TOKEN and GITHUB_REPO):
        return None
    url = '{0}/repos/{1}/contents/{2}'.format(
        'https://api.github.com', GITHUB_REPO, GITHUB_PATH
    )
    headers = {
        'Authorization': 'Bearer {0}'.format(GITHUB_TOKEN),
        'Accept': 'application/vnd.github.raw',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'ebd-api-sync',
    }
    try:
        response = http_requests.get(
            url, headers=headers, params={'ref': GITHUB_BRANCH}, timeout=60
        )
    except http_requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    data = response.content
    if not data.startswith(b'SQLite format 3\x00'):
        return None
    return data


def gravar_bd_local(raw):
    """Substitui a base local para a API passar a servir os dados fundidos já."""
    handle = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite', dir=BASE_DIR)
    try:
        handle.write(raw)
        handle.close()
    except Exception:
        try:
            handle.close()
        finally:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
        return False
    try:
        os.replace(handle.name, DB_PATH)
        return True
    except OSError:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        return False


@app.route('/database', methods=['GET', 'OPTIONS'])
def descarregar_bd():
    """Cópia da base de dados actual, para o app desktop fundir com a local."""
    if request.method == 'OPTIONS':
        return ('', 204)
    if SYNC_TOKEN:
        provided = request.headers.get('X-Sync-Token', '').strip()
        if not provided or not hmac.compare_digest(provided, SYNC_TOKEN):
            return jsonify({'erro': 'Token de sincronização inválido'}), 401
    else:
        erro = authenticate()
        if erro:
            return erro
    raw = db.backup_to_bytes()
    response = app.response_class(raw, mimetype='application/octet-stream')
    response.headers['Content-Disposition'] = 'attachment; filename="database.sqlite"'
    return response


@app.route('/sync', methods=['POST', 'OPTIONS'])
def sync():
    if request.method == 'OPTIONS':
        return ('', 204)
    if not SYNC_TOKEN:
        return jsonify({'erro': 'Sincronização não configurada no servidor',
                        'detalhe': 'A variável SYNC_TOKEN não está definida'}), 503

    provided = request.headers.get('X-Sync-Token', '').strip()
    if not provided or not hmac.compare_digest(provided, SYNC_TOKEN):
        return jsonify({'erro': 'Token de sincronização inválido'}), 401

    if not (GITHUB_TOKEN and GITHUB_REPO):
        return jsonify({'erro': 'Publicação não configurada no servidor',
                        'detalhe': 'Faltam GITHUB_TOKEN e/ou GITHUB_REPO'}), 503

    payload = request.get_json(silent=True) or {}
    content = payload.get('database')
    if not content:
        return jsonify({'erro': 'Dados em falta (campo "database")'}), 400

    try:
        raw = base64.b64decode(content, validate=True)
    except Exception:
        return jsonify({'erro': 'Conteúdo inválido: não é base64 válido'}), 400

    erro = validate_database(raw)
    if erro:
        return jsonify({'erro': erro}), 400

    # Junta o que já foi registado no site: nada do que a igreja gravou pelo site
    # é substituído pela cópia antiga do computador.
    fundido = None
    publicada = baixar_bd_publicada()
    if publicada:
        try:
            raw, fundido = db.merge_bytes(raw, publicada)
        except Exception:
            fundido = None

    message = str(payload.get('message') or GITHUB_COMMIT_MESSAGE)[:200]
    try:
        commit, blob_sha = publish_to_github(raw, message)
    except http_requests.RequestException:
        return jsonify({'erro': 'Sem ligação ao GitHub. Tente novamente.'}), 502
    except RuntimeError as exc:
        return jsonify({'erro': str(exc)}), 502

    local_ok = gravar_bd_local(raw)
    if commit is not None or blob_sha:
        db.mark_all_synced()

    if commit is None:
        return jsonify({'status': 'sem_alteracoes', 'fundido': fundido,
                        'sha256': hashlib.sha256(raw).hexdigest()})
    return jsonify({
        'status': 'publicado',
        'commit': commit,
        'sha': blob_sha,
        'bytes': len(raw),
        'fundido': fundido,
        'local': local_ok,
        'sha256': hashlib.sha256(raw).hexdigest(),
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False)