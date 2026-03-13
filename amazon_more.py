from DrissionPage import ChromiumPage, ChromiumOptions
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import requests
import os
import time
import random
import re
import threading

# ==================== 🎯 多类别配置区 ====================
# 每个类别：(文件夹名, 标签名, [关键词列表], [黑名单词])
CATEGORIES = {

    # ── 1. 鱼缸等室内水景 ──────────────────────────────────
    "Aquarium_Indoor": {
        "label": "Aquarium",
        "keywords": [
            "aquarium fish tank living room decor complete setup",
            "large fish tank stand combo living room interior",
            "saltwater reef tank aquascape living room setup",
            "aquarium coffee table built-in fish tank furniture",
            "indoor water feature fountain zen room decor",
        ],
        "banned": ["outdoor", "pond", "garden", "koi pond", "patio", "reptile", "terrarium",
                   "toy", "plastic model", "miniature", "backyard"],
    },

    # ── 2. 窄叶枯萎/假植物 ────────────────────────────────
    "Narrow_Leaf_Fake_Plant": {
        "label": "NarrowLeaf_Fake",
        "keywords": [
            "artificial grass plant narrow blade indoor home decor",
            "fake pampas grass dried look tall floor vase indoor",
            "artificial wheat grass stem bundle home decoration",
            "faux dried lavender narrow stem indoor arrangement",
            "artificial reed grass indoor living room tall vase",
        ],
        "banned": ["outdoor", "garden", "real", "live", "fresh", "pot soil", "watering",
                   "succulent", "cactus", "tropical broad leaf"],
    },

    # ── 3. 窄叶鲜活植物 ──────────────────────────────────
    "Narrow_Leaf_Live_Plant": {
        "label": "NarrowLeaf_Live",
        "keywords": [
            "live grass plant narrow leaf indoor pot home",
            "snake plant live indoor narrow leaf low light",
            "live spider plant hanging basket indoor narrow",
            "dracaena marginata live indoor narrow leaf plant",
            "live chives herb narrow blade indoor kitchen pot",
        ],
        "banned": ["artificial", "fake", "faux", "silk", "plastic", "dried",
                   "outdoor", "garden", "broad leaf", "tropical"],
    },

    # ── 4. 宽叶枯萎/假植物 ────────────────────────────────
    "Wide_Leaf_Fake_Plant": {
        "label": "WideLeaf_Fake",
        "keywords": [
            "artificial monstera plant large leaf indoor decor",
            "fake fiddle leaf fig tree indoor living room",
            "artificial tropical palm tree indoor broad leaf",
            "faux bird of paradise plant tall indoor decor",
            "artificial banana leaf plant indoor home staging",
        ],
        "banned": ["outdoor", "garden", "real", "live", "fresh", "soil",
                   "narrow", "grass", "succulent", "seed"],
    },

    # ── 5. 宽叶鲜活植物 ──────────────────────────────────
    "Wide_Leaf_Live_Plant": {
        "label": "WideLeaf_Live",
        "keywords": [
            "live monstera deliciosa plant indoor large leaf",
            "fiddle leaf fig live tree indoor home decor",
            "live bird of paradise plant indoor wide leaf",
            "live pothos wide leaf hanging indoor plant",
            "live philodendron broad leaf indoor low light",
        ],
        "banned": ["artificial", "fake", "faux", "silk", "plastic", "dried",
                   "outdoor", "garden", "narrow", "grass"],
    },

    # ── 6. 落地窗 ────────────────────────────────────────
    "Floor_to_Ceiling_Window": {
        "label": "FloorWindow",
        "keywords": [
            "floor to ceiling window curtain panel living room",
            "blackout curtains extra long 108 inch floor window",
            "sliding glass door curtain floor to ceiling interior",
            "panoramic window treatment living room full height",
            "window seat cushion bay floor window interior room",
        ],
        "banned": ["outdoor", "garden", "patio", "car", "bathroom small",
                   "shower", "roller shade only", "mini blind"],
    },

    # ── 7. 小窗 ──────────────────────────────────────────
    "Small_Window": {
        "label": "SmallWindow",
        "keywords": [
            "small window curtain cafe valance kitchen bathroom",
            "bathroom window privacy film frosted small interior",
            "small window roman shade inside mount bedroom",
            "half window sheer curtain kitchen small window",
            "window panel short tier curtain small interior room",
        ],
        "banned": ["floor to ceiling", "patio door", "sliding door", "panoramic",
                   "outdoor", "garden", "exterior storm window"],
    },

    # ── 8. 入户门 ────────────────────────────────────────
    "Entry_Door": {
        "label": "EntryDoor",
        "keywords": [
            "front entry door wreath hanger interior foyer decor",
            "entry door smart lock keypad indoor entryway",
            "front door indoor draft stopper entryway rug set",
            "entry door sidelight curtain panel foyer interior",
            "front door bell camera indoor entryway hallway view",
        ],
        "banned": ["interior door", "bedroom door", "bathroom door", "cabinet",
                   "pet door", "dog door", "garage door", "storm door exterior only",
                   "sliding barn"],
    },

    # ── 9. 室内门 ────────────────────────────────────────
    "Interior_Door": {
        "label": "InteriorDoor",
        "keywords": [
            "interior barn door sliding hardware bedroom living room",
            "interior French door glass panel bedroom office",
            "interior door knob set bedroom hallway modern",
            "pocket door hardware kit interior room divider",
            "interior door panel solid core bedroom sound proof",
        ],
        "banned": ["front door", "entry door", "exterior", "garage", "pet door",
                   "storm door", "screen door", "outdoor", "cabinet door small"],
    },
}

PAGES_PER_KEYWORD = 10    # 每个关键词爬几页
MAX_BROWSER_TABS = 5     # 同时开几个详情页标签（太多易被封）
MAX_DOWNLOAD_WORKERS = 30  # 下载线程数
SCENE_IMG_INDEX = 2      # 取第几张图（从0计，2=第3张场景图）

# ==========================================================

def get_high_res_url(thumb_url):
    return re.sub(r'\._.*?_\.', '.', thumb_url)

def download_image_task(item):
    img_url = item['High_Res_URL']
    filename = item['Image']
    save_dir = item['Save_Dir']
    os.makedirs(save_dir, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(img_url, headers=headers, stream=True, timeout=10)
        if r.status_code == 200:
            with open(os.path.join(save_dir, filename), 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            print(f"  📸 {filename}")
            return True
    except Exception:
        pass
    return False

def scrape_category(browser, tab, category_name, config, base_dir, seen_asins_global, lock):
    """爬取单个类别，返回结果列表"""
    label = config["label"]
    keywords = config["keywords"]
    banned = config["banned"]
    save_dir = os.path.join(base_dir, category_name)
    results = []
    local_seen = set()

    print(f"\n{'='*50}")
    print(f"🗂️  开始爬取类别: 【{category_name}】标签: {label}")
    print(f"{'='*50}")

    for keyword in keywords:
        print(f"\n  🔍 关键词: {keyword}")
        for page in range(1, PAGES_PER_KEYWORD + 1):
            url = f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}&page={page}"
            try:
                tab.get(url)
            except Exception:
                tab.stop_loading()

            time.sleep(random.uniform(1.5, 2.5))
            cards = tab.eles('xpath://div[@data-asin and string-length(@data-asin)=10]')
            if not cards:
                print(f"    ⚠️ 第{page}页无商品，跳过")
                continue

            for card in cards:
                try:
                    asin = card.attr('data-asin')
                    if not asin:
                        continue

                    # 全局去重（同一个ASIN只采集一次）
                    with lock:
                        if asin in seen_asins_global:
                            continue
                        if asin in local_seen:
                            continue

                    title_ele = card.ele('tag:h2')
                    product_name = title_ele.text if title_ele else ""

                    if any(b.lower() in product_name.lower() for b in banned):
                        print(f"    🚫 过滤: {asin} | {product_name[:40]}")
                        continue

                    clean_url = f"https://www.amazon.com/dp/{asin}"
                    detail_tab = browser.new_tab(clean_url)
                    detail_tab.set.timeouts(page_load=4)

                    scene_img_url = None
                    try:
                        detail_tab.wait.eles_loaded('xpath://div[@id="altImages"]//img', timeout=3)
                        alt_images = detail_tab.eles('xpath://div[@id="altImages"]//img')
                        if len(alt_images) > SCENE_IMG_INDEX:
                            scene_img_url = alt_images[SCENE_IMG_INDEX].attr('src')
                        elif len(alt_images) >= 2:
                            scene_img_url = alt_images[1].attr('src')
                        elif len(alt_images) == 1:
                            scene_img_url = alt_images[0].attr('src')
                    except Exception:
                        pass
                    finally:
                        detail_tab.close()

                    if not scene_img_url:
                        continue

                    high_res = get_high_res_url(scene_img_url)
                    img_filename = f"{label}_{asin}_scene.jpg"

                    results.append({
                        'Category': category_name,
                        'ASIN': asin,
                        'Original_Name': product_name,
                        'Label': label,
                        'Image': img_filename,
                        'URL': clean_url,
                        'High_Res_URL': high_res,
                        'Save_Dir': save_dir,
                    })

                    with lock:
                        seen_asins_global.add(asin)
                    local_seen.add(asin)
                    print(f"    ✅ {asin} | {product_name[:45]}")

                except Exception:
                    pass

            if page < PAGES_PER_KEYWORD:
                time.sleep(random.uniform(1.0, 2.5))

    print(f"\n  🎯 【{category_name}】完成，采集 {len(results)} 张")
    return results


# ==================== 主流程 ====================
if __name__ == "__main__":
    import sys
    start_time = time.time()
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "TrainingData")

    print("🚀 启动浏览器（极速DOM模式）...")
    co = ChromiumOptions().set_paths(browser_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.no_imgs(True)
    co.mute(True)
    co.set_load_mode('none')

    browser = ChromiumPage(co)
    tab = browser.latest_tab
    tab.set.timeouts(page_load=3)

    # ── 人工验证一次 ──
    first_url = "https://www.amazon.com/s?k=aquarium+fish+tank+living+room"
    try:
        tab.get(first_url)
    except Exception:
        tab.stop_loading()

    print("\n" + "⚠️ "*15)
    print("【首次人工安检】请通过验证码/确保页面正常加载...")
    input("👉 确认正常后按【回车键】继续！")
    print("⚠️ "*15 + "\n")

    # ── 逐类别爬取（串行，避免被Amazon封） ──
    all_results = []
    seen_asins_global = set()
    lock = threading.Lock()

    for cat_name, cat_config in CATEGORIES.items():
        cat_results = scrape_category(
            browser, tab,
            cat_name, cat_config,
            base_dir,
            seen_asins_global, lock
        )
        all_results.extend(cat_results)

    browser.quit()
    print(f"\n🌐 全部类别扫描完毕！共 {len(all_results)} 条记录，开始多线程下载图片...")

    # ── 多线程下载 ──
    with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as executor:
        futures = [executor.submit(download_image_task, item) for item in all_results]
        done = sum(1 for f in as_completed(futures) if f.result())
    print(f"  ✅ 成功下载 {done} / {len(all_results)} 张图片")

    # ── 保存Excel（按类别分sheet） ──
    excel_path = os.path.join(base_dir, "ALL_categories_info.xlsx")
    os.makedirs(base_dir, exist_ok=True)
    df_all = pd.DataFrame(all_results).drop(columns=['High_Res_URL', 'Save_Dir'], errors='ignore')

    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        df_all.to_excel(writer, sheet_name='ALL', index=False)
        for cat in CATEGORIES:
            df_cat = df_all[df_all['Category'] == cat]
            if not df_cat.empty:
                sheet_name = cat[:31]  # Excel sheet名最长31字符
                df_cat.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"\n📊 Excel 已保存: {excel_path}")
    print(f"📁 图片根目录: {base_dir}")
    print(f"⏳ 总耗时: {time.time() - start_time:.2f} 秒")

    # ── 打印各类别统计 ──
    print("\n📈 各类别采集统计:")
    for cat in CATEGORIES:
        count = sum(1 for r in all_results if r['Category'] == cat)
        print(f"  {cat:<35} {count} 张")