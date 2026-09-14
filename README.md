# SweaterCo 外协调度台 · DSS5105 Capstone Track 2

把群聊里的外发请求变成可审计的派单决策：解析请求，检查车间能不能做、接不接得下、允不允许接，按目标给出带交期估算的推荐，人确认后写入账本和审计记录；没有按时方案时说清楚晚几天和有哪些选项。

团队：屈妍玥 · 张锦若 · 吴杰 · 李岩 · 吴若晗 · 许佩瑶

> **状态：第一周（2026-09-14）。** 仓库内容由 Claude 起草。已在 Python 3.12 上跑通全部测试、官方模拟器、基线对比、压力场景和调度员界面，结果见 [`docs/results_week1.md`](docs/results_week1.md)。

## 打开调度员界面

```bash
python -m pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

浏览器会打开 http://localhost:8501 。点左侧 **Load morning inbox** 收到 4 月 1 日的 30 条群聊，然后逐条点开处理。**系统只推荐，确认按钮按下之前不会派出任何一单。** 页面说明和演示脚本见 [`docs/ui_guide.md`](docs/ui_guide.md)。

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
| `eval/compute_gold_facts.py` | 按协议重放 30 条请求的推荐与数字，写入标签文件所在目录；定稿前是 `eval/draft/`，独立分类前不要打开 |
| `llm/llm_client.py` | 规则回退解析器对 30 条请求的解析结果 |

### 端到端跑一遍早上的 30 条群聊

```bash
python desk/pipeline.py
python desk/pipeline.py --only R21
python desk/pipeline.py --llm
```

| 命令 | 作用 |
|---|---|
| `desk/pipeline.py` | 用规则解析器按时间顺序处理 30 条：解析 → 订单状态检查 → 判定派单、追问、拒绝或无法回答 → 内核算交期与排序 → 用工具输出生成解释并核查数字 → 派单请求自动确认后写账本。不联网、不花钱 |
| `--only R21` | 只看一条请求的完整决策和工具调用链 |
| `--llm` | 改用 GPT-5 nano 解析，需要 `.env`，会产生费用 |

输出写入 `eval/runs/<时间>/`，该目录被 git 忽略：`transcript.md` 是人能读的逐条记录，`decisions.jsonl` 是结构化决策，`audit.json` 是账本审计记录。如果 `eval/draft/` 里有标准答案草稿，运行结束会打印对照分数。**独立分类交齐之前不要看这些输出，里面有答案。**

**引用任何模拟器数字时，同时写出命令、seed 和 commit。** `run_baselines.py` 会把 commit 写进 CSV。

## LLM 账号、费用与密钥

语言层用 OpenAI 的 GPT-5 nano 从群聊里提取字段，其余一律由 `kernel/` 计算。不配置 LLM 时系统自动使用规则解析器，所有测试和模拟器实验都不需要密钥。

**账号。** 程序通过 OpenAI API 调用模型，需要在 [platform.openai.com](https://platform.openai.com) 注册账号、充值并生成 API key。ChatGPT 的订阅不包含 API 额度，不能给程序调用。建议由 LLM 基础设施负责人吴若晗注册团队账号并充值，给每位需要调用的组员各生成一把 key，便于单独吊销。

**模型。** 默认 `gpt-5-nano`，是 GPT-5 系列里最便宜的，足够完成字段提取。价格来自 OpenAI 官方价目表，2026-09-13 核对：

| 模型 | 输入 $/百万 token | 输出 $/百万 token |
|---|---|---|
| gpt-5-nano | 0.05 | 0.40 |
| gpt-5-mini | 0.25 | 2.00 |
| gpt-5 | 1.25 | 10.00 |

GPT-5 系列会先生成推理 token，按输出价计费。`DESK_LLM_REASONING_EFFORT` 默认设为 `low`，控制这部分开销。

**预算。** 下面是估算，按每次提取约 1,500 个输入 token、800 个输出 token 算，输出里含推理 token。真实花费以运行后打印的数字为准。

| 用量 | 估算花费 |
|---|---|
| 每条请求 | 约 0.0004 美元 |
| 30 条官方请求加 44 条留出集，跑一轮 | 约 0.03 美元 |
| 开发期反复跑一百轮 | 约 3 美元 |

建议在 OpenAI 后台给项目设 **每月 10 美元的支出上限**，程序里再用 `DESK_LLM_BUDGET_USD` 做单次运行的保险。

**密钥放哪里。** 只放在本机的 `.env` 文件里，这个文件已被 `.gitignore` 排除。

```bash
cp .env.example .env
```

Windows PowerShell 用：

```bash
Copy-Item .env.example .env
```

然后编辑 `.env`，把 `OPENAI_API_KEY` 换成自己的 key。验证：

```bash
python llm/llm_client.py --llm --limit 3
```

输出末尾会显示本次调用次数和花费。key 一旦出现在聊天、issue、截图或 commit 里，立即到控制台吊销并重新生成。

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
