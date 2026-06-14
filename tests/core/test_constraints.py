"""Tests for constraint validators."""

import pytest
from evolution.core.constraints import ConstraintValidator
from evolution.core.config import EvolutionConfig


@pytest.fixture
def validator():
    config = EvolutionConfig()
    return ConstraintValidator(config)


class TestSizeConstraints:
    def test_skill_under_limit(self, validator):
        result = validator._check_size("x" * 1000, "skill")
        assert result.passed

    def test_skill_over_limit(self, validator):
        result = validator._check_size("x" * 20_000, "skill")
        assert not result.passed
        assert "exceeded" in result.message

    def test_tool_description_under_limit(self, validator):
        result = validator._check_size("Search files by content", "tool_description")
        assert result.passed

    def test_tool_description_over_limit(self, validator):
        result = validator._check_size("x" * 600, "tool_description")
        assert not result.passed


class TestGrowthConstraints:
    def test_acceptable_growth(self, validator):
        baseline = "x" * 1000
        evolved = "x" * 1100  # 10% growth
        result = validator._check_growth(evolved, baseline, "skill")
        assert result.passed

    def test_excessive_growth(self, validator):
        baseline = "x" * 1000
        evolved = "x" * 1300  # 30% growth
        result = validator._check_growth(evolved, baseline, "skill")
        assert not result.passed

    def test_shrinkage_is_ok(self, validator):
        baseline = "x" * 1000
        evolved = "x" * 800  # 20% smaller
        result = validator._check_growth(evolved, baseline, "skill")
        assert result.passed

    def test_excessive_shrinkage_fails(self, validator):
        baseline = "x" * 1000
        evolved = "x" * 500
        result = validator._check_shrinkage(evolved, baseline, "skill")
        assert not result.passed

    def test_growth_is_not_reported_as_negative_shrinkage(self, validator):
        baseline = "x" * 1000
        evolved = "x" * 1400
        result = validator._check_shrinkage(evolved, baseline, "skill")
        assert result.passed
        assert "+0.0%" in result.message


class TestNonEmpty:
    def test_non_empty_passes(self, validator):
        result = validator._check_non_empty("some content")
        assert result.passed

    def test_empty_fails(self, validator):
        result = validator._check_non_empty("")
        assert not result.passed

    def test_whitespace_only_fails(self, validator):
        result = validator._check_non_empty("   \n  ")
        assert not result.passed


class TestSkillStructure:
    def test_valid_skill(self, validator):
        skill = "---\nname: test-skill\ndescription: A test skill\n---\n\n# Test\nContent here"
        result = validator._check_skill_structure(skill)
        assert result.passed

    def test_missing_frontmatter(self, validator):
        skill = "# Test\nContent without frontmatter"
        result = validator._check_skill_structure(skill)
        assert not result.passed

    def test_missing_name(self, validator):
        skill = "---\ndescription: A test skill\n---\n\n# Test"
        result = validator._check_skill_structure(skill)
        assert not result.passed

    def test_missing_description(self, validator):
        skill = "---\nname: test-skill\n---\n\n# Test"
        result = validator._check_skill_structure(skill)
        assert not result.passed


class TestValidateAll:
    def test_valid_skill_passes_all(self, validator):
        skill = "---\nname: test\ndescription: Test skill\n---\n\n# Procedure\n1. Do thing"
        results = validator.validate_all(skill, "skill")
        assert all(r.passed for r in results)

    def test_empty_skill_fails(self, validator):
        results = validator.validate_all("", "skill")
        failed = [r for r in results if not r.passed]
        assert len(failed) > 0

    def test_reference_mentions_must_be_preserved(self, validator):
        baseline = (
            "---\nname: test\ndescription: Test skill\n---\n\n"
            "# Procedure\nRead [playbook](references/playbook.md).\n"
            "## Steps\nDo thing"
        )
        evolved = (
            "---\nname: test\ndescription: Test skill\n---\n\n"
            "# Procedure\nUse the playbook.\n"
            "## Steps\nDo thing"
        )

        results = validator.validate_all(evolved, "skill", baseline_text=baseline)
        failed = {r.constraint_name for r in results if not r.passed}

        assert "reference_retention" in failed

    def test_reference_mentions_pass_when_preserved(self, validator):
        baseline = (
            "---\nname: test\ndescription: Test skill\n---\n\n"
            "# Procedure\nRead references/playbook.md.\n"
            "## Steps\nDo thing"
        )
        evolved = (
            "---\nname: test\ndescription: Test skill\n---\n\n"
            "# Procedure\nStill read references/playbook.md.\n"
            "## Steps\nDo thing"
        )

        results = validator.validate_all(evolved, "skill", baseline_text=baseline)
        assert all(r.passed for r in results)
