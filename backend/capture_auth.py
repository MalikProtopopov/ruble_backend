"""Authenticate via OTP 111111 and capture real responses of every authed endpoint."""
import json, urllib.request, urllib.error

B = "http://127.0.0.1:8000"


def call(method, path, token=None, body=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data=data, headers=h, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def login_otp(email):
    call("POST", "/api/v1/auth/send-otp", body={"email": email})
    _, raw = call("POST", "/api/v1/auth/verify-otp", body={"email": email, "code": "111111"})
    return json.loads(raw)["access_token"]


def show(label, code, raw, limit=900):
    try:
        pretty = json.dumps(json.loads(raw), ensure_ascii=False, indent=1)
    except Exception:
        pretty = raw
    if len(pretty) > limit:
        pretty = pretty[:limit] + " …(обрезано)"
    print(f"\n### {label}  →  HTTP {code}\n{pretty}")


donor = login_otp("donor@example.com")
patron = login_otp("patron@example.com")
print("AUTH OK: donor + patron через OTP 111111")

# collect ids
camps = json.loads(call("GET", "/api/v1/campaigns", donor)[1])["data"]
cid = camps[0]["id"]
don = json.loads(call("GET", "/api/v1/donations", donor)[1])
did = (don.get("data") or [{}])[0].get("id")
subs = json.loads(call("GET", "/api/v1/subscriptions", donor)[1])
sid = subs[0]["id"] if subs else None
txns = json.loads(call("GET", "/api/v1/transactions", donor)[1])
tid = (txns.get("data") or [{}])[0].get("id")

# ---- authed GET screens ----
show("GET /me (профиль)", *call("GET", "/api/v1/me", donor))
show("GET /campaigns [0] (лента, PER-USER поля)", *( (lambda c: (c[0], json.dumps(json.loads(c[1])["data"][0], ensure_ascii=False)))(call("GET","/api/v1/campaigns",donor)) ))
show("GET /campaigns/{id} (детали, per-user)", *call("GET", f"/api/v1/campaigns/{cid}", donor))
show("GET /donations [список]", *call("GET", "/api/v1/donations", donor))
show("GET /donations/{id} (детали)", *call("GET", f"/api/v1/donations/{did}", donor)) if did else None
show("GET /subscriptions", *call("GET", "/api/v1/subscriptions", donor))
show("GET /subscriptions/active", *call("GET", "/api/v1/subscriptions/active", donor))
show("GET /transactions", *call("GET", "/api/v1/transactions", donor))
show("GET /transactions/{id}", *call("GET", f"/api/v1/transactions/{tid}", donor)) if tid else None
show("GET /impact", *call("GET", "/api/v1/impact", donor))
show("GET /impact/achievements", *call("GET", "/api/v1/impact/achievements", donor))
show("GET /thanks/unseen", *call("GET", "/api/v1/thanks/unseen", donor))
show("GET /payment-methods", *call("GET", "/api/v1/payment-methods", donor))
show("GET /payment-methods/orphans", *call("GET", "/api/v1/payment-methods/orphans", donor))
show("GET /patron/payment-links (PATRON)", *call("GET", "/api/v1/patron/payment-links", patron))

# ---- authed POST flows ----
# create donation to a campaign the donor hasn't hit recently → 201 (or 429 cooldown)
show("POST /donations (создание)", *call("POST", "/api/v1/donations", donor,
     {"campaign_id": camps[1]["id"], "amount_kopecks": 5000}))
show("POST /donations повтор в тот же сбор (кулдаун 429)", *call("POST", "/api/v1/donations", donor,
     {"campaign_id": camps[1]["id"], "amount_kopecks": 5000}))
# create subscription
show("POST /subscriptions (создание)", *call("POST", "/api/v1/subscriptions", donor,
     {"amount_kopecks": 300, "billing_period": "monthly", "allocation_strategy": "platform_pool"}))
# patron payment link
show("POST /patron/payment-links (PATRON)", *call("POST", "/api/v1/patron/payment-links", patron,
     {"campaign_id": cid, "amount_kopecks": 10000}))
