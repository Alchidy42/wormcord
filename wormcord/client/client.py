# client/main.py

import os
import sys
import json
import socket
import threading
import hashlib

from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QListWidget, QTextEdit, QLineEdit, QInputDialog,
    QMessageBox, QMenu, QFrame
)
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor, QFont
from PyQt5.QtCore import Qt, QPoint

USER_DATA_PATH = os.path.expanduser("~/.wormcord_user_data.json")

def load_user_data():
    if not os.path.exists(USER_DATA_PATH):
        data = {"username": "", "recent_servers": []}
        os.makedirs(os.path.dirname(USER_DATA_PATH), exist_ok=True)
        with open(USER_DATA_PATH, "w") as f:
            json.dump(data, f, indent=2)
    with open(USER_DATA_PATH, "r") as f:
        return json.load(f)

def save_user_data(data):
    with open(USER_DATA_PATH, "w") as f:
        json.dump(data, f, indent=2)

class WormcordClient(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wormcord")
        self.setMinimumSize(1000, 650)

        # Palette
        self.bg_color = "#1e1f29"
        self.accent_color = "#282a36"
        self.text_color = "#eee"
        self.highlight = "#44475a"

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {self.bg_color};
                color: {self.text_color};
                font-family: "Segoe UI", sans-serif;
            }}
            QFrame#panel {{
                background-color: {self.accent_color};
                border-radius: 8px;
            }}
            QListWidget {{
                padding: 5px;
                border: none;
                background-color: transparent;
            }}
            QListWidget::item {{
                padding: 8px;
                margin: 2px 0;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {self.highlight};
            }}
            QTextEdit {{
                background-color: {self.accent_color};
                border: none;
                padding: 10px;
                border-radius: 8px;
            }}
            QLineEdit {{
                background-color: {self.accent_color};
                border: none;
                padding: 8px;
                border-radius: 8px;
            }}
            QLineEdit:focus {{
                border: 1px solid {self.highlight};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 0 0 0 0;
            }}
            QScrollBar::handle:vertical {{
                background: {self.highlight};
                min-height: 20px;
                border-radius: 4px;
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{
                height: 0;
            }}
        """)

        # Données utilisateur
        self.user_data = load_user_data()
        self.username = self.user_data.get("username", "")
        while not self.username:
            pseudo, ok = QInputDialog.getText(self, "Ton pseudo", "Entrez votre pseudo :")
            if ok and pseudo.strip():
                self.username = pseudo.strip()
                self.user_data["username"] = self.username
                save_user_data(self.user_data)
            else:
                QMessageBox.warning(self, "Pseudo requis", "Le pseudo ne peut pas être vide.")

        self.server_addr = None
        self.channels = []
        self.messages = {}
        self.current_channel = None
        self.sock = None

        self.build_ui()

    def build_ui(self):
        # Splitter principal
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        # Panel Serveurs
        servers_frame = QFrame()
        servers_frame.setObjectName("panel")
        v1 = QVBoxLayout(servers_frame)
        v1.setContentsMargins(10, 10, 10, 10)
        self.server_list = QListWidget()
        self.server_list.addItem("➕ Ajouter un serveur")
        for srv in self.user_data["recent_servers"]:
            self.server_list.addItem(srv)
        self.server_list.itemClicked.connect(self.select_server)
        self.server_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.server_list.customContextMenuRequested.connect(self.on_server_context_menu)
        v1.addWidget(self.server_list)
        splitter.addWidget(servers_frame)

        # Panel Salons
        channels_frame = QFrame()
        channels_frame.setObjectName("panel")
        v2 = QVBoxLayout(channels_frame)
        v2.setContentsMargins(10, 10, 10, 10)
        self.channel_list = QListWidget()
        self.channel_list.itemClicked.connect(self.select_channel)
        v2.addWidget(self.channel_list)
        splitter.addWidget(channels_frame)

        # Panel Chat
        chat_frame = QFrame()
        chat_frame.setObjectName("panel")
        v3 = QVBoxLayout(chat_frame)
        v3.setContentsMargins(10, 10, 10, 10)
        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)
        self.chat_box.setFont(QFont("Consolas", 10))
        v3.addWidget(self.chat_box)
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Tapez votre message…")
        self.input_box.returnPressed.connect(self.send_message)
        v3.addWidget(self.input_box)
        splitter.addWidget(chat_frame)

        # Ratio par défaut
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 3)

        # Layout principal
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(splitter)

    def on_server_context_menu(self, pos):
        item = self.server_list.itemAt(pos)
        if item and not item.text().startswith("➕"):
            menu = QMenu()
            delete_action = menu.addAction("Supprimer")
            if menu.exec_(self.server_list.mapToGlobal(pos)) == delete_action:
                addr = item.text()
                row = self.server_list.row(item)
                self.server_list.takeItem(row)
                if addr in self.user_data["recent_servers"]:
                    self.user_data["recent_servers"].remove(addr)
                    save_user_data(self.user_data)
                if self.server_addr == addr and self.sock:
                    self.sock.close()
                    self.server_addr = None
                    self.channel_list.clear()
                    self.chat_box.clear()

    def select_server(self, item):
        addr = item.text()
        if addr.startswith("➕"):
            addr, ok = QInputDialog.getText(self, "Ajouter un serveur", "Adresse IP:Port")
            if not ok or not addr.strip():
                return
            addr = addr.strip()
            if addr not in self.user_data["recent_servers"]:
                self.user_data["recent_servers"].insert(0, addr)
                save_user_data(self.user_data)
                self.server_list.insertItem(1, addr)
        self.connect_to(addr)

    def connect_to(self, addr):
        try:
            host, port = addr.split(":")
            port = int(port)
        except ValueError:
            QMessageBox.critical(self, "Adresse invalide", "Le format doit être IP:Port")
            return

        try:
            new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            new_sock.settimeout(5)
            new_sock.connect((host, port))
        except Exception as e:
            QMessageBox.critical(self, "Erreur de connexion", f"Impossible de joindre {addr} :\n{e}")
            return

        if self.sock:
            try: self.sock.close()
            except: pass
        self.sock = new_sock
        self.sock.settimeout(None)
        self.server_addr = addr

        threading.Thread(target=self.listen, daemon=True).start()

        join_msg = json.dumps({"type": "join", "username": self.username}) + "\n"
        self.sock.send(join_msg.encode())

    def select_channel(self, item):
        ch = item.text()
        if ch not in self.channels:
            return
        self.current_channel = ch
        self.chat_box.clear()
        for msg in self.messages.get(ch, []):
            self.display_message(msg["username"], msg["content"])

    def listen(self):
        import time
        while True:
            try:
                data = self.sock.recv(4096)
                if not data:
                    raise ConnectionError("Déconnecté")
                for line in data.decode().split("\n"):
                    if not line.strip(): continue
                    msg = json.loads(line)
                    if msg["type"] == "banned":
                        QMessageBox.critical(self, "Banni", msg.get("reason", "Vous êtes banni."))
                        self.sock.close()
                        return
                    if msg["type"] == "channels":
                        self.channels = msg["channels"]
                        self.channel_list.clear()
                        for ch in self.channels:
                            self.channel_list.addItem(ch)
                    elif msg["type"] == "history":
                        self.messages[msg["channel"]] = msg["messages"]
                    elif msg["type"] == "message":
                        ch = msg["channel"]
                        self.messages.setdefault(ch, []).append(msg)
                        if ch == self.current_channel:
                            self.display_message(msg["username"], msg["content"])
            except Exception as e:
                print("Écoute interrompue :", e)
                return

    def send_message(self):
        if not self.current_channel: return
        content = self.input_box.text().strip()
        if not content: return
        self.input_box.clear()
        packet = {"type": "message", "channel": self.current_channel, "content": content}
        try:
            self.sock.send((json.dumps(packet)+"\n").encode())
        except Exception as e:
            QMessageBox.critical(self, "Erreur envoi", str(e))

    def display_message(self, username, content):
        cursor = self.chat_box.textCursor()
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self.pseudo_color(username)))
        cursor.setCharFormat(fmt)
        cursor.insertText(f"{username}: ")
        fmt.setForeground(QColor(self.text_color))
        cursor.setCharFormat(fmt)
        cursor.insertText(f"{content}\n")
        self.chat_box.moveCursor(QTextCursor.End)

    def pseudo_color(self, pseudo):
        h = hashlib.sha256(pseudo.encode()).hexdigest()
        return f"#{h[:6]}"

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = WormcordClient()
    win.show()
    sys.exit(app.exec_())
