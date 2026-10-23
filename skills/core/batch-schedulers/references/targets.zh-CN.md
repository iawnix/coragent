# 平台与调度入口

平台选择、软件环境、存储和多平台计划统一见[execution-platforms](../../execution-platforms/SKILL.zh-CN.md)。

在所选平台的 `schedulers.<entry>` 下设置 `executor`、`handler` 和 `handler_environment`。
handler argv 使用提交端实际的 Python 与脚本路径。PBS／Torque／Slurm 示例中的
`/opt/coragent` 只是示例安装根目录；随附脚本位于其下的
`current/agent/skills/core/batch-schedulers/scripts/`。本机平台从已安装 Skill 的实际路径
定位脚本；SSH 平台则在远端提交主机安装独立 handler，配置远端绝对路径和 Python。
控制端的 `CORAGENT_PACKAGE_ROOT` 不代表远端路径。
