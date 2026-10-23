# CoRAgent documentation

[English](README.md) | [简体中文](README.zh-CN.md)

Start with installation and terminal usage. These guides describe the current
source and versioned contracts. Completed implementation plans and one-off test
reports are retained in Git history rather than used as operating instructions.

## Use and operate

| Need | Read |
| --- | --- |
| Install, configure, upgrade and uninstall | [Installation](INSTALLATION.md), [Directory layout](APP_LAYOUT.md) |
| Terminal, sessions and Monitor | [Terminal](TERMINAL.md) |
| Phone connection and client contract | [CoRAgent Link](CORAGENT_LINK.md), [Phone protocol (Chinese)](PHONE_PROTOCOL.zh-CN.md) |
| Models, credentials and context capacity | [Model configuration](MODEL_COMPATIBILITY.md) |
| Scientific methods and supported scope | [Scientific operations](SCIENTIFIC_CAPABILITIES_OPERATIONS.md), [Capability inventory](../skills/chemical/method-selection/references/capabilities.md) |
| Scheduler handlers and Job resources | [External Jobs](EXTERNAL_JOBS.md), [Qrun local/SSH queues](QRUN.md) |
| Skills and their operation entrypoints | [Skill catalog](../skills/README.md), [Script index](skill-script-routing.md) |

## Understand and maintain

| Need | Read |
| --- | --- |
| Runtime and storage ownership | [Architecture](ARCHITECTURE.md), [Execution boundaries](ARCHITECTURE_BOUNDARIES.md) |
| Task Controller, Job Manager and input admission | [Task and Job architecture (Chinese)](TASK_JOB_ARCHITECTURE.zh-CN.md) |
| Research Memory selection, injection and synthesis | [Research context (Chinese)](RESEARCH_CONTEXT.zh-CN.md) |
| Node granularity, planning and correction | [Research planning (Chinese)](RESEARCH_PLANNING.zh-CN.md) |
| Evidence, materials and provenance | [Research Memory Skill](../skills/core/research-memory/SKILL.md), [Evidence architecture (Chinese)](RESEARCH_EVIDENCE_ARCHITECTURE.zh-CN.md), [Artifact Store](ARTIFACT_PROVIDERS.md) |
| Skill loading, prompt assembly and execution declarations | [Skills and execution catalog](EXTENSIONS.md) |
| Maintain, test and package | [Maintainer Guide](MAINTAINER_GUIDE.md), [Contributing](../CONTRIBUTING.md), [Test runner](../tools/test/README.md) |
| Scientific regression scope | [Scientific regressions (Chinese)](SCIENTIFIC_REGRESSIONS.zh-CN.md) |
| Pinned Pi integration | [Pi runtime patches](PI_RUNTIME_PATCHES.md) |

[Named execution platforms and multi-cluster execution](EXECUTION_PLATFORMS.md) explains the
platform/entry configuration, shared environments, storage, task plans and installer entry selection.

## Proposals

[Pi 1.3.0 migration audit (Chinese)](PI_1_3_MIGRATION.zh-CN.md) is a dated upstream
comparison and unimplemented proposal. The current runtime remains pinned to Pi
1.1.0 in `packaging/coragent_packaging/pi/source.json`; the audit is not an upgrade procedure.

## Documentation maintenance

Use code, configuration examples and schemas to verify commands and paths.
Update paired English/Chinese guides together. Keep one current explanation of
each contract and link to it; remove superseded plans once their useful guidance
has been incorporated. Label unimplemented proposals explicitly. Test results
apply only to the tested source or release artifact, not every later version.

Project source uses [Apache License 2.0](../LICENSE); third-party dependencies,
Pi source and assets retain their own notices.

- [TRI deployment and maintenance](TRI_OPERATIONS.md)
