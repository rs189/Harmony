import argparse
import gi
import json
import os
import re
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import subprocess
import sys
import threading
import _thread
import time

from flask import Flask, request

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

parser = argparse.ArgumentParser()
parser.add_argument('-app', type=str, required=True)
args = parser.parse_args()

# Get current path
current_path = os.path.dirname(os.path.realpath(__file__))
print(f"Current path: {current_path}")

# Logger class
class Logger:
    def __init__(self, log_file):
        self.log_file = log_file
        with open(self.log_file, 'w') as f:
            f.write('')

        self.window = None
        self.progress = ''

    def log_to_file(self, message, exception=None):
        if exception:
            print(message, exception)
        else:
            print(message)
        with open(self.log_file, 'a') as f:
            f.write(f"{message}\n")

    def log_progress(self, message):
        self.progress = message
        print(message)
        if self.window:
            self.window.update_label(message)

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

# Integrity check, make sure no other Python process is running for the same app
def check_running_processes():
    logger.log_to_file(f"Checking for running processes of {args.app}...")
    try:
        # List all running processes
        processes = subprocess.check_output(['ps', 'aux'], text=True).splitlines()
        current_pid = os.getpid() # Get the current process ID
        for process in processes:
            if 'python' in process and 'app.py' in process and args.app in process:
                logger.log_to_file(f"Found process: {process}")

                # Extract the PID
                pid = int(process.split()[1])

                # If the found PID is not the current process, kill it
                if pid != current_pid:
                    logger.log_to_file(f"Killing process with PID {pid}...")
                    subprocess.run(['kill', str(pid)])  # Ensure PID is passed as a string

    except subprocess.CalledProcessError as e:
        logger.log_to_file(f"Error checking running processes: {e}")

# Gtk application window
class AppWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_default_size(400, 300)  # Set default window size

        # Move window to center of the screen
        self.set_position(Gtk.WindowPosition.CENTER)

        # Create a Gtk.Fixed container to overlay the image and label
        fixed_container = Gtk.Fixed()
        self.add(fixed_container)

        # Load and add the image
        app_splash = app_config.get('splash')
        image_path = os.path.join(current_path, 'apps', app_splash)
        image = Gtk.Image.new_from_file(image_path)
        fixed_container.put(image, 0, 0)  # Place image at (0, 0)

        # Create the shadow label, this is not ideal but I don't want more complexity
        self.shadow_label = Gtk.Label()
        self.shadow_label.set_markup('<span foreground="black" size="large">Your Text Here</span>')  # Shadow color
        self.shadow_label.set_sensitive(False)  # Make it non-interactive
        self.shadow_label.set_margin_top(0)
        self.shadow_label.set_margin_bottom(0)

        # Create the main label and set its properties
        self.label = Gtk.Label()
        self.label.set_markup('<span foreground="white" size="large">Your Text Here</span>')  # Main text color
        self.label.set_sensitive(False)  # Make it non-interactive
        self.label.set_margin_top(0)
        self.label.set_margin_bottom(0)

        # Overlay the labels at the bottom left corner of the image
        fixed_container.put(self.shadow_label, 15, 415)  # Position for shadow label
        fixed_container.put(self.label, 15, 415)  # Position for main label

        self.connect("destroy", self.on_destroy)  # Close the window when the 'X' button is clicked

    def on_destroy(self, *args):
        print("Destroying window...")
        Gtk.main_quit()  # Quit the GTK main loop

    def update_label(self, new_text):
        # Use GLib.idle_add to ensure thread-safe updates to the labels
        GLib.idle_add(self.label.set_markup, f'<span foreground="white" size="large">{new_text}</span>')
        GLib.idle_add(self.shadow_label.set_markup, f'<span foreground="black" size="large">{new_text}</span>')

# Gtk application
class Application(Gtk.Application):
    def __init__(self):
        app_id = f"com.harmony.{args.app}"
        app_id = re.sub(r'\d+', lambda x: f'_{x.group()}', app_id)
        logger.log_to_file(f"[HarmonyApp] [Info] Creating application with ID: {app_id}")
        super().__init__(application_id=app_id)

        self.window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)

    def do_activate(self):
        if not self.window:
            self.window = AppWindow(application=self, title=app_name)

            harmony_app = HarmonyApp()
            harmony_app.window = self.window
            harmony_thread = threading.Thread(target=harmony_app.run)
            harmony_thread.start()

            logger.window = self.window

        self.window.show_all()
        self.window.present()

# Harmony listener
class HarmonyListener(Flask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.shutdown_event = threading.Event()

        @self.route('/ready', methods=['GET'])
        def host_ready():
            logger.log_to_file(f"[HarmonyListener] [Info] Host is ready.")
            self.shutdown_event.set()
            return 'Host is ready.'

def start_harmony_listener(listener):
    listener.run(host='0.0.0.0', port=5000)

# Harmony application
class HarmonyApp():
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

        self.command = app_config.get('command')

        # List of other VMs that use the GPU
        self.gpu_vms_path = os.path.join(os.path.dirname(__file__), 'gpu-vms.json')
        if not os.path.exists(self.gpu_vms_path):
            logger.log_to_file('[HarmonyApp] [Error] Configuration file for GPU VMs not found.')
            sys.exit(1)
        with open(self.gpu_vms_path, 'r') as f:
            self.gpu_vms_config = json.load(f)
        self.vms_config = self.gpu_vms_config.get("vms", [])

    def get_running_vms(self):
        vms = subprocess.check_output(['virsh', 'list', '--name', '--state-running']).decode('utf-8').splitlines()
        return [vm.strip() for vm in vms if vm.strip()]

    def is_vm_running(self, vm_name):
        running_vms = self.get_running_vms()
        return vm_name in running_vms

    def wait_for_vm_start(self, vm_name, timeout=500):
        elapsed = 0
        interval = 1
        while not self.is_vm_running(vm_name):
            if elapsed >= timeout:
                logger.log_to_file(f'[HarmonyApp] [Error] Timeout: VM {vm_name} did not start in time.')
                sys.exit(1)
            logger.log_to_file(f'[HarmonyApp] [Info] Waiting for VM {vm_name} to start...')
            time.sleep(interval)
            elapsed += interval
        logger.log_to_file(f'[HarmonyApp] [Info] VM {vm_name} is now running.')

    def get_vm_ip(self, vm_name, timeout=500):
        elapsed = 0
        interval = 1
        while elapsed < timeout:
            virsh_output = subprocess.check_output(['virsh', 'domifaddr', vm_name]).decode('utf-8')
            pattern = r'(\d{1,3}(?:\.\d{1,3}){3})'
            match = re.search(pattern, virsh_output)
            ip_address = match.group(1) if match else None
            if ip_address:
                return ip_address
            time.sleep(interval)
            elapsed += interval
        logger.log_to_file(f'[HarmonyApp] [Error] No IP address found for the target VM {vm_name}.')
        sys.exit(1)

    def requests_retry_session(self,
        retries=3,
        backoff_factor=0.3,
        status_forcelist=(500, 502, 504),
        session=None,
    ):
        session = session or requests.Session()
        
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def hibernate_vm(self, vm_name):
        ip_address = self.get_vm_ip(vm_name)
        if not ip_address:
            logger.log_to_file(f'[HarmonyApp] [Error] No IP address found for the target VM {vm_name}.')
            sys.exit(1)
        url = 'http://' + ip_address + ':5000/execute'
        try:
            #response = requests.post(url, data={'command': 'python hibernate.py'}, timeout=10)
            response = self.requests_retry_session().post(url, data={'command': 'python ../hibernate.py'}, timeout=10)
            logger.log_to_file(f'[HarmonyApp] [Info] Start app {app_name} response from server: {response.text}')
        except requests.exceptions.Timeout:
            logger.log_to_file(f'[HarmonyApp] [Error] Request timed out trying to hibernate VM {vm_name}')
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            logger.log_to_file(f'[HarmonyApp] [Error] Exception trying to hibernate VM {vm_name} ', e)
            sys.exit(1)

    def wait_for_vm_hibernate(self, vm_name, timeout=500):
        elapsed = 0
        interval = 1
        while self.is_vm_running(vm_name):
            if elapsed >= timeout:
                logger.log_to_file(f"[HarmonyApp] [Error] Timeout: VM {vm_name} did not hibernate in time.")
                sys.exit(1)
            logger.log_to_file(f"[HarmonyApp] [Info] Waiting for VM {vm_name} to hibernate...")
            time.sleep(interval)
            elapsed += interval
        logger.log_to_file(f"[HarmonyApp] [Info] VM {vm_name} has successfully hibernated.")

    def remove_hostdev_entries(self, vm_name, xml_file):
        with open(xml_file, 'w') as file:
            file.write('')
        subprocess.check_output(f'virsh dumpxml {vm_name} > {xml_file}', shell=True, text=True)
        print(f"Dumped XML to {xml_file}")
        with open(xml_file, 'r+') as file:
            content = file.read()
            content = re.sub(r'<hostdev mode=.subsystem. type=.usb. managed=.yes.>.*?</hostdev>', '', content, flags=re.DOTALL)
            file.seek(0)
            file.write(content)
            file.truncate()

    def device_exists_in_xml(self, xml_file, bus, device):
        with open(xml_file, 'r') as file:
            return re.search(f"<address bus='{bus}' device='{device}'/>", file.read()) is not None

    def add_hostdev_entries(self, vm_name, xml_file):
        if not self.usb_devices or not all(self.usb_devices):
            logger.log_to_file(f'[HarmonyApp] [Info] No USB devices specified for {app_name}.')
            return
        ls_usb = subprocess.check_output('lsusb', shell=True, text=True)
        if not ls_usb:
            return
        port = 1
        for usb_device in ls_usb.splitlines():
            for usb_device_name in self.usb_devices:
                if usb_device_name in usb_device:
                    # Extract vendor and product IDs
                    vendor_id = re.search(r'ID (\w+):(\w+)', usb_device).group(1)
                    product_id = re.search(r'ID (\w+):(\w+)', usb_device).group(2)
                    bus = re.search(r'Bus (\d+)', usb_device).group(1)
                    device = re.search(r'Device (\d+)', usb_device).group(1)

                    # Strip leading zeros from the device ID
                    device = str(int(device))

                    # Check if the device already exists in the XML by checking both bus and device
                    if self.device_exists_in_xml(xml_file, bus, device):
                        logger.log_to_file(f'[HarmonyApp] [Info] USB device already exists with bus {bus} device {device} ID {vendor_id}:{product_id} {usb_device_name} in {vm_name} VM.')
                        continue

                    logger.log_to_file(f'[HarmonyApp] [Info] Adding USB device with bus {bus} device {device} ID {vendor_id}:{product_id} {usb_device_name} to {vm_name} VM.')
                    # Add the hostdev entry to the XML
                    with open(xml_file, 'r+') as file:
                        content = file.read()
                        hostdev_entry = f"""
                        <hostdev mode='subsystem' type='usb' managed='yes'>
                            <source>
                                <vendor id='0x{vendor_id}'/>
                                <product id='0x{product_id}'/>
                                <address bus='{bus}' device='{device}'/>
                            </source>
                            <address type='usb' bus='0' port='{port}'/>
                        </hostdev>"""
                        content = re.sub(r'(<devices>)', r'\1\n' + hostdev_entry, content)
                        file.seek(0)
                        file.write(content)
                        file.truncate()

                    logger.log_to_file(f'[HarmonyApp] [Info] Added USB device with bus {bus} device {device} ID {vendor_id}:{product_id} {usb_device_name} to {vm_name} VM.')

                    port += 1

    def define_vm(self, vm_name, xml_file):
        print(f"Defining VM {vm_name}...")
        print(xml_file)
        subprocess.run(['virsh', 'define', xml_file])

    def start_vm(self, vm_name, timeout=500):
        elapsed = 0
        interval = 1
        while elapsed < timeout:
            subprocess.run(['virsh', 'start', vm_name])
            if self.is_vm_running(vm_name):
                logger.log_to_file(f'[HarmonyApp] [Info] Started VM {vm_name}.')
                return
            time.sleep(interval)
            elapsed += interval

    def start_app(self, vm_name):
        ip_address = self.get_vm_ip(self.app_vm)
        if not ip_address:
            logger.log_to_file(f'[HarmonyApp] [Error] No IP address found for the target VM {self.app_vm}.')
            sys.exit(1)
        url = 'http://' + ip_address + ':5000/execute'

        # Go over all other json files and get their `mainexe` and append them to the `killexes` list
        for file in os.listdir(apps_path):
            if file.endswith(".json") and file != f"{args.app}.json":
                with open(os.path.join(apps_path, file), 'r') as f:
                    other_app_config = json.load(f)
                    other_mainexe = other_app_config.get('mainexe')
                    print(self.killexes)
                    self.killexes += f' "{other_mainexe}"'
                    print(f"Added {other_mainexe}...")

        app_command = f'python ../app.py -app {self.command} -mainexe {self.mainexe} -alwaysontop {self.alwaysontop} -exes {self.exes} -killexes {self.killexes}'
        try:
            #response = requests.post(url, data={'command': app_command}, timeout=10)
            response = self.requests_retry_session().post(url, data={'command': app_command}, timeout=10)
            logger.log_to_file(f'[HarmonyApp] [Info] Start app {app_name} response from server: ', response.text)
        except requests.exceptions.Timeout:
            logger.log_to_file(f'[HarmonyApp] [Error] Request timed out trying to start app {app_name}')
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            logger.log_to_file(f'[HarmonyApp] [Error] Exception trying to start app {app_name} ', e)
            sys.exit    

    def start_lg(self):
        os.environ["GDK_BACKEND"] = "wayland"

        lg_command = [
            '/home/russell/Documents/GitHub/LookingGlass/client/build/looking-glass-client',
            'audio:micShowIndicator=no',
            'audio:micDefault=allow',
            'spice:port=5905',
            'wayland:warpSupport=no',
            'win:quickSplash=yes',
            'win:jitRender=yes',
            'spice:captureOnStart=yes',
            'input:captureOnFocus=yes',
            'input:grabKeyboard=no',
        ]
        lg_command.append(f'win:title={app_name}')
        app_id = f"com.harmony.{args.app}"
        app_id = re.sub(r'\d+', lambda x: f'_{x.group()}', app_id)
        lg_command.append(f'win:appId={app_id}')
        try:
            # Launch Looking Glass using Popen and monitor the process
            process = subprocess.Popen(lg_command)

            # Wait for the process to terminate
            process.wait()

            logger.log_to_file(f"[HarmonyApp] [Info] Looking Glass terminated with exit code {process.returncode}")
            _thread.interrupt_main()
        except Exception as e:
            logger.log_to_file(f"[HarmonyApp] [Error] Error launching Looking Glass: {e}")
            sys.exit(1)

    def run(self):
        running_vms = self.get_running_vms()
        if self.app_vm not in running_vms:
            for vm in running_vms:
                # Only hibernate the VMs listed in gpu-vms.json
                if vm in self.vms_config and vm != self.app_vm:
                    logger.log_progress(f"HIBERNATING...")
                    logger.log_to_file(f'[HarmonyApp] [Info] Hibernating {vm}...')
                    self.hibernate_vm(vm)
                    self.wait_for_vm_hibernate(vm)
        
        logger.log_progress(f"REMOVING USB DEVICES...")
        logger.log_to_file(f'[HarmonyApp] [Info] Removing hostdev entries from {self.app_vm} VM...')
        xml_file = "/tmp/libvirt_harmony.xml"
        self.remove_hostdev_entries(self.app_vm, xml_file)

        logger.log_progress(f"ADDING USB DEVICES...")
        logger.log_to_file(f'[HarmonyApp] [Info] Adding hostdev entries to {self.app_vm} VM...')
        self.add_hostdev_entries(self.app_vm, xml_file)

        logger.log_progress(f"DEFINING...")
        logger.log_to_file(f'[HarmonyApp] [Info] Defining VM {self.app_vm}...')
        self.define_vm(self.app_vm, xml_file)

        logger.log_progress(f"STARTING VM...")
        logger.log_to_file(f'[HarmonyApp] [Info] Starting VM {self.app_vm}...')
        self.start_vm(self.app_vm)

        logger.log_progress(f"STARTING APP...")
        logger.log_to_file(f'[HarmonyApp] [Info] Starting app {app_name}...')
        self.start_app(self.app_vm)

        logger.log_progress(f"WAITING...")
        logger.log_to_file(f'[HarmonyApp] [Info] Starting Flask listener...') 
        listener = HarmonyListener(__name__)

        listener_thread = threading.Thread(target=start_harmony_listener, args=(listener,))
        listener_thread.start()
        
        listener.shutdown_event.wait()
        logger.log_progress(f"LAUNCHING...")
        logger.log_to_file("[HarmonyApp] [Info] Shutting down Flask listener...")

        # Close the splash screen
        if self.window:
            logger.log_to_file(f"[HarmonyApp] [Info] Destroying splash screen window...")
            self.window.destroy()

        logger.log_to_file(f'[HarmonyApp] [Info] Launching Looking Glass...')
        self.start_lg()
        sys.exit(1)

if __name__ == "__main__":
    check_running_processes()

    app = Application()
    app.run(None)