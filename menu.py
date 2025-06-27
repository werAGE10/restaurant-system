import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
import os
import hashlib

class RestaurantSystem:
    def __init__(self):
        load_dotenv()
        cred_path = os.getenv('FIREBASE_CREDENTIALS')
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        
        self.db = firestore.client()
        self.current_user = None
        self.init_data()
        self.load_data()

    def init_data(self):
        """Инициализация начальных данных"""
        # Меню
        default_menu = {
            '1': {'name': 'Стейк', 'price': 1200, 'category': 'Основные блюда'},
            '2': {'name': 'Салат Цезарь', 'price': 450, 'category': 'Закуски'},
            '3': {'name': 'Паста Карбонара', 'price': 680, 'category': 'Основные блюда'},
            '4': {'name': 'Суп Том Ям', 'price': 550, 'category': 'Супы'},
            '5': {'name': 'Тирамису', 'price': 350, 'category': 'Десерты'},
            '6': {'name': 'Минеральная вода', 'price': 150, 'category': 'Напитки'},
            '7': {'name': 'Кофе латте', 'price': 250, 'category': 'Напитки'}
        }
        
        menu_ref = self.db.collection('menu')
        if not menu_ref.get():
            for item_id, item_data in default_menu.items():
                menu_ref.document(item_id).set(item_data)
        
        # Столы
        tables_ref = self.db.collection('tables')
        if not tables_ref.get():
            for table_num in range(1, 11):
                tables_ref.document(str(table_num)).set({
                    'number': table_num,
                    'capacity': 4 if table_num <= 5 else 2,
                    'status': 'свободен',
                    'current_order': None,
                    'reservation': None,
                    'client_name': None
                })

        # Персонал
        staff_ref = self.db.collection('staff')
        if not staff_ref.get():
            staff = {
                '1': {'name': 'Иван Иванов', 'position': 'официант', 'login': 'ivan', 'password': self.hash_password('ivan123'), 'shifts': []},
                '2': {'name': 'Мария Петрова', 'position': 'официант', 'login': 'maria', 'password': self.hash_password('maria123'), 'shifts': []},
                '3': {'name': 'Алексей Смирнов', 'position': 'администратор', 'login': 'admin', 'password': self.hash_password('admin123'), 'shifts': []}
            }
            for staff_id, staff_data in staff.items():
                staff_ref.document(staff_id).set(staff_data)

    def hash_password(self, password):
        """Хеширование пароля"""
        return hashlib.sha256(password.encode()).hexdigest()

    def load_data(self):
        """Загрузка данных из Firebase"""
        self.menu = {doc.id: doc.to_dict() for doc in self.db.collection('menu').stream()}
        
        # Для столиков добавляем проверку на наличие capacity
        self.tables = {}
        for doc in self.db.collection('tables').stream():
            table_data = doc.to_dict()
            if 'capacity' not in table_data:
                table_data['capacity'] = 4 if int(doc.id) <= 5 else 2
            self.tables[int(doc.id)] = table_data
        
        self.orders = {int(doc.id): doc.to_dict() for doc in self.db.collection('orders').stream()}
        self.staff = {doc.id: doc.to_dict() for doc in self.db.collection('staff').stream()}
        self.clients = {doc.id: doc.to_dict() for doc in self.db.collection('clients').stream()}
        
        # Загрузка бронирований с проверкой обязательных полей
        self.reservations = {}
        for doc in self.db.collection('reservations').stream():
            res = doc.to_dict()
            if all(key in res for key in ['table_number', 'status', 'datetime']):
                self.reservations[doc.id] = res
        
        self.order_id_counter = max(self.orders.keys()) + 1 if self.orders else 1

    def login_gui(self, login, password):
        """Авторизация пользователя для GUI"""
        password_hash = self.hash_password(password)
        
        for staff_id, staff_data in self.staff.items():
            if staff_data['login'] == login and staff_data['password'] == password_hash:
                self.current_user = {
                    'id': staff_id,
                    'name': staff_data['name'],
                    'position': staff_data['position']
                }
                return True
        
        return False

    def create_reservation_gui(self, client_name, phone, date_str, time_str, guests_str, table_str):
        """Создание бронирования для GUI"""
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
            
            if dt < datetime.now():
                raise ValueError("Нельзя бронировать на прошедшую дату!")
                
            table_num = int(table_str)
            if table_num not in self.tables:
                raise ValueError("Столик с таким номером не существует!")
                
            guests = int(guests_str)
            if guests <= 0:
                raise ValueError("Количество гостей должно быть положительным числом!")
                
            if guests > self.tables[table_num].get('capacity', 4):
                raise ValueError(f"Столик вмещает только {self.tables[table_num].get('capacity', 4)} гостей!")
                
        except ValueError as e:
            raise ValueError(f"Ошибка ввода данных: {str(e)}")
        
        # Проверка доступности столика
        table = self.tables[table_num]
        if table.get('status') != 'свободен':
            raise ValueError(f"Столик {table_num} уже занят или забронирован!")
        
        # Проверка конфликтов бронирований
        for res in self.reservations.values():
            if (res.get('table_number') == table_num and 
                res.get('status') == 'подтверждено'):
                
                res_dt = res.get('datetime')
                if isinstance(res_dt, str):
                    try:
                        res_dt = datetime.strptime(res_dt, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue
                
                if abs((dt - res_dt).total_seconds()) < 7200:
                    raise ValueError(f"Столик уже забронирован на {res_dt.strftime('%d.%m.%Y %H:%M')}!")
        
        # Создание бронирования
        res_data = {
            'client_name': client_name,
            'phone': phone,
            'guests': guests,
            'table_number': table_num,
            'datetime': dt,
            'status': 'подтверждено',
            'created_at': datetime.now(),
            'created_by': self.current_user['id']
        }
        
        res_ref = self.db.collection('reservations').document()
        res_ref.set(res_data)
        
        # Обновление статуса столика
        self.db.collection('tables').document(str(table_num)).update({
            'status': 'забронирован',
            'client_name': client_name,
            'reservation': res_ref.id
        })
        
        self.load_data()
        return f"Бронирование создано! Номер: {res_ref.id}"

    def cancel_reservation_gui(self, res_id):
        """Отмена бронирования для GUI"""
        if res_id not in self.reservations:
            raise ValueError("Бронирование не найдено!")
        
        res = self.reservations[res_id]
        table_num = res.get('table_number')
        
        if not table_num:
            raise ValueError("У бронирования отсутствует номер столика!")
        
        # Обновляем статус брони
        self.db.collection('reservations').document(res_id).update({
            'status': 'отменено',
            'cancelled_at': datetime.now(),
            'cancelled_by': self.current_user['id']
        })
        
        # Освобождаем столик
        self.db.collection('tables').document(str(table_num)).update({
            'status': 'свободен',
            'client_name': None,
            'reservation': None
        })
        
        self.load_data()
        return "Бронирование отменено!"

    def take_order_gui(self, table_num, client_name, order_items):
            """Прием заказа для GUI"""
            try:
                table_num = int(table_num)
                if table_num not in self.tables:
                    raise ValueError("Столик с таким номером не существует!")
                    
                if self.tables[table_num]['status'] != 'свободен':
                    raise ValueError("Столик уже занят или забронирован!")
                    
                if not client_name:
                    raise ValueError("Имя клиента обязательно!")
                    
                if not order_items:
                    raise ValueError("Заказ не может быть пустым!")
                    
                # Преобразуем данные блюд в правильный формат
                formatted_items = []
                for item in order_items:
                    formatted_items.append({
                        'id': item['id'],
                        'name': item['name'],
                        'price': float(item['price']),
                        'quantity': int(item['quantity'])
                    })
                    
            except ValueError as e:
                raise ValueError(f"Ошибка ввода данных: {str(e)}")
            
            # Расчет суммы
            total = sum(item['price'] * item['quantity'] for item in formatted_items)
            
            # Создание заказа
            order_data = {
                'table': table_num,
                'client_name': client_name,
                'waiter_id': self.current_user['id'],
                'waiter_name': self.current_user['name'],
                'items': formatted_items,
                'total': total,
                'status': 'принят',
                'created_at': datetime.now()
            }
            
            # Сохранение в Firebase
            order_ref = self.db.collection('orders').document(str(self.order_id_counter))
            order_ref.set(order_data)
            
            # Обновление статуса столика
            self.db.collection('tables').document(str(table_num)).update({
                'status': 'занят',
                'client_name': client_name,
                'current_order': self.order_id_counter
            })
            
            self.order_id_counter += 1
            self.load_data()
            return f"Заказ принят! Номер заказа: {self.order_id_counter-1}"

    def update_order_status_gui(self, order_id, new_status):
        """Изменение статуса заказа для GUI"""
        try:
            order_id = int(order_id)
            if order_id not in self.orders:
                raise ValueError("Заказ не найден!")
                
            valid_statuses = ['принят', 'готовится', 'готов', 'подано', 'оплачено']
            if new_status not in valid_statuses:
                raise ValueError("Неверный статус заказа!")
                
        except ValueError as e:
            raise ValueError(f"Ошибка ввода данных: {str(e)}")
        
        # Обновление в базе
        self.db.collection('orders').document(str(order_id)).update({
            'status': new_status,
            'updated_at': datetime.now()
        })
        
        self.load_data()
        return f"Статус заказа {order_id} изменен на '{new_status}'"

    def process_payment_gui(self, order_id):
        """Обработка оплаты для GUI"""
        try:
            order_id = int(order_id)
            if order_id not in self.orders:
                raise ValueError("Заказ не найден!")
                
            order = self.orders[order_id]
            if order.get('status') == 'оплачено':
                raise ValueError("Этот заказ уже оплачен!")
                
        except ValueError as e:
            raise ValueError(f"Ошибка ввода данных: {str(e)}")
        
        # Обновляем статус заказа
        self.db.collection('orders').document(str(order_id)).update({
            'status': 'оплачено',
            'paid_at': datetime.now()
        })
        
        # Освобождаем столик
        table_num = order.get('table')
        if table_num:
            self.db.collection('tables').document(str(table_num)).update({
                'status': 'свободен',
                'current_order': None,
                'client_name': None
            })
        
        # Генерация чека
        receipt = {
            'order_id': order_id,
            'amount': order.get('total', 0),
            'payment_date': datetime.now(),
            'staff_id': self.current_user['id'],
            'items': order.get('items', [])
        }
        
        self.db.collection('receipts').document().set(receipt)
        
        self.load_data()
        return "Оплата подтверждена! Чек сформирован."

    def add_dish_gui(self, name, price, category):
        """Добавление блюда для GUI"""
        try:
            price = float(price)
            if price <= 0:
                raise ValueError("Цена должна быть положительным числом!")
                
            if not name:
                raise ValueError("Название не может быть пустым!")
                
            if not category:
                raise ValueError("Категория не может быть пустой!")
                
        except ValueError as e:
            raise ValueError(f"Ошибка ввода данных: {str(e)}")
        
        dish_data = {
            'name': name,
            'price': price,
            'category': category
        }
        
        # Генерируем новый ID
        new_id = str(max(int(k) for k in self.menu.keys()) + 1) if self.menu else '1'
        
        self.db.collection('menu').document(new_id).set(dish_data)
        self.load_data()
        return f"Блюдо добавлено! ID: {new_id}"

    def get_statistics(self):
        """Получение статистики для GUI"""
        stats = {}
        
        # Общая статистика
        stats['total_orders'] = len(self.orders)
        stats['completed_orders'] = len([o for o in self.orders.values() if o.get('status') == 'оплачено'])
        stats['total_reservations'] = len(self.reservations)
        stats['active_reservations'] = len([r for r in self.reservations.values() if r.get('status') == 'подтверждено'])
        stats['total_revenue'] = sum(o.get('total', 0) for o in self.orders.values() if o.get('status') == 'оплачено')
        stats['avg_check'] = stats['total_revenue'] / stats['completed_orders'] if stats['completed_orders'] > 0 else 0
        
        # Статистика по заказам
        stats['order_statuses'] = {}
        for order in self.orders.values():
            status = order.get('status', 'неизвестно')
            stats['order_statuses'][status] = stats['order_statuses'].get(status, 0) + 1
        
        # Статистика по бронированиям
        stats['reservation_statuses'] = {}
        for res in self.reservations.values():
            status = res.get('status', 'неизвестно')
            stats['reservation_statuses'][status] = stats['reservation_statuses'].get(status, 0) + 1
        
        # Статистика по блюдам
        stats['dishes'] = {}
        for order in self.orders.values():
            for item in order.get('items', []):
                dish_id = item.get('id')
                dish_name = item.get('name', 'неизвестно')
                quantity = item.get('quantity', 0)
                price = item.get('price', 0)
                
                if dish_id not in stats['dishes']:
                    stats['dishes'][dish_id] = {
                        'name': dish_name,
                        'quantity': 0,
                        'revenue': 0
                    }
                
                stats['dishes'][dish_id]['quantity'] += quantity
                stats['dishes'][dish_id]['revenue'] += quantity * price
        
        # Сортировка блюд по количеству продаж
        stats['top_dishes'] = sorted(stats['dishes'].items(), key=lambda x: x[1]['quantity'], reverse=True)[:10]
        
        return stats

class RestaurantGUI:
    def __init__(self, system):
        self.system = system
        self.root = tk.Tk()
        self.root.title("Ресторанная система")
        self.root.geometry("1000x700")
        self.root.configure(bg='white')  # Устанавливаем белый фон для главного окна
        
        self.setup_ui()
        
    def setup_ui(self):
        # Стилизация
        style = ttk.Style()
        style.theme_use('clam')  # Используем тему 'clam' для лучшей видимости
        
        # Настройка стилей
        style.configure('.', background='white', foreground='black')  # Основные цвета
        style.configure('TFrame', background='white')
        style.configure('TLabel', background='white', foreground='black', font=('Arial', 10))
        style.configure('TButton', font=('Arial', 10), padding=5, background='#f0f0f0')
        style.configure('Header.TLabel', font=('Arial', 12, 'bold'))
        style.configure('Treeview', background='white', fieldbackground='white')
        style.map('Treeview', background=[('selected', '#0078d7')])
        
        # Главный фрейм
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Фрейм для авторизации
        self.login_frame = ttk.Frame(self.main_frame, borderwidth=2, relief='groove', padding=10)
        self.login_frame.pack(pady=50)
        
        ttk.Label(self.login_frame, text="Ресторанная система", style='Header.TLabel').grid(row=0, column=0, columnspan=2, pady=10)
        ttk.Label(self.login_frame, text="Логин:").grid(row=1, column=0, sticky=tk.E, padx=5, pady=5)
        self.login_entry = ttk.Entry(self.login_frame, width=20)
        self.login_entry.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(self.login_frame, text="Пароль:").grid(row=2, column=0, sticky=tk.E, padx=5, pady=5)
        self.password_entry = ttk.Entry(self.login_frame, width=20, show="*")
        self.password_entry.grid(row=2, column=1, padx=5, pady=5)
        
        ttk.Button(self.login_frame, text="Войти", command=self.handle_login).grid(row=3, column=0, columnspan=2, pady=10)
        
        # Фрейм для основного интерфейса (будет заполнен после авторизации)
        self.app_frame = ttk.Frame(self.main_frame)
        
    def handle_login(self):
        login = self.login_entry.get()
        password = self.password_entry.get()
        
        if self.system.login_gui(login, password):
            self.login_frame.pack_forget()
            self.show_main_interface()
        else:
            messagebox.showerror("Ошибка", "Неверный логин или пароль")
    
    def show_main_interface(self):
        # Очистка предыдущего интерфейса
        for widget in self.app_frame.winfo_children():
            widget.destroy()
            
        self.app_frame.pack(fill=tk.BOTH, expand=True)
        
        # Панель пользователя
        user_panel = ttk.Frame(self.app_frame, padding=5)
        user_panel.pack(fill=tk.X, pady=5)
        
        ttk.Label(user_panel, text=f"Пользователь: {self.system.current_user['name']} ({self.system.current_user['position']})").pack(side=tk.LEFT)
        ttk.Button(user_panel, text="Выход", command=self.logout).pack(side=tk.RIGHT)
        
        # Ноутбук с вкладками
        self.notebook = ttk.Notebook(self.app_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # В зависимости от роли пользователя показываем разные вкладки
        if self.system.current_user['position'] == 'администратор':
            self.setup_admin_tabs()
        else:
            self.setup_waiter_tabs()
    
    def setup_admin_tabs(self):
        # Вкладка бронирований
        reservations_tab = ttk.Frame(self.notebook)
        self.notebook.add(reservations_tab, text="Бронирования")
        self.setup_reservations_tab(reservations_tab)
        
        # Вкладка заказов
        orders_tab = ttk.Frame(self.notebook)
        self.notebook.add(orders_tab, text="Заказы")
        self.setup_orders_tab(orders_tab)
        
        # Вкладка меню
        menu_tab = ttk.Frame(self.notebook)
        self.notebook.add(menu_tab, text="Меню")
        self.setup_menu_tab(menu_tab)
        
        # Вкладка столиков
        tables_tab = ttk.Frame(self.notebook)
        self.notebook.add(tables_tab, text="Столики")
        self.setup_tables_tab(tables_tab)
        
        # Вкладка статистики
        stats_tab = ttk.Frame(self.notebook)
        self.notebook.add(stats_tab, text="Статистика")
        self.setup_stats_tab(stats_tab)
    
    def setup_waiter_tabs(self):
        # Вкладка заказов
        orders_tab = ttk.Frame(self.notebook)
        self.notebook.add(orders_tab, text="Заказы")
        self.setup_orders_tab(orders_tab)
        
        # Вкладка бронирований
        reservations_tab = ttk.Frame(self.notebook)
        self.notebook.add(reservations_tab, text="Бронирования")
        self.setup_reservations_tab(reservations_tab)
    
    def setup_reservations_tab(self, tab):
        # Дерево для отображения бронирований
        columns = ("id", "client", "phone", "table", "datetime", "guests", "status")
        self.reservations_tree = ttk.Treeview(
            tab, columns=columns, show="headings", selectmode="browse"
        )
        
        # Настройка колонок
        self.reservations_tree.heading("id", text="ID")
        self.reservations_tree.heading("client", text="Клиент")
        self.reservations_tree.heading("phone", text="Телефон")
        self.reservations_tree.heading("table", text="Столик")
        self.reservations_tree.heading("datetime", text="Дата и время")
        self.reservations_tree.heading("guests", text="Гости")
        self.reservations_tree.heading("status", text="Статус")
        
        # Размеры колонок
        self.reservations_tree.column("id", width=50, anchor=tk.CENTER)
        self.reservations_tree.column("client", width=150)
        self.reservations_tree.column("phone", width=100)
        self.reservations_tree.column("table", width=50, anchor=tk.CENTER)
        self.reservations_tree.column("datetime", width=120)
        self.reservations_tree.column("guests", width=50, anchor=tk.CENTER)
        self.reservations_tree.column("status", width=100)
        
        self.reservations_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Кнопки управления
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(btn_frame, text="Добавить", command=self.add_reservation).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Отменить", command=self.cancel_reservation).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Обновить", command=self.refresh_reservations).pack(side=tk.RIGHT, padx=2)
        
        # Заполняем данными
        self.refresh_reservations()
    
    def refresh_reservations(self):
        # Очищаем дерево
        for item in self.reservations_tree.get_children():
            self.reservations_tree.delete(item)
        
        # Заполняем новыми данными
        for res_id, res in self.system.reservations.items():
            dt = res.get('datetime', 'N/A')
            if dt != 'N/A':
                if hasattr(dt, 'strftime'):
                    dt = dt.strftime("%d.%m.%Y %H:%M")
                elif isinstance(dt, str):
                    try:
                        dt_obj = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
                        dt = dt_obj.strftime("%d.%m.%Y %H:%M")
                    except ValueError:
                        pass
            
            self.reservations_tree.insert("", tk.END, values=(
                res_id,
                res.get('client_name', 'N/A'),
                res.get('phone', 'N/A'),
                res.get('table_number', 'N/A'),
                dt,
                res.get('guests', 'N/A'),
                res.get('status', 'N/A')
            ))
    
    def add_reservation(self):
        # Создаем окно для добавления бронирования
        dialog = tk.Toplevel(self.root)
        dialog.title("Новое бронирование")
        dialog.geometry("400x400")
        dialog.configure(bg='white')
        
        ttk.Label(dialog, text="Имя клиента:").pack(pady=5)
        client_entry = ttk.Entry(dialog)
        client_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Телефон:").pack(pady=5)
        phone_entry = ttk.Entry(dialog)
        phone_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Дата (ДД.ММ.ГГГГ):").pack(pady=5)
        date_entry = ttk.Entry(dialog)
        date_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Время (ЧЧ:ММ):").pack(pady=5)
        time_entry = ttk.Entry(dialog)
        time_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Количество гостей:").pack(pady=5)
        guests_entry = ttk.Entry(dialog)
        guests_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Номер столика:").pack(pady=5)
        table_entry = ttk.Entry(dialog)
        table_entry.pack(pady=5)
        
        def save_reservation():
            try:
                result = self.system.create_reservation_gui(
                    client_entry.get(),
                    phone_entry.get(),
                    date_entry.get(),
                    time_entry.get(),
                    guests_entry.get(),
                    table_entry.get()
                )
                messagebox.showinfo("Успех", result)
                self.refresh_reservations()
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
        
        ttk.Button(dialog, text="Сохранить", command=save_reservation).pack(pady=10)
    
    def cancel_reservation(self):
        selected = self.reservations_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите бронирование для отмены")
            return
            
        res_id = self.reservations_tree.item(selected[0])['values'][0]
        
        if messagebox.askyesno("Подтверждение", "Вы уверены, что хотите отменить это бронирование?"):
            try:
                result = self.system.cancel_reservation_gui(res_id)
                messagebox.showinfo("Успех", result)
                self.refresh_reservations()
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
    
    def setup_orders_tab(self, tab):
        # Дерево для отображения заказов
        columns = ("id", "table", "client", "waiter", "total", "status", "created_at")
        self.orders_tree = ttk.Treeview(
            tab, columns=columns, show="headings", selectmode="browse"
        )
        
        # Настройка колонок
        self.orders_tree.heading("id", text="ID")
        self.orders_tree.heading("table", text="Столик")
        self.orders_tree.heading("client", text="Клиент")
        self.orders_tree.heading("waiter", text="Официант")
        self.orders_tree.heading("total", text="Сумма")
        self.orders_tree.heading("status", text="Статус")
        self.orders_tree.heading("created_at", text="Дата создания")
        
        # Размеры колонок
        self.orders_tree.column("id", width=50, anchor=tk.CENTER)
        self.orders_tree.column("table", width=50, anchor=tk.CENTER)
        self.orders_tree.column("client", width=150)
        self.orders_tree.column("waiter", width=150)
        self.orders_tree.column("total", width=80, anchor=tk.E)
        self.orders_tree.column("status", width=100)
        self.orders_tree.column("created_at", width=120)
        
        self.orders_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Кнопки управления
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        if self.system.current_user['position'] == 'официант':
            ttk.Button(btn_frame, text="Создать заказ", command=self.create_order).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(btn_frame, text="Изменить статус", command=self.change_order_status).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Оплатить", command=self.pay_order).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Обновить", command=self.refresh_orders).pack(side=tk.RIGHT, padx=2)
        
        # Заполняем данными
        self.refresh_orders()
    
    def refresh_orders(self):
        # Очищаем дерево
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)
        
        # Заполняем новыми данными
        for order_id, order_data in self.system.orders.items():
            dt = order_data.get('created_at', 'N/A')
            if dt != 'N/A':
                if hasattr(dt, 'strftime'):
                    dt = dt.strftime("%d.%m.%Y %H:%M")
                elif isinstance(dt, str):
                    try:
                        dt_obj = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
                        dt = dt_obj.strftime("%d.%m.%Y %H:%M")
                    except ValueError:
                        pass
            
            self.orders_tree.insert("", tk.END, values=(
                order_id,
                order_data.get('table', 'N/A'),
                order_data.get('client_name', 'N/A'),
                order_data.get('waiter_name', 'N/A'),
                order_data.get('total', 'N/A'),
                order_data.get('status', 'N/A'),
                dt
            ))
    
    def create_order(self):
            # Создаем окно для добавления заказа
            dialog = tk.Toplevel(self.root)
            dialog.title("Новый заказ")
            dialog.geometry("600x500")
            dialog.configure(bg='white')
            
            # Выбор столика
            ttk.Label(dialog, text="Столик:").pack(pady=5)
            table_combobox = ttk.Combobox(dialog, values=list(self.system.tables.keys()))
            table_combobox.pack(pady=5)
            
            # Имя клиента
            ttk.Label(dialog, text="Имя клиента:").pack(pady=5)
            client_entry = ttk.Entry(dialog)
            client_entry.pack(pady=5)
            
            # Меню
            ttk.Label(dialog, text="Меню:").pack(pady=5)
            menu_frame = ttk.Frame(dialog)
            menu_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Дерево для меню
            menu_columns = ("id", "name", "price", "category")
            menu_tree = ttk.Treeview(
                menu_frame, columns=menu_columns, show="headings", selectmode="browse"
            )
            
            menu_tree.heading("id", text="ID")
            menu_tree.heading("name", text="Название")
            menu_tree.heading("price", text="Цена")
            menu_tree.heading("category", text="Категория")
            
            menu_tree.column("id", width=50, anchor=tk.CENTER)
            menu_tree.column("name", width=150)
            menu_tree.column("price", width=80, anchor=tk.E)
            menu_tree.column("category", width=100)
            
            # Заполняем меню
            for item_id, item_data in self.system.menu.items():
                menu_tree.insert("", tk.END, values=(
                    item_id,
                    item_data.get('name', 'N/A'),
                    item_data.get('price', 'N/A'),
                    item_data.get('category', 'N/A')
                ))
            
            menu_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # Прокрутка для меню
            scrollbar = ttk.Scrollbar(menu_frame, orient="vertical", command=menu_tree.yview)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            menu_tree.configure(yscrollcommand=scrollbar.set)
            
            # Выбранные блюда
            ttk.Label(dialog, text="Выбранные блюда:").pack(pady=5)
            selected_frame = ttk.Frame(dialog)
            selected_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            selected_columns = ("name", "price", "quantity", "sum")
            self.selected_tree = ttk.Treeview(
                selected_frame, columns=selected_columns, show="headings"
            )
            
            self.selected_tree.heading("name", text="Название")
            self.selected_tree.heading("price", text="Цена")
            self.selected_tree.heading("quantity", text="Количество")
            self.selected_tree.heading("sum", text="Сумма")
            
            self.selected_tree.column("name", width=150)
            self.selected_tree.column("price", width=80, anchor=tk.E)
            self.selected_tree.column("quantity", width=80, anchor=tk.CENTER)
            self.selected_tree.column("sum", width=80, anchor=tk.E)
            
            self.selected_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # Кнопки для добавления/удаления блюд
            btn_frame = ttk.Frame(dialog)
            btn_frame.pack(fill=tk.X, padx=5, pady=5)
            
            def add_item():
                selected = menu_tree.selection()
                if not selected:
                    messagebox.showwarning("Внимание", "Выберите блюдо из меню")
                    return
                    
                item = menu_tree.item(selected[0])
                item_id = item['values'][0]
                item_name = item['values'][1]
                item_price = float(item['values'][2])
                
                # Запрашиваем количество
                quantity = simpledialog.askinteger("Количество", f"Введите количество для {item_name}:", parent=dialog, minvalue=1)
                if quantity:
                    # Проверяем, не добавлено ли уже это блюдо
                    for child in self.selected_tree.get_children():
                        if self.selected_tree.item(child)['values'][0] == item_name:
                            # Увеличиваем количество
                            current_qty = self.selected_tree.item(child)['values'][2]
                            new_qty = current_qty + quantity
                            self.selected_tree.item(child, values=(
                                item_name, 
                                item_price, 
                                new_qty, 
                                item_price * new_qty
                            ))
                            return
                    
                    # Добавляем новое блюдо
                    self.selected_tree.insert("", tk.END, values=(
                        item_name, 
                        item_price, 
                        quantity, 
                        item_price * quantity
                    ))
            
            def remove_item():
                selected = self.selected_tree.selection()
                if selected:
                    self.selected_tree.delete(selected)
            
            ttk.Button(btn_frame, text="Добавить", command=add_item).pack(side=tk.LEFT, padx=2)
            ttk.Button(btn_frame, text="Удалить", command=remove_item).pack(side=tk.LEFT, padx=2)
            
            def save_order():
                try:
                    table_num = table_combobox.get()
                    client_name = client_entry.get()
                    
                    if not table_num:
                        raise ValueError("Выберите номер столика!")
                    if not client_name:
                        raise ValueError("Введите имя клиента!")
                    
                    # Собираем выбранные блюда
                    order_items = []
                    for child in self.selected_tree.get_children():
                        item = self.selected_tree.item(child)['values']
                        # Находим ID блюда по названию
                        item_id = None
                        for menu_id, menu_item in self.system.menu.items():
                            if menu_item['name'] == item[0]:
                                item_id = menu_id
                                break
                        
                        if item_id:
                            order_items.append({
                                'id': item_id,
                                'name': item[0],
                                'price': float(item[1]),
                                'quantity': int(item[2])
                            })
                    
                    if not order_items:
                        raise ValueError("Добавьте хотя бы одно блюдо в заказ!")
                    
                    # Создаем заказ
                    result = self.system.take_order_gui(table_num, client_name, order_items)
                    messagebox.showinfo("Успех", result)
                    self.refresh_orders()
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("Ошибка", str(e))
                    print(f"Ошибка при создании заказа: {e}")  # Добавлено для отладки
            
            ttk.Button(dialog, text="Сохранить заказ", command=save_order).pack(pady=10)
    
    def change_order_status(self):
        selected = self.orders_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите заказ")
            return
            
        order_id = self.orders_tree.item(selected[0])['values'][0]
        current_status = self.orders_tree.item(selected[0])['values'][5]
        
        # Диалог выбора нового статуса
        status_dialog = tk.Toplevel(self.root)
        status_dialog.title("Изменение статуса заказа")
        status_dialog.configure(bg='white')
        
        ttk.Label(status_dialog, text=f"Текущий статус: {current_status}").pack(pady=5)
        ttk.Label(status_dialog, text="Новый статус:").pack(pady=5)
        
        status_var = tk.StringVar()
        statuses = ttk.Combobox(status_dialog, textvariable=status_var, 
                               values=['принят', 'готовится', 'готов', 'подано', 'оплачено'])
        statuses.pack(pady=5)
        
        def save_status():
            new_status = status_var.get()
            if not new_status:
                messagebox.showwarning("Внимание", "Выберите новый статус")
                return
                
            try:
                result = self.system.update_order_status_gui(order_id, new_status)
                messagebox.showinfo("Успех", result)
                self.refresh_orders()
                status_dialog.destroy()
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
        
        ttk.Button(status_dialog, text="Сохранить", command=save_status).pack(pady=10)
    
    def pay_order(self):
        selected = self.orders_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите заказ")
            return
            
        order_id = self.orders_tree.item(selected[0])['values'][0]
        current_status = self.orders_tree.item(selected[0])['values'][5]
        
        if current_status == 'оплачено':
            messagebox.showinfo("Информация", "Этот заказ уже оплачен")
            return
            
        if messagebox.askyesno("Подтверждение", "Подтвердите оплату заказа"):
            try:
                result = self.system.process_payment_gui(order_id)
                messagebox.showinfo("Успех", result)
                self.refresh_orders()
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
    
    def setup_menu_tab(self, tab):
        # Дерево для отображения меню
        columns = ("id", "name", "price", "category")
        self.menu_tree = ttk.Treeview(
            tab, columns=columns, show="headings", selectmode="browse"
        )
        
        # Настройка колонок
        self.menu_tree.heading("id", text="ID")
        self.menu_tree.heading("name", text="Название")
        self.menu_tree.heading("price", text="Цена")
        self.menu_tree.heading("category", text="Категория")
        
        # Размеры колонок
        self.menu_tree.column("id", width=50, anchor=tk.CENTER)
        self.menu_tree.column("name", width=200)
        self.menu_tree.column("price", width=80, anchor=tk.E)
        self.menu_tree.column("category", width=150)
        
        self.menu_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Кнопки управления
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(btn_frame, text="Добавить", command=self.add_dish).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Удалить", command=self.delete_dish).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Обновить", command=self.refresh_menu).pack(side=tk.RIGHT, padx=2)
        
        # Заполняем данными
        self.refresh_menu()
    
    def refresh_menu(self):
        # Очищаем дерево
        for item in self.menu_tree.get_children():
            self.menu_tree.delete(item)
        
        # Заполняем новыми данными
        for item_id, item_data in self.system.menu.items():
            self.menu_tree.insert("", tk.END, values=(
                item_id,
                item_data.get('name', 'N/A'),
                item_data.get('price', 'N/A'),
                item_data.get('category', 'N/A')
            ))
    
    def add_dish(self):
        # Создаем окно для добавления блюда
        dialog = tk.Toplevel(self.root)
        dialog.title("Новое блюдо")
        dialog.geometry("300x200")
        dialog.configure(bg='white')
        
        ttk.Label(dialog, text="Название:").pack(pady=5)
        name_entry = ttk.Entry(dialog)
        name_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Цена:").pack(pady=5)
        price_entry = ttk.Entry(dialog)
        price_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Категория:").pack(pady=5)
        category_entry = ttk.Entry(dialog)
        category_entry.pack(pady=5)
        
        def save_dish():
            try:
                result = self.system.add_dish_gui(
                    name_entry.get(),
                    price_entry.get(),
                    category_entry.get()
                )
                messagebox.showinfo("Успех", result)
                self.refresh_menu()
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
        
        ttk.Button(dialog, text="Сохранить", command=save_dish).pack(pady=10)
    
    def delete_dish(self):
        selected = self.menu_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите блюдо")
            return
            
        item_id = self.menu_tree.item(selected[0])['values'][0]
        
        if messagebox.askyesno("Подтверждение", "Вы уверены, что хотите удалить это блюдо?"):
            try:
                self.system.db.collection('menu').document(item_id).delete()
                messagebox.showinfo("Успех", "Блюдо удалено")
                self.system.load_data()
                self.refresh_menu()
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
    
    def setup_tables_tab(self, tab):
        # Дерево для отображения столиков
        columns = ("number", "capacity", "status", "client_name")
        self.tables_tree = ttk.Treeview(
            tab, columns=columns, show="headings", selectmode="browse"
        )
        
        # Настройка колонок
        self.tables_tree.heading("number", text="Номер")
        self.tables_tree.heading("capacity", text="Вместимость")
        self.tables_tree.heading("status", text="Статус")
        self.tables_tree.heading("client_name", text="Клиент")
        
        # Размеры колонок
        self.tables_tree.column("number", width=50, anchor=tk.CENTER)
        self.tables_tree.column("capacity", width=80, anchor=tk.CENTER)
        self.tables_tree.column("status", width=100)
        self.tables_tree.column("client_name", width=150)
        
        self.tables_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Кнопки управления
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(btn_frame, text="Добавить", command=self.add_table).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Изменить", command=self.edit_table).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Удалить", command=self.delete_table).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Обновить", command=self.refresh_tables).pack(side=tk.RIGHT, padx=2)
        
        # Заполняем данными
        self.refresh_tables()
    
    def refresh_tables(self):
        # Очищаем дерево
        for item in self.tables_tree.get_children():
            self.tables_tree.delete(item)
        
        # Заполняем новыми данными
        for table_num, table_data in self.system.tables.items():
            self.tables_tree.insert("", tk.END, values=(
                table_num,
                table_data.get('capacity', 'N/A'),
                table_data.get('status', 'N/A'),
                table_data.get('client_name', '—')
            ))
    
    def add_table(self):
        # Создаем окно для добавления столика
        dialog = tk.Toplevel(self.root)
        dialog.title("Новый столик")
        dialog.geometry("300x150")
        dialog.configure(bg='white')
        
        ttk.Label(dialog, text="Номер столика:").pack(pady=5)
        number_entry = ttk.Entry(dialog)
        number_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Вместимость (2-10):").pack(pady=5)
        capacity_entry = ttk.Entry(dialog)
        capacity_entry.pack(pady=5)
        
        def save_table():
            try:
                number = int(number_entry.get())
                capacity = int(capacity_entry.get())
                
                if number in self.system.tables:
                    raise ValueError("Столик с таким номером уже существует!")
                if capacity < 2 or capacity > 10:
                    raise ValueError("Вместимость должна быть от 2 до 10!")
                
                table_data = {
                    'number': number,
                    'capacity': capacity,
                    'status': 'свободен',
                    'current_order': None,
                    'reservation': None,
                    'client_name': None
                }
                
                self.system.db.collection('tables').document(str(number)).set(table_data)
                messagebox.showinfo("Успех", f"Столик №{number} добавлен!")
                self.system.load_data()
                self.refresh_tables()
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
        
        ttk.Button(dialog, text="Сохранить", command=save_table).pack(pady=10)
    
    def edit_table(self):
        selected = self.tables_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите столик")
            return
            
        table_num = self.tables_tree.item(selected[0])['values'][0]
        current_capacity = self.tables_tree.item(selected[0])['values'][1]
        
        # Создаем окно для редактирования столика
        dialog = tk.Toplevel(self.root)
        dialog.title("Редактирование столика")
        dialog.geometry("300x150")
        dialog.configure(bg='white')
        
        ttk.Label(dialog, text=f"Редактирование столика №{table_num}").pack(pady=5)
        ttk.Label(dialog, text="Новая вместимость:").pack(pady=5)
        
        capacity_entry = ttk.Entry(dialog)
        capacity_entry.insert(0, current_capacity)
        capacity_entry.pack(pady=5)
        
        def save_changes():
            try:
                new_capacity = int(capacity_entry.get())
                if new_capacity < 2 or new_capacity > 10:
                    raise ValueError("Вместимость должна быть от 2 до 10!")
                
                self.system.db.collection('tables').document(str(table_num)).update({
                    'capacity': new_capacity
                })
                messagebox.showinfo("Успех", "Столик обновлен!")
                self.system.load_data()
                self.refresh_tables()
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
        
        ttk.Button(dialog, text="Сохранить", command=save_changes).pack(pady=10)
    
    def delete_table(self):
        selected = self.tables_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите столик")
            return
            
        table_num = self.tables_tree.item(selected[0])['values'][0]
        table_status = self.tables_tree.item(selected[0])['values'][2]
        
        if table_status != 'свободен':
            messagebox.showerror("Ошибка", "Нельзя удалить занятый или забронированный столик!")
            return
            
        if messagebox.askyesno("Подтверждение", f"Вы уверены, что хотите удалить столик №{table_num}?"):
            try:
                self.system.db.collection('tables').document(str(table_num)).delete()
                messagebox.showinfo("Успех", f"Столик №{table_num} удален!")
                self.system.load_data()
                self.refresh_tables()
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
    
    def setup_stats_tab(self, tab):
        # Фрейм для статистики
        stats_frame = ttk.Frame(tab)
        stats_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Общая статистика
        ttk.Label(stats_frame, text="Общая статистика", style='Header.TLabel').pack(anchor=tk.W, pady=5)
        
        self.total_orders_label = ttk.Label(stats_frame, text="Всего заказов: 0")
        self.total_orders_label.pack(anchor=tk.W)
        
        self.completed_orders_label = ttk.Label(stats_frame, text="Завершенных заказов: 0")
        self.completed_orders_label.pack(anchor=tk.W)
        
        self.total_reservations_label = ttk.Label(stats_frame, text="Всего бронирований: 0")
        self.total_reservations_label.pack(anchor=tk.W)
        
        self.active_reservations_label = ttk.Label(stats_frame, text="Активных бронирований: 0")
        self.active_reservations_label.pack(anchor=tk.W)
        
        self.total_revenue_label = ttk.Label(stats_frame, text="Общая выручка: 0 руб.")
        self.total_revenue_label.pack(anchor=tk.W)
        
        self.avg_check_label = ttk.Label(stats_frame, text="Средний чек: 0 руб.")
        self.avg_check_label.pack(anchor=tk.W)
        
        # Разделитель
        ttk.Separator(stats_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # Статистика по заказам
        ttk.Label(stats_frame, text="Статистика по заказам", style='Header.TLabel').pack(anchor=tk.W, pady=5)
        
        self.orders_by_status_label = ttk.Label(stats_frame, text="По статусам:")
        self.orders_by_status_label.pack(anchor=tk.W)
        
        # Разделитель
        ttk.Separator(stats_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # Топ блюд
        ttk.Label(stats_frame, text="Топ продаж блюд", style='Header.TLabel').pack(anchor=tk.W, pady=5)
        
        self.top_dishes_label = ttk.Label(stats_frame, text="")
        self.top_dishes_label.pack(anchor=tk.W)
        
        # Кнопка обновления
        ttk.Button(stats_frame, text="Обновить статистику", command=self.refresh_stats).pack(pady=10)
        
        # Первоначальное обновление
        self.refresh_stats()
    
    def refresh_stats(self):
        stats = self.system.get_statistics()
        
        # Общая статистика
        self.total_orders_label.config(text=f"Всего заказов: {stats['total_orders']}")
        self.completed_orders_label.config(text=f"Завершенных заказов: {stats['completed_orders']}")
        self.total_reservations_label.config(text=f"Всего бронирований: {stats['total_reservations']}")
        self.active_reservations_label.config(text=f"Активных бронирований: {stats['active_reservations']}")
        self.total_revenue_label.config(text=f"Общая выручка: {stats['total_revenue']:.2f} руб.")
        self.avg_check_label.config(text=f"Средний чек: {stats['avg_check']:.2f} руб.")
        
        # Статистика по заказам
        status_text = "По статусам:\n"
        for status, count in stats['order_statuses'].items():
            status_text += f"  {status}: {count}\n"
        self.orders_by_status_label.config(text=status_text)
        
        # Топ блюд
        top_dishes_text = "Топ продаж:\n"
        for dish_id, dish_data in stats['top_dishes']:
            top_dishes_text += f"  {dish_data['name']}: {dish_data['quantity']} шт., {dish_data['revenue']:.2f} руб.\n"
        self.top_dishes_label.config(text=top_dishes_text)
    
    def logout(self):
        self.system.current_user = None
        self.app_frame.pack_forget()
        self.login_frame.pack(pady=50)
        self.login_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    system = RestaurantSystem()
    gui = RestaurantGUI(system)
    gui.run()