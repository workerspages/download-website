"""
Playwright 版本的网站下载器
用于下载 SPA (单页应用) 网站，通过无头浏览器渲染页面并捕获所有网络资源
"""

import os
import sys
import logging
import argparse
from urllib.parse import urlparse, urljoin
from playwright.sync_api import sync_playwright

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class PlaywrightDownloader:
    def __init__(self, start_url, output_dir="downloaded_site", cookies=None, user_agent=None):
        self.start_url = start_url
        self.output_dir = output_dir
        self.cookies = cookies
        self.user_agent = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        self.downloaded_resources = set()
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 解析起始 URL 获取域名
        parsed = urlparse(start_url)
        self.base_domain = parsed.netloc
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"

    def get_local_path(self, url):
        """将 URL 转换为本地文件路径
        
        主站资源保持原路径，外部资源放到 _external/{domain}/ 目录
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace(':', '_')
            path = parsed.path
            
            # 处理空路径或目录
            if not path or path.endswith('/'):
                path = path + 'index.html'
            
            # 移除开头的斜杠
            if path.startswith('/'):
                path = path[1:]
            
            # 处理查询参数（用于某些动态资源）
            if parsed.query:
                # 将查询参数转为文件名的一部分
                safe_query = parsed.query.replace('?', '_').replace('&', '_').replace('=', '-')
                base, ext = os.path.splitext(path)
                if ext:
                    path = f"{base}_{safe_query}{ext}"
                else:
                    path = f"{path}_{safe_query}"
            
            # 判断是否为主站资源
            if domain == self.base_domain.replace(':', '_'):
                # 主站资源：直接使用路径
                return os.path.join(self.output_dir, path)
            else:
                # 外部资源：放到 _external/{domain}/ 目录
                return os.path.join(self.output_dir, "_external", domain, path)
        except Exception as e:
            logger.error(f"Error calculating local path for {url}: {e}")
            return os.path.join(self.output_dir, "_external", "unknown", "error.html")

    def save_resource(self, response):
        """保存网络响应到本地文件"""
        try:
            url = response.url
            status = response.status
            
            # 只处理成功的响应
            if status != 200:
                return
            
            # 跳过非 HTTP/HTTPS
            if not url.startswith(('http://', 'https://')):
                return
            
            # 跳过 data URI
            if url.startswith('data:'):
                return
            
            # 检查是否已下载
            if url in self.downloaded_resources:
                return
            
            self.downloaded_resources.add(url)
            
            # 获取本地路径
            local_path = self.get_local_path(url)
            
            # 跳过已存在的文件
            if os.path.exists(local_path):
                return
            
            # 创建目录
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # 获取响应内容
            try:
                content = response.body()
                logger.info(f"Saving: {url} -> {local_path}")
                
                with open(local_path, 'wb') as f:
                    f.write(content)
            except Exception as e:
                logger.warning(f"Failed to save {url}: {e}")
                
        except Exception as e:
            logger.error(f"Error in save_resource: {e}")

    def rewrite_html_links(self, html, page_url):
        """重写 HTML 中的资源链接为本地相对路径"""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, 'html.parser')
        page_local_path = self.get_local_path(page_url)
        page_dir = os.path.dirname(page_local_path)
        
        def get_relative_path(asset_url):
            """计算资源相对于页面的路径"""
            full_url = urljoin(page_url, asset_url)
            asset_local_path = self.get_local_path(full_url)
            rel_path = os.path.relpath(asset_local_path, page_dir)
            return rel_path.replace('\\', '/')
        
        # 处理 link 标签 (CSS)
        for link in soup.find_all('link', href=True):
            href = link['href']
            if href.startswith('data:') or href.startswith('javascript:'):
                continue
            full_url = urljoin(page_url, href)
            if full_url in self.downloaded_resources:
                link['href'] = get_relative_path(href)
        
        # 处理 script 标签 (JS)
        for script in soup.find_all('script', src=True):
            src = script['src']
            if src.startswith('data:') or src.startswith('javascript:'):
                continue
            full_url = urljoin(page_url, src)
            if full_url in self.downloaded_resources:
                script['src'] = get_relative_path(src)
        
        # 处理 img 标签
        for img in soup.find_all('img', src=True):
            src = img['src']
            if src.startswith('data:'):
                continue
            full_url = urljoin(page_url, src)
            if full_url in self.downloaded_resources:
                img['src'] = get_relative_path(src)
        
        return soup.prettify()

    def run(self):
        """执行下载"""
        logger.info(f"Starting Playwright download: {self.start_url}")
        
        with sync_playwright() as p:
            # 启动浏览器
            browser = p.chromium.launch(headless=True)
            
            # 创建上下文
            context_options = {
                'user_agent': self.user_agent,
                'viewport': {'width': 1920, 'height': 1080}
            }
            context = browser.new_context(**context_options)
            
            # 设置 Cookie
            if self.cookies:
                cookie_list = []
                for name, value in self.cookies.items():
                    cookie_list.append({
                        'name': name,
                        'value': value,
                        'domain': self.base_domain,
                        'path': '/'
                    })
                context.add_cookies(cookie_list)
            
            # 创建页面
            page = context.new_page()
            
            # 监听所有响应
            page.on("response", self.save_resource)
            
            try:
                # 导航到目标页面，等待网络空闲
                logger.info(f"Navigating to: {self.start_url}")
                page.goto(self.start_url, wait_until="networkidle", timeout=60000)
                
                # 等待额外时间确保动态内容加载
                page.wait_for_timeout(2000)
                
                # 获取渲染后的 HTML
                rendered_html = page.content()
                
                # 重写资源链接
                final_html = self.rewrite_html_links(rendered_html, self.start_url)
                
                # 保存 HTML
                html_path = self.get_local_path(self.start_url)
                os.makedirs(os.path.dirname(html_path), exist_ok=True)
                
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(final_html)
                
                logger.info(f"Saved HTML: {html_path}")
                logger.info(f"Total resources downloaded: {len(self.downloaded_resources)}")
                
            except Exception as e:
                logger.error(f"Failed to download page: {e}")
            finally:
                context.close()
                browser.close()
        
        logger.info("Download completed.")


def parse_cookies(cookie_string):
    """解析 Cookie 字符串"""
    cookies = {}
    if not cookie_string:
        return cookies
    
    for item in cookie_string.split(';'):
        if '=' in item:
            name, value = item.strip().split('=', 1)
            cookies[name] = value
    
    return cookies


if __name__ == "__main__":
    # 环境变量默认值
    env_url = os.environ.get("SITE_URL")
    env_output_dir = os.environ.get("OUTPUT_DIR", "downloaded_site")
    env_cookies = os.environ.get("COOKIES")

    parser = argparse.ArgumentParser(description="Playwright Website Downloader for SPA")
    
    if env_url:
        parser.add_argument("url", nargs="?", default=env_url, help="Target URL")
    else:
        parser.add_argument("url", help="Target URL")
    
    parser.add_argument("output_dir", nargs="?", default=env_output_dir, help="Output directory")
    parser.add_argument("--cookies", default=env_cookies, help="Cookies (key=value; key2=value2)")
    parser.add_argument("--user-agent", help="Custom User-Agent")
    
    args = parser.parse_args()
    
    print(f"Starting download: URL={args.url}, Output={args.output_dir}")
    
    cookies = parse_cookies(args.cookies) if args.cookies else None
    
    downloader = PlaywrightDownloader(
        args.url,
        args.output_dir,
        cookies=cookies,
        user_agent=args.user_agent
    )
    downloader.run()
