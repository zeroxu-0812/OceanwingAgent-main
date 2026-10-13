#!/usr/bin/env python3
"""
卖家精灵批量爬虫 - 稳定版
支持一次性爬取多个类目（最多5个）
包含完善的错误处理、自动重试、Cookie管理等功能
"""

import os
import sys
import time
import pickle
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
import json
import logging
from typing import List, Dict, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


# 项目内数据目录（避免依赖用户 Downloads 目录）
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SELLERSPRITE_DATA_DIR = PROJECT_ROOT / "output" / "seller_sprite_brands"
SELLERSPRITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Ensure project root is on sys.path for config_loader imports
_project_root = str(PROJECT_ROOT)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(SELLERSPRITE_DATA_DIR / "scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SellerSpriteBatchScraper:
    """卖家精灵批量爬虫 - 稳定版"""

    # 配置常量
    MAX_TASKS = 5
    MAX_RETRIES = 3
    REQUEST_TIMEOUT = 30
    DELAY_BETWEEN_REQUESTS = 2
    PAGE_SIZE = 60

    # 市场代码映射 (某些市场可能有多个代码，按优先级顺序排列)
    MARKET_ID_MAP = {
        "US": ["1"],
        "UK": ["3"],
        "DE": ["4"],
        "FR": ["5"],
        "IT": ["35691"],
        "ES": ["7", "44551"],  # ES市场有两个可能的市场代码
        "CA": ["8"],
        "JP": ["6"]
    }

    def __init__(self):
        """初始化"""
        self.session = requests.Session()
        self.cookies = {}
        self.cookie_file = SELLERSPRITE_DATA_DIR / "sellersprite_cookies.pkl"

        # 登录信息 — 从 credentials.json 读取，环境变量可覆盖
        from config_loader import get_sellersprite_email, get_sellersprite_password
        self.login_email = get_sellersprite_email()
        self.login_password = get_sellersprite_password()

        # API接口
        self.category_api = "https://www.sellersprite.com/v2/competitor-lookup/nodes"
        self.data_api = "https://www.sellersprite.com/v3/api/competing-lookup"

        # Headers
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,de;q=0.7',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36'
        }

        # 统计信息
        self.results = []
        self.errors = []

        # 确保输出目录存在
        self.output_dir = SELLERSPRITE_DATA_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("="*60)
        logger.info("卖家精灵批量爬虫已启动")
        logger.info("="*60)

    def login_and_get_cookies(self, force_login: bool = False) -> bool:
        """
        登录并获取Cookie

        Args:
            force_login: 是否强制重新登录

        Returns:
            bool: 是否成功
        """
        logger.info("="*60)
        logger.info("步骤: 登录卖家精灵")
        logger.info("="*60)

        # 检查是否已有Cookie
        if not force_login and self.cookie_file.exists():
            try:
                with open(self.cookie_file, 'rb') as f:
                    self.cookies = pickle.load(f)
                logger.info(f"✅ 已加载 {len(self.cookies)} 个Cookie")

                # 验证Cookie是否包含必要字段
                required = ['JSESSIONID', 'Sprite-X-Token']
                missing = [c for c in required if c not in self.cookies]
                if not missing:
                    logger.info("✅ Cookie验证通过")
                    return True
                else:
                    logger.warning(f"⚠️  Cookie缺少必要字段: {missing}，需要重新登录")
            except Exception as e:
                logger.error(f"❌ 加载Cookie失败: {e}")

        # 执行登录（最多尝试2次，每次120秒超时）
        max_attempts = 2
        login_success = False

        for attempt in range(max_attempts):
            if attempt > 0:
                logger.info(f"\n{'='*60}")
                logger.info(f"第 {attempt + 1} 次登录尝试（等待5秒后重新登录）...")
                logger.info(f"{'='*60}")
                # 清除旧的 Cookie 缓存
                if self.cookie_file.exists():
                    self.cookie_file.unlink()
                    logger.info("已清除旧的 Cookie 缓存")
                time.sleep(5)  # 避免被反爬虫

            logger.info("正在启动Chrome浏览器...")
            logger.info("ℹ️  无头模式，如遇验证码请确保 cookie 缓存有效或使用 --relogin")

            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--guest")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")

            try:
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                wait = WebDriverWait(driver, 120)

                logger.info("正在打开登录页面...")
                driver.get("https://www.sellersprite.com/cn/w/user/login")
                wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
                time.sleep(2)

                logger.info("正在填写登录信息...")

                # 查找并填写表单
                email_input = None
                password_input = None

                # 查找邮箱输入框
                email_selectors = [
                    'input[name="email"]',
                    'input.u-form__input[name="email"]',
                    'input[type="email"]'
                ]
                for selector in email_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for elem in elements:
                            if elem.is_displayed():
                                email_input = elem
                                break
                        if email_input:
                            break
                    except:
                        continue

                # 查找密码输入框
                password_selectors = [
                    'input[type="password"].u-form__input',
                    'input[type="password"]'
                ]
                for selector in password_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for elem in elements:
                            if elem.is_displayed():
                                password_input = elem
                                break
                        if password_input:
                            break
                    except:
                        continue

                if email_input and password_input:
                    email_input.clear()
                    email_input.send_keys(self.login_email)
                    time.sleep(0.3)
                    password_input.send_keys(self.login_password)
                    time.sleep(0.5)

                    # 点击登录按钮
                    button_selectors = [
                        'button.login-btn[type="submit"]',
                        '//button[@type="submit" and contains(text(),"登录")]',
                        '//button[contains(text(),"登录")]'
                    ]
                    for selector in button_selectors:
                        try:
                            if selector.startswith('//'):
                                elements = driver.find_elements(By.XPATH, selector)
                            else:
                                elements = driver.find_elements(By.CSS_SELECTOR, selector)

                            for elem in elements:
                                if elem.is_displayed():
                                    elem.click()
                                    logger.info("✅ 登录信息已提交")
                                    break
                            if email_input:
                                break
                        except:
                            continue

                logger.info("等待登录完成（最长120秒）...")
                try:
                    WebDriverWait(driver, 120).until(
                        lambda d: "login" not in d.current_url.lower()
                    )
                    logger.info("✅ 登录成功！")
                except:
                    logger.warning("⚠️  120秒内未检测到登录跳转，继续提取Cookie...")

                time.sleep(2)

                # 提取Cookie
                cookies = driver.get_cookies()
                self.cookies = {cookie['name']: cookie['value'] for cookie in cookies}

                logger.info(f"✅ 成功提取 {len(self.cookies)} 个Cookie")

                # 验证Cookie
                required = ['JSESSIONID', 'Sprite-X-Token']
                missing = [c for c in required if c not in self.cookies]
                if missing:
                    logger.warning(f"⚠️  缺少关键Cookie: {missing}")
                else:
                    logger.info("✅ 所有关键Cookie都已获取")

                # 保存Cookie
                with open(self.cookie_file, 'wb') as f:
                    pickle.dump(self.cookies, f)

                logger.info(f"✅ Cookie已保存到: {self.cookie_file}")

                driver.quit()
                login_success = True
                break  # 登录成功，跳出重试循环

            except Exception as e:
                logger.error(f"❌ 第 {attempt + 1} 次登录失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                login_success = False
                # 继续下一次重试

        if not login_success:
            logger.error(f"\n{'='*60}")
            logger.error("❌ 登录失败：已尝试 2 次（每次 120 秒），均未成功")
            logger.error("请检查网络连接或账号密码是否正确")
            logger.error(f"{'='*60}")
            return False

        return True

    def query_category(self, category_id: str, market: str) -> Optional[Dict]:
        """
        查询类目信息

        Args:
            category_id: 类目ID
            market: 市场代码

        Returns:
            类目信息字典，失败返回None
        """
        # 获取该市场的所有可能的市场代码
        market_ids = self.MARKET_ID_MAP.get(market, ["3"])

        # 尝试每个市场代码
        for idx, market_id in enumerate(market_ids):
            if len(market_ids) > 1:
                logger.info(f"尝试市场代码 {market_id} ({idx + 1}/{len(market_ids)})")

            params = {
                "marketId": market_id,
                "table": "bsr_sales_nearly",
                "nodeLabelPath": category_id
            }

            for attempt in range(self.MAX_RETRIES):
                try:
                    logger.debug(f"查询类目信息 (市场代码: {market_id}, 尝试 {attempt + 1}/{self.MAX_RETRIES})")

                    response = self.session.get(
                        self.category_api,
                        headers=self.headers,
                        cookies=self.cookies,
                        params=params,
                        timeout=self.REQUEST_TIMEOUT
                    )

                    if response.status_code == 200:
                        data = response.json()
                        if 'items' in data and data['items']:
                            item = data['items'][0]
                            result = {
                                'id': item.get('id', ''),
                                'name': item.get('label', ''),
                                'locale': item.get('nodeLabelLocale', ''),
                                'products': item.get('products', 0),
                                'market_id': market_id  # 记录使用的市场代码
                            }
                            logger.info(f"✅ 类目查询成功 (市场代码: {market_id}): {result['locale']}")
                            return result
                        else:
                            if len(market_ids) > 1 and idx < len(market_ids) - 1:
                                logger.warning(f"⚠️  市场代码 {market_id} 返回空数据，尝试下一个市场代码")
                                break
                            else:
                                logger.warning("⚠️  类目查询返回空数据")
                                return None
                    else:
                        logger.warning(f"⚠️  类目查询失败，状态码: {response.status_code}")
                        if attempt < self.MAX_RETRIES - 1:
                            time.sleep(2)
                        continue

                except requests.exceptions.Timeout:
                    logger.warning(f"⚠️  请求超时 (尝试 {attempt + 1}/{self.MAX_RETRIES})")
                    if attempt < self.MAX_RETRIES - 1:
                        time.sleep(2)
                    continue
                except Exception as e:
                    logger.error(f"❌ 类目查询异常: {e}")
                    if attempt < self.MAX_RETRIES - 1:
                        time.sleep(2)
                    continue
                    return None

        logger.error("❌ 类目查询失败，已尝试所有市场代码和重试次数")
        return None

    def query_data_with_pagination(self, category_id_full: str, market: str) -> List[Dict]:
        """
        查询数据（支持翻页）

        Args:
            category_id_full: 完整类目路径
            market: 市场代码

        Returns:
            数据列表
        """
        headers = self.headers.copy()
        headers['content-type'] = 'application/json;charset=UTF-8'
        headers['origin'] = 'https://www.sellersprite.com'
        headers['referer'] = 'https://www.sellersprite.com/v3/competitor-lookup'

        all_items = []
        page = 1

        logger.info("开始查询数据...")

        while True:
            payload = {
                "market": market,
                "monthName": "bsr_sales_nearly",
                "asins": [],
                "page": page,
                "nodeIdPaths": [category_id_full],
                "symbolFlag": False,
                "size": self.PAGE_SIZE,
                "order": {"field": "total_units", "desc": True},
                "lowPrice": "N"
            }

            try:
                logger.debug(f"正在查询第 {page} 页...")

                response = self.session.post(
                    self.data_api,
                    headers=headers,
                    cookies=self.cookies,
                    json=payload,
                    timeout=self.REQUEST_TIMEOUT
                )

                if response.status_code == 200:
                    result = response.json()

                    # 检查是否需要重新登录
                    if result.get('code') == 'ERR_GLOBAL_SESSION_EXPIRED':
                        logger.error("❌ Cookie已过期，需要重新登录")
                        logger.error("请使用 --relogin 参数重新运行脚本")
                        break

                    if 'data' in result and result['data']:
                        data_obj = result['data']

                        if isinstance(data_obj, dict) and 'items' in data_obj:
                            items = data_obj['items']
                            total = data_obj.get('total', 0)
                            pages = data_obj.get('pages', 1)

                            if items:
                                all_items.extend(items)
                                logger.info(f"  第 {page} 页: 获取 {len(items)} 条，累计 {len(all_items)} 条")

                                # 检查是否还有下一页（更健壮的判断逻辑）
                                # 如果返回的数据量小于每页大小，说明已经是最后一页
                                if len(items) < self.PAGE_SIZE:
                                    logger.info(f"✅ 数据查询完成（本页数据量{len(items)} < 每页大小{self.PAGE_SIZE}），共获取 {len(all_items)} 条")
                                    break
                                # 如果有total和pages信息，也使用它们作为辅助判断
                                elif pages > 0 and page >= pages:
                                    logger.info(f"✅ 数据查询完成（已到第{page}/{pages}页），共获取 {len(all_items)} 条")
                                    break
                                elif total > 0 and len(all_items) >= total:
                                    logger.info(f"✅ 数据查询完成（累计{len(all_items)} >= 总数{total}），共获取 {len(all_items)} 条")
                                    break
                                else:
                                    page += 1
                                    time.sleep(0.5)  # 避免请求过快
                            else:
                                logger.warning(f"⚠️  第 {page} 页没有数据")
                                break
                        else:
                            logger.error("❌ 数据格式异常")
                            break
                    else:
                        logger.warning("⚠️  API返回data为null")
                        break
                else:
                    logger.warning(f"⚠️  API调用失败，状态码: {response.status_code}")
                    break

            except requests.exceptions.Timeout:
                logger.warning(f"⚠️  第{page}页请求超时")
                break
            except Exception as e:
                logger.error(f"❌ 第{page}页查询异常: {e}")
                break

        return all_items

    def extract_and_save_brands(self, data: List[Dict], category_info: Dict, market: str) -> Optional[Dict]:
        """
        提取并保存品牌数据（包含ASIN、品牌、上架时间、价格、销量、销售额）

        Args:
            data: 原始数据
            category_info: 类目信息
            market: 市场代码

        Returns:
            保存结果信息
        """
        if not data:
            logger.error("❌ 没有数据可保存")
            return None

        try:
            df = pd.DataFrame(data)
            logger.info(f"数据维度: {len(df)} 行 × {len(df.columns)} 列")
            logger.info(f"可用列: {list(df.columns)[:20]}...")  # 显示前20列

            # 查找并映射所需字段
            field_mapping = {}

            # ASIN字段映射
            for asin_field in ['asin', 'sku', 'ASIN', 'asin0']:
                if asin_field in df.columns:
                    field_mapping['ASIN'] = asin_field
                    break

            # 品牌字段映射
            for brand_field in ['brand', 'brandShort', 'brand0']:
                if brand_field in df.columns:
                    field_mapping['品牌'] = brand_field
                    break

            # 上架时间字段映射
            for date_field in ['launch_date', 'publishDate', 'publish_date', 'releaseDate']:
                if date_field in df.columns:
                    field_mapping['上架时间'] = date_field
                    break

            # 价格字段映射
            for price_field in ['price', 'Price', 'price0']:
                if price_field in df.columns:
                    field_mapping['价格'] = price_field
                    break

            # 销量(父)字段映射
            for sales_field in ['total_units', 'units_sold', 'salesUnits']:
                if sales_field in df.columns:
                    field_mapping['销量(父)'] = sales_field
                    break

            # 销售额字段映射
            for revenue_field in ['total_revenue', 'salesRevenue', 'revenue']:
                if revenue_field in df.columns:
                    field_mapping['销售额'] = revenue_field
                    break

            logger.info(f"字段映射: {field_mapping}")

            # 提取所需字段
            extracted_data = []
            for _, row in df.iterrows():
                item_data = {}
                for display_name, field_name in field_mapping.items():
                    value = row.get(field_name, '')
                    item_data[display_name] = value
                extracted_data.append(item_data)

            df_extracted = pd.DataFrame(extracted_data)

            logger.info(f"✅ 提取到 {len(df_extracted)} 条产品数据")
            logger.info(f"提取的字段: {list(df_extracted.columns)}")

            # 显示前5条数据预览
            logger.info("数据预览（前5条）:")
            for i, row in df_extracted.head(5).iterrows():
                logger.info(f"  {i+1}. ASIN: {row.get('ASIN', 'N/A')}, 品牌: {row.get('品牌', 'N/A')}, 价格: {row.get('价格', 'N/A')}, 销量: {row.get('销量(父)', 'N/A')}")

            # 按品牌统计
            if '品牌' in df_extracted.columns:
                brand_counts = df_extracted['品牌'].value_counts().reset_index()
                brand_counts.columns = ['Brand', 'Product_Count']
                logger.info(f"✅ 提取到 {len(brand_counts)} 个唯一品牌")

                # 显示前10个品牌
                logger.info("品牌排名（前10个）:")
                for i, row in brand_counts.head(10).iterrows():
                    logger.info(f"  {i+1}. {row['Brand']}: {row['Product_Count']} 个产品")
            else:
                logger.warning("⚠️ 未找到品牌字段，跳过品牌统计")
                brand_counts = pd.DataFrame()

            # 保存文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = category_info['locale'] if category_info['locale'] else category_info['name']
            safe_name = f"{market}_{safe_name}".replace(' ', '_').replace('/', '_')[:50]

            brand_file = self.output_dir / f"品牌列表_{safe_name}_{timestamp}.xlsx"
            data_file = self.output_dir / f"完整数据_{safe_name}_{timestamp}.xlsx"
            extracted_file = self.output_dir / f"提取数据_{safe_name}_{timestamp}.xlsx"

            if not brand_counts.empty:
                brand_counts.to_excel(brand_file, index=False, engine='openpyxl')
                logger.info(f"✅ 品牌列表已保存: {brand_file.name}")

            df.to_excel(data_file, index=False, engine='openpyxl')
            df_extracted.to_excel(extracted_file, index=False, engine='openpyxl')
            logger.info(f"✅ 完整数据已保存: {data_file.name}")
            logger.info(f"✅ 提取数据已保存: {extracted_file.name}")

            return {
                'brand_file': str(brand_file) if not brand_counts.empty else '',
                'data_file': str(data_file),
                'extracted_file': str(extracted_file),
                'total_brands': len(brand_counts) if not brand_counts.empty else 0,
                'total_products': len(df_extracted)
            }

        except Exception as e:
            logger.error(f"❌ 保存数据失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def scrape_one_category(self, market: str, category_id: str, index: int, total: int) -> Dict:
        """
        爬取单个类目

        Args:
            market: 市场代码
            category_id: 类目ID
            index: 当前任务索引
            total: 总任务数

        Returns:
            任务结果字典
        """
        logger.info("")
        logger.info("="*60)
        logger.info(f"[{index}/{total}] 开始爬取: {market} 市场 - 类目ID {category_id}")
        logger.info("="*60)

        result = {
            'market': market,
            'category_id': category_id,
            'status': 'pending',
            'category_name': '',
            'total_products': 0,
            'total_brands': 0,
            'brand_file': '',
            'error': ''
        }

        try:
            # 步骤1: 查询类目信息
            logger.info(f"步骤1: 查询类目信息")
            category_info = self.query_category(category_id, market)

            if not category_info:
                result['status'] = 'failed'
                result['error'] = '类目查询失败'
                self.errors.append(result)
                logger.error(f"❌ [{index}/{total}] 类目查询失败")
                return result

            logger.info(f"类目: {category_info['locale']}")
            logger.info(f"完整路径: {category_info['id']}")
            logger.info(f"产品数: {category_info['products']}")

            result['category_name'] = category_info['locale']

            # 步骤2: 查询数据
            logger.info(f"步骤2: 查询数据")
            data = self.query_data_with_pagination(category_info['id'], market)

            if not data:
                result['status'] = 'failed'
                result['error'] = '数据查询失败'
                self.errors.append(result)
                logger.error(f"❌ [{index}/{total}] 数据查询失败")
                return result

            logger.info(f"✅ 成功获取 {len(data)} 条数据")

            # 步骤3: 提取并保存品牌
            logger.info(f"步骤3: 提取并保存品牌")
            save_result = self.extract_and_save_brands(data, category_info, market)

            if save_result:
                result['status'] = 'success'
                result['total_products'] = save_result['total_products']
                result['total_brands'] = save_result['total_brands']
                result['brand_file'] = save_result['brand_file']

                logger.info(f"✅ [{index}/{total}] 任务完成")
                logger.info(f"   产品数: {result['total_products']}")
                logger.info(f"   品牌数: {result['total_brands']}")

                self.results.append(result)
                return result
            else:
                result['status'] = 'failed'
                result['error'] = '品牌提取失败'
                self.errors.append(result)
                logger.error(f"❌ [{index}/{total}] 品牌提取失败")
                return result

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
            self.errors.append(result)
            logger.error(f"❌ [{index}/{total}] 异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return result

    def generate_summary_report(self):
        """生成汇总报告"""
        logger.info("")
        logger.info("="*60)
        logger.info("批量爬取汇总报告")
        logger.info("="*60)

        total = len(self.results) + len(self.errors)
        success = len(self.results)
        failed = len(self.errors)

        logger.info(f"总任务数: {total}")
        logger.info(f"✅ 成功: {success}")
        logger.info(f"❌ 失败: {failed}")

        if self.results:
            logger.info("")
            logger.info("✅ 成功的类目:")
            logger.info(f"{'市场':<6} {'类目ID':<15} {'类目名称':<30} {'产品数':<10} {'品牌数':<10}")
            logger.info("-" * 80)

            for r in self.results:
                name = r['category_name'][:27] + "..." if len(r['category_name']) > 30 else r['category_name']
                logger.info(f"{r['market']:<6} {r['category_id']:<15} {name:<30} {r['total_products']:<10} {r['total_brands']:<10}")

        if self.errors:
            logger.info("")
            logger.info("❌ 失败的类目:")
            logger.info(f"{'市场':<6} {'类目ID':<15} {'错误信息'}")
            logger.info("-" * 80)

            for e in self.errors:
                logger.info(f"{e['market']:<6} {e['category_id']:<15} {e['error']}")

        # 保存汇总报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.output_dir / f"批量爬取报告_{timestamp}.xlsx"

        # 汇总数据
        summary_data = []
        for r in self.results:
            summary_data.append({
                '市场': r['market'],
                '类目ID': r['category_id'],
                '类目名称': r['category_name'],
                '状态': '成功',
                '产品数': r['total_products'],
                '品牌数': r['total_brands'],
                '品牌文件': r['brand_file']
            })

        for e in self.errors:
            summary_data.append({
                '市场': e['market'],
                '类目ID': e['category_id'],
                '类目名称': e.get('category_name', ''),
                '状态': '失败',
                '产品数': 0,
                '品牌数': 0,
                '品牌文件': e['error']
            })

        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(report_file, index=False, engine='openpyxl')

        logger.info("")
        logger.info(f"✅ 汇总报告已保存: {report_file.name}")

    def run_batch(self, tasks: List[Dict], force_login: bool = False) -> bool:
        """
        批量运行

        Args:
            tasks: 任务列表
            force_login: 是否强制重新登录

        Returns:
            是否全部成功
        """
        start_time = datetime.now()

        logger.info("")
        logger.info("="*60)
        logger.info("卖家精灵批量爬虫")
        logger.info("="*60)
        logger.info(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"任务数量: {len(tasks)}")

        # 显示任务列表
        logger.info("")
        logger.info("任务列表:")
        for i, task in enumerate(tasks, 1):
            logger.info(f"  {i}. {task['market']} 市场 - 类目ID: {task['category_id']}")

        # 登录
        if not self.login_and_get_cookies(force_login=force_login):
            logger.error("❌ 登录失败，无法继续")
            return False

        # 执行任务
        for i, task in enumerate(tasks, 1):
            market = task.get('market', 'UK')
            category_id = task.get('category_id')

            self.scrape_one_category(market, category_id, i, len(tasks))

            # 避免请求过快
            if i < len(tasks):
                logger.info(f"等待 {self.DELAY_BETWEEN_REQUESTS} 秒后继续...")
                time.sleep(self.DELAY_BETWEEN_REQUESTS)

        # 生成汇总报告
        self.generate_summary_report()

        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()

        logger.info("")
        logger.info("="*60)
        logger.info(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"总耗时: {int(elapsed // 60)} 分 {int(elapsed % 60)} 秒")
        logger.info("="*60)

        return len(self.errors) == 0


def validate_tasks(tasks: List[Dict]) -> List[Dict]:
    """验证并清理任务列表"""
    valid_tasks = []
    valid_markets = list(SellerSpriteBatchScraper.MARKET_ID_MAP.keys())

    for task in tasks:
        market = task.get('market', '').upper()
        category_id = task.get('category_id', '').strip()

        if market not in valid_markets:
            logger.warning(f"⚠️  跳过无效市场: {market}")
            continue

        if not category_id:
            logger.warning(f"⚠️  跳过空类目ID")
            continue

        valid_tasks.append({'market': market, 'category_id': category_id})

    return valid_tasks


def load_tasks_from_config(config_file: Path) -> List[Dict]:
    """从配置文件加载任务"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('tasks', [])
    except Exception as e:
        logger.error(f"❌ 配置文件读取失败: {e}")
        return []


def main():
    """主函数"""
    import argparse

    scraper = SellerSpriteBatchScraper()

    parser = argparse.ArgumentParser(
        description='卖家精灵批量爬虫 - 稳定版（最多5个类目）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:

1. 命令行指定多个类目:
   python3 sellersprite_batch_scraper.py --tasks "UK:10706461" "US:3773431" "DE:12345678"

2. 从配置文件读取:
   python3 sellersprite_batch_scraper.py --config tasks.json

3. 强制重新登录:
   python3 sellersprite_batch_scraper.py --tasks "UK:10706461" --relogin

配置文件格式 (JSON):
{
  "tasks": [
    {"market": "UK", "category_id": "10706461"},
    {"market": "US", "category_id": "3773431"},
    {"market": "DE", "category_id": "12345678"}
  ]
}

支持的市场: US, UK, DE, FR, IT, ES, CA, JP
注意: 每次最多爬取5个类目
        '''
    )

    parser.add_argument('--tasks', nargs='+',
                       help='任务列表，格式: "市场:类目ID"（最多5个）')
    parser.add_argument('--config', type=str,
                       help='配置文件路径 (JSON格式)')
    parser.add_argument('--relogin', action='store_true',
                       help='强制重新登录')

    args = parser.parse_args()

    # 收集任务
    tasks = []

    if args.config:
        config_file = Path(args.config)
        if config_file.exists():
            tasks = load_tasks_from_config(config_file)
            if not tasks:
                logger.error("❌ 配置文件为空或格式错误")
                sys.exit(1)
        else:
            logger.error(f"❌ 配置文件不存在: {args.config}")
            sys.exit(1)

    if args.tasks:
        for task_str in args.tasks:
            if ':' in task_str:
                parts = task_str.split(':', 1)
                if len(parts) == 2:
                    market, category_id = parts
                    tasks.append({'market': market.upper(), 'category_id': category_id})

    if not tasks:
        logger.error("❌ 未指定任务")
        logger.info("")
        logger.info("使用方法:")
        logger.info("  python3 sellersprite_batch_scraper.py --tasks 'UK:10706461' 'US:3773431'")
        logger.info("  python3 sellersprite_batch_scraper.py --config tasks.json")
        sys.exit(1)

    # 验证任务
    tasks = validate_tasks(tasks)

    if not tasks:
        logger.error("❌ 没有有效的任务")
        sys.exit(1)

    # 限制任务数量
    if len(tasks) > scraper.MAX_TASKS:
        logger.warning(f"⚠️  任务数量超过限制！")
        logger.warning(f"   指定了 {len(tasks)} 个类目，最多只能爬取 {scraper.MAX_TASKS} 个")
        logger.warning(f"   将只爬取前 {scraper.MAX_TASKS} 个类目")
        tasks = tasks[:scraper.MAX_TASKS]

    # 运行批量爬取
    success = scraper.run_batch(tasks, force_login=args.relogin)

    sys.exit(0 if success else 1)


# ══════════════════════════════════════════════════════════════
# Agent-ready functions: importable entry points
# ══════════════════════════════════════════════════════════════


def scrape_brands(market: str, category_id: str, force_login: bool = False) -> str:
    """
    从 SellerSprite 爬取单个类目的品牌列表（适合 Agent 调用的可导入函数）。

    参数:
        market: 市场代码 (如 'US', 'UK', 'DE')
        category_id: 类目ID
        force_login: 是否强制重新登录

    返回:
        str: 生成的品牌列表 xlsx 文件路径

    抛出:
        RuntimeError: 爬取失败时
    """
    scraper = SellerSpriteBatchScraper()

    # 登录
    if not scraper.login_and_get_cookies(force_login=force_login):
        raise RuntimeError("SellerSprite 登录失败")

    # 执行单任务爬取
    result = scraper.scrape_one_category(market, category_id, 1, 1)

    if result['status'] != 'success':
        error_msg = result.get('error', '未知错误')
        raise RuntimeError(f"SellerSprite 爬取失败 [{market}/{category_id}]: {error_msg}")

    brand_file = result.get('brand_file', '')
    if not brand_file or not Path(brand_file).exists():
        raise RuntimeError(f"品牌文件未生成: {brand_file}")

    return brand_file


def scrape_brands_batch(tasks: list[tuple[str, str]], force_login: bool = False) -> dict[str, str]:
    """
    批量爬取多个市场/类目的品牌列表。
    内部共用同一个 SellerSprite 会话（只登录一次），效率更高。

    参数:
        tasks: [(market, category_id), ...] 如 [("US", "13218451"), ("DE", "123456")]
        force_login: 是否强制重新登录

    返回:
        dict: {"market:category_id": brand_file_path, ...}
    """
    scraper = SellerSpriteBatchScraper()

    if not scraper.login_and_get_cookies(force_login=force_login):
        raise RuntimeError("SellerSprite 登录失败")

    task_dicts = [{"market": m, "category_id": c} for m, c in tasks]
    results = {}

    for i, (market, category_id) in enumerate(tasks, 1):
        result = scraper.scrape_one_category(market, category_id, i, len(tasks))

        if result['status'] == 'success' and result.get('brand_file'):
            results[f"{market}:{category_id}"] = result['brand_file']
        else:
            print(f"⚠️  [{market}/{category_id}] 爬取失败: {result.get('error', '未知错误')}")
            results[f"{market}:{category_id}"] = ""

        if i < len(tasks):
            time.sleep(scraper.DELAY_BETWEEN_REQUESTS)

    return results


if __name__ == '__main__':
    main()
