// FILE: app.js | PURPOSE: Frontend JavaScript for Jardín chat interface

// State
let currentTab = 'chat';

// DOM Elements
const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const navTabs = document.querySelectorAll('.nav-tab');
const tabContents = document.querySelectorAll('.tab-content');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initChat();
    initClients();
    initVoice();
    loadMessages();
    loadPrices();
});

// Tab Navigation
function initTabs() {
    navTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabId = tab.dataset.tab;
            switchTab(tabId);
        });
    });
}

function switchTab(tabId) {
    currentTab = tabId;

    // Update nav
    navTabs.forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabId);
    });

    // Update content
    tabContents.forEach(content => {
        content.classList.toggle('active', content.id === `${tabId}-tab`);
    });

    // Load data for tab
    if (tabId === 'clients') loadClients();
    if (tabId === 'proposals') loadProposals();
    if (tabId === 'messages') loadPendingMessages();
    if (tabId === 'prices') loadPrices();
}

// Voice Recording (Whisper)
let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let audioStream = null;

// Global function for voice button
window.startVoice = async function() {
    const voiceBtn = document.getElementById('voice-btn');
    const input = document.getElementById('chat-input');

    if (isRecording) {
        // Stop recording
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
        }
        return;
    }

    // Start recording
    voiceBtn.style.background = '#f44336';
    input.placeholder = 'Permitiendo micrófono...';

    try {
        audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });

        mediaRecorder = new MediaRecorder(audioStream);
        audioChunks = [];

        mediaRecorder.ondataavailable = function(event) {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async function() {
            isRecording = false;
            voiceBtn.style.background = '';
            input.placeholder = 'Transcribiendo...';

            const audioBlob = new Blob(audioChunks);

            const formData = new FormData();
            formData.append('audio', audioBlob, 'recording.wav');

            try {
                const response = await fetch('/api/transcribe', {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();
                if (data.text) {
                    input.value = data.text;
                } else if (data.error) {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }

            input.placeholder = 'Escribe o habla...';
            audioStream.getTracks().forEach(track => track.stop());
        };

        mediaRecorder.start();
        isRecording = true;
        input.placeholder = 'Grabando... toca  para parar';

    } catch (error) {
        voiceBtn.style.background = '';
        input.placeholder = 'Escribe o habla...';
        alert('Micrófono: ' + error.message);
    }
};

function initVoice() {
    // Voice is now handled by window.startVoice() called from onclick
}

// Chat Functions
function initChat() {
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = chatInput.value.trim();
        if (!message) return;

        // Add user message
        addMessage('user', message);
        chatInput.value = '';

        // Show loading
        const loadingEl = addLoadingMessage();

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            });

            const data = await response.json();

            // Remove loading
            loadingEl.remove();

            // Add assistant response
            addMessage('assistant', data.response, data.client_messages);

            // Show notification for new clients
            if (data.new_clients && data.new_clients.length > 0) {
                showNotification(`Cliente creado: ${data.new_clients[0].name}`);
            }

            // Show notification for proposals
            if (data.proposals && data.proposals.length > 0) {
                showNotification(`Propuesta creada para ${data.proposals[0].client_name}`);
            }

            // Show notification for client messages
            if (data.client_messages && data.client_messages.length > 0) {
                showNotification(`${data.client_messages.length} mensaje(s) listo(s) para enviar`);
            }

        } catch (error) {
            loadingEl.remove();
            addMessage('assistant', 'Lo siento, hubo un error. Por favor intenta de nuevo.');
            console.error('Chat error:', error);
        }
    });
}

function addMessage(role, content, clientMessages = []) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    let html = `<div class="message-content">${escapeHtml(content)}`;

    // Add client message boxes if present
    if (clientMessages && clientMessages.length > 0) {
        clientMessages.forEach(cm => {
            html += `
                <div class="client-message-box">
                    <div class="label">Mensaje para ${escapeHtml(cm.client_name)}:</div>
                    <div class="english">${escapeHtml(cm.message)}</div>
                </div>
            `;
        });
    }

    html += '</div>';
    messageDiv.innerHTML = html;

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    return messageDiv;
}

function addLoadingMessage() {
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message assistant';
    loadingDiv.innerHTML = `
        <div class="message-content loading">
            <div class="loading-spinner"></div>
            Pensando...
        </div>
    `;
    chatMessages.appendChild(loadingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return loadingDiv;
}

// Clients Functions
function initClients() {
    const addClientBtn = document.getElementById('add-client-btn');
    const clientForm = document.getElementById('client-form');

    addClientBtn.addEventListener('click', () => {
        openModal('client-modal');
    });

    clientForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(clientForm);
        const data = Object.fromEntries(formData);

        try {
            const response = await fetch('/api/clients', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (response.ok) {
                closeModal('client-modal');
                clientForm.reset();
                loadClients();
                showNotification('Cliente creado');
            }
        } catch (error) {
            console.error('Error creating client:', error);
        }
    });
}

async function loadClients() {
    const container = document.getElementById('clients-list');

    try {
        const response = await fetch('/api/clients');
        const data = await response.json();

        if (data.clients.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon"></div>
                    <div class="empty-state-text">No hay clientes todavía</div>
                </div>
            `;
            return;
        }

        container.innerHTML = data.clients.map(client => `
            <div class="card">
                <div class="card-header">
                    <span class="card-title">${escapeHtml(client.name)}</span>
                    <span class="card-subtitle">${client.phone || ''}</span>
                </div>
                <div class="card-body">
                    ${client.address ? `<div>${escapeHtml(client.address)}</div>` : ''}
                    ${client.notes ? `<div style="color: var(--text-light); font-size: 13px; margin-top: 4px;">${escapeHtml(client.notes)}</div>` : ''}
                </div>
                <div class="card-actions">
                    <button class="btn-primary btn-small" onclick="createProposal(${client.id}, '${escapeHtml(client.name)}')">
                        Propuesta
                    </button>
                    <button class="btn-secondary btn-small" onclick="generateInvoice(${client.id})">
                        Factura
                    </button>
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Error loading clients:', error);
    }
}

// Messages Functions
async function loadPendingMessages() {
    const container = document.getElementById('messages-list');

    try {
        const response = await fetch('/api/messages/pending');
        const data = await response.json();

        if (data.messages.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon"></div>
                    <div class="empty-state-text">No hay mensajes pendientes</div>
                </div>
            `;
            return;
        }

        container.innerHTML = data.messages.map(msg => `
            <div class="card">
                <div class="card-header">
                    <span class="card-title">${escapeHtml(msg.client_name)}</span>
                    <span class="badge badge-pending">Pendiente</span>
                </div>
                <div class="card-body">
                    <div>${escapeHtml(msg.content)}</div>
                    ${msg.client_phone ? `<div style="margin-top: 8px; color: var(--text-light);"> ${msg.client_phone}</div>` : ''}
                </div>
                <div class="card-actions">
                    <button class="btn-primary btn-small btn-success" onclick="sendMessage(${msg.id})">
                        Enviar
                    </button>
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Error loading messages:', error);
    }
}

async function sendMessage(messageId) {
    try {
        const response = await fetch(`/api/messages/${messageId}/send`, {
            method: 'POST'
        });

        if (response.ok) {
            showNotification('Mensaje enviado');
            loadPendingMessages();
        }
    } catch (error) {
        console.error('Error sending message:', error);
    }
}

// Prices Functions
async function loadPrices() {
    const container = document.getElementById('prices-list');

    try {
        const response = await fetch('/api/prices');
        const data = await response.json();

        if (data.prices.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon"></div>
                    <div class="empty-state-text">
                        Todavía no hay precios registrados.<br>
                        Cuando cotices servicios, los aprenderé automáticamente.
                    </div>
                </div>
            `;
            return;
        }

        container.innerHTML = data.prices.map(price => `
            <div class="price-row">
                <div>
                    <div class="price-service">${escapeHtml(price.service_type)}</div>
                    <div class="price-uses">Usado ${price.times_used} vez(es)</div>
                </div>
                <div class="price-amount">$${price.default_price.toFixed(2)}</div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Error loading prices:', error);
    }
}

// Proposals Functions
async function loadProposals() {
    const container = document.getElementById('proposals-list');

    try {
        const response = await fetch('/api/proposals');
        const data = await response.json();

        if (data.proposals.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon"></div>
                    <div class="empty-state-text">
                        No hay propuestas todavía.<br>
                        Crea una desde el chat o desde la lista de clientes.
                    </div>
                </div>
            `;
            return;
        }

        container.innerHTML = data.proposals.map(prop => `
            <div class="card">
                <div class="card-header">
                    <span class="card-title">${escapeHtml(prop.client_name)}</span>
                    <span class="badge ${prop.status === 'accepted' ? 'badge-sent' : 'badge-pending'}">${prop.status}</span>
                </div>
                <div class="card-body">
                    <div><strong>${prop.proposal_number}</strong></div>
                    <div>Total: $${prop.total.toFixed(2)}</div>
                    <div style="font-size: 12px; color: var(--text-light);">
                        ${prop.services.length} servicio(s)
                    </div>
                </div>
                <div class="card-actions">
                    <button class="btn-primary btn-small" onclick="downloadProposal(${prop.id})">
                        Descargar PDF
                    </button>
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Error loading proposals:', error);
    }
}

async function createProposal(clientId, clientName) {
    const servicesInput = prompt(`Servicios para ${clientName} (ej: Podar árbol:120, Reparar válvula:25)`);
    if (!servicesInput) return;

    // Parse services
    const services = servicesInput.split(',').map(s => {
        const parts = s.trim().split(':');
        return {
            description: parts[0].trim(),
            price: parseFloat(parts[1]) || 0
        };
    }).filter(s => s.description && s.price > 0);

    if (services.length === 0) {
        showNotification('Por favor ingresa servicios válidos');
        return;
    }

    try {
        const response = await fetch('/api/proposals', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                client_id: clientId,
                services: services
            })
        });

        if (response.ok) {
            const data = await response.json();
            showNotification(`Propuesta ${data.proposal_number} creada`);
            window.open(`/api/proposals/${data.proposal_id}/pdf`, '_blank');
        }
    } catch (error) {
        console.error('Error creating proposal:', error);
    }
}

async function downloadProposal(proposalId) {
    window.open(`/api/proposals/${proposalId}/pdf`, '_blank');
}

// Invoice Functions
async function generateInvoice(clientId) {
    const maintenanceAmount = prompt('¿Cuánto es el mantenimiento trimestral? (dejar vacío si no aplica)');

    try {
        const response = await fetch('/api/invoices', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                client_id: clientId,
                maintenance_amount: maintenanceAmount ? parseFloat(maintenanceAmount) : null
            })
        });

        if (response.ok) {
            const data = await response.json();
            showNotification(`Factura ${data.invoice_number} creada`);

            // Open PDF in new tab
            window.open(`/api/invoices/${data.invoice_number}/pdf`, '_blank');
        }
    } catch (error) {
        console.error('Error generating invoice:', error);
    }
}

// Load conversation history
async function loadMessages() {
    try {
        const response = await fetch('/api/conversation');
        const data = await response.json();

        // Skip if no messages or only the welcome message exists
        if (data.messages.length === 0) return;

        // Clear welcome message
        chatMessages.innerHTML = '';

        // Add historical messages
        data.messages.forEach(msg => {
            const role = msg.role === 'jaime' ? 'user' : 'assistant';
            addMessage(role, msg.content);
        });

    } catch (error) {
        console.error('Error loading conversation:', error);
    }
}

// Modal Functions
function openModal(modalId) {
    document.getElementById(modalId).classList.remove('hidden');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.add('hidden');
}

// Utility Functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showNotification(message) {
    // Simple notification - could be enhanced
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: var(--primary);
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        z-index: 1000;
        animation: fadeIn 0.3s ease;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 0.3s';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Make functions available globally
window.closeModal = closeModal;
window.sendMessage = sendMessage;
window.generateInvoice = generateInvoice;
window.createProposal = createProposal;
window.downloadProposal = downloadProposal;
