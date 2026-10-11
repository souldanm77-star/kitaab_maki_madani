#!/usr/bin/env python3
"""Génère une paire de clés SSH ed25519 au format OpenSSH (sans ssh-keygen)."""
import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

HOME = os.path.expanduser("~")
SSH_DIR = os.path.join(HOME, ".ssh")
PRIV = os.path.join(SSH_DIR, "id_ed25519")
PUB = os.path.join(SSH_DIR, "id_ed25519.pub")

os.makedirs(SSH_DIR, mode=0o700, exist_ok=True)

# Génère la clé
key = Ed25519PrivateKey.generate()

# Clé privée — format OpenSSH
pem_priv = key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.OpenSSH,
    encryption_algorithm=serialization.NoEncryption(),
)
with open(PRIV, "wb") as f:
    f.write(pem_priv)
os.chmod(PRIV, 0o600)

# Clé publique — format OpenSSH "ssh-ed25519 AAAA... commentaire"
raw_pub = key.public_key().public_bytes(
    encoding=serialization.Encoding.OpenSSH,
    format=serialization.PublicFormat.OpenSSH,
)
pub_line = raw_pub.decode() + " souldanm77-star@my-project\n"
with open(PUB, "w") as f:
    f.write(pub_line)
os.chmod(PUB, 0o644)

print("Clé privée :", PRIV)
print("Clé publique :", PUB)
print("---")
print(pub_line.strip())
