import sqlite3
import uuid
import json
import tempfile
from datetime import datetime
import os
import sys

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.sqlite')

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_age(birth_date_str):
    """Calcula a idade baseada na data de nascimento (YYYY-MM-DD).
    Devolve None quando a data está vazia ou é inválida."""
    if not birth_date_str:
        return None
    try:
        birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d")
        today = datetime.today()
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    except (ValueError, TypeError):
        return None

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS classes (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        professor_name TEXT,
        age_min INTEGER,
        age_max INTEGER,
        created_at TEXT NOT NULL,
        synced INTEGER NOT NULL DEFAULT 0,
        deleted_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS members (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        birth_date TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT 'Aluno',
        class_id TEXT,
        created_at TEXT NOT NULL,
        synced INTEGER NOT NULL DEFAULT 0,
        deleted_at TEXT,
        FOREIGN KEY(class_id) REFERENCES classes(id)
    )
    """)

    # Migração: se a tabela members já existia sem as colunas novas, adicioná-las
    try:
        cursor.execute("ALTER TABLE members ADD COLUMN birth_date TEXT NOT NULL DEFAULT ''")
    except:
        pass  # Já existe
    try:
        cursor.execute("ALTER TABLE members ADD COLUMN class_id TEXT")
    except:
        pass  # Já existe
    try:
        cursor.execute("ALTER TABLE members ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE members ADD COLUMN marital_status TEXT NOT NULL DEFAULT ''")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE members ADD COLUMN baptized INTEGER NOT NULL DEFAULT 0")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE members ADD COLUMN baptism_date TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE members ADD COLUMN profession TEXT NOT NULL DEFAULT ''")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE members ADD COLUMN enrolled_at TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE members ADD COLUMN photo TEXT")
    except:
        pass
    # Preenche a data de inscrição com a data de criação dos registos antigos
    cursor.execute("UPDATE members SET enrolled_at = created_at WHERE enrolled_at IS NULL")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS class_sessions (
        id TEXT PRIMARY KEY,
        class_id TEXT NOT NULL,
        date TEXT NOT NULL,
        visitors_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        synced INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(class_id) REFERENCES classes(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendances (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        member_id TEXT NOT NULL,
        is_present INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        synced INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(session_id) REFERENCES class_sessions(id),
        FOREIGN KEY(member_id) REFERENCES members(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS staff (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        phone TEXT,
        class_id TEXT,
        created_at TEXT NOT NULL,
        synced INTEGER NOT NULL DEFAULT 0,
        deleted_at TEXT,
        FOREIGN KEY(class_id) REFERENCES classes(id)
    )
    """)
    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_staff_class_role
    ON staff(class_id, role) WHERE deleted_at IS NULL
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS visitors (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        synced INTEGER NOT NULL DEFAULT 0,
        deleted_at TEXT,
        FOREIGN KEY(session_id) REFERENCES class_sessions(id)
    )
    """)

    conn.commit()
    conn.close()
    
    seed_classes()
    update_members_classes()

def seed_classes():
    """Popula/atualiza as 5 turmas da EBD."""
    classes_data = [
        {"id": "moises", "name": "Moisés", "min": 0, "max": 5},
        {"id": "samuel", "name": "Samuel", "min": 6, "max": 10},
        {"id": "jose", "name": "José", "min": 11, "max": 14},
        {"id": "timoteo", "name": "Timóteo", "min": 15, "max": 17},
        {"id": "paulo", "name": "Paulo", "min": 18, "max": 120}
    ]
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    for c in classes_data:
        cursor.execute("SELECT id FROM classes WHERE id = ?", (c["id"],))
        if cursor.fetchone():
            cursor.execute(
                "UPDATE classes SET age_min = ?, age_max = ? WHERE id = ?",
                (c["min"], c["max"], c["id"])
            )
        else:
            cursor.execute(
                "INSERT INTO classes (id, name, age_min, age_max, created_at) VALUES (?, ?, ?, ?, ?)",
                (c["id"], c["name"], c["min"], c["max"], now)
            )
    conn.commit()
    conn.close()

def get_class_for_age(age):
    if age is None:
        return None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name FROM classes WHERE ? >= age_min AND ? <= age_max ORDER BY age_min",
        (age, age)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def add_member(name, birth_date, role="Aluno", phone="", marital_status="",
               baptized=False, baptism_date="", profession=""):
    """Adiciona membro e descobre a classe automaticamente."""
    age = calculate_age(birth_date)
    turma = get_class_for_age(age)
    class_id = turma['id'] if turma else None
    
    conn = get_connection()
    cursor = conn.cursor()
    new_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    
    cursor.execute(
        """INSERT INTO members
           (id, name, birth_date, role, class_id, created_at, synced,
            phone, marital_status, baptized, baptism_date, profession, enrolled_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (new_id, name, birth_date, role, class_id, now, 0,
         phone, marital_status, 1 if baptized else 0, baptism_date or None,
         profession, now)
    )
    conn.commit()
    conn.close()
    return new_id, turma

def update_member(member_id, name, birth_date, phone="", marital_status="",
                  baptized=False, baptism_date="", profession=""):
    """Atualiza os dados do membro e recalcula a classe pela idade."""
    age = calculate_age(birth_date)
    turma = get_class_for_age(age)
    class_id = turma['id'] if turma else None

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE members SET
             name = ?, birth_date = ?, class_id = ?, phone = ?,
             marital_status = ?, baptized = ?, baptism_date = ?, profession = ?,
             synced = 0
           WHERE id = ?""",
        (name, birth_date, class_id, phone,
         marital_status, 1 if baptized else 0, baptism_date or None,
         profession, member_id)
    )
    conn.commit()


    conn.close()
    return turma

def set_member_photo(member_id, photo):
    """Guarda a foto do aluno (data URL JPEG) e marca como não publicada."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE members SET photo = ?, synced = 0 WHERE id = ? AND deleted_at IS NULL",
        (photo, member_id)
    )
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return bool(changed)

def get_member_photo(member_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT photo FROM members WHERE id = ? AND deleted_at IS NULL",
        (member_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row['photo'] if row else None

def get_all_members():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members WHERE deleted_at IS NULL")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_member_by_id(member_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members WHERE id = ? AND deleted_at IS NULL", (member_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_members_by_class(class_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members WHERE class_id = ? AND deleted_at IS NULL ORDER BY name", (class_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_classes():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM classes WHERE deleted_at IS NULL ORDER BY age_min")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_members_classes():
    """Roda na inicialização para mover alunos de turma caso a idade tenha passado."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, birth_date, class_id FROM members WHERE deleted_at IS NULL AND birth_date != ''")
    members = cursor.fetchall()
    
    for m in members:
        age = calculate_age(m['birth_date'])
        correct_turma = get_class_for_age(age)
        if correct_turma and m['class_id'] != correct_turma['id']:
            cursor.execute("UPDATE members SET class_id = ? WHERE id = ?", (correct_turma['id'], m['id']))
            
    conn.commit()
    conn.close()

def get_or_create_session(class_id, date):
    """Devolve a sessão (aula) da classe na data indicada, criando-a se não existir."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM class_sessions WHERE class_id = ? AND date = ?", (class_id, date))
    row = cursor.fetchone()
    if row:
        conn.close()
        return dict(row)

    new_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO class_sessions (id, class_id, date, visitors_count, created_at, synced) VALUES (?, ?, ?, 0, ?, 0)",
        (new_id, class_id, date, now)
    )
    conn.commit()
    cursor.execute("SELECT * FROM class_sessions WHERE id = ?", (new_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)

def get_recent_sessions(class_id, limit=4):
    """Sessões mais recentes da classe, em ordem cronológica (mais antiga -> mais nova)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM class_sessions WHERE class_id = ? ORDER BY date DESC LIMIT ?",
        (class_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]

def get_attendance_map(session_ids):
    """Devolve {(session_id, member_id): is_present} para as sessões indicadas."""
    if not session_ids:
        return {}
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in session_ids)
    cursor.execute(
        f"SELECT session_id, member_id, is_present FROM attendances WHERE session_id IN ({placeholders})",
        session_ids
    )
    result = { (r["session_id"], r["member_id"]): bool(r["is_present"]) for r in cursor.fetchall() }
    conn.close()
    return result

def save_attendance(session_id, presences):
    """Grava as presenças de uma sessão. `presences` = {member_id: bool}."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    for member_id, is_present in presences.items():
        value = 1 if is_present else 0
        cursor.execute("SELECT id FROM attendances WHERE session_id = ? AND member_id = ?", (session_id, member_id))
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE attendances SET is_present = ?, synced = 0 WHERE id = ?", (value, row["id"]))
        else:
            cursor.execute(
                "INSERT INTO attendances (id, session_id, member_id, is_present, created_at, synced) VALUES (?, ?, ?, ?, ?, 0)",
                (str(uuid.uuid4()), session_id, member_id, value, now)
            )
    conn.commit()
    conn.close()

def set_staff(name, role, class_id, phone=""):
    """Regista/atualiza o professor ou auxiliar da turma (máx. 1 por função/turma).
    Se a vaga já estiver preenchida, substitui o ocupante atual."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        "SELECT id FROM staff WHERE class_id = ? AND role = ? AND deleted_at IS NULL",
        (class_id, role)
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            "UPDATE staff SET name = ?, phone = ?, synced = 0 WHERE id = ?",
            (name, phone, row["id"])
        )
        staff_id = row["id"]
        created = False
    else:
        staff_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO staff (id, name, role, phone, class_id, created_at, synced) VALUES (?, ?, ?, ?, ?, ?, 0)",
            (staff_id, name, role, phone, class_id, now)
        )
        created = True
    conn.commit()
    conn.close()
    return staff_id, created

def get_staff_by_class(class_id):
    """Devolve {role: staff_row} para a turma (apenas registos ativos)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM staff WHERE class_id = ? AND deleted_at IS NULL", (class_id,))
    rows = cursor.fetchall()
    conn.close()
    return {r["role"]: dict(r) for r in rows}

def get_all_staff():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, c.name AS class_name FROM staff s
        LEFT JOIN classes c ON c.id = s.class_id
        WHERE s.deleted_at IS NULL
        ORDER BY c.age_min, s.role
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def remove_staff(staff_id):
    """Libera a vaga (soft delete)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE staff SET deleted_at = ?, synced = 0 WHERE id = ?", (datetime.now().isoformat(), staff_id))
    conn.commit()
    conn.close()

def get_sessions_by_class(class_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM class_sessions WHERE class_id = ? ORDER BY date DESC", (class_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_session_by_id(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM class_sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def sync_visitors_count(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS n FROM visitors WHERE session_id = ? AND deleted_at IS NULL", (session_id,))
    count = cursor.fetchone()["n"]
    cursor.execute("UPDATE class_sessions SET visitors_count = ?, synced = 0 WHERE id = ?", (count, session_id))
    conn.commit()
    conn.close()
    return count

def add_visitor(session_id, name):
    conn = get_connection()
    cursor = conn.cursor()
    visitor_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO visitors (id, session_id, name, created_at, synced, deleted_at) VALUES (?, ?, ?, ?, 0, NULL)",
        (visitor_id, session_id, name, now)
    )
    conn.commit()
    conn.close()
    sync_visitors_count(session_id)
    return visitor_id

def get_visitors_by_session(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM visitors WHERE session_id = ? AND deleted_at IS NULL ORDER BY created_at",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_visitor(visitor_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT session_id FROM visitors WHERE id = ?", (visitor_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return
    session_id = row["session_id"]
    cursor.execute("UPDATE visitors SET deleted_at = ?, synced = 0 WHERE id = ?", (datetime.now().isoformat(), visitor_id))
    conn.commit()
    conn.close()
    sync_visitors_count(session_id)

def delete_member(member_id):
    """Remove o aluno da listagem (soft delete) sem apagar o histórico."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE members SET deleted_at = ?, synced = 0 WHERE id = ? AND deleted_at IS NULL",
        (datetime.now().isoformat(), member_id)
    )
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return bool(changed)

SYNCED_TABLES = ('classes', 'members', 'class_sessions', 'attendances', 'staff', 'visitors')

def pending_changes():
    """N.º de registos ainda não publicados no site."""
    conn = get_connection()
    cursor = conn.cursor()
    total = 0
    for table in SYNCED_TABLES:
        try:
            cursor.execute("SELECT COUNT(*) FROM {0} WHERE synced = 0".format(table))
            total += cursor.fetchone()[0]
        except sqlite3.OperationalError:
            pass
    conn.close()
    return total

def mark_all_synced():
    conn = get_connection()
    cursor = conn.cursor()
    for table in SYNCED_TABLES:
        try:
            cursor.execute("UPDATE {0} SET synced = 1 WHERE synced = 0".format(table))
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()

def backup_to_bytes():
    """Cópia consistente da base de dados, mesmo com a app a escrever."""
    handle = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
    handle.close()
    try:
        destino = sqlite3.connect(handle.name)
        try:
            origem = get_connection()
            try:
                origem.backup(destino)
            finally:
                origem.close()
            destino.commit()
        finally:
            destino.close()
        with open(handle.name, 'rb') as ficheiro:
            return ficheiro.read()
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass


def instalar_bytes(raw):
    """Substitui a base de dados local por `raw` de forma atómica."""
    if not raw.startswith(b'SQLite format 3\x00'):
        raise ValueError('A base de dados recebida não é válida.')
    destino = os.path.abspath(DB_PATH)
    pasta = os.path.dirname(destino) or '.'
    handle = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite', dir=pasta)
    try:
        handle.write(raw)
        handle.close()
        conn = sqlite3.connect(handle.name)
        try:
            try:
                verificacao = conn.execute('PRAGMA integrity_check').fetchone()[0]
            except sqlite3.DatabaseError as erro:
                raise ValueError('A base de dados recebida está corrompida ({0}).'.format(erro))
        finally:
            conn.close()
        if verificacao != 'ok':
            raise ValueError('A base de dados recebida está corrompida ({0}).'.format(verificacao))
        os.replace(handle.name, destino)
    finally:
        try:
            if os.path.exists(handle.name):
                os.unlink(handle.name)
        except OSError:
            pass
    for sufixo in ('-wal', '-shm'):
        obsoleto = destino + sufixo
        if os.path.exists(obsoleto):
            try:
                os.unlink(obsoleto)
            except OSError:
                pass
    return destino


def _pragma_table_info(conn, table, schema=''):
    prefix = '{0}.'.format(schema) if schema else ''
    existe = conn.execute(
        "SELECT name FROM {0}sqlite_master WHERE type = 'table' AND name = ?".format(prefix),
        (table,)
    ).fetchone()
    if not existe:
        return []
    return [
        {'name': row[1], 'pk': bool(row[5])}
        for row in conn.execute('PRAGMA {0}table_info({1})'.format(prefix, table))
    ]


def _row_differs(actual, remota, comuns):
    return any(actual[c] != remota[c] for c in comuns)


def merge_bytes(base_raw, remote_raw):
    """Junta `remote_raw` (versão publicada/site) em `base_raw` e devolve o resultado.

    Regra: o que a app ainda não publicou (synced = 0) mantém-se; o resto vem do
    remoto, que é a versão já publicada. Sessões com a mesma turma e data são
    reutilizadas em vez de duplicadas, e os membros são emparelhados por nome +
    data de nascimento quando os identificadores não coincidem.
    Devolve (bytes do resultado, {tabela: {'inseridas': n, 'actualizadas': n}}).
    """
    tmp_base = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
    tmp_base.close()
    tmp_remoto = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
    tmp_remoto.close()
    try:
        with open(tmp_base.name, 'wb') as ficheiro:
            ficheiro.write(base_raw)
        with open(tmp_remoto.name, 'wb') as ficheiro:
            ficheiro.write(remote_raw)

        conn = sqlite3.connect(tmp_base.name)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('ATTACH DATABASE ? AS remoto', (tmp_remoto.name,))
            resumo = {}

            # 1) Sessões: reaproveita a sessão local da mesma turma e data
            mapa_sessoes = {}
            if _pragma_table_info(conn, 'class_sessions') and _pragma_table_info(conn, 'class_sessions', 'remoto'):
                locais = {r['id']: r for r in conn.execute('SELECT * FROM class_sessions')}
                por_chave = {(r['class_id'], r['date']): r['id'] for r in locais.values()}
                inseridas = actualizadas = 0
                for rem in conn.execute('SELECT * FROM remoto.class_sessions').fetchall():
                    actual = locais.get(rem['id'])
                    if actual is not None:
                        mapa_sessoes[rem['id']] = actual['id']
                        if actual['synced'] == 1 and _row_differs(actual, rem, ('date', 'class_id')):
                            conn.execute('UPDATE class_sessions SET date = ?, class_id = ?, synced = 1 WHERE id = ?',
                                         (rem['date'], rem['class_id'], actual['id']))
                            actualizadas += 1
                        continue
                    chave = (rem['class_id'], rem['date'])
                    if chave in por_chave:
                        mapa_sessoes[rem['id']] = por_chave[chave]
                        continue
                    try:
                        conn.execute(
                            'INSERT INTO class_sessions (id, class_id, date, visitors_count, created_at, synced) '
                            'VALUES (?, ?, ?, ?, ?, 1)',
                            (rem['id'], rem['class_id'], rem['date'], rem['visitors_count'], rem['created_at'])
                        )
                    except (sqlite3.IntegrityError, IndexError, KeyError):
                        continue
                    mapa_sessoes[rem['id']] = rem['id']
                    por_chave[chave] = rem['id']
                    inseridas += 1
                resumo['class_sessions'] = {'inseridas': inseridas, 'actualizadas': actualizadas}

            # 2) Tabelas em que a chave é o identificador
            mapa_membros = {}
            for tabela in ('classes', 'members', 'staff'):
                info_local = _pragma_table_info(conn, tabela)
                info_remoto = _pragma_table_info(conn, tabela, 'remoto')
                if not info_local or not info_remoto:
                    continue
                colunas_remotas = {r['name'] for r in info_remoto}
                comuns = [c['name'] for c in info_local if c['name'] in colunas_remotas]
                pk = next((c['name'] for c in info_local if c['pk']), 'id')
                if pk not in comuns:
                    continue
                locais = {r[pk]: r for r in conn.execute('SELECT * FROM {0}'.format(tabela))}
                inseridas = actualizadas = 0
                emparelar_membros = tabela == 'members'

                def _inserir(rem, extras=None):
                    valores = []
                    for coluna in comuns:
                        if extras and coluna in extras:
                            valores.append(extras[coluna])
                        elif coluna == 'synced':
                            valores.append(1)
                        else:
                            valores.append(rem[coluna])
                    conn.execute(
                        'INSERT INTO {0} ({1}) VALUES ({2})'.format(
                            tabela, ', '.join('"{0}"'.format(c) for c in comuns),
                            ', '.join('?' for _ in comuns)
                        ),
                        valores
                    )

                for rem in conn.execute('SELECT * FROM remoto.{0}'.format(tabela)).fetchall():
                    actual = locais.get(rem[pk])
                    if emparelar_membros and actual is None:
                        pareado = conn.execute(
                            'SELECT id FROM members WHERE name = ? AND birth_date = ? AND deleted_at IS NULL '
                            'ORDER BY created_at LIMIT 1',
                            (rem['name'], rem['birth_date'])
                        ).fetchone()
                        if pareado:
                            mapa_membros[rem[pk]] = pareado['id']
                            continue
                    if actual is None:
                        try:
                            _inserir(rem)
                        except sqlite3.IntegrityError:
                            continue
                        if emparelar_membros:
                            mapa_membros[rem[pk]] = rem[pk]
                        inseridas += 1
                        continue
                    if emparelar_membros:
                        mapa_membros[rem[pk]] = actual[pk]
                    difere = [c for c in comuns if c != pk]
                    if actual['synced'] == 1 and difere and _row_differs(actual, rem, difere):
                        conn.execute(
                            'UPDATE {0} SET {1} WHERE "{2}" = ?'.format(
                                tabela, ', '.join('"{0}" = ?'.format(c) for c in difere), pk
                            ),
                            [rem[c] for c in difere] + [rem[pk]]
                        )
                        actualizadas += 1
                resumo[tabela] = {'inseridas': inseridas, 'actualizadas': actualizadas}

            # 3) Presenças (aproveita as sessões e membros já fundidos)
            if _pragma_table_info(conn, 'attendances') and _pragma_table_info(conn, 'attendances', 'remoto'):
                existentes = {
                    (r['session_id'], r['member_id']): r
                    for r in conn.execute('SELECT * FROM attendances')
                }
                membros = {r['id'] for r in conn.execute('SELECT id FROM members')}
                sessoes = {r['id'] for r in conn.execute('SELECT id FROM class_sessions')}
                inseridos = set()
                inseridas = actualizadas = 0
                for rem in conn.execute('SELECT * FROM remoto.attendances').fetchall():
                    sessao = mapa_sessoes.get(rem['session_id'], rem['session_id'])
                    membro = mapa_membros.get(rem['member_id'], rem['member_id'])
                    if membro not in membros or sessao not in sessoes:
                        continue
                    par = (sessao, membro)
                    if par in inseridos:
                        continue
                    actual = existentes.get(par)
                    if actual is None:
                        try:
                            conn.execute(
                                'INSERT INTO attendances (id, session_id, member_id, is_present, created_at, synced) '
                                'VALUES (?, ?, ?, ?, ?, 1)',
                                (rem['id'], sessao, membro, rem['is_present'], rem['created_at'])
                            )
                        except sqlite3.IntegrityError:
                            continue
                        inseridos.add(par)
                        inseridas += 1
                    elif actual['synced'] == 1 and actual['is_present'] != rem['is_present']:
                        conn.execute('UPDATE attendances SET is_present = ?, synced = 1 WHERE id = ?',
                                     (rem['is_present'], actual['id']))
                        actualizadas += 1
                resumo['attendances'] = {'inseridas': inseridas, 'actualizadas': actualizadas}

            # 4) Visitantes (aproveita as sessões fundidas, sem duplicar nomes)
            if _pragma_table_info(conn, 'visitors') and _pragma_table_info(conn, 'visitors', 'remoto'):
                nomes = {
                    (r['session_id'], r['name'])
                    for r in conn.execute('SELECT session_id, name FROM visitors WHERE deleted_at IS NULL')
                }
                existentes = {r['id'] for r in conn.execute('SELECT id FROM visitors')}
                inseridas = actualizadas = 0
                for rem in conn.execute('SELECT * FROM remoto.visitors').fetchall():
                    sessao = mapa_sessoes.get(rem['session_id'])
                    if not sessao:
                        continue
                    if rem['id'] in existentes:
                        continue
                    if (sessao, rem['name']) in nomes:
                        continue
                    try:
                        conn.execute(
                            'INSERT INTO visitors (id, session_id, name, created_at, synced, deleted_at) '
                            'VALUES (?, ?, ?, ?, 1, NULL)',
                            (rem['id'], sessao, rem['name'], rem['created_at'])
                        )
                    except sqlite3.IntegrityError:
                        continue
                    existentes.add(rem['id'])
                    nomes.add((sessao, rem['name']))
                    inseridas += 1
                resumo['visitors'] = {'inseridas': inseridas, 'actualizadas': actualizadas}

            conn.commit()
        finally:
            conn.close()

        with open(tmp_base.name, 'rb') as ficheiro:
            return ficheiro.read(), resumo
    finally:
        for caminho in (tmp_base.name, tmp_remoto.name):
            try:
                os.unlink(caminho)
            except OSError:
                pass


SYNC_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sync_state.json')

def load_sync_state():
    try:
        with open(SYNC_STATE_PATH, encoding='utf-8') as ficheiro:
            estado = json.load(ficheiro)
            return estado if isinstance(estado, dict) else {}
    except (OSError, ValueError):
        return {}

def save_sync_state(estado):
    try:
        with open(SYNC_STATE_PATH, 'w', encoding='utf-8') as ficheiro:
            json.dump(estado, ficheiro, ensure_ascii=False, indent=2)
    except OSError:
        pass

# Inicializa ao importar
init_db()
