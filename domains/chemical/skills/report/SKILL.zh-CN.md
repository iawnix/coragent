---
name: report
description: 根据结构、计算、验证证据、能量数据、图形和结论组装可追溯研究报告。
---

# 研究报告

[English version](SKILL.md)

## 脚本路由

按 executor ID 使用[脚本路由地图](../../../../docs/skill-script-routing.zh-CN.md#report)选择入口、CLI、输入和主要输出。地图是路由依据；`scripts/` 下的 helper 不是独立命令。不要通过读取源码发现调用方式，先读操作合同，只有合同未说明的选项才使用 executor 的 `--help`。

**入口：** `chemical.render@1` → `skills/report/scripts/render.py`；`chemical.trajectory@1` → `skills/report/scripts/research_job.py`；`chemical.research-report@1` → `skills/report/scripts/research_job.py`。

需要可读证据包时使用本 Skill。报告应回答研究问题，展示方法和来源记录，区分观察与解释，并显式呈现缺失或冲突证据。

## 报告流程

1. 收集 result JSON、CSV、几何、日志、验证记录和来源 digest；建立每行对应一个结构、候选、能量状态或路径帧的数据集。
2. 用 `scripts/build.py` 先生成证据表：

```bash
"$CORAGENT_PYTHON" <installed-report-skill>/scripts/build.py --result local=<workspace>/path/to/result.json --output-dir <workspace>/reports/comparison-v1
```

3. 用 `chemical.render@1` 渲染给定几何（`--style`、`--size`、`--charge`、`--multiplicity`），图注写明 Artifact 和电子态。
4. 根据收集数据绘制能量剖面、扫描切片、集合人口和轨迹；图或图注保留单位、标准态、温度、能隙和排除行。
5. 在证据旁写结论。TS 研究展示候选身份、虚频模式、IRC 端点和验证状态；能量研究展示 E/ZPE/H/G 标签及方法/条件；动力学展示 TST 假设、前体范围、浓度、守恒诊断和终止状态。
6. 将报告、图、数据和脚本注册为材料并在研究结论引用。插图 Markdown 包使用 `chemical.research-report@1`，固定视角 GIF/XYZ/CSV 路径产品使用 `chemical.trajectory@1`。

## 交付与审阅

默认可用带图片目录的 Markdown，也可导出 HTML、PDF 或用户指定格式。打开最终文档检查链接、坐标轴、图注、单位、表格和来源。邮件适配器只有在用户授权发送后使用，准备/检查/状态操作见 [报告邮件交付](references/report_email_delivery.zh-CN.md)。

能量数据集见[能量合同](../energetics/references/energy_execution.zh-CN.md)，轨迹和报告包见[研究工具](references/research_tools.zh-CN.md)与[插图报告](references/illustrated_report.zh-CN.md)。
