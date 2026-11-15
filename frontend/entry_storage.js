/**
 * Cadence / Smart Diary - Unified Storage & API Client Layer
 * Handles guest (localStorage) and authenticated (SQLite server) storage,
 * as well as AI extraction, pattern insight generation, exam tracking, and reporting.
 */

// Talk to the server that served this page (so localhost vs 127.0.0.1, or a test port, all work).
// Falls back to the default dev server when the file is opened directly from disk.
const ENTRY_API_BASE = /^https?:$/.test(location.protocol) ? location.origin : 'http://127.0.0.1:8000';
const ENTRY_SESSION_KEY = 'smartdiary_session_token';
const ENTRY_EXPIRED_KEY = 'smartdiary_session_expired';
const ENTRY_LOCAL_KEY = 'diary_entries';
const ENTRY_USER_PROFILE_KEY = 'smartdiary_user_profile';
const EXAM_LOCAL_KEY = 'smartdiary_exams';
// Guest entries are encrypted with a non-extractable Web Crypto key stored in
// IndexedDB for this origin (see ENCRYPTION.md).
const GUEST_CRYPTO_DB = 'smartdiary_guest_crypto';
const GUEST_CRYPTO_KEY_ID = 'guest-entry-key';
const GUEST_ENCRYPTED_PREFIX = 'sdenc:v1:';

const SAMPLE_DIARY_ENTRIES = [
    {
        id: 1,
        date: '2026-11-14',
        title: 'Revision & Music Prototype',
        mood: 'happy',
        text: 'Proper good day! We worked on the generative music engine in Durham and finished the exam revision tracker. Feeling buzzing about the demo.',
        tags: ['#revision', '#music', '#durham'],
        sleepHours: 8.0,
        sleepQuality: 'good',
        stress: 3,
        fatigue: 3,
        studyHours: 5.5,
        workHours: 0,
        summary: 'Focused revision session and completed the music composition engine.',
        dialectTerms: [{ heard: 'proper good', meaning: 'very good' }, { heard: 'buzzing', meaning: 'excited / joyful' }],
        safety: { level: 'none', reason: null },
        spokenReply: 'Brilliant work today. A balanced day like this sets you up nicely.'
    },
    {
        id: 2,
        date: '2026-11-13',
        title: 'Long Library Shift',
        mood: 'reflective',
        text: 'Spent the whole afternoon at Bill Bryson library. Proper knackered by 6pm, but got through the core reading list.',
        tags: ['#library', '#study'],
        sleepHours: 6.0,
        sleepQuality: 'ok',
        stress: 6,
        fatigue: 7,
        studyHours: 6.0,
        workHours: 0,
        summary: 'Studied reading list at library with moderate fatigue.',
        dialectTerms: [{ heard: 'proper knackered', meaning: 'exhausted' }],
        safety: { level: 'none', reason: null },
        spokenReply: 'Good progress on your reading list. Make sure you get some restful sleep tonight.'
    },
    {
        id: 3,
        date: '2026-11-12',
        title: 'Walk Along the River Wear',
        mood: 'calm',
        text: 'Canny quiet morning. Took a breather along the river before meeting the study group. Helped keep stress down.',
        tags: ['#walk', '#river', '#break'],
        sleepHours: 7.5,
        sleepQuality: 'good',
        stress: 2,
        fatigue: 3,
        studyHours: 3.0,
        workHours: 0,
        summary: 'Relaxing walk by the river, low stress baseline.',
        dialectTerms: [{ heard: 'canny quiet', meaning: 'pleasant and quiet' }],
        safety: { level: 'none', reason: null },
        spokenReply: 'Taking breaks like this is essential for keeping stress low.'
    },
    {
        id: 4,
        date: '2026-11-10',
        title: 'Deadline Revision',
        mood: 'stressed',
        text: 'Late night finishing the assignment. Felt radge and stressed trying to meet the submission deadline.',
        tags: ['#deadline', '#stressed'],
        sleepHours: 4.5,
        sleepQuality: 'poor',
        stress: 9,
        fatigue: 8,
        studyHours: 7.5,
        workHours: 0,
        summary: 'High workload and short sleep before deadline.',
        dialectTerms: [{ heard: 'radge', meaning: 'frustrated / agitated' }],
        safety: { level: 'none', reason: null },
        spokenReply: 'Late nights are tough. Be kind to yourself today and try to catch up on rest.'
    }
];

// Seeded examples are not the user's data. They are flagged so pages can label them
// and keep them out of insights, the week view and the weekly composition.
// Older stored copies have no flag, so they are also recognised by id + title.
function isSampleEntry(entry) {
    if (!entry || typeof entry !== 'object') return false;
    if (entry.isSample === true || entry.sample === true) return true;
    return SAMPLE_DIARY_ENTRIES.some(s => s.id === entry.id && s.title === entry.title);
}

function personalEntries(entries) {
    return (Array.isArray(entries) ? entries : []).filter(e => !isSampleEntry(e));
}

const SAMPLE_EXAMS = [
    {
        id: 1,
        subject: 'Algorithms & Data Structures',
        date: '2026-11-28',
        targetHours: 20.0,
        completedHours: 11.5,
        notes: 'Focus on dynamic programming and graph traversals.'
    },
    {
        id: 2,
        subject: 'Software Engineering Practice',
        date: '2026-12-05',
        targetHours: 15.0,
        completedHours: 6.0,
        notes: 'Review design patterns and testing strategies.'
    }
];

// ---- Auth & Session Helpers ----

function getEntrySessionToken() {
    if (sessionStorage.getItem(ENTRY_EXPIRED_KEY) === 'true') return 'expired';
    return sessionStorage.getItem(ENTRY_SESSION_KEY);
}

function setEntrySessionToken(token, userProfile = null) {
    sessionStorage.removeItem(ENTRY_EXPIRED_KEY);
    sessionStorage.setItem(ENTRY_SESSION_KEY, token);
    if (userProfile) {
        localStorage.setItem(ENTRY_USER_PROFILE_KEY, JSON.stringify(userProfile));
    }
}

function clearEntrySession() {
    sessionStorage.removeItem(ENTRY_SESSION_KEY);
    sessionStorage.removeItem(ENTRY_EXPIRED_KEY);
    localStorage.removeItem(ENTRY_USER_PROFILE_KEY);
}

function getStoredUserMode() {
    const profile = getStoredUserProfile();
    if (profile && profile.mode) return profile.mode;
    return localStorage.getItem('smartdiary_user_mode') || 'student';
}

function setStoredUserMode(mode) {
    if (['student', 'employed', 'unemployed'].includes(mode)) {
        localStorage.setItem('smartdiary_user_mode', mode);
        const profile = getStoredUserProfile();
        if (profile) {
            profile.mode = mode;
            localStorage.setItem(ENTRY_USER_PROFILE_KEY, JSON.stringify(profile));
        }
        if (getEntrySessionToken() && getEntrySessionToken() !== 'expired') {
            accountEntriesRequest('/user-profile', {
                method: 'POST',
                body: JSON.stringify({ mode })
            }).catch(() => {});
        }
    }
}

function getStoredUserProfile() {
    try {
        const raw = localStorage.getItem(ENTRY_USER_PROFILE_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch (e) {
        return null;
    }
}

// ---- Data Normalization ----

function normalizeEntry(entry, index = 0) {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return null;

    let dateVal = entry.date;
    if (!dateVal || typeof dateVal !== 'string') {
        dateVal = new Date().toISOString().split('T')[0];
    }

    return {
        id: Number.isSafeInteger(entry.id) ? entry.id : Date.now() + index,
        date: String(dateVal).slice(0, 40),
        title: typeof entry.title === 'string' && entry.title.trim() ? entry.title.slice(0, 120) : 'Diary Entry',
        mood: typeof entry.mood === 'string' ? entry.mood.slice(0, 40) : (typeof entry.mood === 'number' ? String(entry.mood) : 'calm'),
        text: typeof entry.text === 'string' ? entry.text.slice(0, 10000) : '',
        tags: Array.isArray(entry.tags)
            ? entry.tags.filter(t => typeof t === 'string').slice(0, 20).map(t => t.slice(0, 30))
            : [],
        sleepHours: typeof entry.sleepHours === 'number' ? entry.sleepHours : (parseFloat(entry.sleepHours) || null),
        sleepQuality: ['poor', 'ok', 'good'].includes(entry.sleepQuality) ? entry.sleepQuality : null,
        stress: typeof entry.stress === 'number' ? entry.stress : (parseInt(entry.stress, 10) || null),
        fatigue: typeof entry.fatigue === 'number' ? entry.fatigue : (parseInt(entry.fatigue, 10) || null),
        studyHours: typeof entry.studyHours === 'number' ? entry.studyHours : (parseFloat(entry.studyHours) || null),
        workHours: typeof entry.workHours === 'number' ? entry.workHours : (parseFloat(entry.workHours) || null),
        summary: typeof entry.summary === 'string' ? entry.summary : '',
        dialectTerms: Array.isArray(entry.dialectTerms) ? entry.dialectTerms : [],
        safety: (entry.safety && typeof entry.safety === 'object') ? entry.safety : { level: 'none', reason: null },
        spokenReply: typeof entry.spokenReply === 'string' ? entry.spokenReply : '',
        isSample: isSampleEntry(entry)
    };
}

// ---- Guest Storage (encrypted at rest) ----

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
    if (stored === null) {
        const samples = SAMPLE_DIARY_ENTRIES.map(e => ({ ...e, tags: [...e.tags], isSample: true }));
        await saveGuestEntries(samples);
        return samples;
    }
    try {
        const parsed = stored.startsWith(GUEST_ENCRYPTED_PREFIX)
            ? await decryptGuestEntries(stored)
            : JSON.parse(stored);
        const entries = Array.isArray(parsed)
            ? parsed.map((entry, index) => normalizeEntry(entry, index)).filter(Boolean)
            : [];
        // Upgrade legacy plaintext guest entries to the encrypted format.
        if (!stored.startsWith(GUEST_ENCRYPTED_PREFIX)) await saveGuestEntries(entries);
        return entries;
    } catch (error) {
        // Never overwrite data that could not be read: the key may return later.
        throw new Error('Guest entries could not be decrypted or read. The browser data has been kept.');
    }
}

async function saveGuestEntries(entries) {
    localStorage.setItem(ENTRY_LOCAL_KEY, await encryptGuestEntries(entries));
}

async function readGuestEntriesForMigration() {
    try {
        // Seeded demo entries are not the user's data, so never import them.
        return (await getGuestEntries()).filter(entry => entry.isSample !== true);
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
            tags: entry.tags,
            sleepHours: entry.sleepHours,
            sleepQuality: entry.sleepQuality,
            stress: entry.stress,
            fatigue: entry.fatigue,
            studyHours: entry.studyHours,
            workHours: entry.workHours,
            summary: entry.summary,
            dialectTerms: entry.dialectTerms,
            safety: entry.safety,
            spokenReply: entry.spokenReply,
            mode: entry.mode
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
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(`${result.message || 'Guest entry import failed.'} Guest entries remain in the browser.`);
        }
        imported += result.imported || 0;
        offset += entriesBatch.length;
    }
    return { imported };
}

// ---- API Request Wrapper ----

async function accountEntriesRequest(path, options = {}) {
    const token = getEntrySessionToken();
    if (token === 'expired') throw new Error('Your account session expired. Sign in again.');
    if (!token && !path.startsWith('/api/')) throw new Error('Please log in.');

    const headers = {
        ...(token && token !== 'expired' ? { 'Authorization': `Bearer ${token}` } : {}),
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers
    };

    let response;
    try {
        response = await fetch(`${ENTRY_API_BASE}${path}`, { ...options, headers });
    } catch (error) {
        throw new Error('Could not reach the diary backend server.');
    }

    const result = await response.json().catch(() => ({}));

    if (response.status === 401) {
        sessionStorage.removeItem(ENTRY_SESSION_KEY);
        sessionStorage.setItem(ENTRY_EXPIRED_KEY, 'true');
        throw new Error(result.message || 'Session expired. Please log in again.');
    }

    if (!response.ok) {
        throw new Error(result.message || `Request failed with status ${response.status}`);
    }

    return result;
}

// ---- Diary Entries CRUD ----

async function loadDiaryEntries() {
    const token = getEntrySessionToken();
    if (token && token !== 'expired') {
        try {
            const result = await accountEntriesRequest('/entries');
            if (Array.isArray(result.entries)) {
                return result.entries.map((e, idx) => normalizeEntry(e, idx)).filter(Boolean);
            }
        } catch (e) {
            console.warn('Falling back to guest entries due to API error:', e.message);
        }
    }
    return await getGuestEntries();
}

async function createDiaryEntry(entry) {
    const normalized = normalizeEntry(entry, 0);
    const token = getEntrySessionToken();
    let accountError = null;
    if (token && token !== 'expired') {
        try {
            const result = await accountEntriesRequest('/entries', {
                method: 'POST',
                body: JSON.stringify(normalized)
            });
            if (result.entry) return normalizeEntry(result.entry, 0);
        } catch (e) {
            console.warn('Falling back to saving locally:', e.message);
            accountError = e.message;
        }
    }
    const entries = await getGuestEntries();
    entries.unshift(normalized);
    await saveGuestEntries(entries);
    // Tell the caller when an account save fell back to this device, so the UI can say so honestly.
    return accountError ? { ...normalized, savedLocally: true, accountError } : normalized;
}

async function updateDiaryEntry(entryId, changes) {
    const token = getEntrySessionToken();
    if (token && token !== 'expired') {
        try {
            await accountEntriesRequest(`/entries/${encodeURIComponent(entryId)}`, {
                method: 'PUT',
                body: JSON.stringify(changes)
            });
            return;
        } catch (e) {
            console.warn('API update failed, updating local:', e.message);
        }
    }
    const entries = (await getGuestEntries()).map(e => e.id === entryId ? normalizeEntry({ ...e, ...changes }) : e);
    await saveGuestEntries(entries);
}

async function deleteDiaryEntry(entryId) {
    const token = getEntrySessionToken();
    if (token && token !== 'expired') {
        try {
            await accountEntriesRequest(`/entries/${encodeURIComponent(entryId)}`, {
                method: 'DELETE'
            });
            return;
        } catch (e) {
            console.warn('API delete failed, updating local:', e.message);
        }
    }
    const entries = (await getGuestEntries()).filter(e => e.id !== entryId);
    await saveGuestEntries(entries);
}

// ---- Exams & Revision Tracker CRUD ----

async function loadExams() {
    const token = getEntrySessionToken();
    if (token && token !== 'expired') {
        try {
            const result = await accountEntriesRequest('/exams');
            if (Array.isArray(result.exams)) return result.exams;
        } catch (e) {
            console.warn('Falling back to local exams:', e.message);
        }
    }
    const stored = localStorage.getItem(EXAM_LOCAL_KEY);
    if (!stored) {
        localStorage.setItem(EXAM_LOCAL_KEY, JSON.stringify(SAMPLE_EXAMS));
        return SAMPLE_EXAMS;
    }
    try {
        return JSON.parse(stored);
    } catch (e) {
        return [];
    }
}

async function saveExam(exam) {
    const token = getEntrySessionToken();
    if (token && token !== 'expired') {
        try {
            const result = await accountEntriesRequest('/exams', {
                method: 'POST',
                body: JSON.stringify(exam)
            });
            if (result.exam) return result.exam;
        } catch (e) {
            console.warn('API saveExam failed, saving locally:', e.message);
        }
    }
    const exams = await loadExams();
    if (exam.id) {
        const idx = exams.findIndex(e => e.id === exam.id);
        if (idx >= 0) exams[idx] = { ...exams[idx], ...exam };
        else exams.push(exam);
    } else {
        exam.id = Date.now();
        exams.push(exam);
    }
    localStorage.setItem(EXAM_LOCAL_KEY, JSON.stringify(exams));
    return exam;
}

async function deleteExam(examId) {
    const token = getEntrySessionToken();
    if (token && token !== 'expired') {
        try {
            await accountEntriesRequest(`/exams/${encodeURIComponent(examId)}`, {
                method: 'DELETE'
            });
            return;
        } catch (e) {
            console.warn('API deleteExam failed, deleting locally:', e.message);
        }
    }
    const exams = (await loadExams()).filter(e => e.id !== examId);
    localStorage.setItem(EXAM_LOCAL_KEY, JSON.stringify(exams));
}

// ---- AI Endpoints Client ----

async function extractCheckinAI(transcript, mode = 'student', today = null) {
    try {
        const response = await fetch(`${ENTRY_API_BASE}/api/checkin/extract`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transcript, mode, today: today || new Date().toISOString().split('T')[0] })
        });
        if (!response.ok) throw new Error('AI extraction error');
        const data = await response.json();
        return data.extraction;
    } catch (e) {
        // Offline / browser fallback extraction
        const lower = transcript.toLowerCase();
        let mood = 'calm';
        if (lower.includes('happy') || lower.includes('buzzing') || lower.includes('sound') || lower.includes('great')) mood = 'happy';
        else if (lower.includes('stress') || lower.includes('radge') || lower.includes('overwhelmed') || lower.includes('deadline')) mood = 'stressed';
        else if (lower.includes('reflect') || lower.includes('thinking') || lower.includes('wondering')) mood = 'reflective';

        const isCrisis = lower.includes('kill myself') || lower.includes('suicide') || lower.includes('end it all') || lower.includes("don't want to live");

        return {
            // Marks this as a browser-side guess: callers must not treat its numbers as measurements.
            offlineFallback: true,
            mood: mood === 'happy' ? 8 : (mood === 'calm' ? 7 : (mood === 'reflective' ? 5 : 3)),
            sleepHours: 7.0,
            sleepQuality: 'ok',
            stress: mood === 'stressed' ? 8 : 4,
            fatigue: lower.includes('knackered') || lower.includes('tired') ? 8 : 4,
            studyHours: mode === 'student' ? 4.0 : null,
            workHours: mode === 'employed' ? 7.5 : null,
            tags: lower.includes('exam') ? ['#exam'] : (lower.includes('study') ? ['#study'] : ['#checkin']),
            summary: transcript.slice(0, 150),
            dialectTerms: lower.includes('knackered') ? [{ heard: 'knackered', meaning: 'exhausted' }] : [],
            safety: {
                level: isCrisis ? 'crisis' : 'none',
                reason: isCrisis ? 'Crisis indicators detected' : null
            },
            spokenReply: isCrisis
                ? "It sounds like things are really hard right now, and you don't have to deal with this on your own. You can call Samaritans free on 116 123."
                : "Thank you for checking in. Every reflection helps build a clearer picture of your wellbeing."
        };
    }
}

// The summary/prompt endpoints expect mood as a 1-10 number. Word moods ("stressed") or a
// skipped mood ('') are sent as null rather than converted into an invented score.
function entryForApi(entry) {
    return { ...entry, mood: typeof entry.mood === 'number' ? entry.mood : null };
}

async function getInsightsAI(entries, mode = 'student', examInfo = {}) {
    try {
        const response = await fetch(`${ENTRY_API_BASE}/api/insights`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mode,
                entries,
                examPhase: examInfo.examPhase || 'early_term',
                daysToNextExam: examInfo.daysToNextExam || null,
                nextExamSubject: examInfo.nextExamSubject || null
            })
        });
        if (!response.ok) throw new Error('Failed to compute insights');
        return await response.json();
    } catch (e) {
        // Never invent a personal pattern when the service can't be reached.
        return { insights: [], advice: [], unavailable: true };
    }
}

async function getDailyPromptAI(mode = 'student', examInfo = {}, recentEntries = []) {
    try {
        const response = await fetch(`${ENTRY_API_BASE}/api/daily-prompt`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mode,
                examPhase: examInfo.examPhase || 'early_term',
                daysToNextExam: examInfo.daysToNextExam || null,
                nextExamSubject: examInfo.nextExamSubject || null,
                recent: recentEntries.map(entryForApi)
            })
        });
        if (!response.ok) throw new Error('Prompt error');
        const data = await response.json();
        return data.prompt;
    } catch (e) {
        return "What is one small win from today that you want to remember next month?";
    }
}

async function getWeeklySummaryAI(entries, mode = 'student') {
    try {
        const response = await fetch(`${ENTRY_API_BASE}/api/weekly-summary`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode, entries: entries.map(entryForApi) })
        });
        if (!response.ok) throw new Error('Weekly summary error');
        return await response.json();
    } catch (e) {
        // Honest fallback: no invented topics or counts.
        return { summary: "Couldn't put together a summary right now. Your entries are safe; try again later.", recurringTopics: [], highlight: null, unavailable: true };
    }
}

async function getPassportReportAI(entries, mode = 'student', periodDays = 14) {
    try {
        const response = await fetch(`${ENTRY_API_BASE}/api/report/passport`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entries, mode, periodDays })
        });
        if (!response.ok) throw new Error('Report error');
        const data = await response.json();
        return data.report;
    } catch (e) {
        return null;
    }
}

// ---- Mood display helpers ----

const MOOD_KEYS = ['happy', 'calm', 'reflective', 'stressed'];

function moodName(mood) {
    if (typeof mood === 'number') {
        if (mood >= 7.5) return 'Happy';
        if (mood >= 5.5) return 'Calm';
        if (mood >= 4.0) return 'Reflective';
        return 'Stressed';
    }
    // A skipped mood stays empty: never shown or counted as "Calm".
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
    } else {
        delete element.dataset.mood;
    }
    element.appendChild(document.createTextNode(moodName(mood) || 'No mood chosen'));
}
