import flet as ft
import database as db
from datetime import datetime

def main(page: ft.Page):
    page.title = "Secretaria EBD"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = ft.Colors.WHITE
    page.padding = 0
    page.window.width = 1400
    page.window.height = 850

    # Estado da chamada: sessões exibidas e checkboxes por (sessão, aluno)
    chamada_state = {"sessions": [], "checkboxes": {}}
    # Estado dos visitantes: sessão selecionada
    visit_state = {"session_id": None}

    # =============================================
    # FUNÇÕES / HANDLERS
    # =============================================

    def show_snack(msg, color=ft.Colors.GREEN_600):
        page.overlay.append(ft.SnackBar(ft.Text(msg), bgcolor=color, open=True))
        page.update()

    def parse_date_br(value):
        """Converte DD/MM/AAAA em YYYY-MM-DD. Devolve None se inválida."""
        try:
            parts = value.split('/')
            if len(parts) != 3:
                return None
            iso = f"{parts[2]}-{parts[1]}-{parts[0]}"
            datetime.strptime(iso, "%Y-%m-%d")
            return iso
        except:
            return None

    def format_date_br(iso):
        try:
            return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m")
        except:
            return iso

    def format_date_full(iso):
        try:
            return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
        except:
            return iso

    # ---------- ALUNOS ----------

    def handle_cadastro(e):
        if not nome_input.value or not data_nasc_input.value:
            show_snack("Preencha todos os campos!", ft.Colors.RED)
            return

        iso_date = parse_date_br(data_nasc_input.value)
        if not iso_date:
            show_snack("Data inválida. Use o formato DD/MM/AAAA", ft.Colors.RED)
            return

        age = db.calculate_age(iso_date)
        is_adult = bool(age and age >= 18)

        phone = numero_input.value.strip()
        marital = estado_civil_dropdown.value if is_adult else ""
        baptized = bool(batizado_checkbox.value) if is_adult else False
        baptism_date = ""
        if baptized:
            baptism_date = parse_date_br(data_batismo_input.value) or ""
            if data_batismo_input.value and not baptism_date:
                show_snack("Data de batismo inválida. Use o formato DD/MM/AAAA", ft.Colors.RED)
                return
        profession = profissao_input.value.strip() if is_adult else ""

        new_id, turma = db.add_member(
            nome_input.value, iso_date,
            phone=phone, marital_status=marital,
            baptized=baptized, baptism_date=baptism_date, profession=profession,
        )

        if turma:
            show_snack(f"Aluno {nome_input.value} cadastrado na Classe: {turma['name']}!")
        else:
            show_snack("Aluno cadastrado, mas a idade não se encaixa nas turmas.", ft.Colors.ORANGE)

        for f in (nome_input, data_nasc_input, numero_input, profissao_input,
                  data_batismo_input):
            f.value = ""
        estado_civil_dropdown.value = None
        batizado_checkbox.value = False
        data_batismo_input.visible = False
        adultos_container.visible = False
        load_alunos()
        load_turmas()
        page.update()

    def handle_birth_change(e):
        """Mostra/oculta os campos de adulto conforme a idade."""
        iso = parse_date_br(data_nasc_input.value)
        age = db.calculate_age(iso) if iso else None
        adultos_container.visible = bool(age and age >= 18)
        page.update()

    def handle_batismo_change(e):
        data_batismo_input.visible = bool(e.control.value)
        page.update()

    # ---------- EDIÇÃO DE ALUNO ----------

    def open_edit_dialog(member):
        if not member:
            return
        edit_state["member_id"] = member['id']
        edit_nome_input.value = member['name']
        edit_nasc_input.value = format_date_full(member['birth_date']) if member['birth_date'] else ""
        edit_numero_input.value = member['phone'] or ""
        edit_estado_civil_dropdown.value = member['marital_status'] or None
        edit_batizado_checkbox.value = bool(member['baptized'])
        edit_data_batismo_input.value = format_date_full(member['baptism_date']) if member.get('baptism_date') else ""
        edit_data_batismo_input.visible = bool(member['baptized'])
        edit_profissao_input.value = member['profession'] or ""

        age = db.calculate_age(member['birth_date']) if member['birth_date'] else None
        edit_adultos_container.visible = bool(age and age >= 18)
        edit_dialog.open = True
        page.update()

    def handle_edit_birth_change(e):
        iso = parse_date_br(edit_nasc_input.value)
        age = db.calculate_age(iso) if iso else None
        edit_adultos_container.visible = bool(age and age >= 18)
        page.update()

    def handle_edit_batismo_change(e):
        edit_data_batismo_input.visible = bool(e.control.value)
        page.update()

    def save_edit_dialog(e):
        if not edit_nome_input.value or not edit_nasc_input.value:
            show_snack("Nome e data de nascimento são obrigatórios!", ft.Colors.RED)
            return
        iso = parse_date_br(edit_nasc_input.value)
        if not iso:
            show_snack("Data inválida. Use o formato DD/MM/AAAA", ft.Colors.RED)
            return
        age = db.calculate_age(iso)
        is_adult = bool(age and age >= 18)

        baptized = bool(edit_batizado_checkbox.value) if is_adult else False
        baptism_date = ""
        if baptized:
            baptism_date = parse_date_br(edit_data_batismo_input.value) or ""
            if edit_data_batismo_input.value and not baptism_date:
                show_snack("Data de batismo inválida. Use o formato DD/MM/AAAA", ft.Colors.RED)
                return

        turma = db.update_member(
            edit_state["member_id"],
            edit_nome_input.value.strip(),
            iso,
            phone=edit_numero_input.value.strip(),
            marital_status=(edit_estado_civil_dropdown.value or "") if is_adult else "",
            baptized=baptized,
            baptism_date=baptism_date,
            profession=edit_profissao_input.value.strip() if is_adult else "",
        )
        edit_dialog.open = False
        if turma:
            show_snack(f"{edit_nome_input.value} atualizado na Classe: {turma['name']}!")
        else:
            show_snack("Dados atualizados, mas a idade não se encaixa nas turmas.", ft.Colors.ORANGE)
        load_alunos()
        load_turmas()
        page.update()

    def load_alunos():
        alunos_table.rows.clear()
        classes = {c['id']: c['name'] for c in db.get_classes()}
        members = db.get_all_members()
        members.sort(key=lambda m: (m['name'] or '').lower())

        for i, m in enumerate(members):
            birth = format_date_full(m['birth_date']) if m['birth_date'] else "-"
            idade = db.calculate_age(m['birth_date']) if m['birth_date'] else "-"
            classe = classes.get(m['class_id'], "Sem turma")
            phone = m['phone'] or "-"
            inscricao = format_date_full(m['enrolled_at'][:10]) if m.get('enrolled_at') else "-"
            alunos_table.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(i+1))),
                    ft.DataCell(ft.Text(m['name'])),
                    ft.DataCell(ft.Text(birth)),
                    ft.DataCell(ft.Text(str(idade))),
                    ft.DataCell(ft.Text(classe)),
                    ft.DataCell(ft.Text(phone)),
                    ft.DataCell(ft.Text(inscricao)),
                    ft.DataCell(ft.IconButton(
                        ft.Icons.EDIT_OUTLINED,
                        icon_color=ft.Colors.BLUE_700,
                        tooltip="Editar aluno",
                        on_click=lambda e, mid=m['id']: open_edit_dialog(db.get_member_by_id(mid)),
                    )),
                ])
            )
        alunos_count.value = f"{len(members)} alunos matriculados"
        page.update()

    # ---------- TURMAS ----------

    def load_turmas():
        turmas_list.controls.clear()
        classes = db.get_classes()

        for c in classes:
            alunos = db.get_members_by_class(c['id'])
            staff = db.get_staff_by_class(c['id'])
            professor = staff.get('Professor')
            auxiliar = staff.get('Auxiliar')

            prof_text = professor['name'] if professor else "—"
            aux_text = auxiliar['name'] if auxiliar else "—"

            turmas_list.controls.append(
                ft.Card(
                    elevation=1,
                    bgcolor=ft.Colors.WHITE,
                    content=ft.Container(
                        padding=20,
                        content=ft.Column([
                            ft.Row([
                                ft.Text(c['name'], size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                                ft.Container(),
                                ft.Chip(
                                    label=ft.Text(f"{len(alunos)} alunos"),
                                    bgcolor=ft.Colors.BLUE_50,
                                ),
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            ft.Text(f"Faixa etária: {c['age_min']} a {c['age_max']} anos",
                                    size=13, color=ft.Colors.GREY_700),
                            ft.Divider(height=14),
                            ft.Row([
                                ft.Row([ft.Icon(ft.Icons.SCHOOL, size=18, color=ft.Colors.BLUE_700),
                                        ft.Text(f"Professor: {prof_text}", size=14)], spacing=6),
                                ft.Container(),
                                ft.Row([ft.Icon(ft.Icons.GROUPS, size=18, color=ft.Colors.GREEN_700),
                                        ft.Text(f"Auxiliar: {aux_text}", size=14)], spacing=6),
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                        ], spacing=6)
                    )
                )
            )
        page.update()

    # ---------- EQUIPE (PROFESSORES / AUXILIARES) ----------

    def load_staff_dropdowns():
        classes = db.get_classes()
        staff_turma_dropdown.options = [ft.dropdown.Option(key=c['id'], text=c['name']) for c in classes]
        staff_role_dropdown.options = [
            ft.dropdown.Option(key="Professor", text="Professor"),
            ft.dropdown.Option(key="Auxiliar", text="Auxiliar"),
        ]

    def handle_staff_submit(e):
        name = staff_nome_input.value.strip()
        role = staff_role_dropdown.value
        class_id = staff_turma_dropdown.value
        phone = staff_phone_input.value.strip()

        if not name or not role or not class_id:
            show_snack("Preencha nome, função e turma!", ft.Colors.RED)
            return

        staff_id, created = db.set_staff(name, role, class_id, phone)
        label = "Professor" if role == "Professor" else "Auxiliar"

        if created:
            show_snack(f"{label} {name} cadastrado(a) na turma.")
        else:
            show_snack(f"{label} da turma atualizado(a): {name}.")

        staff_nome_input.value = ""
        staff_phone_input.value = ""
        load_equipe()
        load_turmas()
        page.update()

    def handle_remove_staff(staff_id):
        db.remove_staff(staff_id)
        load_equipe()
        load_turmas()
        show_snack("Vaga liberada na turma.")

    def build_staff_slot(role, staff_row):
        if staff_row:
            return ft.Container(
                padding=12,
                border_radius=10,
                bgcolor=ft.Colors.BLUE_50,
                content=ft.Row([
                    ft.Icon(ft.Icons.SCHOOL if role == "Professor" else ft.Icons.GROUPS,
                            color=ft.Colors.BLUE_700),
                    ft.Column([
                        ft.Text(role, size=12, color=ft.Colors.GREY_700),
                        ft.Text(staff_row['name'], weight=ft.FontWeight.W_600, size=15),
                        ft.Text(staff_row['phone'] or "", size=12, color=ft.Colors.GREY_600),
                    ], spacing=0, expand=True),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE,
                        icon_color=ft.Colors.RED_400,
                        tooltip="Liberar vaga",
                        on_click=lambda e, sid=staff_row['id']: handle_remove_staff(sid),
                    ),
                ], spacing=10)
            )
        return ft.Container(
            padding=12,
            border_radius=10,
            border=ft.Border.all(1, ft.Colors.GREY_300),
            content=ft.Row([
                ft.Icon(ft.Icons.SCHOOL if role == "Professor" else ft.Icons.GROUPS,
                        color=ft.Colors.GREY_400),
                ft.Text(f"{role}: vaga aberta", color=ft.Colors.GREY_500, expand=True),
            ], spacing=10)
        )

    def load_equipe():
        equipe_list.controls.clear()
        staff = db.get_staff_by_class
        classes = db.get_classes()

        if not classes:
            equipe_list.controls.append(ft.Text("Nenhuma turma criada.", color=ft.Colors.GREY_600))
        else:
            for c in classes:
                by_role = staff(c['id'])
                card = ft.Card(
                    width=380,
                    elevation=1,
                    bgcolor=ft.Colors.WHITE,
                    content=ft.Container(
                        padding=18,
                        content=ft.Column([
                            ft.Text(c['name'], size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                            ft.Text(f"{c['age_min']} a {c['age_max']} anos",
                                    size=12, color=ft.Colors.GREY_600),
                            ft.Divider(height=12),
                            build_staff_slot("Professor", by_role.get("Professor")),
                            build_staff_slot("Auxiliar", by_role.get("Auxiliar")),
                        ], spacing=10)
                    )
                )
                equipe_list.controls.append(card)
        page.update()

    # ---------- CHAMADA ----------

    def load_chamada_dropdown():
        classes = db.get_classes()
        chamada_turma_dropdown.options = [ft.dropdown.Option(key=c['id'], text=c['name']) for c in classes]

    def load_chamada(class_id, auto_today=False):
        tabela_chamada.rows.clear()
        chamada_state["sessions"] = []
        chamada_state["checkboxes"] = {}
        chamada_msg.visible = False
        chamada_msg.value = ""

        if not class_id:
            tabela_container.visible = False
            chamada_msg.value = "Selecione uma classe para começar a chamada."
            chamada_msg.visible = True
            page.update()
            return

        sessions = db.get_recent_sessions(class_id, limit=4)
        if auto_today and not any(s['date'] == datetime.now().strftime("%Y-%m-%d") for s in sessions):
            today = datetime.now().strftime("%Y-%m-%d")
            db.get_or_create_session(class_id, today)
            sessions = db.get_recent_sessions(class_id, limit=4)
            show_snack("Sessão de hoje criada automaticamente.")

        alunos = db.get_members_by_class(class_id)

        if not sessions:
            tabela_container.visible = False
            chamada_msg.value = (
                "Nenhuma data de aula registada para esta classe.\n"
                "Adicione a data acima para começar a marcar presenças."
            )
            chamada_msg.visible = True
            page.update()
            return

        if not alunos:
            tabela_container.visible = False
            chamada_msg.value = (
                "Esta classe não tem alunos matriculados.\n"
                "Cadastre novos alunos ou edite (lápis) a data de nascimento dos existentes "
                "para que apareçam aqui."
            )
            chamada_msg.visible = True
            page.update()
            return

        att_map = db.get_attendance_map([s['id'] for s in sessions])

        columns = [
            ft.DataColumn(ft.Text("Nº", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("NOME DO ALUNO", weight=ft.FontWeight.BOLD)),
        ]
        for idx, s in enumerate(sessions):
            header = ft.Column([
                ft.Text(format_date_br(s['date']), weight=ft.FontWeight.BOLD),
                ft.Checkbox(
                    fill_color=ft.Colors.GREEN_600,
                    tooltip="Marcar todos como presentes",
                    on_change=lambda e, si=idx: toggle_all_present(e, si),
                ),
            ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            columns.append(ft.DataColumn(header))
        tabela_chamada.columns = columns

        checkboxes = {}
        for i, a in enumerate(alunos):
            cells = [
                ft.DataCell(ft.Text(str(i+1))),
                ft.DataCell(ft.Text(a['name'], size=14)),
            ]
            for s in sessions:
                cb = ft.Checkbox(
                    fill_color=ft.Colors.BLUE_700,
                    value=att_map.get((s['id'], a['id']), False),
                )
                checkboxes[(s['id'], a['id'])] = cb
                cells.append(ft.DataCell(cb))
            tabela_chamada.rows.append(ft.DataRow(cells=cells))

        chamada_state["sessions"] = sessions
        chamada_state["checkboxes"] = checkboxes
        tabela_container.visible = True
        page.update()

    def toggle_all_present(e, session_idx):
        sessions = chamada_state["sessions"]
        if session_idx >= len(sessions):
            return
        sid = sessions[session_idx]['id']
        val = bool(e.control.value)
        for (s, m), cb in chamada_state["checkboxes"].items():
            if s == sid:
                cb.value = val
        page.update()

    def handle_add_session(e):
        class_id = chamada_turma_dropdown.value
        if not class_id:
            show_snack("Selecione uma classe primeiro!", ft.Colors.ORANGE)
            return

        iso_date = parse_date_br(chamada_data_input.value)
        if not iso_date:
            show_snack("Data inválida. Use o formato DD/MM/AAAA", ft.Colors.RED)
            return

        db.get_or_create_session(class_id, iso_date)
        chamada_data_input.value = ""
        load_chamada(class_id)
        show_snack("Data adicionada à chamada!")

    def handle_save_chamada(e):
        sessions = chamada_state["sessions"]
        if not sessions:
            show_snack("Nenhuma aula carregada para salvar.", ft.Colors.ORANGE)
            return

        per_session = {}
        for (session_id, member_id), cb in chamada_state["checkboxes"].items():
            per_session.setdefault(session_id, {})[member_id] = bool(cb.value)

        for session_id, presences in per_session.items():
            db.save_attendance(session_id, presences)

        show_snack("Presenças salvas com sucesso!")

    # ---------- VISITANTES ----------

    def load_visitantes_dropdown():
        classes = db.get_classes()
        visit_turma_dropdown.options = [ft.dropdown.Option(key=c['id'], text=c['name']) for c in classes]
        visit_turma_dropdown.value = None
        visit_session_dropdown.options = []
        visit_session_dropdown.value = None
        visit_state["session_id"] = None
        visit_list.controls.clear()
        visit_empty.visible = True
        visit_count.value = "Selecione uma turma e uma data de aula."
        page.update()

    def load_visitante_sessions(class_id):
        sessions = db.get_sessions_by_class(class_id)
        visit_session_dropdown.options = [
            ft.dropdown.Option(key=s['id'], text=format_date_full(s['date'])) for s in sessions
        ]
        visit_session_dropdown.value = None
        visit_state["session_id"] = None
        visit_list.controls.clear()
        visit_empty.visible = True
        visit_count.value = "Escolha a data da aula para ver os visitantes."
        page.update()

    def handle_visit_turma_change(e):
        class_id = e.control.value
        if class_id:
            load_visitante_sessions(class_id)
        else:
            load_visitantes_dropdown()

    def handle_visit_session_change(e):
        visit_state["session_id"] = e.control.value or None
        load_visitors()

    def handle_add_visit_date(e):
        class_id = visit_turma_dropdown.value
        if not class_id:
            show_snack("Selecione uma turma primeiro!", ft.Colors.ORANGE)
            return

        iso_date = parse_date_br(visit_data_input.value)
        if not iso_date:
            show_snack("Data inválida. Use o formato DD/MM/AAAA", ft.Colors.RED)
            return

        s = db.get_or_create_session(class_id, iso_date)
        visit_data_input.value = ""
        load_visitante_sessions(class_id)
        visit_session_dropdown.value = s['id']
        visit_state["session_id"] = s['id']
        load_visitors()
        show_snack("Data de aula criada.")

    def handle_add_visitor(e):
        session_id = visit_state["session_id"]
        name = visit_nome_input.value.strip()

        if not session_id:
            show_snack("Selecione a turma e a data da aula.", ft.Colors.ORANGE)
            return
        if not name:
            show_snack("Digite o nome do visitante.", ft.Colors.RED)
            return

        db.add_visitor(session_id, name)
        visit_nome_input.value = ""
        load_visitors()
        show_snack(f"Visitante {name} registado.")

    def handle_remove_visitor(visitor_id):
        db.delete_visitor(visitor_id)
        load_visitors()
        show_snack("Visitante removido.")

    def load_visitors():
        visit_list.controls.clear()
        session_id = visit_state["session_id"]

        if not session_id:
            visit_list.visible = True
            visit_empty.visible = True
            visit_count.value = "Escolha a data da aula para ver os visitantes."
            page.update()
            return

        visitors = db.get_visitors_by_session(session_id)
        visit_count.value = f"Visitantes registados: {len(visitors)}"

        if not visitors:
            visit_empty.visible = True
        else:
            visit_empty.visible = False
            for i, v in enumerate(visitors):
                visit_list.controls.append(
                    ft.Card(
                        elevation=1,
                        bgcolor=ft.Colors.WHITE,
                        content=ft.Container(
                            padding=12,
                            content=ft.Row([
                                ft.CircleAvatar(
                                    content=ft.Text(str(i+1)),
                                    bgcolor=ft.Colors.BLUE_700,
                                    color=ft.Colors.WHITE,
                                ),
                                ft.Column([
                                    ft.Text(v['name'], weight=ft.FontWeight.W_600),
                                    ft.Text(f"Aula de {format_date_full(db.get_session_by_id(session_id)['date'])}",
                                            size=12, color=ft.Colors.GREY_600),
                                ], spacing=0, expand=True),
                                ft.IconButton(
                                    ft.Icons.DELETE_OUTLINE,
                                    icon_color=ft.Colors.RED_400,
                                    tooltip="Remover visitante",
                                    on_click=lambda e, vid=v['id']: handle_remove_visitor(vid),
                                ),
                            ], spacing=10)
                        )
                    )
                )
        page.update()

    # ---------- NAVEGAÇÃO ----------

    def rail_changed(e):
        idx = e.control.selected_index
        alunos_view.visible = (idx == 0)
        turmas_view.visible = (idx == 1)
        equipe_view.visible = (idx == 2)
        chamada_view.visible = (idx == 3)
        visitantes_view.visible = (idx == 4)

        if idx == 0:
            load_alunos()
        elif idx == 1:
            load_turmas()
        elif idx == 2:
            load_staff_dropdowns()
            load_equipe()
        elif idx == 3:
            load_chamada_dropdown()
        elif idx == 4:
            load_visitantes_dropdown()

        page.update()

    # =============================================
    # WIDGETS / UI
    # =============================================

    # --- TELA 1: ALUNOS ---
    nome_input = ft.TextField(label="Nome Completo", width=400)
    data_nasc_input = ft.TextField(label="Data de Nascimento (DD/MM/AAAA)", width=300,
                                   hint_text="Ex: 15/08/2010",
                                   on_change=handle_birth_change)
    numero_input = ft.TextField(label="Número / Telefone", width=220)

    estado_civil_dropdown = ft.Dropdown(
        label="Estado Civil", width=180,
        options=[
            ft.dropdown.Option(key="Solteiro(a)", text="Solteiro(a)"),
            ft.dropdown.Option(key="Casado(a)", text="Casado(a)"),
            ft.dropdown.Option(key="Divorciado(a)", text="Divorciado(a)"),
            ft.dropdown.Option(key="Viúvo(a)", text="Viúvo(a)"),
        ],
    )
    batizado_checkbox = ft.Checkbox(label="Batizado(a)", on_change=handle_batismo_change)
    data_batismo_input = ft.TextField(label="Data do Batismo (DD/MM/AAAA)", width=220,
                                      hint_text="Ex: 12/04/2015", visible=False)
    profissao_input = ft.TextField(label="Profissão (opcional)", width=250)

    adultos_label = ft.Text("Informações de adulto (18+):", size=14,
                            weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_900)

    adultos_container = ft.Container(
        visible=False,
        content=ft.Column([
            adultos_label,
            ft.Row([
                estado_civil_dropdown,
                batizado_checkbox,
                data_batismo_input,
                profissao_input,
            ], spacing=15, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=6),
    )

    # --- DIÁLOGO DE EDIÇÃO DE ALUNO ---
    edit_state = {"member_id": None}

    edit_nome_input = ft.TextField(label="Nome Completo", width=420)
    edit_nasc_input = ft.TextField(label="Data de Nascimento (DD/MM/AAAA)", width=300,
                                   hint_text="Ex: 15/08/2010", on_change=handle_edit_birth_change)
    edit_numero_input = ft.TextField(label="Número / Telefone", width=220)
    edit_estado_civil_dropdown = ft.Dropdown(
        label="Estado Civil", width=200,
        options=[
            ft.dropdown.Option(key="Solteiro(a)", text="Solteiro(a)"),
            ft.dropdown.Option(key="Casado(a)", text="Casado(a)"),
            ft.dropdown.Option(key="Divorciado(a)", text="Divorciado(a)"),
            ft.dropdown.Option(key="Viúvo(a)", text="Viúvo(a)"),
        ],
    )
    edit_batizado_checkbox = ft.Checkbox(label="Batizado(a)", on_change=handle_edit_batismo_change)
    edit_data_batismo_input = ft.TextField(label="Data do Batismo (DD/MM/AAAA)", width=220,
                                           hint_text="Ex: 12/04/2015", visible=False)
    edit_profissao_input = ft.TextField(label="Profissão (opcional)", width=250)

    edit_adultos_container = ft.Container(
        visible=False,
        content=ft.Column([
            ft.Text("Informações de adulto (18+):", size=14,
                    weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_900),
            ft.Row([
                edit_estado_civil_dropdown,
                edit_batizado_checkbox,
                edit_data_batismo_input,
                edit_profissao_input,
            ], spacing=15, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=6),
    )

    edit_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Editar Aluno", weight=ft.FontWeight.BOLD),
        content=ft.Column([
            edit_nome_input,
            ft.Row([edit_nasc_input, edit_numero_input], spacing=15, wrap=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            edit_adultos_container,
        ], scroll=ft.ScrollMode.AUTO),
        actions=[
            ft.TextButton("Cancelar",
                          style=ft.ButtonStyle(color=ft.Colors.GREY_700),
                          on_click=lambda e: setattr(edit_dialog, "open", False) or page.update()),
            ft.FilledButton("Salvar Alterações", icon=ft.Icons.SAVE,
                            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
                            on_click=save_edit_dialog),
        ],
    )
    page.overlay.append(edit_dialog)

    alunos_count = ft.Text("", size=14, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_700)

    alunos_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Nº", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("NOME", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("NASCIMENTO", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("IDADE", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("TURMA", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("TELEFONE", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("INSCRIÇÃO", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("AÇÕES", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
    )

    alunos_view = ft.Container(
        padding=40,
        expand=True,
        content=ft.Column([
            ft.Text("Alunos", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("O sistema define a turma automaticamente pela data de nascimento.",
                    color=ft.Colors.GREY_700),
            ft.Divider(),
            ft.Card(
                elevation=1,
                bgcolor=ft.Colors.WHITE,
                content=ft.Container(
                    padding=20,
                    content=ft.Column([
                        ft.Text("Novo Aluno", size=16, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_900),
                        ft.Row([
                            nome_input,
                            data_nasc_input,
                            numero_input,
                            ft.FilledButton("Cadastrar Aluno", icon=ft.Icons.PERSON_ADD,
                                            on_click=handle_cadastro,
                                            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)),
                        ], spacing=20, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        adultos_container,
                    ], spacing=12)
                )
            ),
            ft.Row([alunos_count, ft.Container(expand=True)], spacing=10),
            ft.Row([alunos_table], scroll=ft.ScrollMode.AUTO),
        ], spacing=20, scroll=ft.ScrollMode.AUTO, expand=True)
    )

    # --- TELA 2: TURMAS ---
    turmas_list = ft.Column(spacing=12)

    turmas_view = ft.Container(
        padding=40,
        expand=True,
        content=ft.Column([
            ft.Text("Turmas da EBD", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("Resumo das classes com responsáveis e total de alunos.",
                    color=ft.Colors.GREY_700),
            ft.Divider(),
            turmas_list
        ], spacing=20, expand=True, scroll=ft.ScrollMode.AUTO)
    )

    # --- TELA 3: EQUIPE ---
    staff_nome_input = ft.TextField(label="Nome Completo", width=320)
    staff_role_dropdown = ft.Dropdown(label="Função", width=160, options=[])
    staff_turma_dropdown = ft.Dropdown(label="Turma", width=180, options=[])
    staff_phone_input = ft.TextField(label="Telefone (opcional)", width=180)

    equipe_list = ft.Row(wrap=True, spacing=15, run_spacing=15, expand=True)

    equipe_view = ft.Container(
        padding=40,
        expand=True,
        content=ft.Column([
            ft.Text("Equipe de Professores", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("Cada turma tem 1 professor e 1 auxiliar. Ao cadastrar, a vaga é preenchida automaticamente.",
                    color=ft.Colors.GREY_700),
            ft.Divider(),
            ft.Card(
                elevation=1,
                bgcolor=ft.Colors.WHITE,
                content=ft.Container(
                    padding=20,
                    content=ft.Row([
                        ft.Column([ft.Text("Novo Responsável", size=16, weight=ft.FontWeight.W_600), staff_nome_input],
                                  spacing=8),
                        staff_role_dropdown,
                        staff_turma_dropdown,
                        staff_phone_input,
                        ft.FilledButton("Salvar na Turma", icon=ft.Icons.HOW_TO_REG,
                                        on_click=handle_staff_submit,
                                        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)),
                    ], spacing=15, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)
                )
            ),
            equipe_list,
        ], spacing=20, expand=True, scroll=ft.ScrollMode.AUTO)
    )

    # --- TELA 4: CHAMADAS ---
    chamada_turma_dropdown = ft.Dropdown(
        label="Selecione a Classe",
        width=300,
        on_select=lambda e: load_chamada(e.control.value, auto_today=True)
    )

    chamada_data_input = ft.TextField(
        label="Data da Aula (DD/MM/AAAA)", width=220, hint_text="Ex: 21/09/2026"
    )

    tabela_chamada = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Nº", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("NOME DO ALUNO", weight=ft.FontWeight.BOLD)),
        ],
        rows=[
            ft.DataRow(cells=[
                ft.DataCell(ft.Text("—")),
                ft.DataCell(ft.Text("Nenhuma data carregada", color=ft.Colors.GREY_500)),
            ]),
        ],
    )

    chamada_msg = ft.Text(
        "",
        color=ft.Colors.GREY_700,
        size=14,
        visible=False,
    )

    tabela_container = ft.Row(
        [ft.Card(elevation=1, content=ft.Container(padding=16, content=tabela_chamada))],
        scroll=ft.ScrollMode.AUTO,
        visible=False,
    )

    chamada_view = ft.Container(
        padding=40,
        expand=True,
        content=ft.Column([
            ft.Text("Lista de Presença", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("Marque as presenças dos alunos para cada data de aula.",
                    color=ft.Colors.GREY_700),
            ft.Card(
                elevation=1,
                bgcolor=ft.Colors.WHITE,
                content=ft.Container(
                    padding=16,
                    content=ft.Column([
                        ft.Text("1. Escolha a turma • 2. Marque as presenças • 3. Salve",
                                size=13, color=ft.Colors.BLUE_900,
                                weight=ft.FontWeight.W_500),
                        ft.Row([
                            chamada_turma_dropdown,
                            chamada_data_input,
                            ft.FilledButton("Adicionar Data", icon=ft.Icons.CALENDAR_MONTH,
                                            on_click=handle_add_session,
                                            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                                 color=ft.Colors.WHITE)),
                        ], spacing=15, wrap=True),
                        ft.Text("Dica: a data de hoje é criada automaticamente ao escolher a turma. "
                                "Use a caixa verde no topo de cada data para marcar todos os alunos.",
                                size=12, color=ft.Colors.GREY_600),
                    ], spacing=12)
                )
            ),
            ft.Divider(),
            chamada_msg,
            tabela_container,
            ft.Row([
                ft.FilledButton("Salvar Presenças", icon=ft.Icons.SAVE,
                                on_click=handle_save_chamada,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE)),
            ], alignment=ft.MainAxisAlignment.END)
        ], spacing=20, expand=True, scroll=ft.ScrollMode.AUTO)
    )

    # --- TELA 5: VISITANTES ---
    visit_turma_dropdown = ft.Dropdown(
        label="Turma",
        width=280,
        options=[],
        on_select=handle_visit_turma_change,
    )
    visit_session_dropdown = ft.Dropdown(
        label="Data da Aula",
        width=220,
        options=[],
        on_select=handle_visit_session_change,
    )
    visit_data_input = ft.TextField(
        label="Nova Data (DD/MM/AAAA)", width=200, hint_text="Ex: 21/09/2026"
    )
    visit_nome_input = ft.TextField(label="Nome do Visitante", width=300)

    visit_count = ft.Text("", size=14, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_700)
    visit_empty = ft.Text("Sem visitantes registados nesta aula.", color=ft.Colors.GREY_500)
    visit_list = ft.Column(spacing=8, expand=True)

    visitantes_view = ft.Container(
        padding=40,
        expand=True,
        content=ft.Column([
            ft.Text("Registo de Visitantes", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("Registe os visitantes presentes em cada aula.",
                    color=ft.Colors.GREY_700),
            ft.Row([
                visit_turma_dropdown,
                visit_session_dropdown,
                visit_data_input,
                ft.FilledButton("Criar Data", icon=ft.Icons.CALENDAR_MONTH,
                                on_click=handle_add_visit_date,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)),
            ], spacing=15, wrap=True),
            ft.Divider(),
            ft.Row([
                visit_nome_input,
                ft.FilledButton("Adicionar Visitante", icon=ft.Icons.GROUP_ADD,
                                on_click=handle_add_visitor,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE)),
            ], spacing=10, wrap=True),
            visit_count,
            visit_empty,
            visit_list,
        ], spacing=16, expand=True, scroll=ft.ScrollMode.AUTO)
    )

    # --- NAVEGAÇÃO LATERAL ---
    rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=100,
        min_extended_width=200,
        bgcolor=ft.Colors.BLUE_50,
        group_alignment=-0.9,
        destinations=[
            ft.NavigationRailDestination(
                icon=ft.Icons.PERSON_ADD_OUTLINED, selected_icon=ft.Icons.PERSON_ADD, label="Alunos"
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.CLASS_OUTLINED, selected_icon=ft.Icons.CLASS_, label="Turmas"
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.GROUPS_OUTLINED, selected_icon=ft.Icons.GROUPS, label="Equipe"
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.CHECKLIST_RTL_OUTLINED, selected_icon=ft.Icons.CHECKLIST_RTL, label="Chamada"
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.PEOPLE_OUTLINED, selected_icon=ft.Icons.PEOPLE, label="Visitantes"
            ),
        ],
        on_change=rail_changed,
    )

    alunos_view.visible = True
    turmas_view.visible = False
    equipe_view.visible = False
    chamada_view.visible = False
    visitantes_view.visible = False

    # Layout Principal
    page.add(
        ft.Row(
            [
                rail,
                ft.VerticalDivider(width=1),
                ft.Column([alunos_view, turmas_view, equipe_view, chamada_view, visitantes_view], expand=True),
            ],
            expand=True,
        )
    )
    load_alunos()

if __name__ == "__main__":
    ft.run(main)