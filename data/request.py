# Source - https://stackoverflow.com/q/35371043
# Posted by viviwill, modified by community. See post 'Timeline' for change history
# Retrieved 2026-11-09, License - CC BY-SA 4.0


import requests
import io
import pandas as pd

url = 'https://ecobici.cdmx.gob.mx/wp-content/uploads/2022/06/2010-02-feb.csv'

def request(url):
    with requests.Session() as s:
        download = s.get(url)
        
        if download.status_code == 200:

            decoded_content = download.content.decode('utf-8')

            df = pd.read_csv(io.StringIO(decoded_content), sep=',')
            # print(df.head())
            
            df.columns = df.columns.str.strip().str.lstrip("\ufeff")
            
            df.columns = (
                df.columns
                .str.lstrip("\ufeff")
                .str.strip()
                .str.replace(r"\s+", "_", regex=True)
            )
            
            # Crear las nuevas columnas unificadas combinando fecha y hora con un espacio
            df['Retiro'] = pd.to_datetime(df['Fecha_Retiro'].astype(str) + ' ' + df['Hora_Retiro'].astype(str), format='mixed')
            df['Arribo'] = pd.to_datetime(df['Fecha_Arribo'].astype(str) + ' ' + df['Hora_Arribo'].astype(str), format='mixed')

            # Eliminar las columnas originales para limpiar el DataFrame
            df = df.drop(columns=['Fecha_Retiro', 'Hora_Retiro', 'Fecha_Arribo', 'Hora_Arribo'])
        
            
            return df
        
        else:
            raise ValueError(f"Error 404")