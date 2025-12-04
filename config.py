# config.py
import os
from dataclasses import dataclass

@dataclass
class Config:
    HOST = "0.0.0.0"
    PORT = 8765
    SECRET_KEY = os.getenv("WS_SECRET_KEY", "your-secret-key-here")
    # 心跳间隔（秒）
    HEARTBEAT_INTERVAL = 30
    # 连接超时（秒）
    CONNECTION_TIMEOUT = 300
    # 最大连接数
    MAX_CONNECTIONS = 1000
    # Redis配置（可选，用于集群）
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

config = Config()