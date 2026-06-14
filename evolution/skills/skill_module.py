"""Wraps a SKILL.md file as a DSPy module for optimization.

The key abstraction: a skill file becomes a parameterized DSPy module
where the skill text is the optimizable parameter. GEPA can then
mutate the skill text and evaluate the results.
"""

import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import dspy


REFERENCE_DIRS = ("references", "templates")
EXCLUDED_PARTS = {".git", "__pycache__", ".cache", "node_modules"}
MARKDOWN_SUFFIXES = {".md", ".markdown"}


@dataclass
class SkillBundle:
    """A skill and its read-only local reference context."""

    skill: dict
    skill_dir: Path
    reference_context: str
    reference_files: list[Path]


def load_skill(skill_path: Path) -> dict:
    """Load a skill file and parse its frontmatter + body.

    Returns:
        {
            "path": Path,
            "raw": str (full file content),
            "frontmatter": str (YAML between --- markers),
            "body": str (markdown after frontmatter),
            "name": str,
            "description": str,
        }
    """
    raw = skill_path.read_text()

    # Parse YAML frontmatter
    frontmatter = ""
    body = raw
    if raw.strip().startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            body = parts[2].strip()

    # Extract name and description from frontmatter
    name = ""
    description = ""
    for line in frontmatter.split("\n"):
        if line.strip().startswith("name:"):
            name = line.split(":", 1)[1].strip().strip("'\"")
        elif line.strip().startswith("description:"):
            description = line.split(":", 1)[1].strip().strip("'\"")

    return {
        "path": skill_path,
        "raw": raw,
        "frontmatter": frontmatter,
        "body": body,
        "name": name,
        "description": description,
    }


def load_skill_bundle(skill_path: Path, context_budget: int = 20_000) -> SkillBundle:
    """Load a skill plus safe local referenced files as read-only context."""
    skill = load_skill(skill_path)
    skill_dir = skill_path.parent
    reference_files = discover_reference_files(skill_path, skill["raw"])
    reference_context = format_reference_context(reference_files, skill_dir, context_budget)
    return SkillBundle(
        skill=skill,
        skill_dir=skill_dir,
        reference_context=reference_context,
        reference_files=reference_files,
    )


def discover_reference_files(skill_path: Path, skill_text: str) -> list[Path]:
    """Discover safe local markdown context files for a skill."""
    skill_dir = skill_path.parent
    seen = set()
    ordered = []

    def add(path: Path):
        resolved = path.resolve()
        if resolved in seen or not _is_safe_reference_file(resolved, skill_dir):
            return
        seen.add(resolved)
        ordered.append(resolved)

    for ref in _explicit_reference_paths(skill_text):
        add(skill_dir / ref)

    for dirname in REFERENCE_DIRS:
        root = skill_dir / dirname
        if root.exists():
            for path in sorted(root.rglob("*")):
                add(path)

    add(skill_dir / "SPEC.md")

    for path in sorted(skill_dir.glob("*.md")):
        if path.name != "SKILL.md":
            add(path)

    return ordered


def format_reference_context(reference_files: list[Path], skill_dir: Path, context_budget: int) -> str:
    """Render referenced files as bounded, read-only context."""
    if not reference_files or context_budget <= 0:
        return ""

    parts = []
    for path in reference_files:
        rel = path.relative_to(skill_dir)
        raw = path.read_text(errors="replace")
        current_size = len("\n\n".join(parts))
        separator_size = 2 if parts else 0
        remaining = context_budget - current_size - separator_size
        rendered = _format_reference_file(rel, raw, remaining)
        if not rendered:
            break
        parts.append(rendered)
        if len("\n\n".join(parts)) >= context_budget:
            break

    return "\n\n".join(parts).strip()[:context_budget]


def _format_reference_file(relative_path: Path, text: str, budget: int) -> str:
    header = f"### Reference: {relative_path}\n"
    if budget <= len(header):
        return ""

    available = budget - len(header)
    if len(text) <= available:
        return header + text.strip()

    excerpt = _headings_and_excerpt(text, available)
    return header + excerpt.strip()


def _headings_and_excerpt(text: str, budget: int) -> str:
    lines = text.splitlines()
    heading_lines = [line for line in lines if re.match(r"^\s{0,3}#{1,6}\s+", line)]
    excerpt = "\n".join(lines[:80])
    combined = "\n".join(heading_lines[:30] + ["", excerpt]).strip()
    return combined[:budget]


def _explicit_reference_paths(skill_text: str) -> list[Path]:
    matches = []
    patterns = [
        r"\]\(([^)]+\.md)\)",
        r"(?<![\w./-])((?:references|templates)/[^\s)]+\.md)",
        r"(?<![\w./-])(SPEC\.md)",
    ]
    for pattern in patterns:
        matches.extend(re.findall(pattern, skill_text))
    return [Path(match.split("#", 1)[0]) for match in matches]


def _is_safe_reference_file(path: Path, skill_dir: Path) -> bool:
    try:
        path.relative_to(skill_dir.resolve())
    except ValueError:
        return False
    if not path.is_file():
        return False
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if path.name.startswith(".") or path.name == "SKILL.md":
        return False
    return path.suffix.lower() in MARKDOWN_SUFFIXES


def find_skill(skill_name: str, hermes_agent_path: Path) -> Optional[Path]:
    """Find a skill by name in the hermes-agent skills directory.

    Searches recursively for a SKILL.md in a directory matching the skill name.
    """
    skills_dir = hermes_agent_path / "skills"
    if not skills_dir.exists():
        return None

    # Direct match: skills/<category>/<skill_name>/SKILL.md
    for skill_md in skills_dir.rglob("SKILL.md"):
        if skill_md.parent.name == skill_name:
            return skill_md

    # Fuzzy match: check the name field in frontmatter
    for skill_md in skills_dir.rglob("SKILL.md"):
        try:
            content = skill_md.read_text()[:500]
            if f"name: {skill_name}" in content or f'name: "{skill_name}"' in content:
                return skill_md
        except Exception:
            continue

    return None


class SkillModule(dspy.Module):
    """A DSPy module that wraps a skill file for optimization.

    The skill text (body) is the parameter that GEPA optimizes.
    On each forward pass, the module:
    1. Uses the skill text as instructions
    2. Processes the task input
    3. Returns the agent's response
    """

    def __init__(self, skill_text: str, reference_context: str = ""):
        super().__init__()
        self.reference_context = reference_context
        instructions = (
            f"{skill_text}\n\n"
            "Read-only reference context may be provided as an input. Use it to preserve "
            "the skill's intended doctrine, templates, and examples, but do not copy it "
            "verbatim unless the task requires it."
        )
        signature = dspy.Signature("reference_context, task_input -> output", instructions)
        self.predictor = dspy.ChainOfThought(signature)

    @property
    def skill_text(self) -> str:
        instructions = self.predictor.predict.signature.instructions
        marker = "\n\nRead-only reference context may be provided as an input."
        return instructions.split(marker, 1)[0]

    @skill_text.setter
    def skill_text(self, value: str) -> None:
        suffix = (
            "\n\nRead-only reference context may be provided as an input. Use it to preserve "
            "the skill's intended doctrine, templates, and examples, but do not copy it "
            "verbatim unless the task requires it."
        )
        self.predictor.predict.signature = self.predictor.predict.signature.with_instructions(value + suffix)

    def forward(self, task_input: str) -> dspy.Prediction:
        result = self.predictor(
            reference_context=self.reference_context,
            task_input=task_input,
        )
        return dspy.Prediction(output=result.output)


def reassemble_skill(frontmatter: str, evolved_body: str) -> str:
    """Reassemble a skill file from frontmatter and evolved body.

    Preserves the original YAML frontmatter (name, description, metadata)
    and replaces only the body with the evolved version.
    """
    return f"---\n{frontmatter}\n---\n\n{evolved_body}\n"


def preserve_reference_mentions(evolved_body: str, baseline_text: str) -> str:
    """Ensure evolved skill body keeps baseline referenced-file mentions."""
    baseline_refs = _reference_mentions(baseline_text)
    if not baseline_refs:
        return evolved_body

    evolved_refs = _reference_mentions(evolved_body)
    missing = [ref for ref in baseline_refs if ref not in evolved_refs]
    if not missing:
        return evolved_body

    section = ["## Referenced Files", ""]
    section.extend(f"- `{ref}`" for ref in missing)
    return evolved_body.rstrip() + "\n\n" + "\n".join(section) + "\n"


def _reference_mentions(text: str) -> list[str]:
    refs = []
    seen = set()
    patterns = [
        r"\]\(([^)]+\.md)(?:#[^)]+)?\)",
        r"(?<![\w./-])((?:references|templates)/[^\s)]+\.md)",
        r"(?<![\w./-])(SPEC\.md)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            ref = match.split("#", 1)[0].strip()
            if ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return refs
