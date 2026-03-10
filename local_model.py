import os
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

# 强行设置国内镜像源（确保这次能下下来）
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

# 我们要在你当前目录下建一个专门存离线模型的文件夹
SAVE_DIR = "local_gd_model"

print("🌐 开始从网络拉取模型并保存到本地，请保持网络畅通...")

# 1. 下载并保存 Processor (注意：这里用的是 tiny 版配置)
print("-> 正在保存 Processor...")
processor = AutoProcessor.from_pretrained("IDEA-Research/grounding-dino-tiny")
processor.save_pretrained(os.path.join(SAVE_DIR, "processor"))

# 2. 下载并保存 Model (注意：这里用的是 base 版权重)
print("-> 正在保存 Model...")
model = AutoModelForZeroShotObjectDetection.from_pretrained("IDEA-Research/grounding-dino-base")
model.save_pretrained(os.path.join(SAVE_DIR, "model"))

print(f"✅ 大功告成！模型已永久保存在 '{SAVE_DIR}' 文件夹中。")
print("以后你可以拔掉网线，直接读取本地模型了！")