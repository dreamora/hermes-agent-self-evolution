"""Constraint validators for evolved artifacts.

Every candidate variant must pass ALL constraints before it can be
considered valid. Failed constraints = immediate rejection.
"""

import subprocess
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from evolution.core.config import EvolutionConfig


@dataclass
class ConstraintResult:
    """Result of constraint validation."""
    passed: bool
    constraint_name: str
    message: str
    details: Optional[str] = None


class ConstraintValidator:
    """Validates evolved artifacts against hard constraints."""

    def __init__(self, config: EvolutionConfig):
        self.config = config

    def validate_all(
        self,
        artifact_text: str,
        artifact_type: str,
        baseline_text: Optional[str] = None,
    ) -> list[ConstraintResult]:
        """Run all applicable constraints. Returns list of results."""
        results = []

        # 1. Size limits
        results.append(self._check_size(artifact_text, artifact_type))

        # 2. Growth limit (if baseline provided)
        if baseline_text:
            results.append(self._check_growth(artifact_text, baseline_text, artifact_type))
            results.append(self._check_shrinkage(artifact_text, baseline_text, artifact_type))

        # 3. Non-empty
        results.append(self._check_non_empty(artifact_text))

        # 4. Structural integrity
        if artifact_type == "skill":
            results.append(self._check_skill_structure(artifact_text))
            if baseline_text:
                results.append(self._check_heading_retention(artifact_text, baseline_text))
                results.append(self._check_reference_retention(artifact_text, baseline_text))

        return results

    def run_test_suite(self, hermes_repo: Path) -> ConstraintResult:
        """Run the full hermes-agent test suite. Must pass 100%."""
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/", "-q", "--tb=no"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(hermes_repo),
            )

            if result.returncode == 0:
                return ConstraintResult(
                    passed=True,
                    constraint_name="test_suite",
                    message="All tests passed",
                    details=result.stdout.strip().split("\n")[-1] if result.stdout else "",
                )
            else:
                # Extract failure summary
                last_lines = result.stdout.strip().split("\n")[-5:] if result.stdout else []
                return ConstraintResult(
                    passed=False,
                    constraint_name="test_suite",
                    message="Test suite failed",
                    details="\n".join(last_lines),
                )
        except subprocess.TimeoutExpired:
            return ConstraintResult(
                passed=False,
                constraint_name="test_suite",
                message="Test suite timed out (300s)",
            )
        except Exception as e:
            return ConstraintResult(
                passed=False,
                constraint_name="test_suite",
                message=f"Failed to run tests: {e}",
            )

    def _check_size(self, text: str, artifact_type: str) -> ConstraintResult:
        size = len(text)
        if artifact_type == "skill":
            limit = self.config.max_skill_size
        elif artifact_type == "tool_description":
            limit = self.config.max_tool_desc_size
        elif artifact_type == "param_description":
            limit = self.config.max_param_desc_size
        else:
            limit = self.config.max_skill_size  # Default

        if size <= limit:
            return ConstraintResult(
                passed=True,
                constraint_name="size_limit",
                message=f"Size OK: {size}/{limit} chars",
            )
        else:
            return ConstraintResult(
                passed=False,
                constraint_name="size_limit",
                message=f"Size exceeded: {size}/{limit} chars ({size - limit} over)",
            )

    def _check_growth(self, text: str, baseline: str, artifact_type: str) -> ConstraintResult:
        growth = (len(text) - len(baseline)) / max(1, len(baseline))
        max_growth = self.config.max_prompt_growth

        if growth <= max_growth:
            return ConstraintResult(
                passed=True,
                constraint_name="growth_limit",
                message=f"Growth OK: {growth:+.1%} (max {max_growth:+.1%})",
            )
        else:
            return ConstraintResult(
                passed=False,
                constraint_name="growth_limit",
                message=f"Growth exceeded: {growth:+.1%} (max {max_growth:+.1%})",
            )

    def _check_shrinkage(self, text: str, baseline: str, artifact_type: str) -> ConstraintResult:
        shrinkage = max(0.0, (len(baseline) - len(text)) / max(1, len(baseline)))
        max_shrink = self.config.max_prompt_shrink

        if shrinkage <= max_shrink:
            return ConstraintResult(
                passed=True,
                constraint_name="shrinkage_limit",
                message=f"Shrinkage OK: {shrinkage:+.1%} (max {max_shrink:+.1%})",
            )
        else:
            return ConstraintResult(
                passed=False,
                constraint_name="shrinkage_limit",
                message=f"Shrinkage exceeded: {shrinkage:+.1%} (max {max_shrink:+.1%})",
            )

    def _check_non_empty(self, text: str) -> ConstraintResult:
        if text.strip():
            return ConstraintResult(
                passed=True,
                constraint_name="non_empty",
                message="Artifact is non-empty",
            )
        else:
            return ConstraintResult(
                passed=False,
                constraint_name="non_empty",
                message="Artifact is empty",
            )

    def _check_skill_structure(self, text: str) -> ConstraintResult:
        """Check that a skill file has valid YAML frontmatter and markdown body."""
        has_frontmatter = text.strip().startswith("---")
        has_name = "name:" in text[:500] if has_frontmatter else False
        has_description = "description:" in text[:500] if has_frontmatter else False

        if has_frontmatter and has_name and has_description:
            return ConstraintResult(
                passed=True,
                constraint_name="skill_structure",
                message="Skill has valid frontmatter (name + description)",
            )
        else:
            missing = []
            if not has_frontmatter:
                missing.append("YAML frontmatter (---)")
            if not has_name:
                missing.append("name field")
            if not has_description:
                missing.append("description field")
            return ConstraintResult(
                passed=False,
                constraint_name="skill_structure",
                message=f"Skill missing: {', '.join(missing)}",
            )

    def _check_heading_retention(self, text: str, baseline: str) -> ConstraintResult:
        baseline_headings = _markdown_headings(baseline)
        if not baseline_headings:
            return ConstraintResult(
                passed=True,
                constraint_name="heading_retention",
                message="No baseline headings to preserve",
            )

        headings = set(_markdown_headings(text))
        kept = [heading for heading in baseline_headings if heading in headings]
        retention = len(kept) / len(baseline_headings)
        minimum = self.config.min_heading_retention

        if retention >= minimum:
            return ConstraintResult(
                passed=True,
                constraint_name="heading_retention",
                message=f"Heading retention OK: {retention:.1%} (min {minimum:.1%})",
            )
        else:
            missing = [heading for heading in baseline_headings if heading not in headings][:5]
            return ConstraintResult(
                passed=False,
                constraint_name="heading_retention",
                message=f"Heading retention too low: {retention:.1%} (min {minimum:.1%})",
                details="Missing headings: " + ", ".join(missing),
            )

    def _check_reference_retention(self, text: str, baseline: str) -> ConstraintResult:
        baseline_refs = _referenced_markdown_paths(baseline)
        if not baseline_refs:
            return ConstraintResult(
                passed=True,
                constraint_name="reference_retention",
                message="No baseline reference links to preserve",
            )

        refs = _referenced_markdown_paths(text)
        missing = sorted(baseline_refs - refs)
        if not missing:
            return ConstraintResult(
                passed=True,
                constraint_name="reference_retention",
                message=f"Preserved {len(baseline_refs)} referenced file mentions",
            )
        return ConstraintResult(
            passed=False,
            constraint_name="reference_retention",
            message=f"Missing {len(missing)} referenced file mention(s)",
            details="Missing references: " + ", ".join(missing[:5]),
        )


def _markdown_headings(text: str) -> list[str]:
    headings = []
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if match:
            headings.append(re.sub(r"\s+", " ", match.group(1)).strip().lower())
    return headings


def _referenced_markdown_paths(text: str) -> set[str]:
    refs = set()
    patterns = [
        r"\]\(([^)]+\.md)(?:#[^)]+)?\)",
        r"(?<![\w./-])((?:references|templates)/[^\s)]+\.md)",
        r"(?<![\w./-])(SPEC\.md)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            refs.add(match.split("#", 1)[0].strip())
    return refs
