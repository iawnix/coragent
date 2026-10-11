# 安装配置

仓库只提供可公开的示例；示例使用虚构域名、模型名和凭据，不包含实际账号信息。

| 示例 | 本机私有文件 | 用途 |
| --- | --- | --- |
| `models.example.json` | `models.json` | 模型服务地址与模型定义 |
| `auth.example.json` | `auth.json` | 模型 API 凭据；provider 名称须与 models.json 一致 |
| `job.example.toml` | `job.toml` | 本地和远程计算环境绑定 |
| `name-resolver.example.toml` | `name-resolver.toml` | PubChem、OPSIN 的启用、超时与缓存设置 |
| `email.example.toml` | `email.toml` | 可选邮件通知设置 |

已有真实文件时不要用示例覆盖它们。上述私有文件，以及 `smtp-password` 和
`secrets/`，已从 Git、npm、release 和 Docker 构建上下文排除。不要使用 `git add -f`
提交它们，也不要把凭据放进示例文件。实际凭据文件使用 `0600` 权限。

`./install.sh --config-dir /绝对路径/config` 从同一目录读取可选的
`job.toml`、`models.json`、`auth.json`、`email.toml` 和 `name-resolver.toml`。邮件配置采用
`[notifications.email]`，格式见示例；`password_file` 的相对路径以该配置目录为基准。
授权码单独存放在 `0600` 文件中，安装器会复制到 `<install>/etc/secrets/smtp-password`。
也可以用 `password_env` 引用环境变量。安装后的邮件配置位于 `<install>/etc/email.toml`。
缺少邮件配置或 `enabled = false` 时，不传入邮件设置：新安装不启用邮件，更新保留已有设置。

交互和非交互安装共用同一套参数、配置校验及默认值。命令行参数优先于
`CORAGENT_*` 环境默认值和配置目录。可以用 `--agent-config-dir`、`--job-config`
或 `--email-*` 参数单独指定输入。Phone/Relay 默认不启用，需要时显式使用
`--with-link-relay --link-url https://你的域名`。

从当前本地源码预览安装计划（不会读取或输出模型凭据内容，不会复制授权码或启动服务）：

```bash
./install.sh --source local --config-dir "$PWD/config" \
  --install-root "$HOME/CoRAgent" --non-interactive --yes --dry-run
```

去掉 `--dry-run` 后执行安装。本地源码有未提交修改时，需先提交，或在本机验证时显式
添加 `--allow-dirty`。真实配置文件保持忽略状态，不随源码提交或发布。

新安装没有提供 `job.toml` 时，会自动准备本地 structure/validation 环境并运行结构
验收 Job。已有配置保持原绑定；增加环境使用 `--job-profile local:pyscf` 等选项。
远端先配置 SSH、调度器和队列，再指定 `--job-profile remote:pyscf`、
`--job-software-root remote=/目标/专用目录` 与 `--job-conda remote=/目标/bin/conda`。
这些路径在目标机器上解释。名称服务配置与 Python 环境绑定分开，PubChem/OPSIN
网络不可用不会阻止离线安装验收。完整说明见 `docs/INSTALLATION.zh-CN.md`。

## 自动运行恢复

Host/Worker 启动环境可配置以下执行恢复参数，修改后重启 Host 生效：

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `CORAGENT_TASK_RECOVERY_MAX_RETRIES` | `2` | Pi 请求级重试最终失败后，最多追加的恢复运行次数；`0` 关闭自动恢复 |
| `CORAGENT_TASK_RECOVERY_BASE_DELAY_MS` | `30000` | 首次恢复等待毫秒数，必须大于零 |
| `CORAGENT_TASK_RECOVERY_MAX_DELAY_MS` | `300000` | 指数退避的最大等待，不能小于初始等待 |

次数和截止时间持久保存，重启不会重新获得重试额度。该额度只约束执行恢复，不判断科学任务是否无解；Pi 自身的请求级重试仍由其 retry 设置控制。只自动恢复可识别的临时模型服务错误；配置、权限、请求钩子、中止和未知故障保留为执行待处理。Monitor 展示原因、阶段和重试时间；排除故障后用 `/monitor task resume <task-id>`，或以新用户指令配合 `task_update refine` 恢复。询问故障不会重置额度或自动解除待处理状态。最终回复恢复只允许读取证据和输出回复，不能重发邮件或重做计算。无新证据轮数仅供模型重新评估方法，不触发固定三轮停止。
