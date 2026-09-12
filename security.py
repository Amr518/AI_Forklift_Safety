import os
import json

class SecurityManager:
    """
    Manages security authentication, passwords loading, verification, 
    and password storage persistence for a 5-level access control matrix.
    """
    def __init__(self):
        self.file_name = "security.json"
        self.default_passwords = {
            "Operator": "",
            "Technician": "tech",
            "Supervisor": "1111",
            "Engineer": "admin",
            "Administrator": "superadmin",
            "Admin": "superadmin"
        }
        self.create_file_if_not_exists()

    def create_file_if_not_exists(self):
        if not os.path.exists(self.file_name):
            with open(self.file_name, "w") as file:
                json.dump(self.default_passwords, file, indent=4)
        else:
            # Upgrade existing file with missing default roles
            try:
                with open(self.file_name, "r") as file:
                    data = json.load(file)
                updated = False
                for role, pwd in self.default_passwords.items():
                    if role not in data:
                        data[role] = pwd
                        updated = True
                if updated:
                    with open(self.file_name, "w") as file:
                        json.dump(data, file, indent=4)
            except Exception:
                pass

    def load_passwords(self):
        try:
            with open(self.file_name, "r") as file:
                return json.load(file)
        except Exception:
            return self.default_passwords

    def verify_password(self, role, password):
        passwords = self.load_passwords()
        stored = passwords.get(role)
        if stored is None:
            if role == "Admin":
                stored = passwords.get("Administrator")
            elif role == "Administrator":
                stored = passwords.get("Admin")
        return stored == password

    def change_password(self, role, new_password):
        passwords = self.load_passwords()
        passwords[role] = new_password
        if role == "Admin":
            passwords["Administrator"] = new_password
        elif role == "Administrator":
            passwords["Admin"] = new_password
        with open(self.file_name, "w") as file:
            json.dump(passwords, file, indent=4)

