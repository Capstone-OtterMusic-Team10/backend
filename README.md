# Backend

To run:
- Pull `backend`, `cd` into it
- `python -m venv venv` or `python3 -m venv venv`
- Unix: `source venv/bin/activate`; Windows: `venv\Scripts\activate`
- `pip install -r requirements.txt`

## Database Setup (Postgresql)

If you want to setup database on your local machine, follow the [Postgres Installation Guide](https://dev.to/techprane/setting-up-postgresql-for-macos-users-step-by-step-instructions-2e30)

However there has been an attempt to dockerize the database and the backend (failed). 
There are two files provided with configurations (docker-compose.yml, and Dockerfile). If you run `docker-compose up --build` both the db and backend should start, given correct .env variables.

`docker-compose up --build` fails in-between unless `docker-compose down -v` is ran.

Run this to enter database in docker and use regular SQL to populate data (if needed). 
`docker exec -it ${container_name}$ psql -U username -d database_name`

## .env

Create a .env file (python-dotenv is in requirements.txt), and add this  
if running postgres locally:  

`DATABASE_URL=postgresql://my_username:my_password@localhost:5432/database_name`  

if using Docker: 
```
POSTGRES_PASSWORD=my_password
POSTGRES_USER=my_username
POSTGRES_DB=database_name
```
