# IRC 输入准备

IRC 输入准备属于过渡态验证：从已验证的鞍点检查点准备正向和反向输入，不生成候选，也不认证鞍点。

所选 ts.gjf 通过 `chemical.gaussian-input@1` 执行，收集 `results/ts.chk`，保持相同的
方法、基组、电荷/自旋和资源，并使用 `--validation saddle`。检查原始输出和振动模式
证据后，使用收集的检查点准备 IRC：

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.path-irc --version 1 --input spec=<branch-spec.json> --input checkpoint=<collected-ts.chk> --input-artifact <branch-spec-ref> --input-artifact <checkpoint-ref> --output <work_dir>/irc-request.json -- --max-points 80
```

IRC 准备接收相同的显式变换契约，不依赖端点几何策略。它保留检查点原始字节及摘要，
用 CalcFC 和 Geom=AllCheck 写 forward.gjf/reverse.gjf，在检查点几何上重新计算 Hessian，
不解析二进制检查点，也不复用存储的 Hessian。必须核对检查点的原子顺序、方法、电荷/自旋
和生产证据。先提交并收集输入准备 Job，
再按 Gaussian Skill 分别运行两方向输入，暂存 ts.chk，使用 `--validation irc`。

已有 chemical.reaction_mapping、chemical.gaussian_saddle、chemical.gaussian_irc_connectivity
路径验证器和 chemical.diels_alder_path 验收 profile 仍使用 DA 专用契约。通用准备成功
不会扩展这些检查的适用范围。应针对声明键变化、模式和端点，用适当分析检查收集的输出，
明确记录尚未评估的条件。
