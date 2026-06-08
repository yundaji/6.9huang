import os
import json
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHANNEL_ID = os.getenv("TARGET_CHANNEL_ID")
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "")
COPY_MODE = os.getenv("COPY_MODE", "copy")  # copy 或 forward

OFFSET_FILE = "offset.json"

if not BOT_TOKEN:
    raise RuntimeError("缺少 BOT_TOKEN")

if not TARGET_CHANNEL_ID:
    raise RuntimeError("缺少 TARGET_CHANNEL_ID")

SOURCE_LIST = [x.strip() for x in SOURCE_CHANNELS.split(",") if x.strip()]

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def load_offset():
    if not os.path.exists(OFFSET_FILE):
        return 0

    try:
        with open(OFFSET_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return int(data.get("offset", 0))
    except Exception:
        return 0


def save_offset(offset):
    with open(OFFSET_FILE, "w", encoding="utf-8") as f:
        json.dump({"offset": offset}, f, ensure_ascii=False, indent=2)


def tg_post(method, data):
    url = f"{API_URL}/{method}"
    r = requests.post(url, json=data, timeout=30)
    try:
        result = r.json()
    except Exception:
        raise RuntimeError(r.text)

    if not result.get("ok"):
        raise RuntimeError(result)

    return result


def get_updates(offset):
    data = {
        "offset": offset,
        "timeout": 0,
        "allowed_updates": ["channel_post"],
    }
    return tg_post("getUpdates", data).get("result", [])


def is_source_channel(chat):
    """
    支持两种写法：
    1. 频道 username：@example_channel
    2. 频道数字 ID：-100xxxxxxxxxx
    """
    chat_id = str(chat.get("id"))
    username = chat.get("username")

    possible = [chat_id]
    if username:
        possible.append("@" + username)

    if not SOURCE_LIST:
        return True

    return any(x in SOURCE_LIST for x in possible)


def is_video_message(msg):
    if msg.get("video"):
        return True

    doc = msg.get("document")
    if doc:
        mime = doc.get("mime_type", "")
        file_name = doc.get("file_name", "")
        if mime.startswith("video/"):
            return True
        if file_name.lower().endswith((".mp4", ".mov", ".mkv", ".avi")):
            return True

    return False


def forward_or_copy(msg):
    from_chat_id = msg["chat"]["id"]
    message_id = msg["message_id"]

    if COPY_MODE == "forward":
        return tg_post("forwardMessage", {
            "chat_id": TARGET_CHANNEL_ID,
            "from_chat_id": from_chat_id,
            "message_id": message_id,
        })

    return tg_post("copyMessage", {
        "chat_id": TARGET_CHANNEL_ID,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
    })


def main():
    offset = load_offset()
    updates = get_updates(offset + 1 if offset else None)

    if not updates:
        print("没有新消息")
        return

    max_update_id = offset
    sent_count = 0

    for update in updates:
        update_id = update.get("update_id", 0)
        max_update_id = max(max_update_id, update_id)

        msg = update.get("channel_post")
        if not msg:
            continue

        chat = msg.get("chat", {})

        if not is_source_channel(chat):
            print(f"跳过来源频道：{chat.get('title')} / {chat.get('id')}")
            continue

        if not is_video_message(msg):
            print("跳过：不是视频")
            continue

        try:
            forward_or_copy(msg)
            sent_count += 1
            print(f"已转发视频：来源 {chat.get('title')}，消息ID {msg.get('message_id')}")
        except Exception as e:
            print(f"转发失败：{e}")

    save_offset(max_update_id)
    print(f"完成，本次转发 {sent_count} 个视频")


if __name__ == "__main__":
    main()
