import sqlite3
import uuid
from datetime import datetime
import os

DB_PATH = 'database.sqlite'

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_age(birth_date_str):
    """Calcula a idade baseada na data de nascimento (YYYY-MM-DD)."""
    try:
        birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d")
        today = datetime.today()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        return age
    except:
        return 0

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
                "UPDATE classes SET name = ?, age_min = ?, age_max = ? WHERE id = ?",
                (c["name"], c["min"], c["max"], c["id"])
            )
        else:
            cursor.execute(
                "INSERT INTO classes (id, name, age_min, age_max, created_at) VALUES (?, ?, ?, ?, ?)",
                (c["id"], c["name"], c["min"], c["max"], now)
            )
    conn.commit()
    conn.close()

def get_class_for_age(age):
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

# Inicializa ao importar
init_db()
