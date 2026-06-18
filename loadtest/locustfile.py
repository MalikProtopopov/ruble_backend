"""
Load test for "По Рублю" backend.

Usage:
    pip install locust
    locust -f loadtest/locustfile.py --host https://YOUR_TEST_HOST

Then open http://localhost:8089 in browser to configure users & ramp-up.

Scenarios model a typical mobile user session:
  1. Register anonymous device (once per user)
  2. Browse campaigns (most frequent)
  3. View campaign detail
  4. Create a donation (less frequent, heavy)
  5. Check profile & impact
  6. List donations history
"""

import random
import string
import uuid

from locust import HttpUser, between, task


def random_device_id() -> str:
    return "loadtest-" + uuid.uuid4().hex[:16]


class MobileUser(HttpUser):
    """Simulates a mobile app user browsing campaigns and donating."""

    wait_time = between(1, 3)  # 1-3 sec between actions (realistic think time)

    # Shared state per user instance
    access_token: str | None = None
    refresh_token: str | None = None
    user_id: str | None = None
    campaign_ids: list[str] = []

    def on_start(self):
        """Register anonymous device on user spawn."""
        self._device_register()
        self._fetch_campaign_ids()

    def _device_register(self):
        device_id = random_device_id()
        resp = self.client.post(
            "/api/v1/auth/device-register",
            json={
                "device_id": device_id,
                "timezone": "Europe/Moscow",
            },
            name="/auth/device-register",
        )
        if resp.status_code == 200:
            data = resp.json()
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            self.user_id = data["user"]["id"]

    def _headers(self) -> dict:
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        return {}

    def _fetch_campaign_ids(self):
        """Pre-fetch active campaign IDs for later use."""
        resp = self.client.get(
            "/api/v1/campaigns?status=active&limit=20",
            headers=self._headers(),
            name="/campaigns (seed)",
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            self.campaign_ids = [c["id"] for c in data]

    # ── High-frequency: browsing ─────────────────────────────────

    @task(10)
    def list_campaigns(self):
        """GET /campaigns — main feed, heaviest read endpoint."""
        self.client.get(
            "/api/v1/campaigns?status=active&limit=20",
            headers=self._headers(),
            name="/campaigns",
        )

    @task(5)
    def campaigns_today(self):
        """GET /campaigns/today — home screen widget."""
        self.client.get(
            "/api/v1/campaigns/today",
            headers=self._headers(),
            name="/campaigns/today",
        )

    @task(6)
    def view_campaign_detail(self):
        """GET /campaigns/{id} — campaign detail screen."""
        if not self.campaign_ids:
            return
        cid = random.choice(self.campaign_ids)
        self.client.get(
            f"/api/v1/campaigns/{cid}",
            headers=self._headers(),
            name="/campaigns/[id]",
        )

    # ── Medium-frequency: profile & impact ───────────────────────

    @task(3)
    def get_profile(self):
        """GET /me — profile screen."""
        self.client.get(
            "/api/v1/me",
            headers=self._headers(),
            name="/me",
        )

    @task(2)
    def get_impact(self):
        """GET /impact — impact summary."""
        self.client.get(
            "/api/v1/impact",
            headers=self._headers(),
            name="/impact",
        )

    @task(2)
    def get_achievements(self):
        """GET /impact/achievements."""
        self.client.get(
            "/api/v1/impact/achievements",
            headers=self._headers(),
            name="/impact/achievements",
        )

    @task(2)
    def list_donations(self):
        """GET /donations — donation history."""
        self.client.get(
            "/api/v1/donations",
            headers=self._headers(),
            name="/donations",
        )

    # ── Low-frequency: donations ─────────────────────────────────

    @task(1)
    def create_donation(self):
        """POST /donations — create a one-time donation.

        This hits YooKassa in production. In test env with mock/no YooKassa
        it will likely return 422/500 — that's fine, we're measuring backend
        processing time and DB write performance.
        """
        if not self.campaign_ids:
            return
        cid = random.choice(self.campaign_ids)
        self.client.post(
            "/api/v1/donations",
            json={
                "campaign_id": cid,
                "amount_kopecks": random.choice([100, 500, 1000, 5000]),
            },
            headers=self._headers(),
            name="/donations (create)",
        )

    # ── Low-frequency: subscriptions & foundations ────────────────

    @task(1)
    def list_subscriptions(self):
        """GET /subscriptions."""
        self.client.get(
            "/api/v1/subscriptions",
            headers=self._headers(),
            name="/subscriptions",
        )

    @task(1)
    def list_foundations(self):
        """GET /foundations."""
        self.client.get(
            "/api/v1/foundations",
            headers=self._headers(),
            name="/foundations",
        )

    # ── Token refresh (simulates long session) ───────────────────

    @task(1)
    def refresh_token(self):
        """POST /auth/refresh — token refresh."""
        if not self.refresh_token:
            return
        resp = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": self.refresh_token},
            name="/auth/refresh",
        )
        if resp.status_code == 200:
            data = resp.json()
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]


class BrowsingUser(HttpUser):
    """Unauthenticated user — just browses public endpoints.

    Represents visitors who haven't installed the app yet.
    Lighter load, no writes.
    """

    wait_time = between(2, 5)
    weight = 1  # MobileUser has default weight=1, so 50/50 split

    campaign_ids: list[str] = []

    def on_start(self):
        resp = self.client.get(
            "/api/v1/campaigns?status=active&limit=20",
            name="/campaigns (anon seed)",
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            self.campaign_ids = [c["id"] for c in data]

    @task(10)
    def list_campaigns(self):
        self.client.get(
            "/api/v1/campaigns?status=active&limit=20",
            name="/campaigns (anon)",
        )

    @task(5)
    def campaigns_today(self):
        self.client.get(
            "/api/v1/campaigns/today",
            name="/campaigns/today (anon)",
        )

    @task(4)
    def view_campaign_detail(self):
        if not self.campaign_ids:
            return
        cid = random.choice(self.campaign_ids)
        self.client.get(
            f"/api/v1/campaigns/{cid}",
            name="/campaigns/[id] (anon)",
        )

    @task(2)
    def list_foundations(self):
        self.client.get(
            "/api/v1/foundations",
            name="/foundations (anon)",
        )

    @task(1)
    def health(self):
        self.client.get(
            "/api/v1/health",
            name="/health",
        )
