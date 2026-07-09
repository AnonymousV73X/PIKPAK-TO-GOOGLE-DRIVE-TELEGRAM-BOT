"""
PikPak to Google Drive Transfer Bot for Linux Server
Multi-user version with independent configurations and transfers
"""

import os
import subprocess
import sys
import json
import time
import threading
import re
import random
import string
import urllib.request
import zipfile
import stat
from datetime import datetime
from pathlib import Path
import shutil
import sqlite3
from contextlib import contextmanager
import html

# Install required packages if not already installed
def install_package(package):
    try:
        __import__(package)
        print(f"{package} is already installed.")
    except ImportError:
        print(f"Installing {package}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--user", package]
        )
        print(f"{package} installed successfully.")


# Install required packages
install_package("pyTelegramBotAPI")
import telebot
from telebot.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

# Initialize the Telegram bot
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
bot = telebot.TeleBot(BOT_TOKEN)

# Database setup
DB_PATH = os.path.expanduser("~/.pikpak_gdrive_bot.db")


@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db_connection() as conn:
        conn.execute(
            """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            config TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        )
        conn.execute(
            """
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            status TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            destination_folder TEXT,
            files_count INTEGER,
            total_size TEXT,
            error_message TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """
        )
        conn.commit()


# Initialize database on startup
init_db()


# User management
class UserManager:
    @staticmethod
    def get_user(user_id):
        with get_db_connection() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return dict(user) if user else None

    @staticmethod
    def save_user(user_id, username, first_name, config):
        with get_db_connection() as conn:
            conn.execute(
                """
            INSERT OR REPLACE INTO users (user_id, username, first_name, config)
            VALUES (?, ?, ?, ?)
            """,
                (user_id, username, first_name, config),
            )
            conn.commit()

    @staticmethod
    def get_user_config(user_id):
        user = UserManager.get_user(user_id)
        return user["config"] if user and user["config"] else None

    @staticmethod
    def user_exists(user_id):
        with get_db_connection() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
                ).fetchone()
                is not None
            )

    @staticmethod
    def save_transfer(
        user_id,
        status,
        start_time,
        end_time,
        destination_folder,
        files_count,
        total_size,
        error_message,
    ):
        with get_db_connection() as conn:
            conn.execute(
                """
            INSERT INTO transfers (user_id, status, start_time, end_time, destination_folder, files_count, total_size, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    user_id,
                    status,
                    start_time,
                    end_time,
                    destination_folder,
                    files_count,
                    total_size,
                    error_message,
                ),
            )
            conn.commit()

    @staticmethod
    def get_user_transfers(user_id, limit=5):
        with get_db_connection() as conn:
            transfers = conn.execute(
                """
            SELECT * FROM transfers 
            WHERE user_id = ? 
            ORDER BY start_time DESC 
            LIMIT ?
            """,
                (user_id, limit),
            ).fetchall()
            return [dict(t) for t in transfers]


# Transfer management
class TransferManager:
    def __init__(self, user_id):
        self.user_id = user_id
        self.transfer_in_progress = False
        self.transfer_thread = None
        self.update_thread = None
        self.network_monitor = None
        self.status_message = None
        self.status_chat_id = None
        self.status_message_id = None
        self.transfer_logs = []
        self.transfer_process = None
        self.stop_requested = False
        self.status_lock = threading.Lock()
        self.user_config = UserManager.get_user_config(user_id)

        if not self.user_config:
            raise ValueError(
                "No rclone configuration found. Please set it using /config command."
            )

    def run_command(self, command, capture_output=True, shell=True):
        try:
            if capture_output:
                result = subprocess.run(
                    command, shell=shell, capture_output=True, text=True
                )
                stdout = result.stdout.strip() if result.stdout else ""
                stderr = result.stderr.strip() if result.stderr else ""
                return result.returncode == 0, stdout, stderr
            else:
                result = subprocess.run(command, shell=shell)
                return result.returncode == 0, "", ""
        except Exception as e:
            self.log_error(f"Command execution failed: {e}")
            return False, "", str(e)

    def log_info(self, message):
        output = f"[INFO] {message}"
        print(output)
        self.transfer_logs.append(output)

    def log_success(self, message):
        output = f"[SUCCESS] {message}"
        print(output)
        self.transfer_logs.append(output)

    def log_warning(self, message):
        output = f"[WARNING] {message}"
        print(output)
        self.transfer_logs.append(output)

    def log_error(self, message):
        output = f"[ERROR] {message}"
        print(output)
        self.transfer_logs.append(output)

    def log_header(self, message):
        output = f"{'='*50}"
        print(output)
        self.transfer_logs.append(output)
        output = f"{message}"
        print(output)
        self.transfer_logs.append(output)
        output = f"{'='*50}"
        print(output)
        self.transfer_logs.append(output)

    def install_rclone(self):
        rclone_path = os.path.expanduser(f"~/.local/bin/rclone_{self.user_id}")
        if os.path.exists(rclone_path) and os.access(rclone_path, os.X_OK):
            self.log_success("rclone is already installed.")
            return True, rclone_path

        self.log_info("Installing rclone...")
        bin_dir = os.path.dirname(rclone_path)
        os.makedirs(bin_dir, exist_ok=True)
        download_url = "https://downloads.rclone.org/rclone-current-linux-amd64.zip"
        temp_dir = f"/tmp/rclone_install_{self.user_id}"
        zip_path = os.path.join(temp_dir, "rclone.zip")

        try:
            os.makedirs(temp_dir, exist_ok=True)
            self.log_info(f"Downloading rclone from {download_url}...")
            urllib.request.urlretrieve(download_url, zip_path)
            self.log_info("Extracting rclone...")
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            extracted_dirs = [
                d
                for d in os.listdir(temp_dir)
                if os.path.isdir(os.path.join(temp_dir, d)) and d.startswith("rclone-")
            ]

            if not extracted_dirs:
                self.log_error("Could not find extracted rclone directory.")
                return False, None

            extracted_dir = os.path.join(temp_dir, extracted_dirs[0])
            rclone_binary = os.path.join(extracted_dir, "rclone")
            self.log_info(f"Installing rclone to {rclone_path}...")
            shutil.copy2(rclone_binary, rclone_path)
            os.chmod(
                rclone_path,
                stat.S_IRWXU
                | stat.S_IRGRP
                | stat.S_IXGRP
                | stat.S_IROTH
                | stat.S_IXOTH,
            )
            shutil.rmtree(temp_dir, ignore_errors=True)

            success, output, _ = self.run_command(f"{rclone_path} version")
            if success:
                self.log_success(
                    f"rclone installed successfully: {output.splitlines()[0]}"
                )
                return True, rclone_path
            else:
                self.log_error("rclone installation verification failed.")
                return False, None
        except Exception as e:
            self.log_error(f"Failed to install rclone: {str(e)}")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            return False, None

    def create_config(self, rclone_path):
        config_file = os.path.expanduser(f"~/.config/rclone/rclone_{self.user_id}.conf")
        config_dir = Path(config_file).parent
        config_dir.mkdir(parents=True, exist_ok=True)

        with open(config_file, "w") as f:
            f.write(self.user_config)

        self.log_success(f"Configuration created at {config_file}")
        return True, config_file

    def verify_remotes(self, rclone_path, config_file):
        self.log_info("Verifying remote connections...")
        pikpak_remote = "PIKKY"
        gdrive_remote = "GDRIVE"

        for remote_name in [pikpak_remote, gdrive_remote]:
            self.log_info(f"Testing {remote_name} connection...")
            success, _, error = self.run_command(
                f"{rclone_path} --config {config_file} lsd {remote_name}:"
            )
            if not success:
                self.log_error(f"{remote_name} connection failed: {error}")
                return False, None, None
            self.log_success(f"{remote_name} connection verified.")

        return True, pikpak_remote, gdrive_remote

    def analyze_and_find_videos(self, rclone_path, config_file, pikpak_remote):
        self.log_info("Analyzing PikPak contents for video files...")
        video_extensions = [
            "mp4",
            "mkv",
            "avi",
            "mov",
            "wmv",
            "flv",
            "webm",
            "mpg",
            "mpeg",
            "m4v",
            "3gp",
        ]

        success, all_files_str, error = self.run_command(
            f"{rclone_path} --config {config_file} lsf {pikpak_remote}: --recursive"
        )

        if not success:
            self.log_warning(f"Could not list files in PikPak: {error}")
            return False, None, None

        all_files = all_files_str.split("\n") if all_files_str else []
        video_files = [
            f for f in all_files if f.split(".")[-1].lower() in video_extensions
        ]

        self.log_info(f"Found {len(all_files)} total files.")

        if video_files:
            self.log_success(f"Found {len(video_files)} video files to transfer.")
            self.log_info("Sample video files:")
            for video in video_files[:7]:
                print(f"  - {video}")
                self.transfer_logs.append(f"  - {video}")
            return True, video_files, video_extensions
        else:
            self.log_warning("No video files found in PikPak. Nothing to transfer.")
            return False, None, None

    def transfer_videos(
        self,
        rclone_path,
        config_file,
        pikpak_remote,
        gdrive_remote,
        destination_folder,
        video_extensions,
    ):
        self.log_info(
            f"Starting video transfer to {gdrive_remote}:{destination_folder}"
        )
        self.log_warning("This may take a while depending on file sizes...")

        self.network_monitor = NetworkMonitor()
        self.network_monitor.start_monitoring()

        filter_rules = (
            ["+ */"] + [f"+ *.{ext}" for ext in video_extensions] + ["- .*", "- *"]
        )

        command = f"""{rclone_path} --config {config_file} sync {pikpak_remote}: "{gdrive_remote}:{destination_folder}" \
            {' '.join([f'--filter "{rule}"' for rule in filter_rules])} \
            --progress --stats 30s --stats-one-line \
            --transfers 4 --checkers 8 --fast-list --checksum \
            --drive-chunk-size 64M --buffer-size 32M"""

        try:
            process = subprocess.Popen(command, shell=True)
            self.transfer_process = process

            while True:
                ret_code = process.poll()
                if ret_code is not None:
                    break
                if self.stop_requested:
                    process.terminate()
                    time.sleep(2)
                    if process.poll() is None:
                        process.kill()
                    break
                time.sleep(1)

            success = process.returncode == 0
            self.transfer_process = None
            self.network_monitor.stop_monitoring()

            if success:
                self.log_success("Video transfer completed successfully!")
                return True
            else:
                self.log_error("Video transfer failed.")
                return False
        except KeyboardInterrupt:
            self.log_warning("\nTransfer interrupted by user.")
            self.network_monitor.stop_monitoring()
            return False
        except Exception as e:
            self.log_error(f"An unexpected error occurred: {e}")
            self.network_monitor.stop_monitoring()
            return False

    def show_summary(self, destination_folder, start_time, video_files):
        end_time = datetime.now()
        duration = end_time - start_time

        self.log_header("Here Is The Transfer Summary")
        print(f"Start time: {format_datetime(start_time)}")
        print(f"End time: {format_datetime(end_time)}")
        print(f"Duration: {str(duration).split('.')[0]}")
        print(f"Source: PIKKY:")
        print(f"Destination: GDRIVE:{destination_folder}")
        print(f"Files transferred: {len(video_files) if video_files else 0}")
        print("=" * 50)

        self.transfer_logs.append(f"Start time: {format_datetime(start_time)}")
        self.transfer_logs.append(f"End time: {format_datetime(end_time)}")
        self.transfer_logs.append(f"Duration: {str(duration).split('.')[0]}")
        self.transfer_logs.append(f"Source: PIKKY:")
        self.transfer_logs.append(f"Destination: GDRIVE:{destination_folder}")
        self.transfer_logs.append(
            f"Files transferred: {len(video_files) if video_files else 0}"
        )

    def run_transfer(self):
        self.transfer_in_progress = True
        self.stop_requested = False
        start_time = datetime.now()
        destination_folder = None
        video_files = None
        error_message = None

        try:
            self.log_header(
                f"Automated PikPak to Google Drive Video Transfer for User {self.user_id}"
            )
            self.log_info(f"Started at: {format_datetime(start_time)}")

            # Install rclone
            success, rclone_path = self.install_rclone()
            if not success:
                error_message = "Failed to install rclone"
                self.transfer_in_progress = False
                return

            # Create config
            success, config_file = self.create_config(rclone_path)
            if not success:
                error_message = "Failed to create rclone configuration"
                self.transfer_in_progress = False
                return

            # Verify remotes
            success, pikpak_remote, gdrive_remote = self.verify_remotes(
                rclone_path, config_file
            )
            if not success:
                error_message = "Failed to verify remote connections"
                self.transfer_in_progress = False
                return

            # Analyze and find videos
            success, video_files, video_extensions = self.analyze_and_find_videos(
                rclone_path, config_file, pikpak_remote
            )
            if not success:
                self.transfer_in_progress = False
                return

            # Generate destination folder
            alien_name = generate_alien_name()
            destination_folder = (
                f"{alien_name}-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
            )

            # Transfer videos
            success = self.transfer_videos(
                rclone_path,
                config_file,
                pikpak_remote,
                gdrive_remote,
                destination_folder,
                video_extensions,
            )

            if success:
                self.show_summary(destination_folder, start_time, video_files)
                self.log_success("Script completed successfully!")
                status = "completed"
            else:
                self.log_error("Script finished with errors.")
                status = "failed"
                error_message = "Transfer failed"

            # Save transfer record
            UserManager.save_transfer(
                self.user_id,
                status,
                start_time,
                datetime.now(),
                destination_folder,
                len(video_files) if video_files else 0,
                "Unknown",
                error_message,
            )

            self.transfer_in_progress = False
        except KeyboardInterrupt:
            self.log_warning("\nTransfer interrupted by user.")
            if self.network_monitor:
                self.network_monitor.stop_monitoring()
            self.transfer_in_progress = False

            # Save transfer record
            UserManager.save_transfer(
                self.user_id,
                "cancelled",
                start_time,
                datetime.now(),
                destination_folder,
                len(video_files) if video_files else 0,
                "Unknown",
                "Cancelled by user",
            )
        except Exception as e:
            self.log_error(f"An unexpected error occurred: {e}")
            if self.network_monitor:
                self.network_monitor.stop_monitoring()
            self.transfer_in_progress = False

            # Save transfer record
            UserManager.save_transfer(
                self.user_id,
                "failed",
                start_time,
                datetime.now(),
                destination_folder,
                len(video_files) if video_files else 0,
                "Unknown",
                str(e),
            )
        finally:
            self.stop_requested = False


# Network Monitor Class
class NetworkMonitor:
    def __init__(self):
        self.monitoring = False
        self.monitor_thread = None
        self.previous_stats = {}
        self.start_time = None
        self.total_uploaded = 0
        self.total_downloaded = 0
        self.current_upload_speed = 0
        self.current_download_speed = 0
        self.last_update_time = None

    def get_network_stats(self):
        try:
            with open("/proc/net/dev", "r") as f:
                lines = f.readlines()

            data_lines = lines[2:]
            stats = {}

            for line in data_lines:
                if ":" not in line:
                    continue

                interface, data = line.split(":", 1)
                interface = interface.strip()
                data_values = data.split()

                if len(data_values) >= 16:
                    bytes_received = int(data_values[0])
                    bytes_transmitted = int(data_values[8])
                    stats[interface] = {
                        "bytes_received": bytes_received,
                        "bytes_transmitted": bytes_transmitted,
                    }

            return stats
        except Exception as e:
            print(f"Error getting network stats: {e}")
            return {}

    def format_size(self, bytes_value):
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_value < 1024.0:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.2f} PB"

    def format_speed(self, bytes_per_sec):
        return self.format_size(bytes_per_sec) + "/s"

    def calculate_speeds(self, current_stats, time_elapsed):
        if not self.previous_stats or time_elapsed == 0:
            return 0, 0

        total_received_diff = 0
        total_transmitted_diff = 0

        for interface in current_stats:
            if interface in self.previous_stats:
                received_diff = (
                    current_stats[interface]["bytes_received"]
                    - self.previous_stats[interface]["bytes_received"]
                )
                transmitted_diff = (
                    current_stats[interface]["bytes_transmitted"]
                    - self.previous_stats[interface]["bytes_transmitted"]
                )

                if received_diff > 0:
                    total_received_diff += received_diff
                if transmitted_diff > 0:
                    total_transmitted_diff += transmitted_diff

        download_speed = total_received_diff / time_elapsed
        upload_speed = total_transmitted_diff / time_elapsed

        return download_speed, upload_speed

    def get_stats_string(self, user_id):
        current_time = datetime.now()
        elapsed = current_time - self.start_time if self.start_time else None
        elapsed_str = str(elapsed).split(".")[0] if elapsed else "00:00:00"

        status = (
            "ACTIVE"
            if self.current_upload_speed > 1024 or self.current_download_speed > 1024
            else "IDLE"
        )

        status_line = "🌐 NETWORK STATUS & BANDWIDTH 🌐\n"
        status_line += "─" * 18 + "\n"
        status_line += (
            f"🔸Upload Speed: {self.format_speed(self.current_upload_speed)}\n"
        )
        status_line += (
            f"🔹Total Data Uploaded: {self.format_size(self.total_uploaded)}\n"
        )
        status_line += "─" * 18 + "\n"
        status_line += (
            f"🔹 Download Speed: {self.format_speed(self.current_download_speed)}\n"
        )
        status_line += (
            f"◽️ Total Data Downloaded: {self.format_size(self.total_downloaded)}\n"
        )
        status_line += "─" * 18 + "\n"
        status_line += f"▪️ Elapsed Time: {elapsed_str}\n"
        status_line += f"🎴 Current Status: {status}"

        # Create inline keyboard
        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton(
                "🔄 Refresh", callback_data=f"refresh_status_{user_id}"
            ),
            InlineKeyboardButton("⏹️ Stop", callback_data=f"stop_transfer_{user_id}"),
        )

        return status_line, keyboard

    def monitor_loop(self, interval=1.0):
        self.start_time = datetime.now()
        self.previous_stats = self.get_network_stats()

        if not self.previous_stats:
            print("Could not get initial network stats. Monitoring stopped.")
            self.monitoring = False
            return

        print("Network monitoring started.")

        try:
            while self.monitoring:
                time.sleep(interval)
                current_stats = self.get_network_stats()

                if not current_stats:
                    continue

                current_time = datetime.now()

                if self.previous_stats:
                    time_elapsed = (
                        current_time - self.last_update_time
                    ).total_seconds()
                    download_speed, upload_speed = self.calculate_speeds(
                        current_stats, time_elapsed
                    )

                    self.current_download_speed = download_speed
                    self.current_upload_speed = upload_speed
                    self.total_downloaded += download_speed
                    self.total_uploaded += upload_speed

                self.previous_stats = current_stats
                self.last_update_time = current_time
        except Exception as e:
            print(f"Error in network monitoring: {e}")
            self.monitoring = False

    def start_monitoring(self, interval=1.0):
        if self.monitoring:
            print("Network monitoring is already running.")
            return

        self.monitoring = True
        self.last_update_time = datetime.now()
        self.total_uploaded = 0
        self.total_downloaded = 0
        self.current_upload_speed = 0
        self.current_download_speed = 0

        self.monitor_thread = threading.Thread(
            target=self.monitor_loop, args=(interval,)
        )
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def stop_monitoring(self):
        if not self.monitoring:
            return

        self.monitoring = False

        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)

        print("\n" + "=" * 50)
        print("Full Network Usage Summary")
        print(f"Total Upload: {self.format_size(self.total_uploaded)}")
        print(f"Total Download: {self.format_size(self.total_downloaded)}")
        print("=" * 50)


# Global transfer managers dictionary
transfer_managers = {}


# Helper functions
def generate_alien_name():
    prefixes = [
        "Zor",
        "Xen",
        "Qua",
        "Vor",
        "Kly",
        "Sor",
        "Tyr",
        "Neb",
        "Gal",
        "Cos",
        "Andro",
        "Nebu",
        "Puls",
        "Quas",
        "Supern",
        "Epsil",
        "Centa",
        "Proxim",
        "Anta",
        "Betel",
        "Rigel",
        "Alde",
        "Arctu",
        "Spic",
        "Poll",
        "Fomal",
        "Deneb",
        "Regul",
        "Cast",
        "Bella",
        "Mira",
        "Alta",
        "Algo",
        "Capel",
        "Canop",
    ]
    suffixes = [
        "blax",
        "dor",
        "gon",
        "thar",
        "zon",
        "nax",
        "tar",
        "vax",
        "rox",
        "lax",
        "meda",
        "ula",
        "axy",
        "ion",
        "us",
        "ar",
        "ix",
        "um",
        "ra",
        "is",
        "nova",
        "tar",
        "ius",
        "on",
        "os",
        "a",
        "us",
        "is",
        "or",
        "us",
    ]

    name = f"{random.choice(prefixes)}{random.choice(suffixes)}"
    if random.random() > 0.7:
        name += str(random.randint(1, 999))
    return name


def format_datetime(dt):
    return dt.strftime("%b %d, %Y at %I:%M %p")


def remove_ansi_codes(text):
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


def send_long_message(chat_id, text, parse_mode=None, reply_markup=None):
    """
    Send a long message by splitting it into smaller chunks if needed.
    Telegram has a limit of 4096 characters per message.
    """
    max_length = 4096

    if len(text) <= max_length:
        return bot.send_message(
            chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup
        )

    # Split the message into chunks while preserving formatting
    chunks = []
    current_chunk = ""

    # Handle HTML and code blocks specially to avoid breaking them
    in_code_block = False
    in_html_tag = False

    lines = text.split("\n")
    for line in lines:
        # Check if we're entering or leaving a code block
        if "<code>" in line and "</code>" not in line:
            in_code_block = True
        elif "</code>" in line and "<code>" not in line:
            in_code_block = False

        # If adding this line would exceed the limit, start a new chunk
        if len(current_chunk) + len(line) + 1 > max_length:
            # If we're in a code block, try to find a good breaking point
            if in_code_block:
                # Try to split the line if it's very long
                if len(line) > max_length - len(current_chunk):
                    # Split the line into parts that fit
                    remaining_space = max_length - len(current_chunk) - 1
                    if remaining_space > 0:
                        current_chunk += "\n" + line[:remaining_space]
                        chunks.append(current_chunk)
                        current_chunk = "<code>" + line[remaining_space:]
                    else:
                        chunks.append(current_chunk)
                        current_chunk = "<code>" + line
                else:
                    current_chunk += "\n" + line
                    chunks.append(current_chunk)
                    current_chunk = "<code>"
            else:
                chunks.append(current_chunk)
                current_chunk = line
        else:
            if current_chunk:
                current_chunk += "\n" + line
            else:
                current_chunk = line

    # Add the last chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)

    # Send all chunks
    sent_messages = []
    for i, chunk in enumerate(chunks):
        # Only include reply_markup in the last message
        markup = reply_markup if i == len(chunks) - 1 else None

        # Add part indicator for all but the first message
        if i > 0:
            # If we're in a code block, close it before adding the part indicator
            if chunk.startswith("<code>") and "</code>" not in chunk:
                chunk = f"<b>Part {i+1}/{len(chunks)}</b>\n\n{chunk}"
            else:
                chunk = f"<b>Part {i+1}/{len(chunks)}</b>\n\n{chunk}"

        # Ensure we don't exceed the limit with the part indicator
        if len(chunk) > max_length:
            # If still too long, we need to split more aggressively
            # This is a fallback for extremely long lines
            part1 = chunk[: max_length - 100]
            part2 = chunk[max_length - 100 :]

            sent_message = bot.send_message(chat_id, part1, parse_mode=parse_mode)
            sent_messages.append(sent_message)

            # Send the remaining part with part indicator
            part2 = f"<b>Part {i+1}.{2}/{len(chunks)}</b>\n\n{part2}"
            sent_message = bot.send_message(chat_id, part2, parse_mode=parse_mode)
            sent_messages.append(sent_message)
        else:
            sent_message = bot.send_message(
                chat_id, chunk, parse_mode=parse_mode, reply_markup=markup
            )
            sent_messages.append(sent_message)

        # Add a small delay between messages to avoid rate limiting
        if i < len(chunks) - 1:
            time.sleep(0.5)

    return sent_messages[0] if sent_messages else None


# Telegram Bot Handlers
@bot.message_handler(commands=["start", "help"])
def send_welcome(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    first_name = message.from_user.first_name or "N/A"

    # Register user if not exists
    if not UserManager.user_exists(user_id):
        UserManager.save_user(user_id, username, first_name, None)

    welcome_text = (
        f"🤖 <b>PikPak to Google Drive Transfer Bot</b>\n\n"
        f"Welcome, {first_name}!\n\n"
        "Commands:\n"
        "/config - Set your rclone configuration\n\n"
        "/upload - Start transferring video files from PikPak to Google Drive\n\n"
        "/stop - Stop any ongoing transfer\n\n"
        "/status - Resend the status message if deleted\n\n"
        "/drive - Show Google Drive storage statistics\n\n"
        "/drivvy - List all contents of Google Drive\n\n"
        "/pikky - Show PikPak storage statistics and video information\n\n"
        "/history - Show your transfer history\n\n"
        "<b>Important:</b> You must set your rclone configuration using /config before starting a transfer.\n\n"
        "The bot will provide real-time network statistics during the transfer."
    )

    bot.reply_to(message, welcome_text, parse_mode="HTML")


@bot.message_handler(commands=["config"])
def handle_config(message: Message):
    user_id = message.from_user.id

    bot.reply_to(
        message,
        "Please send your rclone configuration as text or upload a configuration file.\n\n"
        "Your configuration should include both PikPak and Google Drive remotes.\n"
        "Make sure your PikPak remote is named 'PIKKY' and Google Drive remote is named 'GDRIVE'.",
        parse_mode="HTML",
    )
    bot.register_next_step_handler(message, process_config)


def process_config(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    first_name = message.from_user.first_name or "N/A"

    try:
        if message.content_type == "text":
            config = message.text
            UserManager.save_user(user_id, username, first_name, config)
            bot.reply_to(
                message,
                "✅ Configuration received and saved. You can now use /upload to start the transfer.",
                parse_mode="HTML",
            )
        elif message.content_type == "document":
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            config = downloaded_file.decode("utf-8")
            UserManager.save_user(user_id, username, first_name, config)
            bot.reply_to(
                message,
                "✅ Configuration file received and saved. You can now use /upload to start the transfer.",
                parse_mode="HTML",
            )
        else:
            bot.reply_to(
                message,
                "❌ Please send the configuration as text or upload a configuration file.",
                parse_mode="HTML",
            )
            bot.register_next_step_handler(message, process_config)
    except Exception as e:
        bot.reply_to(
            message,
            f"❌ Error processing configuration: {str(e)}",
            parse_mode="HTML",
        )


@bot.message_handler(commands=["upload"])
def start_upload(message: Message):
    user_id = message.from_user.id

    # Check if user has config
    if not UserManager.get_user_config(user_id):
        bot.reply_to(
            message,
            "❌ No rclone configuration found. Please set it using /config command first.",
            parse_mode="HTML",
        )
        return

    # Check if transfer is already in progress
    if user_id in transfer_managers and transfer_managers[user_id].transfer_in_progress:
        bot.reply_to(
            message,
            "⚠️ A transfer is already in progress. Please wait for it to complete.",
            parse_mode="HTML",
        )
        return

    # Create transfer manager for user
    transfer_managers[user_id] = TransferManager(user_id)

    # Send initial status message
    status_message = bot.send_message(
        message.chat.id,
        "🔄 <b>Starting transfer from PikPak to Google Drive...</b>\n\n"
        "⏳ Initializing...",
        parse_mode="HTML",
    )

    transfer_managers[user_id].status_message = status_message
    transfer_managers[user_id].status_chat_id = status_message.chat.id
    transfer_managers[user_id].status_message_id = status_message.message_id

    # Start transfer thread
    transfer_managers[user_id].transfer_thread = threading.Thread(
        target=transfer_managers[user_id].run_transfer
    )
    transfer_managers[user_id].transfer_thread.daemon = True
    transfer_managers[user_id].transfer_thread.start()

    # Start status update thread
    transfer_managers[user_id].update_thread = threading.Thread(
        target=update_status_periodically, args=(user_id,)
    )
    transfer_managers[user_id].update_thread.daemon = True
    transfer_managers[user_id].update_thread.start()


def update_status_periodically(user_id):
    manager = transfer_managers.get(user_id)
    if not manager:
        return

    while manager.transfer_in_progress:
        try:
            if manager.network_monitor and manager.network_monitor.monitoring:
                stats_text, keyboard = manager.network_monitor.get_stats_string(user_id)

                with manager.status_lock:
                    if manager.status_chat_id and manager.status_message_id:
                        try:
                            bot.edit_message_text(
                                chat_id=manager.status_chat_id,
                                message_id=manager.status_message_id,
                                text=stats_text,
                                parse_mode="HTML",
                                reply_markup=keyboard,
                            )
                        except Exception as e:
                            print(f"Error updating status message: {e}")

            time.sleep(15)
            
        except Exception as e:
            print(f"Error in status update thread: {e}")
            
            time.sleep(15)

    # Send final status when transfer is complete
    try:
        final_message = format_final_message(manager)
        with manager.status_lock:
            if manager.status_chat_id and manager.status_message_id:
                try:
                    bot.edit_message_text(
                        chat_id=manager.status_chat_id,
                        message_id=manager.status_message_id,
                        text=final_message,
                        parse_mode="HTML",
                    )
                except Exception as e:
                    print(f"Error sending final status: {e}")
    except Exception as e:
        print(f"Error in final status update: {e}")


def format_final_message(manager):
    stats_text = (
        manager.network_monitor.get_stats_string(manager.user_id)[0]
        if manager.network_monitor
        else "Network stats unavailable"
    )

    cleaned_logs = []
    for log in manager.transfer_logs[-15:]:
        clean_log = remove_ansi_codes(log)
        if clean_log and not clean_log.startswith("="):
            cleaned_logs.append(clean_log)

    logs_text = "\n".join(cleaned_logs)
    final_message = (
        "🌌 <b>HEY THERE TRANSFER COMPLETE</b> 🌌\n\n"
        f"{stats_text}\n\n"
        "📝 <b>Transfer Summary:</b>\n"
        f"<code>{html.escape(logs_text)}</code>"
    )
    return final_message


@bot.message_handler(commands=["stop"])
def stop_transfer(message: Message):
    user_id = message.from_user.id

    if (
        user_id not in transfer_managers
        or not transfer_managers[user_id].transfer_in_progress
    ):
        bot.reply_to(
            message, "⚠️ No transfer is currently in progress.", parse_mode="HTML"
        )
        return

    manager = transfer_managers[user_id]
    manager.stop_requested = True
    manager.transfer_in_progress = False

    if manager.network_monitor and manager.network_monitor.monitoring:
        manager.network_monitor.stop_monitoring()

    if manager.transfer_process:
        try:
            if manager.transfer_process.poll() is None:
                manager.transfer_process.terminate()
                time.sleep(2)
                if manager.transfer_process.poll() is None:
                    manager.transfer_process.kill()

            bot.reply_to(
                message, "✅ Transfer process has been stopped.", parse_mode="HTML"
            )
        except Exception as e:
            bot.reply_to(
                message, f"❌ Error stopping transfer: {str(e)}", parse_mode="HTML"
            )
    else:
        bot.reply_to(message, "✅ Transfer has been stopped.", parse_mode="HTML")


@bot.message_handler(commands=["status"])
def show_status(message: Message):
    user_id = message.from_user.id

    if (
        user_id not in transfer_managers
        or not transfer_managers[user_id].transfer_in_progress
    ):
        bot.reply_to(
            message, "⚠️ No transfer is currently in progress.", parse_mode="HTML"
        )
        return

    manager = transfer_managers[user_id]

    # Try to delete the existing status message if it exists
    if manager.status_chat_id and manager.status_message_id:
        try:
            bot.delete_message(manager.status_chat_id, manager.status_message_id)
        except Exception as e:
            print(f"Error deleting status message: {e}")

    # Send a new status message
    try:
        if manager.network_monitor and manager.network_monitor.monitoring:
            stats_text, keyboard = manager.network_monitor.get_stats_string(user_id)
            status_message = bot.send_message(
                message.chat.id, stats_text, parse_mode="HTML", reply_markup=keyboard
            )

            with manager.status_lock:
                manager.status_message = status_message
                manager.status_chat_id = status_message.chat.id
                manager.status_message_id = status_message.message_id
        else:
            status_message = bot.send_message(
                message.chat.id,
                "🔄 <b>Transfer in progress...</b>\n\n"
                "⏳ Network monitoring unavailable.",
                parse_mode="HTML",
            )

            with manager.status_lock:
                manager.status_message = status_message
                manager.status_chat_id = status_message.chat.id
                manager.status_message_id = status_message.message_id
    except Exception as e:
        bot.reply_to(
            message, f"❌ Error retrieving status: {str(e)}", parse_mode="HTML"
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("refresh_status_"))
def refresh_status_callback(call: CallbackQuery):
    user_id = int(call.data.split("_")[-1])

    if (
        user_id not in transfer_managers
        or not transfer_managers[user_id].transfer_in_progress
    ):
        bot.answer_callback_query(call.id, "No active transfer found.", show_alert=True)
        return

    manager = transfer_managers[user_id]

    if manager.network_monitor and manager.network_monitor.monitoring:
        stats_text, keyboard = manager.network_monitor.get_stats_string(user_id)

        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=stats_text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            bot.answer_callback_query(call.id, "Status refreshed!")
        except Exception as e:
            print(f"Error refreshing status: {e}")
            bot.answer_callback_query(
                call.id, "Failed to refresh status.", show_alert=True
            )
    else:
        bot.answer_callback_query(
            call.id, "Network monitoring unavailable.", show_alert=True
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("stop_transfer_"))
def stop_transfer_callback(call: CallbackQuery):
    user_id = int(call.data.split("_")[-1])

    if (
        user_id not in transfer_managers
        or not transfer_managers[user_id].transfer_in_progress
    ):
        bot.answer_callback_query(call.id, "No active transfer found.", show_alert=True)
        return

    manager = transfer_managers[user_id]
    manager.stop_requested = True
    manager.transfer_in_progress = False

    if manager.network_monitor and manager.network_monitor.monitoring:
        manager.network_monitor.stop_monitoring()

    if manager.transfer_process:
        try:
            if manager.transfer_process.poll() is None:
                manager.transfer_process.terminate()
                time.sleep(2)
                if manager.transfer_process.poll() is None:
                    manager.transfer_process.kill()

            bot.answer_callback_query(call.id, "Transfer stopped successfully!")

            # Update the message to show transfer stopped
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="⏹️ <b>TRANSFER STOPPED</b>\n\nThe transfer has been stopped by user request.",
                    parse_mode="HTML",
                )
            except Exception as e:
                print(f"Error updating message after stop: {e}")
        except Exception as e:
            bot.answer_callback_query(
                call.id, f"Error stopping transfer: {str(e)}", show_alert=True
            )
    else:
        bot.answer_callback_query(call.id, "Transfer stopped!")

        # Update the message to show transfer stopped
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="⏹️ <b>OKAY TRANSFER STOPPED</b>\n\nThe transfer has been stopped by user request.",
                parse_mode="HTML",
            )
        except Exception as e:
            print(f"Error updating message after stop: {e}")


@bot.message_handler(commands=["drive"])
def drive_command(message: Message):
    show_drive_stats(message)


def show_drive_stats(message: Message):
    user_id = message.from_user.id
    config = UserManager.get_user_config(user_id)

    if not config:
        bot.reply_to(
            message,
            "❌ No rclone configuration found. Please set it using /config command first.",
            parse_mode="HTML",
        )
        return

    try:
        # Create temporary config file
        config_file = os.path.expanduser(f"~/.config/rclone/drive_stats_{user_id}.conf")
        config_dir = Path(config_file).parent
        config_dir.mkdir(parents=True, exist_ok=True)

        with open(config_file, "w") as f:
            f.write(config)

        # Get rclone path
        rclone_path = os.path.expanduser(f"~/.local/bin/rclone_{user_id}")
        if not os.path.exists(rclone_path):
            # Install rclone if not exists
            manager = TransferManager(user_id)
            success, rclone_path = manager.install_rclone()
            if not success:
                bot.reply_to(
                    message,
                    "❌ Failed to install rclone. Please try starting a transfer first.",
                    parse_mode="HTML",
                )
                return

        # Get drive stats
        result = subprocess.run(
            f"{rclone_path} --config {config_file} about GDRIVE:",
            shell=True,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            lines = result.stdout.split("\n")
            total = used = free = "Unknown"

            for line in lines:
                if line.startswith("Total:"):
                    total = line.split(":")[1].strip()
                elif line.startswith("Used:"):
                    used = line.split(":")[1].strip()
                elif line.startswith("Free:"):
                    free = line.split(":")[1].strip()

            response = (
                "📊 <b>Google Drive Storage</b>\n\n"
                f"🔸 Total: {total}\n"
                f"🔹 Used: {used}\n"
                f"◽️ Free: {free}"
            )
            bot.reply_to(message, response, parse_mode="HTML")
        else:
            bot.reply_to(
                message,
                f"❌ Failed to get Google Drive storage: {result.stderr.strip()}",
                parse_mode="HTML",
            )
    except Exception as e:
        bot.reply_to(
            message,
            f"❌ Error getting drive stats: {str(e)}",
            parse_mode="HTML",
        )


@bot.message_handler(commands=["drivvy"])
def list_drive_contents(message: Message):
    user_id = message.from_user.id
    config = UserManager.get_user_config(user_id)

    if not config:
        bot.reply_to(
            message,
            "❌ No rclone configuration found. Please set it using /config command first.",
            parse_mode="HTML",
        )
        return

    try:
        # Create temporary config file
        config_file = os.path.expanduser(f"~/.config/rclone/drive_list_{user_id}.conf")
        config_dir = Path(config_file).parent
        config_dir.mkdir(parents=True, exist_ok=True)

        with open(config_file, "w") as f:
            f.write(config)

        # Get rclone path
        rclone_path = os.path.expanduser(f"~/.local/bin/rclone_{user_id}")
        if not os.path.exists(rclone_path):
            # Install rclone if not exists
            manager = TransferManager(user_id)
            success, rclone_path = manager.install_rclone()
            if not success:
                bot.reply_to(
                    message,
                    "❌ Failed to install rclone. Please try starting a transfer first.",
                    parse_mode="HTML",
                )
                return

        # Get drive contents
        result = subprocess.run(
            f"{rclone_path} --config {config_file} lsf GDRIVE: --recursive",
            shell=True,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            contents = result.stdout.split("\n") if result.stdout else []

            if contents:
                # Send initial message
                initial_message = bot.reply_to(
                    message,
                    f"📁 <b>Google Drive Contents</b>\n\nFound {len(contents)} files. Sending in chunks...",
                    parse_mode="HTML",
                )

                # Process files in smaller chunks
                chunk_size = 30  # Reduced chunk size
                for i in range(0, len(contents), chunk_size):
                    chunk = contents[i : i + chunk_size]

                    # Format without code blocks to avoid parsing issues
                    formatted_output = "\n".join(
                        f"📄 {html.escape(file)}" for file in chunk if file.strip()
                    )

                    # Create message with part indicator
                    part_num = i // chunk_size + 1
                    total_parts = (len(contents) + chunk_size - 1) // chunk_size

                    message_text = (
                        f"📁 <b>Google Drive Contents</b> (Part {part_num}/{total_parts})\n\n"
                        f"{formatted_output}"
                    )

                    # Send message with a small delay to avoid rate limiting
                    bot.send_message(message.chat.id, message_text, parse_mode="HTML")
                    time.sleep(1)
            else:
                bot.reply_to(message, "📁 Google Drive is empty.", parse_mode="HTML")
        else:
            bot.reply_to(
                message,
                f"❌ Failed to list Google Drive contents: {html.escape(result.stderr.strip())}",
                parse_mode="HTML",
            )
    except Exception as e:
        bot.reply_to(
            message,
            f"❌ Error listing drive contents: {html.escape(str(e))}",
            parse_mode="HTML",
        )

def set_bot_commands():
    """Set up the bot's command menu in Telegram"""
    commands = [
        telebot.types.BotCommand("start", "🤖 Show welcome message and help"),
        telebot.types.BotCommand("help", "❓ Show help information"),
        telebot.types.BotCommand("config", "⚙️ Set rclone configuration"),
        telebot.types.BotCommand("upload", "📤 Start transferring videos from PikPak to Google Drive"),
        telebot.types.BotCommand("stop", "⏹️ Stop any ongoing transfer"),
        telebot.types.BotCommand("status", "📊 Show current transfer status"),
        telebot.types.BotCommand("drive", "💾 Show Google Drive storage statistics"),
        telebot.types.BotCommand("drivvy", "📁 List all contents of Google Drive"),
        telebot.types.BotCommand("pikky", "🎬 Show PikPak storage and video information"),
        telebot.types.BotCommand("history", "📜 Show your transfer history")
    ]
    
    try:
        bot.set_my_commands(commands)
        print("Bot commands menu set successfully!")
    except Exception as e:
        print(f"Failed to set bot commands: {e}")
        
        
@bot.message_handler(commands=["pikky"])
def pikky_stats(message: Message):
    user_id = message.from_user.id
    config = UserManager.get_user_config(user_id)

    if not config:
        bot.reply_to(
            message,
            "❌ No rclone configuration found. Please set it using /config command first.",
            parse_mode="HTML",
        )
        return

    try:
        # Create temporary config file
        config_file = os.path.expanduser(f"~/.config/rclone/pikky_stats_{user_id}.conf")
        config_dir = Path(config_file).parent
        config_dir.mkdir(parents=True, exist_ok=True)

        with open(config_file, "w") as f:
            f.write(config)

        # Get rclone path
        rclone_path = os.path.expanduser(f"~/.local/bin/rclone_{user_id}")
        if not os.path.exists(rclone_path):
            # Install rclone if not exists
            manager = TransferManager(user_id)
            success, rclone_path = manager.install_rclone()
            if not success:
                bot.reply_to(
                    message,
                    "❌ Failed to install rclone. Please try starting a transfer first.",
                    parse_mode="HTML",
                )
                return

        # Get PikPak stats
        result = subprocess.run(
            f"{rclone_path} --config {config_file} about PIKKY:",
            shell=True,
            capture_output=True,
            text=True,
        )

        storage_response = ""
        if result.returncode == 0:
            lines = result.stdout.split("\n")
            total = used = free = "Unknown"

            for line in lines:
                if line.startswith("Total:"):
                    total = line.split(":")[1].strip()
                elif line.startswith("Used:"):
                    used = line.split(":")[1].strip()
                elif line.startswith("Free:"):
                    free = line.split(":")[1].strip()

            storage_response = (
                "📊 <b>PikPak Storage</b>\n\n"
                f"🔸 Total: {total}\n"
                f"🔹 Used: {used}\n"
                f"◽️ Free: {free}"
            )
        else:
            storage_response = (
                f"❌ Failed to get PikPak storage: {html.escape(result.stderr.strip())}"
            )

        # Get PikPak videos
        video_extensions = [
            "mp4",
            "mkv",
            "avi",
            "mov",
            "wmv",
            "flv",
            "webm",
            "mpg",
            "mpeg",
            "m4v",
            "3gp",
        ]

        # Get all files first
        result = subprocess.run(
            f"{rclone_path} --config {config_file} lsf PIKKY: --recursive",
            shell=True,
            capture_output=True,
            text=True,
        )

        video_response = ""
        if result.returncode == 0:
            all_files = result.stdout.split("\n") if result.stdout else []
            video_files = [
                f for f in all_files if f.split(".")[-1].lower() in video_extensions
            ]

            if video_files:
                # Format the first 8 video files with double line breaks
                video_list = "\n\n".join(
                    f"🎬 {html.escape(file)}" for file in video_files[:8]
                )

                if len(video_files) > 8:
                    video_list += f"\n\n... and {len(video_files)-8} more videos."

                # Get total size
                filter_rules = (
                    ["+ */"]
                    + [f"+ *.{ext}" for ext in video_extensions]
                    + ["- .*", "- *"]
                )
                filter_args = " ".join([f'--filter "{rule}"' for rule in filter_rules])

                size_result = subprocess.run(
                    f"{rclone_path} --config {config_file} size PIKKY: {filter_args}",
                    shell=True,
                    capture_output=True,
                    text=True,
                )

                total_size = "Unknown"
                if size_result.returncode == 0:
                    for line in size_result.stdout.split("\n"):
                        if line.startswith("Total size:"):
                            total_size = line.split(":")[1].strip()

                video_response = (
                    f"🎬 <b>PikPak Videos</b>\n\n"
                    f"🔸 Total Videos: {len(video_files)}\n"
                    f"🔹 Total Size: {total_size}\n\n"
                    f"<b>Sample Videos:</b>\n{video_list}"
                )
            else:
                video_response = "🎬 No video files found in PikPak."
        else:
            video_response = (
                f"❌ Failed to get PikPak videos: {html.escape(result.stderr.strip())}"
            )

        full_response = f"{storage_response}\n\n{video_response}"

        # Use send_long_message to handle potentially long messages
        send_long_message(message.chat.id, full_response, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(
            message,
            f"❌ Error getting PikPak stats: {html.escape(str(e))}",
            parse_mode="HTML",
        )


@bot.message_handler(commands=["history"])
def show_history(message: Message):
    user_id = message.from_user.id
    transfers = UserManager.get_user_transfers(user_id)

    if not transfers:
        bot.reply_to(
            message,
            "📜 <b>Transfer History</b>\n\nNo transfer history found.",
            parse_mode="HTML",
        )
        return

    history_text = "📜 <b>Transfer History</b>\n\n"

    for transfer in transfers:
        status_emoji = {"completed": "✅", "failed": "❌", "cancelled": "⚠️"}.get(
            transfer["status"], "❓"
        )

        start_time = datetime.fromisoformat(transfer["start_time"])
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")

        if transfer["end_time"]:
            end_time = datetime.fromisoformat(transfer["end_time"])
            end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            end_str = "N/A"

        history_text += (
            f"{status_emoji} <b>Transfer #{transfer['id']}</b>\n"
            f"Status: {transfer['status'].title()}\n"
            f"Started: {start_str}\n"
            f"Ended: {end_str}\n"
            f"Destination: {transfer['destination_folder'] or 'N/A'}\n"
            f"Files: {transfer['files_count'] or 0}\n"
            f"Size: {transfer['total_size'] or 'Unknown'}\n\n"
        )

    # Use send_long_message to handle potentially long history
    send_long_message(message.chat.id, history_text, parse_mode="HTML")


def main():
    print("Starting PikPak to Google Drive Transfer Bot...")
    # Set up bot commands menu
    set_bot_commands()
    bot.infinity_polling()


if __name__ == "__main__":
    main()
