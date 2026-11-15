window.updateAccountNavigation = function updateAccountNavigation() {
    const activeAccountSession = Boolean(sessionStorage.getItem('smartdiary_session_token'))
        && sessionStorage.getItem('smartdiary_session_expired') !== 'true';

    document.querySelectorAll('.session-link').forEach(link => {
        link.textContent = activeAccountSession ? '👤 Account' : '👤 Log In';
        link.href = activeAccountSession ? 'account.html' : 'login.html';
    });

    document.querySelectorAll('.signup-link').forEach(link => {
        link.hidden = activeAccountSession;
    });

    const signupForm = document.getElementById('signup-form');
    const signupSessionNotice = document.getElementById('signup-session-notice');
    if (activeAccountSession && signupForm) signupForm.hidden = true;
    if (activeAccountSession && signupSessionNotice) signupSessionNotice.hidden = false;
};

window.updateAccountNavigation();
