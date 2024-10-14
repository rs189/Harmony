import os
import re
import requests
import subprocess
import sys
import time

from logger import Logger
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

current_path = os.path.dirname(os.path.realpath(__file__))
logger = Logger(os.path.join(current_path, 'app.log'), False)

class HarmonyAppCommon():
    def __init__(self):
        pass

    def get_running_vms(self):
        vms = subprocess.check_output(['virsh', 'list', '--name', '--state-running']).decode('utf-8').splitlines()
        return [vm.strip() for vm in vms if vm.strip()]

    def is_vm_running(self, vm_name):
        running_vms = self.get_running_vms()
        return vm_name in running_vms

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
        logger.log_to_file(f'[HarmonyAppCommon] [Error] No IP address found for the target VM {vm_name}.')
        sys.exit(1)

    def requests_retry_session(self,
        retries=30,
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