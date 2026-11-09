import http.server
import json
import os
import threading
import time
import socket
import base64
import webbrowser
import traceback
from http.server import ThreadingHTTPServer

# ====== CONFIG ======
API_KEY =os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("WARNING: GEMINI_API_KEY is not set.")

MODEL = "gemini-2.0-flash"
# FIXED URL: Ends with & so we can append the key safely
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:streamGenerateContent?alt=sse&"

PORT = int(os.environ.get("PORT", 8000))
HISTORY_FILE = "perito_memory.json"
USAGE_FILE = "perito_usage.json"
SETTINGS_FILE = "perito_settings.json"
# ====================

try:
    import requests
except ImportError:
    raise SystemExit("requests is not installed.")

HISTORY = []
USAGE = {"messages_today": 0, "last_reset_date": str(time.strftime('%Y-%m-%d')), "is_premium": False}
SETTINGS = {"prompt": "You are PERITO, a master developer. Format code nicely with Markdown.", "temperature": 0.7}
FREE_LIMIT = 5

def load_data():
    global HISTORY, USAGE, SETTINGS
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f: HISTORY = json.load(f)
        except: HISTORY = []
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r") as f: USAGE = json.load(f)
        except: pass
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f: SETTINGS = json.load(f)
        except: pass

def save_data():
    try:
        with open(HISTORY_FILE, "w") as f: json.dump(HISTORY, f)
        with open(USAGE_FILE, "w") as f: json.dump(USAGE, f)
        with open(SETTINGS_FILE, "w") as f: json.dump(SETTINGS, f)
    except: pass

def check_usage():
    today = str(time.strftime('%Y-%m-%d'))
    if USAGE.get("last_reset_date") != today:
        USAGE["messages_today"] = 0
        USAGE["last_reset_date"] = today
        save_data()
    if USAGE.get("is_premium"): return True
    if USAGE["messages_today"] >= FREE_LIMIT: return False
    USAGE["messages_today"] += 1
    save_data()
    return True

load_data()

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>PERITO AI</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/styles/atom-one-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/highlight.min.js"></script>
    <style>
        body { margin: 0; padding: 0; background-color: #1e1e1e; color: white; font-family: -apple-system, sans-serif; display: flex; flex-direction: column; height: 100vh; }
        #header { background-color: #171717; padding: 15px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #333; }
        #title { font-weight: bold; font-size: 1.2rem; letter-spacing: 1px; }
        .btn { background-color: #444; border: none; color: white; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; margin-left: 5px;}
        #upgrade-btn { background-color: #f39c12; font-weight: bold; display: none; }
        #chat-container { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; }
        .message-wrapper { display: flex; flex-direction: column; max-width: 90%; }
        .user-wrapper { align-self: flex-end; align-items: flex-end; }
        .ai-wrapper { align-self: flex-start; align-items: flex-start; width: 100%;}
        .message { padding: 12px 18px; border-radius: 20px; line-height: 1.5; white-space: pre-wrap; font-size: 0.95rem; width: fit-content; max-width: 100%; overflow-wrap: break-word;}
        .user-msg { background-color: #0078D7; color: white; border-bottom-right-radius: 5px; }
        .ai-msg { background-color: #2b2b2b; color: #f1f1f1; border-bottom-left-radius: 5px; }
        .ai-msg pre { background: #1e1e1e; border-radius: 8px; padding: 10px; overflow-x: auto; margin-top: 5px; border: 1px solid #444; }
        .copy-btn { background: none; border: none; color: #888; font-size: 0.75rem; cursor: pointer; margin-top: 5px; }
        #input-area { background-color: #171717; padding: 15px; display: flex; gap: 10px; align-items: center; padding-bottom: 25px;}
        input[type="text"] { flex: 1; background-color: #2f2f2f; border: none; padding: 15px; border-radius: 25px; color: white; outline: none;}
        input[type="file"] { display: none; }
        .icon-btn { background: none; border: none; color: #888; font-size: 1.5rem; cursor: pointer; }
        button#send-btn { background-color: #0078D7; border: none; color: white; padding: 0 20px; border-radius: 25px; font-weight: bold; height: 45px; }
        
        /* MODALS */
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); justify-content: center; align-items: center; z-index: 100; }
        .modal-content { background: #2a2a2a; padding: 25px; border-radius: 15px; text-align: left; max-width: 320px; width: 85%; border: 1px solid #444;}
        .modal-content h2 { color: #fff; margin-top: 0; font-size: 1.2rem; }
        .modal-content label { display: block; margin-top: 15px; font-size: 0.9rem; color: #aaa; }
        .modal-content textarea, .modal-content input[type="range"] { width: 100%; margin-top: 5px; box-sizing: border-box; }
        .modal-content textarea { background: #1e1e1e; border: 1px solid #555; color: white; padding: 10px; border-radius: 8px; height: 80px; resize: none; }
        .buy-btn { background: #0078D7; color: white; border: none; padding: 12px; width: 100%; border-radius: 8px; font-weight: bold; margin-top: 20px; cursor: pointer;}
        .close-btn { background: #555; color: white; border: none; padding: 12px; width: 100%; border-radius: 8px; font-weight: bold; margin-top: 10px; cursor: pointer; }
    </style>
</head>
<body>
    <div id="header">
        <div id="title">PERITO AI</div>
        <div>
            <button id="upgrade-btn" class="btn" onclick="showModal('paywall-modal')">⭐ Premium</button>
            <button class="btn" onclick="showModal('settings-modal')">⚙️</button>
            <button class="btn" onclick="resetChat()">Clear</button>
        </div>
    </div>
    <div id="chat-container"></div>
    <div id="input-area">
        <button class="icon-btn" onclick="document.getElementById('file-input').click()">📎</button>
        <input type="file" id="file-input" accept="image/*" onchange="handleFile(this)">
        <input type="text" id="user-input" placeholder="Message PERITO..." autocomplete="off">
        <button class="icon-btn" id="mic-btn" onclick="toggleDictation()">🎤</button>
        <button id="send-btn" onclick="sendMessage()">Send</button>
    </div>

    <div id="settings-modal" class="modal">
        <div class="modal-content">
            <h2>AI Settings</h2>
            <label>System Prompt (Personality)</label>
            <textarea id="sys-prompt"></textarea>
            <label>Temperature: <span id="temp-val">0.7</span></label>
            <input type="range" id="temp-slider" min="0" max="1" step="0.1" oninput="document.getElementById('temp-val').textContent = this.value">
            <button class="buy-btn" onclick="saveSettings()">Save Settings</button>
            <button class="close-btn" onclick="hideModal('settings-modal')">Close</button>
        </div>
    </div>

    <div id="paywall-modal" class="modal">
        <div class="modal-content" style="text-align:center;">
            <h2 style="color:#f39c12;">Limit Reached</h2>
            <p>You have used your 5 free messages for today.</p>
            <button class="buy-btn" style="background:#f39c12;" onclick="simulatePayment()">Upgrade for $4.99/mo</button>
            <button class="close-btn" onclick="hideModal('paywall-modal')">Close</button>
        </div>
    </div>

    <script>
        let busy = false, imgB64 = "", imgMime = "";
        const chat = document.getElementById('chat-container'), userIn = document.getElementById('user-input');
        
        let rec = null;
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            rec = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
            rec.onresult = (e) => { userIn.value += e.results[0][0].transcript; document.getElementById('mic-btn').style.color = "#888"; };
        } else { document.getElementById('mic-btn').style.display = 'none'; }

        window.onload = async () => {
            const status = await (await fetch('/status')).json();
            if (status.is_premium) document.getElementById('upgrade-btn').style.display = 'none';
            else document.getElementById('upgrade-btn').style.display = 'inline-block';
            
            const settings = await (await fetch('/settings')).json();
            document.getElementById('sys-prompt').value = settings.prompt;
            document.getElementById('temp-slider').value = settings.temperature;
            document.getElementById('temp-val').textContent = settings.temperature;

            try {
                const data = await (await fetch('/history')).json();
                if (data.history.length === 0) addAI('Hello! I am PERITO.', true);
                else data.history.forEach(m => m.role === 'user' ? addUser(m.parts[0].text) : addAI(m.parts[0].text, true));
            } catch { addAI('Hello! I am PERITO.', true); }
        };

        function showModal(id) { document.getElementById(id).style.display = 'flex'; }
        function hideModal(id) { document.getElementById(id).style.display = 'none'; }

        async function saveSettings() {
            const prompt = document.getElementById('sys-prompt').value;
            const temp = document.getElementById('temp-slider').value;
            await fetch('/settings', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({prompt: prompt, temperature: parseFloat(temp)}) });
            hideModal('settings-modal');
            addAI("⚙️ Settings saved!", false);
        }

        async function simulatePayment() {
            await fetch('/upgrade', { method: 'POST' });
            alert("🎉 Payment Successful!"); hideModal('paywall-modal'); document.getElementById('upgrade-btn').style.display = 'none';
        }

        userIn.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
        
        function toggleDictation() { 
            if (!rec) return alert("Not supported"); 
            if (rec.active) { rec.stop(); rec.active=false; } 
            else { rec.start(); rec.active=true; document.getElementById('mic-btn').style.color = "#d32f2f"; } 
        }
        
        function handleFile(input) {
            const file = input.files[0]; if (!file) return;
            const reader = new FileReader();
            reader.onload = (e) => { imgB64 = e.target.result.split(',')[1]; imgMime = file.type; };
            reader.readAsDataURL(file);
        }

        async function sendMessage() {
            let text = userIn.value.trim(); if (!text || busy) return;
            busy = true; document.getElementById('send-btn').disabled = true;
            addUser(text); userIn.value = '';
            
            const wrapper = document.createElement('div');
            wrapper.className = 'message-wrapper ai-wrapper';
            const bubble = document.createElement('div');
            bubble.className = 'message ai-msg';
            bubble.textContent = "Thinking...";
            wrapper.appendChild(bubble);
            chat.appendChild(wrapper); chat.scrollTop = chat.scrollHeight;

            try {
                const res = await fetch('/ask', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({prompt: text, image: imgB64, mime: imgMime}) });
                
                if (!res.ok) {
                    bubble.textContent = "Error " + res.status;
                } else {
                    const reader = res.body.getReader();
                    const decoder = new TextDecoder("utf-8");
                    let fullText = "";
                    bubble.textContent = ""; 
                    
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        const chunk = decoder.decode(value, { stream: true });
                        fullText += chunk;
                        bubble.innerHTML = formatMarkdown(fullText);
                        chat.scrollTop = chat.scrollHeight;
                    }
                    bubble.innerHTML = formatMarkdown(fullText);
                    highlightCode(bubble);
                }
                imgB64 = ""; imgMime = "";
            } catch (err) {
                bubble.textContent = "Error connecting to server.";
            } finally { busy = false; document.getElementById('send-btn').disabled = false; }
        }

        function formatMarkdown(t) {
            let out = t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            out = out.replace(/```(.*?)\\n([\\s\\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');
            out = out.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
            return out;
        }
        
        function highlightCode(el) {
            el.querySelectorAll('pre code').forEach((block) => { hljs.highlightElement(block); });
        }

        async function resetChat() {
            if (!confirm("Clear chat?")) return;
            await fetch('/reset', { method: 'POST' });
            chat.innerHTML = ''; addAI('Memory cleared.', true);
        }

        function addUser(t) {
            const w = document.createElement('div'); w.className = 'message-wrapper user-wrapper';
            w.innerHTML = `<div class="message user-msg">${t.replace(/</g, '&lt;')}</div>`;
            chat.appendChild(w); chat.scrollTop = chat.scrollHeight;
        }

        function addAI(t, md=false) {
            const w = document.createElement('div'); w.className = 'message-wrapper ai-wrapper';
            const b = document.createElement('div'); b.className = 'message ai-msg';
            
            if (md) { b.innerHTML = formatMarkdown(t); w.appendChild(b); highlightCode(b); }
            else { b.textContent = t; w.appendChild(b); }
            
            const btn = document.createElement('button'); btn.className = 'copy-btn'; btn.textContent = '📋 Copy';
            btn.onclick = () => { navigator.clipboard.writeText(t); btn.textContent = '✅ Copied!'; setTimeout(() => btn.textContent = '📋 Copy', 2000); };
            w.appendChild(btn);
            
            chat.appendChild(w); chat.scrollTop = chat.scrollHeight;
        }
    </script>
</body>
</html>
"""

class PeritoHandler(http.server.BaseHTTPRequestHandler):
    def _send(self, status, ctype, body):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ('/', '/index.html'): self._send(200, 'text/html', HTML_PAGE.encode('utf-8'))
        elif self.path == '/history': self._send(200, 'application/json', json.dumps({"history": HISTORY}).encode('utf-8'))
        elif self.path == '/status': self._send(200, 'application/json', json.dumps(USAGE).encode('utf-8'))
        elif self.path == '/settings': self._send(200, 'application/json', json.dumps(SETTINGS).encode('utf-8'))
        else: self._send(404, 'text/plain', b'Not Found')

    def do_POST(self):
        if self.path == '/ask':
            try:
                length = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(length).decode('utf-8'))
                prompt = (data.get('prompt') or '').strip()
                img = data.get('image')
                mime = data.get('mime')

                if not prompt: return self._send(400, 'application/json', b'{"reply":"Empty"}')
                if not check_usage(): return self._send(429, 'application/json', b'{"error":"LIMIT"}')

                parts = [{"text": prompt}]
                if img and mime: parts.append({"inline_data": {"mime_type": mime, "data": img}})
                HISTORY.append({"role": "user", "parts": parts})
                
                payload = {
                    "system_instruction": {"parts": [{"text": SETTINGS["prompt"]}]},
                    "contents": HISTORY,
                    "generationConfig": {"temperature": SETTINGS["temperature"]}
                }

                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()

                full_reply = ""
                
                # FIXED: Removed the ? and just appended the key to the URL string
                with requests.post(URL, headers={"x-goog-api-key": API_KEY}, json=payload, stream=True, timeout=30) as r:
                    if r.status_code != 200:
                        error_msg = f"Google API Error {r.status_code}: {r.text}"
                        error_bytes = error_msg.encode('utf-8')
                        self.wfile.write(f"{len(error_bytes):X}\r\n".encode('utf-8'))
                        self.wfile.write(error_bytes)
                        self.wfile.write(b"\r\n")
                        self.wfile.write(b"0\r\n\r\n")
                        self.wfile.flush()
                        return
                        
                    for line in r.iter_lines():
                        if line:
                            decoded_line = line.decode('utf-8')
                            if decoded_line.startswith('data: '):
                                data_str = decoded_line[6:].strip()
                                if data_str == '[DONE]':
                                    break
                                try:
                                    chunk_data = json.loads(data_str)
                                    candidates = chunk_data.get('candidates', [])
                                    if candidates:
                                        content = candidates[0].get('content', {})
                                        parts_out = content.get('parts', [])
                                        if parts_out and 'text' in parts_out[0]:
                                            text = parts_out[0]['text']
                                            full_reply += text
                                            
                                            chunk_bytes = text.encode('utf-8')
                                            self.wfile.write(f"{len(chunk_bytes):X}\r\n".encode('utf-8'))
                                            self.wfile.write(chunk_bytes)
                                            self.wfile.write(b"\r\n")
                                            self.wfile.flush()
                                except Exception:
                                    pass
                
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
                    
                HISTORY.append({"role": "model", "parts": [{"text": full_reply}]})
                save_data()
            except Exception as e:
                error_msg = f"Python Error: {str(e)}"
                error_bytes = error_msg.encode('utf-8')
                self.wfile.write(f"{len(error_bytes):X}\r\n".encode('utf-8'))
                self.wfile.write(error_bytes)
                self.wfile.write(b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            
        elif self.path == '/settings':
            length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(length).decode('utf-8'))
            SETTINGS["prompt"] = data.get("prompt", SETTINGS["prompt"])
            SETTINGS["temperature"] = float(data.get("temperature", SETTINGS["temperature"]))
            save_data()
            self._send(200, 'application/json', b'{"ok":true}')
            
        elif self.path == '/upgrade':
            USAGE["is_premium"] = True
            save_data()
            self._send(200, 'application/json', b'{"ok":true}')
            
        elif self.path == '/reset':
            HISTORY.clear()
            save_data()
            self._send(200, 'application/json', b'{"ok":true}')

    def log_message(self, format, *args): 
        pass

class ReusableServer(ThreadingHTTPServer):
    allow_reuse_address = True

if __name__ == "__main__":
    print("Starting...")
    try:
        with ReusableServer(("0.0.0.0", PORT), PeritoHandler) as httpd:
            print(f"PERITO IS RUNNING ON PORT {PORT}")
            httpd.serve_forever()
    except Exception as e:
        print("CRITICAL ERROR:", e)
        traceback.print_exc()
        time.sleep(10)
