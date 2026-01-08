"""
Helper function para resolver captcha de PerimeterX
"""
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def solve_px_captcha(driver, logger, url, hold_time=12):
    """
    Resolver captcha de PerimeterX
    
    Args:
        driver: Selenium WebDriver
        logger: Logger instance
        url: URL original a cargar después de resolver
        hold_time: Tiempo en segundos para mantener el botón presionado
    
    Returns:
        bool: True si el captcha fue resuelto, False en caso contrario
    """
    try:
        logger.info("🔍 Iniciando resolución de captcha PerimeterX...")
        
        # Esperar a que el captcha se cargue
        time.sleep(3)
        
        # Método 1: Buscar iframe dentro del contenedor px-captcha
        iframe = None
        iframe_index = None
        
        try:
            # Buscar contenedor px-captcha
            container = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, 'px-captcha'))
            )
            logger.info("✅ Contenedor px-captcha encontrado")
            
            # Buscar iframe dentro del contenedor
            try:
                iframe = container.find_element(By.TAG_NAME, 'iframe')
                logger.info("✅ Iframe encontrado dentro del contenedor")
            except:
                try:
                    iframe = container.find_element(By.XPATH, './/iframe')
                    logger.info("✅ Iframe encontrado por XPath relativo")
                except:
                    logger.debug("No se encontró iframe dentro del contenedor")
        except Exception as e:
            logger.debug(f"Contenedor px-captcha no encontrado: {e}")
        
        # Método 2: Buscar todos los iframes y verificar
        if not iframe:
            try:
                iframes_all = driver.find_elements(By.TAG_NAME, 'iframe')
                logger.info(f"📋 Encontrados {len(iframes_all)} iframes en la página")
                
                for idx, ifr in enumerate(iframes_all):
                    try:
                        # Verificar parent
                        parent = ifr.find_element(By.XPATH, './..')
                        parent_id = parent.get_attribute('id') or ''
                        if 'px-captcha' in parent_id.lower():
                            iframe = ifr
                            iframe_index = idx
                            logger.info(f"✅ Iframe encontrado por parent (índice {idx})")
                            break
                    except:
                        pass
                    
                    # Verificar src o id del iframe
                    iframe_src = ifr.get_attribute('src') or ''
                    iframe_id = ifr.get_attribute('id') or ''
                    if ('px' in iframe_src.lower() and 'captcha' in iframe_src.lower()) or 'px' in iframe_id.lower():
                        iframe = ifr
                        iframe_index = idx
                        logger.info(f"✅ Iframe encontrado por src/id (índice {idx})")
                        break
            except Exception as e:
                logger.error(f"Error buscando iframes: {e}")
        
        # Método 3: Buscar iframe por XPath directo
        if not iframe:
            try:
                iframe = driver.find_element(By.XPATH, '//iframe[contains(@src, "px") or contains(@id, "px")]')
                logger.info("✅ Iframe encontrado por XPath directo")
            except:
                pass
        
        if not iframe:
            logger.warning("⚠️  No se encontró iframe, intentando buscar botón directamente en la página...")
            return _try_solve_without_iframe(driver, logger, url, hold_time)
        
        # Cambiar al iframe
        driver.switch_to.default_content()
        time.sleep(1)
        
        # Obtener índice del iframe si no lo tenemos
        if iframe_index is None:
            iframes_all = driver.find_elements(By.TAG_NAME, 'iframe')
            for idx, ifr in enumerate(iframes_all):
                try:
                    ifr_src = ifr.get_attribute('src') or ''
                    iframe_src = iframe.get_attribute('src') or ''
                    if ifr_src == iframe_src:
                        iframe_index = idx
                        break
                except:
                    continue
        
        # Cambiar al iframe
        try:
            if iframe_index is not None:
                driver.switch_to.frame(iframe_index)
                logger.info(f"✅ Cambiado al iframe usando índice {iframe_index}")
            else:
                driver.switch_to.frame(iframe)
                logger.info("✅ Cambiado al iframe directamente")
            
            time.sleep(2)
            
            # Buscar botón - múltiples métodos
            button = _find_captcha_button(driver, logger)
            
            if button:
                logger.info(f"🖱️  Botón encontrado, haciendo click y mantener por {hold_time} segundos...")
                
                # Hacer scroll al botón
                driver.execute_script("arguments[0].scrollIntoView(true);", button)
                time.sleep(1)
                
                # Click and hold
                actions = ActionChains(driver)
                actions.move_to_element(button).click_and_hold(button).perform()
                
                logger.info("   ⏳ Manteniendo click presionado...")
                for i in range(hold_time):
                    time.sleep(1)
                    try:
                        _ = button.is_displayed()
                    except:
                        logger.warning(f"   ⚠️  Botón desapareció en segundo {i+1}")
                        break
                    if i % 3 == 0:
                        logger.info(f"   ⏳ Manteniendo click... {hold_time-i} segundos restantes")
                
                actions.release(button).perform()
                driver.switch_to.default_content()
                logger.info("✅ Click liberado, esperando validación...")
                time.sleep(8)
                
                # Recargar URL original
                logger.info("🔄 Recargando URL original...")
                driver.get(url)
                time.sleep(5)
                
                # Verificar resolución
                current_url_after = driver.current_url
                logger.info(f"📍 URL después de captcha: {current_url_after}")
                if "/blocked" not in current_url_after:
                    logger.info("✅✅✅ Captcha resuelto exitosamente!")
                    return True
                else:
                    logger.warning("⚠️  Captcha no resuelto completamente")
                    return False
            else:
                logger.error("❌ No se pudo encontrar el botón del captcha")
                driver.switch_to.default_content()
                return False
                
        except Exception as e:
            logger.error(f"❌ Error interactuando con iframe: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            try:
                driver.switch_to.default_content()
            except:
                pass
            return False
            
    except Exception as e:
        logger.error(f"❌ Error general resolviendo captcha: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False


def _find_captcha_button(driver, logger):
    """Buscar botón del captcha con múltiples métodos"""
    button = None
    
    # Método 1: Buscar por tag button
    try:
        button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.TAG_NAME, "button"))
        )
        logger.info("✅ Botón encontrado por tag button")
        return button
    except:
        pass
    
    # Método 2: Buscar por texto "PULSAR" o "MANTENER"
    try:
        button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'PULSAR') or contains(text(), 'MANTENER') or contains(text(), 'Pulsar') or contains(text(), 'Mantener')]"))
        )
        logger.info("✅ Botón encontrado por texto")
        return button
    except:
        pass
    
    # Método 3: Buscar cualquier elemento clickeable con texto relacionado
    try:
        button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'PULSAR') or contains(text(), 'MANTENER') or contains(text(), 'Pulsar') or contains(text(), 'Mantener')]"))
        )
        logger.info("✅ Botón encontrado por texto en cualquier elemento")
        return button
    except:
        pass
    
    # Método 4: Buscar por clase o atributos comunes
    try:
        button = driver.find_element(By.XPATH, "//button | //div[@role='button'] | //a[@role='button']")
        logger.info("✅ Botón encontrado por selector genérico")
        return button
    except:
        pass
    
    # Método 5: Buscar todos los botones y tomar el primero visible
    try:
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                button = btn
                logger.info("✅ Botón encontrado como primer botón visible")
                return button
    except:
        pass
    
    return None


def _try_solve_without_iframe(driver, logger, url, hold_time):
    """Intentar resolver captcha sin iframe (botón directamente en la página)"""
    try:
        logger.info("🔍 Buscando botón directamente en la página principal...")
        button = _find_captcha_button(driver, logger)
        
        if button:
            logger.info(f"🖱️  Botón encontrado en página principal, haciendo click y mantener por {hold_time} segundos...")
            
            driver.execute_script("arguments[0].scrollIntoView(true);", button)
            time.sleep(1)
            
            actions = ActionChains(driver)
            actions.move_to_element(button).click_and_hold(button).perform()
            
            for i in range(hold_time):
                time.sleep(1)
                if i % 3 == 0:
                    logger.info(f"   ⏳ Manteniendo click... {hold_time-i} segundos restantes")
            
            actions.release(button).perform()
            time.sleep(8)
            
            driver.get(url)
            time.sleep(5)
            
            current_url_after = driver.current_url
            if "/blocked" not in current_url_after:
                logger.info("✅✅✅ Captcha resuelto exitosamente (sin iframe)!")
                return True
            else:
                logger.warning("⚠️  Captcha no resuelto completamente")
                return False
        else:
            logger.error("❌ No se pudo encontrar el botón del captcha en ningún lugar")
            return False
    except Exception as e:
        logger.error(f"❌ Error resolviendo captcha sin iframe: {e}")
        return False

