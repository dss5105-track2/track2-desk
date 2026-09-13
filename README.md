# SweaterCo 外协调度台 · DSS5105 Capstone Track 2

把群聊里的外发请求变成可审计的派单决策：解析请求，检查车间能不能做、接不接得下、允不允许接，按目标给出带交期估算的推荐，人确认后写入账本和审计记录；没有按时方案时说清楚晚几天和有哪些选项。

团队：屈妍玥 · 张锦若 · 吴杰 · 李岩 · 吴若晗 · 许佩瑶

> **状态：第一周（2026-09-13）。** 仓库内容由 Claude 在一台没有 Python 的机器上起草，**代码尚未运行过**。第一个任务是按下面的命令跑通测试，失败就开 issue。

## 快速开始

需要 Python 3.9 或更新版本，内核只用标准库。

```bash
python -m pip install -r requirements.txt
python tests/test_kernel.py
python harness/simulate.py
python harness/run_baselines.py
python harness/run_baselines.py --shock
python harness/run_seeds.py --seeds 5105 1 2 3 4 5
python eval/compute_gold_facts.py
python llm/llm_client.py
```

| 命令 | 期望结果 |
|---|---|
| `tests/test_kernel.py` | 全部 PASS，`failed: 0` |
| `harness/simulate.py` | 官方三个 baseline 表 |
| `harness/run_baselines.py` | 官方 baseline + 十行启发式 + 五个目标配置，写入 `results/` |
| `harness/run_seeds.py` | 每个策略迟交率与 P90 的最小、平均、最大值 |
| `eval/compute_gold_facts.py` | 按协议重放 30 条请求的推荐与数字，写入 `eval/gold_facts.csv` |
| `llm/llm_client.py` | 规则回退解析器对 30 条请求的解析结果 |

**引用任何模拟器数字时，同时写出命令、seed 和 commit。** `run_baselines.py` 会把 commit 写进 CSV。

## 目录

```
data/                官方数据，原样，永不修改
harness/             simulate.py 原样；run_baselines.py；run_seeds.py
kernel/              确定性内核，零 LLM
  register.py        车间登记册与资格三问
  orders.py          订单表与状态交叉检查
  estimator.py       交期估算（队列 + 加工 + 返工期望 + 运输）与拆单估算
  allocator.py       目标即配置的分配器；十行启发式
  ledger.py          队列账本与审计记录
language/            结构化请求 schema 与 30 条手工解析
llm/                 LLM 客户端接口与规则回退解析器
eval/                请求处理协议、标注指南、留出集矩阵、标准答案生成脚本
  draft/             标注草稿，全员独立分类前不要打开
scenarios/           压力场景（交期压缩、配件激增、指定车间停工）
ui/wireframes/       调度员界面线框
docs/                工具规格、架构、主目标备忘、行业入门
tests/               内核验收测试
```

## 设计约束

- LLM 不做算术。队列、估算、排序、成本全部来自 `kernel/`。
- 解释中的每个数字必须能对应某次工具调用的输出。
- 只有人确认后才写账本；拒绝、追问、无按时方案的请求不占用产能。
- 官方数据与模拟器不改；扩展场景的结果与官方结果分表报告。

详见 [`eval/protocol.md`](eval/protocol.md)、[`docs/tool_spec.md`](docs/tool_spec.md)、[`docs/architecture_v0.md`](docs/architecture_v0.md)、[`CONTRIBUTING.md`](CONTRIBUTING.md)。

## 第一周进度

见 [`docs/week1_status.md`](docs/week1_status.md)。
