"""Password hashing con bcrypt.

bcrypt limita il plaintext a 72 byte: chiamate con stringhe più lunghe
sono troncate dalla libreria. Per i casi d'uso del progetto (password
utente) il limite non è una preoccupazione.
"""

import bcrypt


def hash_password(plain: str) -> str:
    """Hash bcrypt della password (cost factor default = 12).

    Ritorna stringa UTF-8 idiomatica per inserire in colonna `TEXT` o
    `VARCHAR`.
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica se `plain` corrisponde all'hash `hashed`.

    Constant-time comparison fornito da bcrypt. Ritorna False se
    l'hash è malformato (non solleva eccezioni).
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
