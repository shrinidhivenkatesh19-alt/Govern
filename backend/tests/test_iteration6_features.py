"""Iteration 6 backend tests — state-machine guards on decisions, per-step SLA deadlines."""
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


def _past(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


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
        "title": title or f"TEST_IT6_{uuid.uuid4().hex[:8]}",
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


def _approve(tokens, key, sid, note=""):
    return requests.post(f"{BASE_URL}/submissions/{sid}/approve", json={"note": note}, headers=_h(tokens, key), timeout=20)


def _request_revision(tokens, key, sid, note="needs work"):
    return requests.post(f"{BASE_URL}/submissions/{sid}/request-revision", json={"note": note}, headers=_h(tokens, key), timeout=20)


def _forward(tokens, key, sid, target_id, *, note=None, timeline=None):
    body = {"assigned_user_id": target_id}
    if note is not None:
        body["note"] = note
    if timeline is not None:
        body["timeline"] = timeline
    return requests.post(f"{BASE_URL}/submissions/{sid}/approve-and-forward", json=body, headers=_h(tokens, key), timeout=20)


def _mark_live(tokens, key, sid):
    return requests.post(f"{BASE_URL}/submissions/{sid}/mark-live", json={}, headers=_h(tokens, key), timeout=20)


def _get_sub(tokens, key, sid):
    return requests.get(f"{BASE_URL}/submissions/{sid}", headers=_h(tokens, key), timeout=20)


# ---------- 1) Terminal-status guards on /approve ----------
class TestApproveTerminalGuards:
    def test_approve_from_approved_returns_400(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        a1 = _approve(tokens, "reviewer", sid, "first approve")
        assert a1.status_code == 200, a1.text
        assert a1.json()["status"] == "approved"
        # second approve should fail
        a2 = _approve(tokens, "reviewer", sid, "re-approve")
        assert a2.status_code == 400, a2.text
        assert "approved" in a2.text.lower()

    def test_approve_from_revision_requested_returns_400(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        rv = _request_revision(tokens, "reviewer", sid, "fix it")
        assert rv.status_code == 200, rv.text
        a = _approve(tokens, "reviewer", sid)
        assert a.status_code == 400, a.text
        assert "revision_requested" in a.text.lower()

    def test_approve_from_live_returns_400(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        _approve(tokens, "reviewer", sid)
        ml = _mark_live(tokens, "submitter", sid)
        assert ml.status_code == 200, ml.text
        a = _approve(tokens, "reviewer", sid)
        assert a.status_code == 400, a.text
        assert "live" in a.text.lower()


# ---------- 2) Terminal-status guards on /request-revision ----------
class TestRequestRevisionTerminalGuards:
    def test_revision_from_approved_returns_400(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        _approve(tokens, "reviewer", sid)
        rv = _request_revision(tokens, "reviewer", sid, "wait, no")
        assert rv.status_code == 400, rv.text
        assert "approved" in rv.text.lower()

    def test_revision_from_revision_requested_returns_400(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        _request_revision(tokens, "reviewer", sid, "first")
        rv2 = _request_revision(tokens, "reviewer", sid, "second")
        assert rv2.status_code == 400, rv2.text
        assert "revision_requested" in rv2.text.lower()

    def test_revision_from_live_returns_400(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        _approve(tokens, "reviewer", sid)
        _mark_live(tokens, "submitter", sid)
        rv = _request_revision(tokens, "reviewer", sid)
        assert rv.status_code == 400, rv.text
        assert "live" in rv.text.lower()


# ---------- 3) Terminal-status guards on /approve-and-forward ----------
class TestApproveAndForwardTerminalGuards:
    def test_forward_from_approved_returns_400(self, tokens):
        # reviewer approves; can't forward already-approved item
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        a = _approve(tokens, "reviewer", sid)
        assert a.status_code == 200
        f = _forward(tokens, "reviewer", sid, tokens["lead"]["user"]["id"])
        assert f.status_code == 400, f.text
        assert "approved" in f.text.lower()

    def test_forward_from_revision_requested_returns_400(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        _request_revision(tokens, "reviewer", sid, "rework")
        f = _forward(tokens, "reviewer", sid, tokens["lead"]["user"]["id"])
        assert f.status_code == 400, f.text
        assert "revision_requested" in f.text.lower()

    def test_forward_from_live_returns_400(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        _approve(tokens, "reviewer", sid)
        _mark_live(tokens, "submitter", sid)
        f = _forward(tokens, "reviewer", sid, tokens["lead"]["user"]["id"])
        assert f.status_code == 400, f.text
        assert "live" in f.text.lower()


# ---------- 4) /approve still works from valid statuses + step_timeline captured ----------
class TestApproveValidStatusesAndStepTimeline:
    def test_approve_from_pending_acceptance(self, tokens):
        # Submission starts in pending_acceptance
        tl = _timeline(2, 4, 6)
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only", timeline=tl)
        sid = r.json()["id"]
        a = _approve(tokens, "reviewer", sid, "ok")
        assert a.status_code == 200, a.text
        s = a.json()
        assert s["status"] == "approved"
        chain = s.get("approval_chain") or []
        assert len(chain) == 1
        entry = chain[0]
        assert entry["closed"] is True
        assert entry["step_timeline"] == tl

    def test_approve_from_in_progress(self, tokens):
        tl = _timeline(3, 5, 7)
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only", timeline=tl)
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)  # → in_progress
        a = _approve(tokens, "reviewer", sid, "good")
        assert a.status_code == 200, a.text
        s = a.json()
        assert s["status"] == "approved"
        chain = s.get("approval_chain") or []
        assert len(chain) == 1
        assert chain[0]["closed"] is True
        assert chain[0]["step_timeline"] == tl


# ---------- 5) /approve-and-forward: timeline replaces submission timeline; step_timeline captures prev ----------
class TestApproveForwardPerStepTimeline:
    def test_forward_with_timeline_replaces_submission_timeline(self, tokens):
        t1 = _timeline(2, 4, 6)
        t2 = _timeline(7, 9, 11)
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="ceo_required", timeline=t1)
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        f = _forward(tokens, "reviewer", sid, tokens["lead"]["user"]["id"], note="to lead", timeline=t2)
        assert f.status_code == 200, f.text
        s = f.json()
        # submission timeline now equals t2
        assert s["timeline"] == t2
        # chain entry's step_timeline captures the closed step's SLA (t1)
        chain = s["approval_chain"]
        assert len(chain) == 1
        assert chain[0]["step_timeline"] == t1
        assert chain[0]["closed"] is False
        assert chain[0]["forwarded_to_id"] == tokens["lead"]["user"]["id"]

    def test_forward_without_timeline_keeps_existing(self, tokens):
        t1 = _timeline(3, 5, 8)
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="ceo_required", timeline=t1)
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        f = _forward(tokens, "reviewer", sid, tokens["lead"]["user"]["id"], note="no new timeline")
        assert f.status_code == 200, f.text
        s = f.json()
        assert s["timeline"] == t1, f"expected timeline to remain {t1}, got {s['timeline']}"
        # step_timeline on the closed entry == t1 also
        assert s["approval_chain"][0]["step_timeline"] == t1

    def test_auto_nudges_sent_reset_on_forward(self, tokens):
        t1 = _timeline(2, 4, 6)
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="ceo_required", timeline=t1)
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        f = _forward(tokens, "reviewer", sid, tokens["lead"]["user"]["id"])
        assert f.status_code == 200
        s = f.json()
        # auto_nudges_sent should be reset to {} on the submission after forward
        # If not present in serialized body, fetch via GET
        nudges = s.get("auto_nudges_sent")
        if nudges is None:
            g = _get_sub(tokens, "lead", sid)
            assert g.status_code == 200, g.text
            nudges = g.json().get("auto_nudges_sent")
        assert nudges == {}, f"expected reset auto_nudges_sent={{}}, got {nudges!r}"


# ---------- 6) End-to-end multi-step chain with per-step SLAs ----------
class TestEndToEndChainPerStepSLAs:
    def test_three_step_chain_with_per_step_timelines(self, tokens):
        t1 = _timeline(2, 4, 6)
        t2 = _timeline(5, 7, 9)
        t3 = _timeline(8, 10, 12)
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"],
                      tier="ceo_required", request_type="partnership_announcement", timeline=t1)
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)

        # A(reviewer, t1) → forward with t2 → B(lead)
        r1 = _forward(tokens, "reviewer", sid, tokens["lead"]["user"]["id"], note="to lead", timeline=t2)
        assert r1.status_code == 200, r1.text
        s1 = r1.json()
        assert s1["timeline"] == t2
        assert s1["approval_chain"][0]["step_timeline"] == t1
        assert s1["approval_chain"][0]["closed"] is False

        # B(lead, t2) → forward with t3 → C(vp)
        _accept(tokens, "lead", sid)
        r2 = _forward(tokens, "lead", sid, tokens["vp"]["user"]["id"], note="to vp", timeline=t3)
        assert r2.status_code == 200, r2.text
        s2 = r2.json()
        assert s2["timeline"] == t3
        assert len(s2["approval_chain"]) == 2
        assert s2["approval_chain"][0]["step_timeline"] == t1
        assert s2["approval_chain"][1]["step_timeline"] == t2
        assert all(e["closed"] is False for e in s2["approval_chain"])

        # C(vp, t3) → approve (closes)
        _accept(tokens, "vp", sid)
        r3 = _approve(tokens, "vp", sid, "final")
        assert r3.status_code == 200, r3.text
        s3 = r3.json()
        assert s3["status"] == "approved"
        chain = s3["approval_chain"]
        assert len(chain) == 3, f"expected 3 entries, got {len(chain)}"
        # Per-step SLAs are recorded correctly
        assert chain[0]["step_timeline"] == t1, f"entry 0 step_timeline mismatch: {chain[0].get('step_timeline')}"
        assert chain[1]["step_timeline"] == t2, f"entry 1 step_timeline mismatch: {chain[1].get('step_timeline')}"
        assert chain[2]["step_timeline"] == t3, f"entry 2 step_timeline mismatch: {chain[2].get('step_timeline')}"
        # Only last is closed
        assert chain[0]["closed"] is False
        assert chain[1]["closed"] is False
        assert chain[2]["closed"] is True
        # Roles in order
        assert chain[0]["approver_role"] == "reviewer"
        assert chain[1]["approver_role"] == "marketing_lead"
        assert chain[2]["approver_role"] == "vp"


# ---------- 7) Scheduler uses CURRENT timeline after forward ----------
class TestSchedulerUsesCurrentTimeline:
    def test_scheduler_fires_auto_nudge_accept_using_new_timeline(self, tokens):
        # Create with a generous t1, forward with a t2 that has a PAST accept_by
        t1 = _timeline(7, 9, 12)  # all future
        t2 = {"accept_by": _past(1), "review_by": _future(5), "approve_by": _future(8)}
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="ceo_required", timeline=t1)
        sid = r.json()["id"]
        _accept(tokens, "reviewer", sid)
        f = _forward(tokens, "reviewer", sid, tokens["lead"]["user"]["id"], note="past accept_by", timeline=t2)
        assert f.status_code == 200, f.text
        s = f.json()
        assert s["status"] == "pending_acceptance"
        assert s["timeline"] == t2
        # Lead does NOT accept — leave in pending_acceptance with past accept_by
        # Trigger scheduler
        sch = requests.post(f"{BASE_URL}/scheduler/run", headers=_h(tokens, "vp"), timeout=30)
        assert sch.status_code == 200, sch.text
        # Activity should now contain an auto_nudge_accept entry
        g = _get_sub(tokens, "lead", sid)
        assert g.status_code == 200, g.text
        activity = g.json().get("activity", [])
        nudge_entries = [a for a in activity if a.get("action") == "auto_nudge_accept"]
        assert len(nudge_entries) >= 1, f"expected auto_nudge_accept entry; got activity: {activity}"
