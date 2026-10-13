#!/usr/bin/env python3
"""
卖家精灵翻页诊断脚本
检查数据查询和翻页是否正常工作
"""

import json
import pickle
import requests
from pathlib import Path

# 项目路径
PROJECT_ROOT = Path("/Users/wanjuanbu/Desktop/智研π队/SI竞手流量自动化")
SELLERSPRITE_DIR = PROJECT_ROOT / "output" / "seller_sprite_brands"
COOKIE_FILE = SELLERSPRITE_DIR / "sellersprite_cookies.pkl"
CONFIG_FILE = PROJECT_ROOT / "config" / "sellersprite_tasks.json"

def load_config():
    """加载配置文件"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def load_cookies():
    """加载Cookie"""
    if COOKIE_FILE.exists():
        with open(COOKIE_FILE, 'rb') as f:
            return pickle.load(f)
    return None

def test_pagination():
    """测试翻页功能"""

    print("="*80)
    print("卖家精灵翻页诊断")
    print("="*80)

    # 加载配置
    config = load_config()
    if not config or not config.get('tasks'):
        print("❌ 配置文件为空或不存在")
        return

    task = config['tasks'][0]
    market = task['market']
    category_id = task['category_id']

    print(f"\n📋 配置信息:")
    print(f"   市场: {market}")
    print(f"   类目ID: {category_id}")

    # 加载Cookie
    cookies = load_cookies()
    if not cookies:
        print("❌ Cookie文件不存在")
        return

    print(f"   Cookie数量: {len(cookies)}")

    # 首先查询类目信息
    category_api = "https://www.sellersprite.com/v2/competitor-lookup/nodes"

    market_id_map = {
        "US": ["1"],
        "UK": ["3"],
        "DE": ["4"],
        "FR": ["5"],
        "IT": ["35691", "6"],
        "ES": ["7", "44551"],
        "CA": ["8"],
        "JP": ["9"]
    }

    market_ids = market_id_map.get(market, ["1"])

    print(f"\n📊 步骤1: 查询类目信息")

    for market_id in market_ids:
        params = {
            "marketId": market_id,
            "table": "bsr_sales_nearly",
            "nodeLabelPath": category_id
        }

        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }

        try:
            response = requests.get(
                category_api,
                headers=headers,
                cookies=cookies,
                params=params,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                if 'items' in data and data['items']:
                    item = data['items'][0]
                    category_full_id = item.get('id', '')
                    category_name = item.get('label', '')
                    product_count = item.get('products', 0)

                    print(f"✅ 类目查询成功:")
                    print(f"   完整ID: {category_full_id}")
                    print(f"   类目名称: {category_name}")
                    print(f"   产品数量: {product_count}")

                    # 测试数据查询
                    print(f"\n📊 步骤2: 测试数据查询和翻页")

                    data_api = "https://www.sellersprite.com/v3/api/competing-lookup"

                    headers['content-type'] = 'application/json;charset=UTF-8'
                    headers['origin'] = 'https://www.sellersprite.com'
                    headers['referer'] = 'https://www.sellersprite.com/v3/competitor-lookup'

                    all_items = []
                    page_size = 60

                    for page in range(1, 4):  # 测试前3页
                        payload = {
                            "market": market,
                            "monthName": "bsr_sales_nearly",
                            "asins": [],
                            "page": page,
                            "nodeIdPaths": [category_full_id],
                            "symbolFlag": False,
                            "size": page_size,
                            "order": {"field": "total_units", "desc": True},
                            "lowPrice": "N"
                        }

                        print(f"\n--- 第 {page} 页 ---")

                        try:
                            response = requests.post(
                                data_api,
                                headers=headers,
                                cookies=cookies,
                                json=payload,
                                timeout=30
                            )

                            print(f"状态码: {response.status_code}")

                            if response.status_code == 200:
                                result = response.json()

                                # 打印完整的响应结构
                                print(f"响应结构:")
                                print(f"  code: {result.get('code')}")
                                print(f"  message: {result.get('message')}")

                                if 'data' in result:
                                    data_obj = result['data']
                                    print(f"  data类型: {type(data_obj)}")

                                    if isinstance(data_obj, dict):
                                        print(f"  data字段: {list(data_obj.keys())}")

                                        if 'items' in data_obj:
                                            items = data_obj['items']
                                            total = data_obj.get('total', 0)
                                            pages_count = data_obj.get('pages', 0)

                                            print(f"  items数量: {len(items)}")
                                            print(f"  total: {total}")
                                            print(f"  pages: {pages_count}")

                                            if items:
                                                all_items.extend(items)
                                                print(f"✅ 第 {page} 页获取 {len(items)} 条数据")
                                                print(f"   累计: {len(all_items)} 条")

                                                # 显示前3条数据的基本信息
                                                print(f"\n   前3条数据示例:")
                                                for i, item in enumerate(items[:3], 1):
                                                    brand = item.get('brand', 'N/A')
                                                    asin = item.get('asin', 'N/A')
                                                    print(f"   {i}. 品牌: {brand}, ASIN: {asin}")

                                                if page >= pages_count:
                                                    print(f"\n   已到最后一页 (第{pages_count}页)")
                                                    break
                                            else:
                                                print(f"⚠️  items为空")
                                                break
                                        else:
                                            print(f"⚠️  data中没有items字段")
                                            print(f"   实际内容: {data_obj}")
                                            break
                                    else:
                                        print(f"⚠️  data不是字典类型")
                                        print(f"   实际内容: {data_obj}")
                                        break
                                else:
                                    print(f"⚠️  响应中没有data字段")
                                    print(f"   完整响应: {result}")
                                    break
                            else:
                                print(f"❌ HTTP错误: {response.status_code}")
                                break

                        except Exception as e:
                            print(f"❌ 请求异常: {e}")
                            break

                    print(f"\n📊 统计结果:")
                    print(f"   总页数测试: {min(3, len(all_items) // page_size + 1)}")
                    print(f"   总数据条数: {len(all_items)}")

                    # 提取品牌统计
                    brands = {}
                    for item in all_items:
                        brand = item.get('brand', 'Unknown')
                        brands[brand] = brands.get(brand, 0) + 1

                    print(f"   品牌数量: {len(brands)}")
                    print(f"\n   前10个品牌:")
                    for i, (brand, count) in enumerate(sorted(brands.items(), key=lambda x: x[1], reverse=True)[:10], 1):
                        print(f"   {i:2d}. {brand:<30} ({count} 个产品)")

                    return  # 成功完成，退出

                else:
                    print(f"⚠️  类目查询返回空数据，尝试下一个市场代码")
            else:
                print(f"⚠️  类目查询失败，状态码: {response.status_code}")

        except Exception as e:
            print(f"❌ 类目查询异常: {e}")

    print("\n❌ 所有市场代码都尝试失败")

if __name__ == "__main__":
    test_pagination()
