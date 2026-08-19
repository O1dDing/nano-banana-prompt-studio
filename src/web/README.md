# Web版本

## 使用

```bash
pip install -e ".[web]"
python src/web/start.py
# 或
python -m nano_banana.web.app
```

## docker

在项目根目录：

```bash
docker build -f web_dockerfile -t nano-banana-web:v0.3.0 .
docker run --rm --name nano-banana-web -p 5000:5000 nano-banana-web:v0.3.0
```
