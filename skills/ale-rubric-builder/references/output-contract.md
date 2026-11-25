# 输出与下游接口

## 正式 JSON

最终输出一个 JSON 数组，每项恰好包含下面六个字段。评分器以此读取独立标准、
优先级和硬门槛；检查路径与来源引文存放在内部预检记录中。

| 字段 | 规则 |
| --- | --- |
| id | 非空且唯一字符串。新建建议 r1、r2、r3；返修尽量保留原 ID |
| source | expert 表示访谈采纳，model 表示自动补全，user 表示调用方预先提供的条目。仅表示生产来源，不证明题面依据 |
| label | deterministic / non-deterministic。按判据性质填写，实际模型依赖另查 |
| description | 一项独立标准，说明对象、属性、通过/失败边界、必要例外及简短 Query/Input 定位 |
| hard_gate | 布尔值，默认 false；仅明确的一票否决规则且能纯代码判时才可 true |
| priority | critical / important。关键项默认 critical，普通补全 important；不据预测得分调权 |

例子仅演示结构，不是本题实际要求：

```json
[
  {
    "id": "r1",
    "source": "expert",
    "label": "deterministic",
    "description": "检查交付 summary.csv 的 total_sales 是否等于 sales.csv 中 amount 列全部数据行之和；依据为 Query 的销售总额要求与 Input 的字段说明。两者以分为整数单位，比较整数值相等。",
    "hard_gate": false,
    "priority": "critical"
  }
]
```

真实输出只能包含六字段数组，不加 score、weight、expected_winner 或内部方法记录。
标准必须模型身份无关；原始 Input 的文件名可以引用，临时下载名和某个 rollout 的私有命名不写入标准。
若权重或调用链尚未知，保持状态未知，不能在 description 里塞一个“待定阈值”冒充完成。

## 内部预检记录

在会话工作目录保存 `review.json`，由助手维护，不要求专家填写，也不是第二份最终交付。
顶层恰好三项：`rubric_sha256`、`basis`、`methods`，后两者逐一覆盖所有正式 ID。

```json
{
  "rubric_sha256": "填写最终 rubric.json 文件的实际 SHA256",
  "basis": {
    "r1": [
      {
        "source": "query",
        "file": "query.txt",
        "locator": "交付要求第1条",
        "quote": "summary.csv 中的 total_sales 为销售总额。",
        "justification": "本条直接检查题面要求的销售总额。"
      },
      {
        "source": "input",
        "file": "input-field-notes.txt",
        "locator": "sales.csv 字段说明",
        "quote": "amount 以分为整数单位，全部数据行均计入销售总额。",
        "justification": "说明本题求和范围和比较单位。"
      }
    ]
  },
  "methods": {
    "r1": {
      "dependency": "unknown",
      "confirmed": false,
      "evidence": "标准可复算，尚未核对本题工具包中的 CSV 读取接口。"
    }
  }
}
```

`file` 相对 review.json 所在目录，指向已核对的 UTF-8 原文或提取文本。原始 XLSX/PDF 等须先实读、
核对定位并留下对应文本；不可编造一份“原文”让引用测试通过。
每条 basis 至少一条 Query/Input 依据；金标和 rollout 不可作为独立准入依据。
`justification` 解释引用如何支持标准；脚本只检查非空、声明来源及引文存在，不替人判断逻辑蕴含。

`methods` 的每项包含 dependency、confirmed 和 evidence。dependency 为
code、judge、agent、mixed 或 unknown；含义见 [判据收敛](judging.md)。
只有实际核对工具入口和依赖链才写 confirmed=true；不能从 description、label 或理论可行性推断。
工具尚缺或未核对时用 unknown/false，并保留具体缺口。

## 部署与调用

完整部署本 Skill 目录，保留 scripts、references 和 agents 子目录。检查脚本要求 Python 3.11+，
只使用标准库；无需安装 Python 包、配置 API 密钥或连接代码仓库。
宿主负责为助手配置模型、对话和文件工具，并分配可写的会话工作目录。

下例 `<skill-dir>` 表示部署后的 Skill 绝对路径，`<work-dir>` 表示会话工作目录；
运行时替换占位符。路径含空格时加引号。工作目录可位于任何位置。

```text
python <skill-dir>/scripts/check_rubric.py <work-dir>/rubric.json --review <work-dir>/review.json
```

脚本从自身目录加载随包的 `judge_weight_check.py`，只读输入并向标准输出打印 JSON，不联网。
返回码 0 / PASS_DRAFT 表示声明范围内的预检通过，1 / FAIL 表示格式、引文或预算失败，
2 / BLOCKED 表示缺证据、依赖未知或文件不可读。不传 --review 可查看格式结果，但整体保持 BLOCKED。

独立运行随包测试：

```text
python -B -m unittest discover -s <skill-dir>/scripts -p "test_*.py"
```

## 默认权重及 30% 检查

本 Skill 的草案预检采用固定权重：critical=2，important=1。
模型依赖占比 = 模型依赖条目的权重之和 / 全部条目的权重之和。
judge、agent、mixed 整条计权；unknown 报上下界并保留阻塞。
恰好 30% 合格，超过则报 FAIL。带模型依赖的 hard_gate 即使权重为零也不能通过。
草案采用归一化加权评分假设；最终评分器的实际权重和聚合规则需按其配置核对。

未知或超限时继续完善有任务依据的判法，或把具体条目交下游处理；不自动降关键项权重、
加低价值条目稀释分母、删核心要求或把 mixed 改成 code。
SOTA 0.5-0.7、评测模型 0.2-0.4 留在下游观察/校准环节，不传给 Judge，也不写进 Rubric。

## 实际评分器的权重检查

评分器生成后，可使用随包脚本检查真实配置；该步骤不运行评分器或调整权重。

```text
python <skill-dir>/scripts/judge_weight_check.py <work-dir>/evaluator.toml --review <work-dir>/actual-review.json
```

配置可用 JSON 条目数组，或用 TOML/JSON 的 rubrics 映射。每条需有唯一 id、布尔 hard_gate
及非负数值 weight；映射键作为 id。仅有 priority 不能代替实际权重。
如配置不直接含权重，可在 actual-review.json 的 weights 中提供覆盖所有 ID 的数值映射；
如两处都有权重，必须一致。

actual-review.json 模板如下。哈希针对实际评分器配置文件；methods 覆盖配置中全部 ID。
核实权重来源、归一化聚合规则及每条调用链之后，才能填写相应证据并将 confirmed 改为 true。

```json
{
  "rubric_sha256": "填写 evaluator.toml 文件的实际 SHA256",
  "weight_source": "填写权重所在配置、版本或规则",
  "aggregation": {
    "kind": "normalized_weighted_sum",
    "confirmed": false,
    "evidence": "填写聚合规则、评分尺度和硬门槛效果的核对结果"
  },
  "methods": {
    "r1": {
      "dependency": "unknown",
      "confirmed": false,
      "evidence": "填写本条实际工具入口与模型调用链"
    }
  }
}
```

实际权重检查的返回码为 0 / PASS_PREFLIGHT、1 / FAIL、2 / BLOCKED。
两类检查都不执行评分器：引文存在不代表语义成立，依赖声明不代表工具已实测。
语义覆盖、等价正确解法与实际执行效果须分别核验。
