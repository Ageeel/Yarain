"""ثوابت وأدوات مشتركة بين main.py وتصميم صفحة التفاصيل."""
import flet as ft

BLUE = "#0B3FA0"   # الأزرق المستعمل في coin_version

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


def field(*a, **kw):
    """حقل نص بألوان سوداء واضحة."""
    kw.setdefault("color", "black")
    kw.setdefault("border_color", "black")
    kw.setdefault("focused_border_color", BLUE)
    kw.setdefault("cursor_color", "black")
    kw.setdefault("label_style", ft.TextStyle(color="black"))
    return ft.TextField(*a, **kw)
