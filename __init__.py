import os
import sys
import json
import subprocess
import threading
import queue
import time
import platform

from mcdreforged.api.all import *
from mcdreforged.api.all import Literal, Text, GreedyText

# ========== 全局变量 ==========
mirror_processes = {}          # server_key -> subprocess.Popen对象
server_stdin = {}              # server_key -> 标准输入写入器
server_output_queues = {}      # server_key -> 输出队列
config = {}                    # 配置数据
mcdr_root = os.getcwd()
mcdr_server = None             # 将在 on_load 中赋值，供日志记录使用

# ========== 工具函数 ==========

if sys.platform == 'win32':
    MCDR_Command = 'python -m mcdreforged init&&python -m mcdreforged'
else:
    MCDR_Command = 'python3 -m mcdreforged init&&python3 -m mcdreforged'

PLUGIN_METADATA = {
    'id': 'mcdr_server_pivot',
    'version': '1.0.0',
    'name': 'MCDR-Server-Pivot',
    'description': 'MCDR 服务器枢纽',
    'author': 'MulBerry',
    'dependencies': {'mcdreforged': '>=2.14.1'}
}

DEFAULT_CONFIG = {
    "config": {
        "enable": False,
        "permission": {
            "main": 1,
            "help": 0,
            "servers": 0,
            "s": 2,
            "start": 2,
            "stop": 2,
            "kill": 2,
            "restart": 2,
            "command": 2,
            "mcdr": 2
        }
    },
    "servers": {
        "mirror": {
            "auto_start": False,
            "path": "./mirror",
            "command": MCDR_Command
        }
    }
}

help_msg = '''§6!!msp §r- 主菜单
§6!!msp help §r- 查询所有msp命令
§6!!msp servers §r- 列出所有服务器并显示状态
§6!!msp s <服务器名> §r- 查看服务器状态与操作帮助
§6!!msp s <服务器名> mcdr §r- 启动MCDR(等同于发送 mcdrforged )
§6!!msp s <服务器名> start §r- 通过MCDR启动服务器(等同于发送 !!MCDR server start )
§6!!msp s <服务器名> stop §r- 通过MCDR停止服务器但不退出MCDR(等同于发送 !!MCDR server stop )
§6!!msp s <服务器名> kill §r- 杀死服务器进程(等同于发送 !!MCDR server kill )
§6!!msp s <服务器名> restart §r- 重启服务器
§6!!msp s <服务器名> <命令> §r- 向服务器终端发送命令'''

#  配置加载
def config_load():
    global config
    path = './config/MCDR-Server-Pivot.json'
    try:
        with open(path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        config = DEFAULT_CONFIG.copy()
    except json.JSONDecodeError:
        config = DEFAULT_CONFIG.copy()

#  子进程管理
def start_server(server_key, source=None):
    global mirror_processes, server_stdin, server_output_queues, mcdr_server
    try:
        if server_key in mirror_processes and mirror_processes[server_key].poll() is None:
            reply(source, f'§6服务器 {server_key} 已在运行')
            return
        cfg = config['servers'][server_key]
        cmd = cfg['command']
        rel_path = cfg.get('path', '.')
        work_dir = os.path.join(mcdr_root, rel_path)
        os.makedirs(work_dir, exist_ok=True)

        # 启动子进程，创建管道
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1' 
        proc = subprocess.Popen(
            cmd,
            cwd=work_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env
        )
        mirror_processes[server_key] = proc
        server_stdin[server_key] = proc.stdin
        out_queue = queue.Queue()
        server_output_queues[server_key] = out_queue

        # 读取线程：持续读取输出，放入队列并写入主日志
        def reader_thread(proc, queue, sk):
            try:
                for line in iter(proc.stdout.readline, ''):
                    line = line.rstrip().lstrip()
                    # 跳过空行
                    if not line:
                        continue
                    # 跳过单独的输入提示符 ">"
                    if line == '>':
                        continue
                    queue.put(line)
                    print(line)
            except Exception:
                pass
            finally:
                queue.put(None)

        t = threading.Thread(target=reader_thread, args=(proc, out_queue, server_key), daemon=True)
        t.start()

        # 启动后立即收集初始输出并显示给用户（source）
        if source is not None:
            time.sleep(0.3)  # 等待读取线程捕获初始输出
            initial_lines = []
            while True:
                try:
                    line = out_queue.get_nowait()
                    if line is None:
                        break
                    initial_lines.append(line)
                except queue.Empty:
                    break
            for line in initial_lines:
                reply(source, line)

        reply(source, f'§a服务器 {server_key} 启动成功')
    except Exception as e:
        reply(source, f'§c启动失败: {e}')

def autostart_servers(server):
    for k, v in config.get('servers', {}).items():
        if v.get('auto_start'):
            server.logger.info(f'自动启动 {k}')
            start_server(k, None)

# ========== 命令发送 ==========
def send_command(server_key, cmd, timeout=10.0):
    proc = mirror_processes.get(server_key)
    stdin_writer = server_stdin.get(server_key)
    out_queue = server_output_queues.get(server_key)
    if not proc or proc.poll() is not None:
        raise Exception(f"服务器 {server_key} 未运行")
    if not stdin_writer or stdin_writer.closed:
        raise Exception(f"服务器 {server_key} 的标准输入已关闭，请kill后重启服务器")

    # 清空队列中残留的数据
    while True:
        try:
            out_queue.get_nowait()
        except queue.Empty:
            break

    stdin_writer.write(cmd + '\n')
    stdin_writer.flush()

    # 等待命令执行完成（不输出任何行，输出已由 reader_thread 记录到日志）
    lines = []
    start = time.time()
    last_active = start
    while time.time() - start < timeout:
        try:
            line = out_queue.get(timeout=0.2)
            if line is None:
                break
            lines.append(line)
            last_active = time.time()
        except queue.Empty:
            if lines and (time.time() - last_active) > 1.5:
                break
    return

def reply(src, msg):
    if src and hasattr(src, 'reply'):
        src.reply(msg)
    else:
        print(msg)

# 命令回调
def cmd_main(src, ctx):
    src.reply('§6=== 欢迎使用 MCDR-Server-Pivot ===')
    src.reply(f'§b名称: §r{PLUGIN_METADATA["name"]}')
    src.reply(f'§b版本: §r{PLUGIN_METADATA["version"]}')
    src.reply(f'§b作者: §r{PLUGIN_METADATA["author"]}')
    src.reply('')
    src.reply('§6!!msp help §r- 查询所有msp命令')
    src.reply('§6!!msp s §r- 列出所有服务器并显示状态')
    src.reply('§6!!msp s <服务器名> §r- 查看服务器状态与操作帮助')

def cmd_help(src, ctx):
    for line in help_msg.splitlines():
        src.reply(line)

def cmd_servers(src, ctx):
    servers = config.get('servers', {})
    if not servers:
        src.reply('')
        src.reply('§c===当前没有服务器配置===')
        src.reply('')
        return
    src.reply('§6服务器状态:')
    max_len = max(len(name.encode('gb2312', errors='ignore')) for name in servers.keys())
    for name, cfg in servers.items():
        status = '§a运行中' if mirror_processes.get(name) and mirror_processes[name].poll() is None else '§c未运行'
        src.reply(f'{name.ljust(max_len)} | {status}')

def cmd_server_info(src, ctx):
    key = ctx['server_key']
    servers = config.get('servers', {})
    if key not in servers:
        src.reply(f'§c服务器 {key} 不存在')
        return
    cfg = servers[key]
    status = '§a运行中' if mirror_processes.get(key) and mirror_processes[key].poll() is None else '§c未运行'
    src.reply(f'§6服务器: {key} ———— {status}')
    src.reply(f'§6路径: §r{cfg.get("path", ".")}')
    src.reply('§6可用命令:')
    src.reply('§6!!msp s <服务器名> mcdr §r- 启动MCDR(等同于发送 mcdrforged )')
    src.reply('§6!!msp s <服务器名> start §r- 通过MCDR启动服务器(等同于发送 !!MCDR server start )')
    src.reply('§6!!msp s <服务器名> stop §r- 通过MCDR停止服务器但不退出MCDR(等同于发送 !!MCDR server stop )')
    src.reply('§6!!msp s <服务器名> kill §r- 杀死服务器进程(等同于发送 !!MCDR server kill )')
    src.reply('§6!!msp s <服务器名> restart §r- 重启服务器')
    src.reply('§6!!msp s <服务器名> <命令> §r- 向服务器终端发送命令')

def check_process_running(server_key, src) -> bool:
    proc = mirror_processes.get(server_key)
    if not proc or proc.poll() is not None:
        reply(src, f'§c服务器 {server_key} 的 MCDR 进程未运行')
        reply(src, f'§c请使用 §6!!msp s {server_key} mcdr §c启动')
        return False
    return True

def cmd_start(src, ctx):
    key = ctx['server_key']
    if not check_process_running(key, src):
        return
    src.reply(f'正在通过MCDR启动 {key}...')
    send_command(key, "!!MCDR server start", timeout=10.0)

def cmd_stop(src, ctx):
    key = ctx['server_key']
    if not check_process_running(key, src):
        return
    src.reply(f'正在通过MCDR停止 {key}...')
    send_command(key, "!!MCDR server stop", timeout=10.0)

def cmd_kill(src, ctx):
    key = ctx['server_key']
    if not check_process_running(key, src):
        return
    src.reply(f'正在杀死该MCDR {key}...')
    send_command(key, "!!MCDR server kill", timeout=10.0)

def cmd_command(src, ctx):
    key = ctx['server_key']
    if not check_process_running(key, src):
        return
    cmd = ctx['command']
    src.reply(f'向 {key} 发送命令: {cmd}')
    try:
        send_command(key, cmd, timeout=10)
    except Exception as e:
        src.reply(f'§c发送命令失败: {e}')

def cmd_restart(src, ctx):
    key = ctx['server_key']
    proc = mirror_processes.get(key)
    # 检测进程是否存在且正在运行
    if proc and proc.poll() is None:
        # 进程存在，先 kill
        src.reply(f'正在终止现有 MCDR 进程 {key}...')
        try:
            send_command(key, "!!MCDR server kill", timeout=10.0)
        except Exception as e:
            src.reply(f'§e通过命令终止失败，尝试强制杀死进程...')
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            if key in mirror_processes:
                del mirror_processes[key]
            if key in server_stdin:
                del server_stdin[key]
            if key in server_output_queues:
                del server_output_queues[key]
            src.reply('§a进程已被强制终止')
        src.reply(f'正在启动 {key} 进程...')
    else:
        src.reply(f'§e未检测到运行中的 {key} 进程，直接启动...')
    start_server(key, src)

def cmd_mcdr(src, ctx):
    key = ctx['server_key']
    src.reply(f'正在启动 {key}进程...')
    start_server(key, src)

# ========== 插件入口 ==========
def on_load(server: PluginServerInterface, old):
    global mcdr_server
    mcdr_server = server
    config_load()
    autostart_servers(server)
    server.register_help_message('!!msp', 'MCDR-Server-Pivot 服务器枢纽')

    # 辅助函数：返回一个检查指定命令权限的 lambda
    def need(perm_name: str):
        level = get_permission_level(perm_name)
        return lambda src: src.has_permission(level)

    server.register_command(
        Literal('!!msp')
        .requires(need('main'))
        .runs(cmd_main)
        .then(
            Literal('help')
            .requires(need('help'))
            .runs(cmd_help)
        )
        .then(
            Literal('servers')
            .requires(need('servers'))
            .runs(cmd_servers)
        )
        .then(
            Literal('s')
            .requires(need('s'))
            .runs(cmd_servers)
            .then(
                Text('server_key')
                .requires(need('s_info'))
                .runs(cmd_server_info)
                .then(
                    Literal('mcdr')
                    .requires(need('mcdr'))
                    .runs(cmd_mcdr)
                )
                .then(
                    Literal('start')
                    .requires(need('start'))
                    .runs(cmd_start)
                )
                .then(
                    Literal('stop')
                    .requires(need('stop'))
                    .runs(cmd_stop)
                )
                .then(
                    Literal('kill')
                    .requires(need('kill'))
                    .runs(cmd_kill)
                )
                .then(
                    Literal('restart')
                    .requires(need('restart'))
                    .runs(cmd_restart)
                )
                .then(
                    GreedyText('command')
                    .requires(need('command'))
                    .runs(cmd_command)
                )
            )
        )
    )
    server.logger.info('MCDR-Server-Pivot 加载完成')
