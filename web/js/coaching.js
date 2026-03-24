/**
 * Chat interface for AI coaching - slide-out panel with session management.
 */

let sessionId = null;
let coachInitialized = false;
let sessionListVisible = false;

function initCoachPanel() {
    const toggleBtn = document.getElementById('coach-toggle');
    const closeBtn = document.getElementById('coach-close');
    const sessionsBtn = document.getElementById('coach-sessions-btn');
    const newBtn = document.getElementById('coach-new-btn');

    toggleBtn.addEventListener('click', () => toggleCoachPanel());
    closeBtn.addEventListener('click', () => toggleCoachPanel(false));
    sessionsBtn.addEventListener('click', toggleSessionList);
    newBtn.addEventListener('click', startNewConversation);

    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send');

    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    });
}

function toggleCoachPanel(forceState) {
    const panel = document.getElementById('coach-panel');
    const toggleBtn = document.getElementById('coach-toggle');
    const isOpen = typeof forceState === 'boolean' ? forceState : !panel.classList.contains('open');

    panel.classList.toggle('open', isOpen);
    toggleBtn.classList.toggle('active', isOpen);

    if (isOpen && !coachInitialized) {
        coachInitialized = true;
        addMessage('assistant', 'Hey! I\'m your cycling coach. Ask me anything about your training, upcoming workouts, or race prep for Big Sky Biggie. I can see the same data you\'re looking at.');
    }

    if (isOpen) {
        setTimeout(() => document.getElementById('chat-input').focus(), 350);
    }
}

function addMessage(role, text) {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;
    if (role === 'assistant' && typeof marked !== 'undefined') {
        div.innerHTML = marked.parse(text);
    } else {
        div.textContent = text;
    }
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
}

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    input.style.height = 'auto';
    addMessage('user', text);

    const sendBtn = document.getElementById('chat-send');
    sendBtn.disabled = true;
    const thinking = addMessage('thinking', 'Thinking...');
    thinking.classList.add('assistant', 'thinking');

    try {
        const resp = await apiPost('/api/coaching/chat', {
            message: text,
            session_id: sessionId,
        });
        sessionId = resp.session_id;
        thinking.remove();
        addMessage('assistant', resp.response);

        // Auto-refresh calendar if coach likely modified workouts
        if (typeof refreshCalendar === 'function') {
            refreshCalendar();
        }
    } catch (e) {
        thinking.remove();
        addMessage('assistant', 'Sorry, I had trouble processing that. Error: ' + e.message);
    } finally {
        sendBtn.disabled = false;
        document.getElementById('chat-input').focus();
    }
}

// Session management

function toggleSessionList() {
    sessionListVisible = !sessionListVisible;
    const list = document.getElementById('session-list');
    list.style.display = sessionListVisible ? 'block' : 'none';
    if (sessionListVisible) loadSessionList();
}

async function loadSessionList() {
    const list = document.getElementById('session-list');
    try {
        const sessions = await api('/api/coaching/sessions');
        if (sessions.length === 0) {
            list.innerHTML = '<div style="padding:0.8rem;color:var(--text-muted);font-size:0.8rem;">No previous conversations</div>';
            return;
        }
        list.innerHTML = sessions.map(s => {
            const date = new Date(s.updated_at).toLocaleDateString();
            const active = s.session_id === sessionId ? ' active' : '';
            return `<div class="session-item${active}" data-sid="${s.session_id}">
                <span class="session-title">${escapeHtml(s.title || 'New conversation')}</span>
                <span class="session-date">${date}</span>
                <button class="session-delete" data-sid="${s.session_id}" title="Delete">&times;</button>
            </div>`;
        }).join('');

        list.querySelectorAll('.session-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (e.target.classList.contains('session-delete')) return;
                loadSession(item.dataset.sid);
            });
        });
        list.querySelectorAll('.session-delete').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                deleteSession(btn.dataset.sid);
            });
        });
    } catch (e) {
        list.innerHTML = '<div style="padding:0.8rem;color:var(--red);font-size:0.8rem;">Error loading sessions</div>';
    }
}

async function loadSession(sid) {
    try {
        const detail = await api(`/api/coaching/sessions/${sid}`);
        sessionId = sid;

        const container = document.getElementById('chat-messages');
        container.innerHTML = '';

        for (const msg of detail.messages) {
            const role = msg.author === 'user' ? 'user' : 'assistant';
            addMessage(role, msg.content_text || '');
        }

        // Hide session list after selection
        sessionListVisible = false;
        document.getElementById('session-list').style.display = 'none';
    } catch (e) {
        console.error('Error loading session:', e);
    }
}

async function deleteSession(sid) {
    try {
        await fetch(API + `/api/coaching/sessions/${sid}`, { method: 'DELETE' });
        if (sid === sessionId) {
            startNewConversation();
        }
        loadSessionList();
    } catch (e) {
        console.error('Error deleting session:', e);
    }
}

function startNewConversation() {
    sessionId = null;
    coachInitialized = false;
    const container = document.getElementById('chat-messages');
    container.innerHTML = '';
    coachInitialized = true;
    addMessage('assistant', 'Hey! I\'m your cycling coach. Ask me anything about your training, upcoming workouts, or race prep for Big Sky Biggie.');

    sessionListVisible = false;
    document.getElementById('session-list').style.display = 'none';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize on load
initCoachPanel();
