from DrissionPage import ChromiumPage, ChromiumOptions
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, UnidentifiedImageError
from io import BytesIO
import pandas as pd
import requests
import os
import time
import random
import json


SEARCH_TASKS = {
    # 1. 乡村/小木屋风格 (横梁的绝对主力，木质纹理极其丰富)
    "Beams_1_Rustic_Cabin": [
        "Rustic cabin interior exposed log beams ceiling", # 乡村木屋裸露原木横梁
        "Timber frame house interior vaulted ceiling beams", # 木骨架房屋挑高横梁
        "A-frame cabin interior dark wood beams" # A字型木屋深色横梁
    ],
    
    # 2. 西班牙/地中海风格 (特征：白灰泥墙面 + 极高对比度的深色粗犷木横梁)
    "Beams_2_Spanish_Mediterranean": [
        "Spanish colonial revival interior dark wood exposed beams stucco", # 西班牙复兴白墙深色横梁
        "Mediterranean style living room timber beams ceiling", # 地中海客厅木梁
        "Hacienda style bedroom ceiling beams" # 庄园风格卧室横梁
    ],
    
    # 3. 现代农舍/谷仓改造 (特征：干净明亮的空间 + 规整的装饰性或结构性木梁)
    "Beams_3_Modern_Farmhouse": [
        "Modern farmhouse living room vaulted ceiling exposed wood beams", # 现代农舍挑高木横梁
        "Barn conversion interior structural wooden beams", # 谷仓改造结构木梁
        "Farmhouse kitchen interior ceiling beams" # 农舍厨房天花板横梁
    ],
    
    # 4. 工业风/阁楼 (特征：不仅有木梁，还有钢结构横梁，增加模型泛化能力)
    "Beams_4_Industrial_Loft": [
        "Industrial loft interior exposed steel and wood beams", # 工业阁楼钢木混合横梁
        "Warehouse conversion apartment exposed brick ceiling beams", # 仓库改造红砖与横梁
        "Modern industrial living room metal ceiling beams" # 现代工业风金属横梁
    ],
    
    # 5. 都铎/古典工匠风格 (特征：井字梁、错综复杂的屋顶骨架)
    "Beams_5_Tudor_Craftsman": [
        "Tudor style home interior exposed timber framing", # 都铎风格裸露木框架
        "Craftsman style living room ceiling box beams", # 工匠风格盒子形横梁 (假梁)
        "Coffered ceiling beams classic interior" # 经典的井字/方格横梁吊顶
    ]
}

DATASET_ROOT = "Beams_Interior_Dataset"

# ⚠️ 突破极限的参数设置 
MAX_SCROLLS = 40     # 【疯狂模式】每次搜索往下狂滚 40 次！单关键词保底抓取 200-400 张！
MAX_WORKERS = 30     # 线程数拉满，只要您的网速扛得住，拔图速度飞起
# =======================================================

def download_and_verify_image(item):
    """【带质检的超级下载器】拒绝坏图、拒绝网页、强制转标准JPG"""
    img_url = item['Image_URL']
    filename = item['Image_Name']
    save_dir = item['Save_Dir']
    filepath = os.path.join(save_dir, filename)
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8"
    }
    
    try:
        # 设置超时时间，防卡死
        response = requests.get(img_url, headers=headers, timeout=12)
        
        # 1. 拦截 HTTP 报错 (防盗链等)
        if response.status_code != 200:
            return False
            
        # 2. 拦截伪装成图片的 HTML 网页
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' in content_type:
            return False

        # 3. 核心质检：用 Pillow 尝试打开下载到内存里的二进制数据
        # 如果是坏图、残缺图，Pillow 会直接报错抛出异常
        image_data = BytesIO(response.content)
        img = Image.open(image_data)
        
        # 4. 强制洗白：统一转换为标准的 RGB 模式 (剔除透明通道Alpha，解决WebP/PNG保存为JPG的报错)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
            
        # 5. 落地保存：以标准的高质量 JPEG 格式保存
        img.save(filepath, "JPEG", quality=90)
        return True
        
    except UnidentifiedImageError:
        # 捕捉到不是图片的假文件
        return False
    except Exception as e:
        # 网络超时等其他错误
        return False

if __name__ == "__main__":
    start_time = time.time()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_base_path = os.path.join(current_dir, DATASET_ROOT)
    data_file_path = os.path.join(dataset_base_path, "Clean_Images_Info.xlsx")

    print("🚀 启动浏览器，准备执行【高清无损】图片采集...")
    co = ChromiumOptions()
    co.set_paths(browser_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_load_mode('eager') 
    
    browser = ChromiumPage(co)
    tab = browser.latest_tab

    all_results = []
    seen_urls = set() 

    for style_name, keywords in SEARCH_TASKS.items():
        print(f"\n{'='*50}")
        print(f"🏛️ 正在挖掘: 【{style_name}】")
        
        style_folder_path = os.path.join(dataset_base_path, style_name)
        os.makedirs(style_folder_path, exist_ok=True)

        for kw_index, keyword in enumerate(keywords):
            print(f"🔍 关键词 [{kw_index+1}/{len(keywords)}]: {keyword}")
            search_url = f"https://www.bing.com/images/search?q={keyword.replace(' ', '+')}&form=HDRSC2"
            
            try:
                tab.get(search_url)
                time.sleep(2)
            except Exception:
                tab.stop_loading()
            
            # 暴力滚动
            for _ in range(MAX_SCROLLS):
                tab.scroll.down(1500)
                time.sleep(random.uniform(0.6, 1.2))
            
            # 【终极破解】不再找 <img>，而是找包裹它的 <a> 标签 (class='iusc')
            # 必应把真正的高清大图地址藏在它的 'm' 属性 (一段 JSON 字符串) 里！
            anchor_eles = tab.eles('.iusc')
            valid_img_count = 0
            
            for anchor in anchor_eles:
                try:
                    m_attr = anchor.attr('m')
                    if not m_attr: continue
                    
                    # 解析 JSON，提取原图链接 (murl)
                    img_data = json.loads(m_attr)
                    high_res_url = img_data.get('murl')
                    
                    if not high_res_url or high_res_url in seen_urls:
                        continue
                        
                    # 彻底剔除常见的错误链接特征
                    if high_res_url.startswith('data:image') or 'base64' in high_res_url:
                        continue
                        
                    image_filename = f"{style_name}_kw{kw_index+1}_{valid_img_count:04d}.jpg"
                    
                    all_results.append({
                        'Style_Category': style_name,
                        'Image_Name': image_filename,
                        'Image_URL': high_res_url,
                        'Save_Dir': style_folder_path
                    })
                    seen_urls.add(high_res_url)
                    valid_img_count += 1
                except Exception:
                    pass
            
            print(f"  -> 成功嗅探到 {valid_img_count} 张【高清原图】链接！")

    browser.quit()
    print(f"\n🎯 嗅探完毕，共获得 {len(all_results)} 个原图链接。")
    print(f"⚙️ 启动 {MAX_WORKERS} 线程进行【强制质检下载】，死链和坏图将被自动过滤，请耐心等待...")

    # 启动质检下载
    success_count = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = executor.map(download_and_verify_image, all_results)
        success_count = sum(1 for r in results if r)

    # 导出台账
    df = pd.DataFrame(all_results)
    if not df.empty:
        df = df.drop(columns=['Save_Dir']) 
        df.to_excel(data_file_path, index=False)
        print(f"\n✅ 任务圆满完成！")
        print(f"📊 战报：共尝试下载 {len(all_results)} 张，质检合格并成功保存 {success_count} 张。")
        print(f"📁 完美的数据集已存放至: {DATASET_ROOT}")
    else:
        print("\n❌ 未抓取到数据。")
        
    print(f"⏳ 总耗时: {time.time() - start_time:.2f} 秒")