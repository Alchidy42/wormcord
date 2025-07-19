import sys
import socket
import threading
import json
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QHBoxLayout, QMessageBox
)
from PyQt5.QtCore import Qt

clients = []
channels = []
banned_ips = set()
config = {}
message_lock = threading.Lock()

CONFIG_PATH = "server/config.json"
MESSAGES_PATH = "messages/"

def load_config():
    global config, channels, banned_ips
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    channels[:] = config.get("channels", ["général"])
    banned_ips.clear()
    banned_ips.update(config.get("banned_ips", []))
    os.makedirs(MESSAGES_PATH, exist_ok=True)
    for ch in channels:
        path = f"{MESSAGES_PATH}{ch}.json"
        if not os.path.exists(path):
            with open(path, "w") as f:
                json.dump([], f)

def save_config():
    config["channels"] = channels
    config["banned_ips"] = list(banned_ips)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

def save_message(channel, username, content):
    with message_lock:
        path = f"{MESSAGES_PATH}{channel}.json"
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except:
            data = []
        data.append({"username": username, "content": content})
        with open(path, "w") as f:
            json.dump(data, f)

def load_messages(channel):
    path = f"{MESSAGES_PATH}{channel}.json"
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)

def broadcast(message, channel=None):
    packet = json.dumps(message) + "\n"
    for c in clients:
        try:
            c.send(packet.encode())
        except:
            pass

def handle_client(conn, addr):
    ip = addr[0]
    if ip in banned_ips:
        conn.close()
        return

    username = "???"
    current_channel = "général"
    while True:
        try:
            data = conn.recv(4096)
            if not data:
                break
            for line in data.decode().split("\n"):
                if not line.strip():
                    continue
                message = json.loads(line)
                if message["type"] == "join":
                    username = message["username"]
                    conn.send(json.dumps({
                        "type": "channels",
                        "channels": channels
                    }).encode() + b"\n")
                    for ch in channels:
                        conn.send(json.dumps({
                            "type": "history",
                            "channel": ch,
                            "messages": load_messages(ch)
                        }).encode() + b"\n")
                elif message["type"] == "message":
                    ch = message.get("channel", "général")
                    content = message["content"]
                    msg_obj = {"type": "message", "username": username, "channel": ch, "content": content}
                    save_message(ch, username, content)
                    broadcast(msg_obj)
        except Exception as e:
            print("Erreur client :", e)
            break
    conn.close()
    if conn in clients:
        clients.remove(conn)
    broadcast({"type": "info", "content": f"{username} a quitté le serveur"})

def start_server(host="0.0.0.0", port=9000):
    load_config()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, port))
    sock.listen()
    print(f"[✔] Serveur Wormcord lancé sur {host}:{port}")
    while True:
        conn, addr = sock.accept()
        if addr[0] in banned_ips:
            conn.close()
        else:
            clients.append(conn)
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

# --- INTERFACE GRAPHIQUE DE CONFIGURATION ---

server_thread = None

class AdminGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Configuration du serveur Wormcord")
        self.setGeometry(200, 200, 600, 400)
        self.layout = QVBoxLayout()

        self.name_label = QLabel("Nom du serveur :")
        self.name_input = QLineEdit()
        self.name_input.setText(config.get("server_name", "Wormcord"))
        self.layout.addWidget(self.name_label)
        self.layout.addWidget(self.name_input)

        self.channels_list = QListWidget()
        self.channels_list.addItems(channels)
        self.layout.addWidget(QLabel("Salons :"))
        self.layout.addWidget(self.channels_list)

        ch_input_layout = QHBoxLayout()
        self.new_channel_input = QLineEdit()
        self.new_channel_input.setPlaceholderText("Nom du salon...")
        self.add_ch_btn = QPushButton("Ajouter")
        self.remove_ch_btn = QPushButton("Supprimer")
        self.add_ch_btn.clicked.connect(self.add_channel)
        self.remove_ch_btn.clicked.connect(self.remove_channel)
        ch_input_layout.addWidget(self.new_channel_input)
        ch_input_layout.addWidget(self.add_ch_btn)
        ch_input_layout.addWidget(self.remove_ch_btn)
        self.layout.addLayout(ch_input_layout)

        self.ban_input = QLineEdit()
        self.ban_input.setPlaceholderText("IP à bannir/débannir")
        self.ban_btn = QPushButton("Basculer ban")
        self.ban_btn.clicked.connect(self.toggle_ban)
        self.layout.addWidget(QLabel("Bannir/Débannir une IP :"))
        self.layout.addWidget(self.ban_input)
        self.layout.addWidget(self.ban_btn)

        self.launch_btn = QPushButton("Lancer le serveur")
        self.launch_btn.clicked.connect(self.launch_server)
        self.layout.addWidget(self.launch_btn)

        self.setLayout(self.layout)

    def add_channel(self):
        name = self.new_channel_input.text().strip()
        if name and name not in channels:
            channels.append(name)
            self.channels_list.addItem(name)
            path = f"{MESSAGES_PATH}{name}.json"
            with open(path, "w") as f:
                json.dump([], f)
            self.new_channel_input.clear()

    def remove_channel(self):
        selected = self.channels_list.currentItem()
        if selected:
            ch = selected.text()
            if ch in channels:
                channels.remove(ch)
                os.remove(f"{MESSAGES_PATH}{ch}.json")
                self.channels_list.takeItem(self.channels_list.row(selected))

    def toggle_ban(self):
        ip = self.ban_input.text().strip()
        if ip:
            if ip in banned_ips:
                banned_ips.remove(ip)
                QMessageBox.information(self, "Débanni", f"{ip} a été débanni.")
            else:
                banned_ips.add(ip)
                QMessageBox.information(self, "Banni", f"{ip} a été banni.")
            self.ban_input.clear()

    def launch_server(self):
        global server_thread
        config["server_name"] = self.name_input.text()
        save_config()
        self.hide()
        server_thread = threading.Thread(target=start_server, daemon=False)
        server_thread.start()

if __name__ == "__main__":
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w") as f:
            json.dump({"server_name": "Wormcord", "channels": ["général"], "banned_ips": []}, f)

    load_config()

    app = QApplication(sys.argv)
    window = AdminGUI()
    window.show()
    app.exec_()

    # attend que le thread serveur se termine avant de quitter
    if server_thread is not None:
        server_thread.join()
