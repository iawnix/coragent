# Platforms and scheduler entries

Platform selection, software environments, storage and multi-platform plans are defined in [execution-platforms](../../execution-platforms/SKILL.md).

Set `executor`, `handler` and `handler_environment` under the selected platform's
`schedulers.<entry>` configuration. Handler argv uses the submission host's actual Python
and script paths. `/opt/coragent` in the PBS/Torque/Slurm examples is an example installation
root; bundled scripts are under `current/agent/skills/core/batch-schedulers/scripts/`.
For a local platform, resolve the script from the installed Skill path. For SSH, install
the standalone handler on the remote submission host and configure its remote absolute
path and Python; the controller's `CORAGENT_PACKAGE_ROOT` does not identify a remote path.
