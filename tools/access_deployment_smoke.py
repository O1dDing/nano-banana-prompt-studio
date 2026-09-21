"""复用真实 Docker 迁移测试，启用 Access 配置/持久档案分支。"""
import os
from deployment_smoke import main

if __name__ == '__main__':
    os.environ['NANO_SMOKE_ACCESS'] = '1'
    main()
