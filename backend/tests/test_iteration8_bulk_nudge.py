"""Iteration 8 backend tests — bulk-nudge endpoint, NotificationKind centralisation, per-row nudge regression."""
import os
import uuid
import time
import subprocess
import pytest
import requests
from datetime import datetime, timezone, timedelta


def _load_frontend_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for line in open(p):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)


_load_frontend_env()
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"

ACCOUNTS = {
    "submitter": {"email": "submitter@govern.app", "password": "Pass1234!", "name": "Sara Submitter", "role": "submitter", "team": "Marketing", "designation": "Marketing Associate"},
    "reviewer":  {"email": "reviewer@govern.app",  "password": "Pass1234!", "name": "Reza Reviewer",  "role": "reviewer",  "team": "Product",   "designation": "Senior Product Manager"},
    "lead":      {"email": "lead@govern.app",      "password": "Pass1234!", "name": "Maya Lead",      "role": "marketing_lead", "team": "Marketing", "designation": "Head of Marketing"},
    "vp":        {"email": "vp@govern.app",        "password": "Pass1234!", "name": "Victoria Vee",   "role": "vp",        "team": "Marketing", "designation": "VP of Marketing"},
    "ceo":       {"email": "ceo@govern.app",       "password": "Pass1234!", "name": "Carl Chief",     "role": "ceo",       "team": "Executive", "designation": "Chief Executive Officer"},
}


# ---------- auth helpers ----------
def _login(email, password):
    return requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=20)


def _ensure_user(key):
    info = ACCOUNTS[key]
    r = _login(info["email"], info["password"])
    if r.status_code == 200:
        return r.json()["token"], r.json()["user"]
    payload = {"email": info["email"], "password": info["password"], "name": info["name"], "role": info["role"], "team": info["team"], "designation": info["designation"]}
    rr = requests.post(f"{BASE_URL}/auth/register", json=payload, timeout=20)
    if rr.status_code == 200:
        return rr.json()["token"], rr.json()["user"]
    r2 = _login(info["email"], info["password"])
    assert r2.status_code == 200, f"Could not log in {key}: register={rr.status_code} {rr.text}; login={r2.status_code} {r2.text}"
    return r2.json()["token"], r2.json()["user"]


@pytest.fixture(scope="session")
def tokens():
    out = {}
    for k in ACCOUNTS:
        tk, u = _ensure_user(k)
        out[k] = {"token": tk, "user": u}
    return out


def _h(tokens, key):
    return {"Authorization": f"Bearer {tokens[key]['token']}", "Content-Type": "application/json"}


def _future(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


def _score_result(tier="product_only"):
    return {
        "brand_alignment_score": 80, "completeness_score": 85, "content_classification": "routine",
        "risk_flags": [], "overall_score": 80, "recommended_tier": tier,
        "reasoning": "TEST", "questions_to_resolve": [],
    }


def _timeline():
    return {"accept_by": _future(2), "review_by": _future(4), "approve_by": _future(6)}


def _make_sub(tokens, submitter_key, *, assignee_id, tier="product_only", request_type="custom_email", title=None):
    body = {
        "title": title or f"TEST_IT8_{uuid.uuid4().hex[:8]}",
        "request_type": request_type,
        "brief": "Brief", "content": "Content",
        "deadline": _future(10),
        "score_result": _score_result(tier),
        "chosen_tier": tier,
        "attachments": [],
        "timeline": _timeline(),
        "assigned_user_id": assignee_id,
    }
    r = requests.post(f"{BASE_URL}/submissions", json=body, headers=_h(tokens, submitter_key), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _accept(tokens, key, sid):
    return requests.post(f"{BASE_URL}/submissions/{sid}/accept", json={}, headers=_h(tokens, key), timeout=20)


def _approve(tokens, key, sid, note=""):
    return requests.post(f"{BASE_URL}/submissions/{sid}/approve", json={"note": note}, headers=_h(tokens, key), timeout=20)


def _mark_live(tokens, key, sid):
    return requests.post(f"{BASE_URL}/submissions/{sid}/mark-live", json={}, headers=_h(tokens, key), timeout=20)


def _get_sub(tokens, key, sid):
    return requests.get(f"{BASE_URL}/submissions/{sid}", headers=_h(tokens, key), timeout=20)


def _bulk_nudge(tokens, key, ids, note=None, auth=True):
    payload = {"submission_ids": ids}
    if note is not None:
        payload["note"] = note
    headers = _h(tokens, key) if auth else {"Content-Type": "application/json"}
    return requests.post(f"{BASE_URL}/submissions/bulk-nudge", json=payload, headers=headers, timeout=60)


def _notifications(tokens, key):
    return requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, key), timeout=20)


# ---------- 1) Auth + empty payload ----------
class TestBulkNudgeBasics:
    def test_requires_auth(self, tokens):
        r = _bulk_nudge(tokens, "lead", [], auth=False)
        assert r.status_code in (401, 403), r.text

    def test_empty_ids_returns_400(self, tokens):
        r = _bulk_nudge(tokens, "lead", [])
        assert r.status_code == 400, r.text
        assert "submission_ids" in r.text.lower()

    def test_response_shape(self, tokens):
        # one valid (pending_acceptance) + one unknown id
        sub = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"])
        bogus = str(uuid.uuid4())
        r = _bulk_nudge(tokens, "lead", [sub["id"], bogus], note="hello")
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body.keys()) >= {"nudged", "nudged_ids", "failed"}
        assert isinstance(body["nudged"], int)
        assert isinstance(body["nudged_ids"], list)
        assert isinstance(body["failed"], list)
        assert sub["id"] in body["nudged_ids"]
        assert any(f["id"] == bogus and f["reason"] == "not_found" for f in body["failed"])


# ---------- 2) Status filtering ----------
class TestBulkNudgeStatusFiltering:
    def test_nudges_pending_acceptance_and_in_progress(self, tokens):
        # pending_acceptance
        s1 = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"])
        # in_progress
        s2 = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"])
        a = _accept(tokens, "reviewer", s2["id"])
        assert a.status_code == 200

        r = _bulk_nudge(tokens, "lead", [s1["id"], s2["id"]], note="ping")
        assert r.status_code == 200
        body = r.json()
        assert body["nudged"] == 2
        assert set(body["nudged_ids"]) == {s1["id"], s2["id"]}
        assert body["failed"] == []

        # Verify activity entries
        for sid in (s1["id"], s2["id"]):
            g = _get_sub(tokens, "lead", sid).json()
            nudge_acts = [a for a in g.get("activity", []) if a.get("action") == "nudged"]
            assert len(nudge_acts) >= 1, f"No nudge activity for {sid}"
            assert nudge_acts[-1]["note"] == "ping"

    def test_skips_terminal_statuses(self, tokens):
        # approved
        sub_app = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"])
        _accept(tokens, "reviewer", sub_app["id"])
        ap = _approve(tokens, "reviewer", sub_app["id"])
        assert ap.status_code == 200 and ap.json()["status"] == "approved"

        # live
        sub_live = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"])
        _accept(tokens, "reviewer", sub_live["id"])
        _approve(tokens, "reviewer", sub_live["id"])
        ml = _mark_live(tokens, "submitter", sub_live["id"])
        assert ml.status_code == 200 and ml.json()["status"] == "live"

        # revision_requested
        sub_rev = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"])
        _accept(tokens, "reviewer", sub_rev["id"])
        rv = requests.post(f"{BASE_URL}/submissions/{sub_rev['id']}/request-revision",
                           json={"note": "fix"}, headers=_h(tokens, "reviewer"), timeout=20)
        assert rv.status_code == 200

        r = _bulk_nudge(tokens, "lead", [sub_app["id"], sub_live["id"], sub_rev["id"]])
        assert r.status_code == 200
        body = r.json()
        assert body["nudged"] == 0
        reasons = {f["id"]: f["reason"] for f in body["failed"]}
        assert reasons.get(sub_app["id"]) == "status_approved"
        assert reasons.get(sub_live["id"]) == "status_live"
        assert reasons.get(sub_rev["id"]) == "status_revision_requested"

    def test_skips_unknown_ids(self, tokens):
        bogus = [str(uuid.uuid4()) for _ in range(3)]
        r = _bulk_nudge(tokens, "lead", bogus)
        assert r.status_code == 200
        body = r.json()
        assert body["nudged"] == 0
        for f in body["failed"]:
            assert f["reason"] == "not_found"
        assert {f["id"] for f in body["failed"]} == set(bogus)


# ---------- 3) Scale + notifications ----------
class TestBulkNudgeScale:
    def test_50_ids_consistency_and_notifications(self, tokens):
        reviewer_id = tokens["reviewer"]["user"]["id"]
        # baseline reviewer nudge_manual notification count
        before = _notifications(tokens, "reviewer").json()
        before_count = sum(1 for n in before["items"] if n.get("kind") == "nudge_manual")

        N = 50
        ids = []
        for _ in range(N):
            s = _make_sub(tokens, "submitter", assignee_id=reviewer_id)
            ids.append(s["id"])

        # Sprinkle in a couple of terminal & unknown ones to test counts but still pass exactly N=50 total
        # Replace last 5 with: 2 unknown + 3 approved
        approved_ids = []
        for _ in range(3):
            s = _make_sub(tokens, "submitter", assignee_id=reviewer_id)
            _accept(tokens, "reviewer", s["id"])
            _approve(tokens, "reviewer", s["id"])
            approved_ids.append(s["id"])
        unknown_ids = [str(uuid.uuid4()) for _ in range(2)]

        # Build a 50-id payload: 45 pending + 3 approved + 2 unknown = 50
        payload_ids = ids[:45] + approved_ids + unknown_ids
        assert len(payload_ids) == 50

        r = _bulk_nudge(tokens, "lead", payload_ids, note="bulk-50")
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["nudged"] + len(body["failed"]) == 50, body
        assert body["nudged"] == 45
        assert len(body["failed"]) == 5
        reasons = [f["reason"] for f in body["failed"]]
        assert reasons.count("not_found") == 2
        assert reasons.count("status_approved") == 3

        # Verify exactly 45 new notifications were created for the reviewer
        after = _notifications(tokens, "reviewer").json()
        after_count = sum(1 for n in after["items"] if n.get("kind") == "nudge_manual")
        # Note: list endpoint caps at 100 items. We only check delta ≥ expected,
        # but more robustly: check the most recent 45 nudge_manual notifications reference our ids.
        recent_nudges = [n for n in after["items"] if n.get("kind") == "nudge_manual"]
        nudged_set = set(body["nudged_ids"])
        matching = [n for n in recent_nudges if n.get("submission_id") in nudged_set]
        assert len(matching) >= 45, f"Expected ≥45 notifications referencing nudged ids, got {len(matching)} (before={before_count}, after={after_count})"


# ---------- 4) NotificationKind soft-warn behaviour ----------
class TestNotificationKindLiteral:
    def test_nudge_manual_does_not_warn(self, tokens):
        """After triggering a manual nudge, backend logs should not contain a warning about 'nudge_manual'."""
        sub = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"])
        r = _bulk_nudge(tokens, "lead", [sub["id"]], note="literal-check")
        assert r.status_code == 200

        # Give logs a moment
        time.sleep(0.5)
        try:
            out = subprocess.check_output(
                ["tail", "-n", "300", "/var/log/supervisor/backend.err.log"],
                stderr=subprocess.STDOUT, timeout=10,
            ).decode("utf-8", errors="ignore")
        except Exception:
            out = ""
        # Soft check: no warning about nudge_manual being unknown
        assert "Unknown notification kind 'nudge_manual'" not in out, out[-500:]

    def test_known_kinds_are_in_literal(self):
        """Sanity-check: every kind we use in the codebase is present in NotificationKind."""
        from typing import get_args
        # Import from backend path
        import sys
        sys.path.insert(0, "/app/backend")
        from models import NotificationKind  # noqa: E402
        kinds = set(get_args(NotificationKind))
        expected = {
            "assigned", "accepted", "approved", "forwarded", "forwarded_to_ceo",
            "live", "revision", "escalation", "auto_escalation",
            "auto_nudge_accept", "auto_nudge_review", "nudge_manual",
            "timeline_proposed", "timeline_agreed",
        }
        missing = expected - kinds
        assert not missing, f"Missing from NotificationKind Literal: {missing}"


# ---------- 5) Regression: per-row /nudge still works ----------
class TestPerRowNudgeRegression:
    def test_single_nudge_creates_one_notification(self, tokens):
        reviewer_id = tokens["reviewer"]["user"]["id"]
        sub = _make_sub(tokens, "submitter", assignee_id=reviewer_id)

        before = _notifications(tokens, "reviewer").json()
        before_for_sub = sum(1 for n in before["items"]
                             if n.get("submission_id") == sub["id"] and n.get("kind") == "nudge_manual")

        r = requests.post(f"{BASE_URL}/submissions/{sub['id']}/nudge",
                          json={"note": "per-row"}, headers=_h(tokens, "lead"), timeout=20)
        assert r.status_code == 200, r.text
        # Returned submission has the new activity entry
        item = r.json()
        last_nudge = [a for a in item.get("activity", []) if a.get("action") == "nudged"][-1]
        assert last_nudge["note"] == "per-row"

        after = _notifications(tokens, "reviewer").json()
        after_for_sub = sum(1 for n in after["items"]
                            if n.get("submission_id") == sub["id"] and n.get("kind") == "nudge_manual")
        assert after_for_sub - before_for_sub == 1, (
            f"Expected exactly 1 new nudge_manual notification for {sub['id']}, "
            f"got delta={after_for_sub - before_for_sub}"
        )
