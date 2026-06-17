"""Iteration 5 backend tests — governance gating, dashboard/stats, approve-and-forward chain."""
import os
import uuid
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


def _timeline(accept_in=2, review_in=4, approve_in=6):
    return {"accept_by": _future(accept_in), "review_by": _future(review_in), "approve_by": _future(approve_in)}


def _make_sub(tokens, submitter_key, *, assignee_id, tier="product_only", request_type="custom_email", title=None, timeline=None, deadline_days=10):
    body = {
        "title": title or f"TEST_IT5_{uuid.uuid4().hex[:8]}",
        "request_type": request_type,
        "brief": "Brief content", "content": "Body content",
        "deadline": _future(deadline_days),
        "score_result": _score_result(tier),
        "chosen_tier": tier,
        "attachments": [],
        "timeline": timeline or _timeline(),
        "assigned_user_id": assignee_id,
    }
    return requests.post(f"{BASE_URL}/submissions", json=body, headers=_h(tokens, submitter_key), timeout=30)


def _accept(tokens, key, sid):
    return requests.post(f"{BASE_URL}/submissions/{sid}/accept", json={}, headers=_h(tokens, key), timeout=20)


# 1) Governance overview restricted to vp + ceo
class TestAnalyticsOverviewGating:
    def test_submitter_gets_403(self, tokens):
        r = requests.get(f"{BASE_URL}/analytics/overview", headers=_h(tokens, "submitter"), timeout=30)
        assert r.status_code == 403, r.text

    def test_reviewer_gets_403(self, tokens):
        r = requests.get(f"{BASE_URL}/analytics/overview", headers=_h(tokens, "reviewer"), timeout=30)
        assert r.status_code == 403, r.text

    def test_marketing_lead_gets_403(self, tokens):
        r = requests.get(f"{BASE_URL}/analytics/overview", headers=_h(tokens, "lead"), timeout=30)
        assert r.status_code == 403, r.text

    def test_vp_gets_200(self, tokens):
        r = requests.get(f"{BASE_URL}/analytics/overview", headers=_h(tokens, "vp"), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "total" in data
        assert "by_status" in data
        assert "avg_approval_hours" in data

    def test_ceo_gets_200(self, tokens):
        r = requests.get(f"{BASE_URL}/analytics/overview", headers=_h(tokens, "ceo"), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "total" in data
        assert "by_tier" in data
        assert "idle_breakdown" in data


# 2) Lightweight dashboard stats available to all roles
class TestDashboardStats:
    REQUIRED_FIELDS = {"total", "by_status", "avg_approval_hours", "completed_count"}

    @pytest.mark.parametrize("role", ["submitter", "reviewer", "lead", "vp", "ceo"])
    def test_all_roles_can_read(self, tokens, role):
        r = requests.get(f"{BASE_URL}/dashboard/stats", headers=_h(tokens, role), timeout=30)
        assert r.status_code == 200, f"{role}: {r.status_code} {r.text}"
        data = r.json()
        missing = self.REQUIRED_FIELDS - set(data.keys())
        assert not missing, f"{role}: missing fields {missing}"
        assert isinstance(data["total"], int)
        assert isinstance(data["by_status"], dict)
        assert isinstance(data["completed_count"], int)


# 3) Approve-and-forward endpoint — granular guards
class TestApproveAndForwardGuards:
    def test_unauthenticated_rejected(self, tokens):
        r = requests.post(f"{BASE_URL}/submissions/anything/approve-and-forward", json={"assigned_user_id": "x"}, timeout=20)
        assert r.status_code in (401, 403), r.text

    def test_submitter_role_rejected(self, tokens):
        # submitter doesn't have approve rights — even with assigned_user_id
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        rr = requests.post(f"{BASE_URL}/submissions/{sid}/approve-and-forward",
                           json={"assigned_user_id": tokens["lead"]["user"]["id"]},
                           headers=_h(tokens, "submitter"), timeout=20)
        assert rr.status_code == 403, rr.text

    def test_ceo_cannot_forward(self, tokens):
        # Assigned to CEO; CEO tries to forward → 400 (terminal)
        r = _make_sub(tokens, "submitter", assignee_id=tokens["ceo"]["user"]["id"], tier="ceo_required")
        sid = r.json()["id"]
        _accept(tokens, "ceo", sid)
        rr = requests.post(f"{BASE_URL}/submissions/{sid}/approve-and-forward",
                           json={"assigned_user_id": tokens["vp"]["user"]["id"]},
                           headers=_h(tokens, "ceo"), timeout=20)
        assert rr.status_code == 400, rr.text
        assert "terminal" in rr.text.lower() or "approve" in rr.text.lower()

    def test_missing_assigned_user_id_rejected(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        rr = requests.post(f"{BASE_URL}/submissions/{sid}/approve-and-forward",
                           json={"note": "no target"},
                           headers=_h(tokens, "reviewer"), timeout=20)
        # Could be 400 (server) or 422 (pydantic) depending on EscalateIn model
        assert rr.status_code in (400, 422), rr.text

    def test_non_assigned_user_rejected(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        # marketing_lead is not the assigned user → 403
        rr = requests.post(f"{BASE_URL}/submissions/{sid}/approve-and-forward",
                           json={"assigned_user_id": tokens["vp"]["user"]["id"]},
                           headers=_h(tokens, "lead"), timeout=20)
        assert rr.status_code == 403, rr.text

    def test_submitter_target_rejected(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        rr = requests.post(f"{BASE_URL}/submissions/{sid}/approve-and-forward",
                           json={"assigned_user_id": tokens["submitter"]["user"]["id"]},
                           headers=_h(tokens, "reviewer"), timeout=20)
        assert rr.status_code == 400, rr.text
        assert "submitter" in rr.text.lower()

    def test_self_target_rejected(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        rr = requests.post(f"{BASE_URL}/submissions/{sid}/approve-and-forward",
                           json={"assigned_user_id": tokens["reviewer"]["user"]["id"]},
                           headers=_h(tokens, "reviewer"), timeout=20)
        assert rr.status_code == 400, rr.text
        assert "yourself" in rr.text.lower() or "self" in rr.text.lower()

    def test_target_user_not_found_rejected(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        rr = requests.post(f"{BASE_URL}/submissions/{sid}/approve-and-forward",
                           json={"assigned_user_id": str(uuid.uuid4())},
                           headers=_h(tokens, "reviewer"), timeout=20)
        assert rr.status_code == 400, rr.text
        assert "not found" in rr.text.lower()


# 4) Approve-and-forward — success behaviour
class TestApproveAndForwardSuccess:
    def test_forwards_and_updates_state(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="ceo_required", request_type="press_release")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        rr = requests.post(f"{BASE_URL}/submissions/{sid}/approve-and-forward",
                           json={"assigned_user_id": tokens["lead"]["user"]["id"], "note": "looks good"},
                           headers=_h(tokens, "reviewer"), timeout=30)
        assert rr.status_code == 200, rr.text
        s = rr.json()
        assert s["status"] == "pending_acceptance"
        assert s["reviewer_role"] == "marketing_lead"
        assert s["assigned_user_id"] == tokens["lead"]["user"]["id"]
        assert s["assigned_user_name"] == "Maya Lead"
        assert s["assigned_user_email"] == "lead@govern.app"
        assert s["timeline_agreed"] is False

        chain = s.get("approval_chain") or []
        assert len(chain) == 1
        entry = chain[0]
        assert entry["approver_id"] == tokens["reviewer"]["user"]["id"]
        assert entry["approver_name"] == "Reza Reviewer"
        assert entry["approver_role"] == "reviewer"
        assert entry["approver_designation"] == "Senior Product Manager"
        assert entry["forwarded_to_id"] == tokens["lead"]["user"]["id"]
        assert entry["forwarded_to_name"] == "Maya Lead"
        assert entry["closed"] is False
        assert entry["note"] == "looks good"
        assert "ts" in entry

        # stage_durations should have a roll-up for the prior status
        assert isinstance(s.get("stage_durations"), dict)

    def test_target_user_receives_assigned_notification(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="ceo_required")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        rr = requests.post(f"{BASE_URL}/submissions/{sid}/approve-and-forward",
                           json={"assigned_user_id": tokens["lead"]["user"]["id"]},
                           headers=_h(tokens, "reviewer"), timeout=20)
        assert rr.status_code == 200

        nr = requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, "lead"), timeout=20)
        lead_for_sid = [n for n in nr.json()["items"] if n["submission_id"] == sid and n["kind"] == "assigned"]
        assert len(lead_for_sid) >= 1

    def test_submitter_receives_approved_notification(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="ceo_required")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        rr = requests.post(f"{BASE_URL}/submissions/{sid}/approve-and-forward",
                           json={"assigned_user_id": tokens["lead"]["user"]["id"]},
                           headers=_h(tokens, "reviewer"), timeout=20)
        assert rr.status_code == 200

        nr = requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, "submitter"), timeout=20)
        sub_for_sid = [n for n in nr.json()["items"] if n["submission_id"] == sid and n["kind"] == "approved"]
        assert len(sub_for_sid) >= 1


# 5) /approve appends to approval_chain with closed=True
class TestApproveClosesChain:
    def test_approve_appends_closed_entry(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        ar = requests.post(f"{BASE_URL}/submissions/{sid}/approve", json={"note": "all done"},
                           headers=_h(tokens, "reviewer"), timeout=20)
        assert ar.status_code == 200, ar.text
        s = ar.json()
        assert s["status"] == "approved"
        chain = s.get("approval_chain") or []
        assert len(chain) == 1
        entry = chain[0]
        assert entry["approver_id"] == tokens["reviewer"]["user"]["id"]
        assert entry["approver_role"] == "reviewer"
        assert entry["closed"] is True
        assert entry["note"] == "all done"


# 6) End-to-end chain: A → forward → B → forward → C → approve(close)
class TestEndToEndChain:
    def test_three_step_chain(self, tokens):
        # A = reviewer, B = lead, C = vp; closed by vp via /approve
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"],
                      tier="ceo_required", request_type="partnership_announcement")
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)

        # A → B
        r1 = requests.post(f"{BASE_URL}/submissions/{sid}/approve-and-forward",
                           json={"assigned_user_id": tokens["lead"]["user"]["id"], "note": "to lead"},
                           headers=_h(tokens, "reviewer"), timeout=20)
        assert r1.status_code == 200, r1.text
        s1 = r1.json()
        assert len(s1["approval_chain"]) == 1
        assert s1["approval_chain"][0]["closed"] is False
        assert s1["assigned_user_id"] == tokens["lead"]["user"]["id"]

        # Lead accepts then forwards to VP
        _accept(tokens, "lead", sid)
        r2 = requests.post(f"{BASE_URL}/submissions/{sid}/approve-and-forward",
                           json={"assigned_user_id": tokens["vp"]["user"]["id"], "note": "to vp"},
                           headers=_h(tokens, "lead"), timeout=20)
        assert r2.status_code == 200, r2.text
        s2 = r2.json()
        assert len(s2["approval_chain"]) == 2
        assert all(e["closed"] is False for e in s2["approval_chain"])
        assert s2["approval_chain"][0]["approver_role"] == "reviewer"
        assert s2["approval_chain"][1]["approver_role"] == "marketing_lead"
        assert s2["assigned_user_id"] == tokens["vp"]["user"]["id"]

        # VP accepts and approves (closes)
        _accept(tokens, "vp", sid)
        r3 = requests.post(f"{BASE_URL}/submissions/{sid}/approve",
                           json={"note": "final approve"},
                           headers=_h(tokens, "vp"), timeout=20)
        assert r3.status_code == 200, r3.text
        s3 = r3.json()
        assert s3["status"] == "approved"
        chain = s3["approval_chain"]
        assert len(chain) == 3, f"expected 3 entries, got {len(chain)}: {chain}"
        assert chain[0]["closed"] is False
        assert chain[1]["closed"] is False
        assert chain[2]["closed"] is True
        assert chain[2]["approver_role"] == "vp"
        # First two should have forwarded_to_* fields, last shouldn't
        assert "forwarded_to_id" in chain[0]
        assert "forwarded_to_id" in chain[1]
        assert chain[2].get("forwarded_to_id") in (None, "")  # not set on terminal approve
