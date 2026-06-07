# Redis-like functionality using the file system

import os
import json
import time
from datetime import datetime

class SimpleStore:
    def __init__(self, data_dir="./data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.data_file = os.path.join(data_dir, "store.json")
        if not os.path.exists(self.data_file):
            with open(self.data_file, "w") as f:
                json.dump({}, f)
    
    def set(self, key, value):
        with open(self.data_file, "r") as f:
            data = json.load(f)
        data[key] = value
        with open(self.data_file, "w") as f:
            json.dump(data, f)
    
    def get(self, key):
        with open(self.data_file, "r") as f:
            data = json.load(f)
        return data.get(key, None)
    
    def save_state(self, state_data):
        state_file = os.path.join(self.data_dir, f"state_{int(time.time())}.json")
        with open(state_file, "w") as f:
            json.dump(state_data, f)
        return state_file

# Initialize the simple store
store = SimpleStore()
store.set('last_update', datetime.now().isoformat())
print("Simple store initialized and test data set")