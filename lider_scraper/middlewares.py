"""
Middlewares para manejo de proxies y captcha
"""
import random
import logging

logger = logging.getLogger(__name__)


class ProxyMiddleware:
    """Middleware para rotación de proxies"""
    
    def __init__(self):
        self.proxies = []
        self.current_index = 0

    def process_request(self, request, spider):
        """Procesar request y agregar proxy si está disponible"""
        # Si el spider ya agregó un proxy en meta, usarlo
        if 'proxy' in request.meta:
            return None
        
        # Si el spider tiene proxies, usar uno
        if hasattr(spider, 'proxies') and spider.proxies:
            proxy = spider._get_next_proxy()
            if proxy:
                request.meta['proxy'] = f"http://{proxy}"
                logger.debug(f"Proxy asignado: {proxy}")
        
        return None


class CaptchaMiddleware:
    """Middleware para manejo de captcha (preparado para futuras mejoras)"""
    
    def process_response(self, request, response, spider):
        """Procesar response y detectar captcha"""
        # Detección básica de captcha
        if response.status == 403 or "/blocked" in response.url:
            logger.warning(f"Posible captcha detectado en: {response.url}")
            # Aquí se podría implementar la lógica de resolución automática
        
        return response

