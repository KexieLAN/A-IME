# AIME Backend - 智能上下文感知输入法后端

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AIME (AI-powered Input Method Engine)** 是一款基于端侧大模型的上下文感知输入法后端，专为 Windows 平台设计。通过本地部署的 Qwen2.5-1.5B-Instruct 模型，实现零配置、开箱即用的智能输入体验。

## 核心特性

### 上下文感知引擎
- **全局上下文抓取**：通过 Windows UIAutomation (UIA) 接口实时获取光标前文本，支持 Word、WPS、浏览器等主流应用
- **三级瀑布策略**：TextPattern → ValuePattern → Name 属性，确保跨应用兼容性
- **低延迟**：优化后上下文抓取耗时仅 ~1-10ms

### 两阶段推理架构
- **Phase 1 - 选择策略**：从原生候选词中智能选择最符合语境的词
- **Phase 2 - 生成策略**：当本地词库无匹配时，直接生成贴合上下文的专业词汇
- **拼音碰撞验证**：确保生成词与用户输入拼音基本吻合（相似度阈值 60%）

### 智能候选词重排
- **logprobs 打分**：基于模型 top-20 token 概率对候选词进行真实置信度排序
- **精确边界控制**：通过 `covered_length` 字段实现连续选词支持


## 技术架构

```
┌─────────────────┐    TCP Socket    ┌─────────────────────────────────────┐
│   Lua 前端      │ ◄──────────────► │         Python 后端                 │
│   (RIME Filter) │    127.0.0.1     │                                     │
└─────────────────┘     :5000        │  ┌─────────────┐ ┌───────────────┐ │
                                   │  │ UIA 上下文   │ │ 两阶段推理   │ │
                                   │  │ 看门狗线程   │ │ 引擎         │ │
                                   │  └─────────────┘ └───────────────┘ │
                                   │  ┌─────────────┐ ┌───────────────┐ │
                                   │  │ SQLite      │ │ llama.cpp     │ │
                                   │  │ 记忆体系     │ │ GPU 推理      │ │
                                   │  └─────────────┘ └───────────────┘ │
                                   └─────────────────────────────────────┘
```

### 工作流程

1. **输入拦截**：用户输入拼音 > 5 字符时触发 Lua Filter
2. **上下文获取**：后台看门狗线程每 500ms 更新全局上下文缓存
3. **AI 推理**：两阶段推理引擎生成候选词
4. **候选词重排**：基于 logprobs 对原生候选词进行置信度排序

## 快速开始

### 环境要求

- **操作系统**：Windows 10/11
- **Python**：3.12（推荐使用 `uv` 包管理器）
- **GPU**：支持 CUDA 的显卡（4G+ VRAM）
- **输入法**：小狼毫（需增加 Lua-socket 支持）

### 安装步骤

1. **克隆项目**
   ```bash
   git clone https://github.com/KexieLAN/A-IME.git
   cd A-IME
   ```

2. **安装依赖**
   ```bash
   # 使用 uv（推荐）
   uv sync
   
   # 或使用 pip
   pip install -e .
   ```

3. **下载模型**
   
   从 [Qwen2.5-1.5B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) 下载 Q4_K_M 量化版本，放置到 `F:/QWen/` 目录（或修改 `config/config.yaml` 中的路径）。

4. **配置 RIME 前端**
   
   将 `lua/candidate_collection.lua` 复制到 RIME 用户目录，并在 `.schema.yaml` 中添加：
   ```yaml
   filters:
     - lua_filter@candidate_collection
   ```

5. **启动后端**
   ```bash
   # 直接运行
   python main.py
   
   # 或使用 uv
   uv run python main.py
   ```

## 配置说明

所有配置集中在 `config/config.yaml`：

```yaml
# 大模型配置
model:
  path: "F:/QWen/qwen2.5-1.5b-instruct-q4_k_m.gguf"  # 模型路径
  n_ctx: 32768                                          # 上下文窗口
  n_gpu_layers: -1                                      # GPU 层数（-1 表示全量卸载）

# TCP 服务器
server:
  host: "127.0.0.1"
  port: 5000
  buffer_size: 4096

# UIA 上下文抓取
context:
  max_chars: 150          # 光标前抓取最大字符数
  poll_interval: 0.5      # 轮询间隔（秒）
  uia_timeout: 0.3        # UIA 搜索超时（秒）

# 推理引擎
inference:
  short_context_chars: 100    # 送入模型的上下文长度
  max_candidates: 5           # 发送给模型的候选词数量
  temperature: 0.0            # 贪心解码（确定性输出）
  max_tokens: 6               # 单次输出上限
  pinyin_threshold: 0.60      # 拼音碰撞相似度阈值

# 记忆体系
memory:
  db_path: "data/memory.db"
  max_records: 10000          # 最大记录数
  max_age_days: 30            # 记录保留天数
  cleanup_interval: 3600      # 清理间隔（秒）
```

## 项目结构

```
AIMEBackend/
├── main.py                          # 程序主入口
├── config/                          # 配置管理模块
│   ├── __init__.py                  # 配置加载器（单例模式）
│   └── config.yaml                  # YAML 配置文件
├── core/                            # 核心功能模块
│   ├── logger.py                    # 异步日志系统
│   ├── shutdown.py                  # 全局优雅退出事件
│   ├── context/                     # UIA 上下文抓取
│   ├── inference/                   # 两阶段推理引擎
│   ├── memory/                      # SQLite 记忆体系
│   ├── pinyin/                      # 拼音处理工具
│   └── server/                      # TCP 服务器
├── lua/                             # RIME Lua 前端
│   └── candidate_collection.lua     # 候选词重排与纠错捕获
├── data/                            # 数据目录（自动创建）
│   └── memory.db                    # SQLite 记忆数据库
├── logs/                            # 日志目录（自动创建）
├── etc/                             # 辅助工具与测试
├── pyproject.toml                   # Python 项目配置
└── 产品需求.md                       # 详细产品需求文档
```

## 性能指标

| 指标 | 目标 | 当前状态 |
|------|------|----------|
| 基础输入延迟 | < 30ms | ✅ 已达标 |
| UIA 上下文抓取 | < 20ms | ✅ ~1-10ms |
| TCP 通信超时 | 100ms | ⚠️ 当前 200ms |
| AI 推理总延迟 | 40-80ms | 🔧 取决于 GPU |

## 使用场景

### 场景 A：上下文感知选词
用户在前文提到"神经网络"，输入 `moxing` 时，系统自动将"模型"提升至 2 号位。

### 场景 B：拼音纠错
用户想输入"模型"但误打成 `mingxing`，AI 根据上下文选出"模型"而非默认的"明星"。

### 场景 C：词库穿透生成
撰写学术论文时，输入 `weijiandu`，即使本地词库未收录，AI 也能生成"微监督"等专业词汇。

### 场景 D：连续选词
输入 `damoxingxunlian`，选择"大模型"后，剩余拼音 `xunlian` 自动保留，可继续选择"训练"。

### 场景 E：个性化学习
用户手动纠正 AI 推荐词后，系统静默记录，下次在相似上下文中自动提权。

### 日志查看
运行日志保存在 `logs/aime.log`，支持日志轮转（10MB/文件，保留 3 个备份）。

## 未来路线图

### 近期优化
- [ ] TCP 通信超时从 200ms 优化至 100ms
- [ ] KV Cache 锚点块复用（推理耗时压制至 ~30ms）
- [ ] 拼音模糊音支持（z/zh、s/sh、an/ang 等）

### 中期规划
- [ ] Python 引擎打包为独立 exe 可执行文件
- [ ] 全量离线开箱即用部署方案
- [ ] 单步影子生成（零延迟纠错）

### 长期探索
- [ ] 模型升级路径（Qwen2.5-3B 或专用微调模型）
- [ ] 主动纠偏求助（Tab 触发深度语境解析）
- [ ] 多模型协作架构



## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

## 致谢

- [Qwen2.5](https://github.com/QwenLM/Qwen2.5) - 通义千问大语言模型
- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) - Python LLM 推理框架
- [RIME](https://rime.im/) - 中州韵输入法引擎
- [uiautomation](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows) - Windows UI 自动化库
