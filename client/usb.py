import os
import pyudev
import re
import subprocess
import sys

from logger import Logger

current_path = os.path.dirname(os.path.realpath(__file__))
logger = Logger(os.path.join(current_path, 'app.log'), False)

class HarmonyAppUsb:
    def __init__(self, app_vm, usb_devices):
        self.app_vm = app_vm
        self.usb_devices = usb_devices

    def remove_hostdev_usb_entries(self):
        xml_file = f'/tmp/{self.app_vm}.xml'
        with open(xml_file, 'w') as file:
            file.write('')
        subprocess.check_output(f'virsh dumpxml {self.app_vm} > {xml_file}', shell=True, text=True)
        logger.log_to_file(f'[HarmonyApp] [Info] Dumped XML to {xml_file}')
        with open(xml_file, 'r+') as file:
            content = file.read()
            content = re.sub(r'<hostdev mode=.subsystem. type=.usb. managed=.yes.>.*?</hostdev>', '', content, flags=re.DOTALL)
            file.seek(0)
            file.write(content)
            file.truncate()

    def find_device_info(self, device_name):
        """
        This method searches for USB devices exactly matching the device name.
        It returns a list of dictionaries containing vendor ID, product ID, bus, and device for all matching devices.
        """
        try:
            # Get a list of all connected USB devices
            output = subprocess.check_output(['lsusb'], text=True)
            matching_devices = []

            logger.log_to_file("All USB devices:")
            for line in output.splitlines():
                logger.log_to_file(line)
                if device_name.lower() in line.lower():
                    match = re.search(r'Bus (\d+) Device (\d+): ID (\w+):(\w+)\s*(.*)', line)
                    if match:
                        bus, device, vendor_id, product_id, product = match.groups()
                        matching_devices.append({
                            'bus': bus,
                            'device': device,
                            'vendor_id': vendor_id,
                            'product_id': product_id,
                            'product': product.strip()
                        })

            logger.log_to_file(f"Matching devices for '{device_name}':")
            for device in matching_devices:
                logger.log_to_file(f"  Bus {device['bus']}, Device {device['device']}: ID {device['vendor_id']}:{device['product_id']} ({device['product']})")

            return matching_devices
        except subprocess.CalledProcessError as e:
            logger.log_to_file(f"Error finding USB devices: {str(e)}")
            sys.exit(1)

    def update_vm_usb(self, device_name, command):
        """
        Attach or detach all matching USB devices to/from the virtual machine.
        """
        matching_devices = self.find_device_info(device_name)
        if not matching_devices:
            logger.log_to_file(f"Could not find any devices matching '{device_name}'")
            sys.exit(1)
    
        logger.log_to_file(f"Found {len(matching_devices)} matching devices:")
        for device in matching_devices:
            logger.log_to_file(f"  Bus {device['bus']}, Device {device['device']}: ID {device['vendor_id']}:{device['product_id']} ({device['product']})")
    
        for device in matching_devices:
            # XML template for the USB device
            xml = f"""
            <hostdev mode='subsystem' type='usb' managed='yes'>
              <source>
                <vendor id='0x{device["vendor_id"]}'/>
                <product id='0x{device["product_id"]}'/>
                <address bus='{device["bus"]}' device='{int(device["device"])}'/>
              </source>
            </hostdev>
            """
            logger.log_to_file(f"Running virsh {command} {self.app_vm} for USB device: {device['vendor_id']}:{device['product_id']} (Bus {device['bus']}, Device {device['device']})")
            process = subprocess.run(
                ['virsh',command, self.app_vm, '/dev/stdin', '--persistent'],
                input=xml,
                text=True,
                capture_output=True
            )
            if process.returncode != 0:
                logger.log_to_file(f"Error running virsh command: {command}")
                logger.log_to_file(f"Error output: {process.stderr}")
            else:
                logger.log_to_file(f"Successfully {command}ed device {device['vendor_id']}:{device['product_id']} (Bus {device['bus']}, Device {device['device']})")

    def monitor_usb_changes(self):
       self.usb_devices = [usb_device.lower() for usb_device in self.usb_devices]

       context = pyudev.Context()
       monitor = pyudev.Monitor.from_netlink(context)
       monitor.filter_by('usb')
       
       for action, device in monitor:
           if action == 'add':
               self.handle_usb_addition()
           elif action == 'remove':
               self.handle_usb_removal()

    def get_attached_usb_devices(self):
        xml_file = f'/tmp/{self.app_vm}.xml'

        # Dump the current XML configuration of the VM
        subprocess.check_output(f'virsh dumpxml {self.app_vm} > {xml_file}', shell=True, text=True)
        logger.log_to_file(f'[HarmonyApp] [Info] Dumped XML to {xml_file}')

        # Read the XML file and find USB host devices
        with open(xml_file, 'r') as file:
            content = file.read()

            # Use regex to find all <hostdev> entries for USB devices
            matches = re.findall(r'<hostdev mode=\'subsystem\' type=\'usb\' managed=\'yes\'>.*?</hostdev>', content, flags=re.DOTALL)

        # Extract vendor and product IDs from matches
        attached_devices = []
        for match in matches:
            vendor_match = re.search(r'<vendor id=\'0x(\w+)\'/>', match)
            product_match = re.search(r'<product id=\'0x(\w+)\'/>', match)

            if vendor_match and product_match:
                vendor_id = vendor_match.group(1)
                product_id = product_match.group(1)
                attached_devices.append(f'{vendor_id}:{product_id}')

        return attached_devices

    def handle_usb_addition(self):
        for usb_device in self.usb_devices:
            self.update_vm_usb(usb_device, 'attach-device')

    def detach_usb_device(self, device_name):
        # Extract vendor and product IDs from device_name
        vendor_id, product_id = device_name.split(':')

        # XML to detach the device
        xml = f"""
        <hostdev mode='subsystem' type='usb' managed='yes'>
          <source>
            <vendor id='0x{vendor_id}'/>
            <product id='0x{product_id}'/>
          </source>
        </hostdev>
        """

        logger.log_to_file(f"Running virsh detach-device for USB device: {device_name}")
        process = subprocess.run(
            ['virsh', 'detach-device', self.app_vm, '/dev/stdin', '--persistent'],
            input=xml,
            text=True,
            capture_output=True
        )
        if process.returncode != 0:
            logger.log_to_file(f"Error detaching device {device_name}: {process.stderr}")
        else:
            logger.log_to_file(f"Successfully detached device {device_name}.")

    def handle_usb_removal(self):
        logger.log_to_file("Detected removal of USB device.")

        # Step 1: List all USB devices currently in use by the VM
        attached_devices = self.get_attached_usb_devices()

        # Step 4: Detach invalid devices
        for device_name in attached_devices:
            logger.log_to_file(f"Detaching USB device: {device_name}")
            # Construct XML for detaching the device
            self.detach_usb_device(device_name)

        for usb_device in self.usb_devices:
            self.update_vm_usb(usb_device, 'attach-device')