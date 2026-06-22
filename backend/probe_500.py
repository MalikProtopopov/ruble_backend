"""Probe every readable endpoint for 5xx errors against the local instance."""
import json, urllib.request, urllib.error
from uuid import uuid4

from app.core.security import create_access_token
from app.core.config import settings

B = "http://localhost:8000"
RESULTS = []  # (method, path, status, note)


def call(method, path, token=None, body=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data=data, headers=h, method=method)
    try:
        r = urllib.request.urlopen(req)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa
        return -1, str(e).encode()


def rec(method, path, token=None, body=None):
    code, raw = call(method, path, token, body)
    RESULTS.append((method, path, code))
    return code, raw


# 1) admin token
code, raw = call("POST", "/api/v1/admin/auth/login", body={"email": "admin@porubly.ru", "password": "Admin12345!"})
admin = json.loads(raw)["access_token"]

# 2) collect ids from admin (before any anon user exists)
def data(path):
    c, raw = call("GET", path, admin)
    try:
        d = json.loads(raw)
        return d["data"] if isinstance(d, dict) and "data" in d else d
    except Exception:
        return []

users = data("/api/v1/admin/users")
donor_id = next(u["id"] for u in users if u["role"] == "donor" and u["is_active"])
patron_id = next(u["id"] for u in users if u["role"] == "patron")
admin_id = users and None  # admins list separate
fnds = data("/api/v1/admin/foundations")
camps = data("/api/v1/admin/campaigns")
docs = data("/api/v1/admin/documents")
achs = data("/api/v1/admin/achievements")
medias = data("/api/v1/admin/media")
admins = data("/api/v1/admin/admins")

fnd_id = fnds[0]["id"]
camp_active = next(c["id"] for c in camps if c["status"] == "active")
camp_completed = next((c["id"] for c in camps if c["status"] == "completed"), camp_active)
doc_id = docs[0]["id"]
ach_id = achs[0]["id"]
media_id = medias[0]["id"]
admin_self = admins[0]["id"]

# 3) donor & patron tokens (minted directly)
donor = create_access_token(donor_id, "donor")
patron = create_access_token(patron_id, "patron")

# donor-owned ids
def first_id(path, tok):
    c, raw = call("GET", path, tok)
    try:
        d = json.loads(raw)
        items = d["data"] if isinstance(d, dict) and "data" in d else d
        return items[0]["id"] if items else None
    except Exception:
        return None

donation_id = first_id("/api/v1/donations", donor)
sub_id = first_id("/api/v1/subscriptions", donor)
txn_id = first_id("/api/v1/transactions", donor)
# thanks id from completed campaign detail
_, raw = call("GET", f"/api/v1/campaigns/{camp_completed}", donor)
try:
    thanks_id = (json.loads(raw).get("thanks_contents") or [{}])[0].get("id")
except Exception:
    thanks_id = None
pm_id = first_id("/api/v1/payment-methods", donor)

# document slug (public)
_, raw = call("GET", "/api/v1/documents", donor)
slug = (json.loads(raw).get("data") or [{}])[0].get("slug", "offerta")

RND = str(uuid4())

# 4) device-register to create an anonymous user (reproduces realistic prod state)
rec("POST", "/api/v1/auth/device-register", body={"device_id": "probe-device-0001"})

# 5) endpoint matrix: (method, path, token)
ep = [
    ("GET", "/api/v1/health", None),
    # client - public/donor
    ("GET", "/api/v1/me", donor),
    ("GET", "/api/v1/campaigns", donor),
    ("GET", "/api/v1/campaigns/today", donor),
    ("GET", f"/api/v1/campaigns/{camp_active}", donor),
    ("GET", f"/api/v1/campaigns/{camp_active}/documents", donor),
    ("GET", f"/api/v1/campaigns/{camp_active}/share", donor),
    ("GET", "/api/v1/foundations", donor),
    ("GET", f"/api/v1/foundations/{fnd_id}", donor),
    ("GET", "/api/v1/documents", donor),
    ("GET", f"/api/v1/documents/{slug}", donor),
    ("GET", "/api/v1/donations", donor),
    ("GET", f"/api/v1/donations/{donation_id or RND}", donor),
    ("GET", "/api/v1/subscriptions", donor),
    ("GET", "/api/v1/subscriptions/active", donor),
    ("GET", "/api/v1/transactions", donor),
    ("GET", f"/api/v1/transactions/{txn_id or RND}", donor),
    ("GET", "/api/v1/impact", donor),
    ("GET", "/api/v1/impact/achievements", donor),
    ("GET", "/api/v1/thanks/unseen", donor),
    ("GET", f"/api/v1/thanks/{thanks_id or RND}", donor),
    ("GET", "/api/v1/payment-methods", donor),
    ("GET", "/api/v1/payment-methods/orphans", donor),
    # patron
    ("GET", "/api/v1/patron/payment-links", patron),
    # admin
    ("GET", "/api/v1/admin/foundations", admin),
    ("GET", f"/api/v1/admin/foundations/{fnd_id}", admin),
    ("GET", "/api/v1/admin/campaigns", admin),
    ("GET", f"/api/v1/admin/campaigns/{camp_active}", admin),
    ("GET", f"/api/v1/admin/campaigns/{camp_active}/offline-payments", admin),
    ("GET", "/api/v1/admin/users", admin),
    ("GET", f"/api/v1/admin/users/{donor_id}", admin),
    ("GET", "/api/v1/admin/stats/overview", admin),
    ("GET", f"/api/v1/admin/stats/campaigns/{camp_active}", admin),
    ("GET", "/api/v1/admin/payouts", admin),
    ("GET", "/api/v1/admin/payouts/balance", admin),
    ("GET", "/api/v1/admin/achievements", admin),
    ("GET", "/api/v1/admin/logs/allocation-logs", admin),
    ("GET", "/api/v1/admin/logs/notification-logs", admin),
    ("GET", "/api/v1/admin/admins", admin),
    ("GET", f"/api/v1/admin/admins/{admin_self}", admin),
    ("GET", "/api/v1/admin/documents", admin),
    ("GET", f"/api/v1/admin/documents/{doc_id}", admin),
    ("GET", "/api/v1/admin/media", admin),
    ("GET", f"/api/v1/admin/media/{media_id}", admin),
]
for m, p, t in ep:
    rec(m, p, t)

# report
print(f"{'STATUS':>6}  METHOD PATH")
bad = []
for m, p, code in RESULTS:
    mark = "  " if code < 500 else "❌"
    if code >= 500 or code == -1:
        bad.append((m, p, code))
    print(f"{mark}{code:>4}  {m:6} {p}")

print("\n===== 5xx / ошибки =====")
if not bad:
    print("нет 5xx 🎉")
else:
    for m, p, code in bad:
        print(f"  {code}  {m} {p}")
