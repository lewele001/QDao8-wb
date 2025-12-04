# web_client.py
import asyncio
import os
from pathlib import Path
from aiohttp import web
import aiohttp_jinja2
import jinja2

routes = web.RouteTableDef()


@routes.get('/')
@aiohttp_jinja2.template('index.html')
async def index(request):
    """主页面"""
    return {'title': 'WebSocket客户端'}


@routes.get('/ws-test/{user_id}')
@aiohttp_jinja2.template('client.html')
async def ws_test(request):
    """WebSocket测试页面"""
    user_id = request.match_info['user_id']
    # 获取主机地址，支持外部访问
    host = request.host
    ws_host = request.headers.get('Host', 'localhost:8765').split(':')[0]
    ws_port = 8765
    
    return {
        'user_id': user_id,
        'ws_url': f'ws://{ws_host}:{ws_port}'
    }


@routes.get('/health')
async def health_check(request):
    """健康检查端点"""
    return web.json_response({'status': 'ok', 'service': 'websocket-web-client'})


async def init_app():
    """初始化应用"""
    app = web.Application()
    
    # 设置Jinja2模板
    current_dir = Path(__file__).parent
    templates_dir = current_dir / 'templates'
    
    # 确保模板目录存在
    if not templates_dir.exists():
        os.makedirs(templates_dir, exist_ok=True)
    
    aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader(str(templates_dir))
    )
    
    # 添加路由
    app.add_routes(routes)
    
    # 创建静态目录（如果不存在）
    static_dir = current_dir / 'static'
    if not static_dir.exists():
        os.makedirs(static_dir, exist_ok=True)
    
    # 添加静态文件服务
    app.router.add_static('/static/', path=str(static_dir), name='static')
    
    return app


async def main():
    """启动Web服务器"""
    app = await init_app()
    
    # 获取端口配置
    port = int(os.environ.get('PORT', 8080))
    host = os.environ.get('HOST', '0.0.0.0')
    
    # 启动服务器
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, host, port)
    
    print(f"📱 Web服务器启动在 http://{host}:{port}")
    print(f"📝 访问地址: http://{host}:{port}/")
    print(f"🔗 WebSocket服务器运行在: ws://{host}:8765")
    print("\n📋 快速开始:")
    print("1. 在PC端运行: python client_pc.py <用户ID>")
    print("2. 在浏览器访问: http://<服务器IP>:8080")
    print("3. 输入用户ID进入实时通信页面")
    print("4. 发送消息实现实时同步")
    print("\n按 Ctrl+C 停止服务器")
    
    await site.start()
    
    # 保持运行
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n服务器关闭")
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    # 设置asyncio事件循环策略
    if os.name == 'nt':  # Windows系统
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n服务器已停止")