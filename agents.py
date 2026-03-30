"""Four specialist agents + debate + variant generation.

Each agent is a function that takes parsed script data and returns
structured output via OpenAI's JSON Schema mode.

Error handling: individual agent failures are caught and return
sensible defaults so the pipeline doesn't crash entirely.
"""

import json
import os
import logging
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from schemas import (
    StorySummary, EmotionalArc, EngagementScore,
    DoctorOutput, DebateEntry, ParsedScript,
    ScriptVariant, ScoredVariant, Suggestion,
    StoryCharacter, EmotionBeat, EngagementFactor,
    CliffhangerMoment,
)
import prompts

logger = logging.getLogger("scriptscope")

_client = None
MODEL = "gpt-4.1-mini"
TIMEOUT = 120  # seconds per LLM call


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set. Add it to .env file.")
        _client = OpenAI(api_key=api_key, timeout=TIMEOUT)
    return _client


# ──────────────────────────────────────────────────────────────
# Schema fixer for OpenAI strict JSON Schema mode
# OpenAI requires: additionalProperties=false on every object,
# all properties in required[], optional fields as anyOf with null.
# Pydantic doesn't generate this by default, so we patch it.
# ──────────────────────────────────────────────────────────────

def _fix_schema(schema: dict) -> dict:
    """Recursively fix schema for OpenAI strict JSON Schema mode."""
    if not isinstance(schema, dict):
        return schema

    if schema.get("type") == "object" and "properties" in schema:
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"].keys())

        for prop_name, prop_val in list(schema["properties"].items()):
            if isinstance(prop_val, dict) and prop_val.get("default") is None:
                if "anyOf" not in prop_val:
                    inner = {k: v for k, v in prop_val.items()
                             if k not in ("default", "description", "title")}
                    if inner:
                        new_prop = {"anyOf": [inner, {"type": "null"}], "default": None}
                        for keep in ("description", "title"):
                            if keep in prop_val:
                                new_prop[keep] = prop_val[keep]
                        schema["properties"][prop_name] = new_prop

    for v in schema.values():
        if isinstance(v, dict):
            _fix_schema(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _fix_schema(item)

    if "$defs" in schema:
        for d in schema["$defs"].values():
            _fix_schema(d)

    return schema


# ──────────────────────────────────────────────────────────────
# Core LLM call wrappers
# ──────────────────────────────────────────────────────────────

def _call_structured(system_prompt: str, user_content: str, schema_class, schema_name: str):
    """Call OpenAI with structured output. Raises on failure."""
    client = _get_client()
    fixed_schema = _fix_schema(schema_class.model_json_schema())

    response = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": fixed_schema,
                "strict": True,
            }
        },
    )
    return schema_class.model_validate_json(response.output_text)


def _call_text(system_prompt: str, user_content: str) -> str:
    """Call OpenAI for free-text response."""
    client = _get_client()
    response = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return response.output_text


def _script_context(parsed: ParsedScript) -> str:
    """Format parsed script as context string for agents."""
    ctx = f"TITLE: {parsed.title}\n\n"
    ctx += "SCENES:\n"
    for s in parsed.scenes:
        ctx += f"  {s}\n"
    ctx += f"\nCHARACTERS: {', '.join(c.name for c in parsed.characters)}\n"
    ctx += f"\nDIALOGUE ({parsed.total_beats} beats):\n"
    for b in parsed.beats:
        dir_tag = " [has stage direction]" if b.has_stage_direction else ""
        ctx += f"  Beat {b.beat_number}: {b.character}: {b.line}{dir_tag}\n"
    if parsed.stage_directions:
        ctx += "\nSTAGE DIRECTIONS:\n"
        for d in parsed.stage_directions:
            ctx += f"  [{d}]\n"
    return ctx


# ──────────────────────────────────────────────────────────────
# The 4 Agents (with error handling)
# ──────────────────────────────────────────────────────────────

def story_analyst(parsed: ParsedScript) -> StorySummary:
    """Analyze plot, structure, characters. Returns fallback on error."""
    try:
        return _call_structured(
            system_prompt=prompts.STORY_ANALYST,
            user_content=_script_context(parsed),
            schema_class=StorySummary,
            schema_name="story_summary",
        )
    except Exception as e:
        logger.error(f"Story Analyst failed: {e}")
        return StorySummary(
            summary=f"Analysis failed: {str(e)[:100]}",
            plot_type="Unknown",
            narrative_structure="Unable to determine",
            characters=[StoryCharacter(name=c.name, role="unknown") for c in parsed.characters],
            tags=["error"],
        )


def emotion_analyst(parsed: ParsedScript) -> EmotionalArc:
    """Map emotional arc beat-by-beat. Returns fallback on error."""
    try:
        return _call_structured(
            system_prompt=prompts.EMOTION_ANALYST,
            user_content=_script_context(parsed),
            schema_class=EmotionalArc,
            schema_name="emotional_arc",
        )
    except Exception as e:
        logger.error(f"Emotion Analyst failed: {e}")
        return EmotionalArc(
            beats=[EmotionBeat(
                beat_number=b.beat_number, dialogue_line=b.line,
                character=b.character, primary_emotion="uncertainty",
                intensity=0.5, reasoning=f"Fallback: {str(e)[:50]}"
            ) for b in parsed.beats],
            dominant_emotions=["uncertainty"],
            arc_type="unknown",
            arc_description=f"Analysis failed: {str(e)[:100]}",
        )


def engagement_scorer(parsed: ParsedScript) -> EngagementScore:
    """Score engagement across 6 factors. Returns fallback on error."""
    try:
        return _call_structured(
            system_prompt=prompts.ENGAGEMENT_SCORER,
            user_content=_script_context(parsed),
            schema_class=EngagementScore,
            schema_name="engagement_score",
        )
    except Exception as e:
        logger.error(f"Engagement Scorer failed: {e}")
        default_factors = [
            EngagementFactor(name=n, score=5.0, reasoning=f"Fallback: {str(e)[:50]}", evidence_lines=[])
            for n in ["hook", "conflict", "tension", "depth", "cliffhanger", "resolution"]
        ]
        return EngagementScore(overall=5.0, factors=default_factors, scoring_note="Fallback scores due to error")


def script_doctor(
    parsed: ParsedScript,
    story: StorySummary,
    emotion: EmotionalArc,
    engagement: EngagementScore,
) -> DoctorOutput:
    """Generate suggestions informed by other agents. Returns fallback on error."""
    try:
        context = _script_context(parsed)
        context += "\n\n--- OTHER AGENTS' FINDINGS ---\n\n"
        context += f"STORY ANALYST:\n{json.dumps(story.model_dump(), indent=2)}\n\n"
        context += f"EMOTION ANALYST:\n{json.dumps(emotion.model_dump(), indent=2)}\n\n"
        context += f"ENGAGEMENT SCORER:\n{json.dumps(engagement.model_dump(), indent=2)}\n"

        return _call_structured(
            system_prompt=prompts.SCRIPT_DOCTOR,
            user_content=context,
            schema_class=DoctorOutput,
            schema_name="doctor_output",
        )
    except Exception as e:
        logger.error(f"Script Doctor failed: {e}")
        return DoctorOutput(
            suggestions=[Suggestion(
                title="Analysis Error",
                description=f"Script Doctor could not run: {str(e)[:100]}",
                category="dialogue", target_lines=[],
            )],
            cliffhanger=None,
        )


# ──────────────────────────────────────────────────────────────
# Debate
# ──────────────────────────────────────────────────────────────

DEBATE_MATCHUPS = [
    ("Engagement Scorer", "Story Analyst",    "opening_and_hook_assessment"),
    ("Emotion Analyst",   "Script Doctor",    "character_emotional_depth"),
    ("Story Analyst",     "Emotion Analyst",  "arc_classification_and_ending"),
    ("Script Doctor",     "Engagement Scorer","score_calibration_and_resolution"),
]

AGENT_FINDINGS = {
    "Story Analyst": "story",
    "Emotion Analyst": "emotion",
    "Engagement Scorer": "engagement",
    "Script Doctor": "doctor",
}


def run_debate(findings: dict, rounds: int = 2) -> list:
    """Run debate rounds. Catches individual debate errors gracefully."""
    debate_log = []

    # Round 1: Challenge or Support
    for source, target, topic in DEBATE_MATCHUPS:
        try:
            source_data = findings[AGENT_FINDINGS[source]]
            target_data = findings[AGENT_FINDINGS[target]]

            prompt = prompts.DEBATE_CHALLENGE.format(
                source_agent=source,
                target_agent=target,
                source_findings=json.dumps(source_data.model_dump(), indent=2),
                target_findings=json.dumps(target_data.model_dump(), indent=2),
                topic=topic,
            )

            response = _call_text("You are a script analysis agent in a debate.", prompt)

            action = "challenge"
            if "ALIGNED" in response.upper() or "SUPPORT" in response.upper():
                action = "support"

            debate_log.append(DebateEntry(
                round=1, source_agent=source, target_agent=target,
                action=action, message=response.strip(), claim_referenced=topic,
            ))
        except Exception as e:
            logger.error(f"Debate R1 {source}→{target} failed: {e}")
            debate_log.append(DebateEntry(
                round=1, source_agent=source, target_agent=target,
                action="support", message=f"(Debate error, defaulting to aligned: {str(e)[:60]})",
                claim_referenced=topic,
            ))

    # Round 2: Respond to challenges
    if rounds >= 2:
        challenges = [e for e in debate_log if e.action == "challenge"]
        for challenge in challenges:
            try:
                agent_name = challenge.target_agent
                agent_key = AGENT_FINDINGS[agent_name]
                agent_data = findings[agent_key]

                prompt = prompts.DEBATE_RESPOND.format(
                    agent_name=agent_name,
                    own_findings=json.dumps(agent_data.model_dump(), indent=2),
                    challenge_message=challenge.message,
                )

                response = _call_text(
                    "You are a script analysis agent responding to a debate challenge.",
                    prompt,
                )

                action = "hold"
                if "REVISE" in response.upper() or "ACCEPT" in response.upper() or "UPDAT" in response.upper():
                    action = "revise"

                debate_log.append(DebateEntry(
                    round=2, source_agent=agent_name, target_agent=challenge.source_agent,
                    action=action, message=response.strip(), claim_referenced=challenge.claim_referenced,
                ))
            except Exception as e:
                logger.error(f"Debate R2 {agent_name} response failed: {e}")

    return debate_log


# ──────────────────────────────────────────────────────────────
# Variant Generation (Rewrite + Re-score)
# ──────────────────────────────────────────────────────────────

def rewrite_script(
    parsed: ParsedScript,
    suggestion: Suggestion,
    engagement: EngagementScore,
) -> Optional[ScriptVariant]:
    """Rewrite the script applying one suggestion. Returns None on error."""
    try:
        sorted_factors = sorted(engagement.factors, key=lambda f: f.score)
        weakest = sorted_factors[:2]
        strongest = sorted_factors[-2:]

        context = f"ORIGINAL SCRIPT:\n{parsed.raw_text}\n\n"
        context += f"SUGGESTION TO APPLY:\n"
        context += f"  Title: {suggestion.title}\n"
        context += f"  Category: {suggestion.category}\n"
        context += f"  Description: {suggestion.description}\n"
        if suggestion.target_lines:
            context += f"  Target lines: {suggestion.target_lines}\n"
        context += f"\nORIGINAL ENGAGEMENT SCORES (overall: {engagement.overall}/10):\n"
        for f in engagement.factors:
            marker = ""
            if f in weakest:
                marker = " ← WEAKEST, MUST IMPROVE"
            elif f in strongest:
                marker = " ← STRONG, DO NOT WEAKEN"
            context += f"  {f.name}: {f.score}/10{marker}\n"
        context += f"\nYOUR REWRITE MUST SCORE HIGHER THAN {engagement.overall}/10 OVERALL."

        return _call_structured(
            system_prompt=prompts.SCRIPT_REWRITER,
            user_content=context,
            schema_class=ScriptVariant,
            schema_name="script_variant",
        )
    except Exception as e:
        logger.error(f"Rewrite failed for '{suggestion.title}': {e}")
        return None


def score_variant(variant: ScriptVariant, original_engagement: EngagementScore) -> Optional[ScoredVariant]:
    """Re-score a rewritten variant. Returns None on error."""
    try:
        from parser import parse_script
        reparsed = parse_script(variant.rewritten_script)

        new_engagement = _call_structured(
            system_prompt=prompts.ENGAGEMENT_SCORER,
            user_content=_script_context(reparsed),
            schema_class=EngagementScore,
            schema_name="engagement_score",
        )

        delta = round(new_engagement.overall - original_engagement.overall, 2)

        orig_factors = "\n".join(f"  {f.name}: {f.score}" for f in original_engagement.factors)
        new_factors = "\n".join(f"  {f.name}: {f.score}" for f in new_engagement.factors)

        summary = _call_text(
            "You are a script analysis comparison expert.",
            prompts.VARIANT_COMPARISON.format(
                original_score=original_engagement.overall,
                variant_score=new_engagement.overall,
                original_factors=orig_factors,
                variant_factors=new_factors,
            ),
        )

        return ScoredVariant(
            variant=variant,
            engagement=new_engagement,
            score_delta=delta,
            improvement_summary=summary.strip(),
        )
    except Exception as e:
        logger.error(f"Variant scoring failed: {e}")
        return None


def generate_variants(
    parsed: ParsedScript,
    suggestions: list,
    engagement: EngagementScore,
    max_variants: int = 2,
) -> list:
    """Generate rewritten variants from top suggestions, then re-score.
    Skips any variant that fails to generate or score."""
    to_rewrite = suggestions[:max_variants]

    scored_variants = []
    for suggestion in to_rewrite:
        variant = rewrite_script(parsed, suggestion, engagement)
        if variant is None:
            continue
        scored = score_variant(variant, engagement)
        if scored is None:
            continue
        scored_variants.append(scored)

    scored_variants.sort(key=lambda sv: sv.score_delta, reverse=True)
    return scored_variants


# ──────────────────────────────────────────────────────────────
# Post-Analysis Chat
# ──────────────────────────────────────────────────────────────

def agent_chat(agent_name: str, user_message: str, full_analysis: dict) -> str:
    """Chat with a specific agent. Returns error message on failure."""
    try:
        agent_key_map = {
            "Story Analyst": "story",
            "Emotion Analyst": "emotional_arc",
            "Engagement Scorer": "engagement",
            "Script Doctor": "suggestions",
        }

        own_key = agent_key_map.get(agent_name, "story")
        own_findings = full_analysis.get(own_key, {})
        debate_log = full_analysis.get("debate_log", [])

        prompt = prompts.AGENT_CHAT.format(
            agent_name=agent_name,
            own_findings=json.dumps(own_findings, indent=2),
            full_analysis=json.dumps(full_analysis, indent=2)[:3000],
            debate_log=json.dumps(debate_log, indent=2),
        )

        return _call_text(prompt, f"User question: {user_message}")
    except Exception as e:
        logger.error(f"Agent chat failed: {e}")
        return f"Sorry, I encountered an error: {str(e)[:100]}"
