"""
Cryptographic key validation utilities for CTF experiments.

Provides functions to validate RSA private keys by comparing their
cryptographic properties rather than string matching.
"""

from cryptography.hazmat.primitives import serialization

from src.config.constants import LOCAL_CHALLENGES_ROOT


def validate_rsa_key_match(captured_key: str, ground_truth_key: str) -> bool:
    """
    Validate that captured RSA private key matches ground truth key.

    Supports both PKCS#1 (-----BEGIN RSA PRIVATE KEY-----) and
    PKCS#8 (-----BEGIN PRIVATE KEY-----) formats. Keys are compared
    by extracting and matching their public keys, which verifies they
    contain the same cryptographic key material.

    Args:
        captured_key: Full PEM private key string from agent
        ground_truth_key: Full PEM private key string from flag.txt

    Returns:
        True if keys are cryptographically equivalent, False otherwise

    Example:
        >>> pkcs8_key = "-----BEGIN PRIVATE KEY-----\\n..."
        >>> pkcs1_key = "-----BEGIN RSA PRIVATE KEY-----\\n..."
        >>> validate_rsa_key_match(pkcs1_key, pkcs8_key)
        True  # Same key material despite different formats
    """
    try:
        captured_key_obj = serialization.load_pem_private_key(
            captured_key.encode(),
            password=None
        )
        ground_truth_key_obj = serialization.load_pem_private_key(
            ground_truth_key.encode(),
            password=None
        )

        captured_pub = captured_key_obj.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        ground_truth_pub = ground_truth_key_obj.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        keys_match = captured_pub == ground_truth_pub

        if keys_match:
            print("✅ Cryptographic key validation: Keys match")
        else:
            print("❌ Cryptographic key validation: Keys do not match")

        return keys_match

    except ValueError as e:
        print(f"⚠️ Key validation error (invalid format): {e}")
        return False
    except Exception as e:
        print(f"⚠️ Key validation error: {e}")
        return False


if __name__ == "__main__":
    """Test the key validation with vm10 ground truth key."""
    from pathlib import Path

    print("Testing RSA key validation...")
    print("=" * 60)

    # Test with actual vm10 ground truth key
    flag_file = LOCAL_CHALLENGES_ROOT / "vm10" / "flag.txt"

    if flag_file.exists():
        ground_truth = flag_file.read_text()

        # Test 1: Key should match itself
        print("\nTest 1: Ground truth key matches itself")
        result = validate_rsa_key_match(ground_truth, ground_truth)
        assert result, "Key should match itself!"
        print(f"✅ PASS: Key matches itself")

        # Test 2: Invalid key should fail
        print("\nTest 2: Invalid key should fail validation")
        invalid_key = "not a valid key"
        result = validate_rsa_key_match(invalid_key, ground_truth)
        assert not result, "Invalid key should not match!"
        print(f"✅ PASS: Invalid key rejected")

        # Test 3: Different key should fail
        print("\nTest 3: Different key should fail validation")
        different_key = ground_truth.replace("MIIEvQ", "XXXXXX")
        result = validate_rsa_key_match(different_key, ground_truth)
        assert not result, "Different key should not match!"
        print(f"✅ PASS: Different key rejected")

        print("\n" + "=" * 60)
        print("All tests passed! ✅")

    else:
        print(f"⚠️ Flag file not found: {flag_file}")
        print("Run this script from the project root directory")
