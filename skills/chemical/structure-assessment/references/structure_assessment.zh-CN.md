# 结构评估合同

执行器接收两个 JSON 文件。

`material.json` 必须是由 material-preparation Skill 产生的 `chemical-material/1` 对象。`context.json` 使用以下形式：

```json
{
  "schema_version": "chemical-structure-context/1",
  "role_hint": "ts_candidate",
  "reaction_center": ["atom_4", "atom_7"],
  "bond_changes": [
    {"atoms": ["atom_4", "atom_7"], "before": 0, "after": 1,
     "note": "proposed forming bond"}
  ],
  "reference_material": null,
  "notes": "A candidate for the proposed elementary step"
}
```

`role_hint` 可取 `unknown`、`reactant`、`product`、`intermediate`、`reactive_complex`、
`optimized_structure` 或 `ts_candidate`。它是声明的解释角色，不是计算结论。`reaction_center` 使用本地原子 ID。
`bond_changes` 的键级范围为 0 到 3，是待检验假设；存在分子图时，报告会检查 `before` 是否与图一致。可选的
`reference_material` 必须具有相同原子 ID、元素、同位素和顺序，用于比较几何。`notes` 只作为来源说明，不是证据。

结果状态为 `assessed`、`partial` 或 `inconclusive`，并分开记录：角色评估、结构摘要、几何观察（包括只记录数值、不判断正常性的局部角度）、反应中心、
参考结构比较、不确定性和建议的后续 Skill。

距离标签是相对于共价半径和的观察：`collapsed`、`compressed`、`normal_like` 或 `elongated`。它们不是过渡态
的正常性定义；拉长的成键对可以是有用候选观察，塌陷原子对则表示几何失败。片段散开使用保守的 8 Å 质心观察，
只是 warning，不代表化学不可能。

该 Skill 只处理结构证据，不从坐标推断键、不验证波函数、不认证 TS 或机理，也不规定研究顺序。
