from flask import Flask, request
from flask_cors import CORS
from config import Config
from extensions import db
from common.llm_config import LLMProviderConfig
from common.embedding_config import EmbeddingConfig
from modules.wiki.models import WikiPage
from modules.automation.models import AutomationTask, TaskRun
from modules.weather.models import WeatherConfig
from modules.tasks.models import Scenario, ScenarioNode, TaskState
from modules import (
    article_bp, chat_bp, folder_bp, picture_bp,
    home_bp, note_bp, todo_bp, plan_bp, settings_bp,
    agent_bp
)
app = Flask(__name__)
app.config.from_object(Config)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # 开发环境禁用静态文件缓存

@app.after_request
def _no_cache_static(response):
    """开发环境：静态文件禁用浏览器缓存"""
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

from modules.wiki import wiki_bp
from modules.weather import weather_bp
from modules.mcp import mcp_bp
from modules.mcp.client_routes import mcp_client_bp
from modules.automation import automation_bp
from modules.tasks import tasks_bp

CORS(app)

db.init_app(app)

app.register_blueprint(home_bp)
app.register_blueprint(article_bp)
app.register_blueprint(picture_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(folder_bp)
app.register_blueprint(note_bp)
app.register_blueprint(todo_bp)
app.register_blueprint(plan_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(wiki_bp)
app.register_blueprint(weather_bp)
app.register_blueprint(mcp_bp)
app.register_blueprint(mcp_client_bp)
app.register_blueprint(automation_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(agent_bp)

@app.route('/api')
def api_index():
    return {
        'name': 'SSEditor',
        'version': '1.0.0',
        'description': '个人知识管理系统',
        'api': '/api'
    }

with app.app_context():
    import os

    # Self-update：启动时异步检查代码更新和依赖变化（不阻塞启动）
    import threading
    def _async_self_update():
        try:
            from common.self_update import self_update
            update_logs = self_update()
            for log in update_logs:
                print(f'[SelfUpdate] {log}')
        except Exception as e:
            print(f'[SelfUpdate] 自更新失败（非致命）: {e}')
    threading.Thread(target=_async_self_update, name="self-update", daemon=True).start()

    # ===== 播种逻辑：智能同步 seed/ 到用户目录 =====
    # seed 有变化/新增 → 覆盖/追加；用户自建文件不删除
    def _seed_smart_sync(seed_dir, target_dir, label):
        """智能同步：seed 中有变化的文件覆盖更新，seed 中新增的直接追加，用户自建的保留不动。"""
        if not os.path.isdir(seed_dir):
            print(f"[Seed] {label} 播种源不存在，跳过: {seed_dir}")
            return

        os.makedirs(target_dir, exist_ok=True)
        import shutil
        import filecmp

        updated = 0
        added = 0

        for item in os.listdir(seed_dir):
            src = os.path.join(seed_dir, item)
            dst = os.path.join(target_dir, item)

            if os.path.isdir(src):
                # 目录：递归同步所有文件
                os.makedirs(dst, exist_ok=True)
                for root, _dirs, files in os.walk(src):
                    rel = os.path.relpath(root, src)
                    dst_root = os.path.join(dst, rel) if rel != '.' else dst
                    os.makedirs(dst_root, exist_ok=True)
                    for f in files:
                        sf = os.path.join(root, f)
                        df = os.path.join(dst_root, f)
                        if not os.path.exists(df):
                            shutil.copy2(sf, df)
                            added += 1
                        elif not filecmp.cmp(sf, df, shallow=False):
                            shutil.copy2(sf, df)
                            updated += 1
            else:
                # 文件
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    added += 1
                elif not filecmp.cmp(src, dst, shallow=False):
                    shutil.copy2(src, dst)
                    updated += 1

        if updated or added:
            print(f"[Seed] {label} 同步: +{added} 新增, ~{updated} 更新")
        else:
            print(f"[Seed] {label} 已是最新")

    _seed_smart_sync(
        os.path.join(Config.SEED_DIR, 'mcp'),
        Config.MCP_DIR,
        'MCP 服务')
    _seed_smart_sync(
        os.path.join(Config.SEED_DIR, 'skills'),
        Config.SKILLS_DIR,
        'Skills 技能')

    # ===== 创建目录 =====
    # 用户数据目录
    os.makedirs(Config.INSTANCE_PATH, exist_ok=True)

    # 用户内容目录
    _content_dirs = [
        app.config['ARTICLE_PATH'],
        app.config['IMAGE_PATH'],
        app.config['ATTACHMENT_PATH'],
        app.config['WIKI_PATH'],
    ]
    for d in _content_dirs:
        os.makedirs(d, exist_ok=True)

    # 子目录
    _subdirs = [
        os.path.join(app.config['ATTACHMENT_PATH'], 'chat_uploads'),
        os.path.join(app.config['ATTACHMENT_PATH'], 'file_exports'),
    ]
    for d in _subdirs:
        os.makedirs(d, exist_ok=True)
    db.create_all()

    # ===== 播种内置场景（智能体流水线定义）=====
    # 首次启动插入内置场景，之后用户可自由修改，不被覆盖。
    def _seed_scenarios():
        import json as _json
        builtins = [
            {
                'name': 'software_delivery', 'label': '写代码',
                'description': '从需求到开发交付的软件开发流水线',
                'nodes': [
                    ('requirement', '需求', '你是产品需求分析师。请把用户的诉求整理成清晰、可执行的需求文档，明确范围、目标与非目标。', True, ['*']),
                    ('prototype', '原型', '你是原型/架构设计师。请基于已确认需求，给出技术方案、数据结构与关键流程设计。', True, ['*']),
                    ('develop', '开发', '你是资深开发工程师。请基于已确认需求与设计，编写并落地代码。', True, ['*']),
                ],
            },
            {
                'name': 'ppt', 'label': '写 PPT',
                'description': '从主题到成稿的演示文稿制作流水线',
                'nodes': [
                    ('requirement', '需求', '你是演示策划。请明确演示主题、受众与核心观点。', True, ['*']),
                    ('outline', '大纲', '你是内容策划。请输出演示文稿的详细大纲与分页结构。', True, ['*']),
                    ('draft', '初稿', '你是文案撰写。请根据大纲撰写每一页的标题与正文要点。', False, ['*']),
                    ('polish', '润色', '你是演示美化顾问。请优化表达、提炼要点并检查逻辑连贯性。', True, ['*']),
                ],
            },
            {
                'name': 'todo_import', 'label': '导入待办',
                'description': '把一段文字解析并整理成结构化待办',
                'nodes': [
                    ('parse', '解析', '你负责从用户提供的文本中提取出所有待办事项。', False, ['*']),
                    ('organize', '整理', '你负责把提取出的待办去重、分类并补充优先级。', True, ['*']),
                    ('import', '导入', '你负责把整理好的待办写入待办系统。', True, ['*']),
                ],
            },
        ]
        for spec in builtins:
            if Scenario.query.filter_by(name=spec['name']).first():
                continue
            scenario = Scenario(
                name=spec['name'], label=spec['label'],
                description=spec['description'], is_builtin=True, is_active=True,
            )
            db.session.add(scenario)
            db.session.flush()
            for i, (key, name, role_prompt, gate, tools) in enumerate(spec['nodes']):
                db.session.add(ScenarioNode(
                    scenario_id=scenario.id, key=key, name=name,
                    role_prompt=role_prompt, gate=gate,
                    allowed_tools=_json.dumps(tools, ensure_ascii=False),
                    sort_order=i,
                ))
        db.session.commit()
        print('[Seed] 内置场景（智能体）已就绪')

    _seed_scenarios()

    import sqlite3
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    if os.path.isfile(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(wiki_page)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        migrations = [
            ('provenance_refs', "ALTER TABLE wiki_page ADD COLUMN provenance_refs TEXT DEFAULT '[]'"),
            ('review_status', "ALTER TABLE wiki_page ADD COLUMN review_status VARCHAR(20) DEFAULT 'approved'"),
            ('author', "ALTER TABLE wiki_page ADD COLUMN author VARCHAR(100) DEFAULT ''"),
        ]
        for col_name, sql in migrations:
            if col_name not in existing_columns:
                cursor.execute(sql)
                print(f"Migration: added column {col_name} to wiki_page")

        # todo_item 表迁移：合并 PlanItem，新增 status 字段
        cursor.execute("PRAGMA table_info(todo_item)")
        todo_cols = {row[1] for row in cursor.fetchall()}
        if 'status' not in todo_cols:
            cursor.execute("ALTER TABLE todo_item ADD COLUMN status TEXT DEFAULT 'todo'")
            print("Migration: added column status to todo_item")

        conn.commit()
        conn.close()

    # automation_task 表迁移
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='automation_task'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE automation_task (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(200) NOT NULL,
                    prompt TEXT NOT NULL,
                    mcp_servers VARCHAR(500) DEFAULT '',
                    cron_expression VARCHAR(100) DEFAULT '0 9 * * *',
                    start_date DATE,
                    end_date DATE,
                    is_active BOOLEAN DEFAULT 1,
                    last_run DATETIME,
                    last_result TEXT DEFAULT '',
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """)
            print("Migration: created table automation_task")
        else:
            cursor.execute("PRAGMA table_info(automation_task)")
            auto_cols = {row[1] for row in cursor.fetchall()}
            auto_migrations = [
                ('last_run', "ALTER TABLE automation_task ADD COLUMN last_run DATETIME"),
                ('last_result', "ALTER TABLE automation_task ADD COLUMN last_result TEXT DEFAULT ''"),
                ('start_date', "ALTER TABLE automation_task ADD COLUMN start_date DATE"),
                ('end_date', "ALTER TABLE automation_task ADD COLUMN end_date DATE"),
                ('cron_expression', "ALTER TABLE automation_task ADD COLUMN cron_expression VARCHAR(100) DEFAULT '0 9 * * *'"),
                ('mcp_servers', "ALTER TABLE automation_task ADD COLUMN mcp_servers VARCHAR(500) DEFAULT ''"),
                ('created_at', "ALTER TABLE automation_task ADD COLUMN created_at DATETIME"),
                ('updated_at', "ALTER TABLE automation_task ADD COLUMN updated_at DATETIME"),
                ('schedule_config', "ALTER TABLE automation_task ADD COLUMN schedule_config TEXT DEFAULT ''"),
            ]
            for col_name, sql in auto_migrations:
                if col_name not in auto_cols:
                    cursor.execute(sql)
                    print(f"Migration: added column {col_name} to automation_task")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Migration: automation_task table check failed (non-fatal): {e}")

    # automation_task_run 表迁移
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='automation_task_run'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE automation_task_run (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES automation_task(id) ON DELETE CASCADE,
                    started_at DATETIME,
                    finished_at DATETIME,
                    status VARCHAR(20) DEFAULT 'running',
                    result TEXT DEFAULT '',
                    trigger VARCHAR(20) DEFAULT 'manual'
                )
            """)
            print("Migration: created table automation_task_run")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Migration: automation_task_run table check failed (non-fatal): {e}")

    # scenario_node 表迁移：新增 skills 列（节点可选用 Skills）
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(scenario_node)")
        node_cols = {row[1] for row in cursor.fetchall()}
        if 'skills' not in node_cols:
            cursor.execute("ALTER TABLE scenario_node ADD COLUMN skills TEXT DEFAULT '[]'")
            print("Migration: added column skills to scenario_node")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Migration: scenario_node table check failed (non-fatal): {e}")

    # task_state 表迁移：新增 workspace 列（任务工作空间文件夹路径）
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(task_state)")
        ts_cols = {row[1] for row in cursor.fetchall()}
        if 'workspace' not in ts_cols:
            cursor.execute("ALTER TABLE task_state ADD COLUMN workspace TEXT DEFAULT ''")
            print("Migration: added column workspace to task_state")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Migration: task_state table check failed (non-fatal): {e}")

    # Phase 2: personal 模式下启动时尝试同步公共库
    if Config.INSTANCE_MODE == 'personal' and Config.COMMON_RESOURCE_PATH:
        try:
            from common.sync_service import sync_common_library_async
            sync_common_library_async()
            print(f"[Phase2] 公共库同步已启动 (mode={Config.INSTANCE_MODE})")
        except Exception as e:
            print(f"[Phase2] 公共库同步启动失败: {e}")

    # 定时任务调度器（SAP 物料同步等）
    try:
        from common.scheduler import init_scheduler
        init_scheduler(app)
        print("[Scheduler] 定时任务调度器已启动")
    except Exception as e:
        print(f"[Scheduler] 调度器启动失败（非致命）: {e}")

    # 内置服务（pdf-mcp 等，子进程拉起，异步不阻塞启动）
    # debug 模式下只在 werkzeug 的实际 worker 进程启动，避免 reloader 双开
    try:
        is_main_worker = (
            not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
        )
        if is_main_worker:
            from common.builtin_mcp_manager import init_all_async
            init_all_async()
    except Exception as e:
        print(f"[Builtin] 启动失败（非致命）: {e}")

    # DeepSeek Harness 自动拉起（auto_start）：后台线程启动，不阻塞应用启动
    try:
        if is_main_worker:
            from common import dsh_bridge
            if dsh_bridge.get_config().get('auto_start'):
                def _auto_start_dsh():
                    try:
                        result = dsh_bridge.start()
                        if not result.get('started'):
                            print(f"[DSH] 自动启动未成功: {result.get('error')}")
                    except Exception as _e:
                        print(f"[DSH] 自动启动失败（非致命）: {_e}")

                threading.Thread(target=_auto_start_dsh, name='dsh-auto-start', daemon=True).start()
                print("[DSH] auto_start 已开启，正在后台拉起")
    except Exception as e:
        print(f"[DSH] auto_start 检查失败（非致命）: {e}")

if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    debug = os.getenv('FLASK_DEBUG', '0') == '1'
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    app.run(host=host, port=port, debug=debug, threaded=True)
