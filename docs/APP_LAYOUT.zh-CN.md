# CoRAgent 安装布局

[English](APP_LAYOUT.md) | 简体中文

安装使用四个独立根目录。`config.toml` 指定软件、运行状态和工作区根目录；
配置文件自身的位置确定配置目录。实现依据为
`backend/src/research_agent/foundation/layout.py`。

| 根目录 | 默认路径 | 配置入口 |
| --- | --- | --- |
| 软件 | `~/soft/coragent/` | `paths.software_root` |
| 配置 | `~/.config/coragent/` | 安装参数 `--config`、运行时 `CORAGENT_CONFIG` |
| 运行状态 | `~/.local/state/coragent/` | `paths.state_root` |
| 研究工作区 | `~/DATA/coragent/workspaces/` | `paths.workspace_root` |

```text
<software_root>/
  coragent
  uninstall.sh
  installation.json          # 配置和状态根目录的定位记录
  current -> releases/<id>
  releases/<id>/             # 应用代码和随包 Skill
  runtimes/pi/<commit>/      # 固定 Pi 运行时
  runtimes/maintenance/      # 独立卸载和恢复程序
  host-envs/                 # Host Python 环境的默认存储目录

<configuration_directory>/
  config.toml               # 操作者维护的设置
  credentials.json          # 模型凭据和具名密钥

<state_root>/
  installation/             # 安装身份和环境回执
  host/                     # Host 身份、Link token、租约和后台健康状态
  pi/sessions/              # Pi durable SQLite 会话
  pi/agent/                 # Pi 设置和生成的模型定义
  generated/                # 生成的组件配置
  logs/
  cache/

<workspace_root>/<name>/
  workspace_manifest.json
  research/
  runs/jobs/
  operations/
  artifacts/
```

日常修改 `config.toml` 及相邻的 `credentials.json`。状态根下的
`generated/job.toml`、`generated/email.toml`、`generated/name-resolver.toml`
和 `pi/agent/models.json` 是生成的组件输入；直接编辑不会更新主配置，重新生成时会被覆盖。
运行命令通过 `CORAGENT_JOB_CONFIG` 等变量取得解析后的路径。

Host Python 基础环境和 wheel overlay 位于
`<env_root>/<installation-id>/{base,kernels}/<hash>`。
`runtime.env_root` 可指定专属存储目录；安装器也接受 `CORAGENT_HOST_ENV_ROOT`。
科学解释器和程序通过 `config.toml` 的 `execution.platforms.<platform>.schedulers.<entry>.bindings` 单独配置。

Socket 和进程锁使用按安装身份隔离的系统 runtime 目录。Pi 会话历史位于
`<state_root>/pi/sessions/<workspace-id>/<session-id>/session.sqlite`，
相邻 `meta.json` 保存元数据。研究文件保存在工作区，不随切换会话搬迁。

只读检查解析后的路径：

```bash
python3 -B scripts/app_layout_doctor.py --config /absolute/path/config.toml --json
```

当前布局 schema 为 `coragent-installation/3`。安装根下的旧 `etc/`、`var/`、
`.pi/` 和 `.agents/` 不会自动迁移；重新部署时应保留原有数据。
卸载选项和归属规则见[安装与运维](INSTALLATION.zh-CN.md)。
