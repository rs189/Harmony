import argparse
import json
import os
import re
import requests
import subprocess
import sys
import time

from common import HarmonyAppCommon
from logger import Logger
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

current_path = os.path.dirname(os.path.realpath(__file__))
logger = Logger(os.path.join(current_path, 'hibernate.log'))

class HarmonyAppHibernate():
    def __init__(self):
        self.common = HarmonyAppCommon()

    def hibernate_vm(self, vm_name):
        ip_address = self.common.get_vm_ip(vm_name)
        if not ip_address:
            logger.log_to_file(f'[HarmonyAppHibernate] [Error] No IP address found for the target VM {vm_name}.')
            sys.exit(1)
        url = 'http://' + ip_address + ':5000/execute'
        try:
            #response = requests.post(url, data={'command': 'python hibernate.py'}, timeout=10)
            response = self.common.requests_retry_session().post(url, data={'command': 'python_admin.exe ../hibernate.py'}, timeout=10)
            logger.log_to_file(f'[HarmonyAppHibernate] [Info] Hibernate VM {vm_name} response from server: {response.text}')
        except requests.exceptions.Timeout:
            logger.log_to_file(f'[HarmonyAppHibernate] [Error] Request timed out trying to hibernate VM {vm_name}')
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            logger.log_to_file(f'[HarmonyAppHibernate] [Error] Exception trying to hibernate VM {vm_name} ', e)
            sys.exit(1)

    def wait_for_vm_hibernate(self, vm_name, timeout=500):
        elapsed = 0
        interval = 1
        while self.common.is_vm_running(vm_name):
            if elapsed >= timeout:
                logger.log_to_file(f"[HarmonyAppHibernate] [Error] Timeout: VM {vm_name} did not hibernate in time.")
                sys.exit(1)
            logger.log_to_file(f"[HarmonyAppHibernate] [Info] Waiting for VM {vm_name} to hibernate...")
            time.sleep(interval)
            elapsed += interval
        logger.log_to_file(f"[HarmonyAppHibernate] [Info] VM {vm_name} has successfully hibernated.")

    def run(self):
        running_vms = self.common.get_running_vms()
        for vm in running_vms:
            self.hibernate_vm(vm)
            self.wait_for_vm_hibernate(vm)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-standalone', type=str, required=False) # Whether this script is called on its own 
    args = parser.parse_args()

    if str(args.standalone).lower() == 'true':
        harmony_app_hibernate = HarmonyAppHibernate()
        harmony_app_hibernate.run()