import os
import json

class SecurityManager:
    """
    Manages security authentication, passwords loading, verification, 
    and password storage persistence.
    """
    def __init__(self):
        # Dynamically resolve config path relative to the file location
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_dir = os.path.join(self.base_dir, "config")
        os.makedirs(self.config_dir, exist_ok=True)
        self.file_path = os.path.join(self.config_dir, "security.json")
        
        self.default_passwords = {
            "Supervisor": "1234",
            "Engineer": "admin"
        }
        self.create_file_if_not_exists()

    def create_file_if_not_exists(self):
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w") as file:
                json.dump(self.default_passwords, file, indent=4)

    def load_passwords(self):
        try:
            with open(self.file_path, "r") as file:
                return json.load(file)
        except Exception:
            return self.default_passwords

    def verify_password(self, role, password):
        passwords = self.load_passwords()
        return passwords.get(role) == password

    def change_password(self, role, new_password):
        passwords = self.load_passwords()
        passwords[role] = new_password
        with open(self.file_path, "w") as file:
            json.dump(passwords, file, indent=4)
