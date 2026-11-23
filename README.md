# ALE 出题辅助 Skills

ALE 辅助出题工具当前使用的独立 Skill 分发仓库。两个目录均包含完整入口、引用规则和 Agent 元数据，可以分别安装。

| Skill | 当前版本 | 适用输入 |
| --- | --- | --- |
| [ale-task-interviewer](skills/ale-task-interviewer/SKILL.md) | `ver0.2-ew` | input 素材与一句话任务描述，从想法开始整理题目 |
| [ale-reference-interviewer](skills/ale-reference-interviewer/SKILL.md) | `ver0.2` | input 与 reference，任务描述可选，从已有作品反向出题 |

两者主要交付 **prompt、经济价值、关键做题步骤**，由专家确认；不代替机审，不自动提交产线，也不保证审核通过。

## 获取与安装

前往 [Releases](https://github.com/wisdom-knowledge/ale-authoring-skills/releases/latest) 下载需要的独立 ZIP。解压后，将完整的同名目录放到 Agent 支持的 Skill 目录中。

Codex 通常使用 `~/.codex/skills/`，设置 `CODEX_HOME` 时使用其 `skills/` 子目录。其他宿主按自身的 Skill 安装方式导入。不要只复制 `SKILL.md`，也不要多套一层同名目录；已有版本请先备份。

也可以克隆此仓库：

```sh
git clone https://github.com/wisdom-knowledge/ale-authoring-skills.git
```

然后分别安装 `skills/ale-task-interviewer` 或 `skills/ale-reference-interviewer`。

## 本次分发内容

- `ale-task-interviewer`：在上游 `ver0.1` 基础上，允许在临时副本上使用宿主已安装的专业软件或可信读取库检查材料；缺少 Python 模块、预览不支持时，先核对原生软件能力，再请求必要的人工导出。保留源文件，禁止执行附件宏或脚本，不擅自安装软件、付费或接受新许可。
- `ale-reference-interviewer`：保持上游 `ver0.2` 的功能规则。该版本已经包含原生软件读取、视觉核验及回退路径，本次不虚构新的功能修改。
- 两个 `VERSION.md` 更新公开分发约定；其余功能内容与已核对的工程版本一致。

本包不包含专业软件、模型 API、虚拟机、账号或密钥。安装 Skill 不等于安装这些运行环境。网页上传、登录、限额、会话恢复及 trace 落盘由宿主实现，不属于这两个 Skill 包。

## 来源与版本

首次公开分发标签：`v1.0.0`（2026-11-23）。这是分发仓库版本，不重命名两个 Skill 各自的版本。

来源：`expert-workspace` 的 `code/99` 分支，核对提交 `ba2bff389f42254deb7e6e2734d1009a27b79c3a`，目录 `apps/server/assets/quick-chat/skills/`。原生软件读取修改来自提交 `7dcaf1f`。项目 106 的 Hermes 安装流程也使用这两个目录。

GitHub 标签和 Release ZIP 对应同一份内容。后续修改通过新提交和新分发标签发布，不覆盖已有标签；部署中的工作台需要独立更新，仓库发布不会自动改变生产环境。
