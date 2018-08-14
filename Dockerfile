FROM gorialis/discord.py

WORKDIR /app
ADD . /app

RUN pip install -r requirements.txt
RUN python create_db.py

CMD ["python", "bot.py"]