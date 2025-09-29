# watcher.py
import os
import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.config.logging import get_logger
import re

logger = get_logger("watcher")

MODE = "Auto"
HOST_LOG_DIR = "./ctf-logs/watcher-logs/"  
LOGFILE = "watcher.log"

class Watcher(FileSystemEventHandler):
    def __init__(self, root_folder):
        super().__init__()
        self.root_folder = os.path.abspath(root_folder)
        os.makedirs(HOST_LOG_DIR, exist_ok=True)
        self.log_path = os.path.join(HOST_LOG_DIR, LOGFILE)

    def on_modified(self, event):
        global MODE
        if event.is_directory:
            return
        rel_path = os.path.relpath(event.src_path, self.root_folder)
        msg = f"File modified: {rel_path}"
        self._write_log(msg)
        if re.search(r'flag.*\.txt$', str(rel_path), re.IGNORECASE) and MODE == "Auto": # stops when flag file is changed.
            MODE = "Semi-auto"
            self._write_log("Flag file changed - switching MODE to Semi-auto")

    def _write_log(self, message: str):
        logger.info(message)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")

def main(folder_to_watch):
    global MODE
    event_handler = Watcher(folder_to_watch)
    observer = Observer()
    observer.schedule(event_handler, folder_to_watch, recursive=True)
    observer.start()
    logger.info(f"Started monitoring directory: {folder_to_watch} (MODE={MODE})")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        observer.stop()
    observer.join()
    logger.info("Watcher stopped successfully")

if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "./ctf-workspace"
    if not os.path.isdir(folder):
        logger.error(f"Directory not found: {folder}")
        sys.exit(1)
    main(folder)