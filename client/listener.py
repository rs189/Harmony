import os
import subprocess
import threading

from flask import Flask, request
from logger import Logger

current_path = os.path.dirname(os.path.realpath(__file__))
logger = Logger(os.path.join(current_path, 'app.log'), False)

# Harmony listener
class HarmonyClientListener(Flask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.shutdown_event = threading.Event()

        @self.route('/ready', methods=['GET'])
        def host_ready():
            logger.log_to_file(f"[HarmonyClientListener] [Info] Host is ready.")
            self.shutdown_event.set()
            return 'Host is ready.'

        @self.route('/terminate', methods=['GET'])
        def host_terminate():
            logger.log_to_file(f"[HarmonyClientListener] [Info] Host sent terminate.")  
            
            result = subprocess.run(['pkill', '-f', 'looking-glass-client'])
            if result.returncode == 0:
                logger.log_to_file(f"[HarmonyClientListener] [Info] Successfully terminated Looking Glass process.")
            else:
                logger.log_to_file(f"[HarmonyClientListener] [Error] Failed to terminate Looking Glass process.")
    
            current_pid = os.getpid()
            subprocess.run(['kill', str(current_pid)])
            return 'Host sent terminate.'

def start_harmony_listener(listener, port):
    harmony_port = int(port)
    listener.run(host='0.0.0.0', port=harmony_port)