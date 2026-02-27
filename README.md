# RenderDoc MCP Server

一个面向 **RenderDoc 图形调试工作流** 的 MCP 服务器。它通过「MCP 服务进程 + RenderDoc 扩展」的双进程架构，让 Claude / 其他 MCP 客户端可以直接查询 `.rdc` 捕获数据（DrawCall、Shader、Pipeline、纹理/缓冲区内容等）。

---

## 1. 项目定位与核心能力

本项目解决的问题：
- RenderDoc 内嵌 Python 运行环境能力受限（尤其缺少常规 socket 通信能力）。
- AI 助手需要稳定读取 RenderDoc ReplayController 数据。

因此采用 **文件轮询 IPC**，在不依赖网络 socket 的前提下，实现跨进程请求/响应。

核心能力包括：
- 采集文件管理：列举 `.rdc`、打开指定 capture。
- Action/DrawCall 分析：树形事件、筛选、详情查询、GPU timing。
- 资源分析：纹理元信息、像素数据、Buffer 原始字节流（Base64）。
- Pipeline 还原：各着色器阶段、资源绑定、Sampler、常量缓冲区、RT/DS 等。
- 反向检索：按 Shader 名、Texture 名、ResourceId 追踪关联 Draw。

---

## 2. 总体架构

```text
Claude / MCP Client (stdio)
            │
            ▼
mcp_server (FastMCP, 标准 Python 进程)
            │  文件IPC: %TEMP%/renderdoc_mcp/
            ▼
renderdoc_extension (RenderDoc 扩展进程内)
            │
            ▼
RenderDoc ReplayController / CaptureContext
```

### 2.1 数据流
1. MCP 客户端调用工具（例如 `get_pipeline_state`）。
2. `mcp_server/server.py` 将参数交给 `RenderDocBridge.call()`。
3. Bridge 把请求写入 `request.json`，等待 `response.json`。
4. RenderDoc 扩展定时轮询请求文件，分发到 `RequestHandler`。
5. `RenderDocFacade` 把请求交给具体 Service，并通过 `BlockInvoke` 进入 replay 线程执行。
6. 结果序列化后写回响应文件，MCP 端读取并返回给客户端。

### 2.2 为什么不用 socket
RenderDoc 扩展运行环境限制使 socket/QtNetwork 不可依赖，因此项目采用：
- `request.json` / `response.json` + `lock` 文件
- 轮询间隔 100ms
- 双方均在请求前后做旧文件清理与异常保护

---

## 3. 项目层级架构（逐目录/逐文件功能说明）

> 下方按仓库真实结构说明“每一层负责什么”。

```text
RenderDocMCP_SunSan/
├── mcp_server/
│   ├── __init__.py
│   ├── config.py
│   ├── server.py
│   └── bridge/
│       ├── __init__.py
│       └── client.py
├── renderdoc_extension/
│   ├── __init__.py
│   ├── extension.json
│   ├── socket_server.py
│   ├── request_handler.py
│   ├── renderdoc_facade.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── capture_manager.py
│   │   ├── action_service.py
│   │   ├── search_service.py
│   │   ├── resource_service.py
│   │   └── pipeline_service.py
│   └── utils/
│       ├── __init__.py
│       ├── helpers.py
│       ├── parsers.py
│       └── serializers.py
├── scripts/
│   └── install_extension.py
├── pyproject.toml
├── uv.lock
├── LICENSE
├── renderdoc-mcp-improvement-proposal.md
├── CLAUDE.md
└── README.md
```

### 3.1 `mcp_server/`（MCP 对外接口层）

- `server.py`
  - FastMCP 入口。
  - 定义全部 MCP Tools（capture、draw、search、shader、resource、pipeline）。
  - 只做参数组装和转发，不直接操作 RenderDoc API。
- `bridge/client.py`
  - 文件 IPC 客户端。
  - 负责创建请求 ID、写 `request.json`、轮询 `response.json`、超时与错误映射。
- `config.py`
  - 读取环境变量（`RENDERDOC_MCP_HOST` / `RENDERDOC_MCP_PORT`，主要保留兼容性）。

### 3.2 `renderdoc_extension/`（RenderDoc 进程内执行层）

- `__init__.py`
  - RenderDoc 扩展入口，提供 `register()` / `unregister()`。
  - 初始化 Facade + Handler + IPC Server，并可在 UI 菜单挂状态项。
- `extension.json`
  - RenderDoc 扩展清单文件（名称、入口等元信息）。
- `socket_server.py`
  - 文件 IPC 服务端（QTimer 轮询）。
  - 处理请求读取、响应写入、异常兜底。
- `request_handler.py`
  - 方法路由器：把 method 名映射到 facade 调用。
  - 参数校验、错误码构建（类似 JSON-RPC 风格）。
- `renderdoc_facade.py`
  - 统一门面，封装 replay 线程切换。
  - 按领域拆分到五类 service，避免单文件膨胀。

### 3.3 `renderdoc_extension/services/`（领域能力层）

- `capture_manager.py`
  - 是否已加载 capture、当前 API 类型。
  - 列举目录下 `.rdc` 文件（含大小与时间）。
  - 打开 capture 并返回基础结果。
- `action_service.py`
  - Action 树读取/过滤（marker、event id、flags 等）。
  - draw 详情与帧摘要。
  - GPU timing 查询。
- `search_service.py`
  - 按 shader / texture / resource 反查关联 draw。
- `resource_service.py`
  - Buffer 原始内容读取（offset/length）。
  - Texture 元信息与像素数据提取（mip/slice/sample/depth_slice）。
- `pipeline_service.py`
  - 指定 event 的完整 pipeline 快照。
  - shader reflection、资源绑定、sampler、cbuffer 信息。

### 3.4 `renderdoc_extension/utils/`（通用支撑层）

- `serializers.py`
  - RenderDoc 原生对象转 JSON 友好结构。
- `parsers.py`
  - 参数解析（如 ResourceId 解析）。
- `helpers.py`
  - 常用辅助函数、格式与容错处理。

### 3.5 `scripts/` 与根目录文件（工程与发布层）

- `scripts/install_extension.py`
  - 将扩展复制到 RenderDoc 扩展目录（Windows/Linux 路径自动判断）。
- `pyproject.toml`
  - Python 包配置、依赖、CLI 入口 `renderdoc-mcp`。
- `uv.lock`
  - 依赖锁定。
- `renderdoc-mcp-improvement-proposal.md`
  - 设计/改进提案文档。

---

## 4. MCP Tool 全量说明

### 4.1 Capture 管理
- `list_captures(directory)`：列出目录下所有 `.rdc` 文件。
- `open_capture(capture_path)`：加载指定 capture（会替换当前已加载 capture）。
- `get_capture_status()`：查询是否已加载 capture、文件名、API。

### 4.2 Action / Draw 分析
- `get_draw_calls(...)`：获取树形 action，可按 marker、event id、flags 过滤。
- `get_frame_summary()`：帧统计汇总（draw/dispatch/clear/copy/present/marker 等）。
- `get_draw_call_details(event_id)`：单个 draw 的详细元数据。
- `get_action_timings(...)`：GPU timing（若驱动/硬件支持）。

### 4.3 反向搜索
- `find_draws_by_shader(shader_name, stage?)`
- `find_draws_by_texture(texture_name)`
- `find_draws_by_resource(resource_id)`

### 4.4 Shader / Pipeline / Resource
- `get_shader_info(event_id, stage)`：反汇编、常量缓冲区值、绑定信息。
- `get_pipeline_state(event_id)`：完整 pipeline 状态快照。
- `get_buffer_contents(resource_id, offset=0, length=0)`：返回 Base64 字节。
- `get_texture_info(resource_id)`：纹理描述。
- `get_texture_data(resource_id, mip=0, slice=0, sample=0, depth_slice=None)`：像素数据（Base64）。

---

## 5. 安装与使用

### 5.1 安装 RenderDoc 扩展

```bash
python scripts/install_extension.py
```

安装目标：
- Windows: `%APPDATA%\qrenderdoc\extensions\renderdoc_mcp_bridge`
- Linux: `~/.local/share/qrenderdoc/extensions/renderdoc_mcp_bridge`

然后在 RenderDoc 中启用：
`Tools > Manage Extensions > RenderDoc MCP Bridge`

### 5.2 安装 MCP Server

```bash
uv tool install .
uv tool update-shell
```

重启 shell 后可使用：

```bash
renderdoc-mcp
```

### 5.3 Claude Desktop / Claude Code 配置

```json
{
  "mcpServers": {
    "renderdoc": {
      "command": "renderdoc-mcp"
    }
  }
}
```

### 5.4 典型调用示例

```text
# 打开 capture
open_capture(capture_path="D:\\captures\\frame_1001.rdc")

# 获取事件树（只看 Drawcall/Dispatch）
get_draw_calls(only_actions=true, flags_filter=["Drawcall", "Dispatch"])

# 查看某事件的 Pipeline 状态
get_pipeline_state(event_id=12345)

# 读取贴图像素
get_texture_data(resource_id="ResourceId::987", mip=0, slice=0)
```

---

## 6. 运行要求

- Python 3.10+
- uv
- RenderDoc 1.20+

> 当前实现主要在 Windows + DirectX 场景验证；其他平台/API 需按实际环境测试。

---

## 7. License

MIT
