"""All Pydantic models for the Content Approval Agent."""
from typing import List, Literal, Optional
from pydantic import BaseModel, EmailStr, Field, model_validator


Role = Literal["submitter", "reviewer", "marketing_lead", "vp", "ceo"]
SubmissionStatus = Literal[
    "scored", "pending_acceptance", "in_progress", "under_review",
    "approved", "revision_requested", "escalated", "live",
]
Tier = Literal["auto_approve", "product_only", "ceo_required"]


# -------- Auth --------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Role = "submitter"
    team: Optional[str] = ""
    designation: Optional[str] = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


# -------- Scoring --------
class ScoreIn(BaseModel):
    title: str
    request_type: str
    brief: str
    content: str


class ScoreResult(BaseModel):
    brand_alignment_score: int
    completeness_score: int
    content_classification: Literal["routine", "innovation"]
    risk_flags: List[str]
    overall_score: int
    recommended_tier: Tier
    reasoning: str
    questions_to_resolve: List[str]


# -------- Files --------
class Attachment(BaseModel):
    id: str
    original_filename: str
    content_type: str
    size: int
    storage_path: str


# -------- Submissions --------
class Timeline(BaseModel):
    accept_by: str
    review_by: str
    approve_by: str


class SubmissionCreate(BaseModel):
    title: str
    request_type: str
    brief: str
    content: str
    deadline: str
    score_result: ScoreResult
    chosen_tier: Tier
    attachments: List[Attachment] = Field(default_factory=list)
    timeline: Timeline
    assigned_user_id: Optional[str] = None

    @model_validator(mode="after")
    def _require_assignee_for_non_auto(self):
        if self.chosen_tier != "auto_approve" and not (self.assigned_user_id or "").strip():
            raise ValueError("assigned_user_id is required for non auto_approve tiers")
        return self


class TimelineProposal(BaseModel):
    accept_by: str
    review_by: str
    approve_by: str
    note: Optional[str] = ""


class AcceptIn(BaseModel):
    note: Optional[str] = ""
    timeline: Optional[Timeline] = None


class ActionIn(BaseModel):
    note: Optional[str] = ""


class RevisionIn(BaseModel):
    note: str


class EscalateIn(BaseModel):
    note: Optional[str] = ""
    assigned_user_id: Optional[str] = None


class ApproveForwardIn(BaseModel):
    note: Optional[str] = ""
    assigned_user_id: str
    timeline: Optional[Timeline] = None
