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


def init_app():
    """检测并创建运行所需的配置文件"""
    config_path = os.path.join(BASE_DIR, ".config.json")
    ignore_path = os.path.join(BASE_DIR, "ignored.toml")

    if not os.path.exists(config_path):
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)

    if not os.path.exists(ignore_path):
        # 创建空文件（仅含注释头）
        with open(ignore_path, "w", encoding="utf-8") as f:
            f.write("# 已忽略工单列表\n")
