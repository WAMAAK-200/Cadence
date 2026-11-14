/**
 * Cadence / Smart Diary - Unified Storage & API Client Layer
 * Handles guest (localStorage) and authenticated (SQLite server) storage,
 * as well as AI extraction, pattern insight generation, exam tracking, and reporting.
 */

const ENTRY_API_BASE = 'http://127.0.0.1:8000';
const ENTRY_SESSION_KEY = 'smartdiary_session_token';
const ENTRY_EXPIRED_KEY = 'smartdiary_session_expired';
const ENTRY_LOCAL_KEY = 'diary_entries';
const ENTRY_USER_PROFILE_KEY = 'smartdiary_user_profile';
const EXAM_LOCAL_KEY = 'smartdiary_exams';

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
        spokenReply: typeof entry.spokenReply === 'string' ? entry.spokenReply : ''
    };
}

// ---- Guest Storage ----

function getGuestEntries() {
    const stored = localStorage.getItem(ENTRY_LOCAL_KEY);
    if (stored === null) {
        localStorage.setItem(ENTRY_LOCAL_KEY, JSON.stringify(SAMPLE_DIARY_ENTRIES));
        return SAMPLE_DIARY_ENTRIES.map(e => ({ ...e, tags: [...e.tags] }));
    }
    try {
        const parsed = JSON.parse(stored);
        const entries = Array.isArray(parsed)
            ? parsed.map((e, idx) => normalizeEntry(e, idx)).filter(Boolean)
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
    return getGuestEntries();
}

async function createDiaryEntry(entry) {
    const normalized = normalizeEntry(entry, 0);
    const token = getEntrySessionToken();
    if (token && token !== 'expired') {
        try {
            const result = await accountEntriesRequest('/entries', {
                method: 'POST',
                body: JSON.stringify(normalized)
            });
            if (result.entry) return normalizeEntry(result.entry, 0);
        } catch (e) {
            console.warn('Falling back to saving locally:', e.message);
        }
    }
    const entries = getGuestEntries();
    entries.unshift(normalized);
    saveGuestEntries(entries);
    return normalized;
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
    const entries = getGuestEntries().map(e => e.id === entryId ? normalizeEntry({ ...e, ...changes }) : e);
    saveGuestEntries(entries);
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
    const entries = getGuestEntries().filter(e => e.id !== entryId);
    saveGuestEntries(entries);
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
        return {
            insights: [
                {
                    patternId: 'pat_sleep_stress_01',
                    title: 'Sleep and Stress Link',
                    body: 'Your recent check-ins show that days with higher sleep duration generally correspond with lower stress levels.'
                }
            ],
            advice: [
                {
                    text: 'Aim for a consistent 7-8 hours baseline sleep tonight.',
                    why: 'Consistent rest protects focus and cognitive stamina.'
                }
            ]
        };
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
                recent: recentEntries
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
            body: JSON.stringify({ mode, entries })
        });
        if (!response.ok) throw new Error('Weekly summary error');
        return await response.json();
    } catch (e) {
        return {
            summary: `You logged ${entries.length} check-ins this week. Keeping a steady log helps track your momentum.`,
            recurringTopics: ['study', 'rest'],
            highlight: entries.length > 0 ? entries[0].title : null
        };
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
    return String(mood || '').replace(/[^\p{L}\s-]/gu, '').trim() || 'Calm';
}

function moodKey(mood) {
    const name = moodName(mood).toLowerCase();
    return MOOD_KEYS.includes(name) ? name : 'calm';
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
