import argparse
import _thread
import gi
import json
import os
import re
import requests
import subprocess
import sys
import threading
import time

from common import HarmonyClientCommon
from flask import Flask, request
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from hibernate import HarmonyClientHibernate
from launcher import HarmonyLauncherWindow
from listener import HarmonyClientListener, start_harmony_listener
from logger import Logger
from usb import HarmonyClientUsb

parser = argparse.ArgumentParser()
parser.add_argument('-app', type=str, required=True)
args = parser.parse_args()

current_path = os.path.dirname(os.path.realpath(__file__))
logger = Logger(os.path.join(current_path, 'app.log'))

# Configuration file for the given app
apps_path = os.path.join(os.path.dirname(__file__), 'apps')
app_json_path = os.path.join(apps_path, f"{args.app}.json")
if not os.path.exists(app_json_path):
    logger.log_to_file(f"Configuration file for {args.app} not found.")
    sys.exit(1)
with open(app_json_path, 'r') as f:
    app_config = json.load(f)

app_name = app_config.get('name')

# Harmony configuration file
harmony_config_path = os.path.join(os.path.dirname(__file__), 'harmony.json')
if not os.path.exists(harmony_config_path):
    logger.log_to_file("Harmony configuration file not found.")
    sys.exit(1)
with open(harmony_config_path, 'r') as f:
    harmony_config = json.load(f)

# Gtk application
class HarmonyLauncher(Gtk.Application):
    def __init__(self, app, app_name, app_splash, app_colour):
        app_id = f"com.harmony.{app}"
        app_id = re.sub(r'\d+', lambda x: f'_{x.group()}', app_id)
        logger.log_to_file(f"[HarmonyLauncher] [Info] Creating application with ID: {app_id}")
        super().__init__(application_id=app_id)
        
        self.app_name = app_name
        self.app_splash = app_splash
        self.app_colour = app_colour
        self.harmony_client = None

        self.window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)

    def do_activate(self):
        if not self.window:
            self.window = HarmonyLauncherWindow(application=self)

            harmony_app = HarmonyClient()
            self.harmony_client = harmony_app
            self.window.harmony_client = self.harmony_client
            harmony_app.window = self.window
            harmony_thread = threading.Thread(target=harmony_app.run)
            harmony_thread.start()

            logger.window = self.window

        self.window.show_all()
        self.window.present()

# Harmony application
class HarmonyClient():
    def __init__(self):
        self.window = None

        self.app_vm = app_config.get('vm')
        self.mainexe = app_config.get('mainexe')
        self.alwaysontop = app_config.get('alwaysontop', False)

        self.exes = app_config.get('exes', [])
        self.exes = ' '.join([f'"{exe}"' for exe in self.exes])

        self.killexes = app_config.get('killexes', [])
        self.killexes = ' '.join([f'"{killexe}"' for killexe in self.killexes])

        self.usb_devices = app_config.get('usb_devices', [])

        self.client_command = app_config.get('client_command')
        self.client_undo_command = app_config.get('client_undo_command')
        self.command = app_config.get('command')
        
        self.wait_for_easy_anti_cheat = app_config.get('wait-for-easy-anti-cheat', True)
        self.create_black_window = app_config.get('create-black-window', True)
        self.monitor_process = app_config.get('monitor-process', True)
        self.delay = app_config.get('delay', 0)

        self.common = HarmonyClientCommon()
        self.hibernate = HarmonyClientHibernate()
        self.usb = HarmonyClientUsb(self.app_vm, self.usb_devices)

    def wait_for_vm_start(self, vm_name, timeout=500):
        elapsed = 0
        interval = 1
        while not self.common.is_vm_running(vm_name):
            if elapsed >= timeout:
                logger.log_to_file(f'[HarmonyClient] [Error] Timeout: VM {vm_name} did not start in time.')
                sys.exit(1)
            logger.log_to_file(f'[HarmonyClient] [Info] Waiting for VM {vm_name} to start...')
            time.sleep(interval)
            elapsed += interval
        logger.log_to_file(f'[HarmonyClient] [Info] VM {vm_name} is now running.')

    def start_vm(self, vm_name, timeout=500):
        elapsed = 0
        interval = 1
        while elapsed < timeout:
            subprocess.run(['virsh', 'start', vm_name])
            if self.common.is_vm_running(vm_name):
                logger.log_to_file(f'[HarmonyClient] [Info] Started VM {vm_name}.')
                return
            time.sleep(interval)
            elapsed += interval

    def cancel_start_app(self):
        ip_address = self.common.get_vm_ip(self.app_vm)
        if not ip_address:
            logger.log_to_file(f'[HarmonyClient] [Error] No IP address found for the target VM {self.app_vm}.')
            sys.exit(1)
        url = 'http://' + ip_address + ':5000/cancel'
        exes = self.exes
        logger.log_to_file(f'[HarmonyClient] [Info] Sending command to cancel start app {app_name}: {exes}')
        try:
            response = self.common.requests_retry_session().post(url, data={'exes': exes}, timeout=10)
            logger.log_to_file(f'[HarmonyClient] [Info] Cancel start app {app_name} response from server: ', response.text)
            process = subprocess.Popen(['kill', str(os.getpid())])
            sys.exit(1)
        except requests.exceptions.Timeout:
            logger.log_to_file(f'[HarmonyClient] [Error] Request timed out trying to cancel start app {app_name}')
            process = subprocess.Popen(['kill', str(os.getpid())])
            sys.exit(1)

    def stop_app(self):
        ip_address = self.common.get_vm_ip(self.app_vm)
        if not ip_address:
            logger.log_to_file(f'[HarmonyClient] [Error] No IP address found for the target VM {self.app_vm}.')
            sys.exit(1)
        url = 'http://' + ip_address + ':5000/stop'
        exes = ''
        for file in os.listdir(apps_path):
            if file.endswith(".json"):
                with open(os.path.join(apps_path, file), 'r') as f:
                    other_app_config = json.load(f)
                    if other_app_config.get('vm') == self.app_vm:
                        other_exes = other_app_config.get('exes', [])
                        exes += ' ' + ' '.join([f'"{exe}"' for exe in other_exes])
        logger.log_to_file(f'[HarmonyClient] [Info] Sending command to stop app {app_name}: {exes}')
        try:
            response = self.common.requests_retry_session().post(url, data={'exes': exes}, timeout=10)
            logger.log_to_file(f'[HarmonyClient] [Info] Stop app {app_name} response from server: ', response.text)
            process = subprocess.Popen(['kill', str(os.getpid())])
            sys.exit(1)
        except requests.exceptions.Timeout:
            logger.log_to_file(f'[HarmonyClient] [Error] Request timed out trying to stop app {app_name}')
            process = subprocess.Popen(['kill', str(os.getpid())])
            sys.exit(1)

    def start_app(self):
        ip_address = self.common.get_vm_ip(self.app_vm)
        if not ip_address:
            logger.log_to_file(f'[HarmonyClient] [Error] No IP address found for the target VM {self.app_vm}.')
            sys.exit(1)
        url = 'http://' + ip_address + ':5000/execute'

        # Run client command if specified
        if self.client_command:
            logger.log_to_file(f'[HarmonyClient] [Info] Running client command: {self.client_command}')
            subprocess.run(self.client_command, shell=True)

        # Go over all other json files and get their `mainexe` and append them to the `killexes` list
        for file in os.listdir(apps_path):
            if file.endswith(".json") and file != f"{args.app}.json":
                with open(os.path.join(apps_path, file), 'r') as f:
                    other_app_config = json.load(f)
                    # If other `vm` is the same as the current `vm`
                    if other_app_config.get('vm') == self.app_vm:
                        #other_mainexe = other_app_config.get('mainexe')
                        #self.killexes += f' "{other_mainexe}"'
                        # Instead of just the main exe, we will add all exes
                        other_exes = other_app_config.get('exes', [])
                        self.killexes += ' ' + ' '.join([f'"{exe}"' for exe in other_exes])

        app_command = f'pythonw.exe ../app.py -app "{self.command}" -mainexe "{self.mainexe}" -alwaysontop {self.alwaysontop} -exes {self.exes} -killexes {self.killexes} -waitforeac "{self.wait_for_easy_anti_cheat}" -createblackwindow "{self.create_black_window}" -monitorprocess "{self.monitor_process}" -delay {self.delay}'
        logger.log_to_file(f'[HarmonyClient] [Info] Sending command to start app {app_name}: {app_command}')
        try:
            response = self.common.requests_retry_session().post(url, data={'command': app_command}, timeout=10)
            logger.log_to_file(f'[HarmonyClient] [Info] Start app {app_name} response from server: ', response.text)
        except requests.exceptions.Timeout:
            logger.log_to_file(f'[HarmonyClient] [Error] Request timed out trying to start app {app_name}')
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            logger.log_to_file(f'[HarmonyClient] [Error] Exception trying to start app {app_name} ', e)
            sys.exit    

    def start_lg(self, listener):
        lg_gdk_backend = harmony_config.get('looking-glass-gdk-backend')
        logger.log_to_file(f"[HarmonyClient] [Info] Setting the Looking Glass backend to: {lg_gdk_backend}")
        os.environ["GDK_BACKEND"] = lg_gdk_backend

        lg_path = harmony_config.get('looking-glass-path')
        if not lg_path:
            logger.log_to_file(f"[HarmonyClient] [Error] Looking Glass path not found.")
            sys.exit(1)
        lg_path = os.path.expanduser(lg_path)
        logger.log_to_file(f"[HarmonyClient] [Info] Looking Glass path: {lg_path}")

        lg_command = [lg_path]
        lg_command.append(f'spice:port={int(harmony_config.get('spice-port'))}')
        lg_args = harmony_config.get('looking-glass-args', [])
        for lg_arg in lg_args:
            lg_command.append(lg_arg)
        lg_command.append(f'win:title={app_name}')
        app_id = f"com.harmony.{args.app}"
        app_id = re.sub(r'\d+', lambda x: f'_{x.group()}', app_id)
        lg_command.append(f'win:appId={app_id}')
        logger.log_to_file(f"[HarmonyClient] [Info] Launching Looking Glass with the command: {lg_command}")
        try:
            usb_monitor_thread = threading.Thread(target=self.usb.monitor_usb_changes)
            usb_monitor_thread.daemon = True
            usb_monitor_thread.start()

            # Launch Looking Glass using Popen and monitor the process
            process = subprocess.Popen(lg_command)

            listener_thread = threading.Thread(target=start_harmony_listener, args=(listener,harmony_config.get('port', 5000)))
            listener_thread.start()
        
            # Wait for the process to terminate
            process.wait()

            usb_monitor_thread.join()

            # Run client undo command if specified
            if self.client_undo_command:
                logger.log_to_file(f'[HarmonyClient] [Info] Running client undo command: {self.client_undo_command}')
                subprocess.run(self.client_undo_command, shell=True)

            logger.log_to_file(f"[HarmonyClient] [Info] Looking Glass terminated with exit code {process.returncode}")
            _thread.interrupt_main()
        except Exception as e:
            logger.log_to_file(f"[HarmonyClient] [Error] Error launching Looking Glass: {e}")
            sys.exit(1)

    def run(self):
        listener = HarmonyClientListener(__name__)
        listener_thread = threading.Thread(target=start_harmony_listener, args=(listener,harmony_config.get('port', 5000)))
        listener_thread.start()

        running_vms = self.common.get_running_vms()
        if self.app_vm not in running_vms:
            for vm in running_vms:
                # Only hibernate the VMs listed in gpu-vms.json
                if vm in harmony_config.get('domains', []) and vm != self.app_vm:
                    logger.log_progress(f"HIBERNATING...")
                    logger.log_to_file(f'[HarmonyClient] [Info] Hibernating {vm}...')
                    self.hibernate.hibernate_vm(vm)
                    self.hibernate.wait_for_vm_hibernate(vm)
        
        logger.log_progress(f"REMOVING USB DEVICES...")
        logger.log_to_file(f'[HarmonyClient] [Info] Removing hostdev entries from {self.app_vm} VM...')
        if not self.common.is_vm_running(self.app_vm):
            self.usb.remove_hostdev_usb_entries()

        logger.log_progress(f"STARTING VM...")
        logger.log_to_file(f'[HarmonyClient] [Info] Starting VM {self.app_vm}...')
        self.start_vm(self.app_vm)

        logger.log_progress(f"ADDING USB DEVICES...")
        logger.log_to_file(f'[HarmonyClient] [Info] Adding hostdev entries to {self.app_vm} VM...')
        self.usb.handle_usb_addition()

        logger.log_progress(f"STARTING APP...")
        logger.log_to_file(f'[HarmonyClient] [Info] Starting app {app_name}...')
        self.start_app()

        logger.log_progress(f"WAITING...")
        logger.log_to_file(f'[HarmonyClient] [Info] Starting Flask listener...') 

        listener.shutdown_event.wait()
        logger.log_progress(f"LAUNCHING...")
        logger.log_to_file("[HarmonyClient] [Info] Shutting down Flask listener...")

        # Close the splash screen
        if self.window:
            logger.log_to_file(f"[HarmonyClient] [Info] Destroying splash screen window...")
            self.window.lg_ready = True
            self.window.destroy()

        logger.log_to_file(f'[HarmonyClient] [Info] Launching Looking Glass...')
        self.start_lg(listener)
        sys.exit(1)

if __name__ == "__main__":
    logger.log_to_file(f"Checking for running processes...")
    try:
        processes = subprocess.check_output(['ps', 'aux'], text=True).splitlines()
        for process in processes:
            if 'python' in process and 'app.py' in process:
                logger.log_to_file(f"Found process: {process}")
                pid = int(process.split()[1])
                current_pid = os.getpid()
                if pid != current_pid:
                    logger.log_to_file(f"Killing process with PID {pid}...")
                    subprocess.run(['kill', str(pid)])
    except subprocess.CalledProcessError as e:
        logger.log_to_file(f"Error checking running processes: {e}")

    launcher = HarmonyLauncher(args.app, app_config.get('name'), app_config.get('splash'), app_config.get('colour'))
    launcher.run(None)