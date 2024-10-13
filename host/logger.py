class Logger:
    def __init__(self, log_file):
        self.log_file = log_file
        with open(self.log_file, 'w') as f:
            f.write('')

    def log_to_file(self, message, exception=None):
        if exception:
            print(message, exception)
        else:
            print(message)
        with open(self.log_file, 'a') as f:
            f.write(f"{message}\n")