# إعدادات الاتصال بـ Supabase
SUPABASE_URL = "https://rljonfizqfqdxmzuuepm.supabase.co"

# ضع هنا مفتاح anon (يسمى أحيانًا publishable key) فقط.
# ممنوع وضع مفتاح service_role في التطبيق نهائيًا.
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJsam9uZml6cWZxZHhtenV1ZXBtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTM3MTE0NDQsImV4cCI6MjEwOTI4NzQ0NH0.LfuqO9MfVZ_Xi21y1r-MI2bx5XdapkWVIwX-p6LJqJg"

BUCKET = "images"
_PUB = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}"
AVATAR = {"F": f"{_PUB}/female.png", "M": f"{_PUB}/male.png"}  # ارفع male.png إلى نفس الـ bucket

# تطبيق إدخال البيانات: للمشرف فقط (يخفي إنشاء الحساب ويرفض أي حساب غير مشرف)
ADMIN_ONLY = True
