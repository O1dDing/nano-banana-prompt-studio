"""Web 启动脚本。"""
import sys
import threading
import time
import webbrowser

from nano_banana.web.app import main as run_server


def open_browser():
    time.sleep(2)
    webbrowser.open("http://localhost:5000")


def main():
    print("=" * 60)
    print("Nano Banana Prompt Tool - Web版本")
    print("=" * 60)
    if "--no-browser" not in sys.argv:
        threading.Thread(target=open_browser, daemon=True).start()
    run_server()


if __name__ == "__main__":
    main()
