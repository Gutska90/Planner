#!/usr/bin/env python3
"""
Script para ejecutar todos los spiders en paralelo usando threading
Cada spider se ejecuta en su propio hilo con su propia sesión de Selenium
"""
import threading
import subprocess
import time
import sys
from datetime import datetime
from pathlib import Path

# Lista de spiders a ejecutar
SPIDERS = [
    {
        'name': 'carnes-y-pescados',
        'display_name': 'Carnes y Pescados',
        'emoji': '🥩'
    },
    {
        'name': 'destilados',
        'display_name': 'Destilados',
        'emoji': '🍷'
    },
    {
        'name': 'snacks-y-picoteo',
        'display_name': 'Snacks y Picoteo',
        'emoji': '🍿'
    }
]


def run_spider(spider_info):
    """
    Ejecuta un spider individual en un hilo separado
    
    Args:
        spider_info: Diccionario con información del spider (name, display_name, emoji)
    """
    spider_name = spider_info['name']
    display_name = spider_info['display_name']
    emoji = spider_info['emoji']
    
    thread_id = threading.current_thread().name
    start_time = datetime.now()
    
    print(f"\n{'='*70}")
    print(f"{emoji} [{thread_id}] Iniciando spider: {display_name}")
    print(f"{'='*70}")
    
    try:
        # Ejecutar el spider con Scrapy
        # Usar headless=true para no abrir navegador
        # Usar use_selenium=true para usar Selenium
        cmd = [
            sys.executable, '-m', 'scrapy', 'crawl', spider_name,
            '-a', 'use_selenium=true',
            '-a', 'headless=true'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        if result.returncode == 0:
            print(f"\n✅ [{thread_id}] {display_name} completado exitosamente en {duration:.1f}s")
            # Mostrar últimas líneas del output para ver resumen
            output_lines = result.stdout.split('\n')
            summary_lines = [line for line in output_lines if any(keyword in line.lower() for keyword in ['productos', 'guardados', 'completada', 'páginas'])]
            if summary_lines:
                print(f"   Resumen: {summary_lines[-1] if summary_lines else 'Sin resumen'}")
        else:
            print(f"\n❌ [{thread_id}] {display_name} falló después de {duration:.1f}s")
            print(f"   Error: {result.stderr[:200] if result.stderr else 'Sin detalles'}")
            
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        print(f"\n❌ [{thread_id}] Error ejecutando {display_name} después de {duration:.1f}s: {e}")


def main():
    """Función principal que ejecuta todos los spiders en paralelo"""
    print("\n" + "="*70)
    print("🚀 EJECUTANDO TODOS LOS SPIDERS EN PARALELO")
    print("="*70)
    print(f"📅 Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🧵 Spiders a ejecutar: {len(SPIDERS)}")
    print(f"⚙️  Modo: Headless (navegador no visible)")
    print(f"🔧 Selenium: Habilitado")
    print("="*70)
    
    # Crear y iniciar hilos para cada spider
    threads = []
    for spider_info in SPIDERS:
        thread = threading.Thread(
            target=run_spider,
            args=(spider_info,),
            name=f"Thread-{spider_info['name']}"
        )
        threads.append(thread)
        thread.start()
        # Pequeño delay entre inicios para evitar conflictos de inicialización
        time.sleep(2)
    
    # Esperar a que todos los hilos terminen
    print(f"\n⏳ Esperando a que todos los spiders terminen...")
    for thread in threads:
        thread.join()
    
    # Resumen final
    print("\n" + "="*70)
    print("📊 RESUMEN FINAL")
    print("="*70)
    
    # Verificar archivos generados
    json_files = list(Path('.').glob('*_products.json'))
    xlsx_files = list(Path('.').glob('*_products.xlsx'))
    
    if json_files:
        print(f"\n✅ Archivos JSON generados ({len(json_files)}):")
        for json_file in sorted(json_files):
            size = json_file.stat().st_size / 1024  # KB
            print(f"   📄 {json_file.name} ({size:.1f} KB)")
    
    if xlsx_files:
        print(f"\n✅ Archivos Excel generados ({len(xlsx_files)}):")
        for xlsx_file in sorted(xlsx_files):
            size = xlsx_file.stat().st_size / 1024  # KB
            print(f"   📊 {xlsx_file.name} ({size:.1f} KB)")
    
    print(f"\n✅ Todos los spiders han terminado")
    print(f"📅 Fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")


if __name__ == '__main__':
    main()

