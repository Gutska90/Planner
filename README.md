# Scraper Lider.cl - Categorías

Scraper optimizado para extraer productos de categorías de Lider.cl con soporte para:
- Captcha solver (2Captcha)
- Proxies rotativos gratuitos
- Múltiples estrategias de XPath para máxima compatibilidad
- Exportación a JSON y Excel

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

### Básico (sin captcha solver)

```bash
cd /Users/user/ServicePlaner
scrapy crawl categoria -a url="https://super.lider.cl/browse/carnes-y-pescados/todas-las-carnes/21856785_25641771"
```

### Con 2Captcha (Captcha Solver)

1. Obtén tu API key de [2Captcha](https://2captcha.com) (pagos muy bajos, ~$3 por 1000 captchas)
2. Ejecuta con tu API key:

```bash
scrapy crawl categoria -a url="https://super.lider.cl/browse/carnes-y-pescados/todas-las-carnes/21856785_25641771" -a twocaptcha_key="TU_API_KEY_AQUI"
```

## Archivos Generados

- `lider_products.json` - Productos en formato JSON
- `lider_products.xlsx` - Productos en formato Excel con formato

## Características

### XPath Optimizado
El spider usa múltiples estrategias de XPath para encontrar productos:
1. XPath original proporcionado
2. Búsqueda por clases CSS comunes
3. Búsqueda por estructura de links
4. Métodos fallback alternativos

### Proxies Rotativos
El spider carga automáticamente proxies gratuitos de:
- ProxyScrape
- Geonode

Los proxies rotan automáticamente entre requests.

### Captcha Solver
Integración con 2Captcha (opcional):
- Muy económico (~$3 por 1000 captchas)
- Resolución automática cuando se detecta captcha
- No requiere intervención manual

### Extracción de Datos
Extrae:
- Nombre del producto
- Precio normal
- Precio con descuento
- URL del producto
- URL de la categoría

## Notas

- El spider está optimizado para evitar bloqueos con delays y rotación de proxies
- Si encuentras bloqueos frecuentes, considera usar un servicio de proxies premium
- 2Captcha es opcional pero recomendado para sitios con protección anti-bot

