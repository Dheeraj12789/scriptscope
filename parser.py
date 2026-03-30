"""Script parser — pure regex, no LLM.

Extracts title, scenes, characters, dialogue beats, and stage directions
from common script formats.
"""

import re
from schemas import ParsedScript, Character, DialogueBeat


def parse_script(raw_text: str) -> ParsedScript:
    lines = raw_text.strip().split("\n")
    lines = [l.strip() for l in lines if l.strip()]

    title = _extract_title(lines)
    scenes = _extract_scenes(lines)
    beats, characters_map = _extract_dialogue(lines)
    stage_directions = _extract_stage_directions(lines)

    characters = [
        Character(name=name, line_count=count)
        for name, count in characters_map.items()
    ]

    return ParsedScript(
        title=title,
        raw_text=raw_text,
        scenes=scenes,
        characters=characters,
        beats=beats,
        stage_directions=stage_directions,
        total_beats=len(beats),
        total_characters=len(characters),
    )


def _extract_title(lines: list[str]) -> str:
    for line in lines[:5]:
        m = re.match(r"^(?:Title|TITLE)\s*:\s*(.+)", line, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return "Untitled Script"


def _extract_scenes(lines: list[str]) -> list[str]:
    scenes = []
    scene_pattern = re.compile(
        r"^(?:Scene|SCENE|INT\.|EXT\.|INT/EXT\.)[\s:.-]*(.*)",
        re.IGNORECASE,
    )
    i = 0
    while i < len(lines):
        m = scene_pattern.match(lines[i])
        if m:
            scene_text = m.group(1).strip() if m.group(1).strip() else ""
            # Collect lines until next section header or dialogue
            i += 1
            while i < len(lines) and not _is_section_header(lines[i]) and not _is_dialogue(lines[i]):
                scene_text += " " + lines[i]
                i += 1
            if scene_text.strip():
                scenes.append(scene_text.strip())
        else:
            i += 1

    # Fallback: if no Scene headers, look for descriptive blocks before dialogue
    if not scenes:
        for line in lines:
            if not _is_dialogue(line) and not _is_section_header(line) and len(line) > 30:
                scenes.append(line)
                break

    return scenes if scenes else ["No explicit scene description found."]


def _extract_dialogue(lines: list[str]) -> tuple[list[DialogueBeat], dict[str, int]]:
    beats = []
    characters: dict[str, int] = {}
    beat_num = 0

    dialogue_pattern = re.compile(r"^([A-Z][a-zA-Z]+)\s*:\s*(.+)")

    skip_labels = {"title", "scene", "dialogue", "act", "setting", "int", "ext"}

    for line in lines:
        m = dialogue_pattern.match(line)
        if m:
            char_name = m.group(1).strip()
            if char_name.lower() in skip_labels:
                continue
            dialogue_text = m.group(2).strip()
            beat_num += 1

            # Check for parenthetical stage directions
            has_direction = bool(re.search(r"\(.*?\)", dialogue_text))

            characters[char_name] = characters.get(char_name, 0) + 1

            beats.append(DialogueBeat(
                beat_number=beat_num,
                character=char_name,
                line=dialogue_text,
                has_stage_direction=has_direction,
            ))

    return beats, characters


def _extract_stage_directions(lines: list[str]) -> list[str]:
    directions = []
    bracket_pattern = re.compile(r"^\[(.+)\]$")

    for line in lines:
        m = bracket_pattern.match(line)
        if m:
            directions.append(m.group(1).strip())

    return directions


def _is_section_header(line: str) -> bool:
    headers = ["scene", "dialogue", "title", "act", "int.", "ext."]
    lower = line.lower().strip()
    return any(lower.startswith(h) for h in headers)


def _is_dialogue(line: str) -> bool:
    return bool(re.match(r"^[A-Z][a-zA-Z]+\s*:", line))
