/**
 * Chat interface for AI coaching - slide-out panel.
 */

let sessionId = null;
let coachInitialized = false;

function initCoachPanel() {
    const panel = document.getElementById('coach-panel');
    const toggleBtn = document.getElementById('coach-toggle');
    const closeBtn = document.getElementById('coach-close');

    toggleBtn.addEventListener('click', () => toggleCoachPanel());
    closeBtn.addEventListener('click', () => toggleCoachPanel(false));

    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send');

    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
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
        // Focus the input when panel opens
        setTimeout(() => document.getElementById('chat-input').focus(), 350);
    }
}

function addMessage(role, text) {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;
    div.textContent = text;
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
    const thinking = addMessage('assistant', 'Thinking...');
    thinking.classList.add('thinking');

    try {
        const resp = await apiPost('/api/coaching/chat', {
            message: text,
            session_id: sessionId,
        });
        sessionId = resp.session_id;
        thinking.remove();
        addMessage('assistant', resp.response);
    } catch (e) {
        thinking.remove();
        addMessage('assistant', 'Sorry, I had trouble processing that. Error: ' + e.message);
    } finally {
        sendBtn.disabled = false;
        document.getElementById('chat-input').focus();
    }
}

// Initialize on load
initCoachPanel();
