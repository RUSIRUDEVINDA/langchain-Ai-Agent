import json
import os
from datetime import datetime
from typing import List, Dict, Optional

chat_file = "chat_history.json"

def load_chats() -> List[Dict]:
    if not os.path.exists(chat_file):
        return []
    try:
        with open(chat_file, "r") as f:
            return json.load(f)
    except:
        return []

def save_chat(chat_id: str, title: str, messages: List[Dict]):
    chats = load_chats()
    # Check if chat exists
    existing = next((c for c in chats if c["id"] == chat_id), None)
    
    updated_chat = {
        "id": chat_id,
        "title": title,
        "messages": messages,
        "updated_at": datetime.now().isoformat()
    }

    if existing:
        existing.update(updated_chat)
    else:
        chats.append(updated_chat)
    
    with open(chat_file, "w") as f:
        json.dump(chats, f, indent=2)

def get_chat(chat_id: str) -> Optional[Dict]:
    chats = load_chats()
    return next((c for c in chats if c["id"] == chat_id), None)

def delete_chat(chat_id: str):
    chats = load_chats()
    chats = [c for c in chats if c["id"] != chat_id]
    with open(chat_file, "w") as f:
        json.dump(chats, f, indent=2)

def rename_chat(chat_id: str, new_title: str):
    chats = load_chats()
    for c in chats:
        if c["id"] == chat_id:
            c["title"] = new_title
            c["updated_at"] = datetime.now().isoformat()
            break
    with open(chat_file, "w") as f:
        json.dump(chats, f, indent=2)
