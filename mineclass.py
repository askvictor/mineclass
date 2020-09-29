from PyQt5 import QtCore, QtWebSockets,  QtNetwork
from PyQt5.QtWidgets import QWidget, QPushButton, QApplication, QLabel, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem, \
    QComboBox, QInputDialog, QMessageBox, QHeaderView, QPlainTextEdit, QStackedLayout, QLineEdit, QFileDialog
from PyQt5.QtCore import QSettings, QTimer
from PyQt5.QtGui import QColor
from pyqtgraph import PlotWidget, ScatterPlotItem, mkBrush
import json
import uuid
import datetime
import socket

PORT = 65456

#TODO
# Notification when player uses a potion? subscribe to "ItemAcquired" or "ItemUsed" WON'T WORK! Only seems to work for your own items
# Secure websockets Probably can't do in QT (easily)

#Notes
#some useful protocol info at https://github.com/Sandertv/mcwss

subscribe_cmd = json.dumps({
    "body": {
        "eventName": "PlayerMessage"
    },
    "header": {
        "requestId": "00000000-0000-0000-0000-000000000000",
        "messagePurpose": "subscribe",
        "version": 1,
        "messageType": "commandRequest"
    }
})


class WSServer(QtCore.QObject):
    def __init__(self, parent, settings, address="0.0.0.0", port=PORT):
        super(QtCore.QObject, self).__init__(parent)
        self.settings = settings
        self.server = QtWebSockets.QWebSocketServer(parent.serverName(), parent.secureMode(), parent)
        if self.server.listen(QtNetwork.QHostAddress(address), port):
            print('Listening: '+self.server.serverName()+' : '+self.server.serverAddress().toString()+':'+str(self.server.serverPort()))
        else:
            print('error')
        self.server.newConnection.connect(self.on_new_connection)
        self.clientConnection = None

        self.gui = None

        self.msg_responses = None
        self.msg_uuids = None

        self.users = {}
        self.self_name = None

        print(self.server.isListening())

    def on_new_connection(self):
        self.clientConnection = self.server.nextPendingConnection()
        self.clientConnection.textMessageReceived.connect(self.process_text_message)

        self.clientConnection.disconnected.connect(self.socket_disconnected)
        self.msg_uuids = {}
        self.msg_responses = {}

        self.clientConnection.sendTextMessage(subscribe_cmd)
        self.get_self()
        gui.stack.setCurrentIndex(1)
        gui.activate_buttons(True)
        gui.start_timer()
        print("client connected")

    def process_text_message(self, message):
        if self.clientConnection:
            print(message)
            data = json.loads(message)
            msg_uuid = data['header']['requestId']
            if msg_uuid in self.msg_uuids and data['header']['messagePurpose'] == "commandResponse":
                #update user list TODO - save timestamps of who's in the game and when?
                if self.msg_uuids[msg_uuid] == 'listd':
                    current_users = []
                    for e in json.loads(data['body']['details'][4:-4])['result']:
                        current_uuid = e['uuid']
                        current_users.append(current_uuid)
                        if current_uuid in self.users:
                            self.users[current_uuid]['name'] = e['name']
                        else:
                            self.users[current_uuid] = {'name': e['name'], 'present': True}
                    for current_uuid in list(self.users.keys()):
                        if current_uuid not in current_users:
                            del self.users[current_uuid]
                    self.gui.update_users_from_mc([user['name'] for user in self.users.values()])

                elif self.msg_uuids[msg_uuid] == "querytarget @a":
                    current_users = []
                    for e in json.loads(data['body']['details']):
                        current_uuid = e['uniqueId']
                        current_users.append(current_uuid)
                        if current_uuid in self.users:
                            self.users[current_uuid]['dimension'] = e['dimension']
                            self.users[current_uuid]['position'] = e['position']
                        else:
                            self.users[current_uuid] = {'dimension': e['dimension'], 'position': e['position'], 'present': True}
                    for current_uuid in list(self.users.keys()):
                        if current_uuid not in current_users:
                            del self.users[current_uuid]
                    self.gui.update_map(self.users)
                elif self.msg_uuids[msg_uuid] == "getlocalplayername":
                    self.self_name = data['body']['localplayername']

            elif data['body']['eventName'] == 'PlayerMessage':
                sender = data['body']['properties']['Sender']
                message_type = data['body']['properties']['MessageType']
                message = data['body']['properties']['Message']
                gui.update_chat_box(sender, message, message_type)


    def socket_disconnected(self):
        print('client disconnected')
        gui.stack.setCurrentIndex(0)
        gui.activate_buttons(False)
        gui.stop_timer()
        if self.clientConnection:
            self.clientConnection.deleteLater()

    def send_chat(self, text):
        return self.send_command(f"say {text}")

    def unpause_game(self):
        return self.send_command("globalpause false")

    def pause_game(self):
        return self.send_command("globalpause true")

    def mutable_world(self):
        return self.send_command("immutableworld false")

    def immutable_world(self):
        return self.send_command("immutableworld true")

    def allow_destructiveobjects(self):
        return self.send_command("gamerule allowdestructiveobjects true")

    def disallow_destructiveobjects(self):
        return self.send_command("gamerule allowdestructiveobjects false")

    def allow_player_damage(self):
        self.send_command("gamerule falldamage true")
        self.send_command("gamerule drowningdamage true")
        self.send_command("gamerule firedamage true")

    def disallow_player_damage(self):
        self.send_command("gamerule falldamage false")
        self.send_command("gamerule drowningdamage false")
        self.send_command("gamerule firedamage false")

    def allow_pvp(self):
        return self.send_command("gamerule pvp true")

    def disallow_pvp(self):
        return self.send_command("gamerule pvp false")

    def allow_mobs(self):
        return self.send_command("gamerule allowmobs true")

    def disallow_mobs(self):
        return self.send_command("gamerule allowmobs false")

    def enable_chat(self):
        return self.send_command("gamerule globalmute false")

    def disable_chat(self):
        return self.send_command("gamerule globalmute true")

    def perfect_weather(self):
        self.send_command("weather clear")
        self.send_command("gamerule doWeatherCycle false")

    def imperfect_weather(self):
        return self.send_command("gamerule doWeatherCycle true")

    def teleport_all_to(self, location="@s"):
        return self.send_command(f"tp @a {location}")

    def clear_effects(self, who="@a"):
        return self.send_command(f"effect {who} clear")

    def get_users(self):
        return self.send_command('listd') and self.send_command('querytarget @a')

    def get_self(self):
        self.self_name = None
        return self.send_command('getlocalplayername')

    def send_command(self, cmd, await_response=False):
        print(cmd)
        if not self.clientConnection:
            return False
        msg_uuid = str(uuid.uuid1())
        msg = json.dumps({
            "body": {
                "origin": {
                    "type": "player"
                },
                "commandLine": cmd,
                "version": 1
            },
            "header": {
                "requestId": msg_uuid,
                "messagePurpose": "commandRequest",
                "version": 1,
                "messageType": "commandRequest"
            }
        })
        self.msg_uuids[msg_uuid] = cmd
        self.clientConnection.sendTextMessage(msg)
        return True
        # if await_response:
        #     while True:
        #         if msg_uuid in self.msg_responses:
        #             response = self.msg_responses[msg_uuid]
        #             self.msg_response_mutex.lock()
        #             del self.msg_responses[msg_uuid]
        #             self.msg_response_mutex.unlock()
        #             return response
        #         time.sleep(0.1)

    @staticmethod
    def get_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP



class MCClassroom(QWidget):
    def __init__(self, settings, server):
        super().__init__()

        self.server = server
        self.timer = QTimer()
        self.timer.timeout.connect(self.time_tick)

        self.settings = settings
        self.current_class = None
        self.current_students = []

        self.stack = QStackedLayout()
        self.setLayout(self.stack)

        # First page: connection instructions
        connect_widget = QWidget()
        connect_layout = QVBoxLayout(connect_widget)
        connect_layout.addStretch()
        connect_label = QLabel("Open a world in Minecraft, open a terminal (press t), and type:", self)
        connect_layout.addWidget(connect_label)
        self.connect_command = f'/connect {server.get_ip()}:{PORT}'
        connect_command_box = QLineEdit(self.connect_command, self)
        connect_command_box.setReadOnly(True)
        connect_layout.addWidget(connect_command_box)
        connect_copy_button = QPushButton("Copy to Clipboard", self)
        connect_copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.connect_command))
        connect_layout.addWidget(connect_copy_button)
        connection_problems_button = QPushButton("Connection Problems?", self)
        connection_problems_button.clicked.connect(self.show_connection_help)
        connect_layout.addWidget(connection_problems_button)
        connect_layout.addStretch()
        self.stack.addWidget(connect_widget)

        # Main page
        main_col_widget = QWidget()
        columns = QHBoxLayout(main_col_widget)
        col_left = QVBoxLayout()
        col_mid = QVBoxLayout()
        col_right = QVBoxLayout()
        columns.addLayout(col_left)
        columns.addSpacing(10)
        columns.addLayout(col_mid)
        columns.addSpacing(10)
        columns.addLayout(col_right)
        self.stack.addWidget(main_col_widget)

        self.pause_button = self.setup_toggle_button(col_left, self.server.pause_game, 'Un-pause',
                                                     self.server.unpause_game, 'Pause')
        self.disable_chat_button = self.setup_toggle_button(col_left, self.server.disable_chat, 'Enable Chat',
                                                self.server.enable_chat, 'Disable Chat')
        self.allow_mobs_button = self.setup_toggle_button(col_left, self.server.disallow_mobs, 'Allow Mobs',
                                                self.server.allow_mobs, 'Disable Mobs')
        self.allow_destructiveobjects_button = self.setup_toggle_button(col_left, self.server.disallow_destructiveobjects, 'Enable Destructive Items',
                                                self.server.allow_destructiveobjects, 'Disable Destructive Items')
        self.allow_player_damage_button = self.setup_toggle_button(col_left, self.server.disallow_player_damage, 'Enable Player Damage',
                                                self.server.allow_player_damage, 'Disable Player Damage')
        self.allow_pvp_button = self.setup_toggle_button(col_left, self.server.disallow_pvp, 'Allow Player Fighting',
                                                self.server.allow_pvp, 'Disable Player Fighting')
        self.immutable_button = self.setup_toggle_button(col_left, self.server.immutable_world, 'Enable World Modifications',
                                                         self.server.mutable_world, 'Disable World Modifications')
        self.weather_button = self.setup_toggle_button(col_left, self.server.perfect_weather, 'Disable Perfect Weather',
                                                         self.server.imperfect_weather, 'Enable Perfect Weather')

        self.clear_potions_button = QPushButton('Clear All Potion Effects', self)
        self.clear_potions_button.resize(self.clear_potions_button.sizeHint())
        self.clear_potions_button.clicked.connect(lambda: self.server.clear_effects("@a"))
        col_left.addWidget(self.clear_potions_button)

        self.teleport_button = QPushButton('Teleport Everyone to You', self)
        self.teleport_button.resize(self.teleport_button.sizeHint())
        self.teleport_button.clicked.connect(lambda: self.server.teleport_all_to("@s"))
        col_left.addWidget(self.teleport_button)

        self.disconnect_button = QPushButton('Disconnect', self)
        self.disconnect_button.resize(self.disconnect_button.sizeHint())
        self.disconnect_button.clicked.connect(self.server.socket_disconnected)
        col_left.addWidget(self.disconnect_button)
        self.disconnect_button.setFixedWidth(140)

        col_left.addStretch()

        # Middle Column: Roll/Register
        self.classes_combo = QComboBox(self)
        class_names = self.settings.value("class_names", [])
        self.classes_combo.addItem("Select class")
        self.classes_combo.addItem("Add a class")
        self.classes_combo.addItem("Delete a class")
        self.classes_combo.addItems(class_names)
        self.classes_combo.currentTextChanged.connect(self.class_changed)
        col_mid.addWidget(self.classes_combo)

        self.users_table = QTableWidget(0, 2)
        self.users_table.setFixedWidth(140)
        self.users_table.verticalHeader().hide()
        header = self.users_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.hide()
        col_mid.addWidget(self.users_table)

        self.class_edit_button = QPushButton("Edit Class", self)
        col_mid.addWidget(self.class_edit_button)
        self.class_edit_button.clicked.connect(self.edit_class)

        self.chat_box = QPlainTextEdit(f'Minecraft Education Chat Logs {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', self)
        self.chat_box.setReadOnly(True)
        col_right.addWidget(self.chat_box)

        self.chat_input = QLineEdit(self)
        self.chat_input.setPlaceholderText("Type chat here; enter to send")
        self.chat_input.returnPressed.connect(self.chat_enter)
        col_right.addWidget(self.chat_input)

        self.chat_save = QPushButton("Save Chat Logs", self)
        self.chat_save.clicked.connect(self.save_chat)
        col_right.addWidget(self.chat_save)

        self.user_map = PlotWidget()
        self.map_item = ScatterPlotItem(size=10)
        self.user_map.addItem(self.map_item)
        self.user_map.getPlotItem().hideAxis('left')
        self.user_map.getPlotItem().hideAxis('bottom')
        self.map_item.scene().sigMouseMoved.connect(self.map_hover)
        map_viewbox = self.map_item.getViewBox()
        map_viewbox.menu = None
        col_right.addWidget(self.user_map)

        self.user_map_info = QLineEdit("Hover over a user", self)
        self.user_map_info.setReadOnly(True)
        col_right.addWidget(self.user_map_info)

        self.setGeometry(300, 300, 800, 600)
        self.setWindowTitle('MineClass')

        self.stack.setCurrentIndex(0)
        self.activate_buttons(False)
        self.show()
        if not self.settings.value("HasRunFirstTime", False):
            self.show_connection_help()
            self.settings.setValue("HasRunFirstTime", True)

    def show_connection_help(self):
        QMessageBox.about(self, "Connection Help", '''Before using (or if Minecraft has been newly installed), go to Settings->Profile and disable "Require Encrypted Websockets"\n\n
Sometimes you'll need to attempt connecting twice (use the up arrow in the Minecraft terminal to access history''')

    def save_chat(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Chat Logs", "", "Text Files (*.txt);;All Files (*)", options=options)
        if file_name:
            with open(file_name, "w") as f:
                f.write(self.chat_box.toPlainText())

    def chat_enter(self):
        server.send_chat(self.chat_input.text())
        self.update_chat_box("Teacher", self.chat_input.text(), "chat")
        self.chat_input.clear()

    def map_hover(self, pos):
        act_pos = self.map_item.mapFromScene(pos)
        points = self.map_item.pointsAt(act_pos)

        text = ""
        for p in points:
            text += f'{p.data()}: ({round(p.pos()[0])}, {round(p.pos()[1])}), '
        self.user_map_info.setText(text)

    def time_tick(self):
        self.server.get_users()

    def start_timer(self):
        self.time_tick()
        self.timer.start(10000)

    def stop_timer(self):
        self.timer.stop()

    def update_chat_box(self, sender, message, message_type, receiver=None):
        t = datetime.datetime.now().strftime("%H:%M:%S")
        if message_type == "chat":
            out = f'{t} <{sender}> {message}'
        elif message_type == "tell":
            out = f'{t} <{sender} whispers to {receiver}> {message}'
        self.chat_box.appendPlainText(out)

    def activate_buttons(self, activate):
        self.pause_button.setDisabled(not activate)

    def setup_toggle_button(self, parent, checked_action, checked_text, unchecked_action, unchecked_text):
        button = QPushButton(unchecked_text, self)
        button.resize(button.sizeHint())
        button.setCheckable(True)
        parent.addWidget(button)
        def toggle_button_clicked(checked_status):
            if checked_status:
                checked_action()
                button.setText(checked_text)
            else:
                unchecked_action()
                button.setText(unchecked_text)
        button.toggled.connect(toggle_button_clicked)
        return button

    def get_students_from_grid(self):
        try:
            return [self.users_table.item(i, 0).text() for i in range(self.users_table.rowCount())]
        except AttributeError:
            return []

    def edit_class(self):
        selection = self.classes_combo.currentText()
        if selection in ("Select class", "Add a class"):
            QMessageBox.about(self, "Error", "Please select (or create) a class first")
            return

        current_list = self.get_students_from_grid()
        new_list, ok_pressed = QInputDialog().getMultiLineText(self, "Edit Class List",
                                                                    "Add or remove students from this class",
                                                                    text="\n".join(current_list))
        if ok_pressed:
            students = [i for i in new_list.split("\n") if i]  # list comprehension to remove empty strings
            self.current_students = students
            self.settings.setValue(f'classes/{self.current_class}', students)
            self.load_users()

    def class_changed(self):
        selection = self.classes_combo.currentText()
        # if selection != "Select class":
        #     self.classes_combo.removeItem(self.classes_combo.findText("Select class"))
        if selection == "Add a class":
            new_class, ok_pressed = QInputDialog.getText(self, 'Class Name', 'Enter the Class Name or Code')
            if ok_pressed:
                classes = self.settings.value('class_names', [])
                if new_class in classes:
                    print('Class already exists; ignoring')
                else:
                    classes.append(new_class)
                    self.settings.setValue('class_names', classes)
                    self.classes_combo.addItem(new_class)
                self.classes_combo.setCurrentIndex(self.classes_combo.findText(new_class))
        elif selection == "Select class":
            pass
        elif selection == "Delete a class":
            current_classes = self.settings.value('class_names', [])
            if current_classes:
                class_to_delete, ok_pressed = QInputDialog.getItem(self, 'Delete Class', 'Select which class to delete', current_classes, 0, False)
                if ok_pressed and class_to_delete:
                    current_classes.remove(class_to_delete)
                    self.settings.setValue('class_names', current_classes)
                    self.settings.remove(f'classes/{class_to_delete}')
                    self.classes_combo.removeItem(self.classes_combo.findText(class_to_delete))
                    #TODO delete stdents from table
                    self.current_class = None
                    self.current_students = []
            else:
                QMessageBox.information(self, "No Classes!", "No Class to delete!")
            self.classes_combo.setCurrentIndex(0)
        else:
            self.current_class = selection
            self.current_students = self.settings.value(f'classes/{selection}', [])
            self.load_users()

    def load_users(self):
        if len(self.current_students) != self.users_table.rowCount():
            self.users_table.setRowCount(len(self.current_students))
        for i, user in enumerate(self.current_students):
            self.users_table.setItem(i, 0, QTableWidgetItem(user))
        self.users_table.sortItems(0, QtCore.Qt.AscendingOrder)
        self.users_table.sortItems(1, QtCore.Qt.DescendingOrder)

    def update_users_from_mc(self, users):
        table_user_count = self.users_table.rowCount()
        for i in range(table_user_count):
            current_table_user = self.users_table.item(i, 0).text()
            if current_table_user in users:
                tick = QTableWidgetItem("✓")
                tick.setTextAlignment(QtCore.Qt.AlignCenter)
                tick.setBackground(QColor(QtCore.Qt.green))
                self.users_table.setItem(i, 1, tick)
                users.remove(current_table_user)
            else:
                cross = QTableWidgetItem("✗")
                cross.setTextAlignment(QtCore.Qt.AlignCenter)
                cross.setBackground(QColor(QtCore.Qt.red))
                self.users_table.setItem(i, 1, cross)

        #handle users from server but not in table
        self.users_table.setRowCount(table_user_count + len(users))
        for i, user in enumerate(users):
            self.users_table.setItem(i+table_user_count, 0, QTableWidgetItem(user))

        self.users_table.sortItems(0, QtCore.Qt.AscendingOrder)
        self.users_table.sortItems(1, QtCore.Qt.DescendingOrder)

    def update_map(self, users):
        data = [{'pos': (int(u['position']['x']), int(u['position']['z'])),
                 'data': u['name'],
                 'brush': mkBrush('g'),  #mkBrush("r" if u['name'] == self.server.self_name else "g"),
                 'symbol': ("s" if u['name'] == self.server.self_name else "o"),
                } for u in users.values()]
        self.map_item.setData(data)
        #map(lambda x: "Red" if x['name'] == self.server.self_name else "Green",  users.values())

        # self.map_item.setData(x=[int(u['position']['x']) for u in users.values()],
        #                       y=[int(u['position']['z']) for u in users.values()],
        #                       data=[u['name'] for u in users.values()])


if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)
    settings = QSettings("PositiveState", "MC Classroom")
    serverObject = QtWebSockets.QWebSocketServer('My Socket', QtWebSockets.QWebSocketServer.NonSecureMode)
    server = WSServer(serverObject, settings, address='0.0.0.0')
    gui = MCClassroom(settings, server)
    server.gui = gui
    serverObject.closed.connect(app.quit)
    app.exec_()

