# 轨迹与图文研究报告 Job

[English](research_tools.md)

`chemical.trajectory@1`、`chemical.research-report@1` 是独立 structure Job，使用
structure.lock 已有的 RDKit/NumPy、Matplotlib 和 Pillow；不启动求解器，不依赖 TS 流程。
一个 input JSON 准备请求，以返回请求/摘要和 node_id 提交，再递归收集 results：

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.trajectory --version 1 --input input=<work_dir>/trajectory.json --input-artifact <input-ref> --output <work_dir>/trajectory-request.json
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.research-report --version 1 --input input=<work_dir>/report.json --input-artifact <input-ref> --output <work_dir>/report-request.json
```

替换真实绝对路径和 Artifact 引用，原始日志/材料也应注册为 Artifact。数据摘要不等于
核验科学来源。规范化 JSON 摘要为 sha256: 加上 UTF-8 JSON 的 SHA-256，序列化使用
`json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`，不同于文件字节摘要。

## 轨迹输入

chemical-trajectory-input/1 要求 material（chemical-material/1，1–128 个有坐标
原子）和 kind：irc/neb/optimization/mode/other。以下来源严格三选一：

- frames：2–512 帧，每帧有 coordinates（atom × xyz，Å），可有 energy_hartree
  （有限数/null）。顺序严格等于 material 原子序。要求 source_sha256；有任何能量时
  还需共同 model 对象。保留原帧顺序，本工具不直接解析原始求解器日志。
- neb_result：终止的 chemical-neb-result/2，原子 ID 匹配且有完整配对的
  images/energies；kind=neb。继承模型、摘要及 converged/step_limit/failed 状态，显式
  摘要/模型须一致。未完成的 pending images 不能替代已求值配对。
- mode：包含 vectors（atom × xyz）、representation=cartesian_displacement、
  frequency_cm1，加上 source_sha256 与 kind=mode。质量加权模式须先正确转换。
  自动生成 33 帧正弦示意，amplitude_angstrom 默认 .15、正数且 <=1，表示最大逐原子
  位移。没有计算能量，不表示动力学或 IRC。

可选 coordinates 遵循[局部诊断合同](../../material-preparation/references/local_diagnostics.zh-CN.md)；
display_bonds 最多 512 对显式 ID，不推断键。animation_frames 为 2–128、默认64，
只采样 GIF 并记录原帧索引；JSON/XYZ/CSV 保留全部帧。fps 为 1–30、默认8。
相机、轴和比例全程固定，不逐帧对齐。

输出 result.json、trajectory.xyz、trajectory.gif、profile.csv、profile.svg/png。
能量、距离和角度分面板，缺失能量保留空缺，不插值或补零。相对能以可用帧最低能为零点，
不是活化能；帧索引不是时间，模式动画不能证明 IRC 完整或反应连通。

## 研究报告输入

chemical-research-report-input/1 要求非空 title、question、assessment 和显式
limitations 列表（可为空）。assessment 是**作者解释**，不是程序自动认证结论。
evidence 为 1–128 条，每条含唯一 id、label、带 schema_version 的 result、与 result
规范化内容匹配的 source_sha256，以及可选 artifact_id。artifact_id 是来源标注，
不自动查询 Artifact 存储。result.json 完整保留原结果、报告状态及限制，不提升为新认证。

可选的 `research_review` 字段接受完整的 `research-review/1` 投影。脚本会在排除
`review_digest` 字段后重新计算摘要，并把 Review 的 ID、状态摘要、来源引用、矛盾和
不确定性保存在 `result.json` 与 `report.md` 中。Review 不能替代必需的原始
Result/Artifact 证据，也不能认证过渡态。

可选 structures 最多12条 {label, material, display_bonds}，每条 1–128 个有坐标
原子。可选 trajectory 是上述完整输入。可选 energy_profile 必须是
chemical-energy-profile-input/1，由[能量模块](../../energetics/references/energy_execution.zh-CN.md)
重算并核对物理量、模型、条件和计量守恒；任意能量表不能直接变成能垒图。
缺失所请求的量会拒绝；证据缺失时省略 energy_profile 并在报告说明。

输出 report.md、result.json、可选 structures.png、energy.json/CSV/SVG/PNG 和
trajectory/ 文件。能量图是离散状态能级，不虚构连续势能面。Markdown 嵌入真实产物，
标注作者结论、未完整路径和缺失数据；HTML/PDF 导出及科学解释是后续独立任务。
交付前检查图像、单位、链接、证据覆盖和局限，再注册报告及其材料。
