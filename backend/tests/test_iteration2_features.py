"""Iteration 2 — Backend test suite for: VP role, timeline-driven SLAs, notifications,
propose/agree timeline, forward-to-ceo, one-level escalate, scheduler nudges/escalations."""
import os
import time
import pytest
import requests
from datetime import datetime, timezone, timedelta

def _read_frontend_env_url():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_env_url() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
API = f"{BASE_URL}/api"

CREDS = {
    "submitter": ("submitter@govern.app", "Pass1234!", "Sara Submitter", "submitter"),
    "reviewer": ("reviewer@govern.app", "Pass1234!", "Reza Reviewer", "reviewer"),
    "lead": ("lead@govern.app", "Pass1234!", "Maya Lead", "marketing_lead"),
    "vp": ("vp@govern.app", "Pass1234!", "Victoria Vee", "vp"),
    "ceo": ("ceo@govern.app", "Pass1234!", "Carl Chief", "ceo"),
}
TOKENS = {}


def _login_or_register(key):
    email, pwd, name, role = CREDS[key]
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd})
    if r.status_code == 200:
        return r.json()
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": pwd, "name": name, "role": role})
    assert r.status_code == 200, f"register {key} failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="session", autouse=True)
def auth_all():
    for k in CREDS:
        TOKENS[k] = _login_or_register(k)["token"]
    return TOKENS


def H(k):
    return {"Authorization": f"Bearer {TOKENS[k]}"}


def _future(days):
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _past(days):
    return (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()


def _score(tier="product_only"):
    return {
        "brand_alignment_score": 80, "completeness_score": 80,
        "content_classification": "routine" if tier != "ceo_required" else "innovation",
        "risk_flags": [] if tier != "ceo_required" else ["pricing"],
        "overall_score": 80, "recommended_tier": tier,
        "reasoning": "test", "questions_to_resolve": [],
    }


def _mk_sub(token_key, tier, title, deadline=None, accept_by=None, review_by=None, approve_by=None):
    body = {
        "title": title,
        "content_type": "social_post" if tier != "ceo_required" else "pricing_update",
        "brief": "test brief",
        "content": "test content",
        "deadline": deadline or _future(30),
        "score_result": _score(tier),
        "chosen_tier": tier,
        "timeline": {
            "accept_by": accept_by or _future(2),
            "review_by": review_by or _future(5),
            "approve_by": approve_by or _future(10),
        },
    }
    r = requests.post(f"{API}/submissions", headers=H(token_key), json=body)
    assert r.status_code == 200, f"create failed {r.status_code} {r.text}"
    return r.json()


# ---------- VP role auth ----------
class TestVPRole:
    def test_vp_login(self):
        r = requests.post(f"{API}/auth/login", json={"email": "vp@govern.app", "password": "Pass1234!"})
        assert r.status_code == 200
        j = r.json()
        assert j["user"]["role"] == "vp"
        assert j["user"]["email"] == "vp@govern.app"

    def test_vp_me(self):
        r = requests.get(f"{API}/auth/me", headers=H("vp"))
        assert r.status_code == 200
        assert r.json()["role"] == "vp"


# ---------- Submission creation w/ timeline + tier routing ----------
SUBS = {}


class TestSubmissionRouting:
    def test_auto_approve_skips_chain(self):
        s = _mk_sub("submitter", "auto_approve", "TEST_IT2_AutoApprove")
        assert s["status"] == "approved"
        assert s["reviewer_role"] == "system"
        assert "timeline" in s and s["timeline"]["accept_by"]
        assert any(a["action"] == "auto_approved" for a in s["activity"])
        SUBS["auto"] = s["id"]

    def test_product_only_assigns_reviewer(self):
        s = _mk_sub("submitter", "product_only", "TEST_IT2_ProductOnly")
        assert s["status"] == "pending_acceptance"
        assert s["reviewer_role"] == "reviewer"
        SUBS["product"] = s["id"]

    def test_ceo_required_assigns_vp(self):
        s = _mk_sub("submitter", "ceo_required", "TEST_IT2_CEOReq")
        assert s["status"] == "pending_acceptance"
        # New: ceo_required routes to VP, not directly to CEO
        assert s["reviewer_role"] == "vp", f"Expected vp but got {s['reviewer_role']}"
        SUBS["ceo_req"] = s["id"]

    def test_create_missing_timeline_422(self):
        body = {
            "title": "TEST_IT2_NoTimeline",
            "content_type": "social_post",
            "brief": "x", "content": "x",
            "deadline": _future(30),
            "score_result": _score("product_only"),
            "chosen_tier": "product_only",
        }
        r = requests.post(f"{API}/submissions", headers=H("submitter"), json=body)
        assert r.status_code == 422


# ---------- Notifications on creation ----------
class TestNotifications:
    def test_reviewer_notified_on_product_only(self):
        # Get reviewer notifs first
        r = requests.get(f"{API}/notifications", headers=H("reviewer"))
        assert r.status_code == 200
        j = r.json()
        assert "items" in j and "unread_count" in j
        # Should have at least one assignment notif referencing SUBS["product"]
        matches = [n for n in j["items"] if n["submission_id"] == SUBS["product"] and n["kind"] == "assigned"]
        assert len(matches) >= 1, "Reviewer should receive 'assigned' notification"

    def test_vp_notified_on_ceo_required(self):
        r = requests.get(f"{API}/notifications", headers=H("vp"))
        assert r.status_code == 200
        items = r.json()["items"]
        matches = [n for n in items if n["submission_id"] == SUBS["ceo_req"] and n["kind"] == "assigned"]
        assert len(matches) >= 1, "VP should receive 'assigned' notification for ceo_required"

    def test_notifications_unread_only_filter(self):
        r = requests.get(f"{API}/notifications?unread_only=true", headers=H("reviewer"))
        assert r.status_code == 200
        for n in r.json()["items"]:
            assert n["read"] is False

    def test_mark_single_read(self):
        # Grab one unread for reviewer
        items = requests.get(f"{API}/notifications?unread_only=true", headers=H("reviewer")).json()["items"]
        if not items:
            pytest.skip("No unread notifications to test single mark-read")
        nid = items[0]["id"]
        r = requests.post(f"{API}/notifications/{nid}/read", headers=H("reviewer"))
        assert r.status_code == 200
        # Verify now read
        all_items = requests.get(f"{API}/notifications", headers=H("reviewer")).json()["items"]
        found = next((n for n in all_items if n["id"] == nid), None)
        assert found and found["read"] is True

    def test_mark_all_read(self):
        r = requests.post(f"{API}/notifications/read-all", headers=H("lead"))
        assert r.status_code == 200
        j = requests.get(f"{API}/notifications", headers=H("lead")).json()
        assert j["unread_count"] == 0


# ---------- Accept endpoint ----------
class TestAccept:
    def test_wrong_role_cannot_accept(self):
        # Submitter cannot accept their own product_only submission
        r = requests.post(f"{API}/submissions/{SUBS['product']}/accept",
                          headers=H("submitter"), json={"note": "x"})
        assert r.status_code == 403

    def test_lead_cannot_accept_product_only(self):
        r = requests.post(f"{API}/submissions/{SUBS['product']}/accept",
                          headers=H("lead"), json={"note": "x"})
        assert r.status_code == 403

    def test_reviewer_accepts_product_only(self):
        new_tl = {
            "accept_by": _future(3),
            "review_by": _future(6),
            "approve_by": _future(12),
        }
        r = requests.post(f"{API}/submissions/{SUBS['product']}/accept",
                          headers=H("reviewer"),
                          json={"note": "Accepted", "timeline": new_tl})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "in_progress"
        assert j["timeline"]["review_by"] == new_tl["review_by"]
        assert j.get("timeline_agreed") is True
        assert any(a["action"] == "accepted" for a in j["activity"])
        # stage_durations should now contain pending_acceptance
        assert "pending_acceptance" in (j.get("stage_durations") or {})

    def test_cannot_accept_already_in_progress(self):
        r = requests.post(f"{API}/submissions/{SUBS['product']}/accept",
                          headers=H("reviewer"), json={"note": "again"})
        assert r.status_code == 400

    def test_submitter_notified_on_accept(self):
        items = requests.get(f"{API}/notifications", headers=H("submitter")).json()["items"]
        matches = [n for n in items if n["submission_id"] == SUBS["product"] and n["kind"] == "accepted"]
        assert len(matches) >= 1


# ---------- Propose / Agree timeline ----------
class TestProposeAgreeTimeline:
    def test_reviewer_proposes(self):
        body = {
            "accept_by": _future(4),
            "review_by": _future(8),
            "approve_by": _future(14),
            "note": "Need more time",
        }
        # Use the in-progress 'product' sub; reviewer proposes
        r = requests.post(f"{API}/submissions/{SUBS['product']}/propose-timeline",
                          headers=H("reviewer"), json=body)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["pending_timeline_proposal"]["approve_by"] == body["approve_by"]
        assert any(a["action"] == "timeline_proposed" for a in j["activity"])

    def test_unrelated_user_403(self):
        body = {"accept_by": _future(4), "review_by": _future(8), "approve_by": _future(14), "note": "no"}
        r = requests.post(f"{API}/submissions/{SUBS['product']}/propose-timeline",
                          headers=H("ceo"), json=body)
        assert r.status_code == 403

    def test_proposer_cannot_self_agree(self):
        r = requests.post(f"{API}/submissions/{SUBS['product']}/agree-timeline",
                          headers=H("reviewer"), json={"note": "self"})
        assert r.status_code == 403

    def test_submitter_agrees(self):
        r = requests.post(f"{API}/submissions/{SUBS['product']}/agree-timeline",
                          headers=H("submitter"), json={"note": "ok"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("timeline_agreed") is True
        assert "pending_timeline_proposal" not in j or j.get("pending_timeline_proposal") is None
        assert any(a["action"] == "timeline_agreed" for a in j["activity"])

    def test_agree_without_proposal_400(self):
        r = requests.post(f"{API}/submissions/{SUBS['product']}/agree-timeline",
                          headers=H("submitter"), json={"note": "again"})
        assert r.status_code == 400


# ---------- Forward to CEO (VP-only) ----------
class TestForwardToCEO:
    def test_non_vp_cannot_forward(self):
        r = requests.post(f"{API}/submissions/{SUBS['ceo_req']}/forward-to-ceo",
                          headers=H("reviewer"), json={"note": "no"})
        assert r.status_code == 403

    def test_ceo_cannot_forward(self):
        r = requests.post(f"{API}/submissions/{SUBS['ceo_req']}/forward-to-ceo",
                          headers=H("ceo"), json={"note": "no"})
        assert r.status_code == 403

    def test_vp_forwards_pending_to_ceo(self):
        r = requests.post(f"{API}/submissions/{SUBS['ceo_req']}/forward-to-ceo",
                          headers=H("vp"), json={"note": "Final call needed"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["reviewer_role"] == "ceo"
        assert j["status"] == "pending_acceptance"
        assert any(a["action"] == "forwarded_to_ceo" for a in j["activity"])

    def test_ceo_accepts_forwarded(self):
        r = requests.post(f"{API}/submissions/{SUBS['ceo_req']}/accept",
                          headers=H("ceo"), json={"note": "Got it"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "in_progress"


# ---------- Approve (now includes vp) + notification ----------
class TestApprove:
    def test_vp_can_approve(self):
        # Create fresh ceo_required, VP accepts then approves
        s = _mk_sub("submitter", "ceo_required", "TEST_IT2_VPApprove")
        # VP accepts
        a = requests.post(f"{API}/submissions/{s['id']}/accept",
                         headers=H("vp"), json={"note": "Accepted"})
        assert a.status_code == 200
        # VP approves
        r = requests.post(f"{API}/submissions/{s['id']}/approve",
                         headers=H("vp"), json={"note": "ok"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"
        # Submitter should be notified
        items = requests.get(f"{API}/notifications", headers=H("submitter")).json()["items"]
        assert any(n["submission_id"] == s["id"] and n["kind"] == "approved" for n in items)
        SUBS["vp_approved"] = s["id"]


# ---------- Mark-live requires approved ----------
class TestMarkLive:
    def test_mark_live_non_approved_400(self):
        # SUBS["product"] is in_progress, should fail
        r = requests.post(f"{API}/submissions/{SUBS['product']}/mark-live",
                          headers=H("reviewer"), json={"note": "ship it"})
        assert r.status_code == 400, r.text

    def test_mark_live_approved_ok(self):
        r = requests.post(f"{API}/submissions/{SUBS['vp_approved']}/mark-live",
                          headers=H("reviewer"), json={"note": "live"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "live"
        items = requests.get(f"{API}/notifications", headers=H("submitter")).json()["items"]
        assert any(n["submission_id"] == SUBS["vp_approved"] and n["kind"] == "live" for n in items)


# ---------- Escalate one level up ----------
class TestEscalateOneLevel:
    def test_submitter_cannot_escalate(self):
        s = _mk_sub("submitter", "product_only", "TEST_IT2_EscSubmitter")
        r = requests.post(f"{API}/submissions/{s['id']}/escalate",
                          headers=H("submitter"), json={"note": "x"})
        assert r.status_code == 403

    def test_reviewer_escalates_to_marketing_lead(self):
        s = _mk_sub("submitter", "product_only", "TEST_IT2_EscRev")
        r = requests.post(f"{API}/submissions/{s['id']}/escalate",
                          headers=H("reviewer"), json={"note": "up"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "escalated"
        assert j["reviewer_role"] == "marketing_lead"

    def test_lead_escalates_to_vp(self):
        s = _mk_sub("submitter", "product_only", "TEST_IT2_EscLead")
        r = requests.post(f"{API}/submissions/{s['id']}/escalate",
                          headers=H("lead"), json={"note": "up"})
        assert r.status_code == 200, r.text
        assert r.json()["reviewer_role"] == "vp"

    def test_vp_cannot_use_escalate(self):
        s = _mk_sub("submitter", "ceo_required", "TEST_IT2_EscVP")
        r = requests.post(f"{API}/submissions/{s['id']}/escalate",
                          headers=H("vp"), json={"note": "x"})
        assert r.status_code == 403

    def test_ceo_cannot_use_escalate(self):
        s = _mk_sub("submitter", "ceo_required", "TEST_IT2_EscCEO")
        r = requests.post(f"{API}/submissions/{s['id']}/escalate",
                          headers=H("ceo"), json={"note": "x"})
        assert r.status_code == 403


# ---------- Live SLA / timeline annotations ----------
class TestLiveAnnotations:
    def test_list_includes_timeline_fields(self):
        r = requests.get(f"{API}/submissions", headers=H("submitter"))
        assert r.status_code == 200
        items = r.json()
        # find one with timeline
        ones_with_tl = [it for it in items if it.get("timeline")]
        assert ones_with_tl, "Expected at least one submission with timeline"
        sample = ones_with_tl[0]
        for f in ("timeline_overdue", "any_overdue", "deadline_progress", "needs_nudge", "needs_escalation"):
            assert f in sample, f"missing field {f}"
        assert isinstance(sample["timeline_overdue"], dict)
        assert 0.0 <= sample["deadline_progress"] <= 1.0

    def test_get_single_annotates(self):
        r = requests.get(f"{API}/submissions/{SUBS['product']}", headers=H("submitter"))
        assert r.status_code == 200
        j = r.json()
        assert "timeline_overdue" in j and "deadline_progress" in j


# ---------- Scheduler ----------
class TestScheduler:
    def test_scheduler_fires_nudge_accept(self):
        # Create a submission with accept_by in the past
        s = _mk_sub(
            "submitter", "product_only", "TEST_IT2_SchedAccept",
            deadline=_future(20), accept_by=_past(2), review_by=_future(5), approve_by=_future(10),
        )
        assert s["status"] == "pending_acceptance"
        r = requests.post(f"{API}/scheduler/run", headers=H("ceo"))
        assert r.status_code == 200
        # Fetch and inspect activity
        after = requests.get(f"{API}/submissions/{s['id']}", headers=H("submitter")).json()
        nudges = [a for a in after["activity"] if a["action"] == "auto_nudge_accept"]
        assert len(nudges) >= 1, f"Expected auto_nudge_accept activity, got actions: {[a['action'] for a in after['activity']]}"
        # Reviewer should be notified
        rev_notifs = requests.get(f"{API}/notifications", headers=H("reviewer")).json()["items"]
        assert any(n["submission_id"] == s["id"] and n["kind"] == "auto_nudge_accept" for n in rev_notifs)

    def test_scheduler_dedupes_same_day(self):
        # Create new submission with past accept_by
        s = _mk_sub(
            "submitter", "product_only", "TEST_IT2_SchedDedupe",
            deadline=_future(20), accept_by=_past(1), review_by=_future(5), approve_by=_future(10),
        )
        requests.post(f"{API}/scheduler/run", headers=H("ceo"))
        time.sleep(0.5)
        requests.post(f"{API}/scheduler/run", headers=H("ceo"))
        after = requests.get(f"{API}/submissions/{s['id']}", headers=H("submitter")).json()
        nudges = [a for a in after["activity"] if a["action"] == "auto_nudge_accept"]
        assert len(nudges) == 1, f"Expected single nudge (dedupe), got {len(nudges)}"

    def test_scheduler_nudge_review(self):
        # Create + reviewer accept, then make review_by past, run scheduler
        s = _mk_sub(
            "submitter", "product_only", "TEST_IT2_SchedReview",
            deadline=_future(30), accept_by=_future(1), review_by=_future(2), approve_by=_future(20),
        )
        a = requests.post(f"{API}/submissions/{s['id']}/accept",
                         headers=H("reviewer"),
                         json={"note": "x", "timeline": {
                             "accept_by": _future(1),
                             "review_by": _past(1),  # already overdue
                             "approve_by": _future(20),
                         }})
        assert a.status_code == 200
        r = requests.post(f"{API}/scheduler/run", headers=H("ceo"))
        assert r.status_code == 200
        after = requests.get(f"{API}/submissions/{s['id']}", headers=H("submitter")).json()
        nudges = [act for act in after["activity"] if act["action"] == "auto_nudge_review"]
        assert len(nudges) >= 1, f"Expected auto_nudge_review activity. Got: {[a['action'] for a in after['activity']]}"

    def test_scheduler_auto_escalates_at_80pct(self):
        # Create with deadline very near (so elapsed/total >= 0.8)
        # Use deadline 1 day in the future but created_at is now — we need elapsed/total >= 0.8.
        # Easier: deadline in past makes progress > 1.0; that satisfies >= 0.8
        s = _mk_sub(
            "submitter", "product_only", "TEST_IT2_SchedEscalate",
            deadline=_past(1), accept_by=_past(3), review_by=_past(2), approve_by=_past(1),
        )
        r = requests.post(f"{API}/scheduler/run", headers=H("ceo"))
        assert r.status_code == 200
        after = requests.get(f"{API}/submissions/{s['id']}", headers=H("submitter")).json()
        escalations = [a for a in after["activity"] if a["action"] == "auto_escalated"]
        assert len(escalations) >= 1, f"Expected auto_escalated. Got: {[a['action'] for a in after['activity']]}"
        assert after["status"] == "escalated"
        assert after["reviewer_role"] == "marketing_lead"  # reviewer -> marketing_lead
