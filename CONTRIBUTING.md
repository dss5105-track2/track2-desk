# 协作规范

## 分支

- `main` 受保护，只接受 Pull Request，至少一人 review。
- 功能分支命名：`<名字拼音>/<issue号>-<简述>`，例如 `wujie/3-estimator`。

## Commit

- 一个 commit 做一件事，信息用英文或中文均可，第一行不超过 60 字。
- 格式：`<模块>: <做了什么>`，例如 `kernel: add expected rework to estimator`。
- 关联 issue：正文写 `Refs #3` 或 `Closes #3`。

## Review 结对

| 作者 | Reviewer |
|---|---|
| 吴杰 | 吴若晗 |
| 吴若晗 | 吴杰 |
| 李岩 | 张锦若 |
| 张锦若 | 李岩 |
| 屈妍玥 | 许佩瑶 |
| 许佩瑶 | 屈妍玥 |

## 永远不做

- 修改 `data/` 与 `harness/simulate.py`。扩展场景放 `scenarios/`。
- 把 API key 提交进仓库。用环境变量，见 `llm/llm_client.py`。
- 在未标注"来源命令 + seed + commit"的情况下，在任何文档或幻灯片里引用模拟器数字。
- 在留出集冻结前让系统跑留出集。

## Teams.pdf 留痕

每个 issue 指派负责人；完成时在 issue 里写一句"交付了什么、验收怎么过的"。最后按 issue 与 commit 统计贡献。
