import os
import sqlite3
from datetime import datetime
from urllib.parse import quote
from flask import Flask, jsonify, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.sqlite')

app = Flask(__name__)
app.json.ensure_ascii = False


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


@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


@app.route('/', methods=['GET', 'OPTIONS'])
def home():
    if request.method == 'OPTIONS':
        return ('', 204)
    return jsonify({
        'nome': 'API EBD - leitura',
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
def sessions():
    if request.method == 'OPTIONS':
        return ('', 204)
    sql = '''
        SELECT cs.id, cs.class_id, c.name AS turma, cs.date, cs.visitors_count
        FROM class_sessions cs
        JOIN classes c ON c.id = cs.class_id AND c.deleted_at IS NULL
    '''
    args = []
    class_id = request.args.get('class_id')
    if class_id:
        sql += ' WHERE cs.class_id = ?'
        args.append(class_id)
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    if date_from and not args:
        sql += ' WHERE'
    elif date_from and args:
        sql += ' AND'
    if date_from:
        sql += ' cs.date >= ?'
        args.append(date_from)
        if date_to:
            sql += ' AND cs.date <= ?'
            args.append(date_to)
    elif date_to:
        sql += ' WHERE cs.date <= ?'
        args.append(date_to)
    sql += ' ORDER BY cs.date DESC, cs.class_id'
    sessions = query(sql, args)
    stats = session_stats()
    for s in sessions:
        st = stats.get(s['id'], {})
        s['presencas'] = st.get('presentes', 0) or 0
        s['matriculados'] = st.get('total', 0) or 0
    return jsonify(sessions)


@app.route('/sessions/<session_id>', methods=['GET', 'OPTIONS'])
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
def members():
    if request.method == 'OPTIONS':
        return ('', 204)
    result = query('''
        SELECT m.id, m.name, m.birth_date, m.role, m.class_id, c.name AS turma
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False)