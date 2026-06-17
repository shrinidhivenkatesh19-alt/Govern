"""Iteration 3 backend tests — assigned_user_id, request_type, team/designation."""
import os
import uuid
import time
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
    r = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=20)
    return r


def _ensure_user(key):
    info = ACCOUNTS[key]
    r = _login(info["email"], info["password"])
    if r.status_code == 200:
        return r.json()["token"], r.json()["user"]
    # Try to register
    payload = {"email": info["email"], "password": info["password"], "name": info["name"], "role": info["role"], "team": info["team"], "designation": info["designation"]}
    rr = requests.post(f"{BASE_URL}/auth/register", json=payload, timeout=20)
    if rr.status_code == 200:
        return rr.json()["token"], rr.json()["user"]
    # Already exists? login
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
        "title": title or f"TEST_IT3_{uuid.uuid4().hex[:8]}",
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


# ---------------- Tests ----------------

# 1) Register/Login returns team + designation
class TestUserTeamDesignation:
    def test_login_returns_team_designation(self, tokens):
        r = _login(ACCOUNTS["submitter"]["email"], ACCOUNTS["submitter"]["password"])
        assert r.status_code == 200
        u = r.json()["user"]
        assert "team" in u and "designation" in u, f"missing fields: {u}"
        assert u["team"] == "Marketing"
        assert u["designation"] == "Marketing Associate"

    def test_me_returns_team_designation(self, tokens):
        r = requests.get(f"{BASE_URL}/auth/me", headers=_h(tokens, "vp"), timeout=20)
        assert r.status_code == 200
        u = r.json()
        assert u.get("team") == "Marketing"
        assert u.get("designation") == "VP of Marketing"

    def test_users_list_has_team_designation(self, tokens):
        r = requests.get(f"{BASE_URL}/users", headers=_h(tokens, "submitter"), timeout=20)
        assert r.status_code == 200
        users = r.json()
        by_email = {u["email"]: u for u in users}
        assert by_email["ceo@govern.app"]["team"] == "Executive"
        assert by_email["ceo@govern.app"]["designation"] == "Chief Executive Officer"
        assert by_email["reviewer@govern.app"]["team"] == "Product"
        assert by_email["lead@govern.app"]["designation"] == "Head of Marketing"

    def test_register_accepts_team_designation(self):
        email = f"test_it3_{uuid.uuid4().hex[:6]}@govern.app"
        payload = {"email": email, "password": "Pass1234!", "name": "Tester", "role": "submitter", "team": "QA", "designation": "QA Engineer"}
        r = requests.post(f"{BASE_URL}/auth/register", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        u = r.json()["user"]
        assert u["team"] == "QA"
        assert u["designation"] == "QA Engineer"

    def test_register_defaults_team_designation_empty(self):
        email = f"test_it3_{uuid.uuid4().hex[:6]}@govern.app"
        payload = {"email": email, "password": "Pass1234!", "name": "Tester2", "role": "submitter"}
        r = requests.post(f"{BASE_URL}/auth/register", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        u = r.json()["user"]
        assert u.get("team", "") == ""
        assert u.get("designation", "") == ""


# 2) /score uses request_type, not content_type
class TestScoreRequestType:
    def test_score_with_request_type_succeeds(self, tokens):
        body = {"title": "TEST_IT3_score", "request_type": "internal_newsletter", "brief": "Monthly newsletter for staff", "content": "Hello team, this month..."}
        r = requests.post(f"{BASE_URL}/score", json=body, headers=_h(tokens, "submitter"), timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "overall_score" in data
        assert "recommended_tier" in data

    def test_score_with_old_content_type_fails(self, tokens):
        body = {"title": "TEST_IT3_score_old", "content_type": "blog_article", "brief": "x", "content": "y"}
        r = requests.post(f"{BASE_URL}/score", json=body, headers=_h(tokens, "submitter"), timeout=30)
        assert r.status_code == 422, f"Expected 422 for missing request_type, got {r.status_code}: {r.text}"


# 3) /submissions requires assigned_user_id + request_type
class TestSubmissionAssignment:
    def test_create_assigns_to_specific_user(self, tokens):
        assignee = tokens["reviewer"]["user"]["id"]
        r = _make_sub(tokens, "submitter", assignee_id=assignee, tier="product_only", request_type="case_study")
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["assigned_user_id"] == assignee
        assert s["assigned_user_name"] == "Reza Reviewer"
        assert s["assigned_user_email"] == "reviewer@govern.app"
        assert s["assigned_user_designation"] == "Senior Product Manager"
        assert s["assigned_user_team"] == "Product"
        assert s["reviewer_role"] == "reviewer"
        assert s["request_type"] == "case_study"
        assert s["status"] == "pending_acceptance"

    def test_create_missing_assigned_user_fails(self, tokens):
        body = {
            "title": "TEST_IT3_noassign", "request_type": "x", "brief": "b", "content": "c",
            "deadline": _future(10), "score_result": _score_result(),
            "chosen_tier": "product_only", "attachments": [], "timeline": _timeline(),
        }
        r = requests.post(f"{BASE_URL}/submissions", json=body, headers=_h(tokens, "submitter"), timeout=20)
        assert r.status_code == 422

    def test_create_invalid_assigned_user_fails(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=str(uuid.uuid4()), tier="product_only")
        assert r.status_code == 400
        assert "not found" in r.text.lower()

    def test_auto_approve_works_without_real_assignee(self, tokens):
        # auto_approve bypasses assignee lookup
        r = _make_sub(tokens, "submitter", assignee_id=str(uuid.uuid4()), tier="auto_approve")
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["status"] == "approved"

    def test_assignment_notification_to_specific_user(self, tokens):
        assignee = tokens["lead"]["user"]["id"]
        r = _make_sub(tokens, "submitter", assignee_id=assignee, tier="ceo_required", request_type="press_release")
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        # lead receives notification
        nr = requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, "lead"), timeout=20)
        assert nr.status_code == 200
        items = [n for n in nr.json()["items"] if n["submission_id"] == sid]
        assert len(items) >= 1
        # vp (same role family but not assigned) should NOT have this
        nv = requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, "vp"), timeout=20)
        vp_for_sid = [n for n in nv.json()["items"] if n["submission_id"] == sid]
        assert len(vp_for_sid) == 0


# 4) Action endpoint gating by assigned_user_id
class TestActionGating:
    @pytest.fixture
    def sub_to_lead(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["lead"]["user"]["id"], tier="ceo_required", request_type="partnership_announcement")
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_accept_blocks_other_users_even_same_role(self, tokens, sub_to_lead):
        # Register an alternate marketing_lead user, try to accept → 403
        alt_email = f"alt_lead_{uuid.uuid4().hex[:6]}@govern.app"
        reg = requests.post(f"{BASE_URL}/auth/register", json={"email": alt_email, "password": "Pass1234!", "name": "Alt Lead", "role": "marketing_lead", "team": "Marketing", "designation": "Alt Lead"}, timeout=20)
        assert reg.status_code == 200, reg.text
        alt_token = reg.json()["token"]
        r = requests.post(f"{BASE_URL}/submissions/{sub_to_lead}/accept", json={"note": "try"}, headers={"Authorization": f"Bearer {alt_token}"}, timeout=20)
        assert r.status_code == 403, r.text

    def test_accept_by_assigned_user_works(self, tokens, sub_to_lead):
        r = requests.post(f"{BASE_URL}/submissions/{sub_to_lead}/accept", json={"note": "ok"}, headers=_h(tokens, "lead"), timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "in_progress"

    def test_approve_blocks_other_users(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        requests.post(f"{BASE_URL}/submissions/{sid}/accept", json={}, headers=_h(tokens, "reviewer"), timeout=20)
        # Other reviewer cannot approve — vp tries
        rr = requests.post(f"{BASE_URL}/submissions/{sid}/approve", json={"note": "x"}, headers=_h(tokens, "vp"), timeout=20)
        assert rr.status_code == 403

    def test_request_revision_blocks_other_users(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        requests.post(f"{BASE_URL}/submissions/{sid}/accept", json={}, headers=_h(tokens, "reviewer"), timeout=20)
        rr = requests.post(f"{BASE_URL}/submissions/{sid}/request-revision", json={"note": "n"}, headers=_h(tokens, "lead"), timeout=20)
        assert rr.status_code == 403


# 5) Escalate gating + EscalateIn body
class TestEscalate:
    def test_escalate_auto_picks_next_role(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        requests.post(f"{BASE_URL}/submissions/{sid}/accept", json={}, headers=_h(tokens, "reviewer"), timeout=20)
        er = requests.post(f"{BASE_URL}/submissions/{sid}/escalate", json={"note": "esc"}, headers=_h(tokens, "reviewer"), timeout=20)
        assert er.status_code == 200, er.text
        s = er.json()
        assert s["reviewer_role"] == "marketing_lead"
        assert s["assigned_user_id"] == tokens["lead"]["user"]["id"]
        assert s["status"] == "escalated"

    def test_escalate_to_specific_user(self, tokens):
        # Create alt VP, escalate from lead to that specific VP
        alt_email = f"alt_vp_{uuid.uuid4().hex[:6]}@govern.app"
        reg = requests.post(f"{BASE_URL}/auth/register", json={"email": alt_email, "password": "Pass1234!", "name": "Alt VP", "role": "vp", "team": "Marketing", "designation": "Alt VP"}, timeout=20)
        alt_vp_id = reg.json()["user"]["id"]

        r = _make_sub(tokens, "submitter", assignee_id=tokens["lead"]["user"]["id"], tier="ceo_required")
        sid = r.json()["id"]
        requests.post(f"{BASE_URL}/submissions/{sid}/accept", json={}, headers=_h(tokens, "lead"), timeout=20)
        er = requests.post(f"{BASE_URL}/submissions/{sid}/escalate", json={"note": "to alt vp", "assigned_user_id": alt_vp_id}, headers=_h(tokens, "lead"), timeout=20)
        assert er.status_code == 200, er.text
        assert er.json()["assigned_user_id"] == alt_vp_id

    def test_escalate_to_wrong_role_user_fails(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        requests.post(f"{BASE_URL}/submissions/{sid}/accept", json={}, headers=_h(tokens, "reviewer"), timeout=20)
        # Try to escalate to vp directly (not marketing_lead)
        er = requests.post(f"{BASE_URL}/submissions/{sid}/escalate", json={"assigned_user_id": tokens["vp"]["user"]["id"]}, headers=_h(tokens, "reviewer"), timeout=20)
        assert er.status_code == 400

    def test_only_assigned_user_can_escalate(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        requests.post(f"{BASE_URL}/submissions/{sid}/accept", json={}, headers=_h(tokens, "reviewer"), timeout=20)
        er = requests.post(f"{BASE_URL}/submissions/{sid}/escalate", json={"note": "x"}, headers=_h(tokens, "lead"), timeout=20)
        assert er.status_code == 403


# 6) Forward to CEO
class TestForwardToCEO:
    def test_forward_to_ceo_specific_user(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["vp"]["user"]["id"], tier="ceo_required")
        sid = r.json()["id"]
        requests.post(f"{BASE_URL}/submissions/{sid}/accept", json={}, headers=_h(tokens, "vp"), timeout=20)
        fr = requests.post(f"{BASE_URL}/submissions/{sid}/forward-to-ceo", json={"note": "fwd", "assigned_user_id": tokens["ceo"]["user"]["id"]}, headers=_h(tokens, "vp"), timeout=20)
        assert fr.status_code == 200, fr.text
        s = fr.json()
        assert s["reviewer_role"] == "ceo"
        assert s["assigned_user_id"] == tokens["ceo"]["user"]["id"]
        # submitter notified
        nr = requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, "submitter"), timeout=20)
        sub_notes = [n for n in nr.json()["items"] if n["submission_id"] == sid and n["kind"] == "forwarded_to_ceo"]
        assert len(sub_notes) >= 1

    def test_forward_to_ceo_blocks_non_assigned_vp(self, tokens):
        # Register alt vp; create sub assigned to main vp; alt vp tries to forward
        alt_email = f"vp2_{uuid.uuid4().hex[:6]}@govern.app"
        reg = requests.post(f"{BASE_URL}/auth/register", json={"email": alt_email, "password": "Pass1234!", "name": "VP2", "role": "vp", "team": "Sales", "designation": "VP Sales"}, timeout=20)
        alt_token = reg.json()["token"]
        r = _make_sub(tokens, "submitter", assignee_id=tokens["vp"]["user"]["id"], tier="ceo_required")
        sid = r.json()["id"]
        requests.post(f"{BASE_URL}/submissions/{sid}/accept", json={}, headers=_h(tokens, "vp"), timeout=20)
        fr = requests.post(f"{BASE_URL}/submissions/{sid}/forward-to-ceo", json={}, headers={"Authorization": f"Bearer {alt_token}"}, timeout=20)
        # NOTE: forward_to_ceo only checks role==vp, not assigned. This may pass when it shouldn't per spec.
        # The spec says VP-only AND must be the assigned user. Report whichever it does.
        assert fr.status_code in (200, 403)
        if fr.status_code == 200:
            pytest.fail("forward-to-ceo did not enforce assigned_user_id gating (spec violation)")


# 7) Nudge specific user
class TestNudge:
    def test_nudge_notifies_only_assigned_user(self, tokens):
        assignee = tokens["lead"]["user"]["id"]
        r = _make_sub(tokens, "submitter", assignee_id=assignee, tier="ceo_required")
        sid = r.json()["id"]
        before_lead = len(requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, "lead"), timeout=20).json()["items"])
        before_vp = len(requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, "vp"), timeout=20).json()["items"])
        nr = requests.post(f"{BASE_URL}/submissions/{sid}/nudge", json={"note": "please"}, headers=_h(tokens, "submitter"), timeout=20)
        assert nr.status_code == 200
        after_lead = len(requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, "lead"), timeout=20).json()["items"])
        after_vp = len(requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, "vp"), timeout=20).json()["items"])
        assert after_lead > before_lead
        # vp should NOT receive nudge for this sub
        nv = requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, "vp"), timeout=20)
        vp_for_sid = [n for n in nv.json()["items"] if n["submission_id"] == sid and n["kind"] == "nudge_manual"]
        assert len(vp_for_sid) == 0


# 8) Propose timeline - specific user
class TestProposeTimeline:
    def test_propose_by_assigned_notifies_submitter(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        pr = requests.post(f"{BASE_URL}/submissions/{sid}/propose-timeline",
                           json={"accept_by": _future(3), "review_by": _future(5), "approve_by": _future(7), "note": "shifting"},
                           headers=_h(tokens, "reviewer"), timeout=20)
        assert pr.status_code == 200, pr.text
        sn = requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, "submitter"), timeout=20)
        rel = [n for n in sn.json()["items"] if n["submission_id"] == sid and n["kind"] == "timeline_proposed"]
        assert len(rel) >= 1

    def test_propose_by_non_party_forbidden(self, tokens):
        r = _make_sub(tokens, "submitter", assignee_id=tokens["reviewer"]["user"]["id"], tier="product_only")
        sid = r.json()["id"]
        pr = requests.post(f"{BASE_URL}/submissions/{sid}/propose-timeline",
                           json={"accept_by": _future(3), "review_by": _future(5), "approve_by": _future(7)},
                           headers=_h(tokens, "lead"), timeout=20)
        assert pr.status_code == 403


# 9) Scheduler creates notification only for specific assigned user
class TestScheduler:
    def test_scheduler_notifies_specific_user(self, tokens):
        # Past accept_by for SLA breach
        timeline = {"accept_by": _past(2), "review_by": _future(2), "approve_by": _future(5)}
        r = _make_sub(tokens, "submitter", assignee_id=tokens["lead"]["user"]["id"], tier="ceo_required", timeline=timeline, deadline_days=8)
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        # Run scheduler
        run = requests.post(f"{BASE_URL}/scheduler/run", headers=_h(tokens, "submitter"), timeout=60)
        assert run.status_code == 200
        # lead should have auto_nudge_accept for this sid
        nr = requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, "lead"), timeout=20)
        lead_n = [n for n in nr.json()["items"] if n["submission_id"] == sid and n["kind"] == "auto_nudge_accept"]
        assert len(lead_n) == 1
        # vp should not
        nv = requests.get(f"{BASE_URL}/notifications", headers=_h(tokens, "vp"), timeout=20)
        vp_n = [n for n in nv.json()["items"] if n["submission_id"] == sid and n["kind"] == "auto_nudge_accept"]
        assert len(vp_n) == 0
