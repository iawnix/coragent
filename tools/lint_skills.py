#!/usr/bin/env python3
"""Validate the public Skill entrypoints and progressive-disclosure layout."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

if __package__:
    from .markdown_links import markdown_links
else:
    from markdown_links import markdown_links


ROOT = Path(__file__).resolve().parents[1]
FRONTMATTER = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
FIELD = re.compile(r"(?m)^(name|description):\s*(.+?)\s*$")
FORBIDDEN_PUBLIC_NAMES = ("research_" + "continuation", "ts_" + "environment", "ts_" + "reply", "ts_" + "seed", "ts_" + "compare", "ts_" + "analyze", "ts_" + "dispatch", "ts_" + "import", "ts_" + "notify", "ts_" + "render", "ts_" + "report")


def _frontmatter(path: Path) -> dict[str, str]:
    match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"{path}: missing YAML frontmatter")
    fields = dict(FIELD.findall(match.group("body")))
    if set(fields) != {"name", "description"}:
        raise ValueError(f"{path}: frontmatter must contain only name and description")
    return fields


def _heading_slugs(text: str) -> set[str]:
    """Return GitHub-style slugs for Markdown ATX headings.

    Skill references are local, reviewed Markdown.  Checking their fragments
    catches stale routing links without requiring a full Markdown parser.
    """

    slugs: set[str] = set()
    duplicate_counts: dict[str, int] = {}
    for line in text.splitlines():
        match = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        heading = re.sub(r"[`*_~]", "", match.group(2)).strip().lower()
        chars: list[str] = []
        for char in unicodedata.normalize("NFKC", heading):
            if char.isalnum() or char in {"_", "-", " "}:
                chars.append(char)
        slug = re.sub(r"\s+", "-", "".join(chars)).strip("-")
        if not slug:
            continue
        duplicate = duplicate_counts.get(slug, 0)
        duplicate_counts[slug] = duplicate + 1
        slugs.add(slug if duplicate == 0 else f"{slug}-{duplicate}")
    return slugs


def _check_links(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for raw in markdown_links(text):
        target = raw.strip().strip("<>")
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
            continue
        relative_part, separator, fragment = target.partition("#")
        relative = unquote(relative_part.split("?", 1)[0])
        resolved = path if not relative else (path.parent / relative).resolve()
        if not resolved.is_absolute():
            resolved = resolved.resolve()
        if not resolved.is_relative_to(ROOT) or not resolved.exists():
            errors.append(f"{path.relative_to(ROOT)}: broken link {target}")
            continue
        if separator and fragment:
            headings = _heading_slugs(resolved.read_text(encoding="utf-8"))
            if unquote(fragment).lower() not in headings:
                errors.append(f"{path.relative_to(ROOT)}: broken fragment {target}")
    return errors


def _reachable_references(entry: Path, skill_root: Path) -> set[Path]:
    """Allow progressive disclosure through linked references, not just the entry."""
    visited: set[Path] = set()
    pending = [entry.resolve()]
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        for raw in markdown_links(path.read_text(encoding="utf-8")):
            target = raw.strip().strip("<>")
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                continue
            relative = unquote(target.split("#", 1)[0].split("?", 1)[0])
            resolved = (path.parent / relative).resolve()
            if resolved.is_relative_to(skill_root.resolve()) and resolved.suffix == ".md" and resolved.is_file():
                # Do not let a translation's routes hide missing local routes.
                if resolved.name.endswith(".zh-CN.md") == entry.name.endswith(".zh-CN.md"):
                    pending.append(resolved)
    return visited


def _check_script_routing(root: Path, skill_roots: list[Path]) -> list[str]:
    """Keep the progressive-disclosure entrypoints tied to the execution registry."""
    errors: list[str] = []
    routing_doc = root / "docs" / "skill-script-routing.md"
    routing_doc_zh = root / "docs" / "skill-script-routing.zh-CN.md"
    if not routing_doc.is_file() or not routing_doc_zh.is_file():
        return ["docs/skill-script-routing(.zh-CN).md: script routing maps are required"]
    routing = routing_doc.read_text(encoding="utf-8")
    execution = root / "domains" / "chemical" / "execution.json"
    if execution.is_file():
        for item in json.loads(execution.read_text(encoding="utf-8")).get("executors", []):
            operation = item["id"]
            short_operation = operation.removeprefix("chemical.")
            entry = item.get("entry")
            cli = item.get("cli")
            for value, label in ((short_operation, "operation"), (entry, "entry"), (cli, "cli")):
                if value and value not in routing:
                    errors.append(f"docs/skill-script-routing.md: missing {label} {value}")
    for skill_root in skill_roots:
        english = skill_root / "SKILL.md"
        chinese = skill_root / "SKILL.zh-CN.md"
        if english.is_file():
            text = english.read_text(encoding="utf-8")
            if "## Script routing" not in text or "skill-script-routing.md" not in text:
                errors.append(f"{english.relative_to(root)}: missing script routing guidance")
        if chinese.is_file():
            text = chinese.read_text(encoding="utf-8")
            if "## 脚本路由" not in text or "skill-script-routing.zh-CN.md" not in text:
                errors.append(f"{chinese.relative_to(root)}: missing Chinese script routing guidance")
    return errors


def validate_skills(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    skill_roots: list[Path] = []
    package = json.loads((root / "package.json").read_text())
    for relative in package["pi"]["skills"]:
        skill_roots.extend(path.parent for path in (root / relative).rglob("SKILL.md"))
    seen_names: dict[str, Path] = {}
    for skill_root in sorted(skill_roots):
        if (skill_root / "SKILL.md").is_file():
            try:
                frontmatter_name = _frontmatter(skill_root / "SKILL.md").get("name")
            except ValueError as error:
                errors.append(str(error))
                continue
            if frontmatter_name in seen_names:
                errors.append(f"duplicate Skill name {frontmatter_name}: {seen_names[frontmatter_name].relative_to(root)} and {skill_root.relative_to(root)}")
                continue
            seen_names[frontmatter_name] = skill_root
        english = skill_root / "SKILL.md"
        chinese = skill_root / "SKILL.zh-CN.md"
        if not english.is_file() or not chinese.is_file():
            errors.append(f"{skill_root.relative_to(root)}: bilingual SKILL.md entrypoints are required")
            continue
        try:
            en_fields = _frontmatter(english)
            zh_fields = _frontmatter(chinese)
        except ValueError as error:
            errors.append(str(error))
            continue
        if en_fields["name"] != skill_root.name or zh_fields["name"] != skill_root.name:
            errors.append(f"{skill_root.relative_to(root)}: frontmatter name must match directory")
        description = en_fields["description"]
        if not 20 <= len(description) <= 240:
            errors.append(f"{english.relative_to(root)}: description must be 20-240 characters")
        if zh_fields["description"].strip() == "":
            errors.append(f"{chinese.relative_to(root)}: description must not be empty")

        en_text = english.read_text(encoding="utf-8")
        zh_text = chinese.read_text(encoding="utf-8")
        if len(en_text.splitlines()) > 100 or len(zh_text.splitlines()) > 100:
            errors.append(f"{skill_root.relative_to(root)}: entrypoint exceeds 100 lines; move detail to references")
        for forbidden in FORBIDDEN_PUBLIC_NAMES:
            if forbidden in en_text or forbidden in zh_text:
                errors.append(f"{skill_root.relative_to(root)}: retired public tool name {forbidden}")

        references = sorted((skill_root / "references").glob("*.md")) if (skill_root / "references").is_dir() else []
        english_refs = [path for path in references if not path.name.endswith(".zh-CN.md")]
        chinese_refs = [path for path in references if path.name.endswith(".zh-CN.md")]
        expected_zh = {f"{path.stem}.zh-CN.md" for path in english_refs}
        if {path.name for path in chinese_refs} != expected_zh:
            errors.append(f"{skill_root.relative_to(root)}: every English reference needs one .zh-CN.md pair")
        en_reachable = _reachable_references(english, skill_root)
        zh_reachable = _reachable_references(chinese, skill_root)
        for path in english_refs:
            translated = path.with_name(f"{path.stem}.zh-CN.md")
            if path.resolve() not in en_reachable:
                errors.append(f"{english.relative_to(root)}: reference is not routed: {path.name}")
            if translated.resolve() not in zh_reachable:
                errors.append(f"{chinese.relative_to(root)}: reference is not routed: {translated.name}")
        for path in references:
            lines = path.read_text(encoding="utf-8").splitlines()
            if len(lines) > 100:
                heading = "## 内容" if path.name.endswith(".zh-CN.md") else "## Contents"
                if heading not in lines:
                    errors.append(f"{path.relative_to(root)}: long reference needs {heading}")
            errors.extend(_check_links(path, path.read_text(encoding="utf-8")))
        errors.extend(_check_links(english, en_text))
        errors.extend(_check_links(chinese, zh_text))
    errors.extend(_check_script_routing(root, skill_roots))
    return errors


def main() -> int:
    errors = validate_skills()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    count = sum(1 for relative in json.loads((ROOT / "package.json").read_text())["pi"]["skills"] for path in (ROOT / relative).rglob("SKILL.md"))
    print(f"skill contract check passed: {count} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
