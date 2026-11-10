import requests
from bs4 import BeautifulSoup

def ecobici_links():
    url_base = "https://ecobici.cdmx.gob.mx/datos-abiertos/"
    
    # 1. Hacemos la petición a la página principal de datos abiertos
    respuesta = requests.get(url_base)
    respuesta.raise_for_status() # Verifica que no haya error 404/500
    
    # 2. Analizamos el HTML de la página
    soup = BeautifulSoup(respuesta.text, 'html.parser')
    
    links_descarga = []
    
    # 3. Buscamos todos los enlaces en la página
    for etiqueta_a in soup.find_all('a'):
        href = etiqueta_a.get('href')
        
        # 4. Filtramos solo los que son archivos de datos (suelen ser .csv o .zip)
        if href and (href.endswith('.csv') or href.endswith('.zip')):
            links_descarga.append('https://ecobici.cdmx.gob.mx'+href)
            
    return links_descarga