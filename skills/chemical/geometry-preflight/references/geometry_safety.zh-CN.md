# 几何预检合同

独立执行器接收一个 `chemical-geometry-safety-input/1` JSON 对象，返回
`chemical-geometry-safety/1` JSON 报告。硬检查范围是有限笛卡尔坐标、元素数与坐标数一致、
原子核塌陷，以及显式反应原子对之外的严重短接触。它不从坐标推断键，不确立分子身份，
也不认证过渡态。元素和所有上下文必须使用相同的原子顺序。

`bonded_pairs` 和 `reaction_pairs` 使用从零开始的原子索引。反应原子对可以比正常键更长或更短，
但仍不能低于绝对塌陷下限。非反应非键接触使用元素相关的共价半径比例检查。反应中心非平衡警告
对许多有效 TS 候选都是预期结果。

从分子图提供 `bonded_pairs`；省略表示连接关系未知，空列表表示明确没有键。已知非成键 H–H
距离小于 1.20 Å 时拒绝；H₂ 成键对和声明的反应原子对按其各自语境检查。连接未知时，小于
0.70 Å 的接触被拒绝，0.70–1.20 Å 的接触产生需要核对连接关系的警告。

可选 `fragment_groups` 对全部零起始原子索引分组，用于识别片段间接触。
可选 `reference_coordinates` 按同一原子顺序提供参考坐标，用于报告非反应键长度变化。
变化超过 0.20 Å 与参考长度 20% 中较大者时给出诊断警告；无参考时，键长超出共价半径和的
0.65–1.6 倍时给出警告。选择或细化反应姿态时结合这些具体距离判断。

同时提供 `bonded_pairs` 和 `reference_coordinates` 时，也会比较所给成键图上的键角。
变化绝对值超过 30° 时产生 `bond_angle_change` 警告，`checks.bond_angles` 为 `warning`。
其中 `angles` 的每项记录三个原子索引、`angle_degrees`、`reference_angle_degrees`、
`delta_degrees`，以及相邻键中声明的 `reaction_pairs`。反应键上的角度变化也会记录，
以免遗漏将原先弯曲片段拉直的情况。这些变化只产生诊断警告，不导致硬拒绝；是否符合预期
由反应上下文决定。未提供成键图或参考结构时，`checks.bond_angles` 为 `not_assessed`。
保持不变的线性片段通过该比较，线性本身不是几何错误。

必填字段为 `schema_version`、`elements` 和 `coordinates`（每个元素对应三个数的笛卡尔坐标，
单位为 Å）。`profile` 默认为 `general`，也可选 `reaction_seed`、`ts_candidate` 或 `path_image`。
可选 `clash_scale` 覆盖非反应短接触的默认半径乘数（依次为 0.75、0.72、0.70 和 0.72），
必须介于 0.1 和 1.5 之间，不改变核塌陷检查。不要为了消除无法解释的短接触而降低此参数。

例如，有意形成的 C–C 原子对可使用：

```json
{
  "schema_version": "chemical-geometry-safety-input/1",
  "elements": ["C", "C"],
  "coordinates": [[0, 0, 0], [1.8, 0, 0]],
  "bonded_pairs": [],
  "reaction_pairs": [[0, 1]],
  "profile": "ts_candidate"
}
```

按 [Skill](../SKILL.zh-CN.md) 的示例，通过准备器的 `--input input=<path>` 角色传入此文件。
运行器的 `--input` 和 `--output` 由准备器管理，不要在 `--` 后重复传递。
准备后的请求不是几何报告。通过 `job_start` 提交，完成后读取 `results/result.json`。
`unsafe` 报告也是成功执行诊断的结果，不能据此原样提交候选计算。

报告包含总体 `verdict`（`safe` 或 `unsafe`）、`hard_failures`、`warnings`、`checks` 中的分项状态、
原子数，以及已评估时的最小原子对距离。`not_assessed` 是分项状态，不是独立执行器的总体结论。
保留报告及其对应的确切候选坐标；修改几何后旧报告失效。`safe` 仅表示通过已覆盖的硬检查，
继续计算前仍须审查警告和化学合理性。

原始 XYZ 或 GJF/COM 输入使用 [Gaussian](../../gaussian/SKILL.zh-CN.md) 中对应的注册执行器。
显式输入执行器 `chemical.gaussian-input@1` 在请求准备时以及启动前，使用共享几何函数
检查 Cartesian 块。仅使用检查点的 `Geom=AllCheck`
无法从输入文本筛查坐标。通用 Bash 执行不会调用这些检查。路径合同也使用同一几何函数
检查端点和每个 NEB image。
