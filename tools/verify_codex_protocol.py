#!/usr/bin/env python3
"""检查安装的官方 Codex 生成协议，不进行模型调用或登录。"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "/app/codex-protocol.json")
    version = subprocess.check_output(["codex", "--version"], text=True).strip()
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(["codex", "app-server", "generate-json-schema", "--out", directory], check=True,
                       stdout=subprocess.DEVNULL)
        files = {p.name: p for p in Path(directory).rglob("*.json")}
        def load(name):
            path = files.get(name)
            if not path:
                raise RuntimeError(f"Codex 协议缺少 {name}")
            return json.loads(path.read_text())
        thread = load("ThreadStartParams.json")
        turn = load("TurnStartParams.json")
        reply = load("ThreadStartResponse.json")
        account = load("GetAccountResponse.json") if "GetAccountResponse.json" in files else None
        if "ephemeral" not in thread.get("properties", {}):
            raise RuntimeError("Codex 不支持 ephemeral；拒绝创建会话历史")
        if "outputSchema" not in turn.get("properties", {}):
            raise RuntimeError("Codex 不支持结构化输出")
        all_text = "\n".join(p.read_text() for p in files.values())
        if '"ephemeral"' not in json.dumps(reply):
            raise RuntimeError("Codex thread 响应不确认 ephemeral")
        caps = {"ready": True, "version": version, "ephemeral": True, "output_schema": True,
                "interrupt": "TurnInterruptParams.json" in files,
                "image_generation": '"imageGeneration"' in all_text,
                "image_parameter_control": "prompt_hints_only", "transport": "stdio"}
        if not caps["interrupt"]:
            raise RuntimeError("Codex 不支持中断任务")
        output.write_text(json.dumps(caps, indent=2) + "\n")
        print(json.dumps(caps))


if __name__ == "__main__":
    main()
