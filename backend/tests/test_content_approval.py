"""Backend test suite for Content Approval Agent."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://routing-agent.preview.emergentagent.com").rstrip("/")

CREDS = {
    "submitter": ("submitter@govern.app", "Pass1234!", "Sara Submitter", "submitter"),
    "reviewer": ("reviewer@govern.app", "Pass1234!", "Reza Reviewer", "reviewer"),
    "lead": ("lead@govern.app", "Pass1234!", "Maya Lead", "marketing_lead"),
    "ceo": ("ceo@govern.app", "Pass1234!", "Carl Chief", "ceo"),
}

TOKENS = {}


def _login_or_register(key):
    email, pwd, name, role = CREDS[key]
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd})
    if r.status_code == 200:
        return r.json()
    # Register if missing
    r = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": pwd, "name": name, "role": role})
    assert r.status_code == 200, f"register {key} failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="session", autouse=True)
def auth_all():
    for k in CREDS:
        data = _login_or_register(k)
        TOKENS[k] = data["token"]
    return TOKENS


def hdr(role_key):
    return {"Authorization": f"Bearer {TOKENS[role_key]}"}


# ---------- Auth ----------
class TestAuth:
    def test_login_all_roles(self):
        for k, (email, pwd, _, role) in CREDS.items():
            r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd})
            assert r.status_code == 200, f"{k} login failed: {r.text}"
            j = r.json()
            assert j["user"]["email"] == email
            assert j["user"]["role"] == role
            assert isinstance(j["token"], str) and len(j["token"]) > 20

    def test_login_invalid(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "submitter@govern.app", "password": "wrong"})
        assert r.status_code == 401

    def test_me(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=hdr("submitter"))
        assert r.status_code == 200
        assert r.json()["email"] == "submitter@govern.app"

    def test_me_no_token(self):
        r = requests.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code in (401, 403)

    def test_register_duplicate(self):
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": "submitter@govern.app", "password": "Pass1234!", "name": "x", "role": "submitter"
        })
        assert r.status_code == 400


# ---------- Scoring ----------
SCORED = {}


class TestScore:
    def test_score_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/score", json={
            "title": "x", "content_type": "social_post", "brief": "x", "content": "x"
        })
        assert r.status_code in (401, 403)

    def test_score_routine(self):
        r = requests.post(f"{BASE_URL}/api/score", headers=hdr("submitter"), json={
            "title": "Weekly Team Update",
            "content_type": "social_post",
            "brief": "Audience: LinkedIn followers. Goal: share weekly team culture moment. CTA: like and share. Channel: LinkedIn.",
            "content": "This week our engineering team shipped 3 features. Proud of the collaboration across regions. #teamwork",
        }, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        for f in ["brand_alignment_score","completeness_score","content_classification","risk_flags","overall_score","recommended_tier","reasoning","questions_to_resolve"]:
            assert f in j, f"missing {f}"
        assert 0 <= j["brand_alignment_score"] <= 100
        assert 0 <= j["completeness_score"] <= 100
        assert 0 <= j["overall_score"] <= 100
        assert j["content_classification"] in ("routine", "innovation")
        assert j["recommended_tier"] in ("auto_approve", "product_only", "ceo_required")
        assert isinstance(j["risk_flags"], list)
        assert isinstance(j["questions_to_resolve"], list)
        SCORED["routine"] = j

    def test_score_risky(self):
        r = requests.post(f"{BASE_URL}/api/score", headers=hdr("submitter"), json={
            "title": "New Pricing Announcement & Partnership Launch",
            "content_type": "press_release",
            "brief": "Announcing 20% price increase across all plans and new strategic partnership with Acme Corp. Target: enterprise customers. Channel: PR wire.",
            "content": "Today we announce major pricing changes and a partnership with Acme Corp to transform the industry.",
        }, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["recommended_tier"] in ("ceo_required", "product_only")
        SCORED["risky"] = j


# ---------- Submissions ----------
SUBS = {}


class TestSubmissions:
    def test_create_auto_approve(self):
        score = SCORED.get("routine") or {
            "brand_alignment_score": 90, "completeness_score": 90, "content_classification": "routine",
            "risk_flags": [], "overall_score": 90, "recommended_tier": "auto_approve",
            "reasoning": "ok", "questions_to_resolve": []
        }
        r = requests.post(f"{BASE_URL}/api/submissions", headers=hdr("submitter"), json={
            "title": "TEST_AutoApprove", "content_type": "social_post", "brief": "b", "content": "c",
            "deadline": "2026-12-01", "score_result": score, "chosen_tier": "auto_approve",
        })
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "approved"
        assert j["activity"][0]["action"] == "submitted"
        assert any(a["action"] == "auto_approved" for a in j["activity"])
        SUBS["auto"] = j["id"]

    def test_create_product_only(self):
        score = {"brand_alignment_score": 70, "completeness_score": 70, "content_classification": "routine",
                 "risk_flags": [], "overall_score": 70, "recommended_tier": "product_only",
                 "reasoning": "x", "questions_to_resolve": []}
        r = requests.post(f"{BASE_URL}/api/submissions", headers=hdr("submitter"), json={
            "title": "TEST_ProductOnly", "content_type": "blog_article", "brief": "b", "content": "c",
            "deadline": "2026-12-01", "score_result": score, "chosen_tier": "product_only",
        })
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "under_review"
        assert j["reviewer_role"] == "reviewer"
        SUBS["product"] = j["id"]

    def test_create_ceo_required(self):
        score = {"brand_alignment_score": 80, "completeness_score": 80, "content_classification": "innovation",
                 "risk_flags": ["pricing"], "overall_score": 80, "recommended_tier": "ceo_required",
                 "reasoning": "x", "questions_to_resolve": []}
        r = requests.post(f"{BASE_URL}/api/submissions", headers=hdr("submitter"), json={
            "title": "TEST_CEORequired", "content_type": "pricing_update", "brief": "b", "content": "c",
            "deadline": "2026-12-01", "score_result": score, "chosen_tier": "ceo_required",
        })
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "under_review"
        assert j["reviewer_role"] == "ceo"
        SUBS["ceo"] = j["id"]

    def test_list_submissions(self):
        r = requests.get(f"{BASE_URL}/api/submissions", headers=hdr("reviewer"))
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list) and len(items) >= 3
        for it in items:
            for f in ("idle_hours", "idle_days", "needs_nudge", "needs_escalation"):
                assert f in it

    def test_list_filter(self):
        r = requests.get(f"{BASE_URL}/api/submissions?status_filter=approved", headers=hdr("reviewer"))
        assert r.status_code == 200
        for it in r.json():
            assert it["status"] == "approved"

    def test_get_single(self):
        r = requests.get(f"{BASE_URL}/api/submissions/{SUBS['product']}", headers=hdr("reviewer"))
        assert r.status_code == 200
        j = r.json()
        assert j["id"] == SUBS["product"]
        assert "score_result" in j
        assert isinstance(j["activity"], list) and len(j["activity"]) >= 1

    def test_get_404(self):
        r = requests.get(f"{BASE_URL}/api/submissions/nonexistent-id", headers=hdr("reviewer"))
        assert r.status_code == 404

    def test_submitter_cannot_approve(self):
        r = requests.post(f"{BASE_URL}/api/submissions/{SUBS['product']}/approve",
                          headers=hdr("submitter"), json={"note": "n/a"})
        assert r.status_code == 403

    def test_reviewer_approves(self):
        r = requests.post(f"{BASE_URL}/api/submissions/{SUBS['product']}/approve",
                          headers=hdr("reviewer"), json={"note": "Looks good"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "approved"
        assert any(a["action"] == "approved" for a in j["activity"])
        assert "under_review" in (j.get("stage_durations") or {})

    def test_request_revision(self):
        r = requests.post(f"{BASE_URL}/api/submissions/{SUBS['ceo']}/request-revision",
                          headers=hdr("ceo"), json={"note": "Please rework"})
        assert r.status_code == 200
        assert r.json()["status"] == "revision_requested"

    def test_escalate(self):
        # Create fresh product_only sub to escalate
        score = {"brand_alignment_score": 70, "completeness_score": 70, "content_classification": "routine",
                 "risk_flags": [], "overall_score": 70, "recommended_tier": "product_only",
                 "reasoning": "x", "questions_to_resolve": []}
        c = requests.post(f"{BASE_URL}/api/submissions", headers=hdr("submitter"), json={
            "title": "TEST_Escalate", "content_type": "blog_article", "brief": "b", "content": "c",
            "deadline": "2026-12-01", "score_result": score, "chosen_tier": "product_only",
        }).json()
        r = requests.post(f"{BASE_URL}/api/submissions/{c['id']}/escalate",
                          headers=hdr("lead"), json={"note": "Escalating"})
        assert r.status_code == 200
        assert r.json()["status"] == "escalated"

    def test_mark_live(self):
        r = requests.post(f"{BASE_URL}/api/submissions/{SUBS['auto']}/mark-live",
                          headers=hdr("reviewer"), json={"note": "Published"})
        assert r.status_code == 200
        assert r.json()["status"] == "live"

    def test_nudge(self):
        r = requests.get(f"{BASE_URL}/api/submissions/{SUBS['ceo']}", headers=hdr("submitter"))
        before = len(r.json()["activity"])
        before_status = r.json()["status"]
        r = requests.post(f"{BASE_URL}/api/submissions/{SUBS['ceo']}/nudge",
                          headers=hdr("submitter"), json={"note": "Friendly nudge"})
        assert r.status_code == 200
        j = r.json()
        assert len(j["activity"]) == before + 1
        assert j["activity"][-1]["action"] == "nudged"
        assert j["status"] == before_status  # status unchanged


# ---------- Analytics ----------
class TestAnalytics:
    def test_overview(self):
        r = requests.get(f"{BASE_URL}/api/analytics/overview", headers=hdr("ceo"))
        assert r.status_code == 200
        j = r.json()
        for f in ["total","by_status","by_tier","by_type","risk_flag_counts","idle_count","idle_breakdown","avg_stage_hours","avg_approval_hours","bottleneck_reviewers","completed_count"]:
            assert f in j, f"missing {f}"
        assert j["total"] >= 3
        assert isinstance(j["by_status"], dict)
        assert isinstance(j["idle_breakdown"], list)
        assert j["completed_count"] >= 1
