# 网站整站下载脚本

这是一个基于 Python 的网站下载工具，可以下载指定网站的 HTML、CSS、JavaScript 和图片等资源，并保持目录结构，支持离线浏览。

## 功能特点

*   **资源下载**：自动识别并下载 `img`, `link`, `script` 标签中的资源。
*   **链接重写**：将 HTML 中的资源链接重写为本地相对路径。
*   **递归爬取**：支持指定深度的递归爬取（仅限同域名）。
*   **断点续传**：已下载的文件自动跳过。

## 快速开始

### 1. 安装依赖

确保已安装 Python 3.6+。

```bash
pip install -r requirements.txt
```

### 2. 运行脚本

```bash
python download_site.py <目标URL> [输出目录] [最大深度]
```

**参数说明：**

*   `<目标URL>`: 必填，要下载的网站首页地址（例如 `https://example.com`）。
*   `[输出目录]`: 选填，默认 `downloaded_site`。
*   `[最大深度]`: 选填，递归爬取深度，默认为 `1`（仅首页资产）。设置 `0` 只通过首页，设置 `>1` 会爬取链接。
*   `--cookies`: 选填，传入登录后的 Cookie 字符串。

### 示例

**1. 基本使用：**

下载 `example.com` 到 `my_site` 目录，深度为 1：

```bash
python download_site.py https://example.com my_site 1
```

**2. 登录下载（Cookie）：**

如果网站需要登录，请先在浏览器登录，按 `F12` 打开开发者工具，在“网络(Network)”面板刷新页面，点击第一个请求，复制请求头中的 `Cookie` 字段。

```bash
python download_site.py https://restricted-site.com my_site 1 --cookies "session_id=xyz; userid=123"
```

### 3. Docker 使用

可以通过 Docker 运行本工具，所有参数均支持环境变量配置。

*   `SITE_URL`: 目标 URL
*   `OUTPUT_DIR`: 输出目录（容器内路径）
*   `MAX_DEPTH`: 递归深度
*   `COOKIES`: Cookie 字符串

**构建镜像：**
```bash
docker build -t website-downloader .
```

**运行容器：**
```bash
docker run -v $(pwd)/downloaded_site:/app/downloaded_site -e SITE_URL="https://example.com" website-downloader
```

```bash
docker run -v $(pwd)/downloaded_site:/app/downloaded_site -e SITE_URL="https://example.com" website-downloader
```

### 4. Docker Compose 使用

使用 Docker Compose 可以更方便地管理配置，默认使用 `ghcr.io` 的预构建镜像。

1.  修改 `docker-compose.yml` 中的 `SITE_URL` 和其他环境变量。
2.  运行命令：

```bash
docker-compose up
```

### 5. GitHub Actions (CI/CD)

本项目配置了 GitHub Actions 自动构建并推送镜像到 **Docker Hub** 和 **GitHub Container Registry (GHCR)**。

**触发条件：**
*   推送到 `main` 分支：构建并推送 `latest` 标签。
*   推送 Tag (如 `v1.0.0`)：构建并推送对应版本标签。

**配置 Secrets：**
请在 GitHub 仓库的 `Settings` -> `Secrets and variables` -> `Actions` 中添加以下 Repository secrets：

*   `DOCKERHUB_USERNAME`: Docker Hub 用户名
*   `DOCKERHUB_TOKEN`: Docker Hub Access Token

## 注意事项

*   请遵守目标网站的 `robots.txt` 协议。
*   脚本仅供学习和个人备份使用，请勿用于非法抓取。
*   对于动态加载（AJAX）的内容，本脚本无法获取，只能下载静态 HTML 源码中的资源。
