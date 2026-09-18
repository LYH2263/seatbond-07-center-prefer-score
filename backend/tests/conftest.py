"""测试环境：在导入 app 之前用 sqlite 覆盖数据库配置。"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SEED_ON_EMPTY", "false")
