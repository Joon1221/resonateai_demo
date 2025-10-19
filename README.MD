Demo videos/pictures in [here](https://drive.google.com/drive/folders/14wcA5SNKy4IjDBMTsVz78vM1ZWqO4Eya?usp=sharing).

# To run front end server,

```
venv\Scripts\activate
cd frontend
npm run dev
```
Access at `http://localhost:5173/`

# To run back end server,

```
venv\Scripts\activate
cd backend
python manage.py runserver
```

# To populate database,

```
python manage.py makemigrations
python manage.py migrate
python manage.py create_timeslots
```


Main frontend file is located at `frontend/src/components/ChatWindow.vue`


Main backend file is located at `backend/api/views.py`
