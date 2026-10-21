# 执行目标选择

科学 Skill 只声明执行器、软件后端、资源和输入输出合同。它不能选择
`local`、`tri`、`slurm` 或其它执行目标。

任务层解析用户的执行要求，并把解析后的 target 固定在任务记录中：

- 用户明确说 TRI、本机 TRI 队列或 `tri`，选择 `scheduler = "tri"` 的 target。
- “本机（Tri 队列）”“local（TRI 队列）”和“TRI 队列”都要求 TRI，即使 handler 在本机运行。单独用“local”指定执行目的地时，表示直接本机执行（`scheduler="none"`、`location="controller"`）。
- 用户明确说 Slurm，选择 `scheduler = "slurm"` 的 target。
- 用户没有说明平台，使用安装配置中的 `execution.default_target`。
- 同一个 scheduler 有多个 target，或没有可匹配 target 时，停止并报告歧义；不能猜测，也不能退回直接本机执行。

任务内保存最终 target 名称，例如 `execution_target = "tri"`。后续准备、提交、状态查询和收集都必须沿用这个 target。修改安装配置的默认值不会改变已经开始的任务。

`transport = "local"` 只表示 CoRAgent 在当前主机调用外部 handler；它不表示计算进程直接在当前主机运行。是否经过队列由 target 的 `driver` 和 `scheduler` 决定：

| target 特征 | 含义 |
| --- | --- |
| `driver = "systemd"`, `scheduler = "none"` | 直接在控制主机执行 |
| `driver = "external"`, `scheduler = "tri"` | 通过 TRI 提交 |
| `driver = "external"`, `scheduler = "slurm"` | 通过 Slurm 提交 |

领域 Skill 中不要写 `--target`。任务内由运行时注入并继承已经固定的 target；没有活跃任务时执行器才使用安装配置中的 `execution.default_target`：

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors \
  --config "$CORAGENT_JOB_CONFIG" \
  --executor <selected-executor-id> --version <selected-version> \
  --input <role>=<input-path> \
  --output prepared/request.json
```

提交前必须检查 prepared request 的 target 与任务 target 相同。按所选调度器的[接入说明](../../batch-schedulers/SKILL.zh-CN.md)核实提交回执。

## 原文绑定、继承与纠错

`task_begin` 调用通用 Jobs 解析器，保存实际目标名、scheduler、location、路由摘要、选取版本和真实指令引文。没指定平台时省略 `execution_target`，控制器固定当时的默认目标；明确指定调度器时传入：

```json
{"execution_intent":{"source_submission_id":"24","source_text":"local（Tri队列）","scheduler":"tri"}}
```

引文必须精确存在于引用的实际用户提交中，选择肯定的执行指令，排除否定选项和历史引用。解析器进行配置匹配，不是通用自然语言解析器。它检查原文中已配置的 scheduler 与传入选择是否冲突；多个目标匹配时必须指定满足用户限制的具体 `execution_target`，或澄清缺失选择，不能退回默认目标。直接在控制机执行可指定 `scheduler="none"`、`location="controller"`。

运行时把活跃任务的选择通过 `CORAGENT_TASK_EXECUTION` 注入 bash；准备器自动继承，因此领域 Skill 不需要 `--target`。任务之外才使用配置默认目标。提交端独立校验可信任务目标和路由摘要，包括从文件加载的准备请求；修改 bash 环境不能绕过提交校验。

误登记原始目标时用 `task_update action=correct_execution`：传当前 `expected_revision`、原始明确指令的 `execution_intent`、必要时的正确 `execution_target` 和 `reason`。这不会改变目标/验收要求，也不授权迁移或取消已有 Jobs；保存新选择版本和审计记录，原有无关 blocker 继续保留。

用户新改目的地时用 `refine`，引用新的 `source_submission_ids` 并传选择。同名目标的实际路由变化会阻止准备和新提交，返回 `execution_target_changed`；核实变化后，凭新的用户指令通过 `refine` 重新固定。仅资源默认值变化不改变路由身份。已有 Jobs 保留原身份，应读取、协调和收集，不能仅为换目标而重提。
