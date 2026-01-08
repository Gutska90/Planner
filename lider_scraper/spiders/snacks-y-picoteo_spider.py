"""
Spider para extraer productos de snacks y picoteo de Lider.cl
Replica la lógica de los otros spiders con paginación y soporte para captcha
"""
import re
import time
import random
from typing import Optional
from urllib.parse import urljoin

import scrapy
from scrapy.http import HtmlResponse, Request
from scrapy.utils.response import open_in_browser
from itemadapter import ItemAdapter

try:
    from twocaptcha import TwoCaptcha
    TWOCAPTCHA_AVAILABLE = True
except ImportError:
    TWOCAPTCHA_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import undetected_chromedriver as uc
    UNDETECTED_CHROMEDRIVER_AVAILABLE = True
except ImportError:
    UNDETECTED_CHROMEDRIVER_AVAILABLE = False

from lider_scraper.items import ProductItem


def _clean_money(text: str | None) -> str | None:
    """Limpia y extrae valores monetarios"""
    if not text:
        return None
    text = text.strip()
    m = re.search(r"\$\s?\d{1,3}(?:\.\d{3})*", text)
    return m.group(0).replace(" ", "") if m else None


def _clean_text(text: str | None) -> str | None:
    """Limpia espacios en blanco múltiples"""
    if not text:
        return None
    t = re.sub(r"\s+", " ", text).strip()
    return t or None


class SnacksYPicoteoSpider(scrapy.Spider):
    name = "snacks-y-picoteo"
    allowed_domains = ["super.lider.cl"]
    
    # XPath optimizado para capturar TODOS los productos
    PRODUCT_XPATHS = [
        # XPath recomendado - captura todos los enlaces de productos directamente
        "//a[contains(@href, '/ip/') and normalize-space(.) != '']",
        # Fallback: buscar links de productos y obtener su contenedor padre
        '//a[contains(@href, "/ip/")]/ancestor::div[contains(@class, "product") or contains(@class, "item") or contains(@class, "card")][1]',
        # XPath original proporcionado
        '//*[@id="0"]/section/div/div[1]/div/div',
        # Versión más genérica que busca contenedores de productos
        '//section[contains(@class, "product") or contains(@class, "item")]//div[contains(@class, "product")]',
        # Buscar por estructura de grid/list
        '//div[contains(@class, "product") or contains(@class, "item")]//a[contains(@href, "/ip/")]/ancestor::div[contains(@class, "product") or @data-product-id or @data-item-id]',
        # Último recurso: cualquier link de producto y su contenedor cercano
        '//a[contains(@href, "/ip/")]/parent::*/parent::*',
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 2.0,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS": 1,  # Reducido para evitar bloqueos
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 2,
        "AUTOTHROTTLE_MAX_DELAY": 10,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 0.5,
        "HTTPCACHE_ENABLED": False,  # Desactivado para evitar caché de páginas bloqueadas
        "FEED_EXPORT_ENCODING": "utf-8",
        "LOG_LEVEL": "INFO",
        "ROBOTSTXT_OBEY": False,
        "USER_AGENT": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-CL,es;q=0.9,es-ES;q=0.8,en-US;q=0.7,en;q=0.6",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        },
        "ITEM_PIPELINES": {
            "lider_scraper.pipelines.JsonPipeline": 300,
            "lider_scraper.pipelines.ExcelPipeline": 400,
        },
        "DOWNLOADER_MIDDLEWARES": {
            "lider_scraper.middlewares.ProxyMiddleware": 543,
            "lider_scraper.middlewares.CaptchaMiddleware": 544,
        },
    }

    def __init__(self, *args, **kwargs):
        super(SnacksYPicoteoSpider, self).__init__(*args, **kwargs)
        self.proxies = []
        self.current_proxy_index = 0
        self.two_captcha_api_key = kwargs.get('twocaptcha_key', '')
        self.two_captcha_solver = None
        self.use_selenium = kwargs.get('use_selenium', 'true').lower() == 'true'
        self.driver = None
        
        # Inicializar captcha solver si hay API key
        if self.two_captcha_api_key and TWOCAPTCHA_AVAILABLE:
            try:
                self.two_captcha_solver = TwoCaptcha(self.two_captcha_api_key)
                self.logger.info("2Captcha solver inicializado")
            except Exception as e:
                self.logger.warning(f"No se pudo inicializar 2Captcha: {e}")
        
        # Cargar proxies
        self._load_proxies()
        
        # Inicializar Selenium si está habilitado (lazy loading en start_requests)
        if self.use_selenium:
            if UNDETECTED_CHROMEDRIVER_AVAILABLE:
                self.logger.info("Selenium habilitado (se inicializará cuando sea necesario)")
            else:
                self.logger.warning("undetected-chromedriver no disponible. Instala con: pip install undetected-chromedriver")
                self.use_selenium = False

    def _load_proxies(self):
        """Cargar proxies desde fuentes gratuitas"""
        if not REQUESTS_AVAILABLE:
            self.logger.warning("requests no disponible, no se cargarán proxies")
            return
        
        self.logger.info("Cargando proxies gratuitos...")
        
        # Fuentes de proxies gratuitos
        sources = [
            self._get_proxies_from_proxyscrape,
            self._get_proxies_from_geonode,
        ]
        
        for source_func in sources:
            try:
                proxies = source_func()
                if proxies:
                    self.proxies.extend(proxies)
                    self.logger.info(f"Obtenidos {len(proxies)} proxies de {source_func.__name__}")
            except Exception as e:
                self.logger.debug(f"Error obteniendo proxies de {source_func.__name__}: {e}")
        
        if not self.proxies:
            self.logger.warning("No se obtuvieron proxies, continuando sin proxies")
        else:
            self.logger.info(f"Total de proxies disponibles: {len(self.proxies)}")

    def _get_proxies_from_proxyscrape(self):
        """Obtener proxies de ProxyScrape"""
        try:
            url = "https://api.proxyscrape.com/v2/?request=get&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                proxies = [p.strip() for p in response.text.strip().split('\n') if p.strip() and ':' in p]
                return proxies[:50]  # Limitar a 50
        except:
            pass
        return []

    def _get_proxies_from_geonode(self):
        """Obtener proxies de Geonode"""
        try:
            url = "https://proxylist.geonode.com/api/proxy-list?limit=50&page=1&sort_by=lastChecked&sort_type=desc&protocols=http%2Chttps"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                proxies = []
                for proxy in data.get('data', [])[:50]:
                    ip = proxy.get('ip')
                    port = proxy.get('port')
                    if ip and port:
                        proxies.append(f"{ip}:{port}")
                return proxies
        except:
            pass
        return []

    def _get_next_proxy(self):
        """Obtener el siguiente proxy de la lista (rotación)"""
        if not self.proxies:
            return None
        
        proxy = self.proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        return proxy

    def start_requests(self):
        """Iniciar requests con manejo de URL"""
        url = getattr(self, "url", None)
        if not url:
            # URL por defecto para snacks y picoteo
            url = "https://super.lider.cl/browse/bebidas-y-snacks/snacks-y-picoteo/13901022_66742898"
        
        # Si tenemos Selenium, usar directamente para cargar la página
        if self.use_selenium and UNDETECTED_CHROMEDRIVER_AVAILABLE:
            try:
                self.logger.info("🚀 Usando Selenium directamente para cargar página de snacks y picoteo...")
                # Inicializar driver si no está inicializado
                if not self.driver:
                    self._init_selenium_driver()
                
                if self.driver:
                    # Cargar página directamente con Selenium y procesar con paginación
                    success = self._load_page_with_selenium(url)
                    if success:
                        try:
                            # Procesar todas las páginas con paginación
                            self.logger.info("🔄 Iniciando procesamiento con paginación...")
                            for item in self._process_all_pages_with_pagination():
                                yield item
                            return
                        except Exception as e:
                            self.logger.error(f"Error procesando páginas con Selenium: {e}")
                    else:
                        self.logger.warning("⚠️  No se pudo cargar la página con Selenium")
                else:
                    self.logger.warning("⚠️  Driver de Selenium no disponible")
            except Exception as e:
                self.logger.error(f"❌ Error en carga inicial con Selenium: {e}")
        
        # Si no usamos Selenium o falló, intentar con Scrapy normal
        self.logger.info("🌐 Intentando con Scrapy (puede necesitar proxies o 2Captcha)...")
        # Usar proxy si está disponible
        meta = {}
        proxy = self._get_next_proxy()
        if proxy:
            meta['proxy'] = f"http://{proxy}"
            self.logger.info(f"🔄 Usando proxy: {proxy}")
        
        yield scrapy.Request(url, callback=self.parse, meta=meta, dont_filter=True)

    def parse(self, response: HtmlResponse):
        """Método principal de parsing"""
        self.logger.info(f"Status={response.status} URL={response.url}")

        # 1) Detectar bloqueo
        title = _clean_text(response.css("title::text").get() or "")
        body_text = " ".join(t.strip() for t in response.css("body *::text").getall() if t.strip()).lower()

        if "/blocked" in response.url or "robot or human" in body_text or "captcha" in body_text:
            self.logger.warning("Página bloqueada detectada")
            
            # Si tenemos Selenium disponible, intentar resolver el captcha
            if self.driver:
                self.logger.info("Intentando resolver captcha con Selenium...")
                success = self._solve_captcha_with_selenium(response.url)
                if success:
                    # Volver a hacer request después de resolver captcha
                    yield Request(
                        url=response.url,
                        callback=self.parse,
                        dont_filter=True,
                        meta={'dont_retry': True}
                    )
                    return
                else:
                    yield {
                        "_blocked": True,
                        "category_url": response.url,
                        "title": title,
                        "note": "No se pudo resolver el captcha automáticamente.",
                    }
                    return
            
            # Intentar resolver captcha si está disponible (2Captcha)
            if self.two_captcha_solver:
                self.logger.info("Intentando resolver captcha con 2Captcha...")
            
            yield {
                "_blocked": True,
                "category_url": response.url,
                "title": title,
                "note": "La página está protegida con captcha/challenge. Usa -a use_selenium=true para resolverlo automáticamente.",
            }
            return

        # 2) Procesar productos
        for item in self.parse_products(response):
            yield item

    def parse_products(self, response: HtmlResponse):
        """Método separado para parsear productos desde cualquier fuente (Scrapy o Selenium)"""
        title = _clean_text(response.css("title::text").get() or "")
        
        # Buscar productos con múltiples XPath
        product_nodes = []
        
        for xpath in self.PRODUCT_XPATHS:
            try:
                nodes = response.xpath(xpath)
                if nodes:
                    product_nodes = nodes
                    self.logger.info(f"✅ Encontrados {len(product_nodes)} productos con XPath: {xpath[:50]}...")
                    break
            except Exception as e:
                self.logger.debug(f"Error con XPath {xpath[:30]}...: {e}")
                continue

        # Si no se encontraron con XPath específico, buscar por links de productos (método de respaldo)
        if not product_nodes:
            self.logger.warning("No se encontraron productos con XPath específico, intentando método alternativo...")
            # Obtener todos los links de productos y sus contenedores
            product_links = response.xpath('//a[contains(@href, "/ip/")]')
            seen_hrefs = set()
            
            for link in product_links:
                href = link.xpath('./@href').get()
                if href and href not in seen_hrefs:
                    seen_hrefs.add(href)
                    # Obtener el contenedor padre más cercano
                    container = link.xpath('./ancestor::div[contains(@class, "product") or contains(@class, "item") or contains(@class, "card")][1]')
                    if container:
                        product_nodes.extend(container)
                    else:
                        # Si no hay contenedor, usar el link mismo
                        product_nodes.append(link)

        self.logger.info(f"✅ Total de nodos de producto detectados: {len(product_nodes)}")

        if not product_nodes:
            yield {
                "_debug": True,
                "category_url": response.url,
                "title": title,
                "note": "No se encontraron productos. El DOM puede haber cambiado.",
                "html_sample": response.text[:500],
            }
            return

        # 3) Extraer datos de cada producto
        extracted_count = 0
        for idx, product_node in enumerate(product_nodes, 1):
            try:
                item = self._extract_product_data(product_node, response.url, idx)
                if item and item.get('name'):
                    extracted_count += 1
                    yield item
            except Exception as e:
                self.logger.error(f"Error extrayendo producto {idx}: {e}")
                continue
        
        if extracted_count > 0:
            self.logger.info(f"✅ {extracted_count} productos extraídos exitosamente")
    
    def _process_all_pages_with_pagination(self):
        """Procesar todas las páginas con paginación usando Selenium"""
        page_number = 1
        max_pages = 50  # Límite de seguridad para evitar loops infinitos
        
        while page_number <= max_pages:
            try:
                # Verificar que la ventana esté abierta antes de continuar
                try:
                    from selenium.common.exceptions import NoSuchWindowException
                    _ = self.driver.current_url
                except (NoSuchWindowException, Exception) as e:
                    self.logger.error(f"❌ Ventana cerrada en página {page_number}: {e}")
                    self.logger.info("🔄 Intentando reinicializar driver...")
                    self.driver = None
                    if not self._init_selenium_driver():
                        self.logger.error("❌ No se pudo reinicializar el driver")
                        break
                    # Recargar la URL actual si es posible
                    try:
                        current_url = getattr(self, '_last_url', None)
                        if current_url:
                            self.driver.get(current_url)
                            time.sleep(5)
                    except:
                        pass
                
                # Obtener el HTML de Selenium de la página actual
                try:
                    page_source = self.driver.page_source
                    current_url = self.driver.current_url
                    self._last_url = current_url  # Guardar URL para recuperación
                except Exception as e:
                    self.logger.error(f"❌ Error obteniendo page_source: {e}")
                    break
                
                # Crear response con el HTML de Selenium
                response = HtmlResponse(
                    url=current_url,
                    body=page_source.encode('utf-8'),
                    encoding='utf-8'
                )
                
                # Procesar productos de la página actual
                self.logger.info(f"📊 Procesando productos de la página {page_number}...")
                page_items = 0
                for item in self.parse_products(response):
                    page_items += 1
                    yield item
                
                self.logger.info(f"✅ Página {page_number}: {page_items} productos extraídos")
                
                # Buscar botón de siguiente página
                next_button = self._find_next_page_button()
                
                if next_button:
                    is_enabled = self._is_button_enabled(next_button)
                    self.logger.info(f"🔍 Botón encontrado. Habilitado: {is_enabled}")
                    
                    if is_enabled:
                        # Click en el botón de siguiente página
                        self.logger.info(f"➡️  Avanzando a la página {page_number + 1}...")
                        try:
                            # Hacer scroll al botón para asegurar que sea visible
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", next_button)
                            time.sleep(2)
                            
                        # Intentar hacer click - primero intentar con JavaScript si es necesario
                        try:
                            # Verificar ventana antes del click
                            try:
                                _ = self.driver.current_url
                            except:
                                raise Exception("Ventana cerrada antes del click")
                            
                            # Intentar click directo
                            next_button.click()
                        except Exception as click_error:
                            # Si falla, intentar con JavaScript
                            self.logger.debug(f"Click directo falló ({click_error}), intentando con JavaScript...")
                            try:
                                self.driver.execute_script("arguments[0].click();", next_button)
                            except Exception as js_error:
                                self.logger.error(f"❌ Click con JavaScript también falló: {js_error}")
                                raise
                        
                        time.sleep(4)  # Esperar a que cargue la nueva página
                        
                        # Verificar que la ventana sigue abierta
                        try:
                            new_url = self.driver.current_url
                            if new_url != current_url:
                                self.logger.info(f"✅ Página cambió: {new_url}")
                            else:
                                self.logger.warning("⚠️  La URL no cambió después del click, esperando más tiempo...")
                                time.sleep(3)
                                new_url = self.driver.current_url
                                if new_url == current_url:
                                    self.logger.warning("⚠️  La URL aún no cambió, puede haber un problema con la paginación")
                        except Exception as url_error:
                            self.logger.error(f"❌ Error verificando URL después del click: {url_error}")
                            raise
                            
                            # Hacer scroll para cargar productos
                            self.logger.info("📜 Haciendo scroll para cargar productos...")
                            for i in range(3):
                                self.driver.execute_script(f"window.scrollTo(0, {(i+1) * 500});")
                                time.sleep(1)
                            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(3)
                            self.driver.execute_script("window.scrollTo(0, 0);")
                            time.sleep(2)
                            
                            page_number += 1
                        except Exception as e:
                            self.logger.error(f"❌ Error al hacer click en botón de siguiente página: {e}")
                            # Intentar una vez más con método alternativo
                            try:
                                self.logger.info("🔄 Intentando método alternativo de click...")
                                from selenium.webdriver.common.action_chains import ActionChains
                                actions = ActionChains(self.driver)
                                actions.move_to_element(next_button).click().perform()
                                time.sleep(4)
                                page_number += 1
                            except Exception as e2:
                                self.logger.error(f"❌ Método alternativo también falló: {e2}")
                                break
                    else:
                        self.logger.info(f"✅ Botón deshabilitado. Paginación completada. Total de páginas procesadas: {page_number}")
                        break
                else:
                    self.logger.info(f"✅ No se encontró botón de siguiente página. Paginación completada. Total de páginas procesadas: {page_number}")
                    break
                    
            except Exception as e:
                self.logger.error(f"❌ Error procesando página {page_number}: {e}")
                # Si es un error de ventana cerrada, intentar recuperar
                if "no such window" in str(e).lower() or "target window already closed" in str(e).lower():
                    self.logger.warning("🔄 Ventana cerrada detectada, intentando recuperar...")
                    try:
                        self.driver = None
                        if self._init_selenium_driver():
                            # Intentar recargar la última URL conocida
                            last_url = getattr(self, '_last_url', None)
                            if last_url:
                                self.logger.info(f"🔄 Recargando última URL: {last_url}")
                                self.driver.get(last_url)
                                time.sleep(5)
                                # Continuar con la siguiente iteración
                                continue
                    except Exception as recover_error:
                        self.logger.error(f"❌ No se pudo recuperar: {recover_error}")
                break
    
    def _find_next_page_button(self):
        """Buscar el botón de siguiente página usando el XPath proporcionado"""
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            # XPath proporcionado por el usuario para el botón de paginación
            xpath = '//*[@id="maincontent"]/main/div/div/div/div/div[5]/nav/ul/li[6]'
            
            try:
                # Intentar encontrar el botón con WebDriverWait
                button = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                return button
            except:
                # Si no se encuentra con wait, intentar directamente
                try:
                    button = self.driver.find_element(By.XPATH, xpath)
                    return button
                except:
                    # Intentar variaciones del XPath
                    alternative_xpaths = [
                        '//*[@id="maincontent"]//nav//li[6]',  # Versión más genérica
                        '//nav//li[6]//a[contains(@aria-label, "Next") or contains(@aria-label, "Siguiente")]',  # Por aria-label
                        '//nav//li[contains(@class, "next") or contains(@class, "pagination")]//a',  # Por clases
                    ]
                    
                    for alt_xpath in alternative_xpaths:
                        try:
                            button = self.driver.find_element(By.XPATH, alt_xpath)
                            self.logger.debug(f"Botón encontrado con XPath alternativo: {alt_xpath}")
                            return button
                        except:
                            continue
                    
                    self.logger.debug("No se encontró botón de siguiente página")
                    return None
        except Exception as e:
            self.logger.debug(f"Error buscando botón de siguiente página: {e}")
            return None
    
    def _is_button_enabled(self, button):
        """Verificar si el botón está habilitado"""
        try:
            from selenium.webdriver.common.by import By
            
            # Verificar si tiene atributo disabled
            disabled = button.get_attribute('disabled')
            if disabled is not None and disabled != 'false':
                self.logger.debug("Botón tiene atributo disabled")
                return False
            
            # Verificar si tiene clase de disabled
            class_name = button.get_attribute('class') or ''
            if 'disabled' in class_name.lower():
                self.logger.debug(f"Botón tiene clase disabled: {class_name}")
                return False
            
            # Verificar si el elemento está visible
            if not button.is_displayed():
                self.logger.debug("Botón no está visible")
                return False
            
            # Verificar si hay un link <a> dentro y si tiene href
            try:
                link = button.find_element(By.TAG_NAME, 'a')
                href = link.get_attribute('href')
                aria_disabled_link = link.get_attribute('aria-disabled')
                
                # Si el link tiene aria-disabled="true", está deshabilitado
                if aria_disabled_link and aria_disabled_link.lower() == 'true':
                    self.logger.debug("Link dentro del botón tiene aria-disabled=true")
                    return False
                
                # Si no tiene href o href es vacío, probablemente está deshabilitado
                if not href or href.strip() == '' or href.strip() == '#' or 'javascript:void' in href.lower():
                    self.logger.debug(f"Link no tiene href válido: {href}")
                    return False
                
                # Verificar clase del link
                link_class = link.get_attribute('class') or ''
                if 'disabled' in link_class.lower():
                    self.logger.debug(f"Link tiene clase disabled: {link_class}")
                    return False
                
                self.logger.debug(f"✅ Botón habilitado - href: {href}")
                return True
            except Exception as e:
                # Si no hay link, verificar si el botón mismo tiene atributo aria-disabled
                aria_disabled = button.get_attribute('aria-disabled')
                if aria_disabled and aria_disabled.lower() == 'true':
                    self.logger.debug("Botón tiene aria-disabled=true")
                    return False
                
                # Si no hay link ni aria-disabled, verificar si es clickeable
                try:
                    # Intentar verificar si tiene onclick o similar
                    onclick = button.get_attribute('onclick')
                    if onclick:
                        self.logger.debug("Botón tiene onclick, asumiendo habilitado")
                        return True
                except:
                    pass
                
                # Si no hay link pero el botón está visible y no tiene disabled, asumir habilitado
                self.logger.debug("No se encontró link, pero botón parece habilitado")
                return True
            
        except Exception as e:
            self.logger.error(f"❌ Error verificando si botón está habilitado: {e}")
            return False

    def _extract_product_data(self, product_node, category_url: str, index: int) -> Optional[ProductItem]:
        """Extraer datos de un producto individual"""
        try:
            item = ProductItem()
            item['category_url'] = category_url
            
            # URL del producto
            # Si el nodo mismo es un link <a>, obtener href directamente
            if product_node.root.tag == 'a':
                href = product_node.xpath('./@href').get()
            else:
                # Buscar link dentro del nodo
                href = product_node.xpath('.//a[contains(@href, "/ip/")]/@href').get()
                if not href:
                    # Intentar obtener href directamente del nodo si es un link
                    href = product_node.xpath('./@href').get()
            
            if href:
                item['product_url'] = urljoin(category_url, href)
            else:
                item['product_url'] = None

            # Nombre del producto - múltiples estrategias
            name = None
            
            # Si el nodo mismo es un link <a>, obtener texto directamente
            if product_node.root.tag == 'a':
                name_text = product_node.xpath('normalize-space(.)').get()
                if name_text and len(name_text) > 3:
                    name = _clean_text(name_text)
            else:
                # Buscar en elementos hijos
                name_selectors = [
                    './/h3//text()',
                    './/h2//text()',
                    './/h4//text()',
                    './/a[contains(@href, "/ip/")]//text()',
                    './/span[contains(@class, "name")]//text()',
                    './/div[contains(@class, "name")]//text()',
                    './/p[contains(@class, "name")]//text()',
                ]
                
                for selector in name_selectors:
                    name_text = product_node.xpath(f'normalize-space({selector})').get()
                    if name_text and len(name_text) > 3:  # Filtrar nombres muy cortos
                        name = _clean_text(name_text)
                        break
            
            if not name:
                # Último recurso: obtener todo el texto del nodo y limpiar
                all_text = " ".join(product_node.xpath('.//text()').getall())
                # Intentar extraer el nombre (generalmente es el primer texto significativo)
                name_parts = [t.strip() for t in all_text.split('\n') if t.strip() and len(t.strip()) > 3]
                if name_parts:
                    name = _clean_text(name_parts[0])
            
            item['name'] = name or "Sin nombre"

            # Texto completo para análisis
            # Si el nodo es un link <a>, buscar texto en el contenedor padre también
            try:
                node_tag = product_node.root.tag if hasattr(product_node, 'root') else None
                if node_tag == 'a':
                    # Para links, obtener texto del contenedor padre completo
                    # Buscar el contenedor padre más cercano que tenga clase de producto
                    container = product_node.xpath('./ancestor::div[contains(@class, "product") or contains(@class, "item") or contains(@class, "card") or @data-product-id][1]')
                    if container:
                        # Usar el contenedor para obtener todo el texto
                        raw_text = " ".join(t.strip() for t in container.xpath(".//text()").getall() if t.strip())
                    else:
                        # Si no hay contenedor específico, buscar en padre y hermanos cercanos
                        link_text = " ".join(t.strip() for t in product_node.xpath(".//text()").getall() if t.strip())
                        parent_text = " ".join(t.strip() for t in product_node.xpath("../text() | ../*/text() | ../../text() | ../../*/text()").getall() if t.strip())
                        raw_text = f"{link_text} {parent_text}"
                    raw_text = _clean_text(raw_text)
                else:
                    raw_text = " ".join(t.strip() for t in product_node.xpath(".//text()").getall() if t.strip())
                    raw_text = _clean_text(raw_text)
            except Exception as e:
                # Fallback: método básico
                raw_text = " ".join(t.strip() for t in product_node.xpath(".//text()").getall() if t.strip())
                raw_text = _clean_text(raw_text)
            
            item['raw_text'] = raw_text

            # Precios - buscar todos los valores monetarios en raw_text y también en elementos cercanos
            prices = re.findall(r"\$\s?\d{1,3}(?:\.\d{3})*", raw_text)
            if not prices:
                # Si no encontramos precios en raw_text, buscar en el contenedor padre si es un link
                try:
                    node_tag = product_node.root.tag if hasattr(product_node, 'root') else None
                    if node_tag == 'a':
                        container = product_node.xpath('./ancestor::div[1]')
                        if container:
                            container_text = " ".join(t.strip() for t in container.xpath(".//text()").getall() if t.strip())
                            prices = re.findall(r"\$\s?\d{1,3}(?:\.\d{3})*", container_text)
                except:
                    pass
            prices = [p.replace(" ", "") for p in prices if p.strip()]
            
            # Eliminar duplicados manteniendo el orden
            seen_prices = set()
            unique_prices = []
            for price in prices:
                if price not in seen_prices:
                    seen_prices.add(price)
                    unique_prices.append(price)

            # Heurística para determinar precio normal vs descuento
            if len(unique_prices) >= 2:
                # Generalmente el precio más bajo es el descuento y el más alto el normal
                # Pero puede variar según el sitio, así que tomamos ambos
                price_values = []
                for price_str in unique_prices:
                    # Convertir "$5.490" a 5490 para comparar
                    num_str = price_str.replace('$', '').replace('.', '')
                    try:
                        price_values.append((int(num_str), price_str))
                    except:
                        pass
                
                price_values.sort(key=lambda x: x[0])
                
                if len(price_values) >= 2:
                    item['discount_price'] = price_values[0][1]  # Menor = descuento
                    item['price'] = price_values[-1][1]  # Mayor = precio normal
                elif len(price_values) == 1:
                    item['discount_price'] = price_values[0][1]
                    item['price'] = price_values[0][1]
                else:
                    item['price'] = unique_prices[0] if unique_prices else None
                    item['discount_price'] = None
            elif len(unique_prices) == 1:
                item['price'] = unique_prices[0]
                item['discount_price'] = unique_prices[0]  # Mismo precio
            else:
                item['price'] = None
                item['discount_price'] = None

            # Validar que al menos tenemos un nombre
            if not item['name'] or item['name'] == "Sin nombre":
                return None

            return item

        except Exception as e:
            self.logger.error(f"Error extrayendo datos del producto: {e}")
            return None

    def _init_selenium_driver(self):
        """Inicializar driver de Selenium de forma lazy"""
        if self.driver:
            return True
        
        if not self.use_selenium or not UNDETECTED_CHROMEDRIVER_AVAILABLE:
            return False
        
        try:
            import ssl
            ssl._create_default_https_context = ssl._create_unverified_context
            
            from selenium.webdriver.common.by import By
            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            # No usar headless para evitar detección
            # Intentar inicialización simple primero
            try:
                self.driver = uc.Chrome(options=options, version_main=None)
            except:
                # Fallback: sin opciones adicionales
                self.driver = uc.Chrome(version_main=None)
            
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(10)
            self.logger.info("✅ Selenium con undetected-chromedriver inicializado")
            return True
        except Exception as e:
            self.logger.error(f"No se pudo inicializar Selenium: {e}")
            self.driver = None
            return False

    def _load_page_with_selenium(self, url: str) -> bool:
        """Cargar página usando Selenium directamente (resuelve captcha automáticamente)"""
        if not self._init_selenium_driver():
            return False
        
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.common.exceptions import NoSuchWindowException
            
            # Verificar que la ventana esté abierta
            try:
                _ = self.driver.current_url
            except (NoSuchWindowException, Exception) as e:
                self.logger.warning(f"Ventana cerrada, reinicializando driver: {e}")
                self.driver = None
                if not self._init_selenium_driver():
                    return False
            
            self.logger.info(f"🌐 Cargando página con Selenium (visible): {url}")
            try:
                self.driver.get(url)
            except Exception as e:
                self.logger.error(f"Error cargando URL con Selenium: {e}")
                return False
            
            self.logger.info("⏳ Esperando a que cargue la página (5 segundos)...")
            time.sleep(5)
            
            # Verificar que la ventana sigue abierta
            try:
                current_url = self.driver.current_url
            except (NoSuchWindowException, Exception) as e:
                self.logger.error(f"Ventana cerrada durante la carga: {e}")
                return False
            
            current_url = self.driver.current_url
            self.logger.info(f"📍 URL actual: {current_url}")
            
            # Si la URL tiene /blocked, intentar resolver captcha
            if "/blocked" in current_url:
                self.logger.info("🔍 Página bloqueada detectada, buscando captcha...")
                
                # Verificar si hay iframe de captcha
                try:
                    # Buscar iframe por múltiples métodos
                    iframe = None
                    try:
                        # Método 1: Buscar contenedor y luego iframe
                        container = self.driver.find_element(By.ID, 'px-captcha')
                        iframe = container.find_element(By.TAG_NAME, 'iframe')
                        self.logger.info("✅ Iframe encontrado por contenedor")
                    except:
                        try:
                            # Método 2: Buscar todos los iframes
                            iframes = self.driver.find_elements(By.TAG_NAME, 'iframe')
                            for ifr in iframes:
                                try:
                                    parent = ifr.find_element(By.XPATH, './..')
                                    if parent.get_attribute('id') == 'px-captcha':
                                        iframe = ifr
                                        self.logger.info("✅ Iframe encontrado por parent")
                                        break
                                except:
                                    continue
                        except:
                            pass
                    
                    if iframe:
                        self.logger.info("✅ Iframe de captcha encontrado, intentando resolver...")
                        # Cambiar al iframe usando índice
                        self.driver.switch_to.default_content()
                        iframes_all = self.driver.find_elements(By.TAG_NAME, 'iframe')
                        iframe_index = None
                        for idx, ifr in enumerate(iframes_all):
                            try:
                                parent = ifr.find_element(By.XPATH, './..')
                                if parent.get_attribute('id') == 'px-captcha':
                                    iframe_index = idx
                                    break
                            except:
                                continue
                        
                        if iframe_index is not None:
                            self.driver.switch_to.frame(iframe_index)
                            self.logger.info(f"✅ Cambiado al iframe (índice {iframe_index})")
                            time.sleep(2)
                            
                            # Buscar botón dentro del iframe
                            try:
                                button = WebDriverWait(self.driver, 10).until(
                                    EC.presence_of_element_located((By.TAG_NAME, "button"))
                                )
                                if button:
                                    self.logger.info("🖱️  Botón encontrado, haciendo click y mantener por 12 segundos...")
                                    # Hacer click y mantener
                                    actions = ActionChains(self.driver)
                                    actions.click_and_hold(button).perform()
                                    for i in range(12):
                                        time.sleep(1)
                                        if i % 3 == 0:
                                            self.logger.info(f"   ⏳ Manteniendo click... {12-i} segundos restantes")
                                    actions.release(button).perform()
                                    self.driver.switch_to.default_content()
                                    self.logger.info("✅ Click liberado, esperando validación...")
                                    time.sleep(5)
                                    
                                    # Recargar la URL original después de resolver captcha
                                    self.driver.get(url)
                                    time.sleep(5)
                                    
                                    # Verificar si se resolvió
                                    current_url = self.driver.current_url
                                    self.logger.info(f"📍 URL después de captcha: {current_url}")
                                    if "/blocked" not in current_url:
                                        self.logger.info("✅✅ Captcha resuelto exitosamente!")
                                    else:
                                        self.logger.warning("⚠️  Captcha no resuelto completamente")
                            except Exception as e:
                                self.logger.debug(f"Error interactuando con botón: {e}")
                                self.driver.switch_to.default_content()
                    else:
                        self.logger.info("ℹ️  No se encontró iframe de captcha")
                except Exception as e:
                    self.logger.debug(f"Error buscando captcha: {e}")
            else:
                self.logger.info("✅ Página accesible sin bloqueo")
            
            # Esperar a que los productos se carguen (scroll para activar lazy loading)
            self.logger.info("📜 Haciendo scroll para cargar productos...")
            for i in range(3):
                self.driver.execute_script(f"window.scrollTo(0, {(i+1) * 500});")
                time.sleep(1)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
            
            # Verificar que tenemos contenido válido
            page_source = self.driver.page_source
            if len(page_source) < 1000:
                self.logger.warning("⚠️  HTML obtenido es muy corto, puede haber un problema")
                return False
            
            current_url_final = self.driver.current_url
            if "/blocked" in current_url_final:
                self.logger.warning("⚠️  Página sigue bloqueada después de intentar resolver captcha")
                return False
            
            self.logger.info(f"✅ Página cargada exitosamente con Selenium: {current_url_final}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error cargando página con Selenium: {e}")
            return False

    def _solve_captcha_with_selenium(self, url: str) -> bool:
        """Resolver captcha usando Selenium (método de respaldo)"""
        # Este método se puede usar si es necesario, pero _load_page_with_selenium ya lo maneja
        return self._load_page_with_selenium(url)

    def closed(self, reason):
        """Cerrar driver al finalizar"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

