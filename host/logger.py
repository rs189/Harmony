import ctypes
import os
import sys

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

class Logger:
    def __init__(self, log_file, clear=True):
        self.log_file = log_file

        # Check if file exists
        if not os.path.exists(self.log_file):
            if not is_admin():
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
                sys.exit()

        if clear:
            with open(self.log_file, 'w') as f:
                f.write('')
                
    def log_to_file(self, message, exception=None):
        if exception:
            print(message, exception)
        else:
            print(message)
        with open(self.log_file, 'a') as f:
            f.write(f"{message}\n")