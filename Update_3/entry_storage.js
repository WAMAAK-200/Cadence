const ENTRY_API_BASE = 'http://127.0.0.1:8000';
const ENTRY_SESSION_KEY = 'smartdiary_session_token';
const ENTRY_EXPIRED_KEY = 'smartdiary_session_expired';
const ENTRY_LOCAL_KEY = 'diary_entries';
const GUEST_CRYPTO_DB = 'smartdiary_guest_crypto';
const GUEST_CRYPTO_KEY_ID = 'guest-entry-key';
const GUEST_ENCRYPTED_PREFIX = 'sdenc:v1:';

function getEntrySessionToken() {
    if (sessionStorage.getItem(ENTRY_EXPIRED_KEY) === 'true') return 'expired';
    return sessionStorage.getItem(ENTRY_SESSION_KEY);
}

function normalizeGuestEntry(entry, index) {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return null;
    return {
        id: Number.isSafeInteger(entry.id) ? entry.id : Date.now() + index,
        date: typeof entry.date === 'string' ? entry.date.slice(0, 40) : '',
        title: typeof entry.title === 'string' ? entry.title.slice(0, 120) : 'Untitled Entry',
        mood: typeof entry.mood === 'string' ? entry.mood.slice(0, 40) : '',
        text: typeof entry.text === 'string' ? entry.text.slice(0, 10000) : '',
        tags: Array.isArray(entry.tags)
            ? entry.tags.filter(tag => typeof tag === 'string').slice(0, 20).map(tag => tag.slice(0, 30))
            : []
    };
}

function openGuestCryptoDb() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(GUEST_CRYPTO_DB, 1);
        request.onupgradeneeded = () => request.result.createObjectStore('keys');
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function getGuestEncryptionKey() {
    if (!window.crypto || !crypto.subtle || !window.indexedDB) {
        throw new Error('This browser cannot securely encrypt guest entries.');
    }
    const database = await openGuestCryptoDb();
    try {
        const existingKey = await new Promise((resolve, reject) => {
            const request = database.transaction('keys', 'readonly').objectStore('keys').get(GUEST_CRYPTO_KEY_ID);
            request.onsuccess = () => resolve(request.result || null);
            request.onerror = () => reject(request.error);
        });
        if (existingKey) return existingKey;

        const generatedKey = await crypto.subtle.generateKey(
            { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']
        );
        return await new Promise((resolve, reject) => {
            const transaction = database.transaction('keys', 'readwrite');
            const store = transaction.objectStore('keys');
            let selectedKey = generatedKey;
            const request = store.get(GUEST_CRYPTO_KEY_ID);
            request.onsuccess = () => {
                if (request.result) selectedKey = request.result;
                else store.put(generatedKey, GUEST_CRYPTO_KEY_ID);
            };
            transaction.oncomplete = () => resolve(selectedKey);
            transaction.onerror = () => reject(transaction.error);
            transaction.onabort = () => reject(transaction.error || new Error('Could not store the encryption key.'));
        });
    } finally {
        database.close();
    }
}

function toBase64(bytes) {
    let binary = '';
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    return btoa(binary);
}

function fromBase64(value) {
    return Uint8Array.from(atob(value), character => character.charCodeAt(0));
}

async function encryptGuestEntries(entries) {
    const key = await getGuestEncryptionKey();
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const cleartext = new TextEncoder().encode(JSON.stringify(entries));
    const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, cleartext);
    return `${GUEST_ENCRYPTED_PREFIX}${toBase64(iv)}:${toBase64(new Uint8Array(ciphertext))}`;
}

async function decryptGuestEntries(stored) {
    const parts = stored.slice(GUEST_ENCRYPTED_PREFIX.length).split(':');
    if (parts.length !== 2) throw new Error('Encrypted guest entries are malformed.');
    const key = await getGuestEncryptionKey();
    const cleartext = await crypto.subtle.decrypt(
        { name: 'AES-GCM', iv: fromBase64(parts[0]) }, key, fromBase64(parts[1])
    );
    return JSON.parse(new TextDecoder().decode(cleartext));
}

async function getGuestEntries() {
    const stored = localStorage.getItem(ENTRY_LOCAL_KEY);
    if (stored === null) return [];
    try {
        const parsed = stored.startsWith(GUEST_ENCRYPTED_PREFIX)
            ? await decryptGuestEntries(stored)
            : JSON.parse(stored);
        if (!Array.isArray(parsed)) throw new Error('Saved guest entries are not a list.');
        if (parsed.some(entry => !entry || typeof entry !== 'object' || Array.isArray(entry))) {
            throw new Error('A saved guest entry has an unexpected format.');
        }
        if (!stored.startsWith(GUEST_ENCRYPTED_PREFIX)) await saveGuestEntries(parsed);
        return parsed;
    } catch (error) {
        throw new Error('Guest entries could not be decrypted or read. The browser data has been kept.');
    }
}

async function readGuestEntriesForMigration() {
    try {
        return await getGuestEntries();
    } catch (error) {
        throw new Error(`${error.message} Login was stopped and the browser data was kept.`);
    }
}

async function importGuestEntriesToAccount(token, entries) {
    if (!Array.isArray(entries)) {
        throw new Error('Guest entries could not be read as a list. They remain in the browser.');
    }
    if (entries.length === 0) return { imported: 0 };
    const maxBatchBytes = 4 * 1024 * 1024;
    const encoder = new TextEncoder();
    const batches = [];
    let batch = [];
    let batchBytes = 64;

    for (const entry of entries) {
        const cleanEntry = {
            id: entry.id,
            date: entry.date,
            title: entry.title,
            mood: entry.mood,
            text: entry.text,
            tags: entry.tags
        };
        const entryBytes = encoder.encode(JSON.stringify(cleanEntry)).byteLength + 1;
        if (entryBytes + 64 > maxBatchBytes) {
            throw new Error('A guest entry is too large to import. It remains in the browser.');
        }
        if (batch.length && batchBytes + entryBytes > maxBatchBytes) {
            batches.push(batch);
            batch = [];
            batchBytes = 64;
        }
        batch.push(cleanEntry);
        batchBytes += entryBytes;
    }
    if (batch.length) batches.push(batch);

    let imported = 0;
    let offset = 0;
    for (const entriesBatch of batches) {
        let response;
        try {
            response = await fetch(`${ENTRY_API_BASE}/entries/import`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ entries: entriesBatch, offset })
            });
        } catch (error) {
            throw new Error('Could not reach the diary server; guest entries were kept in the browser.');
        }
        const result = await response.json();
        if (!response.ok) {
            throw new Error(`${result.message || 'Guest entry import failed.'} Guest entries remain in the browser.`);
        }
        imported += result.imported || 0;
        offset += entriesBatch.length;
    }
    return { imported };
}

async function saveGuestEntries(entries) {
    localStorage.setItem(ENTRY_LOCAL_KEY, await encryptGuestEntries(entries));
}

async function accountEntriesRequest(path, options = {}) {
    const token = getEntrySessionToken();
    if (token === 'expired') throw new Error('Your account session expired. Sign in again to access account entries.');
    if (!token) throw new Error('Please log in to access account entries.');
    const headers = {
        'Authorization': `Bearer ${token}`,
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers
    };
    let response;
    try {
        response = await fetch(`${ENTRY_API_BASE}${path}`, { ...options, headers });
    } catch (error) {
        throw new Error('Could not reach the diary server. Start it with: python security.py');
    }
    const result = await response.json();
    if (response.status === 401) {
        sessionStorage.removeItem(ENTRY_SESSION_KEY);
        sessionStorage.setItem(ENTRY_EXPIRED_KEY, 'true');
        if (window.updateAccountNavigation) window.updateAccountNavigation();
        throw new Error(result.message || 'Your session expired. Please log in again.');
    }
    if (!response.ok) throw new Error(result.message || 'The diary request failed.');
    return result;
}

async function loadDiaryEntries() {
    if (getEntrySessionToken()) {
        const result = await accountEntriesRequest('/entries');
        return Array.isArray(result.entries) ? result.entries : [];
    }
    return await getGuestEntries();
}

async function createDiaryEntry(entry) {
    if (getEntrySessionToken()) {
        const result = await accountEntriesRequest('/entries', {
            method: 'POST',
            body: JSON.stringify(entry)
        });
        return result.entry;
    }
    const entries = await getGuestEntries();
    entries.unshift(normalizeGuestEntry(entry, 0));
    await saveGuestEntries(entries);
    return entries[0];
}

async function updateDiaryEntry(entryId, changes) {
    if (getEntrySessionToken()) {
        return accountEntriesRequest(`/entries/${encodeURIComponent(entryId)}`, {
            method: 'PUT',
            body: JSON.stringify(changes)
        });
    }
    const entries = (await getGuestEntries()).map(entry => entry.id === entryId
        ? normalizeGuestEntry({ ...entry, ...changes }, 0)
        : entry);
    await saveGuestEntries(entries);
}

async function deleteDiaryEntry(entryId) {
    if (getEntrySessionToken()) {
        return accountEntriesRequest(`/entries/${encodeURIComponent(entryId)}`, { method: 'DELETE' });
    }
    await saveGuestEntries((await getGuestEntries()).filter(entry => entry.id !== entryId));
}
