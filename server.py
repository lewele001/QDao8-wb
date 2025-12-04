# server.py
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Set
from collections import defaultdict

import websockets
from websockets.exceptions import ConnectionClosed

from config import config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        # 用户ID -> WebSocket连接映射
        self.user_connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        # 连接ID -> 用户ID映射
        self.connection_users: Dict[str, str] = {}
        # 用户频道订阅
        self.user_channels: Dict[str, Set[str]] = defaultdict(set)
        # 活跃用户列表
        self.active_users: Dict[str, datetime] = {}

    async def register(self, websocket: websockets.WebSocketServerProtocol, user_id: str):
        """注册用户连接"""
        connection_id = str(uuid.uuid4())
        self.connection_users[connection_id] = user_id
        self.user_connections[user_id] = websocket
        self.active_users[user_id] = datetime.now()
        
        logger.info(f"用户 {user_id} 已连接, 连接ID: {connection_id}")
        return connection_id

    async def unregister(self, user_id: str, connection_id: str = None):
        """注销用户连接"""
        if user_id in self.user_connections:
            del self.user_connections[user_id]
        
        if connection_id and connection_id in self.connection_users:
            del self.connection_users[connection_id]
        
        if user_id in self.active_users:
            del self.active_users[user_id]
        
        logger.info(f"用户 {user_id} 已断开连接")

    async def send_to_user(self, user_id: str, message: dict):
        """发送消息给指定用户"""
        if user_id in self.user_connections:
            try:
                websocket = self.user_connections[user_id]
                await websocket.send(json.dumps(message))
                return True
            except ConnectionClosed:
                logger.warning(f"向用户 {user_id} 发送消息失败，连接已关闭")
                await self.unregister(user_id)
                return False
        return False

    async def broadcast(self, message: dict, exclude_user: str = None):
        """广播消息给所有用户"""
        tasks = []
        for user_id, websocket in self.user_connections.items():
            if user_id != exclude_user:
                try:
                    tasks.append(websocket.send(json.dumps(message)))
                except ConnectionClosed:
                    continue
        if tasks:
            await asyncio.gather(*tasks)

    def get_online_users(self):
        """获取在线用户列表"""
        return list(self.active_users.keys())

    def update_user_activity(self, user_id: str):
        """更新用户活跃时间"""
        self.active_users[user_id] = datetime.now()


class MessageHandler:
    @staticmethod
    def create_message(msg_type: str, data: dict, sender: str = None):
        """创建标准消息格式"""
        message = {
            "type": msg_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "message_id": str(uuid.uuid4())
        }
        if sender:
            message["sender"] = sender
        return message

    @staticmethod
    def validate_message(message: dict) -> bool:
        """验证消息格式"""
        required_fields = ["type", "data", "timestamp"]
        return all(field in message for field in required_fields)


# 全局管理器实例
ws_manager = WebSocketManager()
message_handler = MessageHandler()


async def authenticate(message: dict) -> str:
    """
    用户认证
    实际应用中应替换为JWT或其他认证方式
    """
    if message.get("type") == "auth":
        user_id = message.get("data", {}).get("user_id")
        token = message.get("data", {}).get("token")
        
        # 这里简化认证，实际应验证token
        if user_id and token:
            # 验证token逻辑（示例）
            return user_id
    return None


async def handle_message(websocket: websockets.WebSocketServerProtocol, path: str):
    """处理WebSocket连接"""
    user_id = None
    connection_id = None
    
    try:
        # 等待认证消息
        auth_message = await asyncio.wait_for(websocket.recv(), timeout=10)
        auth_data = json.loads(auth_message)
        
        # 认证用户
        user_id = await authenticate(auth_data)
        if not user_id:
            await websocket.send(json.dumps({
                "type": "error",
                "data": {"message": "认证失败"}
            }))
            return
        
        # 注册连接
        connection_id = await ws_manager.register(websocket, user_id)
        
        # 发送连接成功消息
        welcome_msg = message_handler.create_message(
            "connection_established",
            {"user_id": user_id, "connection_id": connection_id}
        )
        await websocket.send(json.dumps(welcome_msg))
        
        # 通知其他用户（可选）
        await ws_manager.broadcast(
            message_handler.create_message(
                "user_online",
                {"user_id": user_id},
                sender="system"
            ),
            exclude_user=user_id
        )
        
        logger.info(f"用户 {user_id} 认证成功，开始监听消息...")
        
        # 主消息循环
        async for message in websocket:
            try:
                data = json.loads(message)
                
                if not message_handler.validate_message(data):
                    continue
                
                # 更新用户活跃时间
                ws_manager.update_user_activity(user_id)
                
                msg_type = data["type"]
                
                if msg_type == "ping":
                    # 心跳响应
                    await websocket.send(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    }))
                
                elif msg_type == "send_message":
                    # 发送消息给其他用户
                    target_user = data["data"].get("target_user")
                    content = data["data"].get("content")
                    
                    if target_user and content:
                        # 创建消息
                        msg = message_handler.create_message(
                            "new_message",
                            {
                                "content": content,
                                "from_user": user_id,
                                "to_user": target_user
                            },
                            sender=user_id
                        )
                        
                        # 发送给目标用户
                        success = await ws_manager.send_to_user(target_user, msg)
                        
                        # 回执给发送者
                        receipt = message_handler.create_message(
                            "message_receipt",
                            {
                                "message_id": data.get("message_id"),
                                "status": "delivered" if success else "failed",
                                "target_user": target_user
                            }
                        )
                        await websocket.send(json.dumps(receipt))
                
                elif msg_type == "subscribe":
                    # 订阅频道
                    channel = data["data"].get("channel")
                    if channel:
                        ws_manager.user_channels[user_id].add(channel)
                
                elif msg_type == "unsubscribe":
                    # 取消订阅
                    channel = data["data"].get("channel")
                    if channel and channel in ws_manager.user_channels[user_id]:
                        ws_manager.user_channels[user_id].remove(channel)
                
                elif msg_type == "get_online_users":
                    # 获取在线用户列表
                    online_users = ws_manager.get_online_users()
                    response = message_handler.create_message(
                        "online_users",
                        {"users": online_users}
                    )
                    await websocket.send(json.dumps(response))
                
            except json.JSONDecodeError:
                logger.error(f"消息JSON解析失败: {message}")
            except Exception as e:
                logger.error(f"处理消息时出错: {e}")
    
    except asyncio.TimeoutError:
        logger.warning("连接认证超时")
    except ConnectionClosed:
        logger.info("连接已关闭")
    except Exception as e:
        logger.error(f"连接处理错误: {e}")
    finally:
        if user_id:
            await ws_manager.unregister(user_id, connection_id)
            # 通知其他用户离线
            await ws_manager.broadcast(
                message_handler.create_message(
                    "user_offline",
                    {"user_id": user_id},
                    sender="system"
                ),
                exclude_user=user_id
            )


async def health_check():
    """健康检查，清理不活跃连接"""
    while True:
        await asyncio.sleep(60)  # 每分钟检查一次
        now = datetime.now()
        inactive_users = []
        
        for user_id, last_active in ws_manager.active_users.items():
            if (now - last_active).seconds > config.CONNECTION_TIMEOUT:
                inactive_users.append(user_id)
        
        for user_id in inactive_users:
            logger.info(f"清理不活跃用户: {user_id}")
            await ws_manager.unregister(user_id)


async def main():
    """启动WebSocket服务器"""
    # 启动健康检查任务
    asyncio.create_task(health_check())
    
    # 启动WebSocket服务器
    server = await websockets.serve(
        handle_message,
        config.HOST,
        config.PORT,
        ping_interval=config.HEARTBEAT_INTERVAL,
        ping_timeout=10,
        max_size=2**20  # 1MB最大消息大小
    )
    
    logger.info(f"WebSocket服务器启动在 ws://{config.HOST}:{config.PORT}")
    
    try:
        await server.wait_closed()
    except KeyboardInterrupt:
        logger.info("服务器关闭")


if __name__ == "__main__":
    asyncio.run(main())