"""Flask 应用工厂。"""
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from nano_banana.web.blueprints import chat, config, images, presets


def _static_dir() -> Path:
    bundled = Path(__file__).resolve().parent / "static"
    if bundled.exists():
        return bundled
    return Path(__file__).resolve().parents[2] / "web" / "static"


def create_app() -> Flask:
    static_dir = _static_dir()
    app = Flask(__name__, static_folder=str(static_dir), static_url_path="/static")
    CORS(app)
    app.register_blueprint(config.bp)
    app.register_blueprint(presets.bp)
    app.register_blueprint(chat.bp)
    app.register_blueprint(images.bp)

    @app.route("/")
    def index():
        return send_from_directory(static_dir, "index.html")

    @app.route("/.well-known/appspecific/com.chrome.devtools.json")
    def chrome_devtools():
        return jsonify({})

    return app


app = create_app()


def main():
    static_dir = _static_dir()
    static_dir.mkdir(exist_ok=True)
    print("=" * 60)
    print("Nano Banana Prompt Tool - Web版本")
    print("=" * 60)
    print("服务器启动在: http://localhost:5000")
    print("按 Ctrl+C 停止服务器")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    main()
