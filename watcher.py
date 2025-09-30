# watcher.py
import os
import sys
import time
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.config.logging import get_logger
from src.utils.state_manager import get_mode, set_mode, update_state, get_model_token_state
import re

load_dotenv()
logger = get_logger("watcher")

# Constants
HOST_LOG_DIR = "./ctf-logs/watcher-logs/"
LOGFILE = "watcher.log"
WATCH_INTERVAL = 30  # seconds
TOKEN_DISPLAY_INTERVAL = 30  # seconds
DEFAULT_WORKSPACE = "./ctf-workspace"

class Watcher(FileSystemEventHandler):
    def __init__(self, root_folder):
        super().__init__()
        self.root_folder = os.path.abspath(root_folder)
        os.makedirs(HOST_LOG_DIR, exist_ok=True)
        self.log_path = os.path.join(HOST_LOG_DIR, LOGFILE)

    def on_modified(self, event):
        if event.is_directory:
            return
        rel_path = os.path.relpath(event.src_path, self.root_folder)
        msg = f"File modified: {rel_path}"
        self._write_log(msg)

        # Check if flag file was modified and mode is still auto
        if re.search(r'flag.*\.txt$', str(rel_path), re.IGNORECASE):
            current_mode = get_mode()
            if current_mode == "auto":
                set_mode("semi-auto")
                update_state(flag_found=True)
                self._write_log("Flag file changed - switching MODE to semi-auto")

    def _write_log(self, message: str):
        logger.info(message)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")

def main(folder_to_watch):
    # Get model from environment
    selected_model = os.getenv("OPENROUTER_MODEL", "unknown")

    event_handler = Watcher(folder_to_watch)
    observer = Observer()
    observer.schedule(event_handler, folder_to_watch, recursive=True)
    observer.start()
    current_mode = get_mode()

    logger.info(f"Started monitoring directory: {folder_to_watch}")
    logger.info(f"MODE={current_mode} | MODEL={selected_model}")
    print(f"🔍 Watcher started - Monitoring: {folder_to_watch}")
    print(f"   • Mode: {current_mode}")
    print(f"   • Model: {selected_model}")

    try:
        last_token_display = time.time()
        last_token_stats = get_model_token_state(selected_model)
        while True:
            time.sleep(WATCH_INTERVAL)

            # Check for token stat changes
            current_token_stats = get_model_token_state(selected_model)
            stats_changed = (
                current_token_stats.get('request_count', 0) != last_token_stats.get('request_count', 0) or
                current_token_stats.get('total_tokens', 0) != last_token_stats.get('total_tokens', 0) or
                current_token_stats.get('total_cost', 0) != last_token_stats.get('total_cost', 0)
            )

            # Display token stats only if there are changes
            if stats_changed and current_token_stats.get('request_count', 0) > 0:
                print(f"\n📊 Overall Token Stats ({selected_model}):")
                print(f"   • Total requests (all sessions): {current_token_stats.get('request_count', 0)}")
                print(f"   • Total tokens (all sessions): {current_token_stats.get('total_tokens', 0)}")
                print(f"   • Cost (all sessions): {current_token_stats.get('total_cost', 0):.6f} credits")
                last_token_stats = current_token_stats

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        observer.stop()
    observer.join()
    logger.info("Watcher stopped successfully")

if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WORKSPACE
    if not os.path.isdir(folder):
        logger.error(f"Directory not found: {folder}")
        sys.exit(1)
    main(folder)