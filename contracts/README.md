# Framework contracts

[English](README.md) | [简体中文](README.zh-CN.md)

This directory owns machine interfaces shared by the framework, execution runtime
and clients. Skill instructions describe when and how to use those interfaces;
they do not duplicate parameter schemas or define client transport protocols.

| Owner | Contract | Consumers |
| --- | --- | --- |
| Application and tools | [commands](commands/README.md) | Python dispatch, Node tools, generated types and response checks |
| Task monitoring | [Monitor API](monitor/README.md) | Host, terminal and browser clients |
| Execution events | [Job Monitor records](monitor/jobs/README.md) | Python outbox and Host event notifications |
| Connectivity | [Link](link/README.md) | Host, Relay and device clients |
| Workspace materials | [Files](files/README.md) | Host file access and phone previews |
| Research views | [Web](coragent-web/README.md) | Research provider and the independent Web component |

Directory names describe responsibilities. `schema_version`, protocol names and
schema IDs identify the current wire/storage formats.

`tools/generate_contracts.py` generates application command catalogs, Node types,
the packaged Python Monitor schemas and command test fixtures. Edit the sources
here, regenerate, and run `--check`. Test fixtures live in `tests/fixtures/contracts/`
and are excluded from product packages. Runtime copies are generated, not separately
maintained definitions.

Domain-specific input and output formats belong beside the Skill that produces
or consumes them. Put usage guidance in its `references/` and machine schemas in
its `schemas/` when scripts actually validate them. Task workflow instructions
belong to `skills/core/research-workflow/`; generic task and Job schemas remain
framework-owned. Every contract needs an identified reader or writer and validation
against actual requests, records or responses.
