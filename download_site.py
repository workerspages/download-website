import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import logging
import sys
from fake_useragent import UserAgent
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

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
        
        # Configure Retries
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Random User Agent
        try:
            ua = UserAgent()
            user_agent = ua.random
        except Exception:
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            
        logger.info(f"Using User-Agent: {user_agent}")

        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Referer': start_url
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
        """将URL转换为本地文件路径，包含域名以避免冲突"""
        try:
            parsed_url = urlparse(url)
            # 使用域名作为第一级目录
            domain = parsed_url.netloc
            path = parsed_url.path
            
            if not path or path.endswith('/'):
                path += 'index.html'
            
            # 移除开头的 /
            if path.startswith('/'):
                path = path[1:]
                
            # Windows文件系统对某些字符有限制，简单处理
            domain = domain.replace(':', '_')
            
            return os.path.join(self.output_dir, domain, path)
        except Exception as e:
            logger.error(f"Error calculating local path for {url}: {e}")
            # Fallback
            return os.path.join(self.output_dir, "unknown_domain", "error.html")

    def download_asset(self, url):
        """下载静态资源 (Legacy/Redirect to download_to_local)"""
        return self.download_to_local(url)

    def process_page(self, url, current_depth):
        if current_depth > self.max_depth:
            return
        
        if url in self.visited_urls:
            return
        self.visited_urls.add(url)
        
        logger.info(f"Processing page: {url} (Depth: {current_depth})")
        
        try:
            # 确保主页面也能正确下载
            local_path = self.get_local_path(url)
            
            response = self.session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Helper to handle asset processing
            def process_asset_link(tag, attr):
                asset_url = tag.get(attr)
                if not asset_url:
                    return
                
                full_asset_url = urljoin(url, asset_url)
                
                # Try to download
                if self.download_to_local(full_asset_url):
                    # Only rewrite if download successful (or file exists)
                    tag[attr] = self.get_relative_path(url, full_asset_url)
                else:
                    # Keep absolute URL if download fails so it might load from web
                    tag[attr] = full_asset_url

            # 1. 处理 CSS (link)
            for link in soup.find_all('link', href=True):
                process_asset_link(link, 'href')

            # 2. 处理 JS (script)
            for script in soup.find_all('script', src=True):
                process_asset_link(script, 'src')

            # 3. 处理 图片 (img)
            for img in soup.find_all('img', src=True):
                process_asset_link(img, 'src')

            # 保存修改后的HTML
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
                        # 对于页面链接，我们先计算相对路径
                        a['href'] = self.get_relative_path(url, next_url)
                        self.process_page(next_url, current_depth + 1)

        except Exception as e:
            logger.error(f"Failed to process {url}: {e}")

    def download_to_local(self, url):
        """
        辅助方法：下载任意文件到本地对应的路径
        Returns:
            bool: True if file exists or downloaded successfully, False otherwise
        """
        try:
            if not url:
                return False
            
            # 跳过非HTTP/HTTPS链接和Data URI
            if url.startswith('data:') or not url.startswith(('http://', 'https://')):
                return False

            local_path = self.get_local_path(url)
            
            if os.path.exists(local_path):
                return True
            
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            logger.info(f"Downloading file: {url}")
            try:
                response = self.session.get(url, stream=True, timeout=10)
                if response.status_code == 200:
                    with open(local_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    return True
                else:
                    logger.warning(f"Status {response.status_code} for {url}")
                    return False
            except Exception as download_error:
                logger.warning(f"Download failed for {url}: {download_error}")
                # Clean up if partial file created?
                if os.path.exists(local_path) and os.path.getsize(local_path) == 0:
                     os.remove(local_path)
                return False
                
        except Exception as e:
            logger.error(f"Error in download_to_local {url}: {e}")
            return False

    def get_relative_path(self, base_url, target_url):
        """计算两个URL对应本地文件的相对路径"""
        base_path = self.get_local_path(base_url)
        target_path = self.get_local_path(target_url)
        rel_path = os.path.relpath(target_path, os.path.dirname(base_path))
        # 确保URL使用正斜杠
        return rel_path.replace('\\', '/')

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
