import ctypes
import json
import os
import shlex
import subprocess
import threading
import time

from common import HarmonyHostCommon
from flask import Flask, request
from logger import Logger

current_path = os.path.dirname(os.path.realpath(__file__))

logger = Logger(os.path.join(current_path, 'listener.log'))

# Harmony configuration file
harmony_config_path = os.path.join(os.path.dirname(__file__), 'harmony.json')
if not os.path.exists(harmony_config_path):
    logger.log_to_file("Harmony configuration file not found.")
    sys.exit(1)
with open(harmony_config_path, 'r') as f:
    harmony_config = json.load(f)

last_keepalive_time = time.time()
watcher_thread = None
thread_lock = threading.Lock()
disconnect_watcher_thread = None
disconnect_thread_lock = threading.Lock()

def run_command_after_delay(command, delay=0.1):
    time.sleep(delay)
    try:
        subprocess.run(command, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")

common = HarmonyHostCommon()

def lg_watcher():
    global last_keepalive_time
    while True:
        if not common.are_processes_running(['looking-glass-host.exe']):
            # Check if no keep alive within last 10 seconds
            if time.time() - last_keepalive_time > 10:
                lg_path = harmony_config.get('looking-glass-path')
                if not lg_path:
                    logger.log_to_file(f"[HarmonyHostListener] [Error] Looking Glass path not found.")
                    sys.exit(1)
                lg_path = os.path.expanduser(lg_path)

                cmd = f'start /realTime "" "{lg_path}"'
                subprocess.Popen(
                    cmd,
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                    close_fds=True,
                    shell=True
                )
        time.sleep(1)

def keepalive_watcher():
    keepalive_timeout = harmony_config.get('keepalive_timeout', 60)
    global last_keepalive_time
    while True:
        time_since_last_keepalive = time.time() - last_keepalive_time
        if time_since_last_keepalive >= keepalive_timeout:
            print("Timeout received, hibernating PC.")
            subprocess.run(["shutdown", "/h"])  # Hibernate the PC
            break  # Exit the loop after hibernation
        print("Keepalive watcher alive.")
        time.sleep(1)  # Check every second

def disconnect_watcher(exes, timeout):
    print(f"Disconnecting in {timeout} seconds.")
    time.sleep(timeout)
    print("Timeout received, disconnecting.")
    common.kill_process('pythonw.exe')
    exe_list = shlex.split(exes)
    for exe in exe_list:
        print(f"Killing process: {exe}")
        common.kill_process(exe)

# Check if watcher thread is alive
def is_thread_alive(thread):
    return thread is not None and thread.is_alive()

# Harmony listener
class HarmonyHostListener(Flask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        @self.route('/execute', methods=['POST'])
        def execute_command():
            command = request.form.get('command')
            print(f"Received command: {command}")
            if command:
                # Inform the client that the command is about to run
                response = f"Command '{command}' will be executed."

                # Run the command in a separate thread, after a short delay
                threading.Thread(target=run_command_after_delay, args=(command,)).start()

                return response
            return 'No command provided.'

        @self.route('/cancel', methods=['POST'])
        def cancel_command():
            exes = request.form.get('exes')
            print("Cancelling the command with exes: ", exes)
            # Cancel the command by killing the process
            common.kill_process('pythonw.exe')
            exe_list = shlex.split(exes)
            for exe in exe_list:
                print(f"Killing process: {exe}")
                common.kill_process(exe)
            return 'Cancelled'

        @self.route('/disconnected', methods=['POST'])
        def disconnected():
            global disconnect_watcher_thread
            timeout = request.form.get('timeout')
            exes = request.form.get('exes')
            print(f"Disconnecting with timeout: {timeout}, exes: {exes}")
            with disconnect_thread_lock:
                if not (disconnect_watcher_thread and disconnect_watcher_thread.is_alive()):
                    disconnect_watcher_thread = threading.Thread(target=disconnect_watcher, args=(exes, int(timeout)), daemon=True)
                    disconnect_watcher_thread.start()
                else:
                    print("Disconnect watcher thread is already running.")
                    # Wait for the existing thread to finish and then start a new one
                    disconnect_watcher_thread.join()
                    disconnect_watcher_thread = threading.Thread(target=disconnect_watcher, args=(exes, int(timeout)), daemon=True)
                    disconnect_watcher_thread.start()
            return f"Disconnected. Timeout: {timeout}"

        @self.route('/stop', methods=['POST'])
        def stop_command():
            exes = request.form.get('exes')
            print("Stopping the command with exes: ", exes)
            # Stop the command by killing the process
            common.kill_process('pythonw.exe')
            exe_list = shlex.split(exes)
            for exe in exe_list:
                print(f"Killing process: {exe}")
                common.kill_process(exe)
            return 'Stopped'

        @self.route('/keepalive', methods=['GET'])
        def keep_alive():
            global last_keepalive_time, watcher_thread
            last_keepalive_time = time.time()  # Reset keepalive time
            
            # Lock the thread to avoid race conditions
            with thread_lock:
                # Check if the watcher thread is alive
                if not is_thread_alive(watcher_thread):
                    print("Starting a new watcher thread.")
                    # Create a new watcher thread if it doesn't exist or has stopped
                    watcher_thread = threading.Thread(target=keepalive_watcher, daemon=True)
                    watcher_thread.start()
                else:
                    print("Watcher thread is already running.")
            
            return 'Acknowledged'

def set_console_non_topmost():
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002)  # SWP_NOMOVE | SWP_NOSIZE

if __name__ == '__main__':
    set_console_non_topmost() # Set console window as non-topmost
    lg_watcher_thread = threading.Thread(target=lg_watcher, daemon=True)
    lg_watcher_thread.start()
    listener = HarmonyHostListener(__name__)
    harmony_port = int(harmony_config.get('port', 5000))
    listener.run(host='0.0.0.0', port=harmony_port)