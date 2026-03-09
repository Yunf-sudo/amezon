from DrissionPage import ChromiumPage, ChromiumOptions
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import requests
import os
import time
import random
import re

# ==================== 🎯 核心配置区 ====================
# 【改动1】将一长串文本改为了关键词列表
# SEARCH_KEYWORDS = [
#     "computer desk", 
#     "office desk", 
#     "standing desk", 
#     "writing desk", 
#     "gaming desk", 
#     "workstation"
# ]

# SEARCH_KEYWORDS = [
#     "dining table", 
#     "vanity table", 
#     "kitchen island",
#     "bar counter",
#     "pub table",
#     "makeup desk"
# ]
#useful_table
# ==================== 🎯 亚马逊专属：室内植物/生旺化煞类爬虫搜索词 ====================
SEARCH_KEYWORDS = [
    # 1. 🌳 大型落地植物 (主攻客厅角落、沙发旁、电视柜旁，大型能量锚点)
    "large artificial floor plant",     # 大型室内落地仿真植物 (🔥极品词，场景图完美)
    "tall fake tree for living room",   # 客厅高大仿真树 (背景必有高档沙发或大窗户)
    "fiddle leaf fig tree indoor",      # 琴叶榕 (欧美中产阶级最爱，阔叶聚气代表)
    "large snake plant in pot",         # 大型虎皮兰 (尖叶，风水常用于化煞挡灾)
    "money tree plant large",           # 大型发财树 (财位标配)

    # 2. 🪴 中型盆栽/桌面植物 (主攻茶几、玄关桌、办公桌，中坚能量调节)
    "desktop plant in ceramic pot",     # 陶瓷盆桌面植物 (带陶瓷盆的图更显家居质感)
    "zz plant indoor live",             # 金钱树 (Zamioculcas zamiifolia，极具辨识度的排列叶片)
    "peace lily live plant",            # 白掌/一帆风顺 (开白花，常放在案头或卫生间化阴)
    "monstera deliciosa plant",         # 龟背竹 (极具现代家居设计感，叶片有裂纹)

    # 3. 🎋 小型/风水特化植物 (主攻书桌、置物架、窗台，微观能量点缀)
    "lucky bamboo plant indoor",        # 富贵竹 (通常在水培玻璃瓶里，带有浓烈的风水意象)
    "indoor bonsai tree live",          # 室内盆景树 (松柏类微缩盆景，极其考验模型对复杂边缘的识别)
    "succulent plants in cute pots",    # 多肉植物盆栽组合 (体积小，常排成一排)
    "small fake desk plants",           # 桌面小型仿真植物 (经常摆在电脑显示器旁边)

    # 4. 🌿 垂吊/藤蔓植物 (主攻高处书架、吊顶、窗边，垂直空间能量流动)
    "hanging plants artificial indoor", # 室内悬挂/垂吊植物 (往下垂的枝条，常在书架顶端)
    "pothos live plant trailing",       # 绿萝藤蔓 (最常见的室内垂吊植物)
    "fake ivy vines for bedroom"        # 卧室常春藤假藤蔓 (常挂在墙上或床头)
]

PAGES_PER_KEYWORD = 10            # 每个关键词抓取几页 (建议调小一点，因为词变多了)
CUSTOM_ITEM_NAME = "Aplant"     
SAVE_FOLDER_NAME = "Aplant" 
MAX_WORKERS = 20  # 并发下载图片的线程数
# =======================================================



def get_high_res_url(thumb_url):
    """通过正则清洗亚马逊图片URL，直接把缩略图变成高清大图URL"""
    return re.sub(r'\._.*?_\.', '.', thumb_url)

def download_image_task(item):
    """给多线程使用的下载任务函数"""
    img_url = item['High_Res_URL']
    filename = item['Image']
    save_dir = item['Save_Dir']
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
    except Exception as e:
        print(f"  -> ❌ 失败: {filename} ({e})")
    return False

# ==================== 主流程开始 ====================
if __name__ == "__main__":
    start_time = time.time()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    image_save_directory = os.path.join(current_dir, SAVE_FOLDER_NAME)
    data_file_path = os.path.join(current_dir, f"{SAVE_FOLDER_NAME}_info.xlsx")

    print("🚀 正在启动浏览器...")
    co = ChromiumOptions().set_paths(browser_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_load_mode('eager') 
    
    browser = ChromiumPage(co)
    tab = browser.latest_tab
    tab.set.timeouts(page_load=5) 

    all_results = []
    seen_asins = set() # 全局去重，不同关键词搜到同一个商品不会重复下载
    
    is_first_scan = True # 用于控制只在第一次打开网页时进行人工安检

    # 【改动2】外层循环遍历所有关键词，内层循环遍历页数
    for keyword in SEARCH_KEYWORDS:
        print(f"\n=========================================")
        print(f"🔍 正在切换搜索词: 【{keyword}】")
        print(f"=========================================")
        
        for page in range(1, PAGES_PER_KEYWORD + 1):
            print(f"📄 正在极速扫描 【{keyword}】 的第 {page} 页...")
            search_url = f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}&page={page}"
            
            try:
                tab.get(search_url)
            except Exception:
                tab.stop_loading()
            
            # 人工安检 (仅在整个程序的第一个网页触发一次)
            if is_first_scan:
                print("\n" + "⚠️ "*20)
                print("【人工安检环节】请通过验证码 / 更改美国邮编...")
                input("👉 确认无误后，按下【回车键 (Enter)】继续！")
                print("⚠️ "*20 + "\n")
                tab.refresh()
                is_first_scan = False
                try:
                    tab.wait.eles_loaded('xpath://div[@data-asin and string-length(@data-asin)=10]', timeout=5)
                except:
                    pass

            # 智能等待
            try:
                tab.wait.eles_loaded('xpath://div[@data-asin and string-length(@data-asin)=10]', timeout=5)
            except:
                pass 

            # 加快滚动频率
            tab.scroll.to_half()
            time.sleep(0.3) 
            tab.scroll.to_bottom()
            time.sleep(0.5) 
            
            # 提取当前页所有的商品卡片
            product_cards = tab.eles('xpath://div[@data-asin and string-length(@data-asin)=10]')
            
            if not product_cards:
                print(f"⚠️ 第 {page} 页没有找到商品卡片！可能是被验证码拦截，短暂等待...")
                time.sleep(2)
                
            for card in product_cards:
                try:
                    asin = card.attr('data-asin')
                    if not asin or asin in seen_asins:
                        continue # 如果这个商品在之前的关键词里抓过了，直接跳过
                    
                    img_ele = card.ele('tag:img')
                    title_ele = card.ele('tag:h2')
                    
                    if not img_ele:
                        continue
                        
                    thumb_url = img_ele.attr('src')
                    product_name = title_ele.text if title_ele else "N/A"
                    clean_url = f"https://www.amazon.com/dp/{asin}"
                    
                    high_res_url = get_high_res_url(thumb_url)
                    image_filename = f"{CUSTOM_ITEM_NAME}_{asin}.jpg"
                    
                    all_results.append({
                        'ASIN': asin,
                        'Original_Name': product_name,
                        'Label': CUSTOM_ITEM_NAME,
                        'Image': image_filename,
                        'URL': clean_url,
                        'High_Res_URL': high_res_url,
                        'Save_Dir': image_save_directory
                    })
                    seen_asins.add(asin) # 记录下抓取过的 ASIN
                except Exception as e:
                    pass
                    
            if page < PAGES_PER_KEYWORD:
                time.sleep(random.uniform(0.5, 1))
                
        # 换词的时候多休息一下，避免被封
        time.sleep(random.uniform(1.5, 3))

    browser.quit()
    print(f"\n🎯 网页扫描完毕！去重后共提取 {len(all_results)} 个商品。开始多线程极速拔图...")

    # 2. 多线程并发下载图片
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        executor.map(download_image_task, all_results)

    # 3. 保存 Excel
    df = pd.DataFrame(all_results)
    if not df.empty:
        df = df.drop(columns=['High_Res_URL', 'Save_Dir']) 
        df.to_excel(data_file_path, index=False)
        print(f"\n✅ 任务圆满完成！Excel 数据已保存到 {data_file_path}")
    else:
        print("\n❌ 抓取到的数据为空，未生成 Excel 文件。")
        
    print(f"⏳ 总耗时: {time.time() - start_time:.2f} 秒")