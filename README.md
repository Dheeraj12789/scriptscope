# ScriptScope — Multi-Agent Script Analysis Engine

A Python-based AI system that analyzes short-form scripts using **4 specialist agents** running in parallel, followed by a **cross-agent debate** and an **RL-style feedback loop** that rewrites the script and re-scores to prove which suggestions actually improve engagement.

![Python](https://img.shields.io/badge/Python-3.9+-blue) ![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4.1--mini-green) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-red)

---

## Quick Start

```bash
git clone https://github.com/dheerajgupta0001/scriptscope.git
cd scriptscope
pip install -r requirements.txt
echo "OPENAI_API_KEY=sk-..." > .env
uvicorn app:app --reload --port 8000
```

Open **http://127.0.0.1:8000** → paste a script → click Analyze.

---

## What It Does

Given a short script (1-3 pages of dialogue), the system produces:

| Output | Description |
|--------|-------------|
| **Story Summary** | 3-4 sentence summary with plot type, structure, and character roles |
| **Emotional Arc** | Beat-by-beat emotion mapping with intensity values (0-1) and arc classification |
| **Engagement Score** | 6-factor rubric-based score (hook, conflict, tension, depth, cliffhanger, resolution) |
| **Improvement Suggestions** | 3-5 actionable suggestions targeting the weakest areas |
| **Cliffhanger Detection** | Identifies the peak suspense moment and explains why it works |
| **Script Variants** | Rewrites the script applying top 2 suggestions, re-scores each to prove improvement |
| **Debate Log** | Cross-agent challenges and revisions with evidence |
| **Agent Chat** | Post-analysis Q&A with any of the 4 agents |
| **Architecture Page** | In-app explanation of every design decision (`/architecture`) |

---

## Approach

### Why Multi-Agent?

A single prompt asking the LLM to do everything produces generic output — vague summaries, uncalibrated scores, and shallow suggestions. By splitting the work across 4 specialist agents, each with a focused prompt and domain-specific rubrics, we get:

- **Calibrated scores** — the Engagement Scorer uses defined rubrics per score level, not "rate 1-10"
- **Granular emotion mapping** — the Emotion Analyst maps each dialogue beat individually
- **Cross-informed suggestions** — the Script Doctor reads other agents' findings before suggesting improvements
- **Self-correction** — the debate rounds catch blind spots between agents

### Pipeline Architecture

```
Script → Parser (regex, no LLM)
              │
              ├──► Story Analyst ────┐
              ├──► Emotion Analyst ──┤  (3 agents in parallel)
              ├──► Engagement Scorer ┤
              │                      │
              └──► Script Doctor ────┘  (reads other 3 agents' output)
                                     │
                         Debate (2 rounds)
                                     │
                     Rewrite 2 variants from top suggestions
                                     │
                     Re-score each variant (RL-style feedback)
                                     │
                               Final Report
```

**Phase 1 — Parse:** Pure regex extraction. No LLM call. Splits the script into title, scenes, characters, dialogue beats, and stage directions.

**Phase 2 — Parallel Analysis:** Three agents run simultaneously via `asyncio.gather`. Each produces structured JSON output validated by Pydantic schemas.

**Phase 3 — Informed Analysis:** The Script Doctor reads all three agents' findings from the context, then targets the weakest engagement factors and emotional flat spots.

**Phase 4 — Debate:** 4 debate matchups across 2 rounds. Agents challenge or support each other's findings with evidence. Challenged agents must revise or hold with reasoning.

**Phase 5 — Rewrite:** Top 2 suggestions are applied as full script rewrites. Each variant is a complete rewritten script targeting the weakest engagement factors.

**Phase 6 — Re-score:** Each variant is scored by the Engagement Scorer independently. Score deltas show whether the suggestion actually improved the script — an RL-style feedback loop that proves which suggestions work.

### Agent Descriptions

| Agent | Responsibility | Key Prompt Feature |
|-------|---------------|-------------------|
| **Story Analyst** | Summary, plot type, narrative structure, character roles | Constrained to 9 plot archetypes; structure as arrow chains |
| **Emotion Analyst** | Per-beat emotion + intensity mapping, arc classification | Fixed 15-emotion vocabulary; intensity rubric (0.1-0.3 subtle, 0.9-1.0 overwhelming) |
| **Engagement Scorer** | 6-factor scoring with evidence | Rubric per score level (e.g., "9-10: Immediate mystery, viewer cannot scroll past"); weighted formula for overall |
| **Script Doctor** | Improvement suggestions + cliffhanger detection | Reads other agents' output; targets lowest scores and flat spots first |

---

## Prompt Design

Prompts are the core of this system. Key design decisions:

### 1. Rubric-Based Scoring (not "rate 1-10")

Without rubrics, LLMs produce random, uncalibrated numbers. With rubrics, each score level has explicit criteria:

```
OPENING HOOK:
  9-10: Immediate mystery or physical jolt. Viewer cannot scroll past.
  7-8:  Strong curiosity that takes a moment to land.
  5-6:  Interesting but passive opening.
  3-4:  Generic setup, no urgency.
  1-2:  No reason to keep watching.
```

This produces consistent, explainable scores across different scripts.

### 2. Constrained Emotion Vocabulary

Instead of letting the LLM hallucinate arbitrary emotions, we constrain to 15 options:
`shock, anger, guilt, hope, sadness, tension, vulnerability, uncertainty, joy, relief, fear, nostalgia, revelation, defiance, resignation`

This makes the output structured, comparable across scripts, and visualizable.

### 3. Evidence Requirement

Every engagement score must cite specific dialogue lines. This forces the LLM to ground its analysis in the actual text rather than making vague claims.

### 4. Weighted Scoring Formula

For short-form content, hook and cliffhanger matter most (they determine whether people start watching and share). The overall score uses:

```
overall = (hook×1.5 + conflict + tension + depth + cliffhanger×1.5 + resolution) / 7
```

### 5. Cross-Agent Context for Script Doctor

The Doctor doesn't analyze in isolation — it reads the Engagement Scorer's weak factors and the Emotion Analyst's flat spots, then generates suggestions that target the actual problems.

### 6. Debate Protocol

Agents are paired for cross-review:
- Engagement Scorer → Story Analyst (hook assessment)
- Emotion Analyst → Script Doctor (character depth)
- Story Analyst → Emotion Analyst (arc classification)
- Script Doctor → Engagement Scorer (score calibration)

Each must CHALLENGE or SUPPORT with evidence, then the challenged agent must REVISE or HOLD with reasoning.

---

## Model & Tools

| Component | Choice | Why |
|-----------|--------|-----|
| **LLM** | OpenAI GPT-4.1-mini | Structured output (JSON Schema mode) guarantees valid schemas; fast; cost-effective (~$0.01/analysis) |
| **Structured Output** | OpenAI JSON Schema mode + Pydantic | Eliminates parsing errors; every response matches the exact schema |
| **Backend** | FastAPI + Jinja2 | Python-native; serves UI directly; no separate frontend needed |
| **Parser** | Regex (no LLM) | Deterministic, instant, no cost; handles common script formats |
| **Async** | asyncio.gather | 3 agents run in parallel; reduces wall time by ~60% vs sequential |

### Why GPT-4.1-mini?

- **Structured output mode** — guarantees valid JSON matching Pydantic schemas (no regex parsing, no "hope it's valid JSON")
- **1M token context** — handles long scripts without truncation
- **Cost** — $0.40/1M input tokens, ~$0.01 per full analysis
- **Speed** — faster than GPT-4o for structured tasks
- Could swap to Claude or Gemini via a simple client change

---

## Project Structure

```
scriptscope/
├── app.py              # FastAPI app, routes, template rendering
├── pipeline.py         # Orchestrator: parse → parallel → doctor → debate → merge
├── agents.py           # 4 agent functions + debate + chat + OpenAI client
├── schemas.py          # Pydantic models for all structured outputs
├── prompts.py          # All system prompts with rubrics
├── parser.py           # Regex-based script parser (no LLM)
├── templates/
│   ├── index.html      # Input page with pipeline loading animation
│   ├── results.html    # Dashboard: report, debate, variants, chat, JSON export
│   └── architecture.html # In-app architecture explanation (11 sections)
├── static/
│   └── style.css       # Full CSS styling
├── sample_scripts/     # 3 example scripts
│   ├── the_last_message.txt
│   ├── midnight_confession.txt
│   └── the_interview.txt
├── requirements.txt    # 7 dependencies
├── .env.example
└── README.md
```

**11 files. ~700 lines of Python. ~450 lines of prompts. ~500 lines of HTML/CSS.**

---

## Limitations

- **English only** — prompts and emotion vocabulary are English-specific
- **Single-scene scripts** — no multi-act screenplay support with scene-level aggregation
- **Engagement rubrics are heuristic** — not trained on actual viewership data (completion rates, shares)
- **Debate rounds are fixed (2)** — not dynamic based on disagreement level
- **Latency** — full pipeline takes ~30-60s depending on API response times (4 structured output calls + 4-8 debate calls)
- **No persistence** — analysis results are not saved between sessions
- **Parser is regex-based** — handles common formats but may miss non-standard script layouts

---

## Possible Improvements (with more time)

1. **Fine-tuned scoring model** — train on actual engagement data (views, completion rates, share rates) to replace heuristic rubrics
2. **Multi-scene support** — break long screenplays into scenes, analyze each individually, then synthesize a whole-script report
3. **A/B rewrite mode** — Script Doctor generates alternative versions of weak sections, Engagement Scorer compares before/after
4. **Streaming responses** — show each agent's output as it completes instead of waiting for the full pipeline
5. **Dynamic debate** — more rounds when agents strongly disagree, fewer when aligned
6. **Comparative analysis** — analyze multiple scripts and rank them against each other
7. **Agent memory** — agents remember past analyses and spot patterns across scripts by the same author
8. **Export formats** — PDF report generation, Notion/Google Docs integration

---

## Running the Sample Scripts

The system comes with 3 sample scripts:

| Script | Genre | Beats | Key Feature |
|--------|-------|-------|-------------|
| **The Last Message** | Revelation Drama | 8 | Suspended decision ending |
| **Midnight Confession** | Thriller | 12 | Loyalty vs. duty conflict |
| **The Interview** | Psychological Drama | 14 | Impossible moral choice |

Select any sample from the dropdown on the input page, or paste your own script.

---

## Cost

| Per Analysis | Tokens | Cost |
|-------------|--------|------|
| 3 parallel agents | ~6,000 | ~$0.004 |
| Script Doctor | ~3,000 | ~$0.002 |
| Debate (2 rounds) | ~4,000 | ~$0.003 |
| **Total** | **~13,000** | **~$0.009** |

Less than 1 cent per analysis.

---

## License

MIT
