# 科学执行与运维

[English](SCIENTIFIC_CAPABILITIES_OPERATIONS.md)

`skills/chemical/execution.json` 声明随包的便捷执行入口和验证器；Skill 说明方法选择、科学限制和解释。Research Memory 记录原始要求、研究问题与结果，新增执行入口不需要添加方法专用研究字段。

这些入口不是 workflow 或能力白名单。Agent 可以准备原生命令或任务脚本，使用通用 Job 执行，
无需为每项计算登记新入口。目录字段与加载机制见 [Skill 与科学执行目录](EXTENSIONS.zh-CN.md)。

## 准备与执行

先读取相关 Skill，选择其预设入口、原生命令或任务脚本，以及安装目录 `etc/job.toml` 中的命名环境。预设入口提供后端键、固定脚本、纯 CLI 解析器、输入角色和输出。原生命令无需 Python 绑定；Python 脚本使用目标环境配置的解释器。

`"$CORAGENT_PYTHON" -m research_agent.application.executors --list` 返回简短的预设入口索引，可按 `--skill`、`--backend` 或 `--executor`/`--version` 筛选；`--details` 返回完整声明。加 `--config … --target …` 只显示绑定是否已配置，不探测软件。实际 runner 参数通过 `executors --executor <id> --version <版本> --help` 获取；只加载已固定的 CLI 解析器，不运行科学程序。

准备命令写入请求并返回 `request_file` 与 `request_sha256`，提交到 `job_start`；关联研究问题时提供 `node_id`。Runtime 检查文件和输入，固定所选 Node 归属与内容版本、`prepared_ref` 与提交意图。准备本身不派发 Job，也不证明科学结果。

任务临时 Python 方法用 `--script <文件.py> --backend <绑定>` 替代 executor/version，声明暂存依赖和收集输出。已登记证据通过 `--input-artifact <id或引用>` 传入，Runtime 核验实际暂存字节并保留来源。

丢失响应时复用原请求身份，通过 `job_status`、`job_reconcile` 和 `job_collect` 恢复；超时或客户端断连不代表允许重投。明确重复计算需要新身份和前驱、原因、预算声明。

## 执行目标检查

在会话中使用 `job_probe` 检查已配置 execution target。在安装的控制环境中，针对所选入口核验软件：

```bash
"$CORAGENT_PYTHON" -m research_agent.application.environment_check --config "$CORAGENT_JOB_CONFIG" --target <环境> --executor <id> --version <版本>
```

该命令只连接所选环境。没有预设入口的程序或任务脚本用 `--backend <绑定>` 替代 executor/version；可加 `--runtime native` 或 `--runtime python` 指定运行方式。`--details` 展示底层观测。缺少预设入口、缺少配置和实际检查失败分别返回 `recipe_not_found`、`not_configured` 和 `check_failed`；成功的 `verified` 只表示环境前置条件通过。

安装维护时省略 target 及入口/后端选择，可检查所有已配置目标（包括 SSH 目标）。`job_probe` 的目标基础设施观察与具体软件依赖核验是不同检查。

## 环境与进程归属

job.toml 所选后端提供程序、Python 绑定、激活脚本及资源默认值。结构/材料分析及通用科学检查执行器使用化学扩展的 `structure` 后端，注册的 validator 配方使用 `validation`；各目标须配置自己的依赖。执行入口与验证器可以声明 `requirements`，其中 `python` 和 `packages` 使用 Python 版本约束，`imports` 列出需要实际导入的模块；原生入口不声明 Python 依赖。

准备器在选定本地或 SSH 目标上核验解释器前缀、Conda 显式锁、pip 固定版本、安装回执、包清单，以及程序和激活文件摘要。请求身份包含这次观测；新提交时复查，真正运行时由暂存并固定摘要的检查程序再次复查。激活文件先检查再加载。变化导致拒绝执行，既有 Job 的查询和重试仍返回原身份。核验保证环境与记录一致，科学能力仍须由实际求解与验证证明。

安装回执记录 `inventory_sha256`。已安装环境通过 `scripts/install_job_environment.py --config … --target … --backend … --adopt` 实际核验后发布新回执；不得手工补写摘要。统一安装器准备所选 domain 环境，在受管控制环境中核验配置与依赖，并在切换版本前运行有时限的普通验收 Job。本机目标自动检查；远端仅在选择 `--job-profile TARGET:PROFILE` 或 `--verify-job-target TARGET` 时检查。报告区分目标验证、已测试后端和未验证目标，PubChem/OPSIN 外部可用性不阻止离线验收。`job_probe` 只表示目标基础设施状态。

应用提交的本地 Job 运行在独立 systemd 用户临时服务中，Host 重启不会连带终止它们。任务只接收最小环境和显式变量，资源请求通过 CPUQuota/MemoryMax 实施。Runtime 在 Job 内或配置的 scratch_root 下创建专属 scratch；显式环境值可引用 `{scratch}`。临时单元移除后，回执仍保留在工作区。

资源默认值只在准备或提交边界合并一次，顺序为目标、后端、显式请求；已准备入口的资源固定后不能在提交时覆盖。Job 回执和执行指纹记录实际资源。`allowed_queues` 仅是权限范围，不能代替 `submission.queue`。本机直接进程不接受队列字段；本机连接的外部目标可以提交队列任务；Torque 将 cpus/memory_mb 转为 nodes/ppn 和 mem，PBS 使用 select（不能同时声明 select 和 cpus/memory_mb）。walltime 与程序 timeout_seconds 同时存在时取较短值。

外部 Job 使用配置的本机/SSH 连接和队列脚本，与本地共享最小进程环境、线程默认值和 scratch 规则；不继承登录 shell 的科学环境，需要的路径和激活脚本必须由绑定明确提供。每个远端目录带本地 Job 路径的摘要，不同工作区的同名 Job 不共享目录。已接受任务通过保存的请求身份和脚本的只读查询恢复，见[外部任务接入](EXTERNAL_JOBS.zh-CN.md)。

`command_timeout_seconds` 限制本机或 SSH 控制命令（默认 60 秒），`transfer_timeout_seconds` 单独限制每次 rsync（默认 3600 秒），二者都不是科学程序的执行时限。回收排除本地 spec、receipt、status 等控制文件，计算输出不能覆盖它们。求解器结束和输出完整收集仍是两个独立事实。

远端提交明确关闭调度器自动邮件和自动重跑，通知与重复计算由研究流程管理。`qdel` 成功仅登记取消请求；确认执行已结束后才记录 cancelled，查不到记录时保持 unknown。取消期间的连接故障仍为 unknown，程序先完成则保留实际退出结果。

## 证据与支持范围

Job 文件位于 `runs/jobs/<job_id>`。收集把声明文件登记为生产 Job 的 Artifact；显式 recursive 输出目录中的文件逐个保留来源。Agent 结合领域方法解释证据，在对应 Node 中记事并按需发布 Result。退出码为零或报告已生成不足以证明科学成功。

[当前能力清单](../skills/chemical/method-selection/references/capabilities.zh-CN.md)
列出可独立调用的执行器、后端和科学边界。随包模块覆盖：

- 名称/SMILES/XYZ 材料、映射候选、张量重排与构象比较。
- CF22D、xTB、Gaussian 计算，以及有界 CREST 构象集合和刚性片段复合物采样。
- [反应构象编辑](../skills/chemical/reactive-geometry/SKILL.zh-CN.md)：定向片段摆放、局部编辑和绑定证据的模式位移；先做几何筛选，再由独立求解器精修。
- xTB/Gaussian 弛豫扫描、QST2/QST3 准备、梯度与 ASE NEB v2 候选搜索。
- 通用驻点、模式与 IRC 检查，以及热化学、构象自由能与能量剖面。
- 多步路径检查、条件 TST、共同前体竞争分支与质量作用动力学网络。
- 有限范围的 Gaussian 指定自旋基态和单重 TD/TDA 计算、给定张量的态跟踪、不同自旋表面的局部交叉搜索与检查。

xTB 的便捷封装仍接受 `sp/opt/opt-sp`；有界扫描和 NEB 使用独立执行器。
频率和分子动力学使用原生命令与通用 Job，详见 [xTB Skill](../skills/chemical/xtb/SKILL.zh-CN.md)。
可选 `path` 环境 profile 绑定 `path_xtb` / `path_gaussian`，使用含 RDKit/NumPy、ASE、SciPy 的 path.lock；
不安装原生求解器，也不默认运行科学冒烟计算，见[环境配置](../skills/chemical/environments/README.zh-CN.md)。

NEB 统一使用 ASE 版本 2 接入 Gaussian/xTB calculator，旧 NumPy 实现已删除。QBICS 仍需明确核实外部命令或脚本；内置交叉搜索使用
Gaussian 与本地 NumPy 算法。态跟踪需要提供 AO 密度/重叠张量，尚未实现从 Gaussian
检查点自动提取。经典 TS/IRC 检查不认证跨态或激发态连续性。驻点、模式和端点证据使用[通用检查](../skills/chemical/validation/references/general_checks.zh-CN.md)。
局部诊断与搜索恢复指南分别见 material-preparation/method-selection。独立轨迹与报告 Job 包含分子图、数据表和能量曲线，做法与证据要求见[报告 Skill](../skills/chemical/chemical-report/SKILL.zh-CN.md)。

## 验证

用 `tools/test/runner.py` 选择源码、Native 与发行检查。真实求解器和远端验收使用隔离工作区及明确绑定。合成日志、解析势和确定性求解器替身验证合同、数值算法、解析与本地 Job 生命周期，不证明真实求解精度或自主机理发现。A–J 模块已通过确定性验收，真实求解器科学基准与真实模型研究验收尚未执行。

原生程序的前置探测只解析并固定所配置可执行文件的摘要，不运行求解器，也不证明许可、
收敛或科学结论成立。`environment_executable_missing` 表示所选命令无法执行；
`environment_activation_missing` 表示激活脚本缺失；`environment_dependency_missing`
表示要求的包或模块缺失；`environment_import_failed` 表示已有依赖导入初始化失败。
报告实际观测与所选目标：未配置绑定或没有预设入口不等于所有环境都未安装软件。
绑定或程序字节发生变化后须重新准备请求，不能继续派发旧准备命令。

## 扩展资源合同

已登记执行器、Python 脚本和验证器都支持 `submission={"resources": {"cpus": 12, "memory_mb": 16384}}`。
规则见[逐作业资源](EXTERNAL_JOBS.zh-CN.md#逐作业资源)。

执行声明可增加 `resource_contract`，路径必须在已哈希的 `resources` 闭包内。
它是仅依赖标准库的纯 Python 模块，提供三个函数：`defaults(descriptor)` 返回最终兜底值；
`requirements(descriptor, arguments, inputs)` 返回显式输入需求；
`prepare(descriptor, arguments, inputs, resources)` 返回 `(normalized_arguments, report)`。
arguments 仅包含转发给程序的参数，inputs 是角色到绝对源路径的映射。标准化必须确定、幂等；
矛盾时抛出可操作的 `ValueError`，不改写用户输入、不探测容量、不执行程序。
提交时依据已固定输入、最终资源和参数重新校验。没有该合同的执行器及任意脚本，其内部资源使用标为未验证。

`configuration_sha256` 固定配置默认值和软件绑定；`execution_binding.submission` 是本次最终申请，
根据 `submission_request` 重新计算，不要求等于配置默认值。最终资源也参与执行指纹。
运行时 `CORAGENT_JOB_CPUS`、`CORAGENT_JOB_MEMORY_MB` 提供最终申请；软件激活后再次设置线程默认值，
避免激活脚本恢复旧线程数。这些变量表示申请量，不是实测占用或节点容量。
