import os
import time
import json
import requests
import threading
from shutil import rmtree
from datetime import timedelta
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor, as_completed

import bittensor as bt
from diskcache import Cache
from huggingface_hub import HfApi
from constants import constants


class StorageManager:
    def __init__(self, cache_dir: str, hf_repo_id: str, sync_on_init=True):
        """
        Manages local cache, Hugging Face Hub storage, and centralized storage.

        Args:
            cache_dir (str): Path to the local cache directory.
            hf_repo_id (str): ID of the Hugging Face Hub repository.
            sync_on_init (bool): Whether to sync data from the Hub to the local cache during initialization.
        """

        # Decentralized storage on Hugging Face Hub
        self.hf_repo_id = hf_repo_id
        self.hf_api = HfApi()
        bt.logging.info(f"Authenticated as {self.hf_api.whoami()["name"]}")
        self._validate_hf_repo()

        # Local cache with disk cache
        self.cache_dir = cache_dir
        self.cache_ttl = int(timedelta(days=14).total_seconds()) # TTL set equal to a decaying period
        self.local_caches: dict[Cache] = {}
        self.centralized_storage_url = constants.STORAGE_URL + "/upload"

        # Queue and background thread for async updates
        self.storage_queue = Queue()
        self.storage_thread = threading.Thread(target=self._process_storage_queue, daemon=True)
        self.storage_thread.start()

        # Start periodic cache-to-hub synchronization
        self.sync_thread = threading.Thread(
            target=self._sync_cache_to_hub_periodically,
            kwargs={"interval": 3600},
            daemon=True
        )
        self.sync_thread.start()

        os.makedirs(self.cache_dir, exist_ok=True)

        # Sync data from Hugging Face Hub to local cache if required
        if sync_on_init:
            self.sync_hub_to_cache()

    def _validate_hf_repo(self):
        """
        Validates the Hugging Face repository:
        - Ensures the token has write permissions.
        - Confirms the repository exists and meets required attributes.
        - Creates a public repository if it does not exist.
        """
        # Step 1: Ensure token has write permissions
        permission = self.hf_api.get_token_permission()
        if permission != "write":
            raise PermissionError(f"Token does not have sufficient permissions for repository {self.hf_repo_id}. Current permission: {permission}.")
        bt.logging.info("Token has write permissions.")

        # Step 2: Check accessible namespaces (users/orgs)
        user_info = self.hf_api.whoami()
        allowed_namespaces = {user_info["name"], *user_info["orgs"]}
        repo_namespace, _ = self.hf_repo_id.split("/")
        if repo_namespace not in allowed_namespaces:
            raise PermissionError(f"Token does not grant write access to the namespace '{repo_namespace}'. Accessible namespaces: {allowed_namespaces}.")
        bt.logging.info(f"Namespace '{repo_namespace}' is accessible with write permissions.")

        # Step 3: Validate or create the repository
        try:
            repo_info = self.hf_api.repo_info(repo_id=self.hf_repo_id)
            if repo_info.private:
                raise ValueError(f"Repository '{self.hf_repo_id}' is private but must be public.")
            bt.logging.info(f"Repository '{self.hf_repo_id}' exists and is public.")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:  # Repo does not exist
                bt.logging.warning(f"Repository '{self.hf_repo_id}' does not exist. Attempting to create it.")
                try:
                    self.hf_api.create_repo(repo_id=self.hf_repo_id, private=False, exist_ok=True)
                    bt.logging.info(f"Repository '{self.hf_repo_id}' has been successfully created.")
                except Exception as create_err:
                    raise RuntimeError(f"Failed to create repository '{self.hf_repo_id}': {create_err}")
            else:
                raise RuntimeError(f"Error validating repository '{self.hf_repo_id}': {e}")

    def _get_cache(self, challenge_name: str) -> Cache:
        """
        Returns the diskcache instance for a specific challenge, with a expiration policy.

        Args:
            challenge_name (str): The name of the challenge.

        Returns:
            Cache: The cache instance.
        """
        if challenge_name not in self.local_caches:
            challenge_cache_path = os.path.join(self.cache_dir, challenge_name)
            cache = Cache(challenge_cache_path, eviction_policy="none")
            cache.expire = self.cache_ttl
            self.local_caches[challenge_name] = cache
        return self.local_caches[challenge_name]

    def sync_hub_to_cache(self, erase_local_cache=True):
        """
        Syncs data from Hugging Face Hub to the local cache.

        Args:
            erase_local_cache (bool): Whether to erase the local cache before syncing.
        """
        # Erase the existing local cache if needed
        if erase_local_cache and os.path.exists(self.cache_dir):
            rmtree(self.cache_dir)
            os.makedirs(self.cache_dir, exist_ok=True)

        # Reconstruct the local cache from the downloaded snapshot
        repo_snapshot_path = self._snapshot_repo(erase_cache=True)
        for dirpath, _, filenames in os.walk(repo_snapshot_path):
            relative_dir = os.path.relpath(dirpath, repo_snapshot_path)

            if relative_dir == ".":
                continue  # Skip the root directory

            challenge_name = relative_dir
            cache = self._get_cache(challenge_name)
            for filename in filenames:
                if filename.endswith(".json"):
                    file_path = os.path.join(dirpath, filename)
                    with open(file_path, "r") as file:
                        data = json.load(file)

                    # Use filename (without .json) as the key
                    key = os.path.splitext(filename)[0]
                    cache[key] = data

    def sync_cache_to_hub(self):
        """
        Syncs the local cache to the Hugging Face Hub in batches using `run_as_future`.

        This method ensures:
        1. Records found in the local cache are added to the Hub if not present.
        2. Records in the Hub are updated if they differ from the cache.
        3. Records in the Hub that are not in the cache are left untouched.

        WARNING: This operation may overwrite existing records in the Hub if differences are detected.

        Returns:
            None
        """
        bt.logging.warning("This operation may alter the Hub repository significantly!")

        # Take a snapshot of the Hugging Face Hub repository
        repo_snapshot_path = self._snapshot_repo(erase_cache=False)

        # Step 1: Build a set of records already in the Hub
        hub_records = {}  # {challenge_name: {key: data}}
        for dirpath, _, filenames in os.walk(repo_snapshot_path):
            relative_dir = os.path.relpath(dirpath, repo_snapshot_path)

            if relative_dir == ".":
                continue  # Skip the root directory

            challenge_name = relative_dir
            hub_records[challenge_name] = {}

            for filename in filenames:
                if filename.endswith(".json"):
                    file_path = os.path.join(dirpath, filename)
                    with open(file_path, "r") as file:
                        hub_data = json.load(file)

                    key = os.path.splitext(filename)[0]  # Use filename without ".json"
                    hub_records[challenge_name][key] = hub_data

        # Step 2: Compare the local cache with the Hub and prepare updates
        upload_futures = []
        for challenge_name, cache in self.local_caches.items():
            for key in cache.iterkeys():
                value = cache[key]
                filepath = f"{challenge_name}/{key}.json"

                # Determine whether to add or update
                if (
                    challenge_name not in hub_records
                    or key not in hub_records[challenge_name]
                    or hub_records[challenge_name][key] != value
                ):
                    # Schedule the file upload as a future
                    upload_futures.append(
                        self.hf_api.upload_file(
                            path_or_fileobj=json.dumps(value).encode("utf-8"),
                            path_in_repo=filepath,
                            repo_id=self.hf_repo_id,
                            use_auth_token=True,
                            commit_message=f"Sync record {key} for {challenge_name}",
                            run_as_future=True,  # Non-blocking
                        )
                    )

        # Step 3: Wait for all uploads to complete and handle results
        if upload_futures:
            for future in as_completed(upload_futures):
                try:
                    result = future.result()
                    bt.logging.info(f"Uploaded to Hub successfully: {result.filepath}")
                except Exception as e:
                    bt.logging.error(f"Failed to upload file to Hub: {e}")
        else:
            bt.logging.info("No updates required. Hub is already in sync with the local cache.")

    def _sync_cache_to_hub_periodically(self, interval: int):
        """
        Periodically syncs the local cache to the Hugging Face Hub.

        Args:
            interval (int): Time interval in seconds between consecutive syncs.
        """
        while True:
            try:
                self.sync_cache_to_hub()
                bt.logging.info("Periodic sync to Hugging Face Hub completed successfully.")
            except Exception as e:
                bt.logging.error(f"Error during periodic cache sync: {e}")
            time.sleep(interval)

    def _snapshot_repo(self, erase_cache: bool) -> str:
        """
        Creates a snapshot of the Hugging Face Hub repository in a temporary cache directory.
        """
        hf_cache_dir = os.path.join(self.cache_dir, ".hf_cache/")
        os.makedirs(hf_cache_dir, exist_ok=True)

        # Download the repository snapshot
        return self.hf_api.snapshot_download(
            repo_id=self.hf_repo_id,
            cache_dir=hf_cache_dir,
            force_download=erase_cache,
        )
    
    def update_batch(self, challenge_name: str, records: list[dict]):
        """
        Processes a batch of records, ensuring updates across all storages.

        Args:
            challenge_name (str): The challenge name.
            records (list[dict]): A list of record data dictionaries.
        """
        for record in records:
            try:
                self.update_record(challenge_name, record)
            except ValueError as e:
                bt.logging.error(f"Invalid record skipped: {e}")

    def update_record(self, data: dict, async_update=True):
        """
        Updates or inserts a record across all storages: centralized, local, and decentralized.

        Args:
            data (dict): The record data. Must include "encrypted_commit" and "challenge_name".
            async_update (bool): Whether to process the update asynchronously.
        """
        # Validate required fields in data
        if "encrypted_commit" not in data:
            bt.logging.error("Data must include 'encrypted_commit' as a unique identifier.")
            return
        if "challenge_name" not in data:
            bt.logging.error("Data must include 'challenge_name'.")
            return

        if async_update:
            # Enqueue the task for the background thread
            self.storage_queue.put(data)
            bt.logging.info(f"Record with encrypted_commit={data['encrypted_commit']} queued for storage.")
            return

        # Process the record immediately
        challenge_name = data["challenge_name"]
        encrypted_commit = data["encrypted_commit"]

        # Track success for all storage operations
        success = True
        errors = []

        # Step 1: Upsert in Local Cache
        try:
            cache = self._get_cache(challenge_name)
            cache[encrypted_commit] = data  # Upserts the record in the local cache
        except Exception as e:
            success = False
            errors.append(f"Local cache update failed: {e}")

        # Step 2: Upsert in Centralized Storage
        try:
            response = requests.post(
                self.centralized_storage_url,
                json=data,
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            success = False
            errors.append(f"Centralized storage update failed: {e}")

        # Step 3: Sync to Decentralized Storage (Hugging Face Hub)
        try:
            filepath = f"{challenge_name}/{encrypted_commit}.json"
            with cache.read(encrypted_commit) as file_handle:
                self.hf_api.upload_file(
                    path_or_fileobj=file_handle,
                    path_in_repo=filepath,
                    repo_id=self.hf_repo_id,
                    use_auth_token=True,
                )
        except KeyError:
            success = False
            errors.append(f"Record with key {encrypted_commit} not found in local cache for decentralized sync.")
        except Exception as e:
            success = False
            errors.append(f"Decentralized storage sync failed: {e}")

        # Final Logging
        if success:
            bt.logging.info(f"Record successfully updated across all storages: {encrypted_commit}")
        else:
            bt.logging.error(f"Failed to update record {encrypted_commit} across all storages. Errors: {errors}")

    def update_batch(self, records: list[dict], async_update=True):
        """
        Processes a batch of records efficiently across all storages.

        Args:
            records (list[dict]): A list of record data dictionaries.
            async_update (bool): Whether to process the batch asynchronously.
        """
        if async_update:
            # Enqueue the entire batch for the background thread
            self.storage_queue.put(records)
            bt.logging.info(f"Batch of size {len(records)} queued for storage.")
            return
        
        # Process each record synchronously
        with ThreadPoolExecutor(max_workers=5) as executor:
            executor.map(lambda record: self.update_record(record, async_update=False), records)

    def _process_storage_queue(self):
        """
        Background thread function to process storage tasks from the queue.
        Handles both single records and batches.
        """
        while True:
            try:
                data = self.storage_queue.get(timeout=1)  # Wait for a task
                if isinstance(data, list):
                    self.update_batch(data, async_update=False)
                elif isinstance(data, dict):
                    self.update_record(data, async_update=False)
                else:
                    bt.logging.warning("Unknown submission type in storage queue.")
                self.storage_queue.task_done()
            except Empty:
                pass  # No tasks in the queue, keep looping
            time.sleep(1)  # Prevent the thread from consuming too much CPU