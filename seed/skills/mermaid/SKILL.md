---
name: mermaid
description: Use when the user asks to draw diagrams, flowcharts, sequence diagrams, class diagrams, ER diagrams, Gantt charts, pie charts, mindmaps, or any Mermaid-based visualization (流程图/时序图/类图/ER图/甘特图/饼图/思维导图等)
---

# Mermaid 图表生成规范

当需要生成 `mermaid` 代码块时，严格遵守以下规则。**所有图表类型（flowchart/classDiagram/sequenceDiagram/erDiagram/gantt/pie/stateDiagram 等）均适用规则 1-2。**

**全局要求：所有引号必须使用 ASCII 直引号 `"` (U+0022)，禁止弯引号 `"` `"` (U+201C/U+201D)，否则渲染失败。**

## 1. 节点和标签引用（所有图表通用）

所有含特殊字符（空格、`()`、`&`、`"`、中文括号、`+`、`/`、`→`、中文等）的 **标签/名称文本** 必须用双引号包裹。

flowchart：
```
正确：A["界面层"]、B["子流程(A)"]、C["输入/输出"]
错误：A[界面层]、B[子流程(A)]
```

classDiagram：
```
正确：
class "智能体Agent" {
    +观察Observe()
}
错误：
class 智能体Agent {
    +观察Observe()
}
```

节点 ID 本身用简单英文+数字，如 `R1`、`NODE_A`。

## 2. 关系箭头规则

- 实线箭头：`A --> B`
- 虚线箭头：`A -.-> B`
- 粗线箭头：`A ==> B`
- 带标签实线：`A -->|"创建"| B`
- 带标签虚线：`A -.->|"异步通知"| B`

**严禁以下写法**（mermaid.ink 不支持，都会渲染失败）：

```
错误：A -- "标签" --> B        ← 标签写在 -- 和 --> 之间
错误：A -. "标签" .-> B        ← 标签写在 -. 和 .-> 之间
错误：A -.中文无引号.-> B      ← 中文标签不加引号直接夹在虚线中间，最容易出现
错误：START -.由 Agent 定义.-> L1  ← 同上，含空格的更严重
```

**正确写法只有一种**：标签用 `|"标签"|` 包在箭头前后两部分之间：

```
正确：A -->|"标签"| B
正确：A -.->|"标签"| B
正确：START -.->|"由 Agent 定义状态机"| NODE
```

**边的起点/终点必须是节点 ID，不能是 subgraph ID**：

## 3. subgraph 结构规则（重要！易错！）

### 3.1 跨 subgraph 的连线必须全部放在所有 `end` 之后

mermaid.ink **不允许**在 subgraph 内部写引用外部节点的连线。必须先把所有 subgraph 声明完，然后在最外层统一写跨组连线。

**错误示例（会渲染失败）：**
```
subgraph A["分组A"]
    N1["节点1"] --> N2["节点2"]   ← 同组内 OK
end
subgraph B["分组B"]
    N3["节点3"]
    N1 --> N3                     ← 错误！N1 在分组A，这行跨组了
end
```

**正确写法：**
```
subgraph A["分组A"]
    N1["节点1"] --> N2["节点2"]
end
subgraph B["分组B"]
    N3["节点3"]
end
N1 -->|"跨组"| N3                 ← 所有跨组连线集中在 end 之后
```

### 3.2 subgraph ID 用简单英文，标签用双引号包裹

```
正确：subgraph FE["前端层"]
错误：subgraph 前端[前端层]
错误：subgraph front-end["前端层"]
```

### 3.3 嵌套 subgraph 的跨层连线同样集中到最外层

嵌套结构中，只要连线两端不在同一个 subgraph 内，就不能写在 subgraph 内：

**正确结构模板：**
```
subgraph OUTER["外层"]
    subgraph INNER1["内层1"]
        A["节点A"]
    end
    subgraph INNER2["内层2"]
        B["节点B"] --> C["节点C"]   ← 同组 OK
    end
    A --> B                         ← A 在 INNER1，B 在 INNER2，放内层 end 之后
end
```

### 3.4 节点超过 15 个时必须用 subgraph 分组

## 4. 多行节点标签

如需换行，必须用自闭合 `<br/>`（禁止不闭合的 `<br>`，某些解析器会失败）：

```
RT["Router 节点<br/>(conditional_edge)"]
```

## 5. 时序图规范

参与者命名用 `participant ID as "显示名"`，中文括号放在引号内：

```
正确：
participant U as "用户"
participant S as "服务端(API)"

错误：
participant U as 用户
participant S as 服务端(API)
```

## 6. 多源合并禁止

不要使用 `&` 合并多个源节点到同一条边（mermaid.ink 不支持）：

```
正确：S1 --> M、S2 --> M、S3 --> M（拆成独立边）
错误：S1 & S2 & S3 --> M
```

## 7. 类图（classDiagram）规范

类名含中文/特殊字符时用双引号包裹；关系标签用 `: "标签"` 语法（不是 `|"标签"|`）：

```
正确：
class "智能体Agent" {
    +观察Observe()
    +行动Act()
}
"智能体Agent" o-- "AgentLoop" : "由核心循环驱动"
"决策策略" <|-- "ReAct" : "继承关系"

错误：
class 智能体Agent { }
智能体Agent o-- AgentLoop : 由核心循环驱动
```

## 语法审查清单（生成后逐条检查）

生成 Mermaid 代码后，必须逐条自检以下内容：

- [ ] 所有含特殊字符的 label 都加了双引号？（空格、()、&、"、中文括号、+、/、→等）
- [ ] 箭头/关系标签用了 `|"xxx"|` 语法？（严禁 `-- "xxx" -->` / `-.中文.->` / `-. "xxx" .->`；classDiagram 用 `: "xxx"`）
- [ ] 边的起点/终点是节点 ID 而非 subgraph ID？
- [ ] **所有跨 subgraph 连线是否都在 `end` 之后？subgraph 内部只能有本组成员之间的连线**
- [ ] 所有节点 ID 是否已定义？（包括跨 subgraph 引用的节点）
- [ ] 中文括号、`&`、`()`、`+` 是否都在引号内？
- [ ] 是否使用了 `&` 多源合并语法？
- [ ] 节点数超过 15 时是否用了 subgraph 分组？
- [ ] subgraph ID 是否为纯英文（无特殊字符）？

**发现任一问题，必须自动修正后重新输出完整代码。**
