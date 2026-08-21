# MCP 通用文本写入工具设计方案

> 目标：新增 `save_text_file` 工具，支持任意路径、任意扩展名、超长内容的通用文本写入，
> 通过 `mode: "append"` 实现按块追加，绕过客户端单次 JSON-RPC 传输大小限制。
> 不影响现有 `write_note` 的行为和语义。

---

## 1. 背景与问题

### 1.1 现状

`write_note`（[tools_write.py](../../PersonLLMWiki/src/modules/mcp/tools_write.py)）是当前唯一的 MCP 文件写入工具，定位为"知识库文章写入"：

| 特性 | write_note |
|------|------------|
| 路径范围 | `ARTICLE_PATH` 内 |
| 扩展名 | 仅 `.md` |
| 写入模式 | 覆盖写入 |
| 图片处理 | 自动提取内联 base64 图片 |
| 路径安全 | `resolve_article_path()` + commonpath 校验 |

### 1.2 两个缺陷

| 问题 | 根因 | 影响 |
|------|------|------|
| 1.5 万字超长文档截断 | 客户端 JSON-RPC 传输大小限制（非 ZSSNote 服务端） | 长文档无法通过单次 `write_note` 写入 |
| 缺少通用文本写入能力 | `write_note` 限定 article 路径 + .md 扩展名 + 图片提取 | LLM 无法写入 `.json` / `.csv` / `.txt` 等格式，或写到非文章目录 |

### 1.3 解决策略

| 问题 | 策略 |
|------|------|
| 超长截断 | **方案 A：分块追加** — `mode: "append"` 支持多次调用，客户端自行分块 |
| 通用写入 | 新增独立工具 `save_text_file`，默认路径范围为 `ARTICLE_PATH`（与 write_note 同根），`root="resource"` 时锚定 `RESOURCE_BASE_PATH` |

> 方案 B（文件路径中转）放弃：要求客户端有文件系统访问权限，不通用。

---

## 2. 工具定义

### 2.1 save_text_file

```
tool: save_text_file
description: >
  将任意文本/Markdown 内容写入指定文件。支持覆盖和追加两种模式。
  路径相对于资源根目录（RESOURCE_BASE_PATH），自动创建父目录。
  【超长内容】若单次写入受限，请分多次调用：首次用
  mode="overwrite" 创建文件，后续用 mode="append" 追加。
  【注意事项】仅在最初覆盖写入时发生实际覆盖；追加时内容附加到文件末尾。
```

**输入参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | string | 是 | — | 相对路径，如 `"data/export.json"` 或 `"notes/draft.md"` |
| `content` | string | 是 | — | 要写入的文本内容 |
| `mode` | string | 否 | `"overwrite"` | `"overwrite"` 覆盖 / `"append"` 追加 |
| `create_folders` | boolean | 否 | `true` | 自动创建不存在的父目录 |

**返回**：

```json
{
  "path": "notes/draft.md",
  "bytes_written": 15234,
  "total_bytes": 15234,
  "mode": "overwrite",
  "created": true
}
```

**错误**（`isError: true`）：

| 场景 | 错误码 | 消息 |
|------|--------|------|
| path 缺失 | -32602 | `path 参数必填` |
| content 缺失 | -32602 | `content 参数必填` |
| 路径越界 | -32602 | `路径越界` |
| 父目录不存在且 create_folders=false | -32602 | `父目录不存在: ...` |
| 权限/IO 错误 | -32602 | `写入失败: {err}` |

---

## 3. 安全设计

### 3.1 路径校验（和 write_note 保持一致的范式）

新增 `resolve_resource_path()` 在 [security.py](../../PersonLLMWiki/src/modules/mcp/security.py)：

```
resolve_resource_path(rel_path) → abs_path
  ├── 规范化路径分隔符（Windows/Unix）
  ├── 与 RESOURCE_BASE_PATH 拼接后 os.path.normpath + abspath
  └── os.path.commonpath 校验：结果必须在 RESOURCE_BASE_PATH 内
```

与现有 `resolve_article_path()` 的区别只在于锚定根目录不同（`RESOURCE_BASE_PATH` vs `ARTICLE_PATH`）。

### 3.2 扩展名不限

非 `.md` 文件不能通过 `write_note` 写入，但 `save_text_file` 定位为"通用文本写入"，
不对扩展名做限制。安全依赖路径越界检测，不依赖扩展名白名单。

### 3.3 原子写入（overwrite 模式）

```
写入流程（overwrite）：
  1. tempfile.mkstemp(dir=父目录) → 临时文件
  2. f.write(content)              → 写入临时文件
  3. os.replace(tmp, target)       → 原子替换
  4. 异常时 os.unlink(tmp)         → 清理临时文件
```

write 模式（append）：

```
写入流程（append）：
  1. os.makedirs(父目录, exist_ok=True)
  2. with open(path, 'a', encoding='utf-8') as f:
       f.write(content)
```

追加模式不用原子替换，因为：
- 追加不涉及"全量覆盖"的完整性风险
- 分块追加天然有断点续写的需求，原子化反而增加复杂度

---

## 4. 与现有 write_note 的关系

| 维度 | write_note | save_text_file |
|------|------------|----------------|
| 定位 | 知识库文章写入 | 通用文本/数据写入 |
| 路径根 | `ARTICLE_PATH` | `RESOURCE_BASE_PATH` |
| 扩展名 | 仅 `.md` | 不限 |
| 图片提取 | 自动处理 base64 内联图片 | 不处理（纯文本写入） |
| 写入模式 | 仅覆盖 | 覆盖 + 追加 |
| 原子写入 | 否（直接 `open + write`） | overwrite 模式是 |

**共存策略**：
- `write_note` 保持不变，不修改语义
- `save_text_file` 作为补充，不替代
- LLM 描述中明确何时用哪个：写文章用 `write_note`，写数据/日志/配置/超长文档用 `save_text_file`

---

## 5. 变更文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `modules/mcp/security.py` | 修改 | 新增 `resolve_resource_path()` |
| `modules/mcp/tools_write.py` | 修改 | 新增 `handle_save_text_file()` |
| `modules/mcp/tools_registration.py` | 修改 | 注册 `save_text_file` 工具 |
| `doc/PersonLLMWiki设计规范.md` | 修改 | 更新 MCP 工具列表文档 |

---

## 6. 测试要点

| 用例 | 预期 |
|------|------|
| overwrite 创建新文件 | 返回 `{created: true, mode: "overwrite"}` |
| overwrite 覆盖已有文件 | 返回 `{created: false, mode: "overwrite"}`，内容替换 |
| append 追加到已有文件 | 返回 `{mode: "append"}`，内容追加到末尾 |
| append 追加到不存在文件 | 返回 `{created: true, mode: "append"}`，相当于覆盖 |
| 路径越界 `../` | 返回 `isError: true, "路径越界"` |
| 父目录不存在 + create_folders=false | 返回 `isError: true, "父目录不存在"` |
| path 缺失 | 返回 `isError: true, "path 参数必填"` |
| content 缺失 | 返回 `isError: true, "content 参数必填"` |
| 写入非 .md 文件（如 .json） | 正常写入 |
| 写入到 RESOURCE_BASE_PATH 子目录（如 img/） | 正常写入 |
| 覆盖模式原子性（模拟断电） | 若写入中断，原文件不受影响 |

---

## 7. 变更记录

### 2026-08-11

**新增 `save_text_file` MCP 工具**（本设计文档）

- 新增通用文本写入工具，默认锚定 `ARTICLE_PATH`（与 write_note 同根），`root="resource"` 时锚定 `RESOURCE_BASE_PATH`
- 支持覆盖和追加两种模式，通过分块追加解决客户端传输大小限制
- 覆盖模式使用临时文件 + `os.replace` 原子写入
- 不影响现有 `write_note` 工具的行为和语义
