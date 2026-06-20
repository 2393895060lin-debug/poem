# 古诗文搜索站点部署

这个项目不是纯静态网页，前端会请求 `server.py` 提供的 `/api/lookup` 接口，所以要按 Python Web 服务部署，不能只上传 `index.html`。

## 本地启动

```powershell
python -m pip install -r requirements.txt
python server.py
```

本地默认地址：

```text
http://127.0.0.1:8765
```

## 推荐部署方式

最省事的是部署到 Render 或 Railway。这两个平台都支持直接从 Git 仓库构建。

### 方式一：直接用 Docker 部署

项目已经带了 `Dockerfile`，直接把仓库推到 GitHub 后：

1. 在 Render 或 Railway 新建一个 Web Service。
2. 选择这个仓库。
3. 平台会自动识别 `Dockerfile` 并构建。
4. 部署完成后会给你一个公网域名，直接把那个链接发给别人即可。

## 环境变量

服务已经兼容云平台常见配置：

- `PORT`：云平台自动注入时会直接使用。
- `POEM_UI_HOST`：部署时建议是 `0.0.0.0`，Dockerfile 已经设置好了。
- `POEM_DATA_DIR`：可选，用来指定缓存和导出文件目录。

## 不想上云的临时分享

如果只是临时发给别人用，不想部署服务器，也可以在你自己电脑启动项目后，用 Cloudflare Tunnel 或 ngrok 暴露本地端口：

```powershell
python server.py
cloudflared tunnel --url http://127.0.0.1:8765
```

它会返回一个公网链接。你的电脑需要保持开机，链接才可用。

## 这次为部署做的改动

- `server.py` 已支持读取云平台的 `PORT`。
- 服务支持绑定 `0.0.0.0`，可以对外提供访问。
- 项目内新增了 `lookup_classical_text.py`，不再依赖你本机 `~/.codex/skills/...` 的脚本。
