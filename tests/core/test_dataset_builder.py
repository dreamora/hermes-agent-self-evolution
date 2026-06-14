"""Tests for evaluation dataset generation."""

import contextlib
import json

from evolution.core.config import EvolutionConfig
from evolution.core.dataset_builder import SyntheticDatasetBuilder


class FakeGenerator:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)

        class Result:
            test_cases = json.dumps([
                {
                    "task_input": "Use the skill",
                    "expected_behavior": "Should use referenced doctrine",
                    "difficulty": "medium",
                    "category": "reference_context",
                }
            ])

        return Result()


def test_synthetic_generation_receives_reference_context(monkeypatch):
    monkeypatch.setattr("evolution.core.dataset_builder.dspy.LM", lambda model: object())
    monkeypatch.setattr("evolution.core.dataset_builder.dspy.context", lambda **kwargs: contextlib.nullcontext())

    builder = SyntheticDatasetBuilder(EvolutionConfig())
    fake = FakeGenerator()
    builder.generator = fake

    dataset = builder.generate(
        artifact_text="SKILL.md body",
        artifact_type="skill",
        reference_context="Reference doctrine",
        num_cases=1,
    )

    assert fake.calls[0]["artifact_text"] == "SKILL.md body"
    assert fake.calls[0]["reference_context"] == "Reference doctrine"
    assert len(dataset.all_examples) == 1
