import os
import json
import tempfile

class SecurityManager:
    """
    Manages security authentication, passwords loading, verification, 
    and password storage persistence for a 5-level access control matrix.
    """
    def __init__(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.file_name = os.path.join(script_dir, "security.json")
        self.default_passwords = {
            "Operator": "",
            "Technician": "tech",
            "Supervisor": "1111",
            "Engineer": "admin",
            "Administrator": "superadmin",
            "Admin": "superadmin"
        }
        self.create_file_if_not_exists()

    def _atomic_write(self, data):
        dir_name = os.path.dirname(self.file_name)
        temp_fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_sec_")
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.file_name)
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            raise e

    def create_file_if_not_exists(self):
        if not os.path.exists(self.file_name):
            try:
                self._atomic_write(self.default_passwords)
            except Exception:
                pass
        else:
            # Upgrade existing file with missing default roles
            try:
                with open(self.file_name, "r", encoding="utf-8") as file:
                    data = json.load(file)
                updated = False
                for role, pwd in self.default_passwords.items():
                    if role not in data:
                        data[role] = pwd
                        updated = True
                if updated:
                    self._atomic_write(data)
            except Exception:
                pass

    def load_passwords(self):
        try:
            with open(self.file_name, "r", encoding="utf-8") as file:
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
        self._atomic_write(passwords)


