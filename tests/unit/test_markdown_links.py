import pytest

from tools.markdown_links import markdown_links
from tools import lint_skills


@pytest.mark.parametrize("code", [
    "`[H:31][C:8]([H:32])([H:33])…`",
    "``[example](missing.md) with a ` inside``",
    "`multiline\n[example](missing.md)`",
    "```smiles\n[H:31][C:8]([H:32])([H:33])\n```",
    "~~~text\n[example](missing.md)\n~~~",
    "````text\n```\n[example](missing.md)\n````",
    "   ~~~text\n[example](missing.md)\n   ~~~~",
])
def test_code_examples_do_not_become_links(code):
    assert markdown_links(code + '\n[`real link`](guide.md) ![image](plot.png)') == [
        'guide.md', 'plot.png',
    ]


def test_unmatched_and_escaped_backticks_leave_real_links_visible():
    assert markdown_links('Unmatched ` and [real](guide.md)') == ['guide.md']
    assert markdown_links(r'Escaped \` [real](guide.md) \`') == ['guide.md']
    assert markdown_links('Unmatched `\n\n[real](guide.md) and another `') == ['guide.md']


def test_unclosed_fence_hides_remaining_example_text():
    assert markdown_links('[real](guide.md)\n```\n[example](missing.md)') == ['guide.md']


def test_smiles_does_not_hide_adjacent_broken_links_or_fragments(tmp_path, monkeypatch):
    monkeypatch.setattr(lint_skills, 'ROOT', tmp_path)
    entry = tmp_path / 'SKILL.md'
    (tmp_path / 'guide.md').write_text('# Guide\n')
    text = '`[H:31][C:8]([H:32])([H:33])` [valid](guide.md#guide)\n'
    text += '[broken](missing.md) [wrong heading](guide.md#absent)\n'
    errors = lint_skills._check_links(entry, text)
    assert errors == ['SKILL.md: broken link missing.md', 'SKILL.md: broken fragment guide.md#absent']


def test_examples_do_not_count_as_skill_reference_routes(tmp_path):
    entry = tmp_path / 'SKILL.md'
    example, actual = tmp_path / 'example.md', tmp_path / 'actual.md'
    example.write_text('# Example\n')
    actual.write_text('# Actual\n')
    entry.write_text('`[example](example.md)`\n[actual](actual.md)\n')
    assert lint_skills._reachable_references(entry, tmp_path) == {entry, actual}
