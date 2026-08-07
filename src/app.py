from flask import Flask
from flask_cors import CORS
from config import Config
from extensions import db
from common.llm_config import LLMProviderConfig
from common.embedding_config import EmbeddingConfig
from modules.wiki.models import WikiPage
from modules.automation.models import AutomationTask, TaskRun
from modules.weather.models import WeatherConfig
from modules import (
    article_bp, chat_bp, folder_bp, picture_bp,
    home_bp, note_bp, todo_bp, plan_bp, settings_bp
)
app = Flask(__name__)
app.config.from_object(Config)

from modules.wiki import wiki_bp
from modules.weather import weather_bp
from modules.mcp import mcp_bp
from modules.mcp.client_routes import mcp_client_bp
from modules.automation import automation_bp

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

    directories = [
        app.config['ARTICLE_PATH'],
        app.config['IMAGE_PATH'],
        app.config['ATTACHMENT_PATH'],
        app.config['WIKI_PATH'],
        app.config['INSTANCE_PATH']
    ]
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")
    
    # 子目录：对话页导出、上传、MCP 服务 & Skills 存放
    _subdirs = [
        os.path.join(app.config['ATTACHMENT_PATH'], 'chat_uploads'),
        os.path.join(app.config['ATTACHMENT_PATH'], 'file_exports'),
        os.path.join(Config.RESOURCE_BASE_PATH, 'bin', 'mcp'),
        os.path.join(Config.RESOURCE_BASE_PATH, 'bin', 'skills'),
    ]
    for d in _subdirs:
        if not os.path.exists(d):
            os.makedirs(d)
            print(f"Created directory: {d}")
    db.create_all()

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

if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    debug = os.getenv('FLASK_DEBUG', '0') == '1'
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    app.run(host=host, port=port, debug=debug, threaded=True)
