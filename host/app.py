import argparse
import ctypes
import json
import os
import psutil
import requests
import subprocess
import sys
import time
import win32con
import win32gui
import win32process

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

from logger import Logger

parser = argparse.ArgumentParser()
parser.add_argument('-app', type=str, required=True)
parser.add_argument('-mainexe', type=str, required=True)
parser.add_argument('-alwaysontop', type=str, default='False')
parser.add_argument('-exes', type=str, nargs='+', required=True)
parser.add_argument('-killexes', type=str, nargs='+', required=True)
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

class HarmonyHost():
    def __init__(self):
        pass
    
    def are_processes_running(self, processes):
        for process in processes:
            logger.log_to_file(f'[HarmonyHost] [Info] Checking if {process} is running...')
            command = f'tasklist /FI "IMAGENAME eq {process}"'

            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            # Check if the process name is in the output
            if process in result.stdout:
                logger.log_to_file(f'[HarmonyHost] [Info] The {process} is running...')
                return True
            if result.returncode != 0:
                logger.log_to_file(f'[HarmonyHost] [Error] Error checking {process}: {result.stderr.strip()}')
        return False

    def kill_process(self, process):
        try:
            subprocess.run(f'taskkill /F /IM {process}', shell=True)
            logger.log_to_file(f'[HarmonyHost] [Info] Killed process {process}')
        except Exception as e:
            logger.log_to_file(f'[HarmonyHost] [Error] Failed to kill process {process}: {e}')

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
    
    def find_hwnds_from_process(self, process):
        hwnds = []
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] == process:
                def callback(hwnd, pid):
                    if win32process.GetWindowThreadProcessId(hwnd)[1] == pid:
                        hwnds.append(hwnd)
                    return True
                win32gui.EnumWindows(callback, proc.info['pid'])
        return hwnds  # Return all window handles associated with the process

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
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            )

            if args.alwaysontop.lower() != 'true':
                # Set the window to be topmost, so it remains above other windows
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_NOTOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
                )
        except Exception as e:
            logger.log_to_file(f'[HarmonyHost] [Error] Failed to bring window to foreground: {e}')

    def wait_host_ready(self):
        # Wait for the main application to start
        timeout = 100
        elapsed = 0
        interval = 1
        while not self.are_processes_running([args.mainexe]):
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
        wait_for_eac = harmony_config.get('wait-for-easy-anti-cheat')
        if str(wait_for_eac).lower() == 'true':
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

        # Wait a little for the window to appear
        time.sleep(1)

        delay = float(args.delay)
        logger.log_to_file(f"[HarmonyHost] [Info] Sending the ready signal after {delay} seconds...")
        time.sleep(delay)

        if self.are_processes_running(args.exes):
            hwnd = self.find_hwnd_from_process(args.mainexe)
            if hwnd:
                logger.log_to_file(f"[HarmonyHost] [Info] Bringing window to foreground: {args.mainexe}")
                self.bring_hwnd_to_foreground(hwnd)

        host_ip = harmony_config.get('host-ip')
        host_port = harmony_config.get('host-port')
        request_address = 'http://' + host_ip + ':' + str(host_port) + '/ready'
        try:
            response = requests.get(request_address)
        except Exception as e:
            logger.log_to_file(f"[HarmonyHost] [Error] Failed sending the ready signal: {e}")
            sys.exit(1)

        # Monitor the process 
        time.sleep(5)
        wait_for_eac = harmony_config.get('monitor-process')
        if str(wait_for_eac).lower() == 'true':
            monitor_interval = 0.5
            while self.are_processes_running([args.mainexe]):
                time.sleep(monitor_interval)
            logger.log_to_file(f"[HarmonyHost] [Info] Sending the termination signal.")
            request_address = 'http://' + host_ip + ':' + str(host_port) + '/terminate'
            try:
                response = requests.get(request_address)
                sys.exit(1)
                return
            except Exception as e:
                sys.exit(1)
                return
        sys.exit(1)

    def run(self):
        if not self.are_processes_running(args.exes):
            #if args.app.startswith('steam://'):
            #    command = f'start {args.app}'
            #else:
            #    command = args.app
            command = f'start {args.app}'
            logger.log_to_file(f"[HarmonyHost] [Info] Executing command: {args.mainexe}")
            subprocess.Popen(command, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)

        # Kill the processes specified
        if self.are_processes_running(args.killexes):
            for process in args.killexes:
                self.kill_process(process)
        
        minimise_processes = harmony_config.get('minimise-processes', [])
        for process in minimise_processes:
            if self.are_processes_running([process]):
                hwnds = self.find_hwnds_from_process(process)  # Get all window handles for the process
                if hwnds:
                    for hwnd in hwnds: # Loop through each window handle
                        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)  # Send close message to each window
                        logger.log_to_file(f"[HarmonyHost] [Info] Minimized window: {process}")
                else:
                    logger.log_to_file(f"[HarmonyHost] [Info] No windows found for process: {process}")

        close_processes = harmony_config.get('close-processes', [])
        for process in close_processes:
            if self.are_processes_running([process]):
                hwnds = self.find_hwnds_from_process(process)  # Get all window handles for the process
                if hwnds:
                    for hwnd in hwnds:  # Loop through each window handle
                        try:
                            # Check if the window is still valid before sending the close message
                            if win32gui.IsWindow(hwnd):  # Check if the window handle is valid
                                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)  # Send close message to each window
                                logger.log_to_file(f"[HarmonyHost] [Info] Sent close signal to window: {process}")
                            else:
                                logger.log_to_file(f"[HarmonyHost] [Info] Invalid window handle: {hwnd}")
                        except Exception as e:
                            logger.log_to_file(f"[HarmonyHost] [Error] Failed to close window {hwnd}: {str(e)}")
                else:
                    logger.log_to_file(f"[HarmonyHost] [Info] No windows found for process: {process}")
                    
        # Kill the looking glass host
        if self.are_processes_running(['looking-glass-host.exe']):
            self.kill_process('looking-glass-host.exe')
        
        lg_path = harmony_config.get('looking-glass-path')
        if not lg_path:
            logger.log_to_file(f"[HarmonyHost] [Error] Looking Glass path not found.")
            sys.exit(1)
        lg_path = os.path.expanduser(lg_path)
        logger.log_to_file("lg path")
        logger.log_to_file(lg_path)

        # Restart the looking glass host
        subprocess.Popen(
            lg_path,
            #'"C:\\Program Files\\Looking Glass (host)\\looking-glass-host.exe"',
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
            shell=True
        )

        if self.are_processes_running(args.exes):
            logger.log_to_file(f"[HarmonyHost] [Info] One or more required processes are already running.")
            hwnd = self.find_hwnd_from_process(args.mainexe)
            if hwnd:
                logger.log_to_file(f"[HarmonyHost] [Info] Bringing window to foreground: {args.mainexe}")
                self.bring_hwnd_to_foreground(hwnd)
            self.wait_host_ready()

        logger.log_to_file(f"[HarmonyHost] [Error] Launching application.")
        self.wait_host_ready()

if __name__ == '__main__':
    if not is_admin():
        # Re-run the script with admin privileges
        print("Requesting administrative privileges...")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

    harmony_host = HarmonyHost()
    harmony_host.run()