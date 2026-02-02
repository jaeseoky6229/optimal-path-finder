import os
import sys
import json
from typing import Dict

def app_root_dir() -> str:
    """
    onedir 빌드에서:
      - sys.executable = .../최적경로계산.exe (또는 main_program.exe)
      - 설정파일은 exe와 같은 폴더에 둔다: <exe폴더>/config.json
    소스 실행 시:
      - 프로젝트 루트(= main_program.py가 있는 폴더)를 기준으로 본다.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def load_config(config_path: str = None) -> Dict[str, str]:
    root = app_root_dir()
    path = config_path or os.path.join(root, "config.json")

    cfg = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

    def pick(key: str, default: str = "") -> str:
        # 환경변수 우선 → config.json → default
        return (os.getenv(key) or cfg.get(key) or default).strip()

    return {
        "KAKAO_REST_API_KEY": pick("KAKAO_REST_API_KEY"),
        "KAKAO_JS_API_KEY": pick("KAKAO_JS_API_KEY"),
        "_CONFIG_PATH": path,
        "_CONFIG_FOUND": "1" if os.path.exists(path) else "0",
    }
