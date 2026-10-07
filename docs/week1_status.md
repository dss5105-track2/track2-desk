# 第一周状态（2026-09-13）

Claude 已起草第一周所有能以文件形式完成的产出。以下"必须由人做"的部分无法代劳，周五验收会前完成。

## 按成员

| 成员 | 已起草 | 必须由本人完成 | 验收标准 |
|---|---|---|---|
| 吴杰 | `kernel/` 五个模块；`tests/test_kernel.py` 16 个测试；`harness/run_baselines.py` | 在本机跑通测试与模拟器；核对三个 baseline 数字是否与手册草图一致；commit 并把命令、seed、commit 写进结果 | 测试 `failed: 0`；`run_baselines.py` 出表；0 次不合格分配 |
| 李岩 | `language/schema.md`；`language/requests_gold.json` 30 条手工解析；`llm/llm_client.py` 规则回退解析器 | 逐条复核 30 条 JSON；运行 `python llm/llm_client.py`，统计规则解析器与手工解析不一致的条目 | 每条 JSON 可回溯到原文；不一致列表开 issue |
| 张锦若 | `eval/protocol.md`；`eval/labeling_guide.md`；`eval/heldout_matrix.md`；`eval/compute_gold_facts.py`；`eval/draft/gold_labels_draft.csv` | 收齐六人独立分类并统计分歧；与李岩双人标注；填写裁定记录；定稿 `eval/gold_labels.csv` | 有分歧率和 kappa；每条最终标签有依据 |
| 吴若晗 | `llm/llm_client.py` 接口；`harness/run_seeds.py`；`scenarios/` 两个配置与生成、运行脚本 | 选定模型与预算，申请 API key 放进环境变量；跑 `run_seeds.py` 至少 6 个 seed；跑一次 `due_7_14` 场景 | 迟交率区间表；回退路径在无 key 时被触发 |
| 屈妍玥 | `docs/objective_memo.md` 初稿 | 补真实调研来源（标题、机构、年份、链接、具体数字）；周五 3 分钟讲两方案 | 至少 3 条可点开的来源；全组投票定主目标 |
| 许佩瑶 | `ui/wireframes/wireframes.md` 三张文本线框；`docs/architecture_v0.md` Mermaid 架构图 | 把线框转为纸面或 Figma；与李岩走一遍 R12；架构图重画为 PNG | 周五能回答线框文档末尾三个问题 |
| 全员 | — | 读 Primer、数据字典、30 条请求、simulate.py；**独立**分类 30 条（不打开 `eval/draft/`）；建公开 GitHub 仓库并各自 commit | 六份分类表；每人至少一次 commit |

## 起草过程中发现的三处更正

项目书 v1.0 与第一周文档中有三处数字需要更正，已在项目书 v1.1 修改：

1. **R12 示例。** R09 派单后 Nimble Needle 做 R12 需 9.49 天，按模拟器的 round() 仍承诺 4 月 10 日，并未超过余量。答案仍从 Nimble Needle 变为 GiantWeave，原因是 GiantWeave 的 9.06 天变为最早。
2. **R21 类别。** R12 占用 GiantWeave 后，R21 在 GiantWeave 晚 1 天；加上 QuickStitch 本周禁令，R21 没有按时方案。若禁令只对 R12 生效，QuickStitch 可按时。这是标注时必须讨论的争议。
3. **ORD-114 最后活动日。** 是 3 月 30 日，不是 4 月 1 日。

## 未完成

- **GPT-5 nano 调用尚未验证。** 规则解析器已跑通；模型调用需要团队确认后运行 `python llm/llm_client.py --llm --limit 3`。
- **`probe_overload` 工具**只写了规格，阶段 1 实现。

## 09-14 更新

- GitHub 公开仓库已建：github.com/dss5105-track2/track2-desk。
- 已在 Python 3.12 上跑通：16 个测试全部通过；官方 baseline 完全复现；lateness 配置与十行启发式打平；标准答案数字与手工重放一致。详见 `docs/results_week1.md`。
- 规则解析器修了两处：R10 被误判为引用 R05；有订单号或信息类问题时不再误报缺失字段。
- 吴杰的验收项"测试通过、baseline 出表、0 次不合格分配"已满足，仍需本人在自己电脑上复跑一次确认。
- `desk/pipeline.py` 端到端流程 v0 已跑通：30 条请求从群聊到解释到账本全部处理完，结果见 `docs/results_week1.md` 第 7 节。这提前完成了原计划阶段 3 的"一条请求从聊天到审计记录可演示"。
- 李岩接手语言层时，路由规则在 `desk/pipeline.py` 的 `Desk.route()`，解析器在 `llm/llm_client.py`。
