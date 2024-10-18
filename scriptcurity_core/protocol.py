from bittensor import Synapse
from cryptography.fernet import Fernet
import time
from .constants import REVEAL_INTERVAL


class Commit(Synapse):
    """
    Commit class that inherits from Synapse.
    - encrypted_commit_dockers (dict): A dictionary that stores the encrypted commit messages.
    - keys (dict): A dictionary that stores the keys used to encrypt the commit messages.
    """

    encrypted_commit_dockers: dict = {}
    public_keys: dict = {}

    # KEEP AWAY FROM VALIDATORS
    secret_keys: dict = {}
    commit_dockers: dict = {}

    def add_encrypted_commit(self, commit: str) -> str:
        """
        Encrypts the commit message using the provided key.
        """
        task_name, docker_hub_id = commit.split("---")
        self.commit_dockers[task_name] = docker_hub_id
        key = Fernet.generate_key()
        f = Fernet(key)
        token = f.encrypt(commit.encode())
        self.encrypted_commit_dockers[task_name] = token
        self.secret_keys[task_name] = (time.time(), key)

    def reveal_if_ready(self):
        for task_name, (created_time, key) in self.secret_keys.items():
            if time.time() - created_time > REVEAL_INTERVAL:
                self.public_keys[task_name] = key