import tkinter as tk
from tkinter import ttk

# Создаем главное окно
root = tk.Tk()
root.title("Тестовое окно")
root.geometry("600x400")

# Явно устанавливаем белый фон для всех элементов
root.configure(bg='white')
root.option_add('*background', 'white')
root.option_add('*foreground', 'black')
root.option_add('*Font', 'Arial 10')

# Простой стиль без тем
style = ttk.Style()
style.theme_use('default')  # Самая базовая тема

# Создаем фрейм с явными параметрами
main_frame = ttk.Frame(root, padding=20)
main_frame.pack(fill=tk.BOTH, expand=True)

# Добавляем виджеты
label = ttk.Label(main_frame, text="Тестовый интерфейс", font=('Arial', 14))
label.pack(pady=10)

entry = ttk.Entry(main_frame, width=30)
entry.pack(pady=10)

button = ttk.Button(main_frame, text="Тестовая кнопка")
button.pack(pady=10)

# Запускаем главный цикл
root.mainloop()