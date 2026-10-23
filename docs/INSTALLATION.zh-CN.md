# 安装与配置

CoRAgent 采用一份主配置 `config.toml` 和相邻的 `credentials.json`。
新布局不兼容安装根下的旧 `etc/`、`var/`；不会自动搬迁或删除旧部署。

## 目录与归属

| 内容 | 默认位置 |
| --- | --- |
| 程序版本、Pi 和 Host 运行环境 | `~/soft/coragent/` |
| 主配置与凭据 | `~/soft/coragent/config/` |
| 安装记录、Host 状态、会话、日志、缓存 | `~/soft/coragent/state/` |
| 研究工作区与 Job 文件 | `~/DATA/coragent/workspaces/` |

通过 `paths.software_root`、`paths.state_root`、`paths.workspace_root` 配置三个根目录；
配置目录由 `--config` 指定的文件位置确定。配置和状态可分别使用软件根下专用的 `config/`、`state/`，研究工作区必须独立。
共享数据路径中的配置级别别名会统一解析；工作区内部的路径安全检查仍然保留。
安装记录会绑定软件根、配置文件和状态根，修改这些位置需要显式重新部署。

默认软件目录包含程序、运行环境、`config/`、`state/`、`generated/`、`jobs/`、`backups/`，以及不含凭据的安装定位记录 `installation.json`。
若 `paths.state_root` 指向软件根之外，`generated/`、`jobs/`、`backups/` 位于该状态根下；
配置目录由所选 `--config` 路径决定。
本机状态目录包含 `installation/`、`host/`、`pi/sessions/`、`logs/`、`cache/`。
`generated/` 及 `pi/agent/models.json` 是组件需要的生成文件，不能作为第二份配置修改。
配置只沿一个方向流动：校验待安装设置，保存 `config.toml` 和 `credentials.json`，再生成组件输入。
安装器不会从生成文件反向推断用户设置。

## 准备配置

从 `config/config.example.toml` 和 `config/credentials.example.json` 开始，按实际用户修改绝对路径。
配置目录权限应为 0700，凭据文件必须为 0600。

主配置分为：

- `paths`：程序、本机状态、共享工作区位置。
- `service`、`web`：服务范围及 Web 监听设置。
- `models`：Pi 模型提供方定义。
- `execution`：默认执行目标、调度接入和计算环境绑定。
- `notifications.email`：通知邮箱设置。
- `name_resolver`、`remote_host`：可选的名称解析和 SSH 终端设置。

`execution` 使用 `config/job.execution.example.toml` 的目标格式，直接合并其 `[execution]` 表。
不要再套一层 `[execution.execution]`。

计算执行、邮件和在线名称解析均可不配置。此时仍可创建工作区、维护研究记录和运行研究任务，
安装器不会创建 Qrun 队列，也不会启用 PubChem/OPSIN。任务首次需要计算时再绑定平台与调度入口，
普通 shell 命令仍在本机执行。已有结构输入与本地分子图检查不要求在线名称解析服务。

启动时检查核心配置，并在 `generated/configuration-status.json` 中记录可选组件的配置错误。
使用对应操作时会明确报告该组件不可用，不会自动换用另一个服务。普通启动不探测 SMTP、SSH
或 HTTP 服务；安装时在激活前校验已配置组件，具体操作再检查所需的外部资源。

凭据文件的 `models` 对象保存 Pi 原生提供方认证，包括 OAuth 刷新结果。
`secrets` 对象保存命名字符串。主配置使用 `credential:名称` 引用，例如：

```toml
[notifications.email]
enabled = true
provider = "smtp"
preset = "custom"
host = "smtp.example.com"
port = 465
security = "ssl"
username = "research@example.com"
recipient = "research@example.com"
password = "credential:smtp_password"
```

也可引用外部 `password_file` 或 `password_env`。外部凭据不会因为卸载而被删除。
模型认证直接在同一份凭据文件内加锁更新，启动时不复制旧认证覆盖刷新结果。
模型的 `thinkingLevelMap` 中用 `false` 表示不支持的思考档位；生成 Pi 配置时会转换为其原生 `null`。

`password_env` 指运行中 Host 环境里的外部变量，安装器不会把其值保存到生成文件或凭据库。
生成的 systemd 单元使用 `PassEnvironment=变量名`。用户服务可通过
`systemctl --user set-environment 变量名=值` 等外部方式向用户管理器提供变量，随后重启
`coragent.service`；注入方式应避免让密码进入 shell 历史。只在 shell 中 export 不会更新
已运行的 systemd 管理器或 Host。需要由安装管理密码时，导入私有密码文件或交互输入，
其值统一保存在 credentials.json。

## 安装、检查与更新

```sh
./install.sh --config /absolute/path/config.toml --dry-run
./install.sh --source local --config /absolute/path/config.toml
```

默认来源为 GitHub；`--source local` 使用本地检出，`--source package` 使用完整发布包。
无交互安装增加 `--non-interactive --yes`。`--dry-run` 不下载、安装或启动服务，且不输出凭据。

安装器准备 CoRAgent 自身的 Python/Pi 运行环境、生成服务并检查已配置的执行环境。
科学计算环境独立准备后在 `execution.platforms.<platform>.bindings` 或入口覆盖中绑定。
主安装器不创建科学环境；平台与 Qrun 参数采用 `PLATFORM/ENTRY`，见
[计算平台](EXECUTION_PLATFORMS.zh-CN.md)。环境准备详见
[科学执行与运维](SCIENTIFIC_CAPABILITIES_OPERATIONS.zh-CN.md)。

安装器不会隐式导入 `~/.pi/agent`。需要导入已有组件配置时，可以显式使用
`--import-config DIRECTORY`，或 `--agent-config-dir`、`--job-config`、`--name-resolver-config`。
导入内容会合并进主配置，来源文件不会成为后续运行的配置来源。
显式导入的 SMTP 密码文件会进入私有凭据存储，主配置只保留凭据引用。
模型定义保存到 `config.toml`，提供方认证保存到 `credentials.json`；编辑生成文件不能覆盖它们。

需要在线化学名称查询时，显式使用 `--name-resolver-config` 导入，或配置 `[name_resolver]`。
再在 structure 后端的环境设置中显式绑定 `CORAGENT_NAME_RESOLVER_CONFIG`，路径必须能被所选平台读取。
本机设置不会自动变成远端路径，也不会自动启用外部服务。

模型和通知设置修改后重启 Host 生效；服务范围、Web 地址等服务设置修改后，重新运行安装器应用。
同一安装的更新复用主配置，通过本地维护记录保护服务停止、版本切换与失败恢复。
激活前失败恢复原配置和版本；激活后失败保留新状态，重新运行安装器修复。

```sh
python3 /absolute/coragent/current/agent/packaging/coragent_packaging/installer/app_layout_doctor.py \
  --config /absolute/path/config.toml --json
```

将 `/absolute/coragent` 替换为软件根。从源码检出运行时，使用相对于检出根的
`packaging/coragent_packaging/installer/app_layout_doctor.py`。

## TRI 与共享计算环境

TRI 是独立集群基础设施。CoRAgent 的配置只描述如何连接与提交任务，不管理 TRI server/client、
节点注册、认证配置或集群数据库。TRI 服务与集群计算软件不随 CoRAgent 卸载。

fed1/fed2 共享软件时，在有写权限的节点安装一次，两个节点分别验证运行兼容性。
共享软件的缓存、临时文件应写到各节点本地。TRI 在线不代表所有计算后端都已准备好。
资源申请与具体节点选择使用现有外部 Job 接口，见 [EXTERNAL_JOBS.zh-CN.md](EXTERNAL_JOBS.zh-CN.md)。

研究 Job 的归档目录仍位于工作区 `runs/jobs/<job-id>/`。
外部目标可设置 `file_mode="shared"` 直接在该目录执行；默认仍为暂存传输。
共享检查和配置方式见 [外部任务](EXTERNAL_JOBS.zh-CN.md)。

执行入口显式选择本机 Qrun 且使用默认 handler 后，主安装器可创建并管理该资源池；
没有执行配置就不会创建队列。SSH 队列通过 `--manage-qrun PLATFORM/ENTRY`
及状态目录、CPU、内存参数显式托管。多个本机目标共用资源池，代码升级要求先排空作业。
日常 CPU／内存预算调整使用 `qrun config` 在线完成，无需排空；升级时未明确传容量参数，
就保留在线调整后的预算。
配置示例及依赖见 [Qrun 安装与运维](QRUN.zh-CN.md)。

## 卸载

```sh
./uninstall.sh --config /absolute/path/config.toml
```

默认移除应用程序及匹配的服务，保留配置、会话和研究工作区。
`--purge-config` 清理主配置、凭据和生成配置；`--purge-workspaces` 显式清理工作区、会话与本机托管 Job 文件；
`--purge-runtime` 只清理有匹配归属记录的 CoRAgent 自身运行环境。
卸载会移除所属本机与 SSH Qrun 队列服务，默认保留队列历史与计算目录。
未完成作业会阻止卸载，除非传入 `--cancel-qrun-jobs`；`--purge-qrun-state`
可删除队列历史。`--purge-all` 包含历史清理，但不隐含取消作业。
它不会清理独立计算环境、独立管理的 Qrun 或 TRI。卸载只删除选定配置文件，不递归删除其父目录中的其他文件。
卸载器的必要解析代码随安装保存，因此删除源码检出后仍可卸载。

## 测试

所有本机测试安装、环境、缓存、临时文件和证据必须位于项目的 `local_debug/`，使用本地确定性
模型与假凭据。测试结束后停止并删除测试服务。该目录不得进入 Git、发布包、外部缓存或附件。

备份默认保留，只有 `--purge-backups` 或 `--purge-all` 才会删除。安装根内存在备份或受管队列时，`--remove-root` 还要求对应的备份、队列清理选项。普通卸载保留目录内的配置、任务数据和队列历史。
