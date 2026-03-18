import os
from glob import glob

SUPPORTED_IMAGES = (".jpg", ".jpeg", ".png")
SUPPORTED_VIDEOS = (".mp4", ".mov", ".avi", ".mkv")

def list_media(media_dir="./media"):
    os.makedirs(media_dir, exist_ok=True)
    files = []
    for ext in list(SUPPORTED_IMAGES) + list(SUPPORTED_VIDEOS):
        files += glob(os.path.join(media_dir, f"*{ext}"))
    files.sort(reverse=True)  # más recientes primero
    return files

def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_IMAGES

def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_VIDEOS
