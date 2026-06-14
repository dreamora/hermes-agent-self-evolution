"""Tests for skill module loading and parsing."""

import pytest
from pathlib import Path
from evolution.skills.skill_module import (
    SkillModule,
    discover_reference_files,
    load_skill,
    load_skill_bundle,
    preserve_reference_mentions,
    reassemble_skill,
)


SAMPLE_SKILL = """---
name: test-skill
description: A skill for testing things
version: 1.0.0
metadata:
  hermes:
    tags: [testing]
---

# Test Skill — Testing Things

## When to Use
Use this when you need to test things.

## Procedure
1. First, do the thing
2. Then, verify it worked
3. Report results

## Pitfalls
- Don't forget to check edge cases
"""


class TestLoadSkill:
    def test_parses_frontmatter(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(SAMPLE_SKILL)
        skill = load_skill(skill_file)

        assert skill["name"] == "test-skill"
        assert skill["description"] == "A skill for testing things"
        assert "version: 1.0.0" in skill["frontmatter"]

    def test_parses_body(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(SAMPLE_SKILL)
        skill = load_skill(skill_file)

        assert "# Test Skill" in skill["body"]
        assert "## Procedure" in skill["body"]
        assert "Don't forget" in skill["body"]

    def test_raw_contains_everything(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(SAMPLE_SKILL)
        skill = load_skill(skill_file)

        assert skill["raw"] == SAMPLE_SKILL

    def test_path_is_stored(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(SAMPLE_SKILL)
        skill = load_skill(skill_file)

        assert skill["path"] == skill_file


class TestReassembleSkill:
    def test_roundtrip(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(SAMPLE_SKILL)
        skill = load_skill(skill_file)

        reassembled = reassemble_skill(skill["frontmatter"], skill["body"])
        assert "---" in reassembled
        assert "name: test-skill" in reassembled
        assert "# Test Skill" in reassembled

    def test_preserves_frontmatter(self):
        frontmatter = "name: my-skill\ndescription: Does stuff"
        body = "# My Skill\nDo the thing."
        result = reassemble_skill(frontmatter, body)

        assert result.startswith("---\n")
        assert "name: my-skill" in result
        assert "# My Skill" in result

    def test_evolved_body_replaces_original(self):
        frontmatter = "name: my-skill\ndescription: Does stuff"
        evolved_body = "# EVOLVED\nNew and improved procedure."
        result = reassemble_skill(frontmatter, evolved_body)

        assert "EVOLVED" in result
        assert "New and improved" in result


class TestPreserveReferenceMentions:
    def test_appends_missing_references(self):
        baseline = (
            "# Skill\n"
            "Use references/playbook.md and [template](templates/output.md)."
        )
        evolved = "# Skill\nImproved instructions."

        result = preserve_reference_mentions(evolved, baseline)

        assert "## Referenced Files" in result
        assert "`references/playbook.md`" in result
        assert "`templates/output.md`" in result

    def test_does_not_duplicate_existing_references(self):
        baseline = "# Skill\nUse references/playbook.md."
        evolved = "# Skill\nStill use references/playbook.md."

        result = preserve_reference_mentions(evolved, baseline)

        assert "## Referenced Files" not in result
        assert result == evolved


class TestLoadSkillBundle:
    def test_discovers_safe_reference_context(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        refs = skill_dir / "references"
        templates = skill_dir / "templates"
        refs.mkdir(parents=True)
        templates.mkdir()
        (refs / "playbook.md").write_text("# Playbook\nReference doctrine")
        (templates / "output.md").write_text("# Output\nTemplate")
        (skill_dir / "SPEC.md").write_text("# Spec\nDetails")
        (skill_dir / "notes.md").write_text("# Notes\nNearby markdown")
        (skill_dir / "script.py").write_text("print('ignore')")
        (skill_dir / ".DS_Store").write_text("ignore")
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test\n---\n\n"
            "# My Skill\nSee [playbook](references/playbook.md)."
        )

        bundle = load_skill_bundle(skill_dir / "SKILL.md")

        relative_files = [path.relative_to(skill_dir) for path in bundle.reference_files]
        assert relative_files == [
            Path("references/playbook.md"),
            Path("templates/output.md"),
            Path("SPEC.md"),
            Path("notes.md"),
        ]
        assert "Reference: references/playbook.md" in bundle.reference_context
        assert "Reference doctrine" in bundle.reference_context
        assert "script.py" not in bundle.reference_context

    def test_no_references_returns_empty_context(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(SAMPLE_SKILL)

        bundle = load_skill_bundle(skill_path)

        assert bundle.reference_files == []
        assert bundle.reference_context == ""

    def test_context_budget_uses_excerpt(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        refs = skill_dir / "references"
        refs.mkdir(parents=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(SAMPLE_SKILL)
        (refs / "long.md").write_text("# Important\n" + ("long text\n" * 200))

        bundle = load_skill_bundle(skill_path, context_budget=120)

        assert "Reference: references/long.md" in bundle.reference_context
        assert len(bundle.reference_context) <= 120

    def test_discovers_explicit_references_before_directory_files(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        refs = skill_dir / "references"
        refs.mkdir(parents=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(
            "---\nname: my-skill\ndescription: Test\n---\n\n"
            "Read [second](references/second.md)."
        )
        (refs / "first.md").write_text("# First")
        (refs / "second.md").write_text("# Second")

        files = discover_reference_files(skill_path, skill_path.read_text())

        assert [path.name for path in files] == ["second.md", "first.md"]


class TestSkillModule:
    def test_skill_text_excludes_read_only_reference_context(self):
        module = SkillModule("# Mutable Skill", reference_context="# Reference")

        assert module.skill_text == "# Mutable Skill"
        assert "reference_context" in module.predictor.predict.signature.input_fields
        assert module.reference_context == "# Reference"
