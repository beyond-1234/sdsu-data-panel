# CLM-Microbe 科研数据管理、展示与分发平台

以 **CLM-Microbe** 为核心科学数据背景，融合 **LeafWeb** 交互式分析体系与 **GRooT** 典雅生态学 UI 规范的轻量级科研数据治理与分发系统。

---

## 🛠️ 技术栈与特性

- **后端体系**: Python 3.10+ / Flask, Flask-SQLAlchemy, Flask-Login, Werkzeug
- **前端风格**: 原生 HTML5 + CSS3 (CSS Grid / Flexbox) + 原生 Vanilla JS，遵循 GRooT 典雅学术深青墨绿规范，无重型前端打包构建流
- **数据交互可视化**: ECharts 5.4.3 原生接入，提供时序缩放 (DataZoom)、土壤剖面深层翻转渲染、Michaelis-Menten & Arrhenius 动力学滑块推演
- **数据源接入**: 支持 GitHub 远端仓库/Release 直链与本地服务器归档双渠道接入
- **科研分发合规**: 参照 FLUXNET / LeafWeb 协议，强制轻量级弹窗登记科研机构与使用目的，留存下载审计日志并提供统计看板

---

## 🚀 快速启动

### 1. 激活环境与依赖安装

```bash
# 如果使用 uv / venv
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 2. 启动服务与初始化数据库

```bash
python3 app.py
```
服务将在 `http://127.0.0.1:5001` 启动。启动时会自动执行种子数据填充（内置北极苔原样点数据、初始学科关键词库与管理员账号）。

### 3. 内置账号

| 角色 | 用户名 | 密码 | 权限范围 |
| --- | --- | --- | --- |
| **系统管理员** | `admin` | `admin123` | 全局数据管理、埋点统计看板、关键词库 CRUD |
| **科研用户** | `researcher` | `res123` | 数据集录入提交、数据下载、用途登记 |
| **访客** | *(无需登录)* | - | 检索过滤、交互式图表预览、元数据查看 |

---

## 📁 项目目录结构

```text
sdsu_data_panel/
├── app.py                  # 应用入口、路由与生命周期管理
├── config.py               # 安全密钥与路径配置
├── models.py               # SQLAlchemy 数据模型定义 (User, Dataset, Keyword, DownloadLog)
├── requirements.txt        # 依赖清单
├── services/
│   ├── data_parser.py      # 时序与土壤垂向剖面、酶动力学计算解析
│   └── stats_service.py    # 埋点日志与后台看板统计服务
├── static/
│   ├── css/
│   │   └── style.css       # GRooT 学术蓝灰侧边栏与卡片样式
│   ├── js/
│   │   ├── echarts.min.js  # 本地 ECharts 5.4.3 图表引擎
│   │   └── main.js         # 模态框与分发下载审计交互
│   └── uploads/            # 模拟与本地上传数据集存放目录
├── templates/
│   ├── base.html           # 固定左侧竖向导航母模版与全局下载模态框
│   ├── index.html          # 数据总览、多维组合检索与标签云
│   ├── detail.html         # 单数据集详情、时序 DataZoom、剖面图
│   ├── analysis.html       # LeafWeb 动力学参数实时滑块推演工作台
│   ├── upload.html         # 数据集提交与多源录入表单
│   ├── login.html          # 科研统一身份认证 (登录/注册)
│   └── admin/
│       ├── dashboard.html  # 埋点可视化看板 (走势/用途构成/日志流水)
│       └── keywords.html   # 全局科学关键词库维护
└── database.db             # 自动初始化的 SQLite 数据库
```
