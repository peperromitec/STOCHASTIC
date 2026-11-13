from request import request as rq
from sql_writer import test_DB, sql_write_df
from links_ecobici import ecobici_links
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from schemas.file_register_model import FileRegister
from dotenv import load_dotenv
import os


def main():
    db_status = test_DB()
    
    if db_status:
        links = ecobici_links()
        df=None
        
        
        
        # Cargar variables de entorno (ej. usando un archivo .env)
        load_dotenv()
        db_user = os.getenv("DB_USER")
        db_pass = os.getenv("DB_PASSWORD")
        db_host = os.getenv("DB_HOST", "localhost")
        db_name = os.getenv("DB_NAME", 'ecobici')
    
        # Crear el motor (ejemplo para PostgreSQL)
        URI = f'postgresql://{db_user}:{db_pass}@{db_host}/{db_name}'
        engine = create_engine(URI)
        
        Session = sessionmaker(bind=engine)
        session = Session()
            
        
        for i in links:
            file_name = os.path.basename(i)
            archivo_existente = session.query(FileRegister).filter_by(file_name=file_name).first()
            
            if archivo_existente:
                print(f'El archivo {file_name} ya esta registrado')
                pass
            else:
                print(i)
                try: 
                    df = rq(i)
                except ValueError:
                    print('Error al sacar link')
                    pass
                
                print(df.head())
                sql_write_df(df, file_name)
            
    else:
        print('No se pudo crear la DB comprueba el nombre, password y tener instalado Postgres')
        
            
    
    

if __name__ == '__main__':
    main()