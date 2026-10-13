"""Task submission IDs resolve to immutable Research Memory source refs."""

import pytest

from research_agent.application.api import execute
from research_agent.research import records
from tests.unit.test_job_recovery import workspace


def test_create_resolves_submission_id_without_guessing_research_ref(tmp_path):
    workspace(tmp_path)
    source = records.record_source(tmp_path, {
        "session_id": "session-1", "message_id": "11", "text": "Study this question",
    })

    created = execute("research.create", tmp_path, {
        "session_id": "session-1", "goal": "Study the question",
        "source_submission_ids": ["11"],
    })

    assert created["node"]["source_refs"] == [source["source_ref"]]

    review = execute("research.read", tmp_path, {
        "session_id": "session-1", "view": "review",
        "source_submission_ids": ["11"],
    })
    assert review["user_sources"] == [{
        "submission_id": "11", "research_ref": source["source_ref"],
    }]


def test_fake_user_ref_explains_the_namespace_error(tmp_path):
    workspace(tmp_path)
    with pytest.raises(ValueError, match="source_ref_invalid.*source_submission_ids"):
        execute("research.create", tmp_path, {
            "goal": "Study the question", "source_refs": ["user_11"],
        })


def test_unknown_submission_id_is_rejected(tmp_path):
    workspace(tmp_path)
    with pytest.raises(ValueError, match="source_submission_not_found: 11"):
        execute("research.create", tmp_path, {
            "session_id": "session-1", "goal": "Study the question",
            "source_submission_ids": ["11"],
        })
