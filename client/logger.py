class Logger:
    def __init__(self, log_file, clear=True):
        self.log_file = log_file
        if clear:
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