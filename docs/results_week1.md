# 第一周运行结果（2026-09-14）

环境：Windows 11，Python 3.12.10。内核与模拟器脚本版本为 commit `2f5f1a0`，本次运行未改动这些文件。`results/` 与 `scenarios/out/` 被 git 忽略，任何人可用下面的命令重新生成。

## 1. 内核测试

```bash
python tests/test_kernel.py
```

16 个测试全部通过，`failed: 0`。

## 2. 官方模拟器复现

```bash
python harness/simulate.py
python harness/simulate.py --shock
```

三个官方 baseline 与项目书草图数字完全一致。

| 策略 | 场景 | 平均天数 | P90 天数 | 迟交率 | 缺陷率 | 成本 | 最大份额 |
|---|---|---|---|---|---|---|---|
| random | 正常 | 21.5 | 45.6 | 34% | 4% | 111,780 | 23% |
| greedy_biggest | 正常 | 49.0 | 80.6 | 84% | 4% | 108,430 | 70% |
| cheapest | 正常 | 105.1 | 192.9 | 93% | 8% | 85,960 | 70% |
| random | shock | 23.4 | 48.4 | 39% | 4% | 111,780 | 23% |
| greedy_biggest | shock | 51.0 | 81.2 | 87% | 4% | 108,430 | 70% |
| cheapest | shock | 103.9 | 190.0 | 92% | 5% | 85,960 | 70% |

## 3. 我们的分配器与十行启发式（seed 5105）

```bash
python harness/run_baselines.py
python harness/run_baselines.py --shock
```

| 策略 | 正常：迟交率 | 正常：P90 | 正常：缺陷率 | 正常：成本 | 正常：最大份额 | shock：迟交率 | shock：P90 |
|---|---|---|---|---|---|---|---|
| earliest_finish（十行启发式） | 2% | 13.7 | 5% | 115,640 | 26% | 2% | 15.4 |
| earliest_finish+rework | 2% | 13.7 | 6% | 115,360 | 25% | 2% | 15.4 |
| cfg:lateness | 2% | 13.7 | 6% | 115,360 | 25% | 2% | 15.4 |
| cfg:defects | 28% | 34.6 | 4% | 110,325 | 43% | 30% | 35.6 |
| cfg:fairness | 5% | 25.4 | 5% | 112,945 | 20% | 16% | 31.5 |
| cfg:hybrid | 16% | 31.8 | 4% | 108,410 | 37% | 19% | 32.4 |
| cfg:cost | 2% | 27.8 | 4% | 100,775 | 38% | 8% | 28.6 |

shock 场景下 lateness 配置只有 2 批迟交，SteadyHands 与 Nimble Needle 各 1 批。

## 4. 多 seed（seed 5105、1、2、3、4、5，无 shock）

```bash
python harness/run_seeds.py --seeds 5105 1 2 3 4 5
```

| 策略 | 迟交率 最小 | 平均 | 最大 | P90 最小 | 平均 | 最大 |
|---|---|---|---|---|---|---|
| random | 33.3% | 35.0% | 40.0% | 45.6 | 49.1 | 58.8 |
| greedy_biggest | 84.2% | 85.0% | 86.7% | 80.6 | 84.0 | 86.3 |
| cheapest | 91.7% | 92.0% | 93.3% | 192.9 | 197.7 | 201.5 |
| earliest_finish | 1.7% | 2.0% | 2.5% | 13.6 | 14.7 | 16.0 |
| cfg:lateness | 1.7% | 2.0% | 2.5% | 13.7 | 14.5 | 16.0 |
| cfg:defects | 28.3% | 30.0% | 32.5% | 33.6 | 34.8 | 36.4 |
| cfg:fairness | 5.0% | 10.1% | 13.3% | 25.4 | 27.3 | 29.1 |
| cfg:hybrid | 15.8% | 17.8% | 19.2% | 31.5 | 32.4 | 33.6 |
| cfg:cost | 2.5% | 5.5% | 8.3% | 27.1 | 28.1 | 28.9 |

## 5. 压力场景：交期压缩到 7 到 14 天（seed 5105）

```bash
python scenarios/make_scenario.py scenarios/due_7_14.json
python scenarios/run_scenario.py scenarios/out/due_7_14 --seeds 5105
```

| 策略 | 迟交率 | P90 | 缺陷率 | 成本 | 最大份额 |
|---|---|---|---|---|---|
| random | 67% | 45.6 | 4% | 111,780 | 23% |
| greedy_biggest | 96% | 80.6 | 4% | 108,430 | 70% |
| cheapest | 98% | 192.9 | 8% | 85,960 | 70% |
| earliest_finish | 22% | 13.7 | 5% | 115,640 | 26% |
| cfg:lateness | 23% | 13.7 | 6% | 115,360 | 25% |
| cfg:defects | 50% | 21.5 | 3% | 108,465 | 41% |
| cfg:fairness | 24% | 15.0 | 3% | 112,130 | 19% |
| cfg:hybrid | 27% | 18.0 | 3% | 111,390 | 35% |
| cfg:cost | 31% | 15.6 | 5% | 105,890 | 33% |

## 6. 标准答案数字

```bash
python eval/compute_gold_facts.py
python eval/compute_gold_facts.py --ban-scope request
```

按协议重放的推荐与之前 PowerShell 手工重放完全一致：只有 R09、R12、R25 三条写入账本；R21 在 QuickStitch 禁令下没有按时方案。若禁令只对 R12 生效，R17、R21、R22、R25、R28、R30 的推荐改为 QuickStitch，其中 R21 可以按时。

## 发现

1. **官方 baseline 可复现。** 项目书第 4.4 节的数字从"初步实验"改为"事实"。
2. **lateness 配置与十行启发式打平。** 在官方数据、shock 和 6 个 seed 上迟交率都是 2.0% 左右。这正是 Spec 预告的情况，报告里照实写。
3. **压力场景出现区分度，但启发式仍领先 1 个百分点。** 交期压到 7 到 14 天后，random 迟交率从 34% 升到 67%，lateness 配置为 23%。
4. **目标之间有真实权衡。** defects 配置把缺陷率从 6% 降到 4%，代价是迟交率升到 28%。当前 defects 权重过于激进，下一步要做敏感性分析。
5. **"按期里最便宜"值得作为 hybrid 候选。** cfg:cost 在 seed 5105 上迟交率同为 2%，成本低 13%，但 6 个 seed 平均迟交 5.5%，P90 翻倍。
6. **fairness 最均衡但 shock 下最脆弱。** 正常场景最大份额 20%、迟交 5%；shock 下迟交升到 16%。

## 尚未验证

- GPT-5 nano 调用（需要团队确认后花费不到 0.01 美元跑 3 条）。
- 项目书中 protect_acc 与 min_defect_on_time 两个草图策略。
- `run_baselines.py` 写入 CSV 的 commit 字段显示 `no-git`，原因是运行时 git 不在该进程的 PATH 中；在组员电脑上正常安装 git 后会显示 commit。
