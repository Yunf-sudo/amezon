from DrissionPage import ChromiumPage, ChromiumOptions
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import requests
import os
import time
import random
import re

# ==================== 🎯 核心配置区 ====================
SEARCH_KEYWORDS = [
    # 巧妙利用周边商品，逼迫亚马逊展示“室内楼梯全景实景图”
    "indoor spiral staircase kit",          # 室内旋转楼梯套件 (高概率出全景实装图)
    "pull down attic stairs wooden",        # 木质折叠阁楼楼梯 (真实的室内走廊/阁楼场景)
    "indoor stair railing kit modern",      # 现代室内楼梯扶手套件 (必然依托于完整的楼梯展示)
    "floating stairs indoor hardware",      # 室内悬浮楼梯五金配件 (展示极简现代风楼梯)
    "staircase chandelier long modern"      # 楼梯长吊灯 (绝杀！这种商品的主图100%是宏大的室内楼梯全景)
]

# ⛔️ 致命黑名单：精准斩杀亚马逊上的“伪楼梯”商品
BANNED_WORDS = [
    'pet', 'dog', 'cat', 'puppy', 'ramp',   # 屏蔽泛滥的宠物楼梯/斜坡
    'gate', 'baby', 'toddler', 'child',     # 屏蔽婴儿防摔护栏门
    'outdoor', 'deck', 'pool', 'patio',     # 屏蔽室外步道、泳池阶梯
    'tread', 'carpet', 'rug', 'mat',        # 屏蔽楼梯防滑垫/地毯 (往往只展示一个台阶的特写)
    'sticker', 'decal', 'wall art',         # 屏蔽贴在台阶上的装饰贴纸
    'step stool', 'ladder'                  # 屏蔽普通的人字梯/小板凳
]

PAGES_PER_KEYWORD = 6            # 建议先少跑几页测试
CUSTOM_ITEM_NAME = "Stairs"  
SAVE_FOLDER_NAME = "Stairs"  
MAX_WORKERS = 30                 # 并发数
# =======================================================

def get_high_res_url(thumb_url):
    """把缩略图变成高清大图"""
    return re.sub(r'\._.*?_\.', '.', thumb_url)

def download_image_task(item):
    """多线程下载"""
    img_url = item['High_Res_URL']
    filename = item['Image']
    save_dir = item['Save_Dir']
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        response = requests.get(img_url, headers=headers, stream=True, timeout=10)
        if response.status_code == 200:  
            filepath = os.path.join(save_dir, filename)
            with open(filepath, 'wb') as file:
                for chunk in response.iter_content(1024):
                    file.write(chunk)
            print(f"  -> 📸 成功: {filename}")
            return True
    except Exception:
        pass
    return False

# ==================== 主流程开始 ====================
if __name__ == "__main__":
    start_time = time.time()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    image_save_directory = os.path.join(current_dir, SAVE_FOLDER_NAME)
    data_file_path = os.path.join(current_dir, f"{SAVE_FOLDER_NAME}_info.xlsx")

    # print("🚀 正在启动浏览器 (室内楼梯场景图深度抓取模式)...")
    # co = ChromiumOptions().set_paths(browser_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    # co.set_argument('--disable-blink-features=AutomationControlled')
    # co.set_load_mode('eager') 
    
    # browser = ChromiumPage(co)
    # tab = browser.latest_tab
    # tab.set.timeouts(page_load=5) 

    print("🚀 正在启动浏览器 (开启极速DOM解析模式)...")
    co = ChromiumOptions().set_paths(browser_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    co.set_argument('--disable-blink-features=AutomationControlled')
    
    # ======== 🐎 提速外挂 ========
    co.no_imgs(True)           # 绝对禁止浏览器下载和渲染任何图片（省下海量带宽和内存）
    co.mute(True)              # 静音，防止带有自动播放视频的详情页卡死
    co.set_load_mode('none')   # 核心绝杀：不要等网页转圈加载完！只要基础 HTML 骨架出来了，立刻开始抓取！
    # ============================
    
    browser = ChromiumPage(co)
    tab = browser.latest_tab
    tab.set.timeouts(page_load=3) # 缩短主页面的容忍度

    all_results = []
    seen_asins = set() 
    is_first_scan = True 

    for keyword in SEARCH_KEYWORDS:
        print(f"\n=========================================")
        print(f"🔍 正在搜索: 【{keyword}】")
        print(f"=========================================")
        
        for page in range(1, PAGES_PER_KEYWORD + 1):
            search_url = f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}&page={page}"
            try:
                tab.get(search_url)
            except Exception:
                tab.stop_loading()
            
            if is_first_scan:
                print("\n" + "⚠️ "*15)
                print("【人工安检】请通过验证码 / 确保页面正常加载...")
                input("👉 确认无误后，按下【回车键】继续！")
                print("⚠️ "*15 + "\n")
                tab.refresh()
                is_first_scan = False

            # 提取搜索页所有的商品 ASIN
            time.sleep(2)
            product_cards = tab.eles('xpath://div[@data-asin and string-length(@data-asin)=10]')
            
            if not product_cards:
                print(f"⚠️ 第 {page} 页没有找到商品，可能被拦截。")
                continue
                
            for card in product_cards:
                try:
                    asin = card.attr('data-asin')
                    if not asin or asin in seen_asins:
                        continue
                        
                    title_ele = card.ele('tag:h2')
                    product_name = title_ele.text if title_ele else ""
                    
                    # 🛡️ 第一道防线：标题封杀！带有宠物、婴儿门、地毯的直接扔掉
                    if any(banned_word in product_name.lower() for banned_word in BANNED_WORDS):
                        print(f"🚫 过滤掉无关/伪楼梯商品: {asin}")
                        continue

                    # 🚪 第二道防线：打开新标签页，进入商品详情，抓取带背景的场景图
                    clean_url = f"https://www.amazon.com/dp/{asin}"
                    detail_tab = browser.new_tab(clean_url)
                    detail_tab.set.timeouts(page_load=4)
                    
                    # 寻找左侧图片缩略图列表 (跳过第1张白底图，直接抓第3或第4张生活场景图)
                    scene_img_url = None
                    try:
                        detail_tab.wait.eles_loaded('xpath://div[@id="altImages"]//img', timeout=3)
                        alt_images = detail_tab.eles('xpath://div[@id="altImages"]//img')
                        
                        # 如果图片大于3张，拿第3张(索引2)；如果只有2张，拿第2张
                        if len(alt_images) >= 3:
                            scene_img_url = alt_images[2].attr('src')
                        elif len(alt_images) == 2:
                            scene_img_url = alt_images[1].attr('src')
                    except Exception:
                        pass
                    
                    detail_tab.close() # 拿完赶紧关掉，节约内存
                    
                    if not scene_img_url:
                        continue # 如果没找到场景图，跳过
                        
                    high_res_url = get_high_res_url(scene_img_url)
                    image_filename = f"{CUSTOM_ITEM_NAME}_{asin}_scene.jpg"
                    
                    all_results.append({
                        'ASIN': asin,
                        'Original_Name': product_name,
                        'Label': CUSTOM_ITEM_NAME,
                        'Image': image_filename,
                        'URL': clean_url,
                        'High_Res_URL': high_res_url,
                        'Save_Dir': image_save_directory
                    })
                    seen_asins.add(asin) 
                    print(f"✅ 成功捕获楼梯场景图: {asin}")
                    
                except Exception as e:
                    pass
                    
            if page < PAGES_PER_KEYWORD:
                time.sleep(random.uniform(1.5, 3.5))

    browser.quit()
    print(f"\n🎯 网页扫描完毕！共提取 {len(all_results)} 个楼梯场景图。开始多线程拔图...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        executor.map(download_image_task, all_results)

    df = pd.DataFrame(all_results)
    if not df.empty:
        df = df.drop(columns=['High_Res_URL', 'Save_Dir']) 
        df.to_excel(data_file_path, index=False)
        print(f"\n✅ 任务圆满完成！Excel 保存至 {data_file_path}")
        
    print(f"⏳ 总耗时: {time.time() - start_time:.2f} 秒")