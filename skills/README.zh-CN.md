# Skill 目录与加载语言

[English](README.md) | [简体中文](README.zh-CN.md)

**默认加载英文 `SKILL.md`。** Pi 先发现名称、描述和文件路径，Agent 按需读取正文与参考资料。
`SKILL.zh-CN.md` 是中文对照，不会根据对话语言自动切换，也不会作为重复 Skill 自动加载。
需要时 Agent 可以显式读取中文文件；回答和报告可以按用户要求使用中文。
实现与资源维护见[Skill 与科学执行目录](../docs/EXTENSIONS.zh-CN.md)。

Skill 提供科学操作、方法/后端适配和研究协调方面的指导，可以调用随附脚本，
也可以编写任务所需的输入和分析脚本。目录明确区分这些职责；脚本按分类目录提供唯一的执行器路径；`execution.json` 的便捷入口不构成能力上限。

`core/` 收纳不依赖领域的工作流、记录、队列管理与邮件 Skill；`chemical/` 收纳化学方法、软件适配、验证和报告，以及配套执行目录、环境清单和共享代码。两组使用同一发现机制。Core 不依赖化学组；化学 Skill 使用通用工作流和任务选定的执行目标。

### 科学操作与证据

这些 Skill 描述要处理的科学对象或问题，可以委托下面的方法/后端适配器执行。

| Skill | 用途 |
| --- | --- |
| [candidate-generation](chemical/candidate-generation/SKILL.zh-CN.md) | 根据映射端点、键变化、约束和结构证据，为过渡态与反应路径搜索生成候选几何。 |
| [material-preparation](chemical/material-preparation/SKILL.zh-CN.md) | 准备分子材料和显式反应定义，为后续科学操作保留身份、电子态与来源。 |
| [energetics](chemical/energetics/SKILL.zh-CN.md) | 评估电子能、ZPE 与热校正、自由能和反应能、势垒、构象集合、TST 速率、竞争分支、质量作用网络及能量剖面。 |
| [reaction-investigation](chemical/reaction-investigation/SKILL.zh-CN.md) | 使用明确的物种身份、原子映射、基元步骤、替代假设与可证伪条件形成、比较并修订反应机理假设。 |
| [reactive-geometry](chemical/reactive-geometry/SKILL.zh-CN.md) | 根据明确的反应中心证据构造和修订反应取向及局部候选几何。 |
| [structure-assessment](chemical/structure-assessment/SKILL.zh-CN.md) | 在不认证机理或过渡态的前提下，根据证据整理材料和反应候选的结构描述。 |
| [surface-crossing](chemical/surface-crossing/SKILL.zh-CN.md) | 用 Gaussian 搜索不同自旋表面的局部交叉候选，并检查能隙、投影梯度和可选交叉缝曲率。 |
| [validation](chemical/validation/SKILL.zh-CN.md) | 根据鞍点、目标振动模式、结构、电子态、立体化学和双向 IRC 连通性证据验证过渡态候选。 |

### 方法与后端适配

这些 Skill 描述计算方法或软件绑定，为上面的科学操作提供配方和解析边界，
本身不定义研究问题。

| Skill | 用途 |
| --- | --- |
| [cf22d](chemical/cf22d/SKILL.zh-CN.md) | 将已声明的 CF22D/PySCF 输入、执行和解析证据适配到注册的 pyscf 绑定。 |
| [crest](chemical/crest/SKILL.zh-CN.md) | 为有界构象和刚性片段集合操作适配 CREST，保留身份、证据与来源。 |
| [gaussian](chemical/gaussian/SKILL.zh-CN.md) | 为已声明的量子化学计算适配 Gaussian，并说明其输入和解析边界。 |
| [qbics](chemical/qbics/SKILL.zh-CN.md) | 判断 QBICS 的适用性，核实已安装命令、输入与验证需求后执行有界研究 Job。 |
| [xtb](chemical/xtb/SKILL.zh-CN.md) | 将已声明的 xTB 输入、原生绑定和解析证据适配到注册后端，不选择科学操作。 |

### 协调、控制与交付

这些 Skill 跨科学操作和后端适配器协调选择，执行通用输入控制，并交付持久证据与结果呈现。

| Skill | 用途 |
| --- | --- |
| [email](core/email/SKILL.zh-CN.md) | 提供通用 SMTP 邮件运输和持久、幂等的发送回执。 |
| [geometry-preflight](chemical/geometry-preflight/SKILL.zh-CN.md) | 在电子结构 Job 前执行跨任务坐标安全检查，同时允许声明的反应中心处于非平衡几何。 |
| [method-selection](chemical/method-selection/SKILL.zh-CN.md) | 协调科学方法、后端与命名计算环境，包括已指定方法时的执行准备。 |
| [chemical-report](chemical/chemical-report/SKILL.zh-CN.md) | 根据研究证据编写图文报告，包含分子结构、能量曲线、数据表、方法、结论和可追溯的来源。 |
| [research-memory](core/research-memory/SKILL.zh-CN.md) | 用持久问题 Node、显式关系、执行观察与不可变 Result 恢复和推进研究。 |
| [research-workflow](core/research-workflow/SKILL.zh-CN.md) | 在 Pi 原生循环中协调研究问题、领域 Skill、持久 Job、材料和有依据的 Result。 |

### 计算基础设施

| Skill | 用途 |
| --- | --- |
| [batch-schedulers](core/batch-schedulers/SKILL.zh-CN.md) | 配置 Qrun、TRI、PBS、Torque、Slurm 执行目标，查询资源并诊断作业状态、日志和恢复。 |

- [execution-platforms](core/execution-platforms/SKILL.zh-CN.md): 命名平台、调度入口、环境、存储与多平台计划。
