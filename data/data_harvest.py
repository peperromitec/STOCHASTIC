from request import request as rq
from sql_writer import test_DB, sql_write_df
from links_ecobici import ecobici_links
import os


def main():
    db_status = test_DB()
    
    if db_status:
        links = ecobici_links()
        df=None
        
        for i in links:
            print(i)
            try: 
                df = rq(i)
            except ValueError:
                print('Error al sacar link')
                pass
            
            print(df.head())
            
            file_name = os.path.basename(i)
            sql_write_df(df, file_name)
            
    else:
        print('No se pudo crear la DB comprueba el nombre, password y tener instalado Postgres')
        
            
    
    

if __name__ == '__main__':
    main()