"""Pydantic models for all structured outputs."""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict


# --- Parsed Script (from regex parser, not LLM) ---

class Character(BaseModel):
    name: str
    line_count: int = 0


class DialogueBeat(BaseModel):
    beat_number: int
    character: str
    line: str
    has_stage_direction: bool = False


class ParsedScript(BaseModel):
    title: str
    raw_text: str
    scenes: list[str]
    characters: list[Character]
    beats: list[DialogueBeat]
    stage_directions: list[str]
    total_beats: int
    total_characters: int


# --- Story Analyst Output ---

class StoryCharacter(BaseModel):
    name: str
    role: str = Field(description="protagonist, antagonist, catalyst, or observer")


class StorySummary(BaseModel):
    summary: str = Field(description="3-4 sentence summary of the story")
    plot_type: str = Field(description="e.g. Revelation Drama, Confrontation, Redemption")
    narrative_structure: str = Field(description="Arrow chain: setup → confrontation → revelation")
    characters: List[StoryCharacter] = Field(description="Each with name and role")
    tags: List[str] = Field(description="2-4 genre/theme tags")


# --- Emotion Analyst Output ---

EMOTION_OPTIONS = Literal[
    "shock", "anger", "guilt", "hope", "sadness", "tension",
    "vulnerability", "uncertainty", "joy", "relief", "fear",
    "nostalgia", "revelation", "defiance", "resignation"
]


class EmotionBeat(BaseModel):
    beat_number: int
    dialogue_line: str
    character: str
    primary_emotion: EMOTION_OPTIONS
    intensity: float = Field(ge=0.0, le=1.0, description="0.0 barely present, 1.0 overwhelming")
    secondary_emotion: Optional[EMOTION_OPTIONS] = None
    reasoning: str = Field(description="Why this emotion at this intensity")


class EmotionalArc(BaseModel):
    beats: list[EmotionBeat]
    dominant_emotions: list[str] = Field(description="2-3 emotions that define this script")
    arc_type: str = Field(description="e.g. tension → release → ambiguity")
    arc_description: str = Field(description="1-2 sentence description of the emotional journey")
    turning_point: Optional[str] = Field(default=None, description="The beat where the dominant emotion shifts")


# --- Engagement Scorer Output ---

class EngagementFactor(BaseModel):
    name: str = Field(description="hook, conflict, tension, depth, cliffhanger, resolution")
    score: float = Field(ge=0.0, le=10.0)
    reasoning: str = Field(description="Why this score, citing specific dialogue lines")
    evidence_lines: list[str] = Field(description="Specific dialogue lines that support this score")


class EngagementScore(BaseModel):
    overall: float = Field(ge=0.0, le=10.0, description="Weighted overall score")
    factors: list[EngagementFactor]
    scoring_note: str = Field(description="Brief note on how the overall was calculated")


# --- Script Doctor Output ---

class Suggestion(BaseModel):
    title: str
    description: str = Field(description="Actionable suggestion with reasoning")
    category: Literal["pacing", "dialogue", "conflict", "hook", "character", "setting"]
    target_lines: list[str] = Field(default_factory=list, description="Lines this suggestion targets")


class CliffhangerMoment(BaseModel):
    quote: str = Field(description="The exact text of the cliffhanger moment")
    explanation: str = Field(description="Why this moment works as a cliffhanger")
    tension_score: float = Field(ge=0.0, le=10.0)


class DoctorOutput(BaseModel):
    suggestions: list[Suggestion] = Field(description="3-5 improvement suggestions")
    cliffhanger: Optional[CliffhangerMoment] = Field(default=None, description="The peak suspense moment")


# --- Debate ---

class DebateEntry(BaseModel):
    round: int
    source_agent: str
    target_agent: str
    action: Literal["challenge", "support", "revise", "hold"]
    message: str
    claim_referenced: str = ""


# --- Script Variants (Rewrite + Re-score) ---

class ScriptVariant(BaseModel):
    variant_name: str = Field(description="e.g. 'Stronger Hook', 'Deeper Conflict'")
    focus: str = Field(description="Which suggestion this variant applies")
    rewritten_script: str = Field(description="The full rewritten script text")
    changes_made: List[str] = Field(description="List of specific changes applied")


class ScoredVariant(BaseModel):
    variant: ScriptVariant
    engagement: EngagementScore
    score_delta: float = Field(description="Difference from original overall score")
    improvement_summary: str = Field(description="1-2 sentence summary of what improved and why")


# --- Final Combined Result ---

class AnalysisResult(BaseModel):
    title: str
    story: StorySummary
    emotional_arc: EmotionalArc
    engagement: EngagementScore
    suggestions: list[Suggestion]
    cliffhanger: Optional[CliffhangerMoment] = None
    debate_log: List[DebateEntry] = Field(default_factory=list)
    variants: List[ScoredVariant] = Field(default_factory=list)
    metadata: dict
