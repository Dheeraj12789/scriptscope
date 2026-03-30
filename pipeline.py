"""Pipeline: parse → 3 agents parallel → doctor → debate → rewrite + re-score → merge.

No orchestrator class. No planner. Just functions.
"""

import asyncio
import time
from schemas import AnalysisResult, ParsedScript
from parser import parse_script
from agents import (
    story_analyst,
    emotion_analyst,
    engagement_scorer,
    script_doctor,
    run_debate,
    generate_variants,
)


async def run_pipeline(raw_script: str) -> AnalysisResult:
    """Full analysis pipeline. Returns AnalysisResult."""
    start = time.time()

    # Phase 1: Parse (regex, no LLM)
    parsed = parse_script(raw_script)

    # Phase 2: Three agents in parallel
    story, emotion, engagement = await asyncio.gather(
        asyncio.to_thread(story_analyst, parsed),
        asyncio.to_thread(emotion_analyst, parsed),
        asyncio.to_thread(engagement_scorer, parsed),
    )

    # Phase 3: Doctor reads other agents' output
    doctor = await asyncio.to_thread(
        script_doctor, parsed, story, emotion, engagement
    )

    # Phase 4: Debate (2 rounds)
    findings = {
        "story": story,
        "emotion": emotion,
        "engagement": engagement,
        "doctor": doctor,
    }
    debate_log = await asyncio.to_thread(run_debate, findings, 2)

    # Phase 5: Generate rewritten variants from top 2 suggestions, re-score each
    variants = await asyncio.to_thread(
        generate_variants, parsed, doctor.suggestions, engagement, 2
    )

    # Phase 6: Merge into final result
    duration = round(time.time() - start, 1)

    result = AnalysisResult(
        title=parsed.title,
        story=story,
        emotional_arc=emotion,
        engagement=engagement,
        suggestions=doctor.suggestions,
        cliffhanger=doctor.cliffhanger,
        debate_log=debate_log,
        variants=[v for v in variants],
        metadata={
            "duration_seconds": duration,
            "model": "gpt-4.1-mini",
            "debate_rounds": 2,
            "total_agents": 4,
            "total_beats": parsed.total_beats,
            "total_characters": parsed.total_characters,
            "revisions": sum(1 for d in debate_log if d.action == "revise"),
            "variants_generated": len(variants),
        },
    )

    return result
