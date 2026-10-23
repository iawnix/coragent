# CoRAgent 安装布局

[English](APP_LAYOUT.md) | 简体中文

默认将配置和可变数据集中在软件根目录下，研究工作区单独保存。`config.toml` 指定软件、运行状态和工作区根目录；
配置文件自身的位置确定配置目录。实现依据为
`backend/src/research_agent/bootstrap/layout.py`。

| 根目录 | 默认路径 | 配置入口 |
| --- | --- | --- |
| 软件 | `~/soft/coragent/` | `paths.software_root` |
| 配置 | `~/soft/coragent/config/` | 安装参数 `--config`、运行时 `CORAGENT_CONFIG` |
| 运行状态 | `~/soft/coragent/state/` | `paths.state_root` |
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
  config/                   # 下述配置目录
  state/                    # 下述状态根目录
  generated/                # 生成的组件配置
  jobs/                     # 本机 Qrun 计算文件
  backups/                  # 保留的安装备份

<configuration_directory>/
  config.toml               # 操作者维护的设置
  credentials.json          # 模型凭据和具名密钥

<state_root>/
  installation/             # 安装身份和环境回执
  host/                     # Host 身份、Link token、租约和后台健康状态
  pi/sessions/              # Pi durable SQLite 会话
  pi/agent/                 # Pi 设置和生成的模型定义
  qrun/                     # 本机队列数据库和服务状态
  logs/
  cache/

<workspace_root>/<name>/
  workspace_manifest.json
  research/
  runs/jobs/
  operations/
  artifacts/
```

上图是默认布局。如果 `paths.state_root` 位于软件根之外，`generated/`、`jobs/`、
`backups/` 会改为该状态根下的目录。通过下方 layout doctor 获取实际解析路径。
平台的执行文件仍由其 `storage.work_root` 决定，`jobs/` 不会隐式替换该设置。

日常修改 `config.toml` 及相邻的 `credentials.json`。数据根下的
`generated/job.toml`、`generated/email.toml`、`generated/name-resolver.toml`
和状态根下的 `pi/agent/models.json` 是生成的组件输入；直接编辑不会更新主配置，重新生成时会被覆盖。
运行命令通过 `CORAGENT_JOB_CONFIG` 等变量取得解析后的路径。
显式导入组件设置时先更新主配置与凭据，不建立第二个配置来源。可选邮件和计算配置的错误会记录在
`generated/configuration-status.json`，不包含秘密值；该文件是诊断输出，不是配置入口。
缺少可选设置不会阻止研究启动，也不会创建队列或名称解析服务。

Host Python 基础环境和 wheel overlay 位于
`<env_root>/{base,kernels}/<hash>`。
存储目录的安装归属单独记录在 `<env_root>/installation-owner.json`。
`runtime.env_root` 可指定专属存储目录；安装器也接受 `CORAGENT_HOST_ENV_ROOT`。
科学解释器和程序通过 `config.toml` 的 `execution.platforms.<platform>.schedulers.<entry>.bindings` 单独配置。

Socket 和进程锁使用按安装身份隔离的系统 runtime 目录。Pi 会话历史位于
`<state_root>/pi/sessions/<workspace-id>/<session-id>/session.sqlite`，
相邻 `meta.json` 保存元数据。研究文件保存在工作区，不随切换会话搬迁。

从源码检出根或安装包根 `<software_root>/current/agent` 运行，
只读检查解析后的路径：

```bash
python3 -B packaging/coragent_packaging/installer/app_layout_doctor.py --config /absolute/path/config.toml --json
```

当前布局 schema 为 `coragent-installation/3`。安装根下的旧 `etc/`、`var/`、
`.pi/` 和 `.agents/` 不会自动迁移；重新部署时应保留原有数据。
卸载选项和归属规则见[安装与运维](INSTALLATION.zh-CN.md)。

已有的分离式配置和状态目录仍受支持，不会自动搬迁。仅允许软件根下专用的 `config/`、`state/` 与软件根嵌套，数据不得放进 `releases/` 或 `current`。迁移必须先停止服务，并同步更新归属记录、队列配置和服务路径。
