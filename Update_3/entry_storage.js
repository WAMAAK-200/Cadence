const ENTRY_API_BASE = 'http://127.0.0.1:8000';
const ENTRY_SESSION_KEY = 'smartdiary_session_token';
const ENTRY_EXPIRED_KEY = 'smartdiary_session_expired';
const ENTRY_LOCAL_KEY = 'diary_entries';

const SAMPLE_DIARY_ENTRIES = [
    { id: 1, date: 'November 14, 2026', title: 'Frontend Redesign', mood: '😊 Happy', text: 'Today we cleaned up the Smart Diary layout to make it feel much more open and distraction-free.', tags: ['#frontend'] },
    { id: 2, date: 'November 12, 2026', title: 'Afternoon Walk', mood: '😌 Calm', text: 'Took a break around Durham this afternoon before catching up with the backend team.', tags: ['#walk'] }
];

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

function getGuestEntries() {
    const stored = localStorage.getItem(ENTRY_LOCAL_KEY);
    if (stored === null) {
        localStorage.setItem(ENTRY_LOCAL_KEY, JSON.stringify(SAMPLE_DIARY_ENTRIES));
        return SAMPLE_DIARY_ENTRIES.map(entry => ({ ...entry, tags: [...entry.tags] }));
    }
    try {
        const parsed = JSON.parse(stored);
        const entries = Array.isArray(parsed)
            ? parsed.map(normalizeGuestEntry).filter(Boolean)
            : [];
        localStorage.setItem(ENTRY_LOCAL_KEY, JSON.stringify(entries));
        return entries;
    } catch (error) {
        localStorage.setItem(ENTRY_LOCAL_KEY, '[]');
        return [];
    }
}

function saveGuestEntries(entries) {
    localStorage.setItem(ENTRY_LOCAL_KEY, JSON.stringify(entries));
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
    return getGuestEntries();
}

async function createDiaryEntry(entry) {
    if (getEntrySessionToken()) {
        const result = await accountEntriesRequest('/entries', {
            method: 'POST',
            body: JSON.stringify(entry)
        });
        return result.entry;
    }
    const entries = getGuestEntries();
    entries.unshift(normalizeGuestEntry(entry, 0));
    saveGuestEntries(entries);
    return entries[0];
}

async function updateDiaryEntry(entryId, changes) {
    if (getEntrySessionToken()) {
        return accountEntriesRequest(`/entries/${encodeURIComponent(entryId)}`, {
            method: 'PUT',
            body: JSON.stringify(changes)
        });
    }
    const entries = getGuestEntries().map(entry => entry.id === entryId
        ? normalizeGuestEntry({ ...entry, ...changes }, 0)
        : entry);
    saveGuestEntries(entries);
}

async function deleteDiaryEntry(entryId) {
    if (getEntrySessionToken()) {
        return accountEntriesRequest(`/entries/${encodeURIComponent(entryId)}`, { method: 'DELETE' });
    }
    saveGuestEntries(getGuestEntries().filter(entry => entry.id !== entryId));
}

// ---- Mood display helpers (shared by Today, All Entries, Calendar, Insights) ----
// Moods are stored as text: "Happy" now, "😊 Happy" in older entries. These give the
// plain name, a key for the CSS mood colour (data-mood), and a ready-made label.
const MOOD_KEYS = ['happy', 'calm', 'reflective', 'stressed'];

function moodName(mood) {
    return String(mood || '').replace(/[^\p{L}\s-]/gu, '').trim();
}

function moodKey(mood) {
    const name = moodName(mood).toLowerCase();
    return MOOD_KEYS.includes(name) ? name : '';
}

function renderMood(element, mood) {
    element.replaceChildren();
    const key = moodKey(mood);
    if (key) {
        element.dataset.mood = key;
        const note = document.createElement('span');
        note.className = 'note';
        note.setAttribute('aria-hidden', 'true');
        element.appendChild(note);
    }
    element.appendChild(document.createTextNode(moodName(mood)));
}
