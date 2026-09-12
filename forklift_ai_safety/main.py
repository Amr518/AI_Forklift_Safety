# ==========================================
# DLL CONFLICT WORKAROUND FOR WINDOWS
# ==========================================
try:
    import torch
except ImportError:
    pass

import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow

def main():
    """
    Main application entry point. Initializes the master event loop
    and displays the Operations Console.
    """
    app = QApplication(sys.argv)
    
    # Establish dynamic window master instance
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
