import psycopg
c = psycopg.connect(host="localhost", user="postgres", password="KayFE17$", dbname="postgres")
c.autocommit = True
existing = [r[0] for r in c.execute("SELECT datname FROM pg_database").fetchall()]
print("BANCOS EXISTENTES:", existing)
if "vrmotos" in existing:
    print("vrmotos JA EXISTE")
else:
    c.execute("CREATE DATABASE vrmotos")
    print("vrmotos CRIADO AGORA")
c.close()
