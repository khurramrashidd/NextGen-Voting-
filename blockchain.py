import hashlib
import json
from datetime import datetime

class BlockchainUtils:
    @staticmethod
    def calculate_hash(index, previous_hash, candidate_id, timestamp, nonce):
        """
        Creates a SHA-256 hash of the block content.
        """
        # Ensure consistent string representation
        value = str(index) + str(previous_hash) + str(candidate_id) + str(timestamp) + str(nonce)
        return hashlib.sha256(value.encode('utf-8')).hexdigest()

    @staticmethod
    def generate_receipt(voter_id, candidate_id, timestamp):
        """
        Generates a unique receipt token for the voter.
        """
        raw = f"{voter_id}:{candidate_id}:{timestamp}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def verify_chain(votes):
        """
        Iterates through vote records to verify integrity.
        Returns (True, "Valid") or (False, "Error Message").
        """
        if not votes:
            return True, "Chain Empty"

        for i in range(1, len(votes)):
            current = votes[i]
            previous = votes[i-1]

            # 1. Check if previous_hash matches the previous block's hash
            if current.previous_hash != previous.block_hash:
                return False, f"Broken Link at Block {current.id}: Previous hash mismatch."

            # 2. Re-calculate hash to check for data tampering
            # Note: We reconstruct the hash using the stored data
            recalc_hash = BlockchainUtils.calculate_hash(
                current.id,
                current.previous_hash,
                current.candidate_id,
                current.timestamp,
                current.nonce
            )
            
            if current.block_hash != recalc_hash:
                return False, f"Data Tampering detected at Block {current.id}"

        return True, "Blockchain Integrity Verified. No tampering detected."