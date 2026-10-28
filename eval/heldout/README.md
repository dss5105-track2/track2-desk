# 留出集（held-out inbox）

43 条组员手写的群消息（2026-04-01 早上，单独一本账），答案在 `gold_labels.csv`。冻结信息见 `FROZEN.txt`。

## 怎么来的

- 写手：吴杰、吴若晗、屈妍玥、张锦若，每人按一张骨架表写 11 条，共 44 条。写手不改提示词、解析器和 `llm/` 代码。
- 标注：每条由两位没写它的组员独立标注，不用 AI。
- 定稿：两位标注人和骨架预期三者一致的 32 条直接定稿；不一致的 12 条按全组已定的标注规则定稿，其中 H24 照消息原文判为 clarify，H43 因原文和骨架意思对不上而剔除。冻结前的分歧率 12 / 44 = 27.3%。
- 备注：H36 和官方 R11 几乎相同，报告里单独标注；H41 两位标注人都漏看了前面 H04 的长期约束。

## 第一次运行（李岩、许佩瑶）

被测系统版本是 `3e9f2ee`（2026-10-07 合并），早于这些消息的写作时间。这次冻结只新增本目录，没有改动任何系统代码，所以在冻结后的 `main` 上运行等同于在 `3e9f2ee` 上运行。

在仓库根目录：

```bash
python eval/run_language_eval.py --inbox eval/heldout/requests.txt --labels eval/heldout/gold_labels.csv --parses "" --tag heldout43 --parser rules --objective use_slack --out eval/heldout/first_run
```

```bash
python eval/run_language_eval.py --inbox eval/heldout/requests.txt --labels eval/heldout/gold_labels.csv --parses "" --tag heldout43 --parser llm --model gpt-5-mini --runs 3 --objective use_slack --env .env --out eval/heldout/first_run
```

- 留出集没有手工解析，所以只报行为、决策、解释三项，不报字段提取。GPT-5 mini 跑 3 遍约 0.2 美元。
- 跑完马上把两组分数和当时的 commit 号写进 `first_run.md` 并提交。**这之后**才能看错误明细、才能改系统。
- 之后再改系统，报告里写“第一次是 X，改了什么之后是 Y”，第一次的数不删。
- 不管过没过 90% 的线，都如实写进报告。

## 第二次运行（修改之后）

记录在 `second_run.md`，结果在 `second_run/`。修改参考了首轮的错误，所以不是干净测试；干净的数字仍是首轮。

## 局限

答案表里只有类别、子类和订单号；约束和之前生效的排除没有逐条填，所以“决策合理”一项不检查长期约束是否被遵守。行为类别是主要指标。
