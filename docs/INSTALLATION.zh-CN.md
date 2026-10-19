# 安装与配置

CoRAgent 采用一份主配置 `config.toml` 和相邻的 `credentials.json`。
新布局不兼容安装根下的旧 `etc/`、`var/`；不会自动搬迁或删除旧部署。

## 目录与归属

| 内容 | 默认位置 |
| --- | --- |
| 程序版本、Pi 和 Host 运行环境 | `~/soft/coragent/` |
| 主配置与凭据 | `~/.config/coragent/` |
| 安装记录、Host 状态、会话、日志、缓存 | `~/.local/state/coragent/` |
| 研究工作区与 Job 文件 | `~/DATA/coragent/workspaces/` |

通过 `paths.software_root`、`paths.state_root`、`paths.workspace_root` 配置三个根目录；
配置目录由 `--config` 指定的文件位置确定。根目录必须互相独立。
共享数据路径中的配置级别别名会统一解析；工作区内部的路径安全检查仍然保留。
安装记录会绑定软件根、配置文件和状态根，修改这些位置需要显式重新部署。

软件目录只保留程序、运行环境和不含凭据的安装定位记录 `installation.json`。
本机状态目录包含 `installation/`、`host/`、`pi/sessions/`、`logs/`、`cache/`。
`generated/` 及 `pi/agent/models.json` 是组件需要的生成文件，不能作为第二份配置修改。

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

## 安装、检查与更新

```sh
./install.sh --config /absolute/path/config.toml --dry-run
./install.sh --source local --config /absolute/path/config.toml
```

默认来源为 GitHub；`--source local` 使用本地检出，`--source package` 使用完整发布包。
无交互安装增加 `--non-interactive --yes`。`--dry-run` 不下载、安装或启动服务，且不输出凭据。

安装器准备 CoRAgent 自身的 Python/Pi 运行环境、生成服务并检查已配置的执行环境。
科学计算环境需独立准备，再在 `execution.targets.*.bindings` 中绑定。
`install_job_environment.py` 可用于显式准备版本化的计算环境；主安装不默认创建科学环境。

安装器不会隐式导入 `~/.pi/agent`。需要导入已有组件配置时，可以显式使用
`--import-config DIRECTORY`，或 `--agent-config-dir`、`--job-config`、`--name-resolver-config`。
导入内容会合并进主配置，来源文件不会成为后续运行的配置来源。

模型和通知设置修改后重启 Host 生效；服务范围、Web 地址等服务设置修改后，重新运行安装器应用。
同一安装的更新复用主配置，通过本地维护记录保护服务停止、版本切换与失败恢复。
激活前失败恢复原配置和版本；激活后失败保留新状态，重新运行安装器修复。

```sh
python3 scripts/app_layout_doctor.py --config /absolute/path/config.toml --json
```

## TRI 与共享计算环境

TRI 是独立集群基础设施。CoRAgent 的配置只描述如何连接与提交任务，不管理 TRI server/client、
节点注册、认证配置或集群数据库。TRI 服务与集群计算软件不随 CoRAgent 卸载。

fed1/fed2 共享软件时，在有写权限的节点安装一次，两个节点分别验证运行兼容性。
共享软件的缓存、临时文件应写到各节点本地。TRI 在线不代表所有计算后端都已准备好。
资源申请与具体节点选择使用现有外部 Job 接口，见 [EXTERNAL_JOBS.zh-CN.md](EXTERNAL_JOBS.zh-CN.md)。

研究 Job 的归档目录仍位于工作区 `runs/jobs/<job-id>/`。
外部目标可设置 `file_mode="shared"` 直接在该目录执行；默认仍为暂存传输。
共享检查和配置方式见 [外部任务](EXTERNAL_JOBS.zh-CN.md)。

## 卸载

```sh
./uninstall.sh --config /absolute/path/config.toml
```

默认移除应用程序及匹配的服务，保留配置、会话和研究工作区。
`--purge-config` 清理主配置、凭据和生成配置；`--purge-workspaces` 显式清理工作区与会话；
`--purge-runtime` 只清理有匹配归属记录的 CoRAgent 自身运行环境。
它不会清理独立计算环境或 TRI。卸载只删除选定配置文件，不递归删除其父目录中的其他文件。
卸载器的必要解析代码随安装保存，因此删除源码检出后仍可卸载。

## 测试

所有本机测试安装、环境、缓存、临时文件和证据必须位于项目的 `local_debug/`，使用本地确定性
模型与假凭据。测试结束后停止并删除测试服务。该目录不得进入 Git、发布包、外部缓存或附件。
