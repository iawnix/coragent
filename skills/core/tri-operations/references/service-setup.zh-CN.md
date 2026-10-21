# 服务部署与维护

## 安装与拓扑

使用选定的 TRI 发行版本，或在源码中执行 `cargo build --locked --release --bins`。将 `CARGO_HOME` 和 `CARGO_TARGET_DIR` 设置到安装/构建区域，测试构建使用仓库私有测试目录。从同一次构建安装 `tri-server`、`tri-client` 和 `tri_*` 工具，保留旧程序及服务配置以便回退。

一个服务端管理队列数据库，每台参与计算的主机运行一个具有唯一节点名的客户端；单机同时运行两者。在服务端主机执行 CLI 诊断，或配置服务端 TCP 地址。多机任务需要一致的输入、输出和程序路径，通常使用共享文件系统。SQLite 数据库放在服务端本地磁盘。

## 显式配置环境

启动服务端前设置绝对路径。`TRI_DATA_DIR` 默认是 `./data`，`TRI_DB` 默认是 `TRI_DATA_DIR/tri.db`；显式设置可使服务重启与启动目录无关。

| 进程 | 配置项 |
| --- | --- |
| 服务端 | `TRI_SOCKET`、`TRI_SERVER_ADDR`、`TRI_DATA_DIR`、`TRI_DB`、`TRI_AUTH_TOKEN` |
| 计算客户端 | `TRI_SERVER_ADDR`、`TRI_AUTH_TOKEN`、`TRI_NODE`、`TRI_NODE_ADDRESS`、`TRI_NODE_CPUS`、`TRI_NODE_MEMORY`、`TRI_NODE_GPUS`、`TRI_NODE_SCRATCH` |
| CLI | 本机服务使用 `TRI_SOCKET`；TCP 使用 `TRI_SERVER_ADDR` 和 `TRI_AUTH_TOKEN` |

服务端和客户端分别使用服务所属用户可读的环境文件，权限设为 `0600`。Systemd `EnvironmentFile` 中填写实际绝对路径，不使用 shell 变量展开。服务端与 TCP 客户端配置相同的随机令牌。单机绑定回环地址；集群绑定私网地址，将 TCP 访问范围限制到参与主机。

按实际可供队列使用的容量设置 CPU、内存和 GPU，为其它应用预留资源。`TRI_NODE_SCRATCH` 指向可写的节点本地目录。GPU 客户端会发现设备路径，非标准设备用 `TRI_NODE_GPU_DEVICES` 指定。任务获得 CPU 集合、GPU 可见性/设备规则，以及申请内存时对应的 cgroup 内存限制。

## 服务定义

先通过 `systemctl --user list-unit-files 'tri*'` 和 `systemctl list-unit-files 'tri*'` 识别现有服务，按实际 system/user 类型检查和修改。即使 TRI 客户端本身是系统服务，计算任务也使用服务账户的 systemd **用户管理器**。

新建用户服务时，可将以下服务端模板放入目标用户的 systemd 单元目录。把 `/ABS/TRI_BIN` 替换为安装的程序目录，并先创建引用的环境文件：

```ini
[Unit]
Description=TRI queue server
[Service]
Type=simple
EnvironmentFile=%h/.config/tri/server.env
ExecStart=/ABS/TRI_BIN/tri-server
Restart=on-failure
RestartSec=2
UMask=0077
[Install]
WantedBy=default.target
```

创建对应的 `tri-client.service`，将相关两行分别改为 `client.env` 和 `tri-client`。每台主机使用各自的客户端配置。执行 `systemctl --user daemon-reload` 后先启动服务端，再启动客户端。需要用户服务长期运行时，在主机配置阶段为服务账户设置 login linger。通过 `tri_node --check` 检查计算主机的 cgroup v2、用户管理器及 cpuset/CPU/memory 控制器。

用户服务日志用 `journalctl --user -u "$TRI_UNIT" -n 100 --no-pager` 读取，系统服务使用对应的系统日志。服务名使用实际发现的单元名。

## 验收与资源调整

`tri_node --check` 通过后，选择共享的绝对路径诊断目录 `TRI_CHECK_DIR`，以及本次安装内唯一的新 `TRI_CHECK_ID`。创建目录后提交：

```bash
tri_sub --json --name ops-check --request-id "$TRI_CHECK_ID" \
  --chdir "$TRI_CHECK_DIR" --cpu 1 --mem 64M --timeout 30 \
  --output 'tri-%j.out' --error 'tri-%j.err' -- /bin/echo tri-ready
```

使用返回的任务 ID 检查状态和日志。验收结果应为 `done`、退出码零、输出中有 `tri-ready`，确认节点调度和输出可见性。调整可分配容量时，修改对应客户端的环境配置，在选定维护时段重启该客户端，再核对上报容量和已有任务的 attempt。请求超过任何节点可用容量的任务会继续等待。

开发测试将 socket、服务地址、数据库、数据、scratch、构建/缓存和证据路径配置到隔离测试环境。本仓库所有测试文件位于 `local_debug/`。使用独立连接地址和节点身份，检查任务单元退出后停止并删除测试服务。

## 升级、备份与 CoRAgent 接入

升级前记录活跃任务及 attempt。使用 SQLite backup API 获取一致备份，或停服务端后离线备份并保留 SQLite 附属文件状态。同时保存配置与程序版本。每次请求会检查协议兼容性，因此协调服务端与客户端升级。重启后检查节点注册、已有 attempt 和诊断任务。回退时核对旧程序与数据库的兼容性；恢复历史数据库前需要核对快照之后启动的任务。

CoRAgent Job 接入和逐节点软件验收见[批处理调度器](../../batch-schedulers/references/tri.zh-CN.md)。

## 历史保留

用户要求维护历史时，选择保留期限，先收集仍需使用的 Job 输出与回执。`tri_clean --json --older-than SECONDS` 删除较旧的终态记录，默认期限为 30 天。清理同时删除幂等回执，此后重试已清理请求可能生成新任务。保留窗口应覆盖工作流恢复和重试需求；`--all` 用于明确选定的全部终态历史删除。

取消时核对 `cancel_confirmed` 和 `completion_reason`。即使已有 `finished_at` 且租约为空，租约到期仍不能证明进程停止；等待完成确认期间，资源仍应视为占用。
