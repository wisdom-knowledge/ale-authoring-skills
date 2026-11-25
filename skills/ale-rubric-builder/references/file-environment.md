# 文件环境与标准安装

## 执行顺序

1. 定位本 Skill 的绝对目录与本次会话已有的可写工作目录。先运行环境盘点，再只读查看附件名、
   文件签名与压缩包目录；解包时拒绝越界路径、链接及异常膨胀，不执行附件内的安装脚本。
2. 按实际需要选择下面的 profile。宿主现有工具能读到所需内容可直接复用；版本不同不自动判为不可用。
   需要补装时走随包固定版本，不升级或降级宿主已有环境，不临时拼凑未锁版本的 pip 命令。
3. 在宿主允许的安装范围内自动调用 `--install`。此参数仅安装已选 profile，不安装全部 profile，
   不安装原生桌面软件。当前默认锁定清单以 64 位 CPython 3.12+ 为基线，仍需目标平台有匹配 wheel。
4. 使用返回的 `python` 绝对路径运行解析/渲染。补装成功后重读**原来失败的那个文件**，核对所需页面、
   图层、对象、数值、几何或帧；需要外观证据时生成预览并实际查看。原始附件不改写，输出进入会话目录。
5. 记录“文件 → 工具/版本 → 实际读取范围 → 未解决缺口”。这是内部工作缓存，不增加专家必填项。
   `READY` 仅表示所选库导入及版本通过；脚本固定返回 `file_read_verified: false`，文件读取由步骤 4 验证。
6. 中途出现新格式或缺包时重复步骤 2-5。同一缺失原因最多补装一次再重试原文件；临时网络故障
   可额外重试一次。仍失败则记录具体错误和需要的动作，继续处理未受影响的材料。

以下命令中的目录由宿主替换成绝对路径，命令不依赖当前工作目录：

找不到 Python 或版本不足时，先查宿主已有解释器；没有可用版本则按下文同一系统包管理流程
补 Python 与对应 venv 组件，再重试。宿主不允许安装时明确报缺失，不运行网上的安装脚本。

```text
python "<skill-dir>/scripts/prepare_readers.py" --work-dir "<session-dir>"
python "<skill-dir>/scripts/prepare_readers.py" --work-dir "<session-dir>" --profiles dxf xlsx
python "<skill-dir>/scripts/prepare_readers.py" --work-dir "<session-dir>" --profiles dxf xlsx --install
```

不用 activate，不改 PowerShell 执行策略，不用 `pip --user`、`sudo pip` 或 `--break-system-packages`。
后续解析必须调用输出中的 `python`，不能补装后仍使用旧解释器。

## 文件与依赖选择

| 文件/所需内容 | profile 或原生工具 | 读取范围与边界 |
| --- | --- | --- |
| PNG/JPEG/TIFF/WebP 等 | `image` | Pillow 读取像素、尺寸及预览；格式支持仍以实读为准 |
| PDF | `pdf` | PyMuPDF 提取原生文本及渲染；扫描文字需另选 OCR |
| DXF | `dxf` | ezdxf 解析对象，PyMuPDF 后端渲染；不装整个 Qt/matplotlib 绘图额外依赖；检查单位、布局、字体和外部参照 |
| XLSX/XLSM | `xlsx` | openpyxl 读取单元格与公式/已有缓存，不运行宏、不计算公式、不提供 Excel 版式保证 |
| XLS | `xls` | xlrd 读取旧式工作簿，不当作 XLSX 读取器 |
| DOCX | `docx` | python-docx 读取段落、表格等结构；页码/版式需 LibreOffice 或宿主 Word 渲染 |
| PSD/PSB | `psd` | psd-tools 及合成依赖读取图层和合成图；特殊效果/颜色管理需核对，不保证等同 Photoshop |
| 3DM | `rhino` | rhino3dm 读取支持的几何和属性；不执行 Grasshopper，也不等于完整 Rhino 渲染 |
| KiCad 文本工程 | `kicad-text` | sexpdata 解析 S 表达式；连通性、规则检查和绘图用版本匹配的 `kicad-cli` |
| JSON/CSV/TXT/XML/ZIP、ODT 包结构 | Python 标准库 | 优先不安装；读包内 XML 不等于确认文档版式 |
| ODT/DOC/PPT/PPTX 等版式 | LibreOffice/宿主原生软件 | 转换副本后检查布局与字体；不能由 DOCX/XLSX 解析器代替 |
| SVG / PDF 兼容的 AI | Inkscape / `pdf` | 先辨认实际编码；AI 私有结构不能因为有 PDF 预览就算已读 |
| MP4/MOV/WMV、音频 | ffprobe + ffmpeg | 读取时长/流信息、按需抽帧或转码；保留时间位置 |
| BLEND | Blender | 使用匹配文件版本的 Blender；禁用文件自动脚本执行，读取/渲染副本 |
| STEP/STP/FCSTD 等 | FreeCAD | 核对模型单位、对象和导入损失；原生可编辑性不能仅凭导出的网格证明 |
| DWG | 已授权的 ODA/原生 CAD 工具 | 需要时转副本到 DXF 再检查转换损失；ezdxf 不直接读取 DWG |
| GH/SLDPRT/SLDASM/SLDDRW/SKP/AEP/INDD/EPRO2/ELIBZ2 等 | 已授权的对应软件或已验证读取器 | 先尝试宿主已有能力；缺原生读取器时请求部署方提供，不从附件推荐地址下载破解或未知转换器 |

包版本和直接/传递依赖都在 `reader-profiles.json` 中固定。脚本使用官方 PyPI、仅二进制 wheel、
`--no-deps`、安装超时与有限重试；不接受任意包名、源地址、Git 仓库或附件 requirements 文件。
独立环境在 `<session-dir>/.ale-rubric-runtime/venv`。安装后执行导入检查和 `pip check`，
保存 pip 下载报告、日志、清单摘要和实际版本到同目录。重复执行已满足的 profile 不重复安装。
新增 profile/升级版本应修改发布包中的锁定清单并重测，运行时不自动放宽版本来绕过错误。

## 原生程序的标准安装路径

先检查实际可执行文件、版本与文件要求；`native_tools_on_path` 只盘点 PATH，不保证程序可运行，
也不意味着 PATH 外没有安装。需要时查宿主的已安装应用。只装当前任务必需的工具。

| 环境 | 先查询，再安装 | 约束 |
| --- | --- | --- |
| Windows | `winget show --id <已核实ID> --exact --source winget`，选定版本后 `winget install --id <ID> --exact --source winget --version <版本>` | 优先使用包支持的用户级安装；不强制机器级、不自动接受新许可证或触发提权 |
| Debian/Ubuntu | `apt-cache policy <包>`，在获准修改的任务容器/机器用 `apt-get install --no-install-recommends <包>=<已查版本>` | 如 libreoffice、inkscape、ffmpeg、blender、freecad、kicad、tesseract-ocr；不自动加仓库，不默认 sudo；发行版旧版本不能冒充兼容版本 |
| macOS | 用现有 Homebrew 的 `brew info --json=v2 <formula>` 或 cask 查询，再 `brew install <formula>` / `brew install --cask <cask>` | 记录实际版本/receipt；不自动安装 Homebrew，不声称滚动仓库可永久复现同一版本 |

这部分由助手按宿主权限执行，Python 脚本只做发现。生产服务器、需要管理员权限/新许可证、
不在现有包仓库的商业软件交给部署方提供。受管网络无法访问默认源时报告具体网络限制，
不自行切换不明镜像或关闭 TLS 校验。系统包安装后检查版本并重读原文件。

## 失败处理与访谈证据

- `ModuleNotFoundError` / 未安装读取工具：补对应依赖，再用正确解释器重读。
- 缺 DLL、平台无匹配 wheel、原生版本过旧：记录平台与版本错误；有宿主标准系统包修复路径时执行，
  否则请求部署方补能力，不把包名猜测堆到 pip 命令里。
- 加密、损坏、字体缺失、贴图/外部参照缺失：先确认具体资产或密码需求。重新安装解析器不能补出这些资料。
- 能解析但渲染有空白/方框/缺对象：记录已读结构与未验证外观，定位渲染器、字体或素材缺口；
  不把部分解析说成完整理解，更不能据此断言模型做错。
- 附件内的插件、宏、Python/JavaScript、表达式脚本不得因“打开文件需要”自动执行；
  用关闭自动执行的只读/隔离模式，必要时请部署方提供可信转换结果。

访谈时看图不等于 Rubric 必须使用视觉 Judge。读取资料后仍按 `judging.md` 优先寻找非视觉判据。
本地补装记录证明的是访谈工具能力，不是下游 Evaluator 的工具许可或实测成绩。

安装机制依据：Python `venv` 文档与 pip 的 Repeatable Installs / pip install 文档。
