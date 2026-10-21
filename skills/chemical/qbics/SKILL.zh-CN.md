---
name: qbics
description: 在声明的 QBICS 安装环境中规划和执行交叉点研究，明确电子态、输入和证据。
---

# QBICS 交叉点研究

[English version](SKILL.md)

## 脚本路由

本 Skill 不提供注册执行脚本，使用下文说明的领域选择流程或通用 Job 接口。

研究同自旋交叉或其它由已安装 QBICS 程序支持的交叉点优化时使用。本 Skill 提供科学设置和 generic Job 交接；仓库目前没有专用 QBICS runner。

## 推荐流程

1. 明确两个电子态、自旋/电子特征、交叉坐标、几何输入、电荷、多重度、溶剂和预期输出。
2. 用版本/帮助输出检查选定环境的 QBICS 可执行文件，并阅读已安装程序文档。记录可执行文件 digest 和所需文件。
3. 按[方法选择的请求模式](../method-selection/references/request_preparation.zh-CN.md)准备 generic Job，声明脚本/后端、暂存输入、控制参数和收集输出。
4. 运行搜索，用声明的脚本解析原生证据，保留态能量、梯度、收敛和 seam/态特征诊断。
5. 若适用 distinct-spin Gaussian crossing 合同，用 `surface-crossing` 做检查；QBICS 专属判据按安装程序文档执行。

任务包装器可通过 generic `job_start` 的 `--script` 和 `--backend` 调用。研究记录保留命令、环境、输入、输出和解析器版本。仓库自带的 projected-gradient 实现在 [surface-crossing](../surface-crossing/SKILL.zh-CN.md)，是独立操作。
