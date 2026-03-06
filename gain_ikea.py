from DrissionPage import ChromiumPage, ChromiumOptions
import pandas as pd
import requests
import os
import time

def getTimes(driver):
    try:
        productsNumberInfo = driver.ele('.text-xs text-neutral-600 product-count', timeout=3).text
        if productsNumberInfo:
            cont_str = productsNumberInfo.split()[0]
            productsNumber = int(cont_str)
            if productsNumber <= 25:
                return 1
            else:
                return ((productsNumber - 25) // 25) + 1
    except:
        return 5 # 如果找不到总数，默认滑动5次

def scrollDown(driver, times):
    for i in range(times):
        driver.scroll(5000)
        time.sleep(1)
        try:
            # 模糊匹配“加载更多”按钮，比写死类名更稳
            btn = driver.ele('.i-btn i-btn--small i-btn--primary', timeout=1) 
            if btn:
                btn.click()
                print(f"已加载更多内容 ({i+1}/{times})")
                time.sleep(1)
        except:
            pass

def download_image(img_url, save_dir, Filename):
    try:
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        response = requests.get(img_url, stream=True, timeout=10)
        if response.status_code == 200:
            filepath = os.path.join(save_dir, Filename)
            with open(filepath, 'wb') as file:
                for chunk in response.iter_content(1024):
                    file.write(chunk)
            print(f"  -> 图片已保存: {Filename}")
            return filepath
    except Exception as e:
        print(f"  -> 下载图片失败: {e}")
    return None

# ==================== 主流程开始 ====================
start_time = time.time()

# 💡 【修改区】在这里统一配置你这次要抓取的任务！
# 1. 填入你要抓取的宜家分类网址
TARGET_URL = "https://www.ikea.cn/cn/zh/search/products/?q=%E9%95%9C%E5%AD%90&qtype=search_keywords" 

# 2. 修改为你想要的统一物品名称（比如 YOLO 里的标签名，如 "plant", "bed", "chair"）
CUSTOM_ITEM_NAME = "mirror" 

# 3. 修改你想保存的文件夹名称（图片会保存在这个文件夹里）
SAVE_FOLDER_NAME = "mirror1" 
# ==================================================

# 1. 启动浏览器
co = ChromiumOptions().set_paths(browser_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
browser = ChromiumPage(co)
tab = browser.new_tab()

# 🌟 自动生成保存路径
current_dir = os.path.dirname(os.path.abspath(__file__))
image_save_directory = os.path.join(current_dir, SAVE_FOLDER_NAME) # 图片保存路径
data_file_path = os.path.join(current_dir, f"{SAVE_FOLDER_NAME}_info.xlsx") # Excel 保存路径

# 2. 访问列表页并滚动
print(f"正在打开页面: {TARGET_URL}")
tab.get(TARGET_URL)
times = getTimes(tab)
print(f"需要翻页次数: {times}")
scrollDown(tab, times)
time.sleep(2) 

# 3. 暴力提取所有商品链接（100% 稳定，基于 URL 特征）
print("正在提取商品链接...")
all_product_links = []
links = tab.eles('tag:a')
for a in links:
    href = a.attr('href')
    if href and '/p/' in href and 'ikea.cn' in href:
        all_product_links.append(href)

# 列表去重
all_product_links = list(set(all_product_links))
print(f"共找到 {len(all_product_links)} 个商品链接，准备开始极速抓取...")

if len(all_product_links) == 0:
    print("未抓取到链接，请检查页面是否正常加载！")
    browser.quit()
    exit()

# 4. 单线程极速抓取目标信息
all_results = []

for index, url in enumerate(all_product_links):
    print(f"\n正在处理 {index + 1}/{len(all_product_links)}: {url}")
    try:
        tab.get(url)
        time.sleep(1) 
        
        # 提取货号
        original_tcin = url.strip('/').split('-')[-1]
        
        # 🌟 直接使用你在顶部设置的统一名称，不再去网页里抓取杂乱的商品原名！
        item_type_name = CUSTOM_ITEM_NAME

        # 提取场景图片 
        alternate_image = "N/A"
        images = tab.eles('.i-image__image', timeout=2)
        
        if len(images) >= 2:
            img_url_S = images[1].attr('src')
            # 给图片命名：物品名_货号_Scene.jpg (例如: plant_40600892_Scene.jpg)
            alternate_image = f"{CUSTOM_ITEM_NAME}_{original_tcin}_Scene.jpg"
            download_image(img_url_S, image_save_directory, alternate_image)
        elif len(images) == 1:
            img_url_S = images[0].attr('src')
            alternate_image = f"{CUSTOM_ITEM_NAME}_{original_tcin}_Scene.jpg"
            download_image(img_url_S, image_save_directory, alternate_image)
        else:
            print("  -> 该商品无可用图片")

        all_results.append({
            'original_tcin': original_tcin,
            'item_type_name': item_type_name,
            'alternate_image': alternate_image,
            'URL': url
        })

    except Exception as e:
        print(f"  -> 发生错误: {e}")

# 5. 关闭浏览器并保存数据
browser.quit()

if os.path.exists(data_file_path):
    os.remove(data_file_path)
df = pd.DataFrame(all_results)
df.to_excel(data_file_path, index=False)

print(f"\n✅ 抓取完成！数据已保存到 {data_file_path}")
print(f"⏳ 代码运行总耗时: {time.time() - start_time:.2f} 秒")