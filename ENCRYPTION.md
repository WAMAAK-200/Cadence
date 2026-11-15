# Data encryption

The app encrypts account email addresses and diary entry contents before writing them to SQLite. It also encrypts guest diary entries before writing them to browser `localStorage`; the browser key is a non-extractable Web Crypto key kept in IndexedDB for this site.

The server creates `.smartdiary.key` with owner-only permissions on first startup. Keep this key file safe and include it in a secure backup alongside the database. Without it, encrypted account data cannot be read. Do not commit or share the key. The app migrates existing plaintext SQLite emails and entries the first time it starts with encryption enabled.

Clearing this site's IndexedDB key while leaving its encrypted `localStorage` entries will make those guest entries unreadable. Clearing site data removes both. This protects a copied database or `localStorage` value without its key; it does not protect data from someone who can run code in the app's origin or access the server and its key.
