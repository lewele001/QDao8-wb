# client_pc.py
import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import Optional

import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PCClient:
    def __init__(self, server_url: str, user_id: str, token: str = "demo-token"):
        self.server_url = server_url
        self.user_id = user_id
        self.token = token
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        
    async def connect(self):
        """连接到WebSocket服务器"""
        try:
            self.websocket = await websockets.connect(self.server_url)
            
            # 发送认证信息
            auth_message = {
                "type": "auth",
                "data": {
                    "user_id": self.user_id,
                    "token": self.token
                },
                "timestamp": datetime.now().isoformat()
            }
            
            await self.websocket.send(json.dumps(auth_message))
            
            # 等待认证响应
            response = await self.websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get("type") == "connection_established":
                logger.info(f"PC客户端 {self.user_id} 连接成功")
                return True
            else:
                logger.error("认证失败")
                return False
                
        except Exception as e:
            logger.error(f"连接失败: {e}")
            return False
    
    async def send_message(self, target_user: str, content: str):
        """发送消息给其他用户"""
        if not self.websocket:
            logger.error("未连接")
            return False
            
        message = {
            "type": "send_message",
            "data": {
                "target_user": target_user,
                "content": content
            },
            "timestamp": datetime.now().isoformat(),
            "message_id": f"msg_{datetime.now().timestamp()}"
        }
        
        try:
            await self.websocket.send(json.dumps(message))
            logger.info(f"消息已发送给 {target_user}: {content}")
            return True
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False
    
    async def listen_for_messages(self):
        """监听来自服务器的消息"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "new_message":
                    # 收到新消息
                    content = data["data"].get("content")
                    from_user = data["data"].get("from_user")
                    logger.info(f"\n📩 收到来自 {from_user} 的消息: {content}")
                    
                    # 这里可以触发PC客户端的UI更新
                    # 例如：显示通知、更新聊天界面等
                    
                elif msg_type == "message_receipt":
                    # 消息回执
                    status = data["data"].get("status")
                    target_user = data["data"].get("target_user")
                    logger.info(f"消息送达状态: {status} (目标用户: {target_user})")
                    
                elif msg_type == "user_online":
                    user_id = data["data"].get("user_id")
                    logger.info(f"👤 用户 {user_id} 上线")
                    
                elif msg_type == "user_offline":
                    user_id = data["data"].get("user_id")
                    logger.info(f"👤 用户 {user_id} 离线")
                    
                elif msg_type == "ping":
                    # 响应心跳
                    await self.websocket.send(json.dumps({"type": "pong"}))
                    
        except websockets.exceptions.ConnectionClosed:
            logger.error("连接已关闭")
            self.running = False
    
    async def heartbeat(self):
        """发送心跳保持连接"""
        while self.running:
            try:
                if self.websocket:
                    await self.websocket.send(json.dumps({"type": "ping"}))
                await asyncio.sleep(30)  # 每30秒发送一次心跳
            except Exception as e:
                logger.error(f"心跳发送失败: {e}")
                break
    
    async def run(self):
        """运行PC客户端"""
        if not await self.connect():
            return
            
        self.running = True
        
        # 启动心跳任务
        heartbeat_task = asyncio.create_task(self.heartbeat())
        
        # 启动消息监听
        listen_task = asyncio.create_task(self.listen_for_messages())
        
        try:
            # 模拟发送消息（在实际应用中，这里应该由用户界面触发）
            await asyncio.sleep(2)
            
            # 示例：自动发送一条测试消息
            if len(sys.argv) > 2:
                target_user = sys.argv[2]
                test_message = "Hello from PC client!"
                await self.send_message(target_user, test_message)
            
            # 保持运行
            await asyncio.gather(heartbeat_task, listen_task)
            
        except KeyboardInterrupt:
            logger.info("客户端关闭")
        finally:
            self.running = False
            if self.websocket:
                await self.websocket.close()


async def interactive_client(user_id: str, server_url: str = "ws://localhost:8765"):
    """交互式客户端"""
    client = PCClient(server_url, user_id)
    
    if not await client.connect():
        return
    
    print(f"\n✅ PC客户端 {user_id} 已连接")
    print("命令:")
    print("  send <目标用户> <消息>  - 发送消息")
    print("  users                  - 查看在线用户")
    print("  quit                   - 退出")
    print("-" * 50)
    
    # 启动监听任务
    listen_task = asyncio.create_task(client.listen_for_messages())
    
    try:
        while True:
            cmd = input("\n> ").strip()
            
            if cmd.lower() == "quit":
                break
                
            elif cmd.lower() == "users":
                # 获取在线用户
                message = {
                    "type": "get_online_users",
                    "timestamp": datetime.now().isoformat()
                }
                await client.websocket.send(json.dumps(message))
                
            elif cmd.startswith("send "):
                parts = cmd.split(" ", 2)
                if len(parts) >= 3:
                    target_user = parts[1]
                    content = parts[2]
                    await client.send_message(target_user, content)
                else:
                    print("用法: send <目标用户> <消息>")
                    
            else:
                print("未知命令")
                
    except KeyboardInterrupt:
        print("\n客户端关闭")
    finally:
        client.running = False
        if client.websocket:
            await client.websocket.close()
        listen_task.cancel()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python client_pc.py <用户ID> [目标用户]")
        print("示例: python client_pc.py user_pc user_mobile")
        sys.exit(1)
    
    user_id = sys.argv[1]
    
    # 运行交互式客户端
    asyncio.run(interactive_client(user_id))