"""عميل Supabase خفيف يعتمد على requests فقط (بديل مكتبة supabase).
يوفّر نفس الواجهة التي يستعملها main.py، وهو أنسب لبناء APK لأن requests مكتبة بايثون صرفة."""
from types import SimpleNamespace as NS

import requests


class APIError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.message = message
        self.code = code


def _msg(r):
    try:
        j = r.json()
    except Exception:
        return f"HTTP {r.status_code}"
    if isinstance(j, dict):
        for k in ("message", "msg", "error_description", "error"):
            if j.get(k):
                return str(j[k])
    return f"HTTP {r.status_code}"


def _v(val):
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)


class Client:
    def __init__(self, url, key, timeout=20):
        self.url, self.key, self.timeout = url.rstrip("/"), key, timeout
        self.access = self.refresh = None
        self.http = requests.Session()
        self.auth = Auth(self)
        self.storage = Storage(self)

    def headers(self, extra=None):
        h = {"apikey": self.key, "Authorization": "Bearer " + (self.access or self.key)}
        if extra:
            h.update(extra)
        return h

    def request(self, method, path, retry=True, headers=None, timeout=None, **kw):
        try:
            r = self.http.request(method, self.url + path, headers=self.headers(headers),
                                  timeout=timeout or self.timeout, **kw)
        except requests.RequestException as ex:
            raise APIError("تعذّر الاتصال بالخادم. تحقق من الإنترنت.") from ex
        if r.status_code == 401 and retry and self.refresh and not path.startswith("/auth/"):
            if self.auth.refresh_session():
                return self.request(method, path, retry=False, headers=headers,
                                    timeout=timeout, **kw)
        if r.status_code >= 400:
            raise APIError(_msg(r), r.status_code)
        return r

    def table(self, name):
        return Query(self, name)

    def rpc(self, fn, params=None):
        return Rpc(self, fn, params or {})


class Auth:
    def __init__(self, c):
        self.c = c
        self._user = None

    def _store(self, j):
        self.c.access, self.c.refresh = j.get("access_token"), j.get("refresh_token")
        self._user = j.get("user") or self._user

    def get_session(self):
        if not self.c.access:
            return None
        return NS(access_token=self.c.access, refresh_token=self.c.refresh)

    def _uid(self):
        return NS(id=(self._user or {}).get("id"))

    def sign_in_with_password(self, cred):
        r = self.c.request("POST", "/auth/v1/token", params={"grant_type": "password"},
                           json={"email": cred["email"], "password": cred["password"]})
        self._store(r.json())
        return NS(user=self._uid(), session=self.get_session())

    def sign_up(self, cred):
        body = {"email": cred["email"], "password": cred["password"]}
        data = (cred.get("options") or {}).get("data")
        if data:
            body["data"] = data
        j = self.c.request("POST", "/auth/v1/signup", json=body).json()
        if j.get("access_token"):
            self._store(j)
            return NS(user=self._uid(), session=self.get_session())
        return NS(user=NS(id=(j.get("user") or j).get("id")), session=None)

    def refresh_session(self):
        if not self.c.refresh:
            return False
        try:
            r = self.c.http.post(self.c.url + "/auth/v1/token",
                                 params={"grant_type": "refresh_token"},
                                 headers={"apikey": self.c.key},
                                 json={"refresh_token": self.c.refresh}, timeout=self.c.timeout)
        except requests.RequestException:
            return False
        if r.status_code >= 400:
            self.c.access = self.c.refresh = None
            return False
        self._store(r.json())
        return True

    def set_session(self, access, refresh):
        self.c.access, self.c.refresh = access, refresh
        if not self.refresh_session():
            raise APIError("انتهت الجلسة. سجّل الدخول من جديد.")
        return NS(user=self._uid(), session=self.get_session())

    def sign_out(self):
        try:
            self.c.request("POST", "/auth/v1/logout", retry=False)
        except Exception:
            pass
        self.c.access = self.c.refresh = None
        self._user = None


class Query:
    def __init__(self, c, table):
        self.c, self.t = c, table
        self.method, self.params, self.body, self.prefer = "GET", [], None, None

    def select(self, cols="*"):
        self.method = "GET"
        self.params.append(("select", cols))
        return self

    def insert(self, data):
        self.method, self.body, self.prefer = "POST", data, "return=representation"
        return self

    def update(self, data):
        self.method, self.body, self.prefer = "PATCH", data, "return=representation"
        return self

    def delete(self):
        self.method, self.prefer = "DELETE", "return=minimal"
        return self

    def eq(self, col, val):
        self.params.append((col, "is.null" if val is None else "eq." + _v(val)))
        return self

    def in_(self, col, vals):
        self.params.append((col, "in.(" + ",".join(_v(v) for v in vals) + ")"))
        return self

    def order(self, col, desc=False):
        self.params.append(("order", f"{col}.{'desc' if desc else 'asc'}"))
        return self

    def limit(self, n):
        self.params.append(("limit", str(int(n))))
        return self

    def execute(self):
        headers = {}
        if self.prefer:
            headers["Prefer"] = self.prefer
        params = list(self.params)
        if self.method == "GET" and not any(k == "select" for k, _ in params):
            params.append(("select", "*"))
        kw = {"params": params, "headers": headers}
        if self.body is not None:
            kw["json"] = self.body
        r = self.c.request(self.method, "/rest/v1/" + self.t, **kw)
        return NS(data=r.json() if r.content else [])


class Rpc:
    def __init__(self, c, fn, params):
        self.c, self.fn, self.params = c, fn, params

    def execute(self):
        r = self.c.request("POST", "/rest/v1/rpc/" + self.fn, json=self.params)
        return NS(data=r.json() if r.content else None)


class Storage:
    def __init__(self, c):
        self.c = c

    def from_(self, bucket):
        return Bucket(self.c, bucket)


class Bucket:
    def __init__(self, c, bucket):
        self.c, self.b = c, bucket

    def upload(self, path, data, opts=None):
        ct = (opts or {}).get("content-type", "application/octet-stream")
        self.c.request("POST", f"/storage/v1/object/{self.b}/{path}",
                       headers={"Content-Type": ct, "x-upsert": "false"}, data=data, timeout=120)

    def get_public_url(self, path):
        return f"{self.c.url}/storage/v1/object/public/{self.b}/{path}"


def create_client(url, key):
    return Client(url, key)
