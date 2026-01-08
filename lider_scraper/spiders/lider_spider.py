"""
Spider optimizado para extraer productos de Lider.cl
Usa Selenium con simulación humana avanzada para evitar detección
"""
import logging
import time
import random
import json
import math
import re
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin, urlparse
from pathlib import Path

import scrapy
from scrapy.http import HtmlResponse

# Para obtener proxies
try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Intentar importar undetected-chromedriver (mejor para evitar detección)
try:
    import undetected_chromedriver as uc
    UNDETECTED_AVAILABLE = True
except ImportError:
    UNDETECTED_AVAILABLE = False

# Fallback a Selenium normal
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException
)

# Librerías para simulación humana
try:
    from selenium_stealth import stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

try:
    from pynput.mouse import Controller as MouseController, Button
    from pynput.keyboard import Controller as KeyboardController
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

from lider_scraper.items import ProductItem

try:
    from webdriver_manager.chrome import ChromeDriverManager
    USE_WEBDRIVER_MANAGER = True
except ImportError:
    USE_WEBDRIVER_MANAGER = False

# Constantes
CLICK_XPATH = "//section/div[2]/div[2]/a[@link-identifier='Boton_carnes_app.png']"
ITEMS_XPATH = "//section/div/ul/li[@data-slide]"
CAPTCHA_IFRAME_XPATH = "//*[@id='px-captcha']/iframe"  # XPath del iframe del captcha
BASE_URL = 'https://super.lider.cl/'
CARNES_DIRECT_URL = 'https://super.lider.cl/content/carnes-y-pescados/21856785?ContentZone12&co_ty=Hubspokes&co_nm=hogar_W01&co_id=020126_hogar_carnes&co_or=2'
PAGE_LOAD_TIMEOUT = 45  # Aumentado
ELEMENT_WAIT_TIMEOUT = 30  # Aumentado
SCROLL_WAIT_TIME = 3
MAX_SCROLL_ATTEMPTS = 5
INITIAL_PAGE_WAIT = 15  # Aumentado
AFTER_CLICK_WAIT = 15  # Aumentado
RANDOM_DELAY_MIN = 3  # Aumentado
RANDOM_DELAY_MAX = 7  # Aumentado
CAPTCHA_HOLD_TIME = 12  # Aumentado
SHADOW_DOM_WAIT_TIME = 30  # Aumentado tiempo de espera para Shadow DOM


class LiderSpider(scrapy.Spider):
    """Spider para extraer productos usando Selenium con JavaScript para Shadow DOM"""
    
    name = 'lider'
    allowed_domains = ['super.lider.cl']
    # Comentado: ya no cargamos la página inicial, vamos directo a carnes
    # start_urls = ['https://super.lider.cl/']
    start_urls = [CARNES_DIRECT_URL]  # Ir directamente a la página de carnes
    
    custom_settings = {
        'DOWNLOAD_TIMEOUT': 30,
        'RANDOMIZE_DOWNLOAD_DELAY': True,
    }

    def __init__(self, *args, **kwargs):
        super(LiderSpider, self).__init__(*args, **kwargs)
        self.driver: Optional[webdriver.Chrome] = None
        self.cookies_file = 'cookies.json'
        self.proxies: List[str] = []
        self.current_proxy_index = 0
        self.mouse = MouseController() if PYNPUT_AVAILABLE else None
        self.keyboard = KeyboardController() if PYNPUT_AVAILABLE else None
        self._load_proxies()
        self._setup_driver()
    
    def _load_proxies(self) -> None:
        """Cargar proxies gratuitos de múltiples fuentes"""
        self.logger.info('Obteniendo proxies gratuitos...')
        all_proxies = []
        
        if not REQUESTS_AVAILABLE:
            self.logger.warning('requests no disponible, no se pueden obtener proxies')
            return
        
        # Fuente 1: FreeProxyList
        try:
            proxies1 = self._get_proxies_from_free_proxy_list()
            all_proxies.extend(proxies1)
            self.logger.info(f'Obtenidos {len(proxies1)} proxies de FreeProxyList')
        except Exception as e:
            self.logger.debug(f'Error obteniendo proxies de FreeProxyList: {e}')
        
        # Fuente 2: ProxyScrape
        try:
            proxies2 = self._get_proxies_from_proxyscrape()
            all_proxies.extend(proxies2)
            self.logger.info(f'Obtenidos {len(proxies2)} proxies de ProxyScrape')
        except Exception as e:
            self.logger.debug(f'Error obteniendo proxies de ProxyScrape: {e}')
        
        # Fuente 3: Geonode
        try:
            proxies3 = self._get_proxies_from_geonode()
            all_proxies.extend(proxies3)
            self.logger.info(f'Obtenidos {len(proxies3)} proxies de Geonode')
        except Exception as e:
            self.logger.debug(f'Error obteniendo proxies de Geonode: {e}')
        
        # Eliminar duplicados
        self.proxies = list(set(all_proxies))
        
        # Si no se obtuvieron proxies, usar lista de respaldo
        if not self.proxies:
            self.logger.warning('No se obtuvieron proxies de APIs, usando lista de respaldo...')
            self.proxies = self._get_fallback_proxies()
        
        self.logger.info(f'Total de proxies disponibles: {len(self.proxies)}')
    
    def _get_fallback_proxies(self) -> List[str]:
        """Lista de proxies de respaldo (pueden no funcionar, pero es mejor que nada)"""
        # Lista de proxies públicos conocidos (pueden no funcionar, pero intentamos)
        fallback = [
            # Agregar algunos proxies conocidos si es necesario
            # Nota: Los proxies gratuitos cambian constantemente
        ]
        return fallback
    
    def _get_proxies_from_free_proxy_list(self) -> List[str]:
        """Obtener proxies de free-proxy-list.net"""
        proxies = []
        try:
            url = 'https://free-proxy-list.net/'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                table = soup.find('table', {'id': 'proxylisttable'})
                if table:
                    rows = table.find_all('tr')[1:21]  # Primeras 20 filas
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) >= 2:
                            ip = cols[0].text.strip()
                            port = cols[1].text.strip()
                            if ip and port:
                                proxies.append(f'http://{ip}:{port}')
        except Exception as e:
            self.logger.debug(f'Error en free-proxy-list: {e}')
        return proxies
    
    def _get_proxies_from_proxyscrape(self) -> List[str]:
        """Obtener proxies de proxyscrape.com"""
        proxies = []
        try:
            url = 'https://api.proxyscrape.com/v2/?request=get&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                lines = response.text.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line and ':' in line:
                        proxies.append(f'http://{line}')
        except Exception as e:
            self.logger.debug(f'Error en proxyscrape: {e}')
        return proxies[:20]  # Limitar a 20
    
    def _get_proxies_from_geonode(self) -> List[str]:
        """Obtener proxies de geonode.com"""
        proxies = []
        try:
            url = 'https://proxylist.geonode.com/api/proxy-list?limit=20&page=1&sort_by=lastChecked&sort_type=desc&protocols=http%2Chttps'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    for proxy in data['data']:
                        ip = proxy.get('ip')
                        port = proxy.get('port')
                        if ip and port:
                            proxies.append(f"http://{ip}:{port}")
        except Exception as e:
            self.logger.debug(f'Error en geonode: {e}')
        return proxies
    
    def _get_next_proxy(self) -> Optional[str]:
        """Obtener siguiente proxy en rotación"""
        if not self.proxies:
            return None
        proxy = self.proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        return proxy
    
    def _test_proxy(self, proxy: str) -> bool:
        """Probar si un proxy funciona"""
        try:
            test_url = 'https://httpbin.org/ip'
            proxies_dict = {'http': proxy, 'https': proxy}
            response = requests.get(test_url, proxies=proxies_dict, timeout=5)
            return response.status_code == 200
        except:
            return False

    def _setup_driver(self, retry_with_new_proxy: bool = False) -> None:
        """Configurar ChromeDriver con anti-detección avanzada y proxy rotativo"""
        try:
            # Obtener proxy para esta sesión
            proxy = None
            if self.proxies:
                proxy = self._get_next_proxy()
                if proxy:
                    self.logger.info(f'Usando proxy: {proxy.split("//")[-1]}')
            
            # Usar undetected-chromedriver si está disponible (mejor para evitar detección)
            if UNDETECTED_AVAILABLE:
                self.logger.info('Usando undetected-chromedriver para evitar detección...')
                options = uc.ChromeOptions()
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--window-size=1920,1080')
                options.add_argument('--start-maximized')
                # NO usar headless - modo visible para mejor simulación humana
                # options.add_argument('--headless=new')  # Comentado para modo visible
                
                if proxy:
                    # Formato para undetected-chromedriver
                    proxy_url = proxy.replace('http://', '')
                    options.add_argument(f'--proxy-server={proxy}')
                
                self.driver = uc.Chrome(options=options, version_main=None)
                self.logger.info('Undetected ChromeDriver inicializado')
            else:
                # Fallback a Selenium normal con stealth
                chrome_options = Options()
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_argument('--window-size=1920,1080')
                chrome_options.add_argument('--start-maximized')
                # NO usar headless - modo visible
                # chrome_options.add_argument('--headless=new')  # Comentado para modo visible
                
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                chrome_options.add_argument(
                    'user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                
                if proxy:
                    chrome_options.add_argument(f'--proxy-server={proxy}')
                
                if USE_WEBDRIVER_MANAGER:
                    service = Service(ChromeDriverManager().install())
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                else:
                    self.driver = webdriver.Chrome(options=chrome_options)
                
                # Aplicar selenium-stealth si está disponible
                if STEALTH_AVAILABLE:
                    stealth(
                        self.driver,
                        languages=["es-CL", "es", "en-US", "en"],
                        vendor="Google Inc.",
                        platform="MacIntel",
                        webgl_vendor="Intel Inc.",
                        renderer="Intel Iris OpenGL Engine",
                        fix_hairline=True,
                    )
                    self.logger.info('Selenium-stealth aplicado')
            
            self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            if not UNDETECTED_AVAILABLE:
                self.driver.maximize_window()
            self.logger.info('ChromeDriver inicializado correctamente (MODO VISIBLE)')
        except WebDriverException as e:
            self.logger.error(f'Error al inicializar ChromeDriver: {e}')
            if retry_with_new_proxy and self.proxies:
                self.logger.info('Reintentando con nuevo proxy...')
                time.sleep(2)
                self._setup_driver(retry_with_new_proxy=False)
            else:
                raise

    def _human_like_delay(self, min_seconds: float = 0.5, max_seconds: float = 2.0) -> None:
        """Delay que simula tiempo de reacción humano"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def _human_like_mouse_move(self, element) -> None:
        """Mover el mouse de forma humana hacia un elemento"""
        if not self.mouse or not element:
            return
        
        try:
            # Obtener posición del elemento
            location = element.location
            size = element.size
            element_x = location['x'] + size['width'] / 2
            element_y = location['y'] + size['height'] / 2
            
            # Obtener posición actual del mouse
            current_x, current_y = self.mouse.position
            
            # Calcular distancia
            distance = math.sqrt((element_x - current_x)**2 + (element_y - current_y)**2)
            
            # Mover en pasos para simular movimiento humano
            steps = max(10, int(distance / 10))
            for i in range(steps):
                progress = (i + 1) / steps
                # Usar curva de aceleración/desaceleración (ease-in-out)
                eased = progress * progress * (3 - 2 * progress)
                
                x = current_x + (element_x - current_x) * eased
                y = current_y + (element_y - current_y) * eased
                
                # Agregar pequeñas variaciones aleatorias para parecer más humano
                x += random.uniform(-2, 2)
                y += random.uniform(-2, 2)
                
                self.mouse.position = (int(x), int(y))
                time.sleep(random.uniform(0.01, 0.03))
            
            # Ajuste final
            self.mouse.position = (int(element_x), int(element_y))
            time.sleep(random.uniform(0.1, 0.3))
        except Exception as e:
            self.logger.debug(f'Error en movimiento de mouse humano: {e}')

    def _human_like_click(self, element) -> None:
        """Hacer click de forma humana"""
        try:
            # Mover mouse de forma humana
            self._human_like_mouse_move(element)
            
            # Pequeña pausa antes del click (tiempo de reacción)
            time.sleep(random.uniform(0.1, 0.3))
            
            # Usar pynput para click real si está disponible
            if self.mouse:
                self.mouse.press(Button.left)
                time.sleep(random.uniform(0.05, 0.15))  # Tiempo de presión variable
                self.mouse.release(Button.left)
            else:
                # Fallback a Selenium
                element.click()
            
            # Pausa después del click
            time.sleep(random.uniform(0.2, 0.5))
        except Exception as e:
            self.logger.warning(f'Error en click humano: {e}')
            try:
                element.click()
            except:
                pass

    def _simulate_human_typing(self, text: str, element) -> None:
        """Simular escritura humana con delays variables"""
        if not self.keyboard or not element:
            element.send_keys(text)
            return
        
        try:
            element.click()
            time.sleep(random.uniform(0.2, 0.5))
            
            for char in text:
                self.keyboard.type(char)
                # Delay variable entre caracteres (más rápido en medio, más lento al inicio/fin)
                delay = random.uniform(0.05, 0.2)
                time.sleep(delay)
        except Exception as e:
            self.logger.warning(f'Error en escritura humana: {e}')
            element.send_keys(text)

    def _simulate_human_page_load(self) -> None:
        """Simular comportamiento humano durante carga de página"""
        # Movimientos aleatorios de mouse durante la carga
        if self.mouse:
            try:
                for _ in range(random.randint(2, 5)):
                    current_x, current_y = self.mouse.position
                    new_x = current_x + random.randint(-50, 50)
                    new_y = current_y + random.randint(-50, 50)
                    self.mouse.position = (new_x, new_y)
                    time.sleep(random.uniform(0.5, 1.5))
            except:
                pass

    def _load_page_with_post(self, url: str) -> bool:
        """Cargar página usando POST request con JavaScript"""
        try:
            self.logger.info(f'Intentando acceder a {url} usando POST con JavaScript...')
            
            # Primero cargar una página base para poder ejecutar JavaScript
            self.driver.get(BASE_URL)
            time.sleep(random.uniform(2, 4))
            
            # Usar JavaScript para hacer un POST request más realista
            post_script = f"""
            (function() {{
                try {{
                    // Crear formulario
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = '{url}';
                    form.style.display = 'none';
                    form.enctype = 'application/x-www-form-urlencoded';
                    
                    // Agregar campos ocultos comunes
                    const csrf = document.createElement('input');
                    csrf.type = 'hidden';
                    csrf.name = '_token';
                    csrf.value = '';
                    form.appendChild(csrf);
                    
                    document.body.appendChild(form);
                    
                    // Hacer submit del formulario
                    form.submit();
                    
                    return {{success: true}};
                }} catch(e) {{
                    return {{success: false, error: e.message}};
                }}
            }})();
            """
            
            # Ejecutar POST usando JavaScript (síncrono, más simple)
            result = self.driver.execute_script(post_script)
            time.sleep(random.uniform(3, 5))
            
            # Verificar que la navegación ocurrió
            current_url = self.driver.current_url
            if url in current_url or 'carnes' in current_url.lower():
                self.logger.info(f'POST request ejecutado, URL actual: {current_url}')
                return True
            else:
                self.logger.warning(f'POST no navegó a la URL esperada. URL actual: {current_url}')
                return False
            
        except Exception as e:
            self.logger.warning(f'Error en POST request con JavaScript: {e}')
            # Fallback a GET normal
            try:
                self.driver.get(url)
                return True
            except:
                return False
    
    def _load_page_with_requests_post(self, url: str) -> bool:
        """Cargar página usando requests POST y luego pasar cookies a Selenium"""
        if not REQUESTS_AVAILABLE:
            return False
        
        try:
            self.logger.info(f'Intentando acceder a {url} usando requests POST...')
            
            # Primero hacer un GET a la página base para obtener cookies de sesión
            session = requests.Session()
            base_headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'es-CL,es;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Primero visitar la página base
            self.logger.info('Visitando página base para obtener cookies de sesión...')
            base_response = session.get(BASE_URL, headers=base_headers, timeout=30)
            time.sleep(random.uniform(1, 2))
            
            # Ahora hacer POST con las cookies de sesión
            post_headers = {
                **base_headers,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': BASE_URL,
                'Referer': BASE_URL,
                'X-Requested-With': 'XMLHttpRequest',  # Simular AJAX
            }
            
            # Hacer POST request con datos mínimos
            response = session.post(
                url,
                headers=post_headers,
                data={},  # Datos vacíos
                allow_redirects=True,
                timeout=30
            )
            
            if response.status_code in [200, 302, 307]:  # Aceptar también redirects
                self.logger.info(f'POST request exitoso (código {response.status_code}), cargando página en Selenium...')
                
                # Cargar la URL en Selenium
                self.driver.get(url)
                
                # Agregar cookies de la sesión de requests
                if session.cookies:
                    for cookie in session.cookies:
                        try:
                            cookie_dict = {
                                'name': cookie.name,
                                'value': cookie.value,
                                'domain': cookie.domain if cookie.domain else '.super.lider.cl',
                                'path': cookie.path if cookie.path else '/',
                            }
                            # Agregar campos opcionales si existen
                            if hasattr(cookie, 'secure') and cookie.secure:
                                cookie_dict['secure'] = True
                            if hasattr(cookie, 'expires') and cookie.expires:
                                cookie_dict['expires'] = cookie.expires
                            
                            self.driver.add_cookie(cookie_dict)
                        except Exception as e:
                            self.logger.debug(f'Error agregando cookie {cookie.name}: {e}')
                    
                    # Recargar para aplicar cookies
                    self.driver.get(url)
                    time.sleep(2)
                
                return True
            else:
                self.logger.warning(f'POST request retornó código {response.status_code}')
                return False
                
        except Exception as e:
            self.logger.warning(f'Error en requests POST: {e}')
            return False

    def parse(self, response: HtmlResponse) -> None:
        """Método principal - Acceso directo a página de carnes usando POST"""
        self.logger.info('Iniciando scraping directamente en: %s', CARNES_DIRECT_URL)
        
        if not self.driver:
            self.logger.error('Driver no inicializado')
            return
        
        try:
            # Intentar acceso usando diferentes métodos
            load_success = False
            
            # Método 1: Intentar GET directo primero (más confiable)
            try:
                self.logger.info('Cargando página de carnes con GET...')
                self.driver.get(CARNES_DIRECT_URL)
                load_success = True
            except Exception as e:
                self.logger.warning(f'Error con GET directo: {e}')
            
            # Método 2: Si GET falla, intentar con requests POST
            if not load_success and REQUESTS_AVAILABLE:
                self.logger.info('Intentando POST con requests...')
                load_success = self._load_page_with_requests_post(CARNES_DIRECT_URL)
            
            # Método 3: Si requests POST falla, intentar con JavaScript POST
            if not load_success:
                try:
                    self.logger.info('Intentando POST con JavaScript...')
                    load_success = self._load_page_with_post(CARNES_DIRECT_URL)
                except Exception as e:
                    self.logger.warning(f'Error en POST JavaScript: {e}')
            
            # Verificar que la carga fue exitosa
            if not load_success:
                self.logger.error('No se pudo cargar la página con ningún método')
                return
            
            # Simular comportamiento humano durante la carga
            self._simulate_human_page_load()
            
            # Delays humanos
            self._human_like_delay(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)
            time.sleep(INITIAL_PAGE_WAIT)
            
            # Verificar si hay captcha
            if self._is_blocked_page():
                self.logger.warning('Página de bloqueo detectada, resolviendo captcha...')
                if not self._solve_captcha_selenium():
                    self.logger.error('No se pudo resolver captcha')
                    return
                else:
                    time.sleep(5)
            
            self._save_cookies()
            
            self._scroll_to_load_content()
            items = self._find_product_elements()
            
            if not items:
                self.logger.warning('No se encontraron productos')
                return
            
            self.logger.info('Procesando %d productos', len(items))
            for idx, item_element in enumerate(items, start=1):
                product = self._extract_product_data(item_element, idx)
                if product:
                    yield product
                    
        except Exception as e:
            self.logger.error(f'Error durante el scraping: {e}', exc_info=True)
        finally:
            self._cleanup_driver()

    def _is_blocked_page(self) -> bool:
        """Verificar página de bloqueo"""
        try:
            return '/blocked' in self.driver.current_url.lower() or 'captcha' in self.driver.page_source.lower()
        except:
            return False

    def _solve_captcha_selenium(self) -> bool:
        """Resolver captcha usando el XPath del iframe"""
        try:
            self.logger.info('Resolviendo captcha usando XPath del iframe...')
            
            # Método principal: Buscar el iframe y cambiar al contexto usando el índice
            self.logger.info('Buscando iframe del captcha...')
            
            # Asegurarse de estar en el contexto principal
            self.driver.switch_to.default_content()
            
            # Buscar todos los iframes y encontrar el índice del captcha
            iframes = self.driver.find_elements(By.TAG_NAME, 'iframe')
            iframe_index = None
            
            for idx, ifr in enumerate(iframes):
                try:
                    # Verificar si este iframe está dentro del contenedor px-captcha
                    parent = ifr.find_element(By.XPATH, './..')
                    if parent.get_attribute('id') == 'px-captcha':
                        iframe_index = idx
                        self.logger.info(f'✅ Iframe encontrado en índice {idx}')
                        break
                except:
                    continue
            
            # Si no se encontró por parent, intentar buscar el contenedor primero
            if iframe_index is None:
                try:
                    container = self.driver.find_element(By.ID, 'px-captcha')
                    iframe = container.find_element(By.TAG_NAME, 'iframe')
                    # Encontrar el índice de este iframe
                    iframes = self.driver.find_elements(By.TAG_NAME, 'iframe')
                    for idx, ifr in enumerate(iframes):
                        if ifr == iframe:
                            iframe_index = idx
                            self.logger.info(f'✅ Iframe encontrado en índice {idx} (método contenedor)')
                            break
                except Exception as e:
                    self.logger.debug(f'Error buscando iframe por contenedor: {e}')
            
            if iframe_index is None:
                raise Exception('No se pudo encontrar el iframe del captcha')
            
            # Esperar un momento para que el iframe esté completamente cargado
            time.sleep(1)
            
            # Cambiar al contexto del iframe usando el índice
            try:
                # Verificar que el iframe sigue existiendo antes de cambiar
                iframes_check = self.driver.find_elements(By.TAG_NAME, 'iframe')
                if iframe_index >= len(iframes_check):
                    raise Exception(f'Índice {iframe_index} fuera de rango, hay {len(iframes_check)} iframes')
                
                self.driver.switch_to.frame(iframe_index)
                self.logger.info(f'✅ Cambiado al contexto del iframe (índice {iframe_index})')
            except Exception as e:
                self.logger.error(f'Error cambiando al iframe: {e}')
                # Intentar de nuevo con un pequeño delay
                try:
                    time.sleep(1)
                    self.driver.switch_to.default_content()
                    self.driver.switch_to.frame(iframe_index)
                    self.logger.info(f'✅ Cambiado al iframe en segundo intento (índice {iframe_index})')
                except Exception as e2:
                    self.logger.error(f'Error definitivo cambiando al iframe: {e2}')
                    raise
                
                time.sleep(2)
                
                # Buscar el botón dentro del iframe
                self.logger.info('Buscando botón dentro del iframe...')
                
                # Intentar múltiples selectores para el botón
                button = None
                button_selectors = [
                    (By.TAG_NAME, "button"),
                    (By.XPATH, "//button"),
                    (By.XPATH, "//div[@role='button']"),
                    (By.XPATH, "//div[contains(@class, 'button')]"),
                    (By.CSS_SELECTOR, "button"),
                    (By.CSS_SELECTOR, "[role='button']"),
                ]
                
                for selector_type, selector_value in button_selectors:
                    try:
                        button = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((selector_type, selector_value))
                        )
                        if button and button.is_displayed():
                            self.logger.info(f'Botón encontrado con {selector_type}: {selector_value}')
                            break
                    except:
                        continue
                
                if not button:
                    # Buscar cualquier elemento clickeable grande
                    try:
                        all_buttons = self.driver.find_elements(By.TAG_NAME, "*")
                        for elem in all_buttons:
                            try:
                                if elem.is_displayed() and elem.size['width'] > 50 and elem.size['height'] > 30:
                                    # Verificar si tiene eventos de click
                                    onclick = elem.get_attribute('onclick')
                                    role = elem.get_attribute('role')
                                    if onclick or role == 'button' or elem.tag_name == 'button':
                                        button = elem
                                        self.logger.info('Botón encontrado por tamaño y atributos')
                                        break
                            except:
                                continue
                    except:
                        pass
                
                if button:
                    self.logger.info('Botón encontrado, haciendo click y mantener...')
                    
                    # Scroll al botón dentro del iframe
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
                    time.sleep(random.uniform(0.5, 1))
                    
                    # Obtener posición del botón para usar mouse real
                    location = button.location
                    size = button.size
                    center_x = location['x'] + size['width'] / 2
                    center_y = location['y'] + size['height'] / 2
                    
                    # Obtener posición del iframe en la página principal
                    self.driver.switch_to.default_content()
                    
                    # Buscar el iframe de nuevo para obtener su posición
                    iframes = self.driver.find_elements(By.TAG_NAME, 'iframe')
                    iframe_element = None
                    for idx, ifr in enumerate(iframes):
                        try:
                            parent = ifr.find_element(By.XPATH, './..')
                            if parent.get_attribute('id') == 'px-captcha':
                                iframe_element = ifr
                                break
                        except:
                            continue
                    
                    if iframe_element:
                        iframe_location = iframe_element.location
                        # Calcular posición absoluta del botón
                        absolute_x = iframe_location['x'] + center_x
                        absolute_y = iframe_location['y'] + center_y
                    else:
                        # Fallback: usar posición relativa
                        absolute_x = center_x
                        absolute_y = center_y
                    
                    # Volver al iframe usando el índice
                    self.driver.switch_to.frame(iframe_index)
                    
                    # Usar mouse real si está disponible
                    if self.mouse:
                        self.logger.info('Usando mouse real para click y mantener...')
                        # Mover mouse de forma humana
                        current_x, current_y = self.mouse.position
                        distance = math.sqrt((absolute_x - current_x)**2 + (absolute_y - current_y)**2)
                        steps = max(15, int(distance / 8))
                        
                        for i in range(steps):
                            progress = (i + 1) / steps
                            eased = progress * progress * (3 - 2 * progress)
                            x = current_x + (absolute_x - current_x) * eased
                            y = current_y + (absolute_y - current_y) * eased
                            x += random.uniform(-1, 1)
                            y += random.uniform(-1, 1)
                            self.mouse.position = (int(x), int(y))
                            time.sleep(random.uniform(0.01, 0.02))
                        
                        self.mouse.position = (int(absolute_x), int(absolute_y))
                        time.sleep(random.uniform(0.2, 0.4))
                        
                        # Presionar y mantener
                        self.logger.info(f'Manteniendo click por {CAPTCHA_HOLD_TIME} segundos...')
                        self.mouse.press(Button.left)
                        
                        # Mantener con pequeñas variaciones
                        for i in range(CAPTCHA_HOLD_TIME):
                            time.sleep(1)
                            if i % 2 == 0:
                                current_x, current_y = self.mouse.position
                                self.mouse.position = (
                                    int(current_x + random.uniform(-2, 2)),
                                    int(current_y + random.uniform(-2, 2))
                                )
                        
                        # Soltar
                        self.mouse.release(Button.left)
                        time.sleep(random.uniform(0.3, 0.7))
                    else:
                        # Fallback a ActionChains
                        self.logger.info('Usando ActionChains para click y mantener...')
                        actions = ActionChains(self.driver)
                        actions.move_to_element(button).click_and_hold(button).perform()
                        self.logger.info(f'Manteniendo click por {CAPTCHA_HOLD_TIME} segundos...')
                        time.sleep(CAPTCHA_HOLD_TIME)
                        actions.release(button).perform()
                    
                    # Volver al contexto principal
                    self.driver.switch_to.default_content()
                    time.sleep(5)
                    
                    # Verificar si se resolvió
                    if not self._is_blocked_page():
                        self.logger.info('✅ Captcha resuelto exitosamente usando iframe!')
                        return True
                    else:
                        self.logger.warning('Página sigue bloqueada después de resolver captcha')
                else:
                    self.logger.warning('No se encontró botón dentro del iframe')
                    self.driver.switch_to.default_content()
                    
            except TimeoutException:
                self.logger.warning('Timeout esperando iframe del captcha')
                try:
                    self.driver.switch_to.default_content()
                except:
                    pass
            except Exception as e:
                self.logger.warning(f'Error accediendo al iframe: {e}')
                try:
                    self.driver.switch_to.default_content()
                except:
                    pass
            
            # Métodos alternativos (fallback) - Solo si el método principal falló
            self.logger.info('Intentando métodos alternativos como fallback...')
            
            # Intentar métodos alternativos con Shadow DOM (por si acaso)
            max_wait = 10  # Reducido ya que el método principal debería funcionar
            shadow_ready = False  # Inicializar variable
            for attempt in range(max_wait):
                # Verificar que la ventana sigue abierta
                try:
                    self.driver.current_url
                except Exception:
                    self.logger.error('Ventana del navegador cerrada')
                    return False
                
                time.sleep(1)
                
                # Script mejorado que también intenta forzar la creación del shadow root
                check_script = """
                return (function() {
                    const container = document.querySelector('#px-captcha');
                    if (!container) return {exists: false, hasShadow: false};
                    
                    // Intentar acceder al shadow root
                    let shadowRoot = container.shadowRoot;
                    
                    // Si no existe, intentar forzar su creación moviendo el mouse
                    if (!shadowRoot) {
                        // Disparar eventos para activar el shadow DOM
                        const mouseOver = new MouseEvent('mouseover', { bubbles: true, cancelable: true });
                        container.dispatchEvent(mouseOver);
                        
                        const mouseMove = new MouseEvent('mousemove', { bubbles: true, cancelable: true });
                        container.dispatchEvent(mouseMove);
                        
                        // Intentar de nuevo
                        shadowRoot = container.shadowRoot;
                    }
                    
                    if (!shadowRoot) return {exists: true, hasShadow: false, attempt: arguments[0]};
                    
                    const button = shadowRoot.querySelector('button');
                    if (!button) {
                        // Buscar cualquier elemento clickeable
                        const clickable = shadowRoot.querySelector('button, [role="button"], div[onclick]');
                        if (clickable) {
                            return {exists: true, hasShadow: true, hasButton: true, ready: true, element: 'found'};
                        }
                        return {exists: true, hasShadow: true, hasButton: false};
                    }
                    
                    return {exists: true, hasShadow: true, hasButton: true, ready: true};
                })();
                """
                
                check_result = self.driver.execute_script(check_script, attempt)
                
                if check_result and check_result.get('ready'):
                    shadow_ready = True
                    self.logger.info(f'Shadow DOM listo después de {attempt + 1} segundos')
                    break
                
                if attempt % 5 == 0:
                    self.logger.info(f'Esperando Shadow DOM... intento {attempt + 1}/{max_wait}, estado: {check_result}')
            
            if not shadow_ready:
                self.logger.warning('Shadow DOM no está disponible después de esperar')
                
                # Método alternativo 1: Buscar dentro de iframes
                self.logger.info('Buscando captcha en iframes...')
                try:
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    for iframe in iframes:
                        try:
                            self.driver.switch_to.frame(iframe)
                            buttons = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'PULSAR') or contains(text(), 'Pulsar') or contains(text(), 'CLICK') or contains(text(), 'Mantener')]")
                            if buttons:
                                button = buttons[0]
                                self.logger.info('Botón encontrado en iframe, haciendo click y mantener...')
                                actions = ActionChains(self.driver)
                                actions.click_and_hold(button).perform()
                                time.sleep(CAPTCHA_HOLD_TIME)
                                actions.release(button).perform()
                                self.driver.switch_to.default_content()
                                time.sleep(5)
                                if not self._is_blocked_page():
                                    self.logger.info('Captcha resuelto en iframe')
                                    return True
                            self.driver.switch_to.default_content()
                        except:
                            self.driver.switch_to.default_content()
                            continue
                except Exception as e:
                    self.logger.warning(f'Error buscando en iframes: {e}')
                
                # Método alternativo 2: Buscar botón directamente en la página
                self.logger.info('Buscando botón directamente en la página...')
                try:
                    self.driver.switch_to.default_content()
                    # Buscar por texto
                    buttons = self.driver.find_elements(By.XPATH, "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pulsar') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'click') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'mantener')]")
                    
                    # Si no se encuentra por texto, buscar por clase o ID
                    if not buttons:
                        buttons = self.driver.find_elements(By.XPATH, "//button[contains(@class, 'captcha') or contains(@class, 'challenge') or contains(@id, 'captcha')]")
                    
                    # Si aún no se encuentra, buscar cualquier botón grande cerca del centro
                    if not buttons:
                        buttons = self.driver.find_elements(By.TAG_NAME, "button")
                        # Filtrar botones visibles y grandes
                        visible_buttons = [b for b in buttons if b.is_displayed() and b.size['width'] > 100 and b.size['height'] > 30]
                        if visible_buttons:
                            buttons = visible_buttons
                    
                    if buttons:
                        button = buttons[0]
                        self.logger.info(f'Botón encontrado: {button.text if button.text else "sin texto"}, haciendo click y mantener...')
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
                        time.sleep(1)
                        actions = ActionChains(self.driver)
                        actions.move_to_element(button).click_and_hold(button).perform()
                        self.logger.info(f'Manteniendo click por {CAPTCHA_HOLD_TIME} segundos...')
                        time.sleep(CAPTCHA_HOLD_TIME)
                        actions.release(button).perform()
                        time.sleep(5)
                        if not self._is_blocked_page():
                            self.logger.info('Captcha resuelto con método alternativo')
                            return True
                except Exception as e:
                    self.logger.warning(f'Método alternativo falló: {e}')
                
                # Método alternativo 3: Usar JavaScript para encontrar y clickear cualquier elemento relacionado
                self.logger.info('Intentando método JavaScript directo...')
                try:
                    js_click_script = """
                    return (function() {
                        // Buscar cualquier elemento clickeable relacionado con captcha
                        const selectors = [
                            'button:contains("PULSAR")',
                            'button:contains("Pulsar")',
                            '[role="button"]',
                            'div[onclick]',
                            'button'
                        ];
                        
                        for (let selector of selectors) {
                            try {
                                const elements = document.querySelectorAll(selector);
                                for (let el of elements) {
                                    if (el.offsetWidth > 100 && el.offsetHeight > 30 && window.getComputedStyle(el).display !== 'none') {
                                        // Hacer click y mantener
                                        const mouseDown = new MouseEvent('mousedown', { bubbles: true, cancelable: true, buttons: 1 });
                                        el.dispatchEvent(mouseDown);
                                        el.click();
                                        return {success: true, element: selector};
                                    }
                                }
                            } catch(e) {}
                        }
                        return {success: false, message: 'No clickable element found'};
                    })();
                    """
                    js_result = self.driver.execute_script(js_click_script)
                    if js_result and js_result.get('success'):
                        self.logger.info(f'Click iniciado con JavaScript, manteniendo por {CAPTCHA_HOLD_TIME} segundos...')
                        time.sleep(CAPTCHA_HOLD_TIME)
                        
                        # Soltar
                        release_js = """
                        document.querySelectorAll('button, [role="button"]').forEach(btn => {
                            const mouseUp = new MouseEvent('mouseup', { bubbles: true, cancelable: true });
                            btn.dispatchEvent(mouseUp);
                        });
                        """
                        self.driver.execute_script(release_js)
                        time.sleep(5)
                        if not self._is_blocked_page():
                            self.logger.info('Captcha resuelto con JavaScript directo')
                            return True
                except Exception as e:
                    self.logger.warning(f'JavaScript directo falló: {e}')
                
                # Tomar screenshot para debugging
                try:
                    self.driver.save_screenshot('captcha_debug.png')
                    self.logger.info('Screenshot guardado en captcha_debug.png')
                except:
                    pass
                return False
            
            # Usar mouse real para hacer click y mantener (más humano)
            self.logger.info('Haciendo click y manteniendo por 10 segundos con mouse real...')
            
            try:
                # Obtener posición del contenedor del captcha
                container = self.driver.find_element(By.ID, 'px-captcha')
                if container:
                    # Scroll suave al captcha
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", container)
                    time.sleep(random.uniform(1, 2))
                    
                    # Obtener posición del contenedor
                    location = container.location
                    size = container.size
                    center_x = location['x'] + size['width'] / 2
                    center_y = location['y'] + size['height'] / 2
                    
                    # Mover mouse de forma humana al centro del captcha
                    if self.mouse:
                        self.logger.info('Usando mouse real para simulación humana...')
                        # Mover mouse de forma natural
                        current_x, current_y = self.mouse.position
                        distance = math.sqrt((center_x - current_x)**2 + (center_y - current_y)**2)
                        steps = max(15, int(distance / 8))
                        
                        for i in range(steps):
                            progress = (i + 1) / steps
                            # Curva de aceleración/desaceleración
                            eased = progress * progress * (3 - 2 * progress)
                            x = current_x + (center_x - current_x) * eased
                            y = current_y + (center_y - current_y) * eased
                            # Variaciones aleatorias pequeñas
                            x += random.uniform(-1, 1)
                            y += random.uniform(-1, 1)
                            self.mouse.position = (int(x), int(y))
                            time.sleep(random.uniform(0.01, 0.02))
                        
                        # Ajuste final
                        self.mouse.position = (int(center_x), int(center_y))
                        time.sleep(random.uniform(0.2, 0.4))
                        
                        # Presionar y mantener con mouse real
                        self.logger.info(f'Manteniendo click por {CAPTCHA_HOLD_TIME} segundos...')
                        self.mouse.press(Button.left)
                        
                        # Mantener presionado con pequeñas variaciones (como haría un humano)
                        for i in range(CAPTCHA_HOLD_TIME):
                            time.sleep(1)
                            # Pequeños movimientos para simular mano temblorosa (más realista)
                            if i % 2 == 0:
                                current_x, current_y = self.mouse.position
                                self.mouse.position = (
                                    int(current_x + random.uniform(-2, 2)),
                                    int(current_y + random.uniform(-2, 2))
                                )
                        
                        # Soltar
                        self.mouse.release(Button.left)
                        time.sleep(random.uniform(0.3, 0.7))
                        
                        # Verificar si se resolvió
                        time.sleep(5)
                        if not self._is_blocked_page():
                            self.logger.info('Captcha resuelto exitosamente con mouse real')
                            return True
                    else:
                        # Fallback a JavaScript si no hay mouse disponible
                        self.logger.info('Mouse no disponible, usando JavaScript...')
                        click_script = """
                        return (function() {
                            const container = document.querySelector('#px-captcha');
                            if (!container) return {success: false, message: 'No container'};
                            const shadowRoot = container.shadowRoot;
                            if (!shadowRoot) return {success: false, message: 'No shadow root'};
                            const button = shadowRoot.querySelector('button');
                            if (!button) return {success: false, message: 'No button'};
                            const mouseDown = new MouseEvent('mousedown', { bubbles: true, cancelable: true, buttons: 1 });
                            button.dispatchEvent(mouseDown);
                            button.click();
                            return {success: true};
                        })();
                        """
                        result = self.driver.execute_script(click_script)
                        if result and result.get('success'):
                            time.sleep(CAPTCHA_HOLD_TIME)
                            release_script = """
                            const container = document.querySelector('#px-captcha');
                            if (container && container.shadowRoot) {
                                const button = container.shadowRoot.querySelector('button');
                                if (button) {
                                    const mouseUp = new MouseEvent('mouseup', { bubbles: true, cancelable: true });
                                    button.dispatchEvent(mouseUp);
                                }
                            }
                            """
                            self.driver.execute_script(release_script)
                            time.sleep(5)
                            if not self._is_blocked_page():
                                self.logger.info('Captcha resuelto con JavaScript')
                                return True
            except Exception as e:
                self.logger.warning(f'Error con mouse real, usando JavaScript: {e}')
                # Fallback a método JavaScript
                click_script = """
                return (function() {
                    const container = document.querySelector('#px-captcha');
                    if (!container) return {success: false, message: 'No container'};
                    const shadowRoot = container.shadowRoot;
                    if (!shadowRoot) return {success: false, message: 'No shadow root'};
                    const button = shadowRoot.querySelector('button');
                    if (!button) return {success: false, message: 'No button'};
                    const mouseDown = new MouseEvent('mousedown', { bubbles: true, cancelable: true, buttons: 1 });
                    button.dispatchEvent(mouseDown);
                    return {success: true};
                })();
                """
                result = self.driver.execute_script(click_script)
                if result and result.get('success'):
                    time.sleep(CAPTCHA_HOLD_TIME)
                    self.driver.execute_script("""
                    const container = document.querySelector('#px-captcha');
                    if (container && container.shadowRoot) {
                        const button = container.shadowRoot.querySelector('button');
                        if (button) {
                            const mouseUp = new MouseEvent('mouseup', { bubbles: true, cancelable: true });
                            button.dispatchEvent(mouseUp);
                        }
                    }
                    """)
                    time.sleep(5)
                    if not self._is_blocked_page():
                        self.logger.info('Captcha resuelto con JavaScript fallback')
                        return True
            
            if self._is_blocked_page():
                self.logger.warning('Página sigue bloqueada después de resolver captcha')
            return False
            
            return False
        except Exception as e:
            self.logger.error(f'Error al resolver captcha: {e}', exc_info=True)
            return False

    def _try_direct_access(self) -> bool:
        """Acceso directo a carnes"""
        try:
            # Verificar que la ventana sigue abierta
            try:
                self.driver.current_url
            except Exception:
                self.logger.error('Ventana del navegador cerrada, no se puede acceder')
                return False
            
            self.logger.info(f'Acceso directo a: {CARNES_DIRECT_URL}')
            self.driver.get(CARNES_DIRECT_URL)
            time.sleep(random.uniform(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX))
            time.sleep(INITIAL_PAGE_WAIT)
            
            if self._is_blocked_page():
                return self._solve_captcha_selenium()
            return True
        except Exception as e:
            self.logger.error(f'Error en acceso directo: {e}')
            return False

    def _click_carnes_button(self) -> bool:
        """Click en botón de carnes con simulación humana"""
        try:
            element = WebDriverWait(self.driver, ELEMENT_WAIT_TIMEOUT).until(
                EC.element_to_be_clickable((By.XPATH, CLICK_XPATH))
            )
            
            # Scroll humano (suave y gradual)
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            self._human_like_delay(1, 2)
            
            # Hover sobre el elemento antes de clickear (comportamiento humano)
            try:
                actions = ActionChains(self.driver)
                actions.move_to_element(element).perform()
                self._human_like_delay(0.3, 0.8)
            except:
                pass
            
            # Click humano
            self._human_like_click(element)
            
            # Delay después del click
            self._human_like_delay(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)
            time.sleep(AFTER_CLICK_WAIT)
            return True
        except TimeoutException:
            return False

    def _scroll_to_load_content(self) -> None:
        """Scroll humano para cargar contenido"""
        try:
            self.logger.info('Haciendo scroll humano para cargar contenido...')
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            
            for attempt in range(MAX_SCROLL_ATTEMPTS):
                # Scroll gradual y humano (en pasos)
                current_scroll = self.driver.execute_script("return window.pageYOffset;")
                target_scroll = self.driver.execute_script("return document.body.scrollHeight;")
                
                # Scroll en pasos para simular comportamiento humano
                steps = random.randint(5, 10)
                scroll_distance = target_scroll - current_scroll
                step_size = scroll_distance / steps
                
                for step in range(steps):
                    scroll_to = current_scroll + (step_size * (step + 1))
                    # Agregar pequeñas variaciones aleatorias
                    scroll_to += random.uniform(-10, 10)
                    self.driver.execute_script(f"window.scrollTo(0, {scroll_to});")
                    time.sleep(random.uniform(0.1, 0.3))
                
                # Scroll final suave
                self.driver.execute_script("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'});")
                
                # Delay humano variable
                self._human_like_delay(SCROLL_WAIT_TIME, SCROLL_WAIT_TIME + 2)
                
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                
                # A veces hacer scroll hacia arriba un poco (comportamiento humano)
                if random.random() < 0.3:
                    scroll_up = random.randint(100, 300)
                    self.driver.execute_script(f"window.scrollBy(0, -{scroll_up});")
                    time.sleep(random.uniform(0.5, 1.5))
                    self.driver.execute_script("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'});")
                    time.sleep(random.uniform(0.5, 1))
            
            # Volver arriba de forma gradual
            self.logger.info('Volviendo arriba...')
            current_scroll = self.driver.execute_script("return window.pageYOffset;")
            steps = random.randint(8, 15)
            for step in range(steps):
                scroll_to = current_scroll - (current_scroll * (step + 1) / steps)
                self.driver.execute_script(f"window.scrollTo(0, {max(0, scroll_to)});")
                time.sleep(random.uniform(0.05, 0.15))
            
            self.driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
            self._human_like_delay(1, 2)
        except Exception as e:
            self.logger.warning(f'Error durante scroll: {e}')

    def _find_product_elements(self) -> List:
        """Encontrar elementos de productos"""
        try:
            WebDriverWait(self.driver, ELEMENT_WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, ITEMS_XPATH))
            )
            return self.driver.find_elements(By.XPATH, ITEMS_XPATH)
        except:
            return []

    def _extract_product_data(self, element, index: int) -> Optional[ProductItem]:
        """Extraer datos del producto"""
        try:
            product = ProductItem()
            product['index'] = index
            
            try:
                name_elem = element.find_element(By.XPATH, ".//h3 | .//h2 | .//span[contains(@class, 'name')]")
                product['name'] = name_elem.text.strip()
            except:
                product['name'] = 'Sin nombre'
            
            try:
                price_elem = element.find_element(By.XPATH, ".//span[contains(@class, 'price')] | .//div[contains(@class, 'price')]")
                product['price'] = price_elem.text.strip()
            except:
                product['price'] = 'Sin precio'
            
            try:
                img_elem = element.find_element(By.XPATH, ".//img")
                img_url = img_elem.get_attribute('src') or img_elem.get_attribute('data-src') or ''
                product['image_url'] = self._normalize_url(img_url) if img_url else ''
            except:
                product['image_url'] = ''
            
            try:
                link_elem = element.find_element(By.XPATH, ".//a[@href]")
                href = link_elem.get_attribute('href') or ''
                product['link'] = self._normalize_url(href) if href else ''
            except:
                product['link'] = ''
            
            product['description'] = ''
            
            if not product.get('name') or product['name'] == 'Sin nombre':
                return None
            
            return product
        except Exception as e:
            self.logger.error(f'Error al extraer producto {index}: {e}')
            return None

    def _normalize_url(self, url: str) -> str:
        """Normalizar URL"""
        if not url:
            return ''
        url = url.strip()
        if url.startswith('http://') or url.startswith('https://'):
            return url
        if url.startswith('/'):
            return urljoin(BASE_URL, url)
        return urljoin(BASE_URL, '/' + url)

    def _save_cookies(self) -> None:
        """Guardar cookies"""
        try:
            cookies = self.driver.get_cookies()
            if cookies:
                with open(self.cookies_file, 'w', encoding='utf-8') as f:
                    json.dump(cookies, f, indent=2)
                self.logger.info(f'Cookies guardadas: {len(cookies)}')
        except Exception as e:
            self.logger.warning(f'Error al guardar cookies: {e}')

    def _cleanup_driver(self) -> None:
        """Cerrar driver"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

    def closed(self, reason: str) -> None:
        """Cerrar cuando el spider se cierra"""
        self._cleanup_driver()

