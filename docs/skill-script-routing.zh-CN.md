# Skill 脚本路由

这是注册 Skill 的脚本地图，来源是 `domains/chemical/execution.json`。executor
ID 和版本是公开接口；通过标准 executor 和 Job 生命周期调用操作。`entry` 是
实现入口，`cli` 是参数解析器。入口导入的文件属于内部 helper，不是独立命令。

不要为了发现注册操作的调用方式而读取脚本源码。输入合同看对应 Skill 的
reference，本地图用于确定入口，只有合同未说明的选项才用 executor 的
`--help`。直接运行脚本仅用于本地诊断或开发，研究 Job 仍必须走
`job_start`、提交和收集流程。

下列路径相对于 `domains/chemical/`。完整操作表见英文版；这里保留各 Skill 的
路由原则和容易误用的入口。

## cf22d

## xtb

## gaussian

## material-preparation

## reactive-geometry

## candidate-generation

## validation

## crest

## energetics

## reaction-investigation

## surface-crossing

## geometry-preflight

## structure-assessment

## report

## method-selection

## qbics

## 后端与准备

- `cf22d`：`chemical.cf22d@1` → `skills/cf22d/scripts/run.py`；环境诊断 → `doctor.py`。
- `xtb`：`chemical.xtb@1` → `skills/xtb/scripts/run.py`；扫描、梯度、NEB 由 `candidate-generation` 负责。
- `gaussian`：XYZ/显式输入 → `skills/gaussian/scripts/run.py`；电子态与跟踪 → `electronic.py`。
- `material-preparation`：解析/种子/反应 → `reaction/prepare.py`；material → `materials/material.py`；几何分析 → `geometry/analysis.py`；局部诊断 → `diagnostics/diagnostics_job.py`。
- `crest`：CREST 运行 → `crest_run.py`；集合导入/筛选/复合物采样 → `ensemble.py`。
- `energetics`：所有注册能量操作 → `energetics/scripts/energy.py`。

## 几何、候选和验证

- `reactive-geometry`：位点 → `reactive_sites.py`；姿态 → `reactive_pose.py`；显式编辑 → `reactive_geometry.py`。
- `candidate-generation`：路径准备 → `path/prepare_path.py`；QST/扫描/恢复 → `search/search.py` 或 `search/recovery.py`；Gaussian 梯度 → `backends/gaussian_path.py`；NEB → `neb/ase_search.py`。
- `validation`：IRC 输入 → `irc_preparation.py`；驻点/模式/IRC/Gaussian 证据 → `evidence_check.py`。
- `reaction-investigation`：路径审查 → `pathway_job.py`。
- `surface-crossing`：搜索和检查 → `crossing.py`。
- `geometry-preflight`：安全检查 → `run.py`。
- `structure-assessment`：结构认知 → `run.py`。

每个入口的 executor ID、CLI、输入和主要输出见[英文完整脚本表](skill-script-routing.md)。
操作 ID 决定子操作；不要直接调用同目录的 helper 源码。

## 没有仓库内 executor 的 Skill

`method-selection` 和 `qbics` 有意没有仓库自带脚本，应按文档走 generic Job
或已安装程序。generic Job 必须明确声明脚本、后端、输入、输出和解析器。

## 非化学运维脚本

以下路径相对于仓库根目录。

### batch-schedulers

- `batch-schedulers`：`skills/batch-schedulers/scripts/batch.py`，首参数为 `pbs`、`torque` 或 `slurm`，stdin/stdout 为 JSON，支持 `probe`、`submit`、`status`、`cancel`、`recover`。
- `batch-schedulers`：`skills/batch-schedulers/scripts/tri.py`，不传调度器参数，stdin/stdout 为 external-Job JSON，支持同样的五个操作。

### email

- `email`：`skills/email/scripts/email_cli.py`，子命令 `check`、`prepare`、`send`，仅授权后发送。
### tri-operations

无仓库内脚本；使用已安装的 TRI 服务端/客户端和系统服务命令。Job handler 归属 `batch-schedulers`。

## research-memory

无仓库内脚本，使用 runtime research-memory 工具。

## research-workflow

无仓库内脚本，使用 runtime task 和 Job 工具。
