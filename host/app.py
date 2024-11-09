import argparse
import ctypes
import json
import os
import psutil
import requests
import subprocess
import sys
import threading
import time
import tkinter as tk
import win32con
import win32gui
import win32process

from common import HarmonyHostCommon
from logger import Logger

parser = argparse.ArgumentParser()
parser.add_argument('-app', type=str, required=True)
parser.add_argument('-mainexe', type=str, required=True)
parser.add_argument('-alwaysontop', type=str, default='False')
parser.add_argument('-exes', type=str, nargs='+', required=True)
parser.add_argument('-killexes', type=str, nargs='+', required=True)
parser.add_argument('-waitforeac', type=str, default='True')
parser.add_argument('-createblackwindow', type=str, default='True')
parser.add_argument('-monitorprocess', type=str, default='True')
parser.add_argument('-delay', type=str, required=False)
args = parser.parse_args()

current_path = os.path.dirname(os.path.realpath(__file__))

logger = Logger(os.path.join(current_path, 'app.log'))

# Harmony configuration file
harmony_config_path = os.path.join(os.path.dirname(__file__), 'harmony.json')
if not os.path.exists(harmony_config_path):
    logger.log_to_file("Harmony configuration file not found.")
    sys.exit(1)
with open(harmony_config_path, 'r') as f:
    harmony_config = json.load(f)

class TkWindow:
    def __init__(self):
        self.root = None
        self._running = False

    def create_window(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True) # Remove window decorations (borderless)
        self.root.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")  # Full screen
        self.root.configure(bg='black') # Set the background to black
        self._running = True

        self.root.after(0, self.after_create)

        self.root.mainloop()

    def after_create(self):
        hwnd = win32gui.FindWindow(None, self.root.winfo_name())  # Find the hwnd using the window name
        if hwnd:
            logger.log_to_file(f'[TkWindow] [Info] Window hwnd: {hwnd}')
        else:
            logger.log_to_file('[TkWindow] [Warning] hwnd not found.')

    def get_hwnd(self):
        return win32gui.FindWindow(None, self.root.winfo_name())  # Return the hwnd of the Tk window

    def run(self):
        self.create_window()

    def stop(self):
        if self.root is not None:
            self._running = False
            self.root.quit()

class HarmonyHost():
    def __init__(self):
        self.common = HarmonyHostCommon()
    
    def find_hwnd_from_process(self, process):
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] == process:
                hwnds = []
                def callback(hwnd, pid):
                    if win32process.GetWindowThreadProcessId(hwnd)[1] == pid:
                        hwnds.append(hwnd)
                    return True
                win32gui.EnumWindows(callback, proc.info['pid'])
                if hwnds:
                    return hwnds[0]
        return None

    def is_valid_window(self, hwnd):
        # Check if the window is visible and has the desired style
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        return win32gui.IsWindowVisible(hwnd) and (style & win32con.WS_DISABLED) == 0

    def find_hwnds_from_process(self, process):
        hwnds = []
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] == process:
                def callback(hwnd, pid):
                    if win32process.GetWindowThreadProcessId(hwnd)[1] == pid:
                        hwnd_title = win32gui.GetWindowText(hwnd) 
                        bad_titles = [ #TODO: Consider alternative way of rejecting invalid hwnd instances rather than manually blacklisting them
                            "MSCTFIME UI",
                            "Default IME",
                            "Battery Watcher",
                            "WinEventHub"
                        ]
                        # Check if the window handle is valid and does not match any bad titles
                        try:
                            if (self.is_valid_window(hwnd) and 
                                not any(bad_title in hwnd_title for bad_title in bad_titles) and 
                                "$AS" not in hwnd_title and 
                                "$Hour" not in hwnd_title):
                                hwnds.append(hwnd)  # Append if all conditions are met
                        except Exception as e:
                            logger.log_to_file(f'[HarmonyHost] [Error] Error checking for valid window: {e}')
                    return True
                win32gui.EnumWindows(callback, proc.info['pid'])
        return hwnds

    def bring_hwnd_to_foreground(self, hwnd):
        # Check if the window is minimized; restore it if it is
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    
        # Attempt to bring the window to the foreground
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception as e:
            logger.log_to_file(f'[HarmonyHost] [Error] Failed to bring window to foreground: {e}')
        
        try:
            # Optionally, ensure the window is topmost for visibility
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST, # Bring to the top of the Z-order
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
            )

            if args.alwaysontop.lower() != 'true':
                # Set the window to be topmost, so it remains above other windows
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_NOTOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
        except Exception as e:
            logger.log_to_file(f'[HarmonyHost] [Error] Failed to bring window to foreground: {e}')

    def wait_host_ready(self):
        # Create a black window to cover up the desktop
        if str(args.createblackwindow).lower() == 'true':
            logger.log_to_file(f"[HarmonyHost] [Info] Creating the black window.")
            tk_window = TkWindow()
            tk_thread = threading.Thread(target=tk_window.run)
            tk_thread.start() 

        # Wait for the main application to start
        timeout = 100
        elapsed = 0
        interval = 1
        while not self.common.are_processes_running([args.mainexe]):
            time.sleep(interval)
            elapsed += interval
            if elapsed >= timeout:
                logger.log_to_file(f"[HarmonyHost] [Error] The main application is not running after {timeout} seconds.")
                sys.exit(1)
        logger.log_to_file(f"[HarmonyHost] [Info] The main application is running.")
        
        # Wait for the main application window to appear
        hwnd_timeout = 100
        hwnd_elapsed = 0
        hwnd_interval = 1
        while not self.find_hwnd_from_process(args.mainexe):
            time.sleep(hwnd_interval)
            hwnd_elapsed += hwnd_interval
            if hwnd_elapsed >= hwnd_timeout:
                logger.log_to_file(f"[HarmonyHost] [Error] The main application window is not running after {hwnd_timeout} seconds.")
                sys.exit(1)
        logger.log_to_file(f"[HarmonyHost] [Info] The main application window is found.")

        # Optional, wait for the easy anti cheat launcher
        if str(args.waitforeac).lower() == 'true':
            eac_timeout = 100
            eac_elapsed = 0
            eac_interval = 1
            eac_launcher = False
            # If the size is 320x240, it must be easy the anti cheat launcher and therefore we need to wait more
            hwnd = self.find_hwnd_from_process(args.mainexe)
            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            if width == 320 and height == 240:
                logger.log_to_file(f"[HarmonyHost] [Info] The Easy Anti Cheat window is found, waiting for main application to start.")
                eac_launcher = True
            while eac_launcher:
                hwnd = self.find_hwnd_from_process(args.mainexe)
                rect = win32gui.GetWindowRect(hwnd)
                width = rect[2] - rect[0]
                height = rect[3] - rect[1]
                if width > 321 and height > 241:
                    break
                time.sleep(eac_interval)
                if hwnd is None:
                    break

        # Wait a little for the window to appear
        time.sleep(0.1)

        if not args.delay:
            args.delay = 0
        delay = float(args.delay)
        logger.log_to_file(f"[HarmonyHost] [Info] Sending the ready signal after {delay} seconds...")
        time.sleep(delay)

        try:
            logger.log_to_file(f"[HarmonyHost] [Info] Bringing the main window to the foreground...")
            if self.common.are_processes_running([args.mainexe]):
                hwnds = self.find_hwnds_from_process(args.mainexe)
                if hwnds:
                    for hwnd in hwnds: # Loop through each window handle
                        if hwnd:
                            hwnd_title = win32gui.GetWindowText(hwnd) 
                            if hwnd_title:
                                logger.log_to_file(f"[HarmonyHost] [Info] Bringing window to foreground: {args.mainexe} with the title: {hwnd_title}")
                                self.bring_hwnd_to_foreground(hwnd)
        except Exception as e:
            logger.log_to_file(f"[HarmonyHost] [Error] Error bringing the main window to the foreground: {e}")

        host_ip = harmony_config.get('host-ip')
        host_port = harmony_config.get('host-port')
        request_address = 'http://' + host_ip + ':' + str(host_port) + '/ready'
        try:
            logger.log_to_file(f"[HarmonyHost] [Info] Sending the ready signal...")
            response = requests.get(request_address)
        except Exception as e:
            logger.log_to_file(f"[HarmonyHost] [Error] Failed sending the ready signal: {e}")
            time.sleep(1)
            if tk_window:
                tk_window.stop()
            if tk_thread:
                tk_thread.join()
            sys.exit(1)

        monitor_interval = 0.2
        keepalive_interval = 5
        last_keepalive_time = time.time()
        harmony_port = int(harmony_config.get('port', 5000))
        while self.common.are_processes_running([args.mainexe]):
            time.sleep(monitor_interval)
            if time.time() - last_keepalive_time >= keepalive_interval:
                keepalive_address = f'http://127.0.0.1:{harmony_port}/keepalive'
                try:
                    keepalive_response = requests.get(keepalive_address)
                    logger.log_to_file(f"[HarmonyHost] [Info] Keepalive signal sent successfully: {keepalive_response.status_code}")
                except Exception as e:
                    logger.log_to_file(f"[HarmonyHost] [Error] Error sending the keepalive signal: {e}")
        
                last_keepalive_time = time.time()  # Reset the keepalive timer

        # Monitor the process 
        time.sleep(5)
        if str(args.monitorprocess).lower() == 'true':
            logger.log_to_file(f"[HarmonyHost] [Info] Sending the termination signal, mainexe running: {str(self.common.are_processes_running([args.mainexe]))}")
            request_address = 'http://' + host_ip + ':' + str(host_port) + '/terminate'
            try:
                response = requests.get(request_address)
                logger.log_to_file(f"[HarmonyHost] [Info] The termination signal sent successfully.")
                time.sleep(1)
                if tk_window:
                    tk_window.stop()
                if tk_thread:
                    tk_thread.join()
                sys.exit(1)
                return
            except Exception as e:
                logger.log_to_file(f"[HarmonyHost] [Error] Error sending the termination signal: {e}")
                time.sleep(1)
                if tk_window:
                    tk_window.stop()
                if tk_thread:
                    tk_thread.join()
                sys.exit(1)
                return
        sys.exit(1)

    def run(self):
        # Kill looking-glass-host.exe
        if self.common.are_processes_running(['looking-glass-host.exe']):
            self.common.kill_process('looking-glass-host.exe')

        if not self.common.are_processes_running(args.exes):
            if args.app.startswith('steam://') or args.app.startswith('com.epicgames.launcher://'):
                command = f'start {args.app}'
            else:
                command = args.app
            logger.log_to_file(f"[HarmonyHost] [Info] Executing command: {command}")
            # Do it twice in case as a workaround for it not launching for some reason with Steam
            for i in range(2):
                subprocess.Popen(command, shell=True, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)

        # Kill the processes specified
        if self.common.are_processes_running(args.killexes):
            for process in args.killexes:
                self.common.kill_process(process)

        minimise_processes = harmony_config.get('minimise-processes', [])
        for process in minimise_processes:
            if self.common.are_processes_running([process]):
                logger.log_to_file(f"[HarmonyHost] [Info] Found running process to minimise: {process}")
                hwnds = self.find_hwnds_from_process(process) # Get all window handles for the process
                if hwnds:
                    for hwnd in hwnds: # Loop through each window handle
                        if hwnd:
                            hwnd_title = win32gui.GetWindowText(hwnd) 
                            if hwnd_title:
                                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE) # Send close message to each window
                                logger.log_to_file(f"[HarmonyHost] [Info] Minimized window: {process} with the title: {hwnd_title}")
                else:
                    logger.log_to_file(f"[HarmonyHost] [Info] No windows found for process: {process}")

        if not self.common.are_processes_running(['looking-glass-host.exe']):
            lg_path = harmony_config.get('looking-glass-path')
            if not lg_path:
                logger.log_to_file(f"[HarmonyHost] [Error] Looking Glass path not found.")
                sys.exit(1)
            lg_path = os.path.expanduser(lg_path)
            
            cmd = f'start /realTime "" "{lg_path}"'
            subprocess.Popen(
                cmd,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
                shell=True
            )

        time.sleep(0.1)

        logger.log_to_file(f"[HarmonyHost] [Info] Waiting to be ready.")
        self.wait_host_ready()

if __name__ == '__main__':
    if not HarmonyHostCommon.is_admin():
        # Re-run the script with admin privileges
        logger.log_to_file(f"Requesting administrative privileges...")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

    # Kill all other instances of this app.py AND restart LG
    try:
        # Get the list of running processes using 'tasklist'
        processes = subprocess.check_output(['tasklist'], text=True).splitlines()
        for process in processes:
            if 'pythonw.exe' in process:
                logger.log_to_file(f"Found process: {process}")
                # Extract the PID from the process line (2nd item in space-separated line)
                pid = int(process.split()[1])
                current_pid = os.getpid()
                # Kill the process if it is not the current process
                if pid != current_pid:
                    logger.log_to_file(f"Killing process with PID {pid}...")
                    subprocess.run(['taskkill', '/PID', str(pid), '/F'])  # '/F' forces termination     
    except subprocess.CalledProcessError as e:
        logger.log_to_file(f"Error checking running processes: {e}")

    time.sleep(0.1)

    harmony_host = HarmonyHost()
    harmony_host.run()