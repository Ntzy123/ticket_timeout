import os
import sys
import json

# 打包后用可执行文件所在目录，开发时用脚本所在目录
BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(sys.argv[0]))

DEFAULT_CONFIG = {
    "headers": {
        "Host": "heimdallr.onewo.com",
        "Connection": "keep-alive",
        "sec-ch-ua-platform": "\"Windows\"",
        "Authorization": "sys:web:tokeneyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiLmnY7ku5Xnp5EiLCJ1c2VySWQiOiJjMTY3Y2Y5NDcwNGY0YjdhYWE4YjUzZGNmMmQ3Zjk4NSIsIm5pa2VOYW1lIjoi5p2O5LuV56eRIiwiY29tcGFueUlkIjoiMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAiLCJleHAiOjE3NDU3MTg5NDB9.j9I3R-kctxcB3CQzMSsBcUXa8OVes9ux5UedJzaWE8WWwOxKKCwRVWgHKubcu2aD-rdQFFQfZuRYMAieu3WAV-b8GrwIstAqydscpr9d20mEcGkQzc8-IWF0LeUFMOCOF7CWJzFNtFqZrCbDzijpYzV791vx-xT-r1r14tymd5s",
        "timestamp": "1745634203289",
        "type": "heimdallr",
        "sec-ch-ua": "\"Google Chrome\";v=\"135\", \"Not-A.Brand\";v=\"8\", \"Chromium\";v=\"135\"",
        "sec-ch-ua-mobile": "?0",
        "nonce": "8cba3dc2-1162-477e-8bb7-94d13b70c362",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "sign": "FuaZzyWV0dtWSLW4KraOAa3+STpKrDqmHjp5p5paF/O85W4G/X9z7NWsbn99DtX2fdeFnSNpT1gyWh01UK0NWh59KNLLQAB2RamPB9qCh8GdKSVwXUr97HOhx8FLkqcKxUZ+KsTgmDx00aI7A7OPXcyLh3ohiHtLnNhG8OOLe2YX0kgJQfBs1ieCIrucCNM6Zggq3Qvr9uBtUlUgSp+I1PNBcBofaicMhzas96yxi5lcXtI4oVRb+tHmha4RAI8FLhEJAO6wIJqVFMaYAiQh0BnEYyfqM6WsmDP4BVZyP2TnBG9nZs2SDNFQu0uozBlRMmL2nPRLnQ1wyxP954bVUw==",
        "systemId": "0e9e407230db4436a56ca1d0df23c255",
        "Need-Permission": "false",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "USER": "c167cf94704f4b7aaa8b53dcf2d7f985",
        "COMPANY": "00000000000000000000000000000000",
        "System-Tag": "web",
        "Origin": "https://heimdallr.onewo.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://heimdallr.onewo.com/remote-event-center-new/",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cookie": "acw_tc=0ae5a7e317456325190965284e006ab92915f016161e0b7b98f8c5fca780e5",
        "Accept-Encoding": "gzip, deflate",
        "Content-Length": "392"
    }
}


# ── 默认部门接单人配置 ────────────────────────────────
DEFAULT_ASSIGN_CONFIG_TOML = '''# =====================
# 部门接单人配置
# =====================
["保洁"]

["保洁".assignees."11号地"]
enabled = true
name = "张明金"
mobile = "15685306313"
userId = "2076797"

["保洁".assignees."6号地"]
enabled = true
name = "柏万碧"
mobile = "18985106736"
userId = "2078412"

["绿化"]

["绿化".assignees."11号地"]
enabled = true
name = "肖钰琴"
mobile = "15186950839"
userId = "2452500"

["绿化".assignees."6号地"]
enabled = true
name = "肖钰琴"
mobile = "15186950839"
userId = "2452500"

["安防"]
backups = [
  { name = "倪昌飞", mobile = "15120193103", userId = "1698342" },
  { name = "曾洪熙", mobile = "18585028903", userId = "1784302" },
]

["安防".assignees."11号地"]
enabled = false
name = "高海超"
mobile = "17623826232"
userId = "2390410"

["安防".assignees."6号地"]
enabled = false
name = "廖清山"
mobile = "18785152330"
userId = "2482763"
'''

# ── 默认管家配置 ──────────────────────────────────────
DEFAULT_BUTLER_CONFIG_TOML = '''# =====================
# 管家配置
# =====================
[[butlers]]
name = "赵中婧"
plot = "11号地"

[[butlers]]
name = "叶小玲"
plot = "11号地"

[[butlers]]
name = "李如玉"
plot = "11号地"

[[butlers]]
name = "余思奥"
plot = "6号地"

[[butlers]]
name = "纪雪婷"
plot = "6号地"

[[butlers]]
name = "王智勇"
plot = "6号地"
'''


def init_app():
    """检测并创建运行所需的配置文件"""
    config_dir = os.path.join(BASE_DIR, "config")
    os.makedirs(config_dir, exist_ok=True)

    config_path = os.path.join(config_dir, ".config.json")
    ignore_path = os.path.join(config_dir, "ignored.toml")
    assign_config_path = os.path.join(config_dir, "assign_config.toml")
    butler_config_path = os.path.join(config_dir, "butler_config.toml")
    history_path = os.path.join(config_dir, "auto_assign_history.json")

    if not os.path.exists(config_path):
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)

    if not os.path.exists(ignore_path):
        with open(ignore_path, "w", encoding="utf-8") as f:
            f.write("# 已忽略工单列表\n")

    if not os.path.exists(assign_config_path):
        with open(assign_config_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_ASSIGN_CONFIG_TOML.lstrip("\n"))

    if not os.path.exists(butler_config_path):
        with open(butler_config_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_BUTLER_CONFIG_TOML.lstrip("\n"))

    if not os.path.exists(history_path):
        with open(history_path, "w", encoding="utf-8") as f:
            f.write("[]\n")
