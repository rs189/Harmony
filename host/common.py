import os
import subprocess

from logger import Logger

current_path = os.path.dirname(os.path.realpath(__file__))
logger = Logger(os.path.join(current_path, 'app.log'), False)

class HarmonyCommon():
    def __init__(self):
        pass

    def are_processes_running(self, processes):
        for process in processes:
            logger.log_to_file(f'[HarmonyCommon] [Info] Checking if {process} is running...')
            command = f'tasklist /FI "IMAGENAME eq {process}"'

            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            # Check if the process name is in the output
            if process in result.stdout:
                logger.log_to_file(f'[HarmonyCommon] [Info] The {process} is running...')
                return True
            if result.returncode != 0:
                logger.log_to_file(f'[HarmonyCommon] [Error] Error checking {process}: {result.stderr.strip()}')
        return False

    def kill_process(self, process):
        try:
            subprocess.run(f'taskkill /F /IM {process}', shell=True)
            logger.log_to_file(f'[HarmonyCommon] [Info] Killed process {process}')
        except Exception as e:
            logger.log_to_file(f'[HarmonyCommon] [Error] Failed to kill process {process}: {e}')