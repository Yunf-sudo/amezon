from DrissionPage import ChromiumPage, ChromiumOptions
import pandas as pd
import requests
import os
import time
import random
import json

# ==================== 🎯 核心配置区 ====================
# 1. 搜索关键词（英文）
# SEARCH_KEYWORD = "dining chair . kitchen chair . side chair . wooden chair . four-legged chair . dining room chair ." 
# SEARCH_KEYWORD = "gaming chair . racing chair . computer gaming chair . ergonomic gaming chair . racing style chair ." 
# SEARCH_KEYWORD = "office chair . desk chair . computer chair . ergonomic chair . task chair ." 
# SEARCH_KEYWORD = "sofa . couch . armchair . lounge chair . recliner . ottoman . upholstered seating ." 
SEARCH_KEYWORD = "coffee table . side table . end table . console table . accent table . low living room table ."#relax_table
# SEARCH_KEYWORD = "computer desk . office desk . standing desk . writing desk . gaming desk . workstation ." #focus_table

# 2. 爬取页数（亚马逊每页约 50 个商品，2页就是 100 个）
MAX_PAGES = 15                   

# 3. 统一标签名称（用于 YOLO 标签和图片命名）
CUSTOM_ITEM_NAME = "relax table"     

# 4. 保存文件夹名称
SAVE_FOLDER_NAME = "relax_table" 
# =======================================================

def download_image(img_url, save_dir, filename):
    try:
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        # 伪装请求头，防止被亚马逊的图片服务器拒绝
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8"
        }
        response = requests.get(img_url, headers=headers, stream=True, timeout=10)
        if response.status_code == 200:  
            filepath = os.path.join(save_dir, filename)
            with open(filepath, 'wb') as file:
                for chunk in response.iter_content(1024):
                    file.write(chunk)
            print(f"  -> 📸 成功保存: {filename}")
            return filepath
    except Exception as e:
        print(f"  -> ❌ 图片下载失败: {e}")
    return None

# ==================== 主流程开始 ====================
start_time = time.time()

current_dir = os.path.dirname(os.path.abspath(__file__))
image_save_directory = os.path.join(current_dir, SAVE_FOLDER_NAME)
data_file_path = os.path.join(current_dir, f"{SAVE_FOLDER_NAME}_info.xlsx")

# 1. 启动浏览器 (接管本地 Chrome)
print("🚀 正在启动浏览器...")
co = ChromiumOptions().set_paths(browser_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
# 屏蔽自动化特征，降低被识别概率
co.set_argument('--disable-blink-features=AutomationControlled')
browser = ChromiumPage(co)
tab = browser.latest_tab

all_product_links = []

print(f"🔍 准备搜索: {SEARCH_KEYWORD}")

# 2. 翻页获取链接
for page in range(1, MAX_PAGES + 1):
    print(f"\n📄 正在扫描第 {page} 页...")
    search_url = f"https://www.amazon.com/s?k={SEARCH_KEYWORD.replace(' ', '+')}&page={page}"
    tab.get(search_url)
    
    # 🔥 核心防封锁拦截：第一页无限期暂停！
    if page == 1:
        print("\n" + "⚠️ "*20)
        print("【人工安检环节】请看弹出的 Chrome 浏览器：")
        print("1. 如果有【字母验证码】，请手动输入通过。")
        print("2. 左上角如果显示【Deliver to China】，请点击它，输入美国邮编 10001 并 Apply。")
        print("3. 当你确认页面刷出了正常的商品列表后...")
        input("👉 请在这里按下【回车键 (Enter)】，让代码继续疯狂抓取！")
        print("⚠️ "*20 + "\n")
        # 刷新页面以应用你刚才改的美国邮编
        tab.refresh()
        time.sleep(3)

    # 随机滚动，假装人类在看商品
    tab.scroll.to_half()
    time.sleep(random.uniform(1.0, 2.5))
    tab.scroll.to_bottom()
    time.sleep(random.uniform(1.5, 3.0))
    
    # 暴力提取所有带 /dp/ 的商品链接
    links = tab.eles('tag:a')
    for a in links:
        try:
            href = a.attr('href')
            if href and '/dp/' in href and 'amazon.com' in href:
                # 过滤掉评论区等干扰链接
                if '#customerReviews' not in href and 'product-reviews' not in href:
                    # 切割出最纯净的 ASIN 链接
                    asin = href.split('/dp/')[1].split('/')[0].split('?')[0]
                    clean_url = f"https://www.amazon.com/dp/{asin}"
                    all_product_links.append(clean_url)
        except:
            continue

# 去重
all_product_links = list(set(all_product_links))
print(f"\n🎯 扫描完毕！共收集到 {len(all_product_links)} 个不重复的商品，开始拔图...")

if len(all_product_links) == 0:
    print("❌ 未抓取到链接，请确保在刚才的人工环节中，页面正确显示了商品！")
    browser.quit()
    exit()

# 3. 深入商品详情页提取高清大图
all_results = []

for index, url in enumerate(all_product_links):
    print(f"\n[{index + 1}/{len(all_product_links)}] 正在处理: {url}")
    try:
        tab.get(url)
        time.sleep(random.uniform(2.0, 4.0)) # 随机停顿极其重要！
        
        asin = url.split('/dp/')[1]
        
        # 获取标题
        title_ele = tab.ele('#productTitle', timeout=2)
        product_name = title_ele.text if title_ele else "N/A"
        
        # 💥 提取亚马逊超清主图
        img_ele = tab.ele('#landingImage', timeout=2)
        image_filename = "N/A"
        
        if img_ele:
            # 亚马逊会把不同分辨率的图片放在 data-a-dynamic-image 这个字典里
            dynamic_img_data = img_ele.attr('data-a-dynamic-image')
            high_res_url = ""
            if dynamic_img_data:
                try:
                    # 解析 JSON，提取分辨率最高的那张图的 URL
                    img_dict = json.loads(dynamic_img_data)
                    high_res_url = list(img_dict.keys())[-1] 
                except:
                    pass
            
            # 如果解析失败，用备用属性
            if not high_res_url:
                high_res_url = img_ele.attr('data-old-hires') or img_ele.attr('src')
            
            if high_res_url:
                image_filename = f"{CUSTOM_ITEM_NAME}_{asin}.jpg"
                download_image(high_res_url, image_save_directory, image_filename)
        else:
            print("  -> ⚠️ 未找到主图元素，跳过。")

        all_results.append({
            'ASIN': asin,
            'Original_Name': product_name,
            'Label': CUSTOM_ITEM_NAME,
            'Image': image_filename,
            'URL': url
        })

    except Exception as e:
        print(f"  -> ❌ 页面解析错误: {e}")

# 4. 扫尾工作
browser.quit()

if os.path.exists(data_file_path):
    os.remove(data_file_path)
df = pd.DataFrame(all_results)
df.to_excel(data_file_path, index=False)

print(f"\n✅ 亚马逊抓取圆满完成！Excel 数据已保存到 {data_file_path}")
print(f"⏳ 总耗时: {time.time() - start_time:.2f} 秒")