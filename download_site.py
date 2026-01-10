import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import logging
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class WebsiteDownloader:
    def __init__(self, start_url, output_dir="downloaded_site", max_depth=1, cookies=None):
        self.start_url = start_url
        self.output_dir = output_dir
        self.max_depth = max_depth
        self.visited_urls = set()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        if cookies:
            self.session.cookies.update(cookies)
        
        # 确保基础输出目录存在
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def is_valid_url(self, url):
        """检查URL是否属于同一个域名"""
        parsed_start = urlparse(self.start_url)
        parsed_url = urlparse(url)
        return parsed_url.netloc == parsed_start.netloc

    def get_local_path(self, url):
        """将URL转换为本地文件路径"""
        parsed_url = urlparse(url)
        path = parsed_url.path
        if not path or path.endswith('/'):
            path += 'index.html'
        
        # 移除开头的 /
        if path.startswith('/'):
            path = path[1:]
            
        return os.path.join(self.output_dir, path)

    def download_asset(self, url):
        """下载静态资源"""
        try:
            if not url:
                return None
                
            # 处理相对路径
            full_url = urljoin(self.start_url, url)
            
            # 简单的文件类型检查，避免下载无关内容
            if full_url.startswith('data:'):
                return url

            local_path = self.get_local_path(full_url)
            
            if os.path.exists(local_path):
                return os.path.relpath(local_path, self.output_dir) # 简化逻辑，暂返回相对路径，后续可能需要针对引用页面的相对路径
            
            # 确保目录存在
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            logger.info(f"Downloading asset: {full_url}")
            response = self.session.get(full_url, stream=True)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return full_url # 返回完整URL用于后续替换，或者直接返回相对路径？
                            # 这里更好的做法是：返回相对于当前HTML文件的路径。
                            # 为了简化，初步版本先下载，替换逻辑在 parse_and_save 中处理。
        except Exception as e:
            logger.error(f"Failed to download asset {url}: {e}")
            return url

    def process_page(self, url, current_depth):
        if current_depth > self.max_depth:
            return
        
        if url in self.visited_urls:
            return
        self.visited_urls.add(url)
        
        logger.info(f"Processing page: {url} (Depth: {current_depth})")
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. 处理 CSS (link)
            for link in soup.find_all('link', href=True):
                asset_url = link['href']
                full_asset_url = urljoin(url, asset_url)
                self.download_to_local(full_asset_url)
                # 重新链接
                link['href'] = self.get_relative_path(url, full_asset_url)

            # 2. 处理 JS (script)
            for script in soup.find_all('script', src=True):
                asset_url = script['src']
                full_asset_url = urljoin(url, asset_url)
                self.download_to_local(full_asset_url)
                script['src'] = self.get_relative_path(url, full_asset_url)

            # 3. 处理 图片 (img)
            for img in soup.find_all('img', src=True):
                asset_url = img['src']
                full_asset_url = urljoin(url, asset_url)
                self.download_to_local(full_asset_url)
                img['src'] = self.get_relative_path(url, full_asset_url)

            # 保存修改后的HTML
            local_path = self.get_local_path(url)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'w', encoding='utf-8') as f:
                f.write(soup.prettify())
            
            # 4. 递归处理链接 (a 标签)
            if current_depth < self.max_depth:
                for a in soup.find_all('a', href=True):
                    next_url = urljoin(url, a['href'])
                    # 移除fragment
                    next_url = next_url.split('#')[0]
                    
                    if self.is_valid_url(next_url):
                        # 修改链接指向本地文件
                        a['href'] = self.get_relative_path(url, next_url)
                        self.process_page(next_url, current_depth + 1)
                    # 如果是外部链接，保持不变

        except Exception as e:
            logger.error(f"Failed to process {url}: {e}")

    def download_to_local(self, url):
        """辅助方法：下载任意文件到本地对应的路径"""
        try:
            if not url:
                return
            
            # 跳过非HTTP/HTTPS链接和Data URI
            if url.startswith('data:') or not url.startswith(('http://', 'https://')):
                return

            local_path = self.get_local_path(url)
            if os.path.exists(local_path):
                return
            
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            logger.info(f"Downloading file: {url}")
            response = self.session.get(url, stream=True, timeout=10)
            if response.status_code == 200:
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
            else:
                logger.warning(f"Status {response.status_code} for {url}")
                
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")

    def get_relative_path(self, base_url, target_url):
        """计算两个URL对应本地文件的相对路径"""
        base_path = self.get_local_path(base_url)
        target_path = self.get_local_path(target_url)
        return os.path.relpath(target_path, os.path.dirname(base_path))

    def run(self):
        self.process_page(self.start_url, 0)
        logger.info("Download completed.")

def parse_cookies(cookie_string):
    """解析 Cookie 字符串，返回字典"""
    cookies = {}
    if not cookie_string:
        return cookies
    
    try:
        for item in cookie_string.split(';'):
            if '=' in item:
                name, value = item.strip().split('=', 1)
                cookies[name] = value
    except Exception as e:
        logger.error(f"Error parsing cookies: {e}")
        print("Warning: Failed to parse cookies string. Please use format 'key=value; key2=value2'")
    
    return cookies

if __name__ == "__main__":
    import argparse
    import os
    
    # 获取环境变量默认值
    env_url = os.environ.get("SITE_URL")
    env_output_dir = os.environ.get("OUTPUT_DIR", "downloaded_site")
    env_max_depth = os.environ.get("MAX_DEPTH", "1")
    env_cookies = os.environ.get("COOKIES")

    parser = argparse.ArgumentParser(description="Website Downloader")
    
    # URL 变为可选参数，如果 Env 中有值
    if env_url:
        parser.add_argument("url", nargs="?", default=env_url, help="Target URL (default from SITE_URL env)")
    else:
        parser.add_argument("url", help="Target URL")
        
    parser.add_argument("output_dir", nargs="?", default=env_output_dir, help="Output directory")
    parser.add_argument("max_depth", nargs="?", type=int, default=int(env_max_depth), help="Recursion depth (default: 1)")
    parser.add_argument("--cookies", default=env_cookies, help="Cookies string (e.g. 'key=value; key2=value2')")
    
    args = parser.parse_args()
    
    print(f"Starting download with: URL={args.url}, Output={args.output_dir}, Depth={args.max_depth}")
    
    cookies = parse_cookies(args.cookies) if args.cookies else None
    
    downloader = WebsiteDownloader(args.url, args.output_dir, args.max_depth, cookies=cookies)
    downloader.run()
