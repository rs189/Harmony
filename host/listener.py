import json
import os
import subprocess
import threading
import time

from flask import Flask, request

# Harmony configuration file
harmony_config_path = os.path.join(os.path.dirname(__file__), 'harmony.json')
if not os.path.exists(harmony_config_path):
    logger.log_to_file("Harmony configuration file not found.")
    sys.exit(1)
with open(harmony_config_path, 'r') as f:
    harmony_config = json.load(f)

def run_command_after_delay(command, delay=0.1):
    time.sleep(delay)
    try:
        subprocess.run(command, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")

# Harmony listener
class HarmonyListener(Flask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        @self.route('/execute', methods=['POST'])
        def execute_command():
            command = request.form.get('command')
            if command:
                # Inform the client that the command is about to run
                response = f"Command '{command}' will be executed."

                # Run the command in a separate thread, after a short delay
                threading.Thread(target=run_command_after_delay, args=(command,)).start()

                return response
            return 'No command provided.'

if __name__ == '__main__':
    listener = HarmonyListener(__name__)
    harmony_port = int(harmony_config.get('port', 5000))
    listener.run(host='0.0.0.0', port=harmony_port)