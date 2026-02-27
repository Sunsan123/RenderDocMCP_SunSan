# RenderDocMCP_SunSan

`RenderDocMCP_SunSan` 是一个面向 MCP（Model Context Protocol）的 RenderDoc 工具服务，方便你在支持 MCP 的客户端里通过自然语言调用 RenderDoc 常用能力（环境检查、抓帧文件目录管理、列出/索引 `.rdc` 文件、打开指定抓帧等）。

## 本次迁移说明

由于当前运行环境无法直接访问 GitHub（`https://github.com/halby24/RenderDocMCP` 请求被网络策略拦截），因此采用“按目标能力重建”的方式完成迁移：

- 新增了可运行的 MCP 服务端入口。
- 实现了围绕 RenderDoc 工作流的基础工具集合。
- 补齐了项目依赖和可执行脚本配置。
- 重写了 README，补充安装、配置、运行和接入方式。

> 如果你希望做到 **100% 文件级一致迁移**，可以在可联网环境下把参考仓库内容导出（zip 或 patch），我可以再帮你做二次精确对齐。

---

## 功能清单

当前版本提供以下 MCP Tools：

1. `health_check`
   - 检查 RenderDoc CLI/GUI 可执行程序是否可用。
2. `create_capture_dir(path?)`
   - 创建抓帧目录（默认 `./captures`）。
3. `list_captures(path?)`
   - 列出目录中的 `.rdc` 文件。
4. `launch_renderdoc(capture_file?, renderdoc_path?)`
   - 启动 `qrenderdoc`，可选自动打开某个 `.rdc`。
5. `open_capture(capture_file, renderdoc_path?)`
   - 打开指定 `.rdc`（`launch_renderdoc` 的语义化封装）。
6. `export_capture_index(path?, output_file='capture_index.json')`
   - 将抓帧列表导出为 JSON 索引文件。

---

## 环境要求

- Python `>= 3.10`
- 已安装 RenderDoc（并能在命令行访问 `qrenderdoc`，或者通过环境变量指定路径）

---

## 安装

```bash
pip install -e .
```

或使用你自己的虚拟环境工具（`uv` / `poetry` / `venv`）。

---

## 配置

可选环境变量：

- `RENDERDOC_PATH`
  - RenderDoc 可执行程序路径，默认：`qrenderdoc`
- `RENDERDOC_CAPTURE_DIR`
  - 默认抓帧目录，默认：`./captures`

示例：

```bash
export RENDERDOC_PATH="/usr/bin/qrenderdoc"
export RENDERDOC_CAPTURE_DIR="$HOME/renderdoc/captures"
```

---

## 本地运行（stdio）

```bash
renderdocmcp
```

这会以 MCP `stdio` 方式启动服务，适合被 MCP Host（如支持 MCP 的 AI 客户端）拉起。

---

## MCP 客户端接入示例

下面是一个通用 JSON 配置示例（不同客户端字段名可能略有差异）：

```json
{
  "mcpServers": {
    "renderdoc": {
      "command": "renderdocmcp",
      "args": [],
      "env": {
        "RENDERDOC_PATH": "qrenderdoc",
        "RENDERDOC_CAPTURE_DIR": "./captures"
      }
    }
  }
}
```

---

## 项目结构

```text
.
├── README.md
├── pyproject.toml
└── renderdoc_mcp_server.py
```

---

## 后续可扩展方向

- 增加对 `renderdoccmd` 的命令封装（抓帧、重放、缩略图导出）。
- 增加跨平台路径检测（Windows/Linux/macOS）与自动发现。
- 增加更细粒度的错误码和结构化返回。
- 为常用场景补充自动化测试。

---

## License

可按你的团队规范补充（如 MIT / Apache-2.0）。
