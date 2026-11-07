import mimetypes
import os
import time

import flet as ft
from sb import create_client

import config
import logic as L

BG, BAR, LABEL, TXT = "#EAEEF1", "#AEBDC6", "#D0D8DD", "#1F2933"
BOLD = ft.FontWeight.BOLD

OCC_TYPES = {"birth": "ولادة", "birthday": "عيد ميلاد", "engagement": "خطوبة",
             "wedding": "زواج", "graduation": "تخرج", "new_job": "وظيفة جديدة",
             "death": "وفاة", "other": "أخرى"}
MSG_TYPES = {"suggestion": "اقتراح", "correction": "تصحيح معلومة", "question": "سؤال",
             "complaint": "شكوى", "other": "أخرى"}
MARRIAGE_STATUS = {"married": "قائم", "divorced": "منتهي (طلاق)", "widowed": "ترمّل (توفي أحد الزوجين)"}
CONTACT_FIELDS = [("phone", "الهاتف"), ("wapp", "واتساب"), ("gml", "البريد (Gmail)"),
                  ("fb", "فيسبوك"), ("telg", "تيليجرام")]
CONTACT_ICONS = {"phone": ft.icons.PHONE, "wapp": ft.icons.CHAT, "gml": ft.icons.EMAIL,
                 "fb": getattr(ft.icons, "FACEBOOK", ft.icons.PUBLIC), "telg": ft.icons.SEND}


def err(ex):
    m = getattr(ex, "message", None) or str(ex)
    return str(m)[:200]


def contact_url(kind, v):
    v = v.strip()
    if kind == "phone":
        return "tel:" + v
    if kind == "wapp":
        return "https://wa.me/" + "".join(c for c in v if c.isdigit())
    if kind == "gml":
        return "mailto:" + v
    if kind == "telg":
        return v if v.startswith("http") else "https://t.me/" + v.lstrip("@")
    return v if v.startswith("http") else "https://" + v


class FamilyApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.sb = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        self.uid = None
        self.profile = {}
        self.people, self.spouses, self.marriages = {}, {}, []
        self.stack = []
        self.upload_pid = None
        self.picker = ft.FilePicker(on_result=self.on_pick)
        page.overlay.append(self.picker)
        page.title = "شجرة العائلة"
        page.rtl = True
        page.bgcolor = BG
        page.padding = 0
        page.on_view_pop = self.back
        self.start()

    # ---------------- أدوات عامة ----------------
    @property
    def is_admin(self):
        return self.profile.get("role") == "admin"

    def can_edit(self, pid):
        p = self.people.get(pid)
        return bool(self.is_admin or self.profile.get("person_id") == pid
                    or (p and p.get("created_by") == self.uid))

    def snack(self, msg):
        self.page.snack_bar = ft.SnackBar(ft.Text(msg))
        self.page.snack_bar.open = True
        self.page.update()

    def avatar(self, p):
        return p.get("img_url") or config.AVATAR[p["gender"]]

    # ---------------- التنقل (Views) ----------------
    def reset(self, fn, *args):
        self.stack = [(fn, args)]
        self.page.views.clear()
        self.page.views.append(fn(*args))
        self.page.update()

    def go(self, fn, *args):
        self.stack.append((fn, args))
        self.page.views.append(fn(*args))
        self.page.update()

    def back(self, e=None):
        if len(self.stack) > 1:
            self.stack.pop()
            self.page.views.pop()
            fn, args = self.stack[-1]
            self.page.views[-1] = fn(*args)   # إعادة بناء الشاشة السابقة ببيانات حديثة
            self.page.update()

    def refresh(self):
        fn, args = self.stack[-1]
        self.page.views[-1] = fn(*args)
        self.page.update()

    def simple_view(self, text):
        return ft.View("/msg", [ft.Container(ft.Text(text, size=16), padding=24)], bgcolor=BG,
                       appbar=ft.AppBar(title=ft.Text("شجرة العائلة"), bgcolor=BAR))

    # ---------------- الدخول ----------------
    def start(self):
        a = self.page.client_storage.get("access")
        r = self.page.client_storage.get("refresh")
        if a and r:
            try:
                res = self.sb.auth.set_session(a, r)
                self.save_session()
                self.after_login(res.user.id)
                return
            except Exception:
                pass
        self.reset(self.login_view)

    def save_session(self):
        s = self.sb.auth.get_session()
        if s:
            self.page.client_storage.set("access", s.access_token)
            self.page.client_storage.set("refresh", s.refresh_token)

    def after_login(self, uid):
        self.uid = uid
        rows = self.sb.table("profiles").select("*").eq("id", uid).limit(1).execute().data
        self.profile = rows[0] if rows else {}
        if config.ADMIN_ONLY and not (self.profile.get("role") == "admin"
                                      and self.profile.get("is_approved")):
            self.logout()
            self.snack("هذا التطبيق مخصص للمشرف فقط")
            return
        if not self.profile.get("is_approved"):
            self.reset(self.pending_view)
            return
        self.reload()
        self.reset(self.home_view)

    def logout(self, e=None):
        try:
            self.sb.auth.sign_out()
        except Exception:
            pass
        self.page.client_storage.remove("access")
        self.page.client_storage.remove("refresh")
        self.uid, self.profile = None, {}
        self.reset(self.login_view)

    def reload(self):
        self.people = {r["id"]: r for r in self.sb.table("persons").select("*").execute().data}
        self.marriages = self.sb.table("marriages").select("*").execute().data
        self.spouses = L.build_spouses(self.people, self.marriages)

    def login_view(self):
        email = ft.TextField(label="البريد الإلكتروني", keyboard_type=ft.KeyboardType.EMAIL)
        pw = ft.TextField(label="كلمة المرور", password=True, can_reveal_password=True)
        name = ft.TextField(label="الاسم الكامل", visible=False)
        msg = ft.Text(color="red")
        mode = {"signup": False}
        btn = ft.ElevatedButton("دخول")
        toggle = ft.TextButton("ليس لديك حساب؟ إنشاء حساب", visible=not config.ADMIN_ONLY)

        def flip(e):
            mode["signup"] = not mode["signup"]
            name.visible = mode["signup"]
            btn.text = "إنشاء حساب" if mode["signup"] else "دخول"
            toggle.text = "لديك حساب؟ تسجيل الدخول" if mode["signup"] else "ليس لديك حساب؟ إنشاء حساب"
            msg.value = ""
            self.page.update()

        def submit(e):
            em, pwd = (email.value or "").strip(), pw.value or ""
            if not em or len(pwd) < 6:
                msg.color, msg.value = "red", "اكتب البريد وكلمة مرور من 6 أحرف على الأقل"
                self.page.update()
                return
            try:
                if mode["signup"]:
                    res = self.sb.auth.sign_up({"email": em, "password": pwd, "options": {
                        "data": {"full_name": (name.value or "").strip()}}})
                    if not res.session:
                        msg.color = "green"
                        msg.value = "تم إنشاء الحساب. أكّد بريدك ثم سجّل الدخول."
                        self.page.update()
                        return
                else:
                    res = self.sb.auth.sign_in_with_password({"email": em, "password": pwd})
                self.save_session()
                self.after_login(res.user.id)
            except Exception as ex:
                msg.color, msg.value = "red", err(ex)
                self.page.update()

        btn.on_click, toggle.on_click = submit, flip
        return ft.View("/login", [ft.Column([
            ft.Icon(ft.icons.FAMILY_RESTROOM, size=64, color=TXT),
            ft.Text("شجرة العائلة", size=24, weight=BOLD, color=TXT),
            name, email, pw, msg, btn, toggle],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12)],
            bgcolor=BG, padding=24, vertical_alignment=ft.MainAxisAlignment.CENTER)

    def pending_view(self):
        def check(e):
            try:
                self.after_login(self.uid)
            except Exception as ex:
                self.snack(err(ex))

        return ft.View("/pending", [ft.Column([
            ft.Icon(ft.icons.HOURGLASS_TOP, size=64, color=TXT),
            ft.Text("حسابك بانتظار موافقة المشرف", size=20, weight=BOLD, color=TXT),
            ft.Text("بعد الموافقة اضغط تحديث.", color=TXT),
            ft.ElevatedButton("تحديث", on_click=check),
            ft.TextButton("تسجيل الخروج", on_click=self.logout)],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12)],
            bgcolor=BG, padding=24, vertical_alignment=ft.MainAxisAlignment.CENTER)

    # ---------------- الشاشة الرئيسية (شبكة الأجداد) ----------------
    def card(self, p, on_click):
        return ft.Container(
            bgcolor="white", on_click=on_click, ink=True,
            content=ft.Stack([
                ft.Image(src=self.avatar(p), fit=ft.ImageFit.COVER, left=0, top=0, right=0, bottom=0,
                         error_content=ft.Icon(ft.icons.PERSON, size=64, color="#9AA5AD")),
                ft.Container(
                    left=8, right=8, bottom=8, bgcolor=LABEL,
                    padding=ft.padding.symmetric(vertical=12, horizontal=6),
                    content=ft.Text(p["ar_name"], size=15, weight=BOLD, color=TXT, max_lines=2,
                                    text_align=ft.TextAlign.CENTER,
                                    overflow=ft.TextOverflow.ELLIPSIS))]))

    def unread_count(self):
        try:
            ids = {r["id"] for r in self.sb.table("notifications").select("id")
                   .order("created_at", desc=True).limit(50).execute().data}
            read = {r["notification_id"] for r in
                    self.sb.table("notification_reads").select("notification_id").execute().data}
            return len(ids - read)
        except Exception:
            return 0

    def home_view(self):
        n = self.unread_count()
        bell = ft.Stack([
            ft.IconButton(ft.icons.NOTIFICATIONS_OUTLINED, icon_color=TXT,
                          on_click=lambda e: self.go(self.notifications_view)),
            ft.Container(ft.Text(str(n), size=10, color="white"), bgcolor="red", border_radius=9,
                         padding=ft.padding.symmetric(horizontal=5, vertical=1),
                         top=6, right=6, visible=n > 0)], width=48, height=48)
        items = [ft.PopupMenuItem(text="رسالة للمشرف", icon=ft.icons.MAIL_OUTLINE,
                                  on_click=lambda e: self.message_dialog(None))]
        if self.is_admin:
            items += [
                ft.PopupMenuItem(text="رسائل الأعضاء", icon=ft.icons.INBOX,
                                 on_click=lambda e: self.go(self.inbox_view)),
                ft.PopupMenuItem(text="الأعضاء", icon=ft.icons.GROUP,
                                 on_click=lambda e: self.go(self.members_view))]
        items.append(ft.PopupMenuItem(text="تسجيل الخروج", icon=ft.icons.LOGOUT, on_click=self.logout))
        appbar = ft.AppBar(title=ft.Text("شجرة العائلة", weight=BOLD, color=TXT), center_title=True,
                           bgcolor=BAR, actions=[bell, ft.PopupMenuButton(items=items, icon_color=TXT)])
        roots = L.roots(self.people)
        if roots:
            body = ft.GridView(
                runs_count=2, child_aspect_ratio=1.0, spacing=12, run_spacing=12, padding=12, expand=True,
                controls=[self.card(p, lambda e, pid=p["id"]: self.go(self.person_view, pid))
                          for p in roots])
        else:
            body = ft.Container(ft.Text("لا توجد بيانات بعد. اضغط + لإضافة أول جد.",
                                        text_align=ft.TextAlign.CENTER, color=TXT),
                                alignment=ft.alignment.center, expand=True, padding=24)
        return ft.View("/", [body], appbar=appbar, bgcolor=BG, padding=0,
                       floating_action_button=ft.FloatingActionButton(
                           icon=ft.icons.ADD, on_click=lambda e: self.add_dialog(None)))

    # ---------------- صفحة الفرد ----------------
    def fetch_one(self, table, pid):
        try:
            rows = self.sb.table(table).select("*").eq("person_id", pid).limit(1).execute().data
            return rows[0] if rows else {}
        except Exception as ex:
            self.snack(err(ex))
            return {}

    def hidden_wife(self, husband_id, wife_id):
        if self.can_edit(husband_id):
            return False
        for m in self.marriages:
            if {m["person1_id"], m["person2_id"]} == {husband_id, wife_id}:
                return not m["show_wife_name"]
        return False

    def person_view(self, pid):
        p = self.people.get(pid)
        if not p:
            return self.simple_view("لم يُعثر على هذا الشخص")
        can = self.can_edit(pid)
        about, con = self.fetch_one("about_persons", pid), self.fetch_one("contacts", pid)

        photo = ft.Stack([
            ft.Container(ft.Image(src=self.avatar(p), fit=ft.ImageFit.COVER, width=220, height=220,
                                  error_content=ft.Icon(ft.icons.PERSON, size=80, color="#9AA5AD")),
                         bgcolor="white", width=220, height=220)], width=220, height=220)
        if can:
            photo.controls.append(ft.IconButton(ft.icons.CAMERA_ALT, bgcolor=LABEL, icon_color=TXT,
                                                right=4, bottom=4,
                                                on_click=lambda e: self.pick_photo(pid)))

        status = L.marital_status(p, self.marriages)
        head = [ft.Row([photo], alignment=ft.MainAxisAlignment.CENTER),
                ft.Text(p["ar_name"], size=22, weight=BOLD, color=TXT, text_align=ft.TextAlign.CENTER),
                ft.Text(status, color="#52606D", text_align=ft.TextAlign.CENTER)]
        if p.get("is_deceased"):
            head.append(ft.Text("رحمها الله" if p["gender"] == "F" else "رحمه الله",
                                color="#52606D", text_align=ft.TextAlign.CENTER))

        rows = [("الاسم بالإنجليزي", p.get("en_name")), ("تاريخ الميلاد", p.get("birth_date")),
                ("مكان الميلاد", p.get("birth_place")), ("يسكن في", p.get("living_at")),
                ("تاريخ الوفاة", p.get("death_date")),
                ("المستوى التعليمي", about.get("education_level")), ("درس في", about.get("studied_at")),
                ("الوظيفة", about.get("job")), ("الاهتمامات", about.get("interests"))]
        info = [ft.Row([ft.Text(k + ":", weight=BOLD, color=TXT), ft.Text(str(v), color=TXT, expand=True)],
                       vertical_alignment=ft.CrossAxisAlignment.START)
                for k, v in rows if v]
        if about.get("about_me"):
            info.append(ft.Divider())
            info.append(ft.Text(about["about_me"], color=TXT))
        sections = list(head)
        if info:
            sections.append(ft.Card(ft.Container(ft.Column(info, spacing=6), padding=12)))

        btns = [ft.IconButton(CONTACT_ICONS[k], tooltip=lbl, icon_color=TXT,
                              on_click=lambda e, k=k: self.page.launch_url(contact_url(k, con[k])))
                for k, lbl in CONTACT_FIELDS if con.get(k)]
        if btns:
            sections.append(ft.Row(btns, alignment=ft.MainAxisAlignment.CENTER))

        for title, ids in L.relatives(self.people, self.spouses, pid):
            chips = []
            for i in ids:
                if title == "الزوجة" and self.hidden_wife(pid, i):
                    chips.append(ft.Text("(غير معروضة)", color="#7B8794"))
                else:
                    chips.append(ft.TextButton(self.people[i]["ar_name"],
                                               on_click=lambda e, i=i: self.go(self.person_view, i)))
            sections.append(ft.Card(ft.Container(ft.Column([
                ft.Text(title, weight=BOLD, color=TXT), ft.Row(chips, wrap=True)]), padding=12)))

        sections.append(ft.Row([
            ft.Text("المناسبات", size=18, weight=BOLD, color=TXT, expand=True),
            ft.IconButton(ft.icons.ADD, tooltip="إضافة مناسبة",
                          on_click=lambda e: self.occasion_dialog(pid))]))
        try:
            occ = self.sb.table("occasions").select("*").eq("person_id", pid) \
                .order("created_at", desc=True).execute().data
            mine = set()
            if occ:
                mine = {r["occasion_id"] for r in self.sb.table("occasion_hearts").select("occasion_id")
                        .eq("user_id", self.uid).in_("occasion_id", [o["id"] for o in occ]).execute().data}
            for o in occ:
                sections.append(self.occasion_card(o, o["id"] in mine))
            if not occ:
                sections.append(ft.Text("لا توجد مناسبات", color="#7B8794"))
        except Exception as ex:
            sections.append(ft.Text(err(ex), color="red"))

        sections.append(ft.Row([
            ft.ElevatedButton("إضافة قريب", icon=ft.icons.PERSON_ADD,
                              on_click=lambda e: self.add_dialog(pid)),
            ft.OutlinedButton("رسالة عن هذا الشخص", icon=ft.icons.MAIL_OUTLINE,
                              on_click=lambda e: self.message_dialog(pid))], wrap=True))

        actions = [ft.IconButton(ft.icons.EDIT, tooltip="تعديل", icon_color=TXT,
                                 on_click=lambda e: self.go(self.edit_view, pid))] if can else []
        return ft.View(f"/person/{pid}", [ft.ListView(sections, expand=True, spacing=10, padding=12)],
                       appbar=ft.AppBar(title=ft.Text(p["ar_name"], color=TXT), bgcolor=BAR,
                                        center_title=True, actions=actions),
                       bgcolor=BG, padding=0)

    def occasion_card(self, o, hearted):
        def toggle(e):
            try:
                if hearted:
                    self.sb.table("occasion_hearts").delete().eq("occasion_id", o["id"]) \
                        .eq("user_id", self.uid).execute()
                else:
                    self.sb.table("occasion_hearts").insert({"occasion_id": o["id"]}).execute()
                self.refresh()
            except Exception as ex:
                self.snack(err(ex))

        def delete(e):
            try:
                self.sb.table("occasions").delete().eq("id", o["id"]).execute()
                self.refresh()
            except Exception as ex:
                self.snack(err(ex))

        lines = [ft.Text(OCC_TYPES.get(o["type"], o["type"]), weight=BOLD, color=TXT)]
        if o.get("content"):
            lines.append(ft.Text(o["content"], color=TXT))
        if o.get("incoming_at"):
            lines.append(ft.Text(o["incoming_at"][:10], size=12, color="#7B8794"))
        side = [ft.IconButton(ft.icons.FAVORITE if hearted else ft.icons.FAVORITE_BORDER,
                              icon_color="red", on_click=toggle),
                ft.Text(str(o.get("hearts", 0)), color=TXT)]
        if self.is_admin or o.get("created_by") == self.uid:
            side.append(ft.IconButton(ft.icons.DELETE, icon_color="#7B8794", on_click=delete))
        return ft.Card(ft.Container(ft.Row([
            ft.Column(lines, expand=True),
            ft.Column(side, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0)]), padding=12))

    # ---------------- التعديل ----------------
    def save_one(self, table, pid, data):
        r = self.sb.table(table).select("id").eq("person_id", pid).limit(1).execute().data
        if r:
            self.sb.table(table).update(data).eq("person_id", pid).execute()
        else:
            self.sb.table(table).insert({**data, "person_id": pid}).execute()

    def edit_view(self, pid):
        p = self.people[pid]
        about, con = self.fetch_one("about_persons", pid), self.fetch_one("contacts", pid)
        f = {}

        def tf(key, label, src, **kw):
            f[key] = ft.TextField(label=label, value=src.get(key) or "", **kw)
            return f[key]

        deceased = ft.Switch(label="متوفى", value=bool(p.get("is_deceased")))
        mcs = []
        for m in self.marriages:
            if pid in (m["person1_id"], m["person2_id"]):
                sid = m["person2_id"] if m["person1_id"] == pid else m["person1_id"]
                sp = self.people[sid]
                wife = sp if sp["gender"] == "F" else p
                mcs.append((m,
                            ft.Dropdown(label=f"الزواج من {sp['ar_name']}", value=m["status"],
                                        options=[ft.dropdown.Option(k, v) for k, v in MARRIAGE_STATUS.items()]),
                            ft.Switch(label=f"إظهار اسم الزوجة ({wife['ar_name']})",
                                      value=bool(m["show_wife_name"]))))

        controls = [
            tf("ar_name", "الاسم بالعربي", p), tf("en_name", "الاسم بالإنجليزي", p),
            tf("birth_date", "تاريخ الميلاد (2000-05-17)", p), tf("birth_place", "مكان الميلاد", p),
            tf("living_at", "يسكن في", p), deceased, tf("death_date", "تاريخ الوفاة (2000-05-17)", p),
            ft.Divider(),
            tf("education_level", "المستوى التعليمي", about), tf("studied_at", "درس في", about),
            tf("job", "الوظيفة", about), tf("interests", "الاهتمامات", about),
            tf("about_me", "نبذة", about, multiline=True, min_lines=3, max_lines=6),
            ft.Divider(),
            *[tf(k, lbl, con) for k, lbl in CONTACT_FIELDS],
        ]
        if mcs:
            controls.append(ft.Divider())
            for _, st, sw in mcs:
                controls += [st, sw]

        def n(k):
            return (f[k].value or "").strip() or None

        def save(e):
            if not n("ar_name"):
                self.snack("الاسم العربي مطلوب")
                return
            ok1, bd = L.parse_date(f["birth_date"].value)
            ok2, dd = L.parse_date(f["death_date"].value)
            if not (ok1 and ok2):
                self.snack("صيغة التاريخ: 2000-05-17")
                return
            dead = bool(deceased.value or dd)
            if not dead:
                dd = None
            try:
                self.sb.table("persons").update({
                    "ar_name": n("ar_name"), "en_name": n("en_name"), "birth_date": bd,
                    "birth_place": n("birth_place"), "living_at": n("living_at"),
                    "is_deceased": dead, "death_date": dd}).eq("id", pid).execute()
                self.save_one("about_persons", pid, {k: n(k) for k in (
                    "about_me", "interests", "studied_at", "job", "education_level")})
                self.save_one("contacts", pid, {k: n(k) for k, _ in CONTACT_FIELDS})
                for m, st, sw in mcs:
                    if st.value != m["status"] or bool(sw.value) != bool(m["show_wife_name"]):
                        self.sb.table("marriages").update({
                            "status": st.value, "show_wife_name": bool(sw.value)}).eq("id", m["id"]).execute()
                self.reload()
                self.snack("تم الحفظ")
                self.back()
            except Exception as ex:
                self.snack(err(ex))

        controls.append(ft.ElevatedButton("حفظ", icon=ft.icons.SAVE, on_click=save))
        return ft.View(f"/edit/{pid}", [ft.ListView(controls, expand=True, spacing=10, padding=12)],
                       appbar=ft.AppBar(title=ft.Text("تعديل البيانات", color=TXT), bgcolor=BAR,
                                        center_title=True), bgcolor=BG, padding=0)

    # ---------------- رفع الصورة ----------------
    def pick_photo(self, pid):
        self.upload_pid = pid
        self.picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.ANY)

    def on_pick(self, e):
        if not e.files or self.upload_pid is None:
            return
        f, pid = e.files[0], self.upload_pid
        if not f.path:
            self.snack("اختيار الصور غير مدعوم في هذا العرض؛ جرّبه على الهاتف")
            return
        try:
            ext = os.path.splitext(f.name)[1].lower() or ".jpg"
            path = f"persons/{pid}_{int(time.time())}{ext}"
            ctype = mimetypes.guess_type(f.name)[0] or "image/jpeg"
            with open(f.path, "rb") as fh:
                data = fh.read()
            bucket = self.sb.storage.from_(config.BUCKET)
            bucket.upload(path, data, {"content-type": ctype})
            url = bucket.get_public_url(path)
            self.sb.table("persons").update({"img_url": url}).eq("id", pid).execute()
            self.reload()
            self.refresh()
        except Exception as ex:
            self.snack(err(ex))

    # ---------------- الحوارات ----------------
    def dialog(self, title, controls, on_ok, ok_text="حفظ"):
        msg = ft.Text(color="red")
        dlg = ft.AlertDialog(modal=True, title=ft.Text(title))

        def close(e=None):
            dlg.open = False
            self.page.update()

        def ok(e):
            try:
                m = on_ok()
            except Exception as ex:
                m = err(ex)
            if m:
                msg.value = m
                self.page.update()
            else:
                close()
                self.refresh()

        dlg.content = ft.Column([*controls, msg], tight=True, scroll=ft.ScrollMode.AUTO)
        dlg.actions = [ft.TextButton(ok_text, on_click=ok), ft.TextButton("إلغاء", on_click=close)]
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()

    def add_dialog(self, ref):
        labels = list(L.KINDS) if ref else ["شخص جديد (ذكر)", "شخص جديد (أنثى)"]
        kind = ft.Dropdown(label="النوع", value="ابن" if ref else labels[0],
                           options=[ft.dropdown.Option(k) for k in labels])
        name = ft.TextField(label="الاسم")

        def ok():
            nm = (name.value or "").strip()
            if not nm:
                return "اكتب الاسم"
            return self.add_relative(ref, kind.value, nm)

        self.dialog("إضافة فرد", [kind, name], ok)

    def add_marriage(self, a, b):
        male, female = (a, b) if self.people[a]["gender"] == "M" else (b, a)
        self.sb.table("marriages").insert({"person1_id": male, "person2_id": female}).execute()

    def add_relative(self, ref, label, name):
        """يرجع نص الخطأ أو None."""
        code, g = L.KINDS[label]
        msg = L.validate_add(self.people, self.spouses, ref, label)
        if msg:
            return msg
        if code in ("father", "mother") and not self.can_edit(ref):
            return "لا تملك صلاحية تعديل هذا الشخص. أرسل رسالة للمشرف."

        def ins(row):
            return self.sb.table("persons").insert(row).execute().data[0]["id"]

        base = {"ar_name": name, "gender": g}
        if code == "new":
            ins(base)
        else:
            r = self.people[ref]
            if code in ("father", "mother"):
                new = ins(base)
                self.sb.table("persons").update({code + "_id": new}).eq("id", ref).execute()
                other = r["mother_id" if code == "father" else "father_id"]
                self.reload()
                if other:
                    self.add_marriage(new, other)
            elif code == "sibling":
                ins({**base, "father_id": r["father_id"], "mother_id": r["mother_id"]})
            elif code == "child":
                fa, mo = L.child_parents(self.people, self.spouses, ref)
                ins({**base, "father_id": fa, "mother_id": mo})
            elif code == "spouse":
                new = ins(base)
                self.reload()
                self.add_marriage(ref, new)
        self.reload()
        return None

    def occasion_dialog(self, pid):
        typ = ft.Dropdown(label="النوع", value="other",
                          options=[ft.dropdown.Option(k, v) for k, v in OCC_TYPES.items()])
        content = ft.TextField(label="التفاصيل", multiline=True, min_lines=2, max_lines=5)
        date = ft.TextField(label="التاريخ (2026-12-31) اختياري")

        def ok():
            good, d = L.parse_date(date.value)
            if not good:
                return "صيغة التاريخ: 2026-12-31"
            self.sb.table("occasions").insert({
                "person_id": pid, "type": typ.value,
                "content": (content.value or "").strip() or None, "incoming_at": d}).execute()
            return None

        self.dialog("إضافة مناسبة", [typ, content, date], ok)

    def message_dialog(self, pid):
        typ = ft.Dropdown(label="النوع", value="suggestion",
                          options=[ft.dropdown.Option(k, v) for k, v in MSG_TYPES.items()])
        text = ft.TextField(label="الرسالة", multiline=True, min_lines=3, max_lines=6)

        def ok():
            t = (text.value or "").strip()
            if not t:
                return "اكتب الرسالة"
            self.sb.table("messages").insert({"type": typ.value, "message": t, "person_id": pid}).execute()
            self.snack("تم إرسال الرسالة للمشرف")
            return None

        self.dialog("رسالة للمشرف", [typ, text], ok, "إرسال")

    # ---------------- الإشعارات ----------------
    def notifications_view(self):
        items = []
        try:
            rows = self.sb.table("notifications").select("*").order("created_at", desc=True) \
                .limit(50).execute().data
            read = {r["notification_id"] for r in
                    self.sb.table("notification_reads").select("notification_id").execute().data}
            fresh = [r["id"] for r in rows if r["id"] not in read]
            for r in rows:
                is_new = r["id"] in fresh
                items.append(ft.Card(ft.Container(ft.Column([
                    ft.Text(r["notification"], color=TXT, weight=BOLD if is_new else None),
                    ft.Text(r["created_at"][:10], size=11, color="#7B8794")]), padding=12)))
            if fresh:
                self.sb.table("notification_reads").insert(
                    [{"notification_id": i} for i in fresh]).execute()
            if not rows:
                items.append(ft.Text("لا توجد إشعارات", color="#7B8794"))
        except Exception as ex:
            items.append(ft.Text(err(ex), color="red"))
        return ft.View("/notifications", [ft.ListView(items, expand=True, spacing=8, padding=12)],
                       appbar=ft.AppBar(title=ft.Text("الإشعارات", color=TXT), bgcolor=BAR,
                                        center_title=True), bgcolor=BG, padding=0)

    # ---------------- شاشات المشرف ----------------
    def inbox_view(self):
        items = []
        try:
            rows = self.sb.table("messages").select("*").order("created_at", desc=True) \
                .limit(100).execute().data
            for m in rows:
                def setst(e, mid=m["id"], st="done"):
                    try:
                        self.sb.table("messages").update({"status": st}).eq("id", mid).execute()
                        self.refresh()
                    except Exception as ex:
                        self.snack(err(ex))
                who = self.people.get(m.get("person_id"), {}).get("ar_name")
                head = MSG_TYPES.get(m["type"], m["type"]) + (f" — عن {who}" if who else "")
                items.append(ft.Card(ft.Container(ft.Column([
                    ft.Text(head, weight=BOLD, color=TXT), ft.Text(m["message"], color=TXT),
                    ft.Row([ft.Text(f"{m['status']} · {m['created_at'][:10]}", size=11,
                                    color="#7B8794", expand=True),
                            ft.IconButton(ft.icons.VISIBILITY, tooltip="تمت القراءة",
                                          on_click=lambda e, f=setst: f(e, st="read")),
                            ft.IconButton(ft.icons.CHECK_CIRCLE, tooltip="تم الحل",
                                          on_click=setst)])]), padding=12)))
            if not rows:
                items.append(ft.Text("لا توجد رسائل", color="#7B8794"))
        except Exception as ex:
            items.append(ft.Text(err(ex), color="red"))
        return ft.View("/inbox", [ft.ListView(items, expand=True, spacing=8, padding=12)],
                       appbar=ft.AppBar(title=ft.Text("رسائل الأعضاء", color=TXT), bgcolor=BAR,
                                        center_title=True), bgcolor=BG, padding=0)

    def members_view(self):
        items = []
        try:
            profs = self.sb.table("profiles").select("*").order("created_at", desc=True).execute().data
            opts = [ft.dropdown.Option("0", "— بدون تغيير —")] + [
                ft.dropdown.Option(str(i), p["ar_name"])
                for i, p in sorted(self.people.items(), key=lambda kv: kv[1]["ar_name"])]
            for pr in profs:
                link = ft.Dropdown(label="ربط بفرد في الشجرة", options=opts,
                                   value=str(pr["person_id"]) if pr.get("person_id") in self.people else "0")
                sw = ft.Switch(label="موافَق عليه", value=bool(pr["is_approved"]))

                def save(e, uid=pr["id"], sw=sw, link=link):
                    try:
                        self.sb.rpc("admin_set_member", {
                            "p_user": uid, "p_approved": bool(sw.value),
                            "p_person": int(link.value) or None}).execute()
                        self.snack("تم الحفظ")
                    except Exception as ex:
                        self.snack(err(ex))
                items.append(ft.Card(ft.Container(ft.Column([
                    ft.Text(pr.get("full_name") or str(pr["id"])[:8], weight=BOLD, color=TXT),
                    sw, link, ft.ElevatedButton("حفظ", on_click=save)]), padding=12)))
        except Exception as ex:
            items.append(ft.Text(err(ex), color="red"))
        return ft.View("/members", [ft.ListView(items, expand=True, spacing=8, padding=12)],
                       appbar=ft.AppBar(title=ft.Text("الأعضاء", color=TXT), bgcolor=BAR,
                                        center_title=True), bgcolor=BG, padding=0)


def main(page: ft.Page):
    if config.SUPABASE_KEY.startswith("ضع"):
        page.add(ft.Text("افتح config.py وضع مفتاح anon في SUPABASE_KEY", size=18))
        return
    FamilyApp(page)


if __name__ == "__main__":
    if os.environ.get("FAMILY_WEB"):          # للتجربة في المتصفح (Termux)
        ft.app(target=main, view=ft.AppView.WEB_BROWSER)
    else:
        ft.app(target=main)
