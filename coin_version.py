"""coin_version — تصميم صفحة تفاصيل الفرد (بطاقات بعناوين زرقاء).
خاص بشاشة التفاصيل فقط. للرجوع للتصميم القديم: DETAILS_VERSION = "classic" في config.py"""
import flet as ft

import logic as L
from common import BLUE, BOLD, CONTACT_FIELDS, CONTACT_ICONS, contact_url, err

BORDER, BODY, PILL = "#6F9BE0", "#E7EEF9", "#F6F9FE"


def _icon(name, fallback):
    return getattr(ft.icons, name, fallback)


def _section(title, icon, body, action=None):
    """بطاقة: شريط عنوان أزرق (أيقونة + عنوان) وتحته جسم فاتح."""
    row = [ft.Icon(icon, color="white", size=22),
           ft.Text(title, color="white", weight=BOLD, size=16)]
    if action is not None:
        row += [ft.Container(expand=True), action]
    header = ft.Container(
        ft.Row(row, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor=BLUE, padding=ft.padding.symmetric(horizontal=14, vertical=6))
    return ft.Container(
        ft.Column([header, ft.Container(body, bgcolor=BODY, padding=10)], spacing=0),
        border=ft.border.all(1.5, BORDER), border_radius=12,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS)


def _pill(app, text, pid=None, size=15, muted=False):
    return ft.Container(
        ft.Text(text, size=size, weight=BOLD, text_align=ft.TextAlign.CENTER,
                color="#6B7280" if muted else "black"),
        bgcolor=PILL, border=ft.border.all(1, BORDER), border_radius=8,
        padding=ft.padding.symmetric(vertical=9, horizontal=6),
        alignment=ft.alignment.center, expand=True, ink=bool(pid),
        on_click=(lambda e, i=pid: app.go(app.person_view, i)) if pid else None)


def _single(app, pid, people):
    if pid in people:
        return ft.Row([_pill(app, people[pid]["ar_name"], pid, 17)])
    return ft.Row([_pill(app, "غير مسجل", None, 15, muted=True)])


def _grid(app, items):
    """items: [(النص, id أو None, باهت؟)] — شبكة من عمودين مثل صورة التصميم."""
    rows = []
    for i in range(0, len(items), 2):
        cells = [_pill(app, t, pid, 15, muted) for t, pid, muted in items[i:i + 2]]
        if len(cells) == 1:
            cells.append(ft.Container(expand=True))
        rows.append(ft.Row(cells, spacing=8))
    return ft.Column(rows, spacing=8)


def person_view(app, pid):
    people = app.people
    p = people.get(pid)
    if not p:
        return app.simple_view("لم يُعثر على هذا الشخص")
    can = app.can_edit(pid)
    about, con = app.fetch_one("about_persons", pid), app.fetch_one("contacts", pid)
    rel = dict(L.relatives(people, app.spouses, pid))

    def names(title):
        return [(people[i]["ar_name"], i, False) for i in sorted(rel.get(title, []))]

    # --- الصورة داخل إطار أزرق ---
    img = ft.Container(
        ft.Image(src=app.avatar(p), fit=ft.ImageFit.COVER, width=260, height=280,
                 error_content=ft.Icon(ft.icons.PERSON, size=80, color="#9AA5AD")),
        width=260, height=280, border=ft.border.all(3, BLUE), border_radius=14,
        bgcolor="white", clip_behavior=ft.ClipBehavior.ANTI_ALIAS)
    photo = ft.Stack([img], width=260, height=280)
    if can:
        photo.controls.append(ft.IconButton(
            ft.icons.CAMERA_ALT, bgcolor=BLUE, icon_color="white", right=6, bottom=6,
            on_click=lambda e: app.pick_photo(pid)))

    # --- الاسم ---
    name_lines = [ft.Row([ft.Text(p["ar_name"], size=22, weight=BOLD, color="black",
                                  expand=True, text_align=ft.TextAlign.CENTER)])]
    if p.get("en_name"):
        name_lines.append(ft.Row([ft.Text(p["en_name"], size=14, color="#374151", expand=True,
                                          text_align=ft.TextAlign.CENTER)]))
    status = L.marital_status(p, app.marriages)
    if p.get("is_deceased"):
        status += " — " + ("رحمها الله" if p["gender"] == "F" else "رحمه الله")
    name_lines.append(ft.Row([ft.Text(status, size=13, color="#374151", expand=True,
                                      text_align=ft.TextAlign.CENTER)]))

    sections = [
        ft.Row([photo], alignment=ft.MainAxisAlignment.CENTER),
        _section("الاسم", ft.icons.PERSON, ft.Column(name_lines, spacing=2)),
        _section("الأب", _icon("MAN", ft.icons.PERSON), _single(app, p["father_id"], people)),
        _section("الأم", _icon("WOMAN", ft.icons.PERSON), _single(app, p["mother_id"], people)),
    ]
    groups = _icon("GROUPS", ft.icons.GROUP)
    for title, key in (("الإخوان", "الأخ"), ("الأخوات", "الأخت"),
                       ("الأبناء", "الابن"), ("البنات", "الابنة")):
        items = names(key)
        if items:
            sections.append(_section(title, groups, _grid(app, items)))

    # --- الزوج / الزوجة (مع احترام خيار إخفاء اسم الزوجة) ---
    sp = sorted(app.spouses.get(pid, set()))
    if sp:
        items = []
        for i in sp:
            if p["gender"] == "M" and app.hidden_wife(pid, i):
                items.append(("(غير معروضة)", None, True))
            else:
                items.append((people[i]["ar_name"], i, False))
        sections.append(_section("الزوجة" if p["gender"] == "M" else "الزوج",
                                 ft.icons.FAVORITE_BORDER, _grid(app, items)))

    # --- معلومات ---
    rows = [("تاريخ الميلاد", p.get("birth_date")), ("مكان الميلاد", p.get("birth_place")),
            ("يسكن في", p.get("living_at")), ("تاريخ الوفاة", p.get("death_date")),
            ("المستوى التعليمي", about.get("education_level")), ("درس في", about.get("studied_at")),
            ("الوظيفة", about.get("job")), ("الاهتمامات", about.get("interests"))]
    info = [ft.Row([ft.Text(k + ":", weight=BOLD, color="black"),
                    ft.Text(str(v), color="black", expand=True)],
                   vertical_alignment=ft.CrossAxisAlignment.START)
            for k, v in rows if v]
    if about.get("about_me"):
        info.append(ft.Text(about["about_me"], color="black"))
    if info:
        sections.append(_section("معلومات", ft.icons.INFO_OUTLINE, ft.Column(info, spacing=6)))

    # --- التواصل ---
    btns = [ft.IconButton(CONTACT_ICONS[k], tooltip=lbl, icon_color=BLUE,
                          on_click=lambda e, k=k: app.page.launch_url(contact_url(k, con[k])))
            for k, lbl in CONTACT_FIELDS if con.get(k)]
    if btns:
        sections.append(_section("التواصل", ft.icons.PHONE,
                                 ft.Row(btns, alignment=ft.MainAxisAlignment.CENTER, wrap=True)))

    # --- المناسبات ---
    try:
        occ = app.sb.table("occasions").select("*").eq("person_id", pid) \
            .order("created_at", desc=True).execute().data
        mine = set()
        if occ:
            mine = {r["occasion_id"] for r in app.sb.table("occasion_hearts").select("occasion_id")
                    .eq("user_id", app.uid).in_("occasion_id", [o["id"] for o in occ]).execute().data}
        cards = [app.occasion_card(o, o["id"] in mine) for o in occ]
        body = ft.Column(cards, spacing=6) if cards else ft.Text("لا توجد مناسبات", color="#374151")
    except Exception as ex:
        body = ft.Text(err(ex), color="red")
    sections.append(_section(
        "المناسبات", ft.icons.EVENT, body,
        action=ft.IconButton(ft.icons.ADD, icon_color="white", tooltip="إضافة مناسبة",
                             on_click=lambda e: app.occasion_dialog(pid))))

    sections.append(ft.Row([
        ft.ElevatedButton("إضافة قريب", icon=ft.icons.PERSON_ADD, bgcolor=BLUE, color="white",
                          on_click=lambda e: app.add_dialog(pid)),
        ft.OutlinedButton("رسالة عن هذا الشخص", icon=ft.icons.MAIL_OUTLINE,
                          on_click=lambda e: app.message_dialog(pid))],
        wrap=True, alignment=ft.MainAxisAlignment.CENTER))

    actions = [ft.IconButton(ft.icons.EDIT, tooltip="تعديل", icon_color="white",
                             on_click=lambda e: app.go(app.edit_view, pid))] if can else []
    body = ft.Container(
        ft.ListView(sections, expand=True, spacing=12, padding=14),
        gradient=ft.LinearGradient(begin=ft.alignment.top_center, end=ft.alignment.bottom_center,
                                   colors=["#FFFFFF", "#D6E4FA"]),
        expand=True)
    return ft.View(f"/person/{pid}", [body],
                   appbar=ft.AppBar(title=ft.Text(p["ar_name"], color="white"), bgcolor=BLUE,
                                    color="white", center_title=True, actions=actions),
                   bgcolor="#F3F7FD", padding=0)
