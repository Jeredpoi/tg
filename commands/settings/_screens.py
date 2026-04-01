from ._shared import (
    html, InlineKeyboardButton, InlineKeyboardMarkup,
    get_main_chat_id, get_monitor_chat_id,
    get_setup_chats, get_setting,
    MANAGEABLE_COMMANDS, get_disabled_commands,
    is_command_enabled,
    MGE_CHARACTERS,
    get_custom_mge_phrases,
    get_custom_swear_responses,
    get_custom_swear_triggers,
    _back_to_menu_btn, _back_to_chats_btn,
)


# ── Экраны чатов ──────────────────────────────────────────────────────────────

async def _show_chat_list(query, context) -> None:
    """Показывает список всех инициализированных групп."""
    setup_chats = get_setup_chats()
    main_id = get_main_chat_id()

    if not setup_chats:
        await query.edit_message_text(
            "💬 <b>Чаты бота</b>\n\n"
            "Бот ещё не инициализирован ни в одной группе.\n"
            "Добавь бота в группу и напиши /start.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[_back_to_menu_btn()]]),
        )
        await query.answer()
        return

    monitor_id = get_monitor_chat_id()
    buttons = []
    for cid in sorted(setup_chats):
        try:
            chat = await context.bot.get_chat(cid)
            name = chat.title or str(cid)
        except Exception:
            name = str(cid)
        if cid == main_id:
            icon = "🟢"
        elif cid == monitor_id:
            icon = "🖥"
        else:
            icon = "⚪"
        buttons.append([InlineKeyboardButton(
            f"{icon} {name}",
            callback_data=f"stg:chat:{cid}",
        )])

    buttons.append([_back_to_menu_btn()])

    main_hint = ""
    if main_id:
        try:
            mc = await context.bot.get_chat(main_id)
            main_name = mc.title or str(main_id)
        except Exception:
            main_name = str(main_id)
        main_hint = f"\n\n🟢 Основная: <b>{html.escape(main_name)}</b>"
    else:
        main_hint = "\n\n⚠️ Основная группа не выбрана"

    await query.edit_message_text(
        f"💬 <b>Управление чатами</b>{main_hint}\n\n"
        "Нажми на чат чтобы изменить его роль:\n"
        "🟢 — основная группа (рассылки, /anon, /rate)\n"
        "🖥 — основная тестовая (мониторинг бота)\n"
        "⚪ — тестовая / без роли",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    await query.answer()


async def _show_chat_detail(query, context, chat_id: int) -> None:
    """Показывает информацию о конкретном чате и кнопки управления."""
    main_id    = get_main_chat_id()
    monitor_id = get_monitor_chat_id()
    is_main    = (main_id == chat_id)
    is_monitor = (monitor_id == chat_id)

    try:
        chat = await context.bot.get_chat(chat_id)
        name = chat.title or str(chat_id)
        members = await context.bot.get_chat_member_count(chat_id)
        members_line = f"\n👥 Участников: {members}"
    except Exception:
        name = str(chat_id)
        members_line = ""

    if is_main:
        role_text = "🟢 Основная"
        role_desc = "Сюда идут: ночной отчёт, фото недели, /anon, /rate"
    elif is_monitor:
        role_text = "🖥 Основная тестовая (мониторинг)"
        role_desc = "Центр управления и мониторинга бота"
    else:
        role_text = "⚪ Тестовая / без роли"
        role_desc = "Рассылки и /anon сюда не приходят"

    action_rows = []
    if is_main:
        action_rows.append([InlineKeyboardButton(
            "⚪ Снять как основную",
            callback_data=f"stg:mk_test:{chat_id}",
        )])
    else:
        action_rows.append([InlineKeyboardButton(
            "🟢 Сделать основной",
            callback_data=f"stg:mk_main:{chat_id}",
        )])

    if is_monitor:
        action_rows.append([InlineKeyboardButton(
            "⚪ Снять роль монитора",
            callback_data=f"stg:mk_nomonitor:{chat_id}",
        )])
    else:
        action_rows.append([InlineKeyboardButton(
            "🖥 Назначить основной тестовой",
            callback_data=f"stg:mk_monitor:{chat_id}",
        )])

    kb = InlineKeyboardMarkup([
        *action_rows,
        [_back_to_chats_btn()],
    ])

    await query.edit_message_text(
        f"💬 <b>{html.escape(name)}</b>\n\n"
        f"🆔 ID: <code>{chat_id}</code>{members_line}\n"
        f"Роль: {role_text}\n"
        f"<i>{role_desc}</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


# ── Экран мат-детекции ────────────────────────────────────────────────────────

async def _show_swear_settings(query) -> None:
    enabled = get_setting("swear_detect")
    chance = get_setting("swear_response_chance")

    status = "🟢 Включена" if enabled else "🔴 Выключена"
    toggle_text = "🔴 Выключить" if enabled else "🟢 Включить"

    chance_options = [
        (0.2, "20%"), (0.35, "35%"), (0.45, "45%"),
        (0.6, "60%"), (0.8, "80%"), (1.0, "100%"),
    ]
    chance_buttons = []
    for val, label in chance_options:
        prefix = "✅ " if abs(chance - val) < 0.01 else ""
        chance_buttons.append(InlineKeyboardButton(
            f"{prefix}{label}",
            callback_data=f"stg:swear_chance:{val}",
        ))

    # Разбиваем на ряды по 3
    rows = [chance_buttons[i:i+3] for i in range(0, len(chance_buttons), 3)]

    trigger_count = len(get_custom_swear_triggers())
    trigger_badge = f" ({trigger_count})" if trigger_count else ""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_text, callback_data="stg:swear_toggle")],
        *rows,
        [InlineKeyboardButton(f"🎯 Слова-триггеры{trigger_badge}", callback_data="stg:swear_triggers")],
        [_back_to_menu_btn()],
    ])

    await query.edit_message_text(
        f"🤬 <b>Мат-детекция</b>\n\n"
        f"Статус: {status}\n"
        f"Шанс ответа на мат: <b>{int(chance * 100)}%</b>\n\n"
        f"<i>Бот реагирует на маты случайным комментарием. "
        f"Здесь можно включить/выключить это и настроить частоту.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


async def _show_swear_triggers_menu(query) -> None:
    """Меню управления словами-триггерами."""
    triggers = get_custom_swear_triggers()
    count = len(triggers)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить слово", callback_data="stg:trigger_add")],
        [InlineKeyboardButton(
            f"📋 Добавленные слова ({count})" if count else "📋 Слов пока нет",
            callback_data="stg:trigger_list",
        )],
        [InlineKeyboardButton("⬅️ Назад", callback_data="stg:swear")],
    ])
    await query.edit_message_text(
        f"🎯 <b>Слова-триггеры</b>\n\n"
        f"Добавлено слов: <b>{count}</b>\n\n"
        f"<i>Бот будет реагировать на эти слова так же, как на маты — "
        f"с настроенным шансом ответа. Можно задать свой ответ на каждое слово.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


async def _show_swear_triggers_list(query) -> None:
    """Список триггерных слов с кнопками удаления."""
    triggers = get_custom_swear_triggers()
    if not triggers:
        await query.edit_message_text(
            "🎯 <b>Слова-триггеры</b>\n\nСвоих слов пока нет.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Назад", callback_data="stg:swear_triggers"),
            ]]),
        )
        await query.answer()
        return

    rows = []
    for i, t in enumerate(triggers):
        resp_hint = " + ответ" if t.get("response") else ""
        rows.append([InlineKeyboardButton(
            f"🗑 «{t['word']}»{resp_hint}",
            callback_data=f"stg:trigger_del:{i}",
        )])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="stg:swear_triggers")])

    await query.edit_message_text(
        f"🎯 <b>Слова-триггеры</b> ({len(triggers)} шт.)\n\n"
        f"Нажми на слово чтобы удалить его:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await query.answer()


# ── Экран отчётов ─────────────────────────────────────────────────────────────

async def _show_reports_settings(query) -> None:
    midnight = get_setting("midnight_report")
    weekly = get_setting("weekly_best_photo")

    midnight_icon = "🟢" if midnight else "🔴"
    weekly_icon = "🟢" if weekly else "🔴"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{midnight_icon} Ночной отчёт по матам",
            callback_data="stg:midnight_toggle",
        )],
        [InlineKeyboardButton(
            f"{weekly_icon} Лучшее фото недели",
            callback_data="stg:weekly_toggle",
        )],
        [_back_to_menu_btn()],
    ])

    await query.edit_message_text(
        "📊 <b>Отчёты и рассылки</b>\n\n"
        f"🌙 Ночной отчёт по матам: {midnight_icon} {'вкл' if midnight else 'выкл'}\n"
        f"📸 Лучшее фото недели: {weekly_icon} {'вкл' if weekly else 'выкл'}\n\n"
        "<i>Ночной отчёт — ежедневная статистика матов в 00:00.\n"
        "Фото недели — лучшее фото по рейтингу за неделю.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


# ── Экран голосования ─────────────────────────────────────────────────────────

async def _show_vote_settings(query) -> None:
    duration = get_setting("vote_duration")

    options = [15, 30, 45, 60]
    buttons = []
    for val in options:
        prefix = "✅ " if duration == val else ""
        buttons.append(InlineKeyboardButton(
            f"{prefix}{val} мин",
            callback_data=f"stg:vote_dur:{val}",
        ))

    kb = InlineKeyboardMarkup([
        buttons,
        [_back_to_menu_btn()],
    ])

    await query.edit_message_text(
        f"🗳 <b>Голосование /rate</b>\n\n"
        f"Длительность: <b>{duration} минут</b>\n\n"
        f"<i>Сколько длится голосование после публикации фото в группе.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


# ── Экран кулдауна ────────────────────────────────────────────────────────────

async def _show_cooldown_settings(query) -> None:
    cd = get_setting("cmd_cooldown")

    options = [5, 10, 15, 30]
    buttons = []
    for val in options:
        prefix = "✅ " if cd == val else ""
        buttons.append(InlineKeyboardButton(
            f"{prefix}{val} сек",
            callback_data=f"stg:cd:{val}",
        ))

    kb = InlineKeyboardMarkup([
        buttons,
        [_back_to_menu_btn()],
    ])

    await query.edit_message_text(
        f"⏱ <b>Кулдаун команд</b>\n\n"
        f"Интервал: <b>{cd} секунд</b>\n\n"
        f"<i>Минимальное время между использованиями одной команды "
        f"одним пользователем. Защищает от спама.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


# ── Экран управления командами ────────────────────────────────────────────────

async def _show_commands_settings(query) -> None:
    """Список команд с кнопками вкл/выкл."""
    rows = []
    for cmd, desc in MANAGEABLE_COMMANDS.items():
        enabled = is_command_enabled(cmd)
        icon = "🟢" if enabled else "🔴"
        rows.append([InlineKeyboardButton(
            f"{icon} {cmd} — {desc}",
            callback_data=f"stg:cmd_toggle:{cmd}",
        )])

    disabled_count = len(get_disabled_commands())
    status_line = (
        "Все команды включены" if disabled_count == 0
        else f"Отключено: {disabled_count}"
    )

    rows.append([_back_to_menu_btn()])

    await query.edit_message_text(
        f"🎮 <b>Управление командами</b>\n\n"
        f"Статус: {status_line}\n\n"
        f"Нажми на команду чтобы включить или выключить её.\n"
        f"🟢 — включена  🔴 — выключена",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await query.answer()


# ── Экраны MGE-фраз ───────────────────────────────────────────────────────────

async def _show_mge_menu(query) -> None:
    phrases = get_custom_mge_phrases()
    count = len(phrases)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить фразу", callback_data="stg:mge_add")],
        [InlineKeyboardButton(
            f"📋 Мои фразы ({count})" if count else "📋 Фраз пока нет",
            callback_data="stg:mge_list",
        )],
        [_back_to_menu_btn()],
    ])
    await query.edit_message_text(
        f"✏️ <b>Фразы /mge</b>\n\n"
        f"Добавлено своих фраз: <b>{count}</b>\n\n"
        f"<i>Кастомные фразы добавляются к стандартным и выпадают случайно так же.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


async def _show_mge_char_picker(query) -> None:
    """Экран выбора персонажа перед вводом фразы."""
    rows = []
    for i in range(0, len(MGE_CHARACTERS), 2):
        row = [
            InlineKeyboardButton(MGE_CHARACTERS[i], callback_data=f"stg:mge_char:{MGE_CHARACTERS[i]}"),
        ]
        if i + 1 < len(MGE_CHARACTERS):
            row.append(InlineKeyboardButton(MGE_CHARACTERS[i+1], callback_data=f"stg:mge_char:{MGE_CHARACTERS[i+1]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ Отмена", callback_data="stg:mge")])

    await query.edit_message_text(
        "✏️ <b>Фразы /mge</b> — выбери персонажа\n\n"
        "От чьего имени будет звучать фраза?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await query.answer()


async def _show_mge_list(query) -> None:
    """Список кастомных фраз с кнопками удаления."""
    phrases = get_custom_mge_phrases()
    if not phrases:
        await query.edit_message_text(
            "✏️ <b>Фразы /mge</b>\n\nСвоих фраз пока нет.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Назад", callback_data="stg:mge"),
            ]]),
        )
        await query.answer()
        return

    rows = []
    for i, p in enumerate(phrases):
        short = p["phrase"][:35] + ("…" if len(p["phrase"]) > 35 else "")
        rows.append([InlineKeyboardButton(
            f"🗑 [{p['char']}] {short}",
            callback_data=f"stg:mge_del:{i}",
        )])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="stg:mge")])

    await query.edit_message_text(
        f"✏️ <b>Свои фразы /mge</b> ({len(phrases)} шт.)\n\n"
        f"Нажми на фразу чтобы удалить её:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await query.answer()


# ── Экраны кастомных ответов на маты ─────────────────────────────────────────

async def _show_swear_resp_menu(query) -> None:
    responses = get_custom_swear_responses()
    count = len(responses)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить ответ", callback_data="stg:swear_resp_add")],
        [InlineKeyboardButton(
            f"📋 Мои ответы ({count})" if count else "📋 Ответов пока нет",
            callback_data="stg:swear_resp_list",
        )],
        [_back_to_menu_btn()],
    ])
    await query.edit_message_text(
        f"💬 <b>Ответы на маты</b>\n\n"
        f"Добавлено своих ответов: <b>{count}</b>\n\n"
        f"<i>Используй <code>{{name}}</code> чтобы вставить имя матерщинника.\n"
        f"Кастомные ответы добавляются к стандартным и выпадают случайно.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()


async def _show_swear_resp_list(query) -> None:
    responses = get_custom_swear_responses()
    if not responses:
        await query.edit_message_text(
            "💬 <b>Ответы на маты</b>\n\nСвоих ответов пока нет.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Назад", callback_data="stg:swear_resp"),
            ]]),
        )
        await query.answer()
        return

    rows = []
    for i, r in enumerate(responses):
        short = r[:40] + ("…" if len(r) > 40 else "")
        rows.append([InlineKeyboardButton(
            f"🗑 {short}",
            callback_data=f"stg:swear_resp_del:{i}",
        )])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="stg:swear_resp")])

    await query.edit_message_text(
        f"💬 <b>Свои ответы на маты</b> ({len(responses)} шт.)\n\n"
        f"Нажми на ответ чтобы удалить его:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await query.answer()


# ── Экран автоудаления ────────────────────────────────────────────────────────

_AUTODEL_OPTIONS = [0, 10, 15, 20, 30, 60, 120, 300, 600, 1800, 3600]  # 0 = выкл

def _autodel_row(setting_key: str, cb_prefix: str, label: str) -> list:
    """Строка кнопок для одной настройки автоудаления."""
    current = get_setting(setting_key)
    btns = []
    for val in _AUTODEL_OPTIONS:
        tick = "✅ " if current == val else ""
        txt  = "выкл" if val == 0 else f"{val}с"
        btns.append(InlineKeyboardButton(f"{tick}{txt}", callback_data=f"{cb_prefix}{val}"))
    return btns


async def _show_autodel_settings(query) -> None:
    h  = get_setting("autodel_help")
    g  = get_setting("autodel_gallery")
    ow = get_setting("autodel_ownerhelp")
    tp = get_setting("autodel_top")
    st = get_setting("autodel_stats")
    dbg = get_setting("autodel_debug")

    def fmt(v): return "выкл" if v == 0 else f"{v} сек."

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 /help", callback_data="stg:noop")],
        _autodel_row("autodel_help",      "stg:adh:",  "/help"),
        [InlineKeyboardButton("🖼 Галерея (личка)", callback_data="stg:noop")],
        _autodel_row("autodel_gallery",   "stg:adg:",  "галерея"),
        [InlineKeyboardButton("👑 /ownerhelp", callback_data="stg:noop")],
        _autodel_row("autodel_ownerhelp", "stg:adow:", "/ownerhelp"),
        [InlineKeyboardButton("📊 /top", callback_data="stg:noop")],
        _autodel_row("autodel_top",       "stg:adt:",  "/top"),
        [InlineKeyboardButton("📈 /stats", callback_data="stg:noop")],
        _autodel_row("autodel_stats",     "stg:ads:",  "/stats"),
        [InlineKeyboardButton("🛠 /debug", callback_data="stg:noop")],
        _autodel_row("autodel_debug",     "stg:add:",  "/debug"),
        [_back_to_menu_btn()],
    ])

    await query.edit_message_text(
        "🗑 <b>Автоудаление сообщений</b>\n\n"
        f"📖 /help: <b>{fmt(h)}</b>\n"
        f"🖼 Галерея (личка): <b>{fmt(g)}</b>\n"
        f"👑 /ownerhelp: <b>{fmt(ow)}</b>\n"
        f"📊 /top: <b>{fmt(tp)}</b>\n"
        f"📈 /stats: <b>{fmt(st)}</b>\n"
        f"🛠 /debug: <b>{fmt(dbg)}</b>\n\n"
        "<i>Сколько секунд показывается сообщение перед удалением.\n"
        "«выкл» — сообщение не удаляется.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await query.answer()
