# 天津大学微电子学院柔性压力传感器综合实验 MCP

这是面向**天津大学微电子学院柔性压力传感器综合实验**开发的 COMSOL Agent MCP 项目。项目基于 Model Context Protocol（MCP）把 COMSOL Multiphysics 的建模、求解和结果导出能力封装为可被 AI Agent 调用的工具，使实验人员可以用自然语言驱动柔性压力传感器仿真流程。

本项目的目标不是简单打开 COMSOL，而是让 Agent 能够理解实验任务，并自动完成典型仿真动作：分析微结构 DXF 文件、建立柔性压力传感器接触压缩模型、设置材料与边界条件、执行参数扫描、导出接触长度和压力积分等关键结果。

## 项目定位

柔性压力传感器综合实验通常涉及微结构设计、弹性体材料建模、上下电极接触、压缩位移加载、接触压力分布分析等步骤。传统 COMSOL 建模需要人工完成大量重复操作，例如几何导入、选择集设置、接触对创建、网格划分、参数扫描和结果后处理。

本 MCP 将这些重复、容易出错的操作封装成标准工具接口，让 AI Agent 可以像调用函数一样操作 COMSOL。学生和研究人员可以把更多精力放在传感器结构设计、仿真结果理解和实验机理分析上。

## MCP 是什么

MCP（Model Context Protocol）是一种让 AI Agent 调用外部工具、数据和软件系统的协议。可以把 MCP 理解为 Agent 和专业软件之间的“标准接口层”。

在本项目中：

- Agent 负责理解用户的自然语言需求。
- MCP Server 负责把需求转换成可执行的工具调用。
- COMSOL 后端负责真实的几何建模、物理场设置、网格划分、求解和结果计算。

因此，用户可以说“用这个 DXF 建一个柔性压力传感器接触模型，压缩位移从 0 到 20 微米扫描”，Agent 会通过 MCP 调用对应工具完成建模与仿真。

## Agent 的作用

Agent 是具备工具调用能力的智能助手。它不仅能回答问题，还能根据任务目标拆解步骤、选择工具、读取结果并继续执行下一步。

在柔性压力传感器实验中，Agent 可以承担以下工作：

- 根据用户描述判断需要建立哪类 COMSOL 模型。
- 自动读取 DXF 微结构轮廓并判断几何尺寸。
- 根据实验参数设置材料、加载、接触和求解器。
- 执行参数扫描并导出 CSV 结果。
- 对接触压力、接触长度、压缩位移关系进行解释。
- 帮助学生理解 MCP、COMSOL API、JVM 和仿真工作流之间的关系。

## 核心功能

本项目保留了通用 COMSOL MCP 能力，同时增加了面向柔性压力传感器综合实验的专用工具。

通用能力包括：

- 启动和连接 COMSOL 会话。
- 创建、加载、保存 COMSOL 模型。
- 创建组件、几何、材料、物理场、网格和研究。
- 执行求解、监控求解进度、导出结果。
- 查询模型结构、参数、数据集、解和图表。

柔性压力传感器专用能力包括：

| 工具名称 | 功能 |
| --- | --- |
| `flex_sensor_analyze_dxf` | 分析 DXF 微结构轮廓，统计线段、圆弧、边界范围，并给出单位建议。 |
| `flex_sensor_build_contact_model` | 从 DXF 自动构建二维接触压缩模型，包括敏感层、上电极、Neo-Hookean 材料、固定边界、位移加载、接触对、网格和参数扫描。 |
| `flex_sensor_export_contact_results` | 从已求解模型中导出接触长度、压力积分等结果，用于后续绘图和性能分析。 |

## 技术架构

本 MCP 的核心架构如下：

```mermaid
flowchart LR
    A["用户自然语言需求"] --> B["AI Agent"]
    B --> C["MCP Client"]
    C --> D["COMSOL MCP Server"]
    D --> E["Python 工具层"]
    E --> F["MPh / JPype"]
    F --> G["JVM"]
    G --> H["COMSOL Java API"]
    H --> I["COMSOL Multiphysics"]
    I --> J["模型与仿真结果"]
```

其中，MPh 和 JPype 用于在 Python 中调用 COMSOL Java API。COMSOL 的 Java client 运行在 JVM 中，真正的几何、物理场和求解操作最终都会传递给 COMSOL Multiphysics 执行。

在本地适配中，本项目还支持使用 **stdio proxy + HTTP sidecar** 的方式连接 COMSOL。这样做的原因是：COMSOL Java client 如果直接放在 MCP stdio 进程中，有时会在连接阶段阻塞，导致 MCP 客户端无法正常收到响应。通过将 COMSOL 操作放在 HTTP sidecar 中，再由 stdio proxy 与 Agent 通信，可以降低 stdio 阻塞风险，使工具调用更加稳定。

## 柔性压力传感器仿真流程

典型实验流程如下：

1. 准备微结构 DXF 文件  
   DXF 文件描述柔性敏感层的二维轮廓，例如微金字塔、微圆顶、沟槽或其他周期结构截面。

2. 分析 DXF 几何  
   使用 `flex_sensor_analyze_dxf` 读取 DXF，获得几何边界、实体数量和推荐单位。

3. 构建接触压缩模型  
   使用 `flex_sensor_build_contact_model` 自动建立敏感层和上电极，配置材料模型、接触边界、固定约束和位移加载。

4. 执行参数扫描  
   对上电极下压位移进行扫描，例如 `0 2 4 6 8 10 12 14 16 18 20` 微米，得到不同压缩状态下的接触行为。

5. 导出结果  
   使用 `flex_sensor_export_contact_results` 导出接触长度、压力积分等数据。

6. 分析传感器性能  
   根据接触面积、压力分布和压缩位移关系，分析柔性压力传感器的灵敏度、线性范围和结构设计差异。

## 环境要求

建议环境：

- Windows 10/11
- Python 3.10 或更高版本
- COMSOL Multiphysics 6.x
- Java/JVM 环境
- Git

本实验环境中，COMSOL 6.3 安装路径为：

```powershell
D:\COMSOL63
```

如果本机 COMSOL 安装在其他路径，需要在本地配置中修改对应的 COMSOL 路径和 Java classpath。

## 安装方法

克隆仓库：

```powershell
git clone https://github.com/tonghui666/flex-sensor-agent-mcp.git
cd flex-sensor-agent-mcp
```

创建并激活 Python 虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```powershell
pip install -e .
```

如果需要运行测试：

```powershell
pip install pytest
pytest
```

## MCP 配置方式

在支持 MCP 的 Agent 客户端中添加本项目的 MCP Server 配置。根据本地部署方式，可以选择直接 stdio 启动，或使用 stdio proxy 连接 HTTP sidecar。

示例配置思路：

```json
{
  "mcpServers": {
    "flex-sensor-comsol": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "C:/Users/Administrator/Desktop/comsol/COMSOL_Multiphysics_MCP"
    }
  }
}
```

如果使用 HTTP sidecar，应先启动 sidecar 服务，再由 stdio proxy 与 MCP 客户端通信。具体命令以本地脚本和配置文件为准。

## 典型使用示例

连接或启动 COMSOL：

```text
请启动 COMSOL，并连接到本地 COMSOL 6.3 环境。
```

分析 DXF 微结构：

```text
请分析这个 DXF 文件的微结构尺寸，并判断适合用什么单位导入 COMSOL。
```

构建柔性压力传感器模型：

```text
请基于该 DXF 建立二维柔性压力传感器接触压缩模型。
上电极高度 20 微米，初始间隙 2 微米，下压位移从 0 到 20 微米扫描。
```

导出结果：

```text
请导出不同压缩位移下的接触长度和压力积分，保存为 CSV 文件。
```

## 仓库结构

```text
.
├── src/                         # MCP Server 与 COMSOL 工具实现
├── tests/                       # 测试用例
├── comsol_models/               # 本地生成的 COMSOL 模型，默认不提交
├── README.md                    # 中文项目说明
├── README_FLEX_SENSOR_AGENT_MCP.md
├── GITHUB_DEPLOYMENT.md
├── pyproject.toml
└── .gitignore
```

## 技术要点

1. MCP 工具封装  
   将 COMSOL 建模动作抽象为 Agent 可调用的工具，例如模型创建、几何导入、边界条件设置、参数扫描和结果导出。

2. COMSOL Java API 调用  
   通过 Python 调用 JVM 中的 COMSOL Java API，实现对 COMSOL 的自动化控制。

3. 柔性传感器专用建模流程  
   将柔性压力传感器实验中的敏感层、上电极、Neo-Hookean 材料、接触对和压缩加载封装成固定工作流。

4. DXF 微结构解析  
   对常见 LINE 和 ARC 轮廓进行保守解析，为后续几何导入和单位选择提供依据。

5. 参数化求解与结果导出  
   支持位移参数扫描，并导出接触长度和压力积分等实验分析指标。

6. stdio proxy + HTTP sidecar 适配  
   将容易阻塞的 COMSOL Java client 操作从 MCP stdio 主进程中隔离出来，提高 Agent 调用稳定性。

## 注意事项

- `.venv/`、`comsol_models/`、`knowledge_base/`、`logs/` 和大型 `.mph` 模型文件默认不提交到 Git。
- COMSOL 求解可能占用较多 CPU 和内存，复杂接触模型建议先使用较小参数范围测试。
- DXF 文件应尽量保持轮廓闭合、单位清晰、结构简洁。
- 若求解不收敛，可以尝试减小位移步长、优化网格、调整接触设置或简化几何。
- 本项目用于教学与科研实验辅助，仿真结果仍需要结合材料参数、实验标定和实际器件结构进行判断。

## 后续扩展方向

- 增加电学模型，实现压阻、电容或电流响应仿真。
- 增加结构参数自动优化能力，例如微结构高度、周期、圆角和间距优化。
- 支持更多 DXF 实体和复杂微结构阵列。
- 增加自动绘图和报告生成功能。
- 引入仿真失败诊断与自动重试策略。
- 建立柔性压力传感器实验数据集，与仿真结果进行对比验证。

## 许可证

本项目遵循仓库中的开源许可证文件。用于课程实验、科研学习和二次开发时，请同时遵守 COMSOL Multiphysics 软件许可协议。
