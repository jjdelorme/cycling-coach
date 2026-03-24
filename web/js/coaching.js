/**
 * Chat interface for AI coaching.
 */

let sessionId = null;

function initCoach() {
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send');

    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    addMessage('assistant', 'Hey! I\'m your cycling coach. Ask me anything about your training, upcoming workouts, or race prep for Big Sky Biggie. What\'s on your mind?');
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
        addMessage('assistant', 'Sorry, I had trouble processing that. The coaching endpoint may not be configured yet. Error: ' + e.message);
    } finally {
        sendBtn.disabled = false;
    }
}
