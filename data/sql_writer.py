import os
import datetime
from dotenv import load_dotenv
from request import request as rq

from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, inspect

from schemas.data_model import Data
from schemas.file_register_model import FileRegister
from schemas.base import Base



def sql_write_df(df, file_name):
    
    # Renombrar columnas para que coincidan con data_model.py
    df = df.rename(columns={
        'Genero_Usuario': 'gender',
        'Edad_Usuario': 'age',
        'Bici': 'bicycle_id',
        'Ciclo_Estacion_Retiro': 'begin_station',
        'Ciclo_EstacionArribo': 'end_station',
        'Retiro': 'begin_time',
        'Arribo': 'end_time'
    })

    # Cargar variables de entorno (ej. usando un archivo .env)
    load_dotenv()
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST", "localhost")
    db_name = os.getenv("DB_NAME", 'ecobici')

    # Crear el motor (ejemplo para PostgreSQL)
    URI = f'postgresql://{db_user}:{db_pass}@{db_host}/{db_name}'
    engine = create_engine(URI)

    # Generar el esquema en la base de datos
    Base.metadata.create_all(engine)
    
    # 1. Crear la fábrica de sesiones asociada a tu motor (engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
    # 2. Hacer la consulta: Buscar el primer registro que coincida con el nombre
        archivo_existente = session.query(FileRegister).filter_by(file_name=file_name).first()

        if archivo_existente:
            print(f'El archivo {file_name} ya esta registrado')
        
        else:
            try:
                df.to_sql(
                    name=Data.__tablename__, 
                    con=engine,
                    if_exists='append', 
                    index=False     # Evita guardar el índice numérico de pandas como una columna en la base de datos
                )
                print(f'Tabla {file_name} escrita con exito')
                
            except Exception:
                import traceback
                traceback.print_exc()
                raise
                
            nuevo_registro = FileRegister(
                                file_name=file_name,
                                process_date=datetime.datetime.now()
                                )
            session.add(nuevo_registro)
            
            session.commit()
        
    
    except Exception as e:
        # Si algo falla rollback
        session.rollback()
        print(f"Error durante el procesamiento: {e}")
        
    finally:
        session.close()
        
def test_DB():
    try:
        load_dotenv()
        # 1. Configurar la conexión
        usuario = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "password")
        host = os.getenv("DB_HOST", "localhost")
        db_name = os.getenv("DB_NAME", "ecobici")
        
        uri = f'postgresql://{usuario}:{password}@{host}/{db_name}'
        engine = create_engine(uri)
        
        # 2. Probar la conexión conectándose al motor
        with engine.connect() as conn:
            print(f"✅ Conexión exitosa a la base de datos '{db_name}'.")

        # 3. Verificar si las tablas ya existen
        inspector = inspect(engine)
        tablas_existentes = inspector.get_table_names()
        
        # Obtenemos los nombres de las tablas
        tabla_viajes = Data.__tablename__
        tabla_registros = FileRegister.__tablename__

        if tabla_viajes in tablas_existentes and tabla_registros in tablas_existentes:
            print("✅ El esquema ya existe. Las tablas están listas.")
        else:
            # 4. Crear el esquema si faltan tablas
            print("⚠️ Tablas no encontradas. Creando el esquema...")
            Base.metadata.create_all(engine)
            print("✅ Esquema creado exitosamente.")
            
        return True

    except Exception as e:
        print(f"❌ Error al conectar o inicializar la base de datos:\n{e}")
        return False
    
 
 
 
 
 
 
 
 
 
 
 
 
 
 
    
'''
url = 'https://ecobici.cdmx.gob.mx/wp-content/uploads/2022/06/2010-02-feb.csv'

df = rq(url)

sql_write_df(df, '2010-02-feb.csv')'''