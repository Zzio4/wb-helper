from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import sqlite3
from datetime import datetime
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('price_monitor.log'),
        logging.StreamHandler()
    ]
)

class EntryPoint:
    def __init__(self, db_path='prices.db'):
        self.db_path = db_path
        self.setup_database()
        self.setup_driver()

    def setup_driver(self):
        chrome_options = Options()
        # chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

        service = Service(executable_path=ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
    
    def setup_database(self):
        """Создание базы данных и таблицы для хранения цен"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_url TEXT NOT NULL,
                product_name TEXT,
                current_price REAL NOT NULL,
                previous_price REAL,
                check_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_url, check_date)
            )
        ''')
        
        conn.commit()
        conn.close()
        logging.info("База данных настроена успешно")
    
    def get_links_from_file(self, filename="links.txt"):
        """Читает ссылки из файла"""
        with open(filename, 'r') as file:
            links = [line.strip() for line in file if line.strip()]
        return links
    
    def get_product_price(self, url):
        """Получает цену товара и сохраняет в базу данных"""
        wait = WebDriverWait(self.driver, 10)

        try:
            self.driver.get(url)
            self.driver.fullscreen_window()
            time.sleep(3)

            # Поиск цены
            price_selector = wait.until(
                EC.visibility_of_element_located((By.XPATH, "//h2[contains(@class, 'mo-typography mo-typography_variant_title2')]"))
            )
            price_text = price_selector.text
            print(f"Найдена цена: {price_text}")
            
            # Парсинг цены
            current_price = self.parse_price(price_text)
            if current_price is None:
                logging.warning(f"Не удалось распарсить цену: {price_text}")
                return
            
            # Получение названия товара
            product_name = self.get_product_name()
            
            # Сохранение в базу данных и проверка изменения цены
            self.save_and_check_price(url, product_name, current_price)
            
        except Exception as e:
            logging.error(f"Ошибка при получении цены с {url}: {str(e)}")
    
    def parse_price(self, price_text):
        """Парсит цену из текста"""
        try:
            cleaned_price = ''.join(c for c in price_text if c.isdigit() or c in ',.')

            cleaned_price = cleaned_price.replace(',', '.').replace(' ', '')

            if '.' in cleaned_price:
                parts = cleaned_price.split('.')
                if len(parts) > 2:
                    cleaned_price = ''.join(parts[:-1]) + '.' + parts[-1]
            
            return float(cleaned_price)
        except Exception as e:
            logging.error(f"Ошибка парсинга цены '{price_text}': {str(e)}")
            return None
    
    def get_product_name(self):
        """Получает название товара"""
        try:
            name_selectors = [
                "h1.product-page__title",
                ".product-page__header",
                "[data-tag='productName']",
                "h1",
                ".product-name"
            ]
            
            for selector in name_selectors:
                try:
                    name_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    name = name_element.text.strip()
                    if name and len(name) > 0:
                        return name
                except:
                    continue
            
            return "Неизвестный товар"
        except:
            return "Неизвестный товар"
    
    def save_and_check_price(self, url, product_name, current_price):
        """Сохраняет цену в базу и проверяет изменение"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT current_price FROM product_prices 
                WHERE product_url = ? 
                ORDER BY check_date DESC 
                LIMIT 1
            ''', (url,))
            
            result = cursor.fetchone()
            previous_price = result[0] if result else None

            cursor.execute('''
                INSERT INTO product_prices (product_url, product_name, current_price, previous_price)
                VALUES (?, ?, ?, ?)
            ''', (url, product_name, current_price, previous_price))
            
            conn.commit()

            self.check_price_change(url, product_name, current_price, previous_price)
            
        except Exception as e:
            logging.error(f"Ошибка при работе с базой данных: {str(e)}")
        finally:
            conn.close()
    
    def check_price_change(self, url, product_name, current_price, previous_price):
        """Проверяет, уменьшилась ли цена в 2 раза"""
        if previous_price is None:
            print(f"🆕 Новый товар: {product_name} - Цена: {current_price} руб.")
            return

        if current_price <= previous_price / 2:
            print(f"✅ Цена УМЕНЬШИЛАСЬ В 2 РАЗА! {product_name}")
            print(f"Было: {previous_price} руб., Стало: {current_price} руб.")
        else:
            change_percent = ((current_price - previous_price) / previous_price) * 100
            print(f"📊 Цена не изменилась значительно: {product_name}")
            print(f"Было: {previous_price} руб., Стало: {current_price} руб. ({change_percent:+.1f}%)")
    
    def get_price_history(self, url):
        """Получает историю цен для товара"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT check_date, current_price, previous_price 
            FROM product_prices 
            WHERE product_url = ? 
            ORDER BY check_date DESC
            LIMIT 10
        ''', (url,))
        
        history = cursor.fetchall()
        conn.close()
        
        return history
    
    def show_price_history(self, url):
        """Показывает историю цен для товара"""
        history = self.get_price_history(url)
        
        if not history:
            print(f"История цен для товара не найдена")
            return
        
        print(f"\n📈 История цен для {url}:")
        for date, current, previous in history:
            change = ""
            if previous:
                percent = ((current - previous) / previous) * 100
                change = f" ({percent:+.1f}%)"
            print(f"  {date}: {current} руб.{change}")
    
    def process_all_links(self):
        """Обрабатывает все ссылки из файла"""
        links = self.get_links_from_file()
        
        print(f"Найдено {len(links)} ссылок для обработки")
        
        for url in links:
            print(f"\n🔍 Обрабатываем: {url}")
            self.get_product_price(url)

            self.show_price_history(url)
            
            time.sleep(2)
    
    def close(self):
        """Закрывает браузер и соединения"""
        if self.driver:
            self.driver.close()
        logging.info("Мониторинг завершен")

if __name__ == "__main__":
    helper = EntryPoint()
    try:
        helper.process_all_links()
    except KeyboardInterrupt:
        print("\n⏹️ Мониторинг остановлен пользователем")
        logging.info("Мониторинг остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Произошла ошибка: {str(e)}")
        logging.error(f"Критическая ошибка: {str(e)}")
    finally:
        helper.close()