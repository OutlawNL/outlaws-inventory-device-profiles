"""Shared SSH host identity verification, before client authentication."""
import base64
import hashlib
import hmac

import paramiko


class PinnedHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    def __init__(self, fingerprint):
        self.fingerprint = fingerprint.strip()

    def missing_host_key(self, client, hostname, key):
        expected = self.fingerprint
        if expected.startswith("SHA256:"):
            actual = "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
            expected = expected.rstrip("=")
        else:
            expected = expected.removeprefix("MD5:").replace(":", "").lower()
            actual = key.get_fingerprint().hex()
        if not hmac.compare_digest(expected, actual):
            raise paramiko.SSHException(f"SSH host fingerprint mismatch for {hostname}.")


def ssh_client(profile):
    client = paramiko.SSHClient()
    fingerprint = str(profile["known_host_fingerprint"] or "") if "known_host_fingerprint" in profile.keys() else ""
    if fingerprint:
        # Deliberately use the policy for EVERY supplied key, including hosts
        # that might otherwise match an unrelated system known_hosts entry.
        client.set_missing_host_key_policy(PinnedHostKeyPolicy(fingerprint))
    else:
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    return client
