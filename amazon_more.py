from DrissionPage import ChromiumPage, ChromiumOptions
import pandas as pd
import requests
import os
import time
import random
import json

# ==================== 🎯 核心配置区 ====================
# 1. 🌟 把单一关键词改成“关键词列表”，想搜多少种就加多少种！
SEARCH_KEYWORDS = [
    "dining chair",     # 餐椅 (常规四腿)
    "kitchen chair",     
    "side chair",     
    "wooden chair",
    "four-legged chair"
]

# 2. 每个关键词爬取几页？（5个词 x 2页 x 50个 = 大约500张图）
MAX_PAGES_PER_KEYWORD = 6                   

# 3. 统一标签名称（你的 RT-DETR 认的统称）
CUSTOM_ITEM_NAME = "dining_chair"     

# 4. 保存文件夹名称
SAVE_FOLDER_NAME = "dining_chair1" 
# =======================================================

def download_image(img_url, save_dir, filename):
    try:
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8"
        }
        response = requests.get(img_url, headers=headers, stream=True, timeout=10)
        if response.status_code == 200:
            filepath = os.path.join(save_dir, filename)
            with open(filepath, 'wb') as file:
                for chunk in response.iter_content(1024):
                    file.write(chunk)
            print(f"    -> 📸 成功保存: {filename}")
            return filepath
    except Exception as e:
        print(f"    -> ❌ 图片下载失败: {e}")
    return None

# ==================== 主流程开始 ====================
start_time = time.time()
current_dir = os.path.dirname(os.path.abspath(__file__))
image_save_directory = os.path.join(current_dir, SAVE_FOLDER_NAME)
data_file_path = os.path.join(current_dir, f"{SAVE_FOLDER_NAME}_info.xlsx")

print("🚀 正在启动浏览器...")
co = ChromiumOptions().set_paths(browser_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
co.set_argument('--disable-blink-features=AutomationControlled')
browser = ChromiumPage(co)
tab = browser.latest_tab

all_results = []
is_first_search = True  # 🌟 新增标志位：记录是否是程序的第一次搜索

for keyword in SEARCH_KEYWORDS:
    print(f"\n" + "="*50)
    print(f"🔍 开启新任务: 正在搜索大类 【{keyword}】")
    print("="*50)
    
    current_keyword_links = []
    
    # --- 阶段 A：翻页获取当前关键词的商品链接 ---
    for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
        print(f"\n  📄 正在扫描 【{keyword}】 的第 {page} 页...")
        search_url = f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}&page={page}"
        tab.get(search_url)
        
        # 🔥 核心修改：只在“整个程序”的第一次打开时拦截！
        if is_first_search:
            print("\n" + "⚠️ "*15)
            print("【全网首次人工安检】请看弹出的 Chrome 浏览器：")
            print("1. 处理可能的字母验证码。")
            print("2. 确保左上角地区是美国（如 Deliver to New York 10001）。")
            print("3. 确认页面刷出了商品后...")
            input("👉 请在这里按下【回车键 (Enter)】，之后它全自动运行，不再打扰！")
            print("⚠️ "*15 + "\n")
            tab.refresh()
            time.sleep(3)
            is_first_search = False # 安检通过，后续关键词直接放行！

        tab.scroll.to_half()
        time.sleep(random.uniform(1.0, 2.0))
        tab.scroll.to_bottom()
        time.sleep(random.uniform(1.5, 2.5))
        
        links = tab.eles('tag:a')
        for a in links:
            try:
                href = a.attr('href')
                if href and '/dp/' in href and 'amazon.com' in href:
                    if '#customerReviews' not in href and 'product-reviews' not in href:
                        asin = href.split('/dp/')[1].split('/')[0].split('?')[0]
                        clean_url = f"https://www.amazon.com/dp/{asin}"
                        current_keyword_links.append(clean_url)
            except:
                continue

    current_keyword_links = list(set(current_keyword_links))
    print(f"\n  🎯 【{keyword}】 扫描完毕！找到 {len(current_keyword_links)} 个商品，开始拔图...")

    # --- 阶段 B：深入详情页提取高清大图 ---
    for index, url in enumerate(current_keyword_links):
        print(f"\n  [{index + 1}/{len(current_keyword_links)}] 处理中: {url}")
        try:
            tab.get(url)
            time.sleep(random.uniform(1.5, 3.5)) 
            
            asin = url.split('/dp/')[1]
            title_ele = tab.ele('#productTitle', timeout=2)
            product_name = title_ele.text if title_ele else "N/A"
            
            img_ele = tab.ele('#landingImage', timeout=2)
            image_filename = "N/A"
            
            if img_ele:
                dynamic_img_data = img_ele.attr('data-a-dynamic-image')
                high_res_url = ""
                if dynamic_img_data:
                    try:
                        img_dict = json.loads(dynamic_img_data)
                        high_res_url = list(img_dict.keys())[-1] 
                    except:
                        pass
                
                if not high_res_url:
                    high_res_url = img_ele.attr('data-old-hires') or img_ele.attr('src')
                
                if high_res_url:
                    # 🌟 图片命名加上了关键词前缀，方便你以后分辨，例如：dining_chair_B08XYZ.jpg
                    prefix = keyword.replace(' ', '_')
                    image_filename = f"{prefix}_{asin}.jpg"
                    download_image(high_res_url, image_save_directory, image_filename)
            else:
                print("    -> ⚠️ 未找到主图元素，跳过。")

            all_results.append({
                'Keyword': keyword,
                'ASIN': asin,
                'Original_Name': product_name,
                'Label': CUSTOM_ITEM_NAME,
                'Image': image_filename,
                'URL': url
            })

        except Exception as e:
            print(f"    -> ❌ 页面解析错误: {e}")
            
    # 每爬完一个关键词，就把 Excel 实时保存/更新一次，防止意外崩溃导致数据全丢
    df = pd.DataFrame(all_results)
    df.to_excel(data_file_path, index=False)
    print(f"\n💾 【{keyword}】 数据已阶段性保存至 Excel！")

# 扫尾工作
browser.quit()
print(f"\n✅ 亚马逊多目标联合抓取圆满完成！")
print(f"📁 所有图片保存在: {image_save_directory}")
print(f"⏳ 总耗时: {(time.time() - start_time) / 60:.2f} 分钟")